"""Focused consent boundaries using native event shapes; no inference or HOM."""
import copy
import io
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from studio.bridge import Bridge
from studio.codex.client import CodexStdioClient
from studio.codex.errors import BridgeError
from studio.codex.protocol import ProtocolPolicy
from studio.codex.trust import STUDIO_TOOLS
from studio.common import AppPaths, StudioError
from studio.workspace import Workspaces


class SessionTrustTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1] / ".runtime" / "tests"
        root.mkdir(parents=True, exist_ok=True)
        directory = tempfile.TemporaryDirectory(dir=root)
        self.addCleanup(directory.cleanup)
        path = Path(directory.name)
        (path / "pyproject.toml").write_text("# fixture", encoding="utf-8")
        paths = AppPaths(path)
        workspace = Workspaces(paths).create("Trust test")
        self.client = Mock(is_running=True)
        self.bridge = Bridge(paths, workspace["workspace_id"], "session", "x" * 40, "codex", self.client)
        self.bridge.thread_id = "thread-1"
        self.bridge._runtime = Mock()
        self.bridge._runtime.call.return_value = {"alive": True, "runtime_id": "runtime-1",
                                                  "scene": {"scene_epoch": "epoch-1"}}
        self.client.request.return_value = {"thread": {"id": "thread-1", "cwd": str(self.bridge.cwd),
                                                       "status": {"type": "idle"}, "turns": []}}

    def change(self, consent, **changes):
        body = {"enabled": consent, "thread_id": self.bridge.thread_id,
                "revision": self.bridge.scene_trust.revision, **changes}
        return self.bridge.route("POST", "/scene-trust", {}, body)["scene_trust"]

    def start(self, turn="turn-1"):
        self.bridge.on_event({"type": "codex_notification", "method": "turn/started",
                              "params": {"threadId": "thread-1", "turn": {"id": turn}}})

    def item(self, tool="hia_execute_hom", arguments=None, call_id="call-1", **extra):
        item = {"id": call_id, "type": "mcpToolCall", "server": "big_chicken", "tool": tool,
                "status": "inProgress", "arguments": arguments if arguments is not None else {"script": "result = 1"},
                **extra}
        self.bridge.on_event({"type": "codex_notification", "method": "item/started",
                              "params": {"threadId": "thread-1", "turnId": "turn-1", "item": item}})
        return item

    def approval(self, item, request_id=1):
        return {"type": "server_request", "request_id": request_id,
                "method": "mcpServer/elicitation/request",
                "params": {"threadId": "thread-1", "turnId": "turn-1", "serverName": item["server"],
                           "mode": "form", "message": f'Allow the {item["server"]} MCP server to run tool "{item["tool"]}"?',
                           "requestedSchema": {"type": "object", "properties": {}},
                           "_meta": {"codex_approval_kind": "mcp_tool_call", "tool_params": item["arguments"]}}}

    def test_default_native_policy_and_first_unmaterialized_thread_consent(self):
        config = self.bridge.thread_config()
        self.assertEqual(config["approvalPolicy"], "on-request")
        self.assertEqual(config["approvalsReviewer"], "user")
        self.assertEqual(config["sandbox"], "workspace-write")
        server = config["config"]["mcp_servers"]["big_chicken"]
        self.assertEqual(server["default_tools_approval_mode"], "prompt")
        self.assertEqual(server["tools"], {name: {"approval_mode": "prompt"} for name in STUDIO_TOOLS})
        self.assertFalse(self.bridge.state()["scene_trust"]["enabled"])
        self.assertTrue(self.change(True)["enabled"])
        self.client.request.assert_not_called()  # No resume, rollout, config edit or model turn required.
        self.assertEqual(config, self.bridge.thread_config())

    def test_scene_replacement_is_checked_before_delegating_a_native_request(self):
        self.change(True)
        self.start()
        item = self.item()
        self.bridge._runtime.call.return_value = {"runtime_id": "runtime-1", "scene": {"scene_epoch": "epoch-2"}}
        self.bridge.on_event(self.approval(item))
        self.client.respond_to_server_request.assert_not_called()
        self.assertFalse(self.bridge.scene_trust.enabled)
        self.assertIn("1", self.bridge.pending_requests)
        self.assertTrue(self.bridge.state()["scene_context"]["changed"])

    def test_save_as_preserves_same_scene_consent_but_unknown_health_does_not_delegate(self):
        self.change(True)
        self.start()
        item = self.item()
        self.bridge._runtime.call.return_value = {"runtime_id": "runtime-1",
            "scene": {"scene_epoch": "epoch-1", "hip_path": "renamed.hip"}}
        self.bridge.on_event(self.approval(item))
        self.client.respond_to_server_request.assert_called_once()
        self.bridge.on_event({"method": "item/completed", "params": {"threadId": "thread-1", "turnId": "turn-1", "item": item}})
        item = self.item(call_id="call-2")
        self.bridge._runtime.call.side_effect = StudioError("CONNECTION_LOST", "fixture")
        self.bridge.on_event(self.approval(item, request_id=2))
        self.client.respond_to_server_request.assert_called_once()
        self.assertIn("2", self.bridge.pending_requests)

    def test_only_current_consent_allows_once_and_revocation_stops_next_request(self):
        self.start()
        item = self.item()
        self.bridge.on_event(self.approval(item))
        self.client.respond_to_server_request.assert_not_called()
        self.change(True)
        self.client.respond_to_server_request.assert_not_called()  # Existing request is not replayed.
        self.bridge.route("POST", "/requests/respond", {}, {"request_id": 1, "result": {"action": "decline"}})
        self.bridge.on_event({"method": "item/completed", "params": {"threadId": "thread-1", "turnId": "turn-1", "item": item}})
        item = self.item(call_id="call-2")
        self.bridge.on_event(self.approval(item, 2))
        self.client.respond_to_server_request.assert_called_with(2, {"action": "accept", "content": {}})
        self.assertNotIn("2", self.bridge.pending_requests)
        self.bridge._runtime.call.reset_mock()
        self.change(False)
        self.bridge._runtime.call.assert_not_called()  # Revocation does not wait for Houdini.
        self.bridge.on_event({"method": "item/completed", "params": {"threadId": "thread-1", "turnId": "turn-1", "item": item}})
        item = self.item(call_id="call-3")
        self.bridge.on_event(self.approval(item, 3))
        self.assertEqual(self.client.respond_to_server_request.call_count, 2)
        self.assertIn("3", self.bridge.pending_requests)

    def test_unknown_tools_wrong_server_old_turn_spoofed_metadata_and_forms_stay_pending(self):
        self.change(True)
        self.start()
        item = self.item()
        base = self.approval(item)
        cases = [
            {"turnId": "old-turn"}, {"turnId": None}, {"serverName": "another_server"},
            {"mode": "url", "url": "https://example.com/login"},
            {"requestedSchema": {"type": "object", "properties": {"answer": {"type": "string"}}}},
            {"_meta": {"codex_approval_kind": "tool_suggestion", "tool_params": item["arguments"]}},
            {"_meta": {**base["params"]["_meta"], "tool_name": "unknown_tool"}},
            {"_meta": {**base["params"]["_meta"], "codex_sensitive_action": True}},
            {"_meta": {**base["params"]["_meta"], "codex_strict_auto_review": True}},
            {"_meta": {"codex_approval_kind": "mcp_tool_call", "tool_params": {"script": "result = 2"}}},
            {"message": 'Allow the big_chicken MCP server to run tool "unknown_tool"?'},
        ]
        for index, changes in enumerate(cases, 1):
            with self.subTest(changes=changes):
                request = copy.deepcopy(base)
                request["request_id"] = index
                request["params"].update(changes)
                self.bridge.on_event(request)
                self.assertIn(str(index), self.bridge.pending_requests)
        for method in ["item/permissions/requestApproval", "item/commandExecution/requestApproval",
                       "item/fileChange/requestApproval", "item/tool/requestUserInput"]:
            request = {**base, "method": method, "request_id": method}
            self.bridge.on_event(request)
        self.client.respond_to_server_request.assert_not_called()
        self.bridge.scene_trust.calls = {}
        unknown = self.item(tool="hia_unknown")
        self.bridge.on_event(self.approval(unknown, 99))
        self.client.respond_to_server_request.assert_not_called()

    def test_ambiguous_missing_consumed_and_redacted_call_identity_fail_closed(self):
        self.change(True)
        self.start()
        item = self.item()
        second = self.item(call_id="call-2")
        self.bridge.on_event(self.approval(item))
        self.client.respond_to_server_request.assert_not_called()
        self.bridge.scene_trust.calls.pop(second["id"])
        self.bridge.on_event(self.approval(item, 2))
        self.assertEqual(self.client.respond_to_server_request.call_count, 1)
        self.bridge.on_event(self.approval(item, 3))
        self.assertEqual(self.client.respond_to_server_request.call_count, 1)
        self.bridge.scene_trust.calls = {}
        self.bridge.on_event(self.approval(item, 4))
        masked = self.item(arguments={"script": "result = '[REDACTED]'"})
        self.bridge.on_event(self.approval(masked, 5))
        self.assertEqual(self.client.respond_to_server_request.call_count, 1)

    def test_selection_aba_revision_process_exit_and_stop_do_not_extend_consent(self):
        old = self.change(True)
        self.bridge.select_thread("thread-1")
        self.assertFalse(self.bridge.scene_trust.enabled)
        with self.assertRaisesRegex(StudioError, "对话或许可已变化"):
            self.change(True, revision=old["revision"])
        self.change(True)
        self.start()
        item = self.item()
        self.bridge.stop_requested = True
        self.bridge.on_event(self.approval(item))
        self.client.respond_to_server_request.assert_not_called()
        self.bridge.on_event({"type": "process_exit"})
        self.assertFalse(self.bridge.scene_trust.enabled)
        self.assertFalse(self.bridge.state()["scene_trust"]["available"])

    def test_grant_rejects_unavailable_runtime_and_invalid_or_stale_binding(self):
        self.bridge._runtime.call.side_effect = StudioError("CONNECTION_LOST", "offline")
        with self.assertRaises(StudioError):
            self.change(True)
        self.assertFalse(self.bridge.scene_trust.enabled)
        self.bridge._runtime.call.side_effect = None
        for changes in [{"thread_id": "other"}, {"revision": -1}, {"revision": True}, {"enabled": "true"}]:
            with self.subTest(changes=changes), self.assertRaises(StudioError):
                self.change(True, **changes)

    def test_failed_response_retains_unknown_request_without_replay(self):
        self.change(True)
        self.start()
        item = self.item()
        self.client.respond_to_server_request.side_effect = BridgeError("CODEX_STDIN_FAILED", "lost acknowledgement")
        self.bridge.on_event(self.approval(item))
        self.assertEqual(self.bridge.pending_requests["1"]["response_state"], "unknown")
        self.assertFalse(self.bridge.scene_trust.enabled)
        self.assertEqual(self.bridge.codex_state, "unknown")
        with self.assertRaises(StudioError) as error:
            self.bridge.route("POST", "/requests/respond", {}, {"request_id": 1, "result": {"action": "accept"}})
        self.assertEqual(error.exception.code, "APPROVAL_RESPONSE_UNKNOWN")
        self.assertEqual(self.client.respond_to_server_request.call_count, 1)
        with self.assertRaises(StudioError):
            self.bridge.start_turn({"text": "next"})
        self.bridge.on_event({"method": "serverRequest/resolved", "params": {"threadId": "thread-1", "requestId": 1}})
        self.assertNotIn("1", self.bridge.pending_requests)

    def test_native_client_registers_request_before_sink_and_revoke_serializes_with_reply(self):
        self.change(True)
        self.start()
        item = self.item()
        client = CodexStdioClient(["codex"], cwd=self.bridge.cwd, environment={}, policy=ProtocolPolicy(),
                                  event_sink=self.bridge.on_event)
        stream = io.StringIO()
        client._process = SimpleNamespace(stdin=stream, poll=lambda: None)
        self.bridge.client = client
        request = self.approval(item)
        client._handle_server_request({"id": 7, "method": request["method"], "params": request["params"]})
        self.assertIsNone(client.pending_server_request(7))
        self.assertEqual(stream.getvalue().strip(), '{"id":7,"result":{"action":"accept","content":{}}}')

        self.bridge.client = self.client
        self.bridge.scene_trust.calls = {}
        item = self.item(call_id="race-call")
        entered, release, revoked = threading.Event(), threading.Event(), threading.Event()
        self.client.respond_to_server_request.side_effect = lambda *_: (entered.set(), release.wait(2))
        answering = threading.Thread(target=self.bridge.on_event, args=(self.approval(item, 8),))
        answering.start()
        self.assertTrue(entered.wait(1))
        revision = self.bridge.scene_trust.revision
        revoking = threading.Thread(target=lambda: (self.bridge.set_scene_trust({
            "enabled": False, "thread_id": "thread-1", "revision": revision}), revoked.set()))
        revoking.start()
        self.assertFalse(revoked.wait(0.03))
        release.set()
        answering.join(2)
        revoking.join(2)
        self.assertTrue(revoked.is_set())
        self.assertFalse(self.bridge.scene_trust.enabled)

    def test_manual_response_write_failure_uses_same_unknown_guard(self):
        self.change(True)
        self.start()
        item = self.item()
        self.bridge.stop_requested = True  # Existing request still needs the user's response.
        self.bridge.on_event(self.approval(item))
        self.client.respond_to_server_request.side_effect = BridgeError("CODEX_STDIN_FAILED", "write failed")
        body = {"request_id": 1, "result": {"action": "accept", "content": {}}}
        with self.assertRaises(StudioError) as error:
            self.bridge.route("POST", "/requests/respond", {}, body)
        self.assertEqual(error.exception.code, "CODEX_STDIN_FAILED")
        self.assertEqual(self.bridge.pending_requests["1"]["response_state"], "unknown")
        self.assertFalse(self.bridge.scene_trust.enabled)
        self.assertEqual(self.bridge.codex_state, "unknown")
        with self.assertRaises(StudioError) as error:
            self.bridge.route("POST", "/requests/respond", {}, body)
        self.assertEqual(error.exception.code, "APPROVAL_RESPONSE_UNKNOWN")
        self.assertEqual(self.client.respond_to_server_request.call_count, 1)

    def test_idle_reconciliation_cannot_bypass_unresolved_approval_response(self):
        self.start()
        item = self.item()
        self.bridge.on_event(self.approval(item))
        self.client.respond_to_server_request.side_effect = BridgeError("CODEX_STDIN_FAILED", "write failed")
        with self.assertRaises(StudioError):
            self.bridge.route("POST", "/requests/respond", {}, {"request_id": 1, "result": {"action": "accept"}})
        self.bridge.reconcile()
        self.assertEqual(self.bridge.codex_state, "idle")
        with self.assertRaises(StudioError) as error:
            self.bridge.start_turn({"text": "next"})
        self.assertEqual(error.exception.code, "APPROVAL_RESPONSE_UNKNOWN")
        with self.assertRaises(StudioError):
            self.change(True)
        with self.assertRaises(StudioError):
            self.bridge.select_thread()
        self.assertIn("1", self.bridge.pending_requests)
        self.client.request.return_value["thread"]["turns"] = [{"id": "turn-1", "status": "completed"}]
        self.bridge.reconcile()
        self.assertIn("1", self.bridge.pending_requests)
        self.bridge.on_event({"method": "turn/completed", "params": {
            "threadId": "thread-1", "turn": {"id": "turn-1", "status": "completed"}}})
        self.assertNotIn("1", self.bridge.pending_requests)
        self.assertTrue(self.change(True)["enabled"])

    def test_grant_rejected_while_selection_inflight_even_after_old_terminal_event(self):
        old = self.change(True)
        target = {"thread": {"id": "thread-2", "cwd": str(self.bridge.cwd),
                             "status": {"type": "idle"}, "turns": []}}

        def select(method, _params):
            if method == "thread/resume":
                self.bridge.on_event({"method": "turn/completed", "params": {
                    "threadId": "thread-1", "turn": {"id": "old-turn", "status": "completed"}}})
                self.assertEqual(self.bridge.codex_state, "completed")
                with self.assertRaises(StudioError) as error:
                    self.change(True)
                self.assertEqual(error.exception.code, "TRUST_UNAVAILABLE")
            return target

        self.client.request.side_effect = select
        self.bridge.select_thread("thread-2")
        self.assertEqual(self.bridge.thread_id, "thread-2")
        self.assertFalse(self.bridge.scene_trust.enabled)
        self.assertGreater(self.bridge.scene_trust.revision, old["revision"])


if __name__ == "__main__":
    unittest.main()
