"""Focused Qt input/draft checks. These do not exercise Windows Microsoft Pinyin."""
import copy
import os
import unittest
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6 import QtCore, QtGui, QtTest, QtWidgets  # noqa: E402

from scripts.preview_ui import PreviewApi, configure_preview_fonts, process_until  # noqa: E402
from studio.ui.panel import Composer, StudioPanel  # noqa: E402
from studio.ui.shared import ApiFailure  # noqa: E402


class ComposerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        configure_preview_fonts(cls.app)
        cls.root = Path(__file__).resolve().parents[1] / ".runtime" / "composer-tests"
        cls.root.mkdir(parents=True, exist_ok=True)

    def setUp(self):
        self.api = PreviewApi(self.root)
        self.api.state["codex"].update(state="idle", stop_requested=False)
        self.api.state["runtime"].update(main_thread_busy=False, active_operation_id=None, queue_depth=0)
        self.panel = StudioPanel(api=self.api, auto_poll=False)
        self.panel.show()
        process_until(lambda: self.panel.transcript.history_known and self.panel.models_loaded)

    def tearDown(self):
        self.panel.close()
        self.panel.deleteLater()
        self.app.processEvents()

    def test_native_input_paste_undo_and_local_shortcuts(self):
        editor = self.panel.input
        self.assertIsInstance(editor, QtWidgets.QTextEdit)
        self.assertFalse(editor.acceptRichText())
        for event in ("keyPressEvent", "inputMethodEvent", "inputMethodQuery"):
            self.assertNotIn(event, Composer.__dict__)
        self.assertTrue(all(s.context() == QtCore.Qt.WidgetShortcut for s in editor._send_shortcuts))
        self.assertTrue(all(not s.autoRepeat() for s in editor._send_shortcuts))
        self.panel.activateWindow()
        editor.setFocus()
        self.app.processEvents()
        sent = []
        editor.send_requested.connect(lambda: sent.append(True))
        QtTest.QTest.keyClicks(editor, "Shelf")
        QtTest.QTest.keyClick(editor, QtCore.Qt.Key_Return)
        self.assertEqual(editor.toPlainText(), "Shelf\n")
        mime = QtCore.QMimeData()
        mime.setText("中文一行\n第二行")
        mime.setHtml("<b>should not become rich text</b>")
        self.app.clipboard().setMimeData(mime)
        QtTest.QTest.keyClick(editor, QtCore.Qt.Key_V, QtCore.Qt.ControlModifier)
        self.assertEqual(editor.toPlainText(), "Shelf\n中文一行\n第二行")
        editor.undo()
        self.assertEqual(editor.toPlainText(), "Shelf\n")
        editor.redo()
        self.assertIn("第二行", editor.toPlainText())
        self.panel.apply_account({"account": None})  # Signal testing must not submit a turn.
        QtTest.QTest.keyClick(editor, QtCore.Qt.Key_Return, QtCore.Qt.ControlModifier)
        QtTest.QTest.keyClick(editor, QtCore.Qt.Key_Enter, QtCore.Qt.ControlModifier)
        self.assertEqual(len(sent), 2)
        self.panel.new_thread.setEnabled(True)
        self.panel.new_thread.setFocus()
        self.app.processEvents()
        QtTest.QTest.keyClick(self.panel.new_thread, QtCore.Qt.Key_Return, QtCore.Qt.ControlModifier)
        self.assertEqual(len(sent), 2)

    def test_synthetic_preedit_commit_is_left_to_qt(self):
        editor = self.panel.input
        editor.setFocus()
        sent = []
        editor.send_requested.connect(lambda: sent.append(True))
        self.app.sendEvent(editor, QtGui.QInputMethodEvent("zhongwen", []))
        self.assertEqual(editor.toPlainText(), "")
        event = QtGui.QInputMethodEvent()
        event.setCommitString("中文")
        self.app.sendEvent(editor, event)
        self.assertEqual(editor.toPlainText(), "中文")
        self.assertFalse(sent)

    def test_mixed_image_clipboard_routes_once_and_uses_attachment_id(self):
        mime = QtCore.QMimeData()
        image = QtGui.QImage(24, 24, QtGui.QImage.Format_RGB32)
        image.fill(QtGui.QColor("#8aaa65"))
        mime.setImageData(image)
        mime.setText("clipboard image fallback must not be inserted")
        self.panel.input.insertPlainText("参考图片")
        self.assertTrue(self.panel.input.canInsertFromMimeData(mime))
        self.app.clipboard().setMimeData(mime)
        self.panel.input.paste()  # Same native path as the context-menu Paste action.
        process_until(lambda: self.panel.attachments and self.panel.attachments[0]["status"] == "ready")
        self.assertEqual(self.panel.input.toPlainText(), "参考图片")
        uploads = [body for _, path, body in self.api.calls if path == "/attachments"]
        self.assertEqual(len(uploads), 1)
        path = Path(uploads[0]["path"])
        self.assertTrue(path.is_relative_to(self.panel.paths.runtime))
        self.assertTrue(path.read_bytes().startswith(b"\x89PNG"))
        self.panel.send()
        posted = [body for _, path, body in self.api.calls if path == "/turn"][-1]
        self.assertEqual(posted["attachments"], ["preview_attachment.png"])

    def test_poll_failures_and_running_turn_never_disable_draft(self):
        editor = self.panel.input
        editor.insertPlainText("本地草稿")
        editor.setFocus()
        cursor = editor.textCursor().position()
        self.panel.account_failed("temporary account polling failure")
        self.assertFalse(self.panel.send_button.isEnabled())
        self.assertTrue(editor.isEnabled())
        self.assertEqual(editor.textCursor().position(), cursor)
        self.panel.connection_failed("temporary connection failure")
        editor.insertPlainText("\n继续编辑")
        self.assertEqual(editor.toPlainText(), "本地草稿\n继续编辑")
        self.api.state["codex"]["state"] = "running"
        self.panel.apply_state(copy.deepcopy(self.api.state))
        self.assertTrue(editor.isEnabled())
        self.assertFalse(editor.isReadOnly())
        self.assertFalse(self.panel.send_button.isEnabled())
        self.assertFalse(self.panel.stop_button.isHidden())

    def test_success_preserves_edits_even_if_text_was_changed_back(self):
        editor = self.panel.input
        editor.insertPlainText("原稿")
        self.api.hold["/turn"] = []
        self.panel.send()
        done, _, _ = self.api.hold["/turn"].pop()
        self.assertTrue(editor.isEnabled())
        editor.insertPlainText("修改")
        cursor = editor.textCursor()
        cursor.movePosition(QtGui.QTextCursor.PreviousCharacter, QtGui.QTextCursor.KeepAnchor, 2)
        cursor.removeSelectedText()
        self.assertEqual(editor.toPlainText(), "原稿")
        done({"turn": {"id": "new_turn", "status": "inProgress", "items": []}})
        self.assertEqual(editor.toPlainText(), "原稿")
        self.assertIsNone(self.panel.pending_submission)

    def test_lost_submission_requires_new_matching_message_in_original_thread(self):
        editor = self.panel.input
        editor.insertPlainText("原消息")
        self.api.hold["/turn"] = []
        self.api.hold["/reconcile"] = []
        self.panel.send()
        _, failed, _ = self.api.hold["/turn"].pop()
        editor.insertPlainText("，继续写草稿")
        failed(ApiFailure("response lost"))
        self.assertEqual(self.panel.pending_submission["text"], "原消息")
        self.assertTrue(self.panel.uncertain_send)
        self.assertEqual(len(self.api.hold["/reconcile"]), 1)
        previous = copy.deepcopy(self.api.thread)
        previous["turns"][0]["items"].append({"id": "old_equal", "type": "userMessage", "content": [{"type": "text", "text": "原消息"}]})
        self.panel.reconciled({"reconciled": True, "codex_state": "idle", "thread": previous})
        self.assertTrue(self.panel.uncertain_send)
        fresh = copy.deepcopy(previous)
        fresh["turns"].append({"id": "new_turn", "status": "completed", "items": [
            {"id": "new_user", "type": "userMessage", "content": [{"type": "text", "text": "原消息"}]}]})
        wrong = copy.deepcopy(fresh)
        wrong["id"] = "another_thread"
        self.panel.reconciled({"reconciled": True, "codex_state": "idle", "thread": wrong})
        self.assertTrue(self.panel.uncertain_send)
        self.panel.reconciled({"reconciled": True, "codex_state": "idle", "thread": fresh})
        self.assertFalse(self.panel.uncertain_send)
        self.assertEqual(editor.toPlainText(), "原消息，继续写草稿")
        self.assertEqual(sum(path == "/turn" for _, path, _ in self.api.calls), 1)

    def test_offline_image_and_removed_upload_are_not_lost_or_resurrected(self):
        self.panel.connection_failed("offline")
        image = QtGui.QImage(16, 16, QtGui.QImage.Format_RGB32)
        image.fill(QtCore.Qt.white)
        self.panel.add_clipboard_image(image)
        self.assertEqual(self.panel.attachments[0]["status"], "waiting")
        self.assertFalse(any(path == "/attachments" for _, path, _ in self.api.calls))
        self.panel.apply_state(copy.deepcopy(self.api.state))
        self.api.hold["/attachments"] = []
        self.panel.upload_attachments()
        done, _, _ = self.api.hold["/attachments"].pop()
        self.panel.remove_attachment(self.panel.attachments[0]["local_key"])
        done({"attachment_id": "late.png", "path": "unused.png", "name": "late.png"})
        self.assertEqual(self.panel.attachments, [])
        self.assertEqual(self.panel.uploading, 0)

    def test_conversation_first_keeps_images_and_unconfirmed_houdini_visible(self):
        self.panel.resize(480, 700)
        self.app.processEvents()
        self.assertTrue(self.panel.settings_area.isHidden())
        self.assertTrue(self.panel.tabs.tabBar().isHidden())
        self.assertTrue(self.panel.transcript.cards["tool_1"].isHidden())
        group = self.panel.transcript.tool_groups["preview_turn"]
        group.click()
        self.assertFalse(self.panel.transcript.cards["tool_1"].isHidden())
        self.api.state["codex"]["state"] = "completed"
        self.api.state["runtime"].update(main_thread_busy=True, active_operation_id="still_running")
        self.panel.apply_state(copy.deepcopy(self.api.state))
        self.assertIn("Houdini 仍在执行", self.panel.runtime_status.text())
        self.panel.apply_operations({"operations": [{"operation_id": "uncertain", "state": "unknown"}]})
        self.api.state["runtime"].update(main_thread_busy=False, active_operation_id=None)
        self.panel.apply_state(copy.deepcopy(self.api.state))
        self.assertIn("结果未确认", self.panel.runtime_status.text())
        self.assertFalse(self.panel.runtime_status.isHidden())
        self.panel.toggle_settings()
        self.assertTrue(self.panel.runtime_status.isVisible())
        self.assertFalse(self.panel.settings_area.isHidden())

    def test_matching_text_without_original_images_cannot_resolve_submission(self):
        editor = self.panel.input
        image = QtGui.QImage(16, 16, QtGui.QImage.Format_RGB32)
        image.fill(QtCore.Qt.white)
        self.panel.add_clipboard_image(image)
        process_until(lambda: self.panel.attachments[0]["status"] == "ready")
        attachment = dict(self.panel.attachments[0])
        editor.insertPlainText("按这张参考图调整")
        self.api.hold["/turn"] = []
        self.api.hold["/reconcile"] = []
        self.panel.send()
        _, failed, _ = self.api.hold["/turn"].pop()
        self.panel.remove_attachment(attachment["local_key"])
        failed(ApiFailure("response lost"))
        self.assertEqual(self.panel.pending_submission["attachments"], [attachment])
        history = copy.deepcopy(self.api.thread)
        content = [{"type": "text", "text": "按这张参考图调整"}]
        history["turns"].append({"id": "new_turn", "status": "completed", "items": [
            {"id": "new_user", "type": "userMessage", "content": content}]})
        self.assertFalse(self.panel.submission_in_history({"thread": history}))
        content.append({"type": "localImage", "path": attachment["path"]})
        self.assertTrue(self.panel.submission_in_history({"thread": history}))
        self.assertEqual(sum(path == "/turn" for _, path, _ in self.api.calls), 1)

    def test_first_message_loss_after_explicit_new_thread_can_reconcile(self):
        self.api.state["thread_id"] = None
        self.panel.apply_state(copy.deepcopy(self.api.state))
        self.panel.input.insertPlainText("第一个书架")
        self.assertFalse(self.panel.send_button.isEnabled())
        self.api.hold["/threads/select"] = []
        self.api.hold["/thread"] = []
        self.panel.select_thread(None)
        selected, _, body = self.api.hold["/threads/select"].pop()
        self.assertEqual(body, {})
        self.api.state.update(thread_id="fresh_thread", turn_id=None)
        self.api.thread = {"id": "fresh_thread", "status": {"type": "idle"}}
        selected({"thread": copy.deepcopy(self.api.thread)})
        loaded = self.api.hold["/thread"].pop()[0]
        loaded({"thread": copy.deepcopy(self.api.thread), "history_available": False})
        self.assertEqual(self.panel.confirmed_new_thread, "fresh_thread")
        self.api.hold["/turn"] = []
        self.api.hold["/reconcile"] = []
        self.panel.update_controls()
        self.panel.send()
        _, failed, _ = self.api.hold["/turn"].pop()
        failed(ApiFailure("first turn response lost"))
        self.assertTrue(self.panel.uncertain_send)
        self.assertTrue(self.panel.pending_submission["history_known"])
        fresh = {"id": "fresh_thread", "turns": [{"id": "first_turn", "status": "completed", "items": [
            {"id": "first_user", "type": "userMessage", "content": [{"type": "text", "text": "第一个书架"}]}]}]}
        self.panel.reconciled({"reconciled": True, "codex_state": "completed", "thread": fresh})
        self.assertFalse(self.panel.uncertain_send)
        self.assertEqual(self.panel.input.toPlainText(), "")
        self.assertEqual(sum(path == "/turn" for _, path, _ in self.api.calls), 1)

    def test_unrelated_receipt_failure_is_not_current_turn_failure(self):
        self.panel.apply_operations({"operations": [{"operation_id": "old_failure", "state": "failed",
                                                     "mutation_outcome": "partial"}]})
        self.assertTrue(self.panel.runtime_status.isHidden())
        self.api.state["turn_id"] = "current_turn"
        self.api.state["runtime"].update(main_thread_busy=True, active_operation_id="current_operation")
        self.panel.apply_state(copy.deepcopy(self.api.state))
        self.panel.apply_operations({"operations": [{"operation_id": "current_operation", "state": "failed",
                                                     "mutation_outcome": "partial"}]})
        self.api.state["runtime"].update(main_thread_busy=False, active_operation_id=None)
        self.panel.apply_state(copy.deepcopy(self.api.state))
        self.assertIn("留下了部分修改", self.panel.runtime_status.text())
        self.api.state["turn_id"] = "next_turn"
        self.panel.apply_state(copy.deepcopy(self.api.state))
        self.assertTrue(self.panel.runtime_status.isHidden())

    def test_existing_approval_card_receives_unknown_response_without_replacement(self):
        request = {"request_id": "permission", "method": "item/commandExecution/requestApproval", "params": {
            "threadId": "preview_thread", "command": "echo preview", "availableDecisions": ["accept", "decline"]}}
        self.panel.sync_requests([request])
        card = self.panel.request_cards["permission"]
        self.panel.sync_requests([{**request, "response_state": "unknown"}])
        self.assertIs(self.panel.request_cards["permission"], card)
        self.assertTrue(all(not action.isEnabled() for action in card.actions))
        self.assertFalse(any(path == "/requests/respond" for _, path, _ in self.api.calls))


if __name__ == "__main__":
    unittest.main()
