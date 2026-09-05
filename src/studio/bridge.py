"""Codex/workspace integration. Runtime receipts remain the scene authority."""
from __future__ import annotations

import collections
import os
import re
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from .codex.client import CodexStdioClient
from .codex.errors import BridgeError
from .codex.protocol import ProtocolPolicy
from .common import TERMINAL, StudioError, atomic_json, new_id, read_json
from .http import Client, serve
from .instructions import SCENE_INSTRUCTIONS
from .workspace import WorkspaceData, Workspaces


class Bridge:
    def __init__(self, paths, workspace_id, session_id, token, codex_path, client=None):
        self.paths, self.workspace_id, self.session_id = paths, workspace_id, session_id
        self.workspace = Workspaces(paths).get(workspace_id)
        self.token, self.owner_id = token, session_id
        self.data = WorkspaceData(paths, workspace_id)
        self.cwd = paths.workspace(workspace_id) / "work"
        self.lock = threading.RLock()
        self.action_lock = threading.Lock()
        self.turn_revision = 0
        self.events = collections.deque(maxlen=1500)
        self.sequence = 0
        self.thread_id = None
        self.turn_id = None
        self.codex_state = "idle"
        self.stop_requested = False
        self.owner_stopped = False
        self.completed_turns = collections.deque(maxlen=256)
        self.pending_requests = {}
        self._runtime = None
        self.server = None
        env = dict(os.environ)
        for path in (paths.local("codex-home"), paths.local("tmp")):
            path.mkdir(parents=True, exist_ok=True)
        env.update({"HIA_PROJECT_ROOT": str(paths.root), "BCS_WORKSPACE_ID": workspace_id,
                    "BCS_SESSION_ID": session_id, "BCS_OWNER_ID": self.owner_id, "BCS_SESSION_TOKEN": token,
                    "CODEX_HOME": str(paths.local("codex-home")), "PYTHONPATH": str(paths.root / "src"),
                    "TEMP": str(paths.local("tmp")), "TMP": str(paths.local("tmp"))})
        self.client = client or CodexStdioClient([str(codex_path), "app-server"], cwd=self.cwd,
                                                environment=env, policy=ProtocolPolicy(), event_sink=self.on_event)
        if client:
            self.client.set_event_sink(self.on_event)

    def start(self):
        self.server = serve(self.route, self.token)
        atomic_json(self.paths.session(self.session_id) / "bridge.json",
                    {"url": "http://127.0.0.1:" + str(self.server.server_port),
                     "workspace_id": self.workspace_id, "launcher_session_id": self.session_id})
        self.client.start()
        self.client.initialize()

    def on_event(self, event):
        with self.lock:
            method, params = event.get("method"), event.get("params", {})
            event_thread = params.get("threadId")
            # App Server may still emit events from previously loaded conversations.
            if event_thread and event_thread != self.thread_id:
                return
            if method == "turn/started":
                turn = params.get("turn", {})
                if turn.get("id") and turn["id"] not in self.completed_turns and self.turn_id in {None, turn["id"]}:
                    self.turn_id = turn.get("id")
                    self.codex_state = "stopping" if self.stop_requested else "running"
                    self.turn_revision += 1
            elif method == "turn/completed":
                turn = params.get("turn", {})
                turn_id = turn.get("id")
                known = turn_id in self.completed_turns
                if turn_id and not known:
                    self.completed_turns.append(turn_id)
                if turn_id and not known and self.turn_id in {None, turn_id}:
                    self.codex_state = turn.get("status", "unknown")
                    self.turn_id = None
                    self.turn_revision += 1
            elif event.get("type") == "process_exit":
                self.codex_state = "unavailable"
                self.pending_requests.clear()
                self.turn_revision += 1
            if event.get("type") == "server_request":
                self.pending_requests[str(event["request_id"])] = event
            if method == "serverRequest/resolved":
                self.pending_requests.pop(str(params.get("requestId")), None)
            self.sequence += 1
            self.events.append({"sequence": self.sequence, **event})

    def runtime(self):
        if self._runtime is None:
            file = self.paths.session(self.session_id) / "runtime.json"
            if not file.exists():
                raise StudioError("HOUDINI_STARTING", "Houdini has not connected yet", 503)
            descriptor = read_json(file)
            if descriptor.get("launcher_session_id") != self.session_id or descriptor.get("workspace_id") != self.workspace_id:
                raise StudioError("RUNTIME_MISMATCH", "Runtime descriptor belongs to another session", 409)
            self._runtime = Client(descriptor["url"], self.token, timeout=0.8)
        return self._runtime

    def state(self):
        try:
            runtime = {"connection": "connected", **self.runtime().call("GET", "/health")}
        except StudioError as exc:
            runtime = {"connection": "unavailable", "message": exc.message}
        with self.lock:
            return {"workspace": self.workspace, "thread_id": self.thread_id, "turn_id": self.turn_id,
                    "codex": {"state": self.codex_state, "alive": self.client.is_running,
                              "stop_requested": self.stop_requested}, "runtime": runtime,
                    "pending_requests": list(self.pending_requests.values())}

    def thread_config(self):
        executable = Path(os.environ.get("BCS_PYTHON_EXECUTABLE") or sys.executable)
        if executable.name.lower() == "pythonw.exe":
            executable = executable.with_name("python.exe")
        context_config = {}
        project_config = self.paths.root / ".codex" / "config.toml"
        if project_config.is_file():
            # Only these two simple integer settings cross into scene sessions;
            # repository development instructions and hooks remain separate.
            for key, value in re.findall(r"(?m)^\s*(model_context_window|model_auto_compact_token_limit)\s*=\s*(\d+)\s*(?:#.*)?$",
                                         project_config.read_text(encoding="utf-8")):
                context_config[key] = int(value)
        return {"cwd": str(self.cwd), "approvalPolicy": "on-request", "sandbox": "workspace-write",
                "developerInstructions": SCENE_INSTRUCTIONS,
                "config": {**context_config, "project_doc_max_bytes": 0, "mcp_servers": {"big_chicken": {
                    "command": str(executable), "args": ["-m", "studio.mcp"],
                    "env_vars": ["HIA_PROJECT_ROOT", "BCS_SESSION_ID", "BCS_WORKSPACE_ID", "BCS_SESSION_TOKEN",
                                 "BCS_OWNER_ID", "BCS_PYTHON_EXECUTABLE", "HIA_RENDER_OUTPUT_DIR", "PYTHONPATH", "TEMP", "TMP"],
                    "startup_timeout_sec": 15, "tool_timeout_sec": 30}}}}

    @contextmanager
    def action(self):
        if not self.action_lock.acquire(blocking=False):
            raise StudioError("REQUEST_PENDING", "Wait for the pending conversation request", 409)
        try:
            yield
        finally:
            self.action_lock.release()

    def select_thread(self, thread_id=None):
        with self.action():
            return self._select_thread(thread_id)

    def _select_thread(self, thread_id):
        with self.lock:
            if self.codex_state in {"running", "starting", "stopping", "unknown", "unavailable", "selecting"}:
                raise StudioError("TURN_ACTIVE", "Finish or stop the current turn before switching conversations", 409)
        config = self.thread_config()
        if thread_id:
            item = self.client.request("thread/read", {"threadId": thread_id, "includeTurns": False})["thread"]
            if Path(item.get("cwd", "")).resolve() != self.cwd.resolve():
                raise StudioError("THREAD_WORKSPACE_MISMATCH", "Conversation belongs to another workspace", 409)
            config["threadId"] = thread_id
        result = self.client.request("thread/resume" if thread_id else "thread/start", config)
        with self.lock:
            self.thread_id, self.turn_id = result["thread"]["id"], None
            self.codex_state, self.stop_requested = "idle", False
            self.pending_requests.clear()
            self.completed_turns.clear()
            self.turn_revision += 1
            self._apply_native_state(result["thread"])
        return result

    def start_turn(self, body):
        with self.action():
            return self._start_turn(body)

    def _start_turn(self, body):
        text = body.get("text", "")
        if not isinstance(text, str) or not text.strip() or len(text) > 64000:
            raise StudioError("INVALID_INPUT", "Enter a message of 1 to 64000 characters")
        inputs = [{"type": "text", "text": text}]
        attachments = body.get("attachments", [])
        if not isinstance(attachments, list) or len(attachments) > 8:
            raise StudioError("INVALID_ATTACHMENTS", "Attach at most eight images")
        for attachment in attachments:
            if not isinstance(attachment, str) or not re.fullmatch(r"[0-9a-f]{32}\.(png|jpg|jpeg|webp)", attachment):
                raise StudioError("INVALID_ATTACHMENT", "Use an attachment returned by the image picker")
            path = self.paths.local("workspaces", self.workspace_id, "attachments", attachment)
            if not path.is_file() or path.parent != self.paths.workspace(self.workspace_id) / "attachments":
                raise StudioError("ATTACHMENT_NOT_FOUND", "Reattach the missing image")
            inputs.append({"type": "localImage", "path": str(path)})
        for key in ("model", "effort"):
            if body.get(key) is not None and (not isinstance(body[key], str) or len(body[key]) > 160):
                raise StudioError("INVALID_INPUT", "Model and effort must be native advertised strings")
        with self.lock:
            if self.codex_state in {"starting", "running", "stopping", "unknown", "unavailable", "selecting"}:
                raise StudioError("TURN_ACTIVE", "Wait for native turn confirmation or reconcile the conversation", 409)
            if not self.thread_id:
                raise StudioError("THREAD_REQUIRED", "Create or select a conversation first", 409)
            if self.owner_stopped:
                try:
                    self.runtime().call("POST", "/owner/resume", {"owner_id": self.owner_id})
                    self.owner_stopped = False
                except StudioError as exc:
                    if exc.code not in {"HOUDINI_STARTING", "CONNECTION_LOST"}:
                        raise
            self.codex_state, self.stop_requested = "starting", False
        params = {"threadId": self.thread_id, "input": inputs}
        for key in ("model", "effort"):
            if body.get(key):
                params[key] = body[key]
        try:
            result = self.client.request("turn/start", params)
        except Exception:
            with self.lock:
                if self.codex_state in {"starting", "stopping"} and not self.turn_id:
                    self.codex_state = "unknown"  # A timed-out start may still have begun.
            raise
        with self.lock:
            turn_id = result["turn"]["id"]
            if turn_id not in self.completed_turns:
                self.turn_id = turn_id
                self.codex_state = "stopping" if self.stop_requested else "running"
            should_interrupt = self.stop_requested and self.turn_id is not None
        if should_interrupt:
            self.client.request("turn/interrupt", {"threadId": self.thread_id, "turnId": turn_id})
        return result

    def reconcile(self):
        """Read native Codex state; this never infers a Houdini mutation outcome."""
        with self.action():
            with self.lock:
                thread_id, revision = self.thread_id, self.turn_revision
            if not thread_id:
                return {"reconciled": False, "message": "Select a native conversation first"}
            value = self.read_thread(thread_id)
            with self.lock:
                fresh = revision == self.turn_revision
                if fresh:
                    self._apply_native_state(value["thread"])
                turn_id = self.turn_id if self.stop_requested else None
            if turn_id:
                self.client.request("turn/interrupt", {"threadId": thread_id, "turnId": turn_id})
            return {**value, "reconciled": fresh, "codex_state": self.codex_state}

    def read_thread(self, thread_id):
        try:
            return self.client.request("thread/read", {"threadId": thread_id, "includeTurns": True})
        except BridgeError as exc:
            # 0.153.4's in-memory store cannot list turns before the first
            # rollout exists. Keep native metadata, never fabricate chat history.
            if exc.code != "CODEX_RPC_ERROR" or "list_turns is not supported yet" not in exc.message:
                raise
            value = self.client.request("thread/read", {"threadId": thread_id, "includeTurns": False})
            return {**value, "history_available": False,
                    "history_message": "Native conversation history is not available yet"}

    def _apply_native_state(self, thread):
        turns = thread.get("turns", [])
        latest = turns[-1] if turns else {}
        status = latest.get("status")
        live = thread.get("status", {}).get("type")
        if status == "inProgress":
            self.codex_state = "stopping" if self.stop_requested else "running"
            self.turn_id = latest.get("id")
        elif live in {"active", "systemError"}:
            self.codex_state, self.turn_id = "unknown", None
        elif status in {"completed", "interrupted", "failed"}:
            self.codex_state, self.turn_id = status, None
            self.completed_turns.append(latest.get("id"))
        elif not turns and live == "idle":
            self.codex_state, self.turn_id = "idle", None
        else:
            self.codex_state, self.turn_id = "unknown", None

    def stop(self):
        with self.lock:
            self.stop_requested = True
            self.owner_stopped = True
            if self.codex_state in {"running", "starting"}:
                self.codex_state = "stopping"
            turn_id, thread_id = self.turn_id, self.thread_id
        try:
            scene = self.runtime().call("POST", "/owner/stop", {"owner_id": self.owner_id})
        except StudioError as exc:
            scene = {"confirmed": False, "message": exc.message}
        error = None
        if turn_id:
            try:
                self.client.request("turn/interrupt", {"threadId": thread_id, "turnId": turn_id})
            except BridgeError as exc:
                error = str(exc)
        return {"codex_interrupt_requested": bool(turn_id), "codex_interrupt_error": error,
                "scene": scene, "message": "Stop requested; check the runtime receipt for current HOM work"}

    def selection(self):
        """An explicit Panel read, independent of the MCP observation binding."""
        runtime = self.runtime()
        identity = runtime.call("GET", "/health")
        op_id = new_id()
        operation = {"operation_id": op_id, "workspace_id": self.workspace_id,
                     "runtime_id": identity["runtime_id"], "owner_id": self.owner_id,
                     "scene_epoch": None, "kind": "context", "arguments": {}, "label": "Panel selection"}
        deadline = time.monotonic() + 0.65
        try:
            value = runtime.call("POST", "/operations", operation, timeout=0.3)
            while value.get("state") not in TERMINAL and time.monotonic() < deadline:
                time.sleep(0.05)
                value = runtime.call("GET", "/operations/" + op_id, timeout=0.2)
        except StudioError as exc:
            if exc.code != "CONNECTION_LOST":
                raise
            return {"operation_id": op_id, "state": "unknown"}
        if value.get("state") == "finished":
            return {"operation_id": op_id, "nodes": value.get("result", {}).get("selected", []),
                    "scene_epoch": value.get("result", {}).get("scene_epoch", value.get("scene_epoch")),
                    "state": "finished"}
        return value

    def attach(self, source):
        path = Path(source).resolve()
        if path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"} or not path.is_file():
            raise StudioError("IMAGE_REQUIRED", "Choose a PNG, JPEG or WebP image")
        if path.stat().st_size > 12 * 1024 * 1024:
            raise StudioError("IMAGE_TOO_LARGE", "Use an image smaller than 12 MB")
        raw = path.read_bytes()
        if not (raw.startswith(b"\x89PNG\r\n\x1a\n") or raw.startswith(b"\xff\xd8\xff") or
                raw.startswith(b"RIFF") and raw[8:12] == b"WEBP"):
            raise StudioError("IMAGE_INVALID", "The selected file is not a supported image")
        folder = self.paths.workspace(self.workspace_id) / "attachments"
        folder.mkdir(exist_ok=True)
        name = new_id() + path.suffix.lower()
        with (folder / name).open("xb") as stream:
            stream.write(raw)
        return {"attachment_id": name, "name": path.name, "path": str(folder / name)}

    def route(self, method, path, query, body):
        try:
            if method == "GET" and path == "/state":
                return self.state()
            if method == "GET" and path == "/events":
                cursor = int(query.get("after", [0])[0])
                with self.lock:
                    gap = bool(self.events and cursor and cursor < self.events[0]["sequence"] - 1)
                    events = [e for e in self.events if e["sequence"] > cursor][:100]
                    return {"events": events, "cursor": events[-1]["sequence"] if events else self.sequence,
                            "resync_required": gap}
            if method == "GET" and path == "/operations":
                return self.runtime().call("GET", "/operations")
            if path.startswith("/operations/"):
                suffix = "?offset=" + str(int(query.get("offset", [0])[0])) if path.endswith("/detail") else ""
                return self.runtime().call(method, path + suffix, body if method == "POST" else None)
            if method == "POST" and path == "/memory":
                return self.data.memory(body["action"], **{k: v for k, v in body.items() if k != "action"})
            if method == "POST" and path == "/lookup":
                return self.data.lookup(body.get("query", ""), body.get("version"))
            if method == "POST" and path == "/threads/select":
                return self.select_thread(body.get("thread_id"))
            if method == "GET" and path == "/threads":
                result = self.client.request("thread/list", {"cwd": str(self.cwd), "limit": 50})
                result["data"] = [t for t in result.get("data", []) if Path(t.get("cwd", "")).resolve() == self.cwd.resolve()]
                return result
            if method == "GET" and path == "/thread":
                if not self.thread_id:
                    return {"thread": None}
                return self.read_thread(self.thread_id)
            if method == "POST" and path == "/reconcile":
                return self.reconcile()
            if method == "POST" and path == "/selection":
                return self.selection()
            if method == "POST" and path == "/turn":
                return self.start_turn(body)
            if method == "POST" and path == "/stop":
                return self.stop()
            if method == "POST" and path == "/attachments":
                return self.attach(body["path"])
            if method == "GET" and path == "/models":
                return self.client.request("model/list", {})
            if method == "GET" and path == "/account":
                return self.client.request("account/read", {"refreshToken": False})
            if method == "POST" and path == "/account/login":
                return self.client.request("account/login/start", {"type": "chatgpt"})
            if method == "POST" and path == "/requests/respond":
                request_id = str(body["request_id"])
                with self.lock:
                    request = self.pending_requests.get(request_id)
                if request is None:
                    raise StudioError("REQUEST_EXPIRED", "This request is no longer pending", 409)
                self.client.respond_to_server_request(request["request_id"], body["result"])
                with self.lock:
                    self.pending_requests.pop(request_id, None)
                return {"responded": True}
        except BridgeError as exc:
            raise StudioError(exc.code, exc.message, exc.http_status) from exc
        raise StudioError("ROUTE_NOT_FOUND", "Unknown bridge route", 404)

    def close(self):
        self.client.close(grace_seconds=1)
        if self.server:
            self.server.shutdown()
            self.server.server_close()
