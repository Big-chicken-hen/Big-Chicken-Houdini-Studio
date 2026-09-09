"""Panel request fences and targeted native history recovery."""
import copy
import unittest
from urllib.parse import parse_qs, urlsplit

from PySide6 import QtTest

import test_ui as fixtures


class HistoryRaceTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.PanelTest.setUpClass.__func__)
    setUp = fixtures.PanelTest.setUp
    tearDown = fixtures.PanelTest.tearDown

    def event(self, method, *, sequence=None, turn="race", **params):
        sequence = sequence or self.panel.cursor + 1
        return {"sequence": sequence, "method": method,
                "params": {"threadId": "preview_thread", "turnId": turn, **params}}

    def deliver(self, events, **extra):
        self.panel.apply_events({"cursor": events[-1]["sequence"], "events": events, **extra})

    def test_terminal_is_visible_before_late_history_and_duplicate_poll_does_not_append(self):
        self.api.hold["/thread/history"] = []
        self.panel.load_history()
        loaded = self.api.hold["/thread/history"].pop()[0]
        self.deliver([self.event("item/started", item={"id": "reply", "type": "agentMessage", "text": ""})])
        delta = self.event("item/agentMessage/delta", itemId="reply", delta="合法重复")
        self.deliver([delta, copy.deepcopy(delta)])
        self.assertEqual(self.panel.transcript.card("reply").source_text(), "合法重复")
        final = {"id": "reply", "type": "agentMessage", "text": "完整终态 END"}
        self.deliver([self.event("item/completed", item=final)])
        self.assertEqual(self.panel.transcript.card("reply").text.toPlainText(), "完整终态 END")
        loaded({"thread": {"id": "preview_thread", "turns": [{"id": "race", "status": "completed",
            "itemsView": "summary", "items": [{**final, "text": "摘要"}]}]}})
        self.assertEqual(self.panel.transcript.card("reply").source_text(), final["text"])

    def test_a_b_a_and_reconnection_reject_old_history_callbacks(self):
        self.api.hold["/thread/history"] = []
        self.panel.load_history()
        old_a = self.api.hold["/thread/history"].pop()[0]
        self.panel.thread_id = "b"
        self.panel.load_history()
        old_b = self.api.hold["/thread/history"].pop()[0]
        self.panel.thread_id = "preview_thread"
        self.panel.load_history()
        current = self.api.hold["/thread/history"].pop()[0]
        old_a({"thread": self.api.thread})
        old_b({"thread": {"id": "b", "turns": []}})
        self.assertEqual(self.panel.transcript.cards, {})
        current({"thread": self.api.thread})
        self.assertEqual(len(self.panel.transcript.cards), 3)
        self.panel.load_history()
        late = self.api.hold["/thread/history"].pop()[0]
        self.panel.advance_connection()
        source = self.panel.transcript.card("agent_1").source_text()
        changed = copy.deepcopy(self.api.thread)
        changed["turns"][0]["items"][1]["text"] = "old connection"
        late({"thread": changed})
        self.assertEqual(self.panel.transcript.card("agent_1").source_text(), source)

    def test_missing_start_and_overflow_repair_target_turn_only(self):
        self.api.hold["/thread/history"] = []
        self.deliver([self.event("item/agentMessage/delta", itemId="gap", delta="tail")], resync_required=True)
        self.assertEqual(self.panel.transcript.card("gap").source_text(), "")
        self.panel.history_refresh.stop()
        self.panel.read_pending_history()
        call = next(call for call in reversed(self.api.calls) if call[1].startswith("/thread/history?"))
        query = parse_qs(urlsplit(call[1]).query)
        self.assertIn("turn_id", query)
        self.api.hold["/thread/history"].pop()[0]({"thread": {"id": "preview_thread", "turns": []}})
        final = {"id": "gap", "type": "agentMessage", "text": "recovered full END"}
        self.deliver([self.event("item/completed", item=final)])
        self.assertEqual(self.panel.transcript.card("gap").source_text(), final["text"])

    def test_archive_delete_fence_queued_history_and_late_items(self):
        self.api.hold["/thread/history"] = []
        self.panel.load_history()
        archived_read = self.api.hold["/thread/history"].pop()[0]
        self.deliver([self.event("thread/archived")])
        self.deliver([self.event("item/completed", item={"id": "late", "type": "agentMessage", "text": "old"})])
        archived_read({"thread": self.api.thread})
        self.assertFalse(any(key.item == "late" for key in self.panel.transcript.cards))
        self.deliver([self.event("thread/deleted")])
        self.deliver([self.event("item/completed", item={"id": "late", "type": "agentMessage", "text": "old"})])
        QtTest.QTest.qWait(10)
        self.assertEqual(self.panel.transcript.cards, {})


if __name__ == "__main__":
    unittest.main()
