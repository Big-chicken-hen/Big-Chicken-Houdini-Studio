"""Native lifecycle scoping, destructive gates and unknown-response boundaries."""
import json
from contextlib import closing
import sqlite3
import unittest

import test_bridge as fixtures
from studio.codex.errors import BridgeError
from studio.common import StudioError


class ConversationTests(unittest.TestCase):
    setUp = fixtures.BridgeTests.setUp

    def thread(self, thread_id="thread-1", **fields):
        return {"id": thread_id, "cwd": str(self.bridge.cwd), "name": "Original",
                "status": {"type": "idle"}, **fields}

    def test_list_uses_title_search_cursor_archive_and_scope(self):
        self.client.handler = lambda *_: {"data": [self.thread(), self.thread("other", cwd=str(self.paths.root))],
                                         "nextCursor": "page-2"}
        value = self.bridge.route("GET", "/threads", {"search": ["曲线"], "cursor": ["page-1"], "archived": ["true"]}, {})
        self.assertEqual([row["id"] for row in value["data"]], ["thread-1"])
        self.assertEqual(value["nextCursor"], "page-2")
        self.assertEqual(self.client.calls[-1][1], {"cwd": str(self.bridge.cwd), "limit": 50,
            "searchTerm": "曲线", "cursor": "page-1", "archived": True, "sortKey": "updated_at", "sortDirection": "desc"})

    def test_mutations_require_target_and_response_workspace(self):
        self.client.handler = lambda *_: {"thread": self.thread("other")}
        with self.assertRaises(StudioError):
            self.bridge.conversations.mutate({"thread_id": "thread-1", "action": "rename", "name": "new"})
        self.assertEqual([name for name, _ in self.client.calls], ["thread/read"])
        self.client.handler = lambda method, _: {"thread": self.thread() if method == "thread/read" else self.thread("wrong")}
        value = self.bridge.conversations.mutate({"thread_id": "thread-1", "action": "unarchive"})
        self.assertFalse(value["confirmed"])
        self.assertIn("thread-1", self.bridge.conversations.pending)

    def test_delete_confirmation_and_current_turn_gate(self):
        body = {"thread_id": "thread-1", "action": "delete"}
        with self.assertRaises(StudioError) as error:
            self.bridge.conversations.mutate(body)
        self.assertEqual(error.exception.code, "DELETE_CONFIRMATION_REQUIRED")
        self.assertFalse(self.client.calls)
        self.client.handler = lambda *_: {"thread": self.thread()}
        body["confirm_delete_with_descendants"] = True
        for state in ("running", "unknown", "stopping"):
            self.bridge.codex_state = state
            with self.assertRaises(StudioError):
                self.bridge.conversations.mutate(body)
        self.bridge.codex_state = "idle"
        self.bridge.pending_requests["request"] = {"response_state": "unknown"}
        with self.assertRaises(StudioError):
            self.bridge.conversations.mutate(body)
        self.assertNotIn("thread/delete", [name for name, _ in self.client.calls])

    def test_delete_checks_old_unknown_receipts_without_modifying_them(self):
        self.client.handler = lambda *_: {"thread": self.thread()}
        ledger = self.paths.workspace(self.bridge.workspace_id) / "operations.sqlite"
        with closing(sqlite3.connect(ledger)) as db, db:
            db.execute("CREATE TABLE operations(receipt TEXT)")
            db.execute("INSERT INTO operations VALUES (?)", (json.dumps({"operation_id": "old", "owner_id": "session", "state": "unknown"}),))
            db.executemany("INSERT INTO operations VALUES (?)", [(json.dumps({"owner_id": "session", "state": "finished"}),)] * 40)
        before = ledger.read_bytes()
        with self.assertRaises(StudioError) as error:
            self.bridge.conversations.mutate({"thread_id": "thread-1", "action": "delete", "confirm_delete_with_descendants": True})
        self.assertEqual(error.exception.details["operation_id"], "old")
        self.assertEqual(before, ledger.read_bytes())

    def test_unknown_delete_absence_never_confirms_or_replays(self):
        def native(method, _):
            if method == "thread/read":
                return {"thread": self.thread("other")}
            raise BridgeError("CODEX_REQUEST_TIMEOUT", "lost", 504)
        self.client.handler = native
        body = {"thread_id": "other", "action": "delete", "confirm_delete_with_descendants": True}
        value = self.bridge.conversations.mutate(body)
        self.assertFalse(value["confirmed"])
        self.client.handler = lambda *_: (_ for _ in ()).throw(BridgeError("CODEX_RPC_ERROR", "not found", 404))
        self.assertFalse(self.bridge.conversations.reconcile({"thread_id": "other"})["confirmed"])
        with self.assertRaises(StudioError):
            self.bridge.conversations.mutate(body)
        self.assertEqual(sum(method == "thread/delete" for method, _ in self.client.calls), 1)
        self.client.sink({"method": "thread/deleted", "params": {"threadId": "other"}})
        self.assertIn("other", self.bridge.conversations.deleted)
        self.assertNotIn("other", self.bridge.conversations.pending)
        self.assertEqual(self.bridge.thread_id, "thread-1")
        self.assertEqual(self.bridge.events[-1]["params"]["threadId"], "other")

    def test_native_ack_and_late_response_preserve_confirmed_deletion(self):
        def native(method, _):
            if method == "thread/read":
                return {"thread": self.thread()}
            self.client.sink({"method": "thread/deleted", "params": {"threadId": "thread-1"}})
            raise BridgeError("CODEX_REQUEST_TIMEOUT", "lost", 504)
        self.client.handler = native
        value = self.bridge.conversations.mutate({"thread_id": "thread-1", "action": "delete", "confirm_delete_with_descendants": True})
        self.assertTrue(value["confirmed"])
        self.assertIsNone(self.bridge.thread_id)
        self.assertFalse(self.bridge.scene_trust.enabled)

    def test_unknown_rename_and_archive_positive_reconciliation(self):
        def native(method, _):
            if method == "thread/read":
                return {"thread": self.thread("other")}
            raise BridgeError("CODEX_REQUEST_TIMEOUT", "lost", 504)
        self.client.handler = native
        self.bridge.conversations.mutate({"thread_id": "other", "action": "rename", "name": "New title"})
        self.client.handler = lambda *_: {"thread": self.thread("other", name="New title")}
        self.assertTrue(self.bridge.conversations.reconcile({"thread_id": "other"})["confirmed"])
        self.client.handler = native
        self.bridge.conversations.mutate({"thread_id": "other", "action": "archive"})
        self.client.handler = lambda method, _: ({"thread": self.thread("other")} if method == "thread/read"
                                               else {"data": [self.thread("other")], "nextCursor": None})
        self.assertTrue(self.bridge.conversations.reconcile({"thread_id": "other"})["confirmed"])
        self.assertTrue(self.client.calls[-1][1]["archived"])

    def test_unknown_scope_notification_invalidates_list_without_deleting(self):
        self.client.sink({"method": "thread/deleted", "params": {"threadId": "foreign"}})
        self.assertGreater(self.bridge.conversations.revision, 0)
        self.assertFalse(self.bridge.conversations.deleted)
        self.assertFalse(self.bridge.events)

    def test_unknown_delete_cannot_be_bypassed_by_idle_turn_reconciliation(self):
        self.bridge.conversations.pending["thread-1"] = {"thread_id": "thread-1", "action": "delete", "state": "unknown"}
        self.bridge.codex_state = "idle"
        with self.assertRaises(StudioError) as error:
            self.bridge.start_turn({"text": "new work"})
        self.assertEqual(error.exception.code, "THREAD_MUTATION_UNKNOWN")
        with self.assertRaises(StudioError):
            self.bridge.select_thread("thread-2")
        self.assertFalse(self.client.calls)


if __name__ == "__main__":
    unittest.main()
