"""Original-account recovery across native process counters; no model or Houdini."""
import copy
import unittest

import test_bridge_steer as fixtures
from studio.common import StudioError


class BridgeSteerRecoveryTests(unittest.TestCase):
    setUp = fixtures.BridgeSteerTests.setUp
    make_bridge = fixtures.BridgeSteerTests.make_bridge
    body = fixtures.BridgeSteerTests.body
    steer = fixtures.BridgeSteerTests.steer

    def restart_unknown(self, *, revision=19, email="fixture@example.invalid"):
        self.client.on_send = lambda _ticket: None
        body = self.body()
        self.assertEqual(self.steer(body)["state"], "unknown")
        client = fixtures.Native()
        restarted = self.make_bridge(client)
        restarted.account.revision = revision
        restarted.account.value["account"]["email"] = email
        restarted.thread_id = restarted.turn_id = None
        restarted.codex_state = "idle"
        client.history = {"id": "thread-a", "cwd": str(restarted.cwd), "status": {"type": "idle"}, "turns": []}
        return body, client, restarted

    @staticmethod
    def add_item(client, body):
        client.history["turns"] = [{"id": "turn-a", "status": "completed", "items": [
            {"id": "original-native-item", "type": "userMessage", "clientId": body["client_user_message_id"], "content": []}]}]

    def test_fresh_bridge_no_thread_exposes_original_owner_and_queries_without_resume(self):
        body, client, bridge = self.restart_unknown()
        record = bridge.state()["unresolved_submissions"][0]
        self.assertEqual(record["snapshot"]["draft_text"], body["draft_text"])
        self.assertEqual(record["recovery_binding"], {"connection_generation": bridge.history.generation, "account_revision": 19})
        self.assertEqual((record["connection_generation"], record["account_revision"]), (body["connection_generation"], 3))
        self.add_item(client, body)
        value = bridge.reconcile({"client_user_message_id": body["client_user_message_id"]})
        self.assertEqual(value["submission"]["state"], "accepted")
        self.assertFalse(value["reconciled"])
        self.assertIsNone(bridge.thread_id)
        self.assertTrue(all(method == "thread/read" for method, _ in client.calls))
        self.assertNotIn("snapshot", value["submission"])
        self.assertEqual(value["submission"]["account_revision"], 3)
        for retry in (body, {**body, "connection_generation": bridge.history.generation}):
            with self.assertRaises(StudioError):
                bridge.route("POST", "/turn/steer", {}, retry)
        self.assertEqual(client.tickets, [])

    def test_different_account_with_equal_counter_never_receives_payload_or_queries(self):
        body, client, bridge = self.restart_unknown(revision=3, email="another@example.invalid")
        disk = bridge.submissions.path.read_bytes()
        record = bridge.state()["unresolved_submissions"][0]
        self.assertNotIn("snapshot", record)
        self.assertIsNone(record["recovery_binding"])
        original = bridge.submissions.records[body["client_user_message_id"]]
        self.assertNotIn("snapshot", bridge._submission_response(original)["submission"])
        with self.assertRaises(StudioError) as error:
            bridge.reconcile({"client_user_message_id": body["client_user_message_id"]})
        self.assertEqual(error.exception.code, "INPUT_ACCOUNT_CHANGED")
        self.assertEqual(client.calls, [])
        self.assertEqual(bridge.submissions.path.read_bytes(), disk)
        bridge.account.value["account"]["email"] = "fixture@example.invalid"
        bridge.account.revision = 20
        returned = bridge.state()["unresolved_submissions"][0]
        self.assertEqual(returned["snapshot"]["text"], body["text"])
        self.assertEqual(returned["account_revision"], 3)
        self.assertEqual(returned["recovery_binding"]["account_revision"], 20)

    def test_account_change_during_recovery_returns_no_old_history_or_payload(self):
        body, client, bridge = self.restart_unknown()
        self.add_item(client, body)
        original_request = client.request

        def changed(method, params):
            value = copy.deepcopy(original_request(method, params))
            if params.get("includeTurns"):
                bridge.account.revision += 1
                bridge.account.value["account"]["email"] = "another@example.invalid"
            return value

        client.request = changed
        value = bridge.reconcile({"client_user_message_id": body["client_user_message_id"]})
        self.assertNotIn("thread", value)
        self.assertFalse(value["reconciled"])
        self.assertEqual(value["submission"]["state"], "unknown")
        self.assertNotIn("snapshot", value["submission"])
        self.assertIsNone(value["submission"]["recovery_binding"])
        self.assertIn("snapshot", bridge.submissions.unresolved()[0])

    def test_current_account_history_confirms_old_counter_and_stale_read_is_fenced(self):
        body, client, bridge = self.restart_unknown()
        bridge.thread_id = "thread-a"
        self.add_item(client, body)
        page = {"thread": client.history, "history_available": True, "connection_generation": bridge.history.generation}

        def stale(*_args, **_kwargs):
            bridge.account.revision += 1
            return copy.deepcopy(page)

        bridge.history.page = stale
        with self.assertRaises(StudioError):
            bridge.route("GET", "/thread/history", {"thread_id": ["thread-a"]}, {})
        self.assertEqual(bridge.submissions.unresolved()[0]["state"], "unknown")
        bridge.history.page = lambda *_args, **_kwargs: copy.deepcopy(page)
        bridge.route("GET", "/thread/history", {"thread_id": ["thread-a"]}, {})
        original = bridge.submissions.records[body["client_user_message_id"]]
        self.assertEqual(original["state"], "accepted")
        self.assertEqual(original["account_revision"], 3)
        self.assertEqual(client.tickets, [])


if __name__ == "__main__":
    unittest.main()
