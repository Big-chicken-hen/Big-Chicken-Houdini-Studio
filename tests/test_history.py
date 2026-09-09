"""Native paging admission, capability fallback and cursor/scope behavior."""
import copy
from types import SimpleNamespace
import unittest

from studio.codex.errors import BridgeError, CodexRPCError
from studio.common import StudioError
from studio.history import NativeHistory


class NativeHistoryTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.turns = [{"id": str(i), "status": "completed", "itemsView": "full", "items": [
            {"id": "i" + str(i), "type": "agentMessage", "text": str(i)}]} for i in range(14)]
        self.handler = lambda *_: {"data": [], "nextCursor": None}
        self.bridge = SimpleNamespace(thread_id="a", conversations=SimpleNamespace(deleted=set()),
                                      client=SimpleNamespace(request=self.request), read_thread=self.read_thread)
        self.history = NativeHistory(self.bridge)

    def request(self, method, params):
        self.calls.append((method, params))
        return self.handler(method, params)

    def read_thread(self, thread_id):
        self.calls.append(("thread/read", {"threadId": thread_id}))
        return {"thread": {"id": thread_id, "turns": copy.deepcopy(self.turns)}}

    def test_native_pages_preserve_cursors_views_and_turn_scope(self):
        def handler(method, params):
            if method == "thread/turns/list":
                self.assertEqual(params["itemsView"], "full")
                return {"data": [self.turns[-1], self.turns[-2]], "nextCursor": "native-cursor"}
            self.assertEqual(params["turnId"], "13")
            return {"data": [{"turnId": "13", "item": self.turns[-1]["items"][0]}], "nextCursor": None}
        self.handler = handler
        page = self.history.page("a")
        self.assertEqual(page["next_cursor"], "native-cursor")
        self.assertEqual([t["id"] for t in page["thread"]["turns"]], ["12", "13"])
        self.history.page("a", cursor="native-cursor")
        self.assertEqual(self.calls[-1][1]["cursor"], "native-cursor")
        item_page = self.history.page("a", turn_id="13")
        self.assertEqual(item_page["thread"]["turns"][0]["items"][0]["text"], "13")
        self.assertNotIn("status", item_page["thread"]["turns"][0])
        self.assertFalse(any(method == "thread/read" for method, _ in self.calls))

    def test_unsupported_is_cached_per_connection_and_fallback_uses_stable_anchor(self):
        def unsupported(method, _params):
            raise CodexRPCError(method, {"code": -32600, "message": "list_turns is not supported yet"})
        self.handler = unsupported
        first = self.history.page("a")
        self.assertEqual(len(first["thread"]["turns"]), 8)
        self.turns.append({"id": "new", "items": []})
        older = self.history.page("a", cursor=first["next_cursor"])
        self.assertEqual([t["id"] for t in older["thread"]["turns"]], [str(i) for i in range(6)])
        self.assertEqual(sum(m == "thread/turns/list" for m, _ in self.calls), 1)
        self.history.reset()
        self.history.page("a")
        self.assertEqual(sum(m == "thread/turns/list" for m, _ in self.calls), 2)

    def test_transient_failures_are_not_unsupported_and_never_fall_back(self):
        def failed(*_):
            raise BridgeError("CODEX_REQUEST_TIMEOUT", "not confirmed", 504)
        self.handler = failed
        with self.assertRaises(BridgeError):
            self.history.page("a")
        self.assertFalse(self.history.unsupported)
        self.assertEqual(len(self.calls), 1)

    def test_changed_connection_thread_or_deleted_target_rejects_late_history(self):
        for change in (lambda: self.history.reset(), lambda: setattr(self.bridge, "thread_id", "b"),
                       lambda: self.bridge.conversations.deleted.add("a")):
            self.bridge.thread_id = "a"
            self.bridge.conversations.deleted.clear()
            def handler(*_):
                change()
                return {"data": [], "nextCursor": None}
            self.handler = handler
            with self.assertRaises(StudioError):
                self.history.page("a")

    def test_wrong_turn_page_and_foreign_fallback_cursor_are_rejected(self):
        self.handler = lambda *_: {"data": [{"turnId": "other", "item": {"id": "i"}}]}
        with self.assertRaises(StudioError):
            self.history.page("a", turn_id="13")
        self.history.unsupported.add("thread/turns/list")
        with self.assertRaises(StudioError):
            self.history.page("a", cursor='{"fallback_thread":"other","turn":null,"before":"1"}')

    def test_terminal_fact_is_captured_before_the_non_atomic_item_read(self):
        self.bridge.completed_turns = []
        def handler(*_):
            self.bridge.completed_turns.append("13")
            return {"data": [{"turnId": "13", "item": self.turns[-1]["items"][0]}]}
        self.handler = handler
        early = self.history.page("a", turn_id="13")
        self.assertFalse(early["thread"]["turns"][0]["history_turn_terminal"])
        late = self.history.page("a", turn_id="13")
        self.assertTrue(late["thread"]["turns"][0]["history_turn_terminal"])


if __name__ == "__main__":
    unittest.main()
