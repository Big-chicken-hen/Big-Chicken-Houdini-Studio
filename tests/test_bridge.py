"""Focused native-turn races and workspace boundaries; no inference or Houdini GUI."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from studio.bridge import Bridge
from studio.codex.errors import BridgeError
from studio.common import AppPaths, StudioError
from studio.workspace import Workspaces


class NativeClient:
    is_running = True

    def __init__(self):
        self.calls = []
        self.handler = lambda method, params: {"turn": {"id": "turn-1"}}

    def set_event_sink(self, sink):
        self.sink = sink

    def request(self, method, params):
        self.calls.append((method, params))
        return self.handler(method, params)


class RuntimeClient:
    def __init__(self):
        self.calls = []

    def call(self, method, path, payload=None, **kwargs):
        self.calls.append((method, path, payload))
        if path == "/health":
            return {"runtime_id": "runtime-1"}
        if path == "/operations":
            return {"operation_id": payload["operation_id"], "state": "finished", "scene_epoch": "epoch-1",
                    "result": {"selected": ["/obj/geo1"]}}
        return {"confirmed": True, "running": ["operation-1"]}


class BridgeTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1] / ".runtime" / "tests"
        root.mkdir(parents=True, exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(dir=root)
        self.addCleanup(self.directory.cleanup)
        path = Path(self.directory.name)
        (path / "pyproject.toml").write_text("# fixture", encoding="utf-8")
        self.paths = AppPaths(path)
        workspace = Workspaces(self.paths).create("Bridge test")
        self.client = NativeClient()
        self.bridge = Bridge(self.paths, workspace["workspace_id"], "session", "x" * 40, "codex", self.client)
        self.bridge.thread_id = "thread-1"
        self.runtime = RuntimeClient()
        self.bridge._runtime = self.runtime

    def event(self, method, turn_id="turn-1", status="inProgress", thread_id="thread-1"):
        self.client.sink({"type": "codex_notification", "method": method,
                          "params": {"threadId": thread_id, "turn": {"id": turn_id, "status": status}}})

    def test_interrupt_ack_is_not_terminal_and_does_not_cancel_running_hom(self):
        self.bridge.start_turn({"text": "edit"})
        self.bridge.stop()
        self.assertEqual(self.bridge.codex_state, "stopping")
        self.assertEqual(self.bridge.turn_id, "turn-1")
        self.assertEqual(self.runtime.calls[-1][1], "/owner/stop")
        self.event("turn/completed", status="interrupted")
        self.assertEqual(self.bridge.codex_state, "interrupted")

    def test_completion_before_start_response_and_late_old_events(self):
        def start(method, params):
            self.event("turn/completed", status="completed")
            self.event("turn/started")
            return {"turn": {"id": "turn-1"}}
        self.client.handler = start
        self.bridge.start_turn({"text": "edit"})
        self.assertEqual(self.bridge.codex_state, "completed")
        self.assertIsNone(self.bridge.turn_id)
        self.client.handler = lambda *_: {"turn": {"id": "turn-2"}}
        self.bridge.start_turn({"text": "next"})
        self.event("turn/completed", status="completed")
        self.assertEqual(self.bridge.turn_id, "turn-2")

    def test_unknown_start_blocks_resubmit_until_native_reconciliation(self):
        def timeout(*_):
            raise BridgeError("CODEX_REQUEST_TIMEOUT", "timeout", 504)
        self.client.handler = timeout
        with self.assertRaises(BridgeError):
            self.bridge.start_turn({"text": "edit"})
        self.assertEqual(self.bridge.codex_state, "unknown")
        with self.assertRaises(StudioError):
            self.bridge.start_turn({"text": "retry"})
        self.client.handler = lambda *_: {"thread": {"status": {"type": "active"}, "turns": []}}
        self.bridge.reconcile()
        self.assertEqual(self.bridge.codex_state, "unknown")
        self.client.handler = lambda *_: {"thread": {"status": {"type": "idle"}, "turns": []}}
        self.bridge.reconcile()
        self.assertEqual(self.bridge.codex_state, "idle")

    def test_native_completion_survives_lost_start_response(self):
        def completed_then_timeout(*_):
            self.event("turn/completed", status="completed")
            raise BridgeError("CODEX_REQUEST_TIMEOUT", "timeout", 504)
        self.client.handler = completed_then_timeout
        with self.assertRaises(BridgeError):
            self.bridge.start_turn({"text": "edit"})
        self.assertEqual(self.bridge.codex_state, "completed")

    def test_reconcile_cannot_overwrite_new_terminal_event(self):
        self.bridge.start_turn({"text": "edit"})
        def read(*_):
            self.event("turn/completed", status="completed")
            return {"thread": {"turns": [{"id": "turn-1", "status": "inProgress"}]}}
        self.client.handler = read
        self.assertFalse(self.bridge.reconcile()["reconciled"])
        self.assertEqual(self.bridge.codex_state, "completed")

    def test_invalid_attachment_never_resumes_owner_or_marks_starting(self):
        with self.assertRaises(StudioError):
            self.bridge.start_turn({"text": "edit", "attachments": ["../other/image.png"]})
        self.assertEqual(self.bridge.codex_state, "idle")
        self.assertEqual(self.runtime.calls, [])
        self.assertEqual(self.client.calls, [])

    def test_previous_thread_events_and_workspace_resume_are_rejected(self):
        self.event("turn/started", thread_id="other-thread")
        self.assertEqual(self.bridge.sequence, 0)
        self.client.handler = lambda *_: {"thread": {"cwd": str(self.paths.root)}}
        with self.assertRaises(StudioError) as error:
            self.bridge.select_thread("other-thread")
        self.assertEqual(error.exception.code, "THREAD_WORKSPACE_MISMATCH")
        self.assertEqual([m for m, _ in self.client.calls], ["thread/read"])

    def test_selection_uses_queue_without_rebinding_or_resuming_owner(self):
        value = self.bridge.selection()
        self.assertEqual(value["nodes"], ["/obj/geo1"])
        operation = self.runtime.calls[-1][2]
        self.assertEqual(operation["kind"], "context")
        self.assertIsNone(operation["scene_epoch"])
        self.assertEqual(operation["owner_id"], "session")
        self.assertEqual(self.client.calls, [])

    def test_offline_native_conversation_and_console_python(self):
        self.bridge._runtime = None
        self.client.handler = lambda *_: {"thread": {"id": "new-thread", "status": {"type": "idle"}, "turns": []}}
        self.bridge.select_thread()
        self.assertEqual(self.bridge.thread_id, "new-thread")
        with patch.dict("os.environ", {"BCS_PYTHON_EXECUTABLE": str(self.paths.root / "python.exe")}):
            config = self.bridge.thread_config()["config"]
        self.assertEqual(config["project_doc_max_bytes"], 0)
        self.assertTrue(config["mcp_servers"]["big_chicken"]["command"].endswith("python.exe"))
        self.assertIn("HIA_RENDER_OUTPUT_DIR", config["mcp_servers"]["big_chicken"]["env_vars"])


if __name__ == "__main__":
    unittest.main()
