"""Focused native Qt interaction checks; no Houdini or AI inference."""
import base64
import copy
import json
import os
import secrets
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6 import QtCore, QtWidgets  # noqa: E402

from scripts.preview_ui import PreviewApi, configure_preview_fonts, fixture_image, process_until  # noqa: E402
from studio.common import AppPaths  # noqa: E402
from studio.ui.launcher import StudioLauncher  # noqa: E402
from studio.ui.panel import StudioPanel  # noqa: E402
from studio.ui.shared import Api, ApiFailure  # noqa: E402


class PanelTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        configure_preview_fonts(cls.app)
        cls.root = Path(__file__).resolve().parents[1] / ".runtime" / "ui-tests"
        cls.root.mkdir(parents=True, exist_ok=True)

    def setUp(self):
        self.api = PreviewApi(self.root)
        self.panel = StudioPanel(api=self.api, auto_poll=False)
        self.panel.show()
        process_until(lambda: len(self.panel.transcript.cards) == 3)

    def tearDown(self):
        self.panel.close()
        self.panel.deleteLater()
        self.app.processEvents()

    def idle(self):
        self.api.state["codex"]["state"] = "idle"
        self.api.state["runtime"].update(main_thread_busy=False, active_operation_id=None, queue_depth=0)
        self.panel.apply_state(copy.deepcopy(self.api.state))

    def test_login_gate_and_offline_decisions(self):
        self.idle()
        self.panel.apply_account({"account": None})
        self.panel.input.setPlainText("build")
        self.assertFalse(self.panel.send_button.isEnabled())
        self.assertFalse(self.panel.new_thread.isEnabled())
        self.assertFalse(self.panel.models.isEnabled())
        self.assertTrue(self.panel.login_button.isEnabled())
        self.api.state["runtime"] = {"connection": "unavailable"}
        self.panel.apply_state(copy.deepcopy(self.api.state))
        self.panel.decision_input.setPlainText("Use meters")
        self.assertTrue(self.panel.decision_save.isEnabled())
        self.panel.save_decision(False)
        process_until(lambda: not self.panel.memory_busy)
        writes = [body for method, path, body in self.api.calls if path == "/memory" and body["action"] == "record"]
        self.assertEqual(writes, [{"action": "record", "body": "Use meters"}])
        self.panel.apply_account(self.api.account)
        self.assertTrue(self.panel.new_thread.isEnabled())
        self.assertTrue(self.panel.send_button.isEnabled())
        self.api.state["runtime"] = {"connection": "connected", "main_thread_busy": False, "queue_depth": 1}
        self.panel.apply_state(copy.deepcopy(self.api.state))
        self.assertIn("等待主线程", self.panel.runtime_label.text())
        self.assertTrue(self.panel.send_button.isEnabled())

    def test_stop_keeps_runtime_fact_and_native_history_does_not_duplicate(self):
        self.assertIn("已中断", self.panel.codex_label.text())
        self.assertIn("正在执行", self.panel.runtime_label.text())
        original = self.panel.transcript.cards["agent_1"].item["text"]
        self.panel.apply_events({"cursor": 1, "events": [{"method": "item/agentMessage/delta", "params": {
            "threadId": "preview_thread", "itemId": "agent_1", "delta": original}}]})
        self.assertEqual(self.panel.transcript.cards["agent_1"].item["text"], original)
        self.panel.apply_events({"cursor": 2, "events": [{"method": "item/completed", "params": {
            "threadId": "preview_thread", "item": {"id": "agent_1", "type": "agentMessage", "text": "Final native item"}}}]})
        self.assertEqual(self.panel.transcript.cards["agent_1"].item["text"], "Final native item")
        self.api.hold["/thread"] = []
        self.panel.load_history()
        callback = self.api.hold["/thread"].pop()[0]
        callback({"thread": {"id": "preview_thread"}, "history_available": False, "history_message": "not materialized"})
        self.assertEqual(self.panel.transcript.cards["agent_1"].item["text"], "Final native item")
        self.panel.stop()
        process_until(lambda: "已发送停止请求" in self.panel.notice.text())
        self.assertIn("正在执行", self.panel.runtime_label.text())
        self.assertTrue(any(path == "/stop" for _, path, _ in self.api.calls))
        self.assertFalse(any(path.endswith("/cancel") for _, path, _ in self.api.calls))

    def test_image_removal_and_ambiguous_send_preserves_draft(self):
        self.idle()
        image = self.root / "attachment.png"
        fixture_image(image)
        self.panel.transcript.put({"id": "native_image", "type": "mcpToolCall", "tool": "capture", "status": "completed",
                                   "result": {"content": [{"type": "image", "mimeType": "image/png",
                                                           "data": base64.b64encode(image.read_bytes()).decode()}]}})
        native_tile = self.panel.transcript.cards["native_image"].images.itemAt(0).widget()
        process_until(lambda: not native_tile.picture.pixmap().isNull())
        self.panel.add_images([str(image)])
        process_until(lambda: len(self.panel.attachments) == 1)
        tile = self.panel.attachment_layout.itemAt(0).widget()
        process_until(lambda: not tile.picture.pixmap().isNull())
        self.assertGreater(tile.picture.pixmap().width(), 0)
        tile.removed.emit()
        self.assertEqual(self.panel.attachments, [])
        self.panel.input.setPlainText("Change only roughness")
        self.api.errors["/turn"] = "response lost"
        self.panel.send()
        process_until(lambda: self.panel.uncertain_send)
        self.assertEqual(self.panel.input.toPlainText(), "Change only roughness")
        self.assertFalse(self.panel.send_button.isEnabled())
        self.panel.send()
        self.assertEqual(sum(path == "/turn" for _, path, _ in self.api.calls), 1)

    def test_history_buffers_inflight_events_and_resolves_snapshot_overlap(self):
        self.api.thread["turns"][0]["status"] = "inProgress"
        self.panel.transcript.reset()
        self.panel.transcript.hydrate(self.api.thread)
        self.api.hold["/thread"] = []
        self.panel.load_history()
        loaded = self.api.hold["/thread"].pop()[0]
        self.panel.apply_events({"cursor": 3, "events": [
            {"sequence": 1, "method": "item/agentMessage/delta", "params": {
                "threadId": "preview_thread", "itemId": "agent_1", "delta": " overlapping"}},
            {"sequence": 2, "method": "item/started", "params": {
                "threadId": "preview_thread", "item": {"id": "new_item", "type": "agentMessage", "text": ""}}},
            {"sequence": 3, "method": "item/agentMessage/delta", "params": {
                "threadId": "preview_thread", "itemId": "new_item", "delta": "new text"}}]})
        self.assertEqual(len(self.panel.history_events), 3)
        snapshot = copy.deepcopy(self.api.thread)
        snapshot["turns"][0]["items"][1]["text"] = "snapshot overlapping"
        loaded({"thread": snapshot})
        self.assertEqual(self.panel.transcript.cards["agent_1"].item["text"], "snapshot overlapping")
        self.assertEqual(self.panel.transcript.cards["new_item"].item["text"], "new text")
        self.assertTrue(self.panel.history_refresh.isActive())
        self.panel.apply_events({"cursor": 4, "events": [{"sequence": 4, "method": "item/completed", "params": {
            "threadId": "preview_thread", "item": {"id": "agent_1", "type": "agentMessage", "text": "final"}}}]})
        self.assertEqual(self.panel.transcript.cards["agent_1"].item["text"], "final")

    def test_late_history_callback_cannot_clear_new_thread_hydration(self):
        self.api.hold["/thread"] = []
        self.panel.load_history()
        old_loaded, old_failed, _ = self.api.hold["/thread"].pop()
        self.panel.thread_id = "new_thread"
        self.panel.load_history()
        new_loaded = self.api.hold["/thread"].pop()[0]
        old_loaded({"thread": self.api.thread})
        old_failed("old error")
        self.assertTrue(self.panel.hydrating)
        new_loaded({"thread": {"id": "new_thread", "turns": []}})
        self.assertFalse(self.panel.hydrating)
        self.assertEqual(self.panel.transcript.cards, {})

    def test_definite_submission_rejection_preserves_editing_without_reconcile(self):
        self.idle()
        self.panel.input.setPlainText("Edit this input")
        self.panel.submitting = True
        self.panel.send_failed(ApiFailure("Missing attachment", code="ATTACHMENT_NOT_FOUND", status=400,
                                          submission_state="not_submitted"))
        self.assertFalse(self.panel.uncertain_send)
        self.assertEqual(self.panel.input.toPlainText(), "Edit this input")
        self.assertTrue(self.panel.send_button.isEnabled())

    def test_native_approval_and_question_require_explicit_action(self):
        approval = {"request_id": 7, "method": "item/commandExecution/requestApproval", "params": {
            "threadId": "preview_thread", "command": "echo preview", "availableDecisions": ["accept", "decline"]}}
        question = {"request_id": 8, "method": "item/tool/requestUserInput", "params": {"threadId": "preview_thread", "questions": [
            {"id": "finish", "header": "材质", "question": "选择表面处理", "isOther": True,
             "options": [{"label": "磨砂", "description": "柔和反射"}, {"label": "抛光", "description": "清晰反射"}]}]}}
        tool_approval = {"request_id": 9, "method": "mcpServer/elicitation/request", "params": {
            "threadId": "preview_thread", "mode": "form", "message": "Allow scene observation?",
            "_meta": {"codex_approval_kind": "mcp_tool_call"},
            "requestedSchema": {"type": "object", "properties": {}}}}
        self.api.state["pending_requests"] = [approval, question, tool_approval]
        self.panel.apply_state(copy.deepcopy(self.api.state))
        self.assertFalse(any(path == "/requests/respond" for _, path, _ in self.api.calls))
        card = self.panel.request_cards["8"]
        card.answer_questions()
        self.assertFalse(card.error.isHidden())
        card.inputs["finish"][0].setCurrentIndex(0)
        card.answer_questions()
        payload = [body for _, path, body in self.api.calls if path == "/requests/respond"][-1]
        self.assertEqual(payload, {"request_id": 8, "result": {"answers": {"finish": {"answers": ["磨砂"]}}}})
        self.panel.request_cards["7"].actions[1].click()
        payload = [body for _, path, body in self.api.calls if path == "/requests/respond"][-1]
        self.assertEqual(payload["result"], {"decision": "decline"})
        card = self.panel.request_cards["9"]
        self.assertEqual(card.actions[0].text(), "允许本次")
        card.actions[0].click()
        payload = [body for _, path, body in self.api.calls if path == "/requests/respond"][-1]
        self.assertEqual(payload, {"request_id": 9, "result": {"action": "accept", "content": {}}})

    def test_operation_read_and_cancel_race_never_claims_cancellation(self):
        self.api.operation.update(state="queued", result_ref="preview_operation")
        self.panel.read_operation("preview_operation")
        process_until(lambda: self.panel.cancel_operation.isEnabled())
        self.api.operation["state"] = "running"
        self.panel.cancel_queued()
        process_until(lambda: "已进入 HOM" in self.panel.notice.text())
        self.assertIn("执行中", self.panel.receipt_label.text())
        self.assertFalse(self.panel.cancel_operation.isEnabled())
        self.panel.load_detail(0)
        process_until(lambda: self.panel.operation_detail.toPlainText() == '{"evidence":"page"}')
        self.assertFalse(any(path == "/operations" and method == "POST" for method, path, _ in self.api.calls))

    def test_launcher_ready_remains_owned_and_busy_selection_cannot_relaunch(self):
        with patch("studio.ui.launcher.discover_houdini", return_value=[]):
            launcher = StudioLauncher(paths=AppPaths())
        item = QtWidgets.QListWidgetItem("Preview only")
        item.setData(QtCore.Qt.UserRole, "preview_workspace")
        launcher.projects.clear()
        launcher.projects.addItem(item)
        launcher.projects.setCurrentRow(0)
        launcher.busy = True
        launcher.update_selection()
        self.assertFalse(launcher.launch_button.isEnabled())
        launcher.busy = False
        launcher.sessions["preview_workspace"] = {"state": "ready", "directory": str(self.root)}
        launcher.update_selection()
        self.assertFalse(launcher.launch_button.isEnabled())
        launcher.statuses_read({"preview_workspace": {"state": "closed", "directory": str(self.root)}})
        self.assertTrue(launcher.launch_button.isEnabled())
        launcher.close()
        launcher.deleteLater()

    def test_real_qt_http_is_nonblocking_and_authenticates(self):
        token = secrets.token_urlsafe(32)
        observed = []
        receipts = {
            "/finished": {"operation_id": "finished-op", "state": "finished", "error": None},
            "/failed": {"operation_id": "failed-op", "state": "failed",
                        "error": {"code": "SCRIPT_ERROR", "message": "Script failed"}},
        }

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                observed.append(self.headers.get("Authorization") == "Bearer " + token)
                time.sleep(0.12)
                rejected = self.path == "/reject"
                data = json.dumps({"error": {"code": "INVALID_INPUT", "message": "Correct the input",
                                             "submission_state": "not_submitted"}} if rejected else
                                  receipts.get(self.path, {"ready": True})).encode()
                self.send_response(400 if rejected else 200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *_args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        api = Api("http://127.0.0.1:" + str(server.server_port), token)
        result, heartbeats = [], []
        heartbeat = QtCore.QTimer()
        heartbeat.setInterval(10)
        heartbeat.timeout.connect(lambda: heartbeats.append(True))
        heartbeat.start()
        try:
            self.assertTrue(api.call("GET", "/slow", done=result.append, unique=True))
            self.assertFalse(api.call("GET", "/slow?cursor=2", done=result.append, unique=True))
            process_until(lambda: bool(result))
            self.assertEqual(observed, [True])
            self.assertGreater(len(heartbeats), 2)
            self.assertEqual(result, [{"ready": True}])
            failures = []
            api.call("GET", "/reject", failed=failures.append)
            process_until(lambda: bool(failures))
            self.assertEqual(str(failures[0]), "Correct the input")
            self.assertEqual(failures[0].submission_state, "not_submitted")
            for path, receipt in receipts.items():
                returned, errors = [], []
                api.call("GET", path, done=returned.append, failed=errors.append)
                process_until(lambda: bool(returned or errors))
                self.assertEqual(errors, [])
                self.assertEqual(returned, [receipt])
        finally:
            heartbeat.stop()
            api.close()
            server.shutdown()
            server.server_close()
            thread.join(1)


if __name__ == "__main__":
    unittest.main()
