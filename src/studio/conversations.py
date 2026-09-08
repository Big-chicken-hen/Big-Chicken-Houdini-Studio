"""Workspace-scoped projections of native conversation lifecycle, without a store."""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3

from .codex.errors import BridgeError
from .common import StudioError, identifier


NOTIFICATIONS = {"thread/name/updated": "rename", "thread/archived": "archive",
                 "thread/unarchived": "unarchive", "thread/deleted": "delete"}
METHODS = {"rename": "thread/name/set", "archive": "thread/archive",
           "unarchive": "thread/unarchive", "delete": "thread/delete"}


class Conversations:
    def __init__(self, bridge):
        self.bridge = bridge
        self.revision = 0
        self.known = set()
        self.deleted = set()
        self.pending = {}

    def snapshot(self):
        return {"revision": self.revision, "deleted": sorted(self.deleted),
                "pending": [dict(value) for value in self.pending.values()]}

    def blocked(self, thread_id):
        return self.pending.get(thread_id, {}).get("action") in {"archive", "delete"}

    def scope(self, thread, expected=None):
        thread_id = thread.get("id")
        if (not isinstance(thread_id, str) or expected is not None and thread_id != expected or
                not thread.get("cwd") or Path(thread["cwd"]).resolve() != self.bridge.cwd.resolve()):
            raise StudioError("THREAD_WORKSPACE_MISMATCH", "Conversation belongs to another workspace", 409)
        identifier(thread_id)
        with self.bridge.lock:
            self.known.add(thread_id)
        return thread

    def read(self, thread_id):
        identifier(thread_id)
        return self.scope(self.bridge.client.request("thread/read", {
            "threadId": thread_id, "includeTurns": False})["thread"], thread_id)

    def listing(self, query):
        params = {"cwd": str(self.bridge.cwd), "limit": 50, "sortKey": "updated_at", "sortDirection": "desc"}
        for source, target, bound in (("cursor", "cursor", 4096), ("search", "searchTerm", 160)):
            value = query.get(source, [None])[0]
            if value is not None:
                if not isinstance(value, str) or len(value) > bound:
                    raise StudioError("INVALID_THREAD_QUERY", "Use a bounded native title search and cursor")
                if value:
                    params[target] = value
        archived = query.get("archived", ["false"])[0]
        if archived not in {"true", "false"}:
            raise StudioError("INVALID_THREAD_QUERY", "archived must be true or false")
        params["archived"] = archived == "true"
        with self.bridge.lock:
            revision = self.revision
        value = self.bridge.client.request("thread/list", params)
        rows = []
        for row in value.get("data", []):
            if row.get("cwd") and Path(row["cwd"]).resolve() == self.bridge.cwd.resolve():
                rows.append(self.scope(row))
        return {"data": rows, "nextCursor": value.get("nextCursor"), "lifecycle_revision": revision}

    def observe(self, method, params):
        action = NOTIFICATIONS.get(method)
        if not action:
            return False
        thread_id = params.get("threadId")
        self.revision += 1  # Unknown-scope notifications only invalidate native lists.
        if thread_id not in self.known and thread_id != self.bridge.thread_id:
            return False
        self.confirm(thread_id, action, params.get("threadName"))
        return True

    def confirm(self, thread_id, action, name=None):
        pending = self.pending.get(thread_id)
        if pending and pending["action"] == action and (action != "rename" or name == pending.get("name")):
            self.pending.pop(thread_id)
        if action == "delete":
            self.deleted.add(thread_id)
        self.revision += 1
        if action in {"delete", "archive"} and thread_id == self.bridge.thread_id:
            bridge = self.bridge
            bridge.scene_trust.reset()
            bridge.thread_id = bridge.turn_id = bridge.thread_scene_epoch = None
            bridge.new_scene_thread = False
            bridge.codex_state, bridge.stop_requested = "idle", False
            bridge.pending_requests.clear()
            bridge.settings.bind(None, {})
            bridge.turn_revision += 1

    def deletion_gate(self, thread_id):
        bridge = self.bridge
        if thread_id != bridge.thread_id:
            return
        with bridge.lock:
            if (bridge._has_unknown_response() or bridge.pending_requests or bridge.turn_id or
                    bridge.codex_state in {"running", "starting", "stopping", "unknown", "unavailable", "selecting"}):
                raise StudioError("THREAD_BUSY", "等待当前轮次、许可和执行结果确认后再删除。", 409)
        descriptor = bridge.paths.session(bridge.session_id) / "runtime.json"
        if descriptor.is_file() or bridge._runtime is not None:
            health = bridge.runtime().call("GET", "/health")
            if health.get("main_thread_busy") or health.get("queue_depth") or health.get("storage_fault"):
                raise StudioError("THREAD_OPERATIONS_PENDING", "相关 Houdini 操作尚未结束或收据未确认。", 409)
        # Read only the runtime's durable receipts, including unknown rows older
        # than the compact /operations list. No write, recovery or scene access.
        ledger = bridge.paths.workspace(bridge.workspace_id) / "operations.sqlite"
        if ledger.is_file():
            try:
                with sqlite3.connect(ledger.resolve().as_uri() + "?mode=ro", uri=True) as db:
                    rows = db.execute("SELECT receipt FROM operations WHERE "
                                      "json_extract(receipt, '$.owner_id')=? AND "
                                      "json_extract(receipt, '$.state') IN ('queued','running','unknown') LIMIT 1",
                                      (bridge.owner_id,)).fetchall()
                if rows:
                    receipt = json.loads(rows[0][0])
                    raise StudioError("THREAD_OPERATIONS_PENDING", "相关 Houdini 收据尚未确认。", 409,
                                      operation_id=receipt["operation_id"])
            except sqlite3.Error as exc:
                raise StudioError("THREAD_OPERATIONS_UNKNOWN", "暂时无法核对 Houdini 收据，保留当前对话。", 409) from exc

    def mutate(self, body):
        action, thread_id = body.get("action"), body.get("thread_id")
        if action not in METHODS:
            raise StudioError("INVALID_THREAD_ACTION", "Unknown native conversation action")
        identifier(thread_id)
        if action == "delete" and body.get("confirm_delete_with_descendants") is not True:
            raise StudioError("DELETE_CONFIRMATION_REQUIRED", "删除不可恢复，原生删除也可能影响派生子对话。", 409)
        name = body.get("name")
        if action == "rename" and (not isinstance(name, str) or not name.strip() or len(name) > 160):
            raise StudioError("INVALID_THREAD_NAME", "请输入 1 至 160 字的对话标题。")
        bridge = self.bridge
        with bridge.action():
            with bridge.lock:
                if thread_id in self.pending:
                    raise StudioError("THREAD_MUTATION_UNKNOWN", "先核对上次原生操作结果，不能重复提交。", 409)
            thread = self.read(thread_id)
            if action in {"delete", "archive"}:
                self.deletion_gate(thread_id)
                if thread.get("status", {}).get("type") == "active":
                    raise StudioError("THREAD_BUSY", "此对话仍在运行，请先停止并确认结果。", 409)
            params = {"threadId": thread_id}
            if action == "rename":
                params["name"] = name.strip()
            pending = {"thread_id": thread_id, "action": action, "state": "pending",
                       "title": thread.get("name") or thread.get("preview") or "未命名对话"}
            if action == "rename":
                pending["name"] = params["name"]
            with bridge.lock:
                self.pending[thread_id] = pending
            try:
                response = bridge.client.request(METHODS[action], params)
                if action == "unarchive":
                    self.scope(response["thread"], thread_id)
            except Exception as exc:
                with bridge.lock:
                    if self.pending.get(thread_id) is not pending:
                        return {"confirmed": True, "thread_id": thread_id, "action": action,
                                "conversations": self.snapshot()}
                    if isinstance(exc, BridgeError) and exc.code == "CODEX_RPC_ERROR":
                        self.pending.pop(thread_id)
                        raise
                    pending["state"] = "unknown"
                    if action in {"archive", "delete"} and bridge.thread_id == thread_id:
                        bridge.codex_state = "unknown"
                        bridge.scene_trust.reset()
                    self.revision += 1
                return {"confirmed": False, "thread_id": thread_id, "action": action,
                        "message": "原生响应未确认；请核对结果，暂不重复提交。", "conversations": self.snapshot()}
            with bridge.lock:
                self.confirm(thread_id, action, params.get("name"))
                return {"confirmed": True, "thread_id": thread_id, "action": action,
                        "conversations": self.snapshot()}

    def reconcile(self, body):
        thread_id = identifier(body.get("thread_id"))
        bridge = self.bridge
        with bridge.action():
            with bridge.lock:
                pending = self.pending.get(thread_id)
                if pending is None:
                    return {"conversations": self.snapshot()}
                pending = dict(pending)
            action = pending["action"]
            # A positive scoped read can confirm a name. A positive archived-list
            # membership can confirm archive/restore. Absence NEVER proves delete.
            confirmed = False
            try:
                thread = self.read(thread_id)
                if action == "rename":
                    confirmed = thread.get("name") == pending["name"]
            except BridgeError:
                thread = None
            if action in {"archive", "unarchive"}:
                query = {"archived": ["true" if action == "archive" else "false"]}
                for _ in range(8):
                    page = self.listing(query)
                    if any(row["id"] == thread_id for row in page["data"]):
                        confirmed = True
                        break
                    if not page["nextCursor"]:
                        break
                    query["cursor"] = [page["nextCursor"]]
            with bridge.lock:
                if confirmed:
                    self.confirm(thread_id, action, pending.get("name"))
                return {"confirmed": thread_id not in self.pending, "thread_id": thread_id, "action": action,
                        "native_thread_present": thread is not None, "conversations": self.snapshot()}
