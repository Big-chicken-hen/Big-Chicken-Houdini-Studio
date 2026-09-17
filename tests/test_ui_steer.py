"""Native steer Composer admission and frozen-payload races, with no model or Houdini."""
import copy
import os
import unittest
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6 import QtCore, QtGui, QtTest, QtWidgets  # noqa: E402

from scripts.preview_ui import PreviewApi, configure_preview_fonts, process_until  # noqa: E402
from studio.common import AppPaths  # noqa: E402
from studio.ui.panel import StudioPanel  # noqa: E402
from studio.ui.shared import ApiFailure  # noqa: E402


GENERATION = "1" * 32


class ComposerSteerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        configure_preview_fonts(cls.app)
        cls.root = Path(__file__).resolve().parents[1]
        cls.evidence = cls.root / ".runtime" / "ui-steer-tests"
        cls.evidence.mkdir(parents=True, exist_ok=True)

    def setUp(self):
        self.api = PreviewApi(self.evidence)
        self.api.state.update(connection_generation=GENERATION, turn_revision=7)
        self.api.state["codex"].update(state="idle", stop_requested=False)
        self.api.state["runtime"].update(main_thread_busy=False, active_operation_id=None, queue_depth=0)
        self.panel = StudioPanel(api=self.api, auto_poll=False, image_roots=(self.evidence,),
                                 paths=AppPaths(self.root, data_root=self.evidence / "state",
                                                cache_root=self.evidence / "cache"))
        self.panel.show()
        process_until(lambda: self.panel.models_loaded and self.panel.logged_in and not self.panel.hydrating)
        self.app.processEvents()
        for route in ("/turn", "/turn/steer", "/stop", "/reconcile", "/state", "/events", "/thread/history"):
            self.api.hold[route] = []
        self.panel.input.setPlainText("")

    def tearDown(self):
        self.panel.close()
        self.api.close()
        self.panel.deleteLater()
        self.app.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
        self.app.processEvents()

    def active(self, turn_id="active_turn"):
        state = copy.deepcopy(self.panel.state)
        state.update(turn_id=turn_id)
        state["codex"].update(state="running", stop_requested=False)
        state["turn_settings"].update(turn_id=turn_id)
        self.panel.apply_state(state)

    def requests(self):
        return [call for call in self.api.calls if call[1] in {"/turn", "/turn/steer"}]

    def submit(self, text="相同文字"):
        self.panel.input.setPlainText(text)
        self.assertTrue(self.panel.send_button.isEnabled())
        self.panel.send_button.click()
        path = self.requests()[-1][1]
        return self.api.hold[path].pop(0)

    @staticmethod
    def response(body, state="accepted", turn_id="active_turn", native_item_id=None):
        return {"connection_generation": GENERATION, "submission": {
            "client_user_message_id": body["client_user_message_id"],
            "intent": "steer" if "expected_turn_id" in body else "start",
            "connection_generation": body["connection_generation"], "account_revision": body["account_revision"],
            "thread_id": body["expected_thread_id"], "expected_turn_id": body.get("expected_turn_id"),
            "turn_id": turn_id if state == "accepted" else None, "state": state,
            "forward_attempted": state != "not_submitted", "native_item_id": native_item_id,
            "error": {"code": "STEER_NOT_SUBMITTED", "message": "原任务已结束，这条引导没有发送。"}
                     if state == "not_submitted" else None}}

    def echo(self, body, *, turn_id="active_turn", thread_id="preview_thread", generation=GENERATION, client_id=None):
        item = {"type": "userMessage", "id": "native_" + body["client_user_message_id"],
                "clientId": client_id or body["client_user_message_id"],
                "content": [{"type": "text", "text": body["text"]}]}
        self.panel.confirm_submission_item(thread_id, turn_id, item, generation)

    def test_working_send_stop_and_three_identical_steers_are_independent(self):
        self.active()
        self.panel.state["runtime"].update(main_thread_busy=True, active_operation_id="staged", queue_depth=1,
                                          storage_fault="receipt result is still unknown")
        self.panel.receipts["staged"] = {"state": "failed", "mutation_outcome": "partial"}
        self.panel.resize(360, 640)
        self.panel.update_controls()
        self.app.processEvents()
        self.assertTrue(self.panel.stop_button.isVisible())
        self.assertTrue(self.panel.send_button.isVisible())
        self.assertFalse(self.panel.stop_button.geometry().intersects(self.panel.send_button.geometry()))
        model = copy.deepcopy(self.panel.state["turn_settings"])
        ids = []
        for _ in range(3):
            done, _failed, body = self.submit()
            ids.append(body["client_user_message_id"])
            self.assertEqual(body["expected_turn_id"], "active_turn")
            self.assertTrue(ids[-1].startswith(GENERATION + "."))
            self.assertEqual(len(ids[-1]), 65)
            self.assertFalse({"model", "effort", "cwd", "settings_revision", "expected_turn_revision"} & body.keys())
            self.panel.input.setPlainText("下一段草稿")
            self.panel.input.send_requested.emit()
            self.panel.send_button.click()
            self.assertEqual(len(self.requests()), len(ids))
            done(self.response(body))
            self.assertEqual(self.panel.input.toPlainText(), "下一段草稿")
            self.assertTrue(self.panel.send_button.isEnabled())
        self.assertEqual(len(set(ids)), 3)
        self.assertEqual(list(self.panel.awaiting_native), ids)
        self.assertEqual(self.panel.state["turn_settings"], model)
        self.assertTrue(all(path == "/turn/steer" for _, path, _ in self.requests()))
        for _, _, body in self.requests():
            self.echo(body)
        self.assertEqual(self.panel.awaiting_native, {})
        self.assertFalse(any(path == "/requests/respond" for _, path, _ in self.api.calls))

    def test_idle_start_and_unknown_stop_runtime_gates_keep_draft(self):
        done, _failed, body = self.submit("开始任务")
        self.assertEqual(self.requests()[-1][1], "/turn")
        self.assertEqual(body["expected_turn_revision"], 7)
        self.assertEqual(body["model"], "preview-model")
        self.assertEqual(body["effort"], "high")
        self.panel.input.setPlainText("下一条")
        done(self.response(body, turn_id="new_turn"))
        self.assertEqual(self.panel.state["codex"]["state"], "idle")
        self.assertFalse(self.panel.send_button.isEnabled())
        self.assertIsNotNone(self.panel.awaiting_start)
        self.active("new_turn")
        self.assertIsNone(self.panel.awaiting_start)
        self.assertTrue(self.panel.send_button.isEnabled())
        cases = [("starting", None, False, False), ("running", None, False, False),
                 ("running", "new_turn", True, False), ("unknown", "new_turn", False, False),
                 ("completed", "new_turn", False, True)]
        for native, turn, stopped, runtime_busy in cases:
            with self.subTest(native=native, turn=turn, stopped=stopped, runtime_busy=runtime_busy):
                self.panel.state["codex"].update(state=native, stop_requested=stopped)
                self.panel.state["turn_id"] = turn
                self.panel.state["runtime"]["main_thread_busy"] = runtime_busy
                self.panel.update_controls()
                self.panel.send()
                self.assertFalse(self.panel.send_button.isEnabled())
                self.assertEqual(self.panel.input.toPlainText(), "下一条")
                self.assertEqual(len(self.requests()), 1)

    def test_late_ack_after_stop_or_terminal_never_changes_new_draft_or_turn(self):
        self.active()
        done, failed, body = self.submit("稍后要保留的引导")
        self.panel.input.setPlainText("后来输入")
        attachment = {"attachment_id": "new.png", "name": "new.png", "path": str(self.evidence / "new.png"),
                      "status": "ready", "local_key": "new"}
        self.panel.attachments = [attachment]
        self.panel.stop_button.click()
        self.assertEqual(len(self.api.hold["/stop"]), 1)
        self.panel.apply_events({"connection_generation": GENERATION, "cursor": 1, "events": [{"sequence": 1,
            "method": "turn/completed", "params": {"threadId": "preview_thread", "turn": {
                "id": "active_turn", "status": "completed"}}}]})
        done(self.response(body))
        failed(ApiFailure("late failure", submission_state="unknown"))
        done(self.response(body))
        self.assertEqual(self.panel.state["codex"]["state"], "completed")
        self.assertTrue(self.panel.stop_pending)
        self.assertTrue(self.panel.stop_unconfirmed)
        self.assertEqual(self.panel.input.toPlainText(), "后来输入")
        self.assertEqual(self.panel.attachments, [attachment])
        self.assertFalse(self.panel.send_button.isEnabled())
        self.assertEqual(len(self.requests()), 1)

    def test_rejected_steer_restores_empty_draft_or_retains_original_beside_new_draft(self):
        self.active()
        done, _failed, body = self.submit("原任务已经结束")
        done(self.response(body, state="not_submitted"))
        self.assertEqual(self.panel.input.toPlainText(), "原任务已经结束")
        self.assertFalse(self.panel.uncertain_send)
        done, _failed, body = self.submit("第二次明确点击")
        self.panel.input.setPlainText("后来输入不能消失")
        done(self.response(body, state="not_submitted"))
        self.assertEqual(self.panel.input.toPlainText(), "后来输入不能消失")
        self.panel.toggle_pending_submission()
        self.assertIn("第二次明确点击", self.panel.pending_preview.toPlainText())
        self.assertTrue(self.panel.pending_preview.isReadOnly())
        self.assertEqual([path for _, path, _ in self.requests()], ["/turn/steer", "/turn/steer"])

    def test_lost_ack_only_exact_native_client_scope_confirms_without_replay(self):
        self.active()
        _done, failed, body = self.submit()
        failed(ApiFailure("lost acknowledgment", submission_state="unknown"))
        self.assertTrue(self.panel.uncertain_send)
        self.assertEqual(self.api.hold["/reconcile"][0][2], {"client_user_message_id": body["client_user_message_id"]})
        for wrong in ({"client_id": GENERATION + "." + "f" * 32}, {"turn_id": "later_turn"},
                      {"thread_id": "other_thread"}, {"generation": "2" * 32}):
            self.echo(body, **wrong)
            self.assertTrue(self.panel.uncertain_send)
        self.echo(body)
        self.assertFalse(self.panel.uncertain_send)
        self.assertFalse(self.panel.reconciling)
        self.assertIsNone(self.panel.pending_submission)
        self.assertEqual(self.panel.awaiting_native, {})
        self.panel.input.setPlainText("native 已确认，即可继续引导")
        self.assertTrue(self.panel.send_button.isEnabled())
        self.api.hold["/reconcile"][0][0]({"reconciled": False, "message": "late unconfirmed result"})
        self.assertFalse(self.panel.uncertain_send)
        self.assertEqual(len(self.requests()), 1)

    def test_bridge_unknown_recovery_uses_original_scope_and_object_attachments(self):
        old_generation = "2" * 32
        body = {"client_user_message_id": old_generation + "." + "3" * 32,
                "connection_generation": old_generation, "account_revision": 1,
                "expected_thread_id": "preview_thread", "expected_turn_id": "old_turn"}
        record = self.response(body, state="unknown")["submission"]
        record["recovery_binding"] = {"connection_generation": GENERATION,
                                      "account_revision": self.panel.account_revision}
        # Actual Bridge recovery shape: prepared objects here, ID strings only in POST bodies.
        record["snapshot"] = {"text": "保留原来的引导与选择", "draft_text": "保留原来的引导", "draft_version": 12,
            "selection_reference": {"scene_epoch": "old_epoch", "nodes": ["/obj/old"]},
            "attachments": [{"attachment_id": "prepared.png", "name": "参考图.png",
                "path": str(self.evidence / "prepared.png"), "status": "ready", "local_key": "prepared.png"}]}
        state = copy.deepcopy(self.panel.state)
        state.update(user_submission=record, unresolved_submissions=[record])
        self.panel.input.setPlainText("新草稿")
        self.panel.apply_state(state)
        self.assertTrue(self.panel.uncertain_send)
        self.assertEqual(self.panel.pending_submission["connection_generation"], old_generation)
        self.assertFalse(self.panel.snapshot_visible(self.panel.pending_submission))
        self.assertEqual(self.panel.input.toPlainText(), "新草稿")
        self.assertEqual(self.panel.attachments, [])
        self.panel.toggle_pending_submission()
        self.assertIn("参考图.png", self.panel.pending_preview.toPlainText())
        self.assertIn(str(self.evidence / "prepared.png"), self.panel.pending_preview.toPlainText())
        self.panel.reconcile()
        self.assertEqual(self.api.hold["/reconcile"][-1][2]["client_user_message_id"], body["client_user_message_id"])
        self.assertEqual(self.requests(), [])
        self.assertFalse(self.panel.valid_recovery_payload({**record["snapshot"], "attachments": ["prepared.png"]}))
        self.panel.pending_submission = None
        self.panel.retained_submissions.clear()
        self.panel.uncertain_send = False
        record["recovery_binding"]["account_revision"] = self.panel.account_revision + 1
        self.panel.apply_submission_state(state)
        self.assertIsNone(self.panel.pending_submission)

    def test_late_scope_results_do_not_restore_into_other_or_deleted_drafts(self):
        # Native item acceptance and the terminal event permit normal A/B/A
        # navigation even when the original HTTP ACK has not reached the UI.
        self.active("aba_old_turn")
        late_a, _failed, a_body = self.submit("A 的原发送，等待迟到 ACK")
        self.echo(a_body, turn_id="aba_old_turn")
        self.panel.apply_events({"connection_generation": GENERATION, "cursor": 1, "events": [{"sequence": 1,
            "method": "turn/completed", "params": {"threadId": "preview_thread", "turn": {
                "id": "aba_old_turn", "status": "completed"}}}]})
        self.panel.thread_id = "other_thread"
        self.panel.activate_draft("other_thread")
        self.panel.input.setPlainText("B 的草稿")
        b_document = self.panel.input.document()
        self.panel.thread_id = "preview_thread"
        self.panel.activate_draft("preview_thread")
        self.active("aba_new_turn")
        self.panel.input.setPlainText("返回 A 后正在写的新草稿")
        a_document = self.panel.input.document()
        current_turn = copy.deepcopy(self.panel.state["turn_settings"])
        late_a(self.response(a_body, turn_id="aba_old_turn"))
        self.assertIs(self.panel.input.document(), a_document)
        self.assertEqual(self.panel.input.toPlainText(), "返回 A 后正在写的新草稿")
        self.assertEqual(b_document.toPlainText(), "B 的草稿")
        self.assertEqual(self.panel.state["turn_id"], "aba_new_turn")
        self.assertEqual(self.panel.state["turn_settings"], current_turn)
        self.assertIsNone(self.panel.pending_submission)
        self.assertEqual(self.panel.awaiting_native, {})

        self.active()
        done, _failed, body = self.submit("原会话的消息")
        self.panel.thread_id = "other_thread"
        self.panel.activate_draft("other_thread")
        self.panel.input.setPlainText("其他会话的草稿")
        done(self.response(body, state="not_submitted"))
        self.assertEqual(self.panel.input.toPlainText(), "其他会话的草稿")
        self.assertIn(body["client_user_message_id"], self.panel.retained_submissions)
        self.panel.thread_id = "preview_thread"
        self.panel.activate_draft("preview_thread")
        self.panel.input.setPlainText("返回 A 后的新草稿")
        self.panel.update_controls()
        for result_state in ("accepted", "not_submitted"):
            with self.subTest(archived_input_result=result_state):
                self.active("archive_" + result_state)
                archive_done, _failed, archive_body = self.submit("归档前的输入 " + result_state)
                cursor = self.panel.cursor + 1
                self.panel.apply_events({"connection_generation": GENERATION, "cursor": cursor,
                    "events": [{"sequence": cursor, "method": "thread/archived",
                                "params": {"threadId": "preview_thread"}}]})
                self.panel.input.setPlainText("归档后保留的草稿")
                archived_document = self.panel.input.document()
                codex, turn_id = copy.deepcopy(self.panel.state["codex"]), self.panel.state["turn_id"]
                archive_done(self.response(archive_body, state=result_state, turn_id="archive_" + result_state))
                self.assertIn("preview_thread", self.panel.archived_threads)
                self.assertIs(self.panel.input.document(), archived_document)
                self.assertEqual(self.panel.input.toPlainText(), "归档后保留的草稿")
                self.assertEqual(self.panel.state["codex"], codex)
                self.assertEqual(self.panel.state["turn_id"], turn_id)
                self.assertFalse(self.panel.send_button.isEnabled())
                if result_state == "not_submitted":
                    self.assertIn(archive_body["client_user_message_id"], self.panel.retained_submissions)
                cursor += 1
                self.panel.apply_events({"connection_generation": GENERATION, "cursor": cursor,
                    "events": [{"sequence": cursor, "method": "thread/unarchived",
                                "params": {"threadId": "preview_thread"}}]})
        self.active()
        done, _failed, body = self.submit("删除前的消息")
        self.panel.deleted_threads.add("preview_thread")
        self.panel.discard_deleted_draft("preview_thread")
        self.panel.input.setPlainText("删除后不得被晚回调改写")
        done(self.response(body))
        self.assertEqual(self.panel.input.toPlainText(), "删除后不得被晚回调改写")
        self.assertNotIn(body["client_user_message_id"], self.panel.awaiting_native)

    def test_reconnect_late_ack_is_fenced_and_original_identity_survives(self):
        self.active()
        done, _failed, body = self.submit("旧连接发送")
        self.panel.input.setPlainText("新连接继续编辑")
        self.panel.accept_connection("2" * 32)
        done(self.response(body))
        self.assertTrue(self.panel.uncertain_send)
        self.assertEqual(self.panel.pending_submission["client_user_message_id"], body["client_user_message_id"])
        self.assertEqual(self.panel.input.toPlainText(), "新连接继续编辑")
        self.assertEqual(self.panel.awaiting_native, {})

    def test_pending_approval_and_running_image_model_remain_separate(self):
        self.active()
        state = copy.deepcopy(self.panel.state)
        state["pending_requests"] = [{"request_id": 7, "method": "item/commandExecution/requestApproval", "params": {
            "threadId": "preview_thread", "turnId": "active_turn", "command": "fixture command",
            "availableDecisions": ["accept", "decline", "cancel"]}}]
        self.panel.apply_state(state)
        self.panel.input.setPlainText("不要批准，先解释")
        self.assertTrue(self.panel.send_button.isEnabled())
        card = next(iter(self.panel.request_cards.values()))
        card.response_unknown = True
        self.panel.update_controls()
        self.assertFalse(self.panel.send_button.isEnabled())
        card.response_unknown = False
        self.panel.model_controls.catalog["text-only"] = {"model": "text-only", "inputModalities": ["text"]}
        self.panel.model_controls.next_model = "text-only"
        self.panel.attachments = [{"attachment_id": "image.png", "name": "image.png", "path": str(self.evidence / "image.png"),
                                   "status": "ready", "local_key": "image.png"}]
        self.panel.update_controls()
        self.assertTrue(self.panel.send_button.isEnabled())  # Active preview-model accepts images.
        self.panel.state["turn_settings"]["model"] = "text-only"
        self.panel.update_controls()
        self.assertFalse(self.panel.send_button.isEnabled())
        self.assertEqual(self.requests(), [])
        self.assertFalse(any(path == "/requests/respond" for _, path, _ in self.api.calls))

    def test_rejected_response_and_send_during_preedit_never_touch_composition(self):
        self.active()
        done, _failed, body = self.submit("原来的发送")
        self.panel.input.setFocus()
        self.app.sendEvent(self.panel.input, QtGui.QInputMethodEvent("xinshuru", []))
        self.assertTrue(self.panel.composer_preedit())
        done(self.response(body, state="not_submitted"))
        self.assertEqual(self.panel.input.toPlainText(), "")
        self.assertEqual(self.panel.input.textCursor().block().layout().preeditAreaText(), "xinshuru")
        self.panel.toggle_pending_submission()
        self.assertIn("原来的发送", self.panel.pending_preview.toPlainText())
        committed = QtGui.QInputMethodEvent()
        committed.setCommitString("新输入")
        self.app.sendEvent(self.panel.input, committed)
        self.app.sendEvent(self.panel.input, QtGui.QInputMethodEvent("houbanju", []))
        self.panel.input._send_shortcuts[0].activated.emit()
        self.panel.send_button.click()
        self.assertEqual(len(self.requests()), 1)
        self.assertEqual(self.panel.input.toPlainText(), "新输入")
        self.assertTrue(self.panel.composer_preedit())

    def test_native_editor_enter_and_shortcuts_share_one_admission(self):
        self.active()
        self.panel.input.setFocus()
        self.panel.input.setPlainText("已经输入的文字")
        self.app.sendEvent(self.panel.input, QtGui.QInputMethodEvent("pinyin", []))
        QtTest.QTest.keyClick(self.panel.input, QtCore.Qt.Key_Return)
        self.assertEqual(self.requests(), [])
        committed = QtGui.QInputMethodEvent()
        committed.setCommitString("拼音")
        self.app.sendEvent(self.panel.input, committed)
        self.assertIn("拼音", self.panel.input.toPlainText())
        self.assertTrue(all(not shortcut.autoRepeat() for shortcut in self.panel.input._send_shortcuts))
        self.panel.input._send_shortcuts[0].activated.emit()
        self.panel.input._send_shortcuts[1].activated.emit()
        self.panel.send_button.click()
        self.assertEqual(len(self.requests()), 1)


if __name__ == "__main__":
    unittest.main()
