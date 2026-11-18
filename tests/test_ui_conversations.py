"""Focused ownership and stale-list checks for the native conversation manager."""
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from PySide6 import QtWidgets

import test_ui as fixtures
from studio.ui.conversations import ConversationManager


class ConversationUiTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.PanelTest.setUpClass.__func__)
    setUp = fixtures.PanelTest.setUp
    tearDown = fixtures.PanelTest.tearDown

    def capture_calls(self, *, api=False):
        calls = []
        def call(method, path, body=None, **callbacks):
            calls.append({"method": method, "path": path, "body": body, **callbacks})
            return True
        override = patch.object(self.panel.api if api else self.panel, "call", call)
        override.start()
        self.addCleanup(override.stop)
        return calls

    def test_unknown_delete_keeps_draft_and_confirmed_delete_is_thread_owned(self):
        self.capture_calls()
        target = self.panel.thread_id
        self.panel.input.setPlainText("Target draft")
        self.panel.activate_draft("other")
        self.panel.input.setPlainText("Keep another draft")
        other_document = self.panel.input.document()
        self.panel.activate_draft(target)
        self.panel.apply_conversations({"revision": 1, "deleted": [], "pending": [
            {"thread_id": target, "action": "delete", "state": "unknown"}]})
        self.assertEqual(self.panel.input.toPlainText(), "Target draft")
        self.assertEqual(self.panel.thread_id, target)
        self.panel.apply_conversations({"revision": 2, "deleted": [target], "pending": []})
        self.assertEqual(self.panel.input.toPlainText(), "")
        self.assertIsNone(self.panel.thread_id)
        self.assertNotIn(target, self.panel.drafts)
        self.assertEqual(other_document.toPlainText(), "Keep another draft")
        self.panel.save_draft()
        self.assertNotIn(target, self.panel.drafts)

    def test_late_list_and_selection_callbacks_cannot_restore_deleted_thread(self):
        calls = self.capture_calls()
        target = self.panel.thread_id
        self.panel.load_threads()
        old_list = calls[-1]["done"]
        self.panel.select_thread(target)
        old_select = next(row["done"] for row in reversed(calls) if row["path"] == "/threads/select")
        self.panel.apply_conversations({"revision": 1, "deleted": [target], "pending": []})
        old_list({"data": [{"id": target, "name": "Deleted"}], "lifecycle_revision": 0})
        old_select({"thread": {"id": target, "turns": []}})
        self.assertIsNone(self.panel.thread_id)
        self.assertFalse(self.panel.switching)
        self.assertNotIn(target, self.panel.drafts)

    def test_noncurrent_delete_notification_keeps_current_composer(self):
        self.capture_calls()
        current = self.panel.thread_id
        self.panel.activate_draft("other")
        self.panel.input.setPlainText("Other draft")
        self.panel.activate_draft(current)
        self.panel.input.setPlainText("Current draft")
        self.panel.apply_events({"cursor": self.panel.cursor + 1, "events": [{"sequence": self.panel.cursor + 1,
            "method": "thread/deleted", "params": {"threadId": "other"}}]})
        self.assertNotIn("other", self.panel.drafts)
        self.assertEqual(self.panel.input.toPlainText(), "Current draft")
        self.assertEqual(self.panel.thread_id, current)

    def captured_start(self):
        fixtures.PanelTest.idle(self)
        calls = self.capture_calls(api=True)
        self.panel.input.setPlainText("A pending message")
        self.panel.update_controls()
        self.assertTrue(self.panel.send_button.isEnabled())
        self.panel.send()
        request = next(row for row in calls if row["path"] == "/turn")
        body = request["body"]
        submission = {"client_user_message_id": body["client_user_message_id"], "intent": "start",
                      "connection_generation": body["connection_generation"],
                      "account_revision": body["account_revision"], "thread_id": body["expected_thread_id"],
                      "expected_turn_id": None, "turn_id": "old-turn", "state": "accepted",
                      "forward_attempted": True, "native_item_id": "accepted-user-item"}
        response = {"connection_generation": body["connection_generation"],
                    "account_revision": body["account_revision"], "submission": submission}
        return request["done"], response, self.panel.pending_submission

    def test_live_thread_accepts_the_captured_turn_acknowledgement(self):
        reply, response, original = self.captured_start()
        self.panel.input.setPlainText("Later draft")
        reply(response)
        self.assertEqual(original["state"], "accepted")
        self.assertIsNone(self.panel.pending_submission)
        self.assertFalse(self.panel.uncertain_send)
        self.assertEqual(self.panel.thread_id, original["thread_id"])
        self.assertEqual(self.panel.input.toPlainText(), "Later draft")

    def test_deleted_thread_rejects_its_late_turn_acknowledgement(self):
        reply, response, original = self.captured_start()
        target = original["thread_id"]
        self.panel.apply_conversations({"revision": 1, "deleted": [target], "pending": []})
        reply(response)
        self.assertEqual(original["state"], "pending")  # The valid ACK was fenced, not applied.
        self.assertIsNone(self.panel.thread_id)
        self.assertIsNone(self.panel.pending_submission)
        self.assertNotIn(original["client_user_message_id"], self.panel.awaiting_native)
        self.assertNotIn(original["client_user_message_id"], self.panel.retained_submissions)
        self.assertNotIn(target, self.panel.drafts)
        self.assertEqual(self.panel.input.toPlainText(), "")

    def test_search_generation_pagination_and_archived_filter(self):
        calls = self.capture_calls()
        manager = ConversationManager(self.panel)
        self.addCleanup(lambda: manager.close() if fixtures.isValid(manager) else None)
        old = calls[-1]["done"]
        manager.search.setText("Curve")
        manager.timer.stop()
        manager.load()
        current = calls[-1]
        self.assertEqual(parse_qs(urlsplit(current["path"]).query)["search"], ["Curve"])
        current["done"]({"data": [{"id": "a", "name": "Curve A"}], "nextCursor": "opaque+cursor", "lifecycle_revision": 0})
        old({"data": [{"id": "old", "name": "Stale"}], "nextCursor": None})
        self.assertEqual(manager.rows.count(), 1)
        manager.load(append=True)
        self.assertEqual(parse_qs(urlsplit(calls[-1]["path"]).query)["cursor"], ["opaque+cursor"])
        calls[-1]["done"]({"data": [{"id": "a", "name": "Curve A"}, {"id": "b", "name": "Curve B"}], "nextCursor": None})
        self.assertEqual(manager.rows.count(), 2)
        manager.archived.setChecked(True)
        query = parse_qs(urlsplit(calls[-1]["path"]).query)
        self.assertEqual(query["archived"], ["true"])
        self.assertNotIn("cursor", query)

    def test_delete_requires_confirmation_and_unknown_item_remains_reconcilable(self):
        calls = self.capture_calls()
        manager = ConversationManager(self.panel)
        self.addCleanup(lambda: manager.close() if fixtures.isValid(manager) else None)
        calls[-1]["done"]({"data": [{"id": "a", "name": "A"}], "nextCursor": None})
        manager.rows.setCurrentRow(0)
        with patch.object(QtWidgets.QMessageBox, "question", return_value=QtWidgets.QMessageBox.No):
            manager.delete()
        self.assertFalse(any(row["path"] == "/threads/manage" for row in calls))
        with patch.object(QtWidgets.QMessageBox, "question", return_value=QtWidgets.QMessageBox.Yes) as question:
            manager.delete()
        self.assertIn("派生子对话", question.call_args.args[2])
        request = next(row for row in reversed(calls) if row["path"] == "/threads/manage")
        self.assertTrue(request["body"]["confirm_delete_with_descendants"])
        request["done"]({"confirmed": False, "conversations": {"revision": 1, "deleted": [],
            "pending": [{"thread_id": "a", "title": "A", "action": "delete", "state": "unknown"}]}})
        manager.load()
        calls[-1]["done"]({"data": [], "nextCursor": None, "lifecycle_revision": 1})
        self.assertEqual(manager.rows.count(), 1)
        manager.rows.setCurrentRow(0)
        self.assertFalse(manager.delete_button.isEnabled())
        self.assertTrue(manager.reconcile_button.isEnabled())
        self.assertNotIn("a", self.panel.deleted_threads)


if __name__ == "__main__":
    unittest.main()
