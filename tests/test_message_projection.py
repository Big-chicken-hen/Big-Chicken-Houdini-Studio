"""Identity/authority rules independent of Qt rendering or persistence."""
import unittest

from studio.message_projection import MessageProjection


class MessageProjectionTests(unittest.TestCase):
    def setUp(self):
        self.p = MessageProjection()
        self.p.bind("a", 1)
        self.sequence = 0

    def event(self, method, *, generation=1, thread="a", turn="t", **params):
        self.sequence += 1
        event = {"sequence": self.sequence, "method": method,
                 "params": {"threadId": thread, "turnId": turn, **params}}
        self.p.event(event, generation)
        return event

    @staticmethod
    def item(text, item_id="i"):
        return {"id": item_id, "type": "agentMessage", "text": text}

    def record(self, turn="t", item="i"):
        return self.p.records[self.p.key(turn, item)]

    def history(self, text, *, revision=1, view="full", status="inProgress", generation=1):
        return self.p.history({"id": "a", "turns": [{"id": "t", "itemsView": view,
            "status": status, "items": [self.item(text)]}]}, generation, revision)

    def test_missing_start_never_guesses_a_prefix_and_short_terminal_wins(self):
        self.event("item/agentMessage/delta", itemId="i", delta="unknown tail")
        self.assertEqual(self.record().item["text"], "")
        self.history("known snapshot")
        self.event("item/agentMessage/delta", itemId="i", delta="overlapping tail")
        self.assertEqual(self.record().item["text"], "known snapshot")
        self.assertTrue(self.record().recovering)
        self.event("item/completed", item=self.item("ok"))
        self.event("item/agentMessage/delta", itemId="i", delta="late")
        self.history("much longer snapshot", revision=2, status="completed")
        self.assertEqual(self.record().item["text"], "ok")

    def test_duplicate_sequences_are_distinct_from_legitimate_repeated_text(self):
        self.event("item/started", item=self.item(""))
        first = self.event("item/agentMessage/delta", itemId="i", delta="repeat")
        self.p.event(first, 1)
        self.event("item/agentMessage/delta", itemId="i", delta="repeat")
        self.assertEqual(self.record().item["text"], "repeatrepeat")
        self.event("item/completed", item=self.item("repeatrepeat"))
        self.event("item/completed", item=self.item("repeatrepeat", "other"))
        self.assertEqual(len(self.p.records), 2)

    def test_connection_and_a_b_a_fence_old_callbacks(self):
        self.event("item/started", item=self.item("trusted prefix"))
        self.p.bind("a", 2)
        self.event("item/completed", generation=1, item=self.item("stale"))
        self.history("stale history", generation=1)
        self.assertEqual(self.record().item["text"], "trusted prefix")
        self.assertTrue(self.record().recovering)
        self.p.bind("b", 3)
        self.event("item/completed", generation=2, item=self.item("old a"))
        self.p.bind("a", 4)
        self.event("item/completed", generation=2, item=self.item("old a again"))
        self.assertEqual(self.p.records, {})

    def test_summary_and_old_history_request_do_not_replace_full_source(self):
        self.history("current full", revision=4)
        self.history("stale", revision=3)
        self.history("summary", revision=5, view="summary", status="completed")
        self.history("", revision=6, view="notLoaded", status="completed")
        self.assertEqual(self.record().item["text"], "current full")

    def test_gap_and_missing_terminal_recover_only_from_full_history(self):
        self.event("item/started", item=self.item("start"))
        self.p.mark_gap("t")
        self.event("item/agentMessage/delta", itemId="i", delta="after gap")
        self.assertEqual(self.record().item["text"], "start")
        self.event("turn/completed", turn="t", status="completed")
        self.history("complete native body", status="completed")
        self.assertTrue(self.record().terminal)
        self.assertFalse(self.p.recovering_turns())

    def test_partial_pages_preserve_uncovered_items_and_order(self):
        self.event("item/completed", turn="new", item=self.item("live", "newest"))
        self.p.history({"id": "a", "turns": [{"id": "old", "itemsView": "full", "status": "completed",
            "items": [self.item("old", "first")]}, {"id": "new", "itemsView": "full",
            "items": [self.item("earlier", "earlier")]}]}, 1, 1)
        self.assertEqual([(k.turn, k.item) for k in self.p.ordered_keys()],
                         [("old", "first"), ("new", "earlier"), ("new", "newest")])
        self.history("", revision=2, view="notLoaded")
        self.assertEqual(len(self.p.records), 3)

    def test_turn_completion_does_not_promote_an_earlier_active_snapshot(self):
        self.event("item/started", item=self.item("prefix"))
        self.event("turn/completed", status="completed")
        self.history("old partial snapshot", status="inProgress")
        self.assertFalse(self.record().terminal)
        self.assertTrue(self.record().recovering)
        self.history("complete native output", revision=2, status="completed")
        self.assertEqual(self.record().item["text"], "complete native output")
        self.assertTrue(self.record().terminal)

    def test_new_recent_turns_append_but_explicit_older_pages_prepend(self):
        self.history("old", status="completed")
        self.p.history({"id": "a", "turns": [{"id": "new", "status": "completed", "items": []}]}, 1, 2)
        self.p.history({"id": "a", "turns": [{"id": "earliest", "status": "completed", "items": []}]}, 1, 3, older=True)
        self.assertEqual(self.p.turns, ["earliest", "t", "new"])


if __name__ == "__main__":
    unittest.main()
