"""Bound recovery projection to the current confirmed owner; Qt offscreen only."""
import copy
import unittest

import test_ui_steer as fixtures


class ComposerRecoveryTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.ComposerSteerTest.setUpClass.__func__)
    setUp = fixtures.ComposerSteerTest.setUp
    tearDown = fixtures.ComposerSteerTest.tearDown
    requests = fixtures.ComposerSteerTest.requests

    def recovery_record(self, *, original_revision=31, binding=True):
        body = {"client_user_message_id": "2" * 32 + "." + "3" * 32,
                "connection_generation": "2" * 32, "account_revision": original_revision,
                "expected_thread_id": "preview_thread", "expected_turn_id": "old_turn"}
        record = fixtures.ComposerSteerTest.response(body, state="unknown")["submission"]
        record["snapshot"] = {"text": "原账号的未决内容", "draft_text": "原账号的未决内容",
                              "draft_version": 8, "attachments": [], "selection_reference": None}
        record["recovery_binding"] = ({"connection_generation": self.panel.native_generation,
                                       "account_revision": self.panel.account_revision} if binding else None)
        return record

    def apply_record(self, record):
        state = copy.deepcopy(self.panel.state)
        state.update(account_revision=self.panel.account_revision, user_submission=record,
                     unresolved_submissions=[record])
        self.panel.apply_state(state)

    def test_no_selected_thread_can_show_and_query_original_id_without_touching_new_draft(self):
        state = copy.deepcopy(self.panel.state)
        state.update(thread_id=None, turn_id=None)
        self.panel.apply_state(state)
        self.panel.input.setPlainText("新草稿不能被恢复输入覆盖")
        record = self.recovery_record()
        self.apply_record(record)
        pending = self.panel.pending_submission
        self.assertEqual(pending["account_revision"], 31)
        self.assertEqual(pending["connection_generation"], "2" * 32)
        self.assertFalse(self.panel.snapshot_visible(pending))
        self.assertTrue(self.panel.reconcile_button.isEnabled())
        self.panel.toggle_pending_submission()
        self.assertIn("原账号的未决内容", self.panel.pending_preview.toPlainText())
        self.panel.reconcile()
        done, _failed, body = self.api.hold["/reconcile"][-1]
        self.assertEqual(body, {"client_user_message_id": record["client_user_message_id"]})
        accepted = {**record, "state": "accepted", "turn_id": "old_turn", "native_item_id": "native-original"}
        accepted.pop("snapshot")
        done({"reconciled": False, "connection_generation": self.panel.native_generation,
              "account_revision": self.panel.account_revision, "submission": accepted,
              "thread": {"id": "preview_thread", "turns": []}})
        self.assertIsNone(self.panel.thread_id)
        self.assertIsNone(self.panel.pending_submission)
        self.assertFalse(self.panel.uncertain_send)
        self.assertEqual(self.panel.input.toPlainText(), "新草稿不能被恢复输入覆盖")
        self.assertEqual(self.requests(), [])

    def test_equal_revision_without_confirmed_owner_never_imports_snapshot(self):
        record = self.recovery_record(original_revision=self.panel.account_revision, binding=False)
        self.apply_record(record)  # Even an accidentally included payload is not trusted.
        self.assertIsNone(self.panel.pending_submission)
        self.assertEqual(self.panel.visible_retained_submissions(), [])
        self.assertTrue(self.panel.native_submission_unresolved())
        self.assertFalse(self.panel.reconcile_button.isEnabled())
        self.assertIn("原账号", self.panel.work_status.text())
        self.assertEqual(self.requests(), [])

    def test_account_switch_hides_retained_content_and_retires_only_old_query(self):
        record = self.recovery_record()
        self.apply_record(record)
        self.panel.toggle_pending_submission()
        self.panel.reconcile()
        old_done = self.api.hold["/reconcile"][-1][0]
        self.panel.input.setPlainText("后来输入")
        self.panel.accept_account_revision(self.panel.account_revision + 1)
        self.assertFalse(self.panel.reconciling)
        denied = {**record, "recovery_binding": None}
        denied.pop("snapshot")
        self.apply_record(denied)
        self.assertTrue(self.panel.pending_preview.isHidden())
        self.assertEqual(self.panel.pending_preview.toPlainText(), "")
        self.assertFalse(self.panel.reconcile_button.isEnabled())
        old_done({"reconciled": True, "submission": {**record, "state": "accepted", "turn_id": "old_turn"}})
        self.assertEqual(self.panel.pending_submission["state"], "unknown")
        # Original owner signs in again with a new process-local revision.
        self.panel.accept_account_revision(self.panel.account_revision + 1)
        returned = copy.deepcopy(record)
        returned["recovery_binding"]["account_revision"] = self.panel.account_revision
        self.apply_record(returned)
        self.panel.reconcile()
        new_request = self.panel.reconcile_request
        old_done({"reconciled": True, "submission": {**record, "state": "accepted", "turn_id": "old_turn"}})
        self.assertIs(self.panel.reconcile_request, new_request)
        self.assertTrue(self.panel.reconciling)
        self.assertEqual(self.panel.input.toPlainText(), "后来输入")
        self.assertEqual(self.requests(), [])

    def test_new_history_confirms_original_item_only_after_current_owner_binding(self):
        record = self.recovery_record()
        self.apply_record(record)
        self.panel.input.setPlainText("后写草稿")
        item = {"id": "native-original", "type": "userMessage", "clientId": record["client_user_message_id"]}
        self.panel.load_history()
        stale_done = self.api.hold["/thread/history"][-1][0]
        self.panel.accept_account_revision(self.panel.account_revision + 1)
        self.assertFalse(self.panel.hydrating)
        current = copy.deepcopy(record)
        current["recovery_binding"]["account_revision"] = self.panel.account_revision
        self.apply_record(current)
        history = {"connection_generation": self.panel.native_generation, "history_available": True,
                   "thread": {"id": "preview_thread", "turns": [{"id": "old_turn", "status": "completed", "items": [item]}]}}
        stale_done(history)
        self.assertEqual(self.panel.pending_submission["state"], "unknown")
        self.panel.confirm_history_submissions(history)
        self.assertIsNone(self.panel.pending_submission)
        self.assertFalse(self.panel.uncertain_send)
        self.assertEqual(self.panel.input.toPlainText(), "后写草稿")
        self.assertEqual(self.requests(), [])


if __name__ == "__main__":
    unittest.main()
