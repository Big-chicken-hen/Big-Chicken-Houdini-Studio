"""Codex/workspace integration. Runtime receipts remain the scene authority."""
from __future__ import annotations

import collections
import copy
import os
import re
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from .accounts import NativeAccount
from .codex.client import CodexStdioClient
from .codex.errors import BridgeError
from .codex.protocol import ProtocolPolicy, steer_rejection_reason
from .codex.settings import ModelCatalog, NativeSettings
from .codex.trust import SessionTrust, STUDIO_TOOLS
from .common import TERMINAL, StudioError, atomic_json, new_id, read_json, payload_hash
from .conversations import Conversations, NOTIFICATIONS
from .http import Client, serve
from .history import NativeHistory
from .instructions import SCENE_INSTRUCTIONS
from .launcher import codex_app_server_command, helper_environment
from .workspace import WorkspaceData, Workspaces
from .submissions import UserSubmissions


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
        self.start_submission_id = None
        self.codex_state = "idle"
        self.stop_requested = False
        self.owner_stopped = False
        self.completed_turns = collections.deque(maxlen=256)
        self.pending_requests = {}
        self.conversations = Conversations(self)
        self.history = NativeHistory(self)
        self.submissions = UserSubmissions(paths.workspace(workspace_id) / "pending-user-input.json")
        self.submission_tickets = {}
        self.scene_trust = SessionTrust()
        self.settings = NativeSettings()
        self.scene_epoch = self.scene_runtime_id = self.thread_scene_epoch = None
        self.new_scene_thread = False
        self.account = self.models = None
        self._runtime = None
        self.server = None
        env = helper_environment(paths)
        for path in (paths.codex_home, paths.cache("tmp")):
            path.mkdir(parents=True, exist_ok=True)
        env.update({"HIA_PROJECT_ROOT": str(paths.root), "BCS_WORKSPACE_ID": workspace_id,
                    "BCS_SESSION_ID": session_id, "BCS_OWNER_ID": self.owner_id, "BCS_SESSION_TOKEN": token,
                    "BCS_DATA_ROOT": str(paths.data_root), "BCS_CACHE_ROOT": str(paths.cache_root),
                    "CODEX_HOME": str(paths.codex_home), "PYTHONPATH": str(paths.root / "src"),
                    "TEMP": str(paths.cache("tmp")), "TMP": str(paths.cache("tmp"))})
        self.client = client or CodexStdioClient(codex_app_server_command(codex_path), cwd=self.cwd,
                                                environment=env, policy=ProtocolPolicy(), event_sink=self.on_event)
        self.account = NativeAccount(self.client)
        self.models = ModelCatalog(self.client, lambda: self.account.revision)
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
        # A possible delegated approval checks only Runtime's cached health.
        # Do not wait on RPC while holding the Bridge lock or touch HOM here.
        approval_runtime = None
        if event.get("type") == "server_request" and self.scene_trust.enabled:
            try:
                approval_runtime = {"connection": "connected", **self.runtime().call("GET", "/health", timeout=0.3)}
            except StudioError:
                approval_runtime = {"connection": "unavailable"}
        with self.lock:
            method, params = event.get("method"), event.get("params", {})
            if event.get("type") == "process_started":
                self.start_submission_id = None
                self.history.reset()
                self.submissions.reset_generation(self.history.generation)
                self.events.clear()  # Retire only the old connection's transient event ring.
            event_thread = params.get("threadId")
            if method in {"item/started", "item/completed"}:
                self._confirm_user_item(event_thread, params.get("turnId"), params.get("item"),
                                        self.history.generation)
            if method in NOTIFICATIONS:
                if self.conversations.observe(method, params):
                    self.sequence += 1
                    self.events.append({"sequence": self.sequence, **event})
                return
            # App Server may still emit events from previously loaded conversations.
            if event_thread and event_thread != self.thread_id:
                return
            if self.account:
                account_revision = self.account.revision
                self.account.observe(event)
                if self.account.revision != account_revision:
                    self.scene_trust.reset()
                    self.models.invalidate()
            if approval_runtime is not None:
                self._observe_scene(approval_runtime)
            if method == "turn/started":
                turn = params.get("turn", {})
                if turn.get("id") and turn["id"] not in self.completed_turns and self.turn_id in {None, turn["id"]}:
                    self.turn_id = turn.get("id")
                    self.codex_state = "stopping" if self.stop_requested else "running"
                    self.turn_revision += 1
                    self.settings.admitted(self.turn_id)
            elif method == "turn/completed":
                turn = params.get("turn", {})
                turn_id = turn.get("id")
                known = turn_id in self.completed_turns
                if turn_id and not known:
                    self.completed_turns.append(turn_id)
                if turn_id and not known and self.turn_id in {None, turn_id}:
                    self.codex_state = turn.get("status", "unknown")
                    self.turn_id = None
                    self.start_submission_id = None
                    self.turn_revision += 1
                if turn_id and turn.get("status") in {"completed", "interrupted", "failed"}:
                    # An authoritative terminal event closes this turn's native
                    # requests, including when a read already saw its status.
                    # A metadata-only idle read is not such evidence.
                    self.pending_requests = {
                        key: request for key, request in self.pending_requests.items()
                        if request.get("params", {}).get("turnId") != turn_id
                    }
            elif event.get("type") == "process_exit":
                self.codex_state = "unavailable"
                self.pending_requests.clear()
                self.turn_revision += 1
            elif method == "model/rerouted":
                self.settings.rerouted(params)
            if event.get("type") in {"process_started", "process_exit", "process_stopped"}:
                self.scene_trust.reset()
                self.pending_requests.clear()
            self.scene_trust.observe(method, params, self.turn_id)
            if event.get("type") == "server_request":
                request_id = str(event["request_id"])
                previous = self.pending_requests.get(request_id)
                call_id, reason = self.scene_trust.match_reason(event, self.thread_id, self.turn_id)
                reason = self._trust_reason(approval_runtime) or reason
                event = previous or {**event, "trust_reason": reason}
                self.pending_requests[request_id] = event
                # Opening consent never answers a request that was already pending.
                if previous is None and call_id and reason is None:
                    try:
                        # Client registers the pending request before invoking this sink.
                        # The lock orders this single response against explicit revocation;
                        # no RPC wait, HOM queue or user wait occurs under it.
                        self._respond_request(str(event["request_id"]), {"action": "accept", "content": {}})
                        event = {**event, "studio_trust_applied": True}
                    except Exception:
                        # A failed write may have reached Codex. Retain the request as
                        # unknown, disable further delegation, and never resend it.
                        event = {**event, "response_state": "unknown", "trust_reason": "response_unknown"}
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
            self._observe_scene(runtime)
            return {"workspace": self.workspace, "thread_id": self.thread_id, "turn_id": self.turn_id,
                    "turn_revision": self.turn_revision,
                    "connection_generation": self.history.generation,
                    "codex": {"state": self.codex_state, "alive": self.client.is_running,
                              "stop_requested": self.stop_requested}, "runtime": runtime,
                    "scene_trust": self._scene_trust_state(runtime),
                    "scene_context": {"thread_id": self.thread_id, "scene_epoch": self.thread_scene_epoch,
                                      "current_scene_epoch": self.scene_epoch,
                                      "changed": bool(self.thread_id and self.scene_epoch and
                                                      self.thread_scene_epoch != self.scene_epoch)},
                    **self.settings.snapshot(), "account_revision": self.account.revision,
                    "conversations": self.conversations.snapshot(),
                    **self._submission_snapshot(),
                    "pending_requests": list(self.pending_requests.values())}

    def _observe_scene(self, runtime):
        if runtime.get("connection") != "connected":
            return
        epoch = runtime.get("scene", {}).get("scene_epoch")
        runtime_id = runtime.get("runtime_id")
        if not epoch or not runtime_id:
            return
        if self.scene_epoch is not None and (epoch != self.scene_epoch or runtime_id != self.scene_runtime_id):
            self.scene_trust.reset()
        self.scene_epoch, self.scene_runtime_id = epoch, runtime_id
        if self.new_scene_thread and self.thread_scene_epoch is None:
            self.thread_scene_epoch = epoch

    def _trust_matches(self, runtime):
        return bool(runtime and runtime.get("connection") == "connected" and
                    runtime.get("runtime_id") == self.scene_trust.runtime_id and
                    runtime.get("scene", {}).get("scene_epoch") == self.scene_trust.scene_epoch and
                    self.scene_trust.scene_epoch)

    def _trust_reason(self, runtime):
        if self._has_unknown_response():
            return "response_unknown"
        if self.stop_requested:
            return "stop_requested"
        if not self.scene_trust.enabled:
            return self.scene_trust.reset_reason
        if not runtime or runtime.get("connection") != "connected":
            return "runtime_unavailable"
        if self.codex_state != "running" or not self._trust_matches(runtime):
            return "scope_changed"
        return None

    def _scene_trust_state(self, runtime=None):
        reason = ""
        if not self.thread_id:
            reason = "请先新建或选择对话。"
        elif self.conversations.blocked(self.thread_id):
            reason = "等待此对话的归档或删除结果确认。"
        elif self.action_lock.locked():
            reason = "等待当前对话请求完成后启用许可。"
        elif self._has_unknown_response():
            reason = "上次许可回复尚未确认，请等待原生请求结论。"
        elif not self.client.is_running or self.codex_state in {"unknown", "unavailable", "selecting"}:
            reason = "等待当前对话状态确认后启用许可。"
        elif self.stop_requested:
            reason = "停止请求后，请先确认当前工作状态。"
        elif runtime is not None and runtime.get("connection") != "connected":
            reason = "等待当前 Houdini 连接后启用许可。"
        elif (not self.scene_epoch or not self.scene_runtime_id or runtime is not None and
              (not runtime.get("scene", {}).get("scene_epoch") or not runtime.get("runtime_id"))):
            reason = "等待当前场景身份确认后启用许可。"
        return {"enabled": self.scene_trust.enabled, "thread_id": self.thread_id,
                "scene_epoch": self.scene_trust.scene_epoch, "runtime_id": self.scene_trust.runtime_id,
                "revision": self.scene_trust.revision, "available": not reason,
                "can_change": self.scene_trust.enabled or not reason, "reason": reason,
                "pending": False, "tools": list(STUDIO_TOOLS),
                "effect": "撤销立即停止后续自动许可；已许可或已接纳的 Houdini 操作仍以执行收据为准。"}

    def _has_unknown_response(self):
        return any(request.get("response_state") == "unknown" for request in self.pending_requests.values())

    def set_scene_trust(self, body):
        enabled, revision = body.get("enabled"), body.get("revision")
        if type(enabled) is not bool or type(revision) is not int:
            raise StudioError("INVALID_TRUST", "Supply enabled and the displayed permission revision")
        # Grant can read cached Runtime health; revocation never waits on Houdini.
        runtime = self.state()["runtime"] if enabled else None
        with self.lock:
            if (not self.thread_id or body.get("thread_id") != self.thread_id or
                    revision != self.scene_trust.revision):
                raise StudioError("TRUST_STALE", "对话或许可已变化，请刷新后重新选择。", 409)
            state = self._scene_trust_state(runtime)
            if enabled and not state["available"]:
                raise StudioError("TRUST_UNAVAILABLE", state["reason"], 409)
            self.scene_trust.change(enabled, self.scene_epoch, self.scene_runtime_id)
            if enabled:
                self.thread_scene_epoch = self.scene_epoch
            # A pending native approval stays pending. Enabling only applies to
            # future requests; it never replays an earlier approval response.
            return {"scene_trust": self._scene_trust_state(runtime)}

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
        return {"cwd": str(self.cwd), "approvalPolicy": "on-request", "approvalsReviewer": "user",
                "sandbox": "workspace-write",
                "developerInstructions": SCENE_INSTRUCTIONS,
                "config": {**context_config, "project_doc_max_bytes": 0, "mcp_servers": {"big_chicken": {
                    "command": str(executable), "args": ["-m", "studio.mcp"],
                    "env_vars": ["HIA_PROJECT_ROOT", "BCS_SESSION_ID", "BCS_WORKSPACE_ID", "BCS_SESSION_TOKEN",
                                 "BCS_OWNER_ID", "BCS_PYTHON_EXECUTABLE", "BCS_DATA_ROOT", "BCS_CACHE_ROOT",
                                 "PYTHONPATH", "TEMP", "TMP"],
                    "startup_timeout_sec": 15, "tool_timeout_sec": 30,
                    # Native session/persistent grants cannot be revoked in-place
                    # in 0.153.4. Keep every batch promptable; Studio delegates only
                    # precisely correlated single approvals after explicit consent.
                    "default_tools_approval_mode": "prompt",
                    "tools": {name: {"approval_mode": "prompt"} for name in STUDIO_TOOLS}}}}}

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
            if self.submissions.unresolved() and thread_id != self.thread_id:
                raise StudioError("INPUT_RESULT_UNKNOWN", "先核对原发送结果，再切换对话。", 409)
            if self.conversations.blocked(self.thread_id) or self.conversations.blocked(thread_id):
                raise StudioError("THREAD_MUTATION_UNKNOWN", "先核对原生归档或删除结果，再切换对话。", 409)
            if self._has_unknown_response():
                raise StudioError("APPROVAL_RESPONSE_UNKNOWN", "上次许可回复尚未确认，暂不能切换对话。", 409)
            if self.codex_state in {"running", "starting", "stopping", "unknown", "unavailable", "selecting"}:
                raise StudioError("TURN_ACTIVE", "Finish or stop the current turn before switching conversations", 409)
        config = self.thread_config()
        if thread_id:
            self.conversations.read(thread_id)
            config["threadId"] = thread_id
        with self.lock:
            self.scene_trust.reset()
            self.codex_state = "selecting"
        try:
            result = self.client.request("thread/resume" if thread_id else "thread/start", config)
            self.conversations.scope(result["thread"], thread_id)
        except Exception:
            with self.lock:
                self.codex_state = "unknown"
            raise
        with self.lock:
            self.scene_trust.reset()
            self.thread_id, self.turn_id = result["thread"]["id"], None
            self.start_submission_id = None
            self.settings.bind(self.thread_id, result)
            self.new_scene_thread = not thread_id
            self.thread_scene_epoch = self.scene_epoch if self.new_scene_thread else None
            self.codex_state, self.stop_requested = "idle", False
            self.pending_requests.clear()
            self.completed_turns.clear()
            self.turn_revision += 1
            self._apply_native_state(result["thread"])
        return {**result, "thread_settings": self.settings.snapshot()["thread_settings"]}

    def start_turn(self, body):
        if "client_user_message_id" in body:
            return self._submit_user_input(body, "start")
        try:
            with self.action():
                with self.lock:
                    if self.submissions.unresolved() or self.submissions.fault:
                        raise StudioError("INPUT_RESULT_UNKNOWN", "先核对原发送结果，再开始下一轮。", 409)
                return self._start_turn(body)
        except StudioError as exc:
            # These validation/owner-fence failures occur before turn/start.
            raise StudioError(exc.code, exc.message, exc.status,
                              **{**exc.details, "submission_state": "not_submitted"}) from exc

    def _account_identity(self, snapshot=None):
        account = (snapshot if snapshot is not None else self.account.snapshot()).get("account") or {}
        return payload_hash({"type": account.get("type"), "email": account["email"]}) if account.get("email") else None

    def _public_submission(self, record):
        value = self.submissions.public(record)
        if value is None:
            return None
        # The saved account revision is a process-local counter, not identity.
        # Grant only a read/recovery projection for the presently confirmed owner;
        # the original message ID, connection and account revision remain frozen.
        account = self.account.snapshot()
        owned = (self.client.is_running and account.get("status") == "signed_in"
                 and record.get("account_identity") and record["account_identity"] == self._account_identity(account))
        value["recovery_binding"] = ({"connection_generation": self.history.generation,
                                      "account_revision": account["account_revision"]} if owned else None)
        if not owned:
            value.pop("snapshot", None)
        return value

    def _submission_snapshot(self):
        value = self.submissions.snapshot(self.thread_id)
        for key in ("user_submission", "unresolved_submissions"):
            records = value[key] if isinstance(value[key], list) else [value[key]]
            projected = [self._public_submission(self.submissions.records.get(record["client_user_message_id"]))
                         for record in records if record]
            value[key] = projected if isinstance(value[key], list) else next(iter(projected), None)
        return value

    def _submission_response(self, record):
        value = {"connection_generation": self.history.generation,
                 "submission": self._public_submission(record)}
        if record.get("turn_id"):
            value["turnId"] = record["turn_id"]
            if record["intent"] == "start":
                # Acceptance is separate from liveness. This envelope never
                # turns a completed Turn back into an in-progress native fact.
                value["turn"] = {"id": record["turn_id"]}
                if (record["connection_generation"] == self.history.generation
                        and record["thread_id"] == self.thread_id):
                    value["turn_settings"] = self.settings.snapshot()["turn_settings"]
        return value

    def _check_user_admission(self, body, intent, record):
        if body.get("connection_generation") != self.history.generation:
            raise StudioError("INPUT_CONNECTION_CHANGED", "连接已变化，原内容已保留；请先核对原发送。", 409)
        if not self.client.is_running or self.account.snapshot().get("status") != "signed_in":
            raise StudioError("ACCOUNT_UNCONFIRMED", "请先确认当前 ChatGPT 连接。", 409)
        if type(body.get("account_revision")) is not int or body["account_revision"] != self.account.revision:
            raise StudioError("ACCOUNT_CHANGED", "账号已变化，原内容已保留。", 409)
        if not self.thread_id or body.get("expected_thread_id") != self.thread_id:
            raise StudioError("THREAD_SELECTION_STALE", "当前任务所属对话已变化，内容已保留。", 409)
        if intent == "start" and (type(body.get("expected_turn_revision")) is not int or body["expected_turn_revision"] != self.turn_revision):
            raise StudioError("TURN_STATE_CHANGED", "点击发送时的任务状态已变化，内容已保留；请重新确认。", 409)
        if self.conversations.blocked(self.thread_id) or self.thread_id in self.conversations.deleted:
            raise StudioError("THREAD_MUTATION_UNKNOWN", "先核对对话的归档或删除结果。", 409)
        if self._has_unknown_response():
            raise StudioError("APPROVAL_RESPONSE_UNKNOWN", "上次许可回应尚未确认，请先核对原请求。", 409)
        if self.submissions.fault:
            raise StudioError("INPUT_STORAGE_UNCONFIRMED", self.submissions.fault, 503)
        if any(item is not record for item in self.submissions.unresolved()):
            raise StudioError("INPUT_RESULT_UNKNOWN", "另一条发送的接纳结果尚未确认；这份内容已保留。", 409)
        if intent == "steer":
            if self.stop_requested:
                raise StudioError("STOP_REQUESTED", "已请求停止，这条引导没有发送；内容已保留。", 409)
            expected = body.get("expected_turn_id")
            if not isinstance(expected, str) or not expected:
                raise StudioError("TURN_ID_REQUIRED", "活动任务身份尚未确认，内容已保留。", 409)
            if self.turn_id and expected != self.turn_id:
                raise StudioError("STEER_TURN_CHANGED", "当前任务已变化，这条引导没有发送；请确认目标后再次发送。", 409)
            if expected in self.completed_turns or not self.turn_id and self.codex_state in {"idle", "completed", "interrupted", "failed"}:
                raise StudioError("STEER_TURN_ENDED", "原任务已结束，这条引导没有发送。内容已保留；再次发送将开始下一轮。", 409)
            if self.codex_state != "running" or self.turn_id != expected:
                raise StudioError("TURN_UNCONFIRMED", "原任务身份尚未确认，内容已保留；请先查询状态。", 409)
        else:
            self.settings.check_binding(body, self.thread_id)
            if self.codex_state in {"starting", "running", "stopping", "unknown", "unavailable", "selecting"} or self.turn_id:
                raise StudioError("TURN_ACTIVE", "任务状态已变化，这条新任务没有发送；请重新确认。", 409)

    def _user_inputs(self, body, intent):
        text, attachments = body.get("text"), body.get("attachments", [])
        if not isinstance(text, str) or not text.strip() or len(text) > 64000:
            raise StudioError("INVALID_INPUT", "Enter a message of 1 to 64000 characters")
        if not isinstance(attachments, list) or len(attachments) > 8:
            raise StudioError("INVALID_ATTACHMENTS", "Attach at most eight images")
        inputs, images = [{"type": "text", "text": text}], []
        folder = (self.paths.workspace(self.workspace_id) / "attachments").resolve()
        for attachment in attachments:
            if not isinstance(attachment, str) or not re.fullmatch(r"[0-9a-f]{32}\.(png|jpg|jpeg|webp)", attachment):
                raise StudioError("INVALID_ATTACHMENT", "Use an attachment returned by the image picker")
            path = (folder / attachment).resolve()
            if path.parent != folder or not path.is_file():
                raise StudioError("ATTACHMENT_NOT_FOUND", "Reattach the missing image")
            inputs.append({"type": "localImage", "path": str(path)})
            images.append({"attachment_id": attachment, "name": path.name, "path": str(path),
                           "status": "ready", "local_key": attachment})
        draft_text, version = body.get("draft_text", text), body.get("draft_version")
        if (not isinstance(draft_text, str) or len(draft_text) > 64000
                or version is not None and (type(version) not in {int, str} or len(str(version)) > 160)):
            raise StudioError("INVALID_DRAFT", "Use a bounded immutable draft snapshot")
        reference = body.get("selection_reference")
        if reference is not None:
            if (not isinstance(reference, dict) or not isinstance(reference.get("scene_epoch"), str)
                    or not 0 < len(reference["scene_epoch"]) <= 128 or not isinstance(reference.get("nodes"), list)
                    or not 0 < len(reference["nodes"]) <= 100
                    or any(not isinstance(path, str) or not path.startswith("/") or len(path) > 2048 for path in reference["nodes"])):
                raise StudioError("INVALID_SELECTION", "请重新确认选择引用。")
            reference = {"scene_epoch": reference["scene_epoch"], "nodes": list(reference["nodes"])}
        if intent == "steer" and any(key in body for key in (
                "model", "effort", "cwd", "sandbox", "approvalPolicy", "developerInstructions", "settings_revision")):
            raise StudioError("STEER_OVERRIDES_REJECTED", "引导只追加输入，不改变当前任务的模型或许可。")
        for key in ("model", "effort"):
            if body.get(key) is not None and (not isinstance(body[key], str) or len(body[key]) > 160):
                raise StudioError("INVALID_INPUT", "Model and effort must be native advertised strings")
        return inputs, {"text": text, "draft_text": draft_text, "draft_version": version,
                        "attachments": images, "selection_reference": reference}

    def _submission_error(self, record, error, *, forwarded=False):
        state = "unknown" if forwarded else "not_submitted"
        details = {"code": getattr(error, "code", "INPUT_UNCONFIRMED"),
                   "message": getattr(error, "message", "原发送结果尚未确认；内容已保留。"),
                   "details": getattr(error, "details", None)}
        reason = steer_rejection_reason(error, record.get("expected_turn_id")) if record["intent"] == "steer" else None
        if reason:
            state = "not_submitted"
            details["native_rejection_reason"] = reason
            if reason == "turn_ended":
                details["message"] = "原任务已结束，这条引导没有发送。内容已保留；再次发送将开始下一轮。"
            elif reason == "turn_changed":
                details["message"] = "当前任务已变化，这条引导没有发送；请确认目标后再次发送。"
        self.submissions.settle(record, state, error=details)

    def _settle_user_rpc(self, record, ticket, result, error):
        interrupt = None
        with self.lock:
            if ticket.settled:
                self.submission_tickets.pop(record["client_user_message_id"], None)
            record["forward_attempted"] = bool(ticket.forward_attempted)
            try:
                if error:
                    self._submission_error(record, error, forwarded=ticket.forward_attempted)
                else:
                    turn_id = ((result.get("turn") or {}).get("id") if record["intent"] == "start"
                               else result.get("turnId")) if isinstance(result, dict) else None
                    if not isinstance(turn_id, str) or not turn_id or (record["intent"] == "steer" and turn_id != record["expected_turn_id"]):
                        raise BridgeError("INPUT_ACK_INVALID", "原生回应没有确认原发送目标。", 502)
                    self.submissions.settle(record, "accepted", turn_id=turn_id)
                    current = (record["connection_generation"] == self.history.generation
                               and record["thread_id"] == self.thread_id
                               and record["account_revision"] == self.account.revision)
                    if (record["intent"] == "start" and current and self.start_submission_id == record["client_user_message_id"]
                            and turn_id not in self.completed_turns and self.turn_id in {None, turn_id}):
                        # Only start owns start-state binding. A steer ACK never
                        # touches Turn state, model settings, Stop or Runtime owner.
                        status = (result.get("turn") or {}).get("status", "inProgress")
                        self.settings.admitted(turn_id)
                        if status in {"completed", "interrupted", "failed"}:
                            self.completed_turns.append(turn_id)
                            self.turn_id, self.codex_state = None, status
                            self.start_submission_id = None
                        else:
                            self.turn_id = turn_id
                            self.codex_state = "stopping" if self.stop_requested else "running"
                            if self.stop_requested and not record.get("stop_interrupt_sent"):
                                record["stop_interrupt_sent"] = True
                                interrupt = (record["thread_id"], turn_id, record["connection_generation"])
                        self.turn_revision += 1
            except (BridgeError, StudioError) as failure:
                if not self.submissions.fault:
                    self._submission_error(record, failure, forwarded=ticket.forward_attempted)
            if (record["intent"] == "start" and record["state"] == "unknown" and self.codex_state == "starting"
                    and record["connection_generation"] == self.history.generation and not self.turn_id):
                self.codex_state = "unknown"
        if interrupt:
            # Do not wait for another RPC from the stdout reader callback.
            threading.Thread(target=self._interrupt_confirmed_start, args=interrupt, daemon=True).start()

    def _interrupt_confirmed_start(self, thread_id, turn_id, generation):
        with self.lock:
            current = (generation == self.history.generation and thread_id == self.thread_id
                       and turn_id == self.turn_id and self.stop_requested)
        if current:
            try:
                self.client.request("turn/interrupt", {"threadId": thread_id, "turnId": turn_id})
            except BridgeError:
                pass  # Existing Stop state/query remains authoritative, no resend.

    def _submit_user_input(self, body, intent):
        body = copy.deepcopy(body)
        with self.lock:
            if body.get("connection_generation") != self.history.generation:
                raise StudioError("INPUT_CONNECTION_CHANGED", "连接已变化；请查询原发送，不会自动重发。", 409,
                                  submission_state="not_submitted")
            record, fresh = self.submissions.remember(body, intent, self._account_identity())
            if not fresh:
                return self._submission_response(record)
            if self.submissions.unresolved() or self.action_lock.locked():
                self._submission_error(record, StudioError("INPUT_RESULT_UNKNOWN",
                    "另一条请求尚未确认；这份内容已保留，不会排队发送。", 409))
                return self._submission_response(record)
            record["state"] = "pending"
        ticket = None
        try:
            with self.action():
                with self.lock:
                    self._check_user_admission(body, intent, record)
                    model = (self.settings.turn or {}).get("model") if intent == "steer" else body.get("model") or self.settings.thread["model"]
                inputs, snapshot = self._user_inputs(body, intent)
                if intent == "start" and (body.get("model") or body.get("effort")) or body.get("attachments"):
                    if not model:
                        raise StudioError("MODEL_UNCONFIRMED", "当前任务的模型尚未确认；内容已保留。", 409)
                    self.models.validate(model, body.get("effort") if intent == "start" else None, bool(body.get("attachments")))
                health = None
                if snapshot["selection_reference"] or intent == "start":
                    try:
                        health = self.runtime().call("GET", "/health")
                    except StudioError:
                        if snapshot["selection_reference"]:
                            raise StudioError("SELECTION_UNCONFIRMED", "无法确认选择引用的场景身份；请保留输入。", 409) from None
                params = {"threadId": record["thread_id"], "clientUserMessageId": record["client_user_message_id"], "input": inputs}
                if intent == "steer":
                    params["expectedTurnId"] = record["expected_turn_id"]
                else:
                    params.update({key: body[key] for key in ("model", "effort") if body.get(key)})
                ticket = self.client.prepare_tracked_request("turn/" + intent, params,
                            lambda ticket, result, error: self._settle_user_rpc(record, ticket, result, error))
                with self.lock:
                    self.submission_tickets[record["client_user_message_id"]] = ticket
                    self._check_user_admission(body, intent, record)
                    if intent == "steer" and body.get("attachments") and model != (self.settings.turn or {}).get("model"):
                        raise StudioError("MODEL_CHANGED", "正在工作的模型已变化；请重新确认图片能力。", 409)
                    if health and snapshot["selection_reference"] and (
                            snapshot["selection_reference"]["scene_epoch"] != health.get("scene", {}).get("scene_epoch")
                            or self.scene_epoch is not None and snapshot["selection_reference"]["scene_epoch"] != self.scene_epoch):
                        raise StudioError("SELECTION_STALE", "选择引用来自先前场景，内容已保留；请重新引用或移除。", 409)
                    if intent == "start":
                        if health and (health.get("main_thread_busy") or health.get("active_operation_id") or health.get("queue_depth") or health.get("storage_fault")):
                            raise StudioError("RUNTIME_WORK_PENDING", "Houdini 原操作尚未收口，内容已保留。", 409)
                        if self.owner_stopped:
                            self.runtime().call("POST", "/owner/resume", {"owner_id": self.owner_id})
                            self.owner_stopped = False
                    self.submissions.reserve(record, snapshot)
                    if intent == "start":
                        self.start_submission_id = record["client_user_message_id"]
                        self.codex_state, self.stop_requested = "starting", False
                        self.settings.requested(self.thread_id, body)
                    # Stop uses this same short lock. RPC waiting is below,
                    # outside both the state and conversation action locks.
                    self.client.send_prepared(ticket)
                    record["forward_attempted"] = bool(ticket.forward_attempted)
            self.client.wait_prepared(ticket)
        except Exception as error:
            with self.lock:
                forwarded = bool(ticket and ticket.forward_attempted)
                record["forward_attempted"] = forwarded
                if ticket and not forwarded and not ticket.settled:
                    self.client.discard_prepared(ticket)
                if record["state"] != "accepted":
                    try:
                        self._submission_error(record, error, forwarded=forwarded)
                    except StudioError:
                        pass  # Keep the original durable snapshot, block new sends.
                if intent == "start" and self.codex_state == "starting" and not self.turn_id:
                    self.codex_state = "unknown" if forwarded else "idle"
                    if not forwarded:
                        self.start_submission_id = None
        with self.lock:
            return self._submission_response(record)

    def _confirm_user_item(self, thread_id, turn_id, item, generation, *, recovering=False):
        if not isinstance(item, dict) or item.get("type") != "userMessage" or not item.get("id"):
            return
        record = self.submissions.records.get(item.get("clientId"))
        if (not record or record["thread_id"] != thread_id or not turn_id
                or record.get("turn_id") not in {None, turn_id}
                or record["intent"] == "steer" and record["expected_turn_id"] != turn_id):
            return
        if recovering:
            if not record.get("account_identity") or record["account_identity"] != self._account_identity():
                return
        elif record["connection_generation"] != generation or record["account_revision"] != self.account.revision:
            return
        try:
            record["forward_attempted"] = True
            self.submissions.settle(record, "accepted", turn_id=turn_id, native_item_id=item["id"])
            ticket = self.submission_tickets.get(record["client_user_message_id"])
            if ticket is not None:
                # Exact native acceptance releases capacity and the original
                # waiter. It is not a fabricated RPC ACK or a retransmission.
                self.client.retire_confirmed(ticket)
                if ticket.settled:
                    self.submission_tickets.pop(record["client_user_message_id"], None)
        except StudioError:
            pass

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
            path = self.paths.workspace(self.workspace_id) / "attachments" / attachment
            if not path.is_file() or path.parent != self.paths.workspace(self.workspace_id) / "attachments":
                raise StudioError("ATTACHMENT_NOT_FOUND", "Reattach the missing image")
            inputs.append({"type": "localImage", "path": str(path)})
        for key in ("model", "effort"):
            if body.get(key) is not None and (not isinstance(body[key], str) or len(body[key]) > 160):
                raise StudioError("INVALID_INPUT", "Model and effort must be native advertised strings")
        with self.lock:
            self.settings.check_binding(body, self.thread_id)
            if self.conversations.blocked(self.thread_id):
                raise StudioError("THREAD_MUTATION_UNKNOWN", "先核对原生归档或删除结果，再发送消息。", 409)
            if self._has_unknown_response():
                raise StudioError("APPROVAL_RESPONSE_UNKNOWN", "上次许可回复尚未确认，暂不能发送新请求。", 409)
            if self.codex_state in {"starting", "running", "stopping", "unknown", "unavailable", "selecting"}:
                raise StudioError("TURN_ACTIVE", "Wait for native turn confirmation or reconcile the conversation", 409)
            if not self.thread_id:
                raise StudioError("THREAD_REQUIRED", "Create or select a conversation first", 409)
            admission_revision = self.turn_revision
        account_revision = self.account.revision
        if body.get("model") or body.get("effort"):
            model = body.get("model") or self.settings.thread["model"]
            if not model:
                raise StudioError("MODEL_UNCONFIRMED", "请先确认本次使用的模型。", 409)
            self.models.validate(model, body.get("effort"), bool(attachments))
        with self.lock:
            self.settings.check_binding(body, self.thread_id)
            if admission_revision != self.turn_revision:
                raise StudioError("TURN_STATE_CHANGED", "发送校验期间任务或停止状态已变化；内容已保留。", 409)
            if self._has_unknown_response() or self.codex_state in {"starting", "running", "stopping", "unknown", "unavailable", "selecting"}:
                raise StudioError("TURN_ACTIVE", "原生状态已变化，请先查询当前对话。", 409)
            if account_revision != self.account.revision:
                raise StudioError("ACCOUNT_CHANGED", "账号已变化，请确认模型后再发送。", 409)
            if self.owner_stopped:
                try:
                    self.runtime().call("POST", "/owner/resume", {"owner_id": self.owner_id})
                    self.owner_stopped = False
                except StudioError as exc:
                    if exc.code not in {"HOUDINI_STARTING", "CONNECTION_LOST"}:
                        raise
            self.codex_state, self.stop_requested = "starting", False
            self.settings.requested(self.thread_id, body)
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
            self.settings.admitted(turn_id)
            if turn_id not in self.completed_turns:
                self.turn_id = turn_id
                self.codex_state = "stopping" if self.stop_requested else "running"
            should_interrupt = self.stop_requested and self.turn_id is not None
        if should_interrupt:
            self.client.request("turn/interrupt", {"threadId": self.thread_id, "turnId": turn_id})
        return {**result, "turn_settings": self.settings.snapshot()["turn_settings"]}

    def reconcile(self, body=None):
        """Read native Codex state; this never infers a Houdini mutation outcome."""
        with self.action():
            with self.lock:
                message_id = (body or {}).get("client_user_message_id")
                record = self.submissions.records.get(message_id) if message_id else None
                if message_id and not record:
                    raise StudioError("INPUT_RECORD_UNAVAILABLE", "原发送身份记录不可用；不会重新发送。", 409)
                account = self.account.snapshot()
                if record and (account.get("status") != "signed_in"
                        or not record.get("account_identity") or record["account_identity"] != self._account_identity(account)):
                    raise StudioError("INPUT_ACCOUNT_CHANGED", "请使用原账号核对原发送；保留的内容不会发送到其他账号。", 409)
                thread_id = record["thread_id"] if record else self.thread_id
                revision, generation, account_revision = self.turn_revision, self.history.generation, account["account_revision"]
            if not thread_id:
                return {"reconciled": False, "message": "Select a native conversation first"}
            if record and thread_id != self.thread_id:
                self.conversations.read(thread_id)  # Explicit original-thread cwd check; no resume or rebinding.
            value = self.read_thread(thread_id)
            with self.lock:
                source_current = generation == self.history.generation and account_revision == self.account.revision
                fresh = source_current and revision == self.turn_revision and thread_id == self.thread_id
                if source_current and value.get("history_available") is not False:
                    thread = value.get("thread") or {}
                    if thread.get("id") == thread_id:
                        for turn in thread.get("turns", []):
                            for item in turn.get("items", []):
                                self._confirm_user_item(thread_id, turn.get("id"), item, generation, recovering=True)
                if fresh:
                    self._apply_native_state(value["thread"])
                turn_id = self.turn_id if fresh and self.stop_requested else None
                submission = self._public_submission(record) if record else self._submission_snapshot()["user_submission"]
                if not source_current:
                    value = {"history_available": False, "message": "连接或账号已变化，请重新查询原发送。"}
            if turn_id:
                self.client.request("turn/interrupt", {"threadId": thread_id, "turnId": turn_id})
            return {**value, "reconciled": fresh, "codex_state": self.codex_state,
                    "connection_generation": generation, "account_revision": account_revision, "submission": submission}

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
            self.start_submission_id = None
            self.completed_turns.append(latest.get("id"))
        elif not turns and live == "idle":
            self.codex_state, self.turn_id = "idle", None
        else:
            self.codex_state, self.turn_id = "unknown", None

    def stop(self):
        with self.lock:
            self.turn_revision += 1
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

    def _respond_request(self, request_id, result):
        with self.lock:
            request = self.pending_requests.get(request_id)
            if request is None:
                raise StudioError("REQUEST_EXPIRED", "This request is no longer pending", 409)
            if request.get("response_state") == "unknown":
                raise StudioError("APPROVAL_RESPONSE_UNKNOWN", "许可回复尚未确认，请查询原生状态或停止当前轮次。", 409)
            call_id = self.scene_trust.match(request, self.thread_id, self.turn_id)
            self.scene_trust.consume(call_id)
            try:
                self.client.respond_to_server_request(request["request_id"], result)
            except Exception:
                self.pending_requests[request_id] = {**request, "response_state": "unknown", "trust_reason": "response_unknown"}
                self.scene_trust.reset()
                self.codex_state = "unknown"
                self.turn_revision += 1
                raise
            self.pending_requests.pop(request_id, None)
            return {"responded": True}

    def route(self, method, path, query, body):
        try:
            if method == "GET" and path == "/state":
                return self.state()
            if method == "POST" and path == "/scene-trust":
                return self.set_scene_trust(body)
            if method == "GET" and path == "/events":
                cursor = int(query.get("after", [0])[0])
                with self.lock:
                    gap = bool(self.events and cursor and cursor < self.events[0]["sequence"] - 1)
                    events = [e for e in self.events if e["sequence"] > cursor][:100]
                    return {"events": events, "cursor": events[-1]["sequence"] if events else self.sequence,
                            "connection_generation": self.history.generation,
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
                return self.conversations.listing(query)
            if method == "POST" and path == "/threads/manage":
                with self.lock:
                    if self.submissions.unresolved(body.get("thread_id")):
                        raise StudioError("INPUT_RESULT_UNKNOWN", "先核对原发送结果，再修改对话状态。", 409)
                return self.conversations.mutate(body)
            if method == "POST" and path == "/threads/reconcile":
                return self.conversations.reconcile(body)
            if method == "GET" and path == "/thread":
                if not self.thread_id:
                    return {"thread": None}
                return self.read_thread(self.thread_id)
            if method == "GET" and path == "/thread/history":
                thread_id = query.get("thread_id", [None])[0]
                if not thread_id:
                    raise StudioError("HISTORY_SCOPE_REQUIRED", "Supply the selected native thread")
                with self.lock:
                    generation, account_revision = self.history.generation, self.account.revision
                value = self.history.page(thread_id, cursor=query.get("cursor", [None])[0],
                                          turn_id=query.get("turn_id", [None])[0])
                with self.lock:
                    if generation != self.history.generation or account_revision != self.account.revision:
                        raise StudioError("HISTORY_SCOPE_CHANGED", "连接或账号已变化，忽略原历史读取。", 409)
                    if (self.account.snapshot().get("status") == "signed_in"
                            and value.get("history_available") is not False
                            and (value.get("thread") or {}).get("id") == thread_id):
                        for turn in value["thread"].get("turns", []):
                            for item in turn.get("items", []):
                                self._confirm_user_item(thread_id, turn.get("id"), item, generation, recovering=True)
                return {**value, "account_revision": account_revision}
            if method == "POST" and path == "/reconcile":
                return self.reconcile(body)
            if method == "POST" and path == "/selection":
                return self.selection()
            if method == "POST" and path == "/turn":
                return self.start_turn(body)
            if method == "POST" and path == "/turn/steer":
                return self._submit_user_input(body, "steer")
            if method == "POST" and path == "/stop":
                return self.stop()
            if method == "POST" and path == "/attachments":
                return self.attach(body["path"])
            if method == "GET" and path == "/models":
                return self.models.read()
            if method == "GET" and path == "/account":
                revision = self.account.revision
                value = self.account.read()
                if revision != self.account.revision:
                    with self.lock:
                        self.scene_trust.reset()
                        self.models.invalidate()
                return value
            if method == "POST" and path == "/account/login":
                return self.account.start_login()
            if method == "POST" and path == "/account/login/cancel":
                return self.account.cancel_login()
            if method == "POST" and path == "/account/logout":
                with self.lock:
                    self.scene_trust.reset()
                    self.models.invalidate()
                return self.account.logout()
            if method == "POST" and path == "/requests/respond":
                return self._respond_request(str(body["request_id"]), body["result"])
        except BridgeError as exc:
            raise StudioError(exc.code, exc.message, exc.http_status, **(exc.details or {})) from exc
        raise StudioError("ROUTE_NOT_FOUND", "Unknown bridge route", 404)

    def close(self):
        with self.lock:
            self.scene_trust.reset()
        self.client.close(grace_seconds=1)
        if self.server:
            self.server.shutdown()
            self.server.server_close()
