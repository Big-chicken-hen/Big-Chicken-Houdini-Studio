"""User-input admission races; controlled native replies, no model or Houdini."""
import copy
from pathlib import Path
from types import SimpleNamespace
import tempfile
import threading
import unittest
from unittest.mock import patch

from studio.bridge import Bridge
from studio.codex.errors import BridgeError, CodexRPCError
from studio.common import AppPaths, StudioError, new_id
from studio.workspace import Workspaces


class Native:
    is_running = True

    def __init__(self):
        self.calls, self.tickets = [], []
        self.active_tickets = {}
        self.on_send = None
        self.history = {"id": "thread-a", "turns": []}

    def set_event_sink(self, sink):
        self.sink = sink

    def prepare_tracked_request(self, method, params, callback):
        if len(self.active_tickets) >= 16:
            raise BridgeError("CODEX_SEND_CAPACITY", "Original RPCs still occupy the correlation bound", 409)
        ticket = SimpleNamespace(request_id=len(self.tickets), method=method, params=params, callback=callback,
                                 forward_attempted=False, settled=False, result=None, error=None,
                                 event=threading.Event())
        self.tickets.append(ticket)
        self.active_tickets[ticket.request_id] = ticket
        return ticket

    def send_prepared(self, ticket):
        if ticket.forward_attempted:
            raise AssertionError("Input replay")
        ticket.forward_attempted = True
        self.calls.append((ticket.method, copy.deepcopy(ticket.params)))
        if self.on_send:
            self.on_send(ticket)
        else:
            self.finish(ticket, {"turnId": ticket.params.get("expectedTurnId")} if ticket.method == "turn/steer"
                        else {"turn": {"id": "new-turn", "status": "inProgress"}})

    def finish(self, ticket, result=None, error=None):
        ticket.result, ticket.error, ticket.settled = result, error, True
        self.active_tickets.pop(ticket.request_id, None)
        ticket.callback(ticket, result, error)
        ticket.event.set()

    def wait_prepared(self, ticket, timeout_seconds=None):
        if not ticket.event.wait(timeout_seconds or .03):
            raise BridgeError("CODEX_REQUEST_TIMEOUT", "fixture reply loss", 504)
        if ticket.error:
            raise ticket.error
        return ticket.result

    def discard_prepared(self, ticket):
        if ticket.forward_attempted:
            raise AssertionError("Cannot discard forwarded request")
        self.active_tickets.pop(ticket.request_id, None)

    def retire_confirmed(self, ticket):
        ticket.settled = True
        ticket.error = BridgeError("CODEX_REQUEST_EXTERNALLY_CONFIRMED", "Native item confirmed input")
        self.active_tickets.pop(ticket.request_id, None)
        ticket.event.set()
        return True

    def request(self, method, params):
        self.calls.append((method, copy.deepcopy(params)))
        if method == "model/list":
            return {"data": [{"model": "image-model", "inputModalities": ["text", "image"],
                               "supportedReasoningEfforts": [{"reasoningEffort": "high"}]},
                              {"model": "text-model", "inputModalities": ["text"],
                               "supportedReasoningEfforts": []}], "nextCursor": None}
        if method == "thread/read":
            return {"thread": self.history}
        return {}


class Runtime:
    def __init__(self):
        self.calls = []
        self.health = {"runtime_id": "runtime-a", "scene": {"scene_epoch": "scene-a"},
                       "main_thread_busy": True, "active_operation_id": "existing-operation"}

    def call(self, method, path, body=None, **_kwargs):
        self.calls.append((method, path, body))
        return copy.deepcopy(self.health) if path == "/health" else {"confirmed": True}


class BridgeSteerTests(unittest.TestCase):
    def setUp(self):
        base = Path(__file__).resolve().parents[1] / ".runtime" / "steer-tests"
        base.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        (root / "pyproject.toml").write_text("# isolated fixture", encoding="utf-8")
        self.paths = AppPaths(root)
        self.workspace = Workspaces(self.paths).create("Steer fixture")["workspace_id"]
        self.client, self.runtime = Native(), Runtime()
        self.bridge = self.make_bridge(self.client)
        self.client.history["cwd"] = str(self.bridge.cwd)

    def make_bridge(self, client):
        bridge = Bridge(self.paths, self.workspace, "fixture", "fixture-token-not-authentication", "unused", client)
        bridge.account.value = {"status": "signed_in", "account": {"type": "chatgpt", "email": "fixture@example.invalid"}}
        bridge.account.revision = 3
        bridge.thread_id, bridge.turn_id, bridge.codex_state = "thread-a", "turn-a", "running"
        bridge.settings.bind("thread-a", {"model": "image-model", "reasoningEffort": "high"})
        bridge.settings.requested("thread-a", {})
        bridge.settings.admitted("turn-a")
        bridge._runtime = self.runtime
        return bridge

    def body(self, **changes):
        generation = self.bridge.history.generation
        return {"text": "相同的引导", "draft_text": "相同的引导", "draft_version": 8, "attachments": [],
                "connection_generation": generation, "client_user_message_id": generation + "." + new_id(),
                "expected_thread_id": "thread-a", "expected_turn_id": "turn-a", "account_revision": 3,
                "expected_turn_revision": self.bridge.turn_revision, **changes}

    def steer(self, body=None):
        return self.bridge.route("POST", "/turn/steer", {}, body or self.body())["submission"]

    def test_three_equal_text_inputs_are_ordered_and_old_ids_never_forward_again(self):
        bodies = [self.body() for _ in range(3)]
        self.bridge.pending_requests["approval"] = {"params": {"turnId": "turn-a"}}
        settings = self.bridge.settings.snapshot()
        for body in bodies:
            self.assertEqual(self.steer(body)["state"], "accepted")
        self.assertEqual([value["clientUserMessageId"] for method, value in self.client.calls if method == "turn/steer"],
                         [body["client_user_message_id"] for body in bodies])
        self.assertEqual(self.steer(bodies[0])["state"], "accepted")
        self.assertEqual(len(self.client.tickets), 3)
        self.assertEqual(self.bridge.settings.snapshot(), settings)
        self.assertIn("approval", self.bridge.pending_requests)
        self.assertEqual(self.runtime.calls, [])
        self.assertTrue(all("snapshot" not in record for record in self.bridge.submissions.records.values()))
        with self.assertRaises(StudioError):
            self.steer({**bodies[0], "text": "changed payload"})

    def test_unknown_blocks_other_panel_and_stop_then_terminal_outlast_late_ack(self):
        self.client.on_send = lambda _ticket: None
        original = self.body()
        self.assertEqual(self.steer(original)["state"], "unknown")
        self.assertEqual(self.steer()["state"], "not_submitted")
        self.assertEqual(self.steer(original)["state"], "unknown")
        self.bridge.stop()
        self.assertIn(("turn/interrupt", {"threadId": "thread-a", "turnId": "turn-a"}), self.client.calls)
        self.bridge.on_event({"method": "turn/completed", "params": {"threadId": "thread-a", "turn": {"id": "turn-a", "status": "interrupted"}}})
        self.client.finish(self.client.tickets[0], {"turnId": "turn-a"})
        self.assertEqual(self.bridge.codex_state, "interrupted")
        self.assertIsNone(self.bridge.turn_id)
        self.assertTrue(self.bridge.stop_requested)
        self.assertTrue(self.bridge.owner_stopped)
        self.assertEqual(self.steer(original)["state"], "accepted")
        self.assertEqual(len(self.client.tickets), 1)

    def test_click_intent_rejections_never_fall_back_and_stop_wins_before_forward(self):
        self.bridge.turn_id, self.bridge.codex_state = None, "completed"
        self.assertEqual(self.steer()["error"]["code"], "STEER_TURN_ENDED")
        self.bridge.turn_id, self.bridge.codex_state = "turn-b", "running"
        self.assertEqual(self.steer()["error"]["code"], "STEER_TURN_CHANGED")
        self.bridge.turn_id = "turn-a"
        self.bridge.stop_requested = True
        self.assertEqual(self.steer()["error"]["code"], "STOP_REQUESTED")
        self.assertEqual(self.client.tickets, [])
        self.assertFalse(any(method == "turn/start" for method, _ in self.client.calls))

    def test_exact_native_item_confirms_same_turn_without_text_matching_or_replay(self):
        self.client.on_send = lambda _ticket: None
        body = self.body()
        self.assertEqual(self.steer(body)["state"], "unknown")
        item = {"id": "native-user", "type": "userMessage", "clientId": body["client_user_message_id"], "content": []}
        for thread, turn in (("thread-b", "turn-a"), ("thread-a", "turn-b")):
            self.bridge.on_event({"method": "item/completed", "params": {"threadId": thread, "turnId": turn, "item": item}})
            self.assertEqual(self.steer(body)["state"], "unknown")
        self.bridge.on_event({"method": "item/completed", "params": {"threadId": "thread-a", "turnId": "turn-a", "item": item}})
        confirmed = self.steer(body)
        self.assertEqual((confirmed["state"], confirmed["native_item_id"]), ("accepted", "native-user"))
        self.assertNotIn("snapshot", confirmed)
        self.assertEqual(len(self.client.tickets), 1)

    def test_restart_retains_original_unknown_and_never_rebinds_old_id(self):
        self.client.on_send = lambda _ticket: None
        body = self.body()
        self.steer(body)
        replacement = Native()
        restarted = self.make_bridge(replacement)
        self.assertEqual(restarted.submissions.unresolved()[0]["snapshot"]["draft_text"], body["draft_text"])
        for retry in (body, {**body, "connection_generation": restarted.history.generation}):
            with self.assertRaises(StudioError):
                restarted.route("POST", "/turn/steer", {}, retry)
        replacement.history = {"id": "thread-a", "cwd": str(restarted.cwd), "status": {"type": "idle"},
            "turns": [{"id": "turn-a", "status": "completed", "items": [{"id": "saved-native", "type": "userMessage",
            "clientId": body["client_user_message_id"], "content": []}]}]}
        value = restarted.reconcile({"client_user_message_id": body["client_user_message_id"]})
        self.assertEqual(value["submission"]["state"], "accepted")
        self.assertEqual(value["submission"]["connection_generation"], body["connection_generation"])
        self.assertEqual(replacement.tickets, [])

    def test_selection_and_images_use_current_facts_without_context_or_owner_resume(self):
        folder = self.paths.workspace(self.workspace) / "attachments"
        folder.mkdir()
        image = new_id() + ".png"
        (folder / image).write_bytes(b"fixture image already prepared")
        self.bridge.settings.turn["model"] = "text-model"
        self.assertEqual(self.steer(self.body(attachments=[image]))["error"]["code"], "MODEL_IMAGE_UNSUPPORTED")
        self.bridge.settings.turn["model"] = "image-model"
        self.assertEqual(self.steer(self.body(selection_reference={"scene_epoch": "old", "nodes": ["/obj/window"]}))["error"]["code"], "SELECTION_STALE")
        self.assertEqual(self.steer(self.body(attachments=[image], selection_reference={"scene_epoch": "scene-a", "nodes": ["/obj/window"]}))["state"], "accepted")
        self.assertTrue(all(path == "/health" for _, path, _ in self.runtime.calls))
        self.assertFalse(any(method in {"thread/resume", "turn/start"} for method, _ in self.client.calls))

    def test_new_start_identity_acceptance_and_late_terminal_keep_start_fences(self):
        self.bridge.turn_id, self.bridge.codex_state = None, "idle"
        self.runtime.health.update(main_thread_busy=False, active_operation_id=None)
        body = self.body(model="image-model", effort="high", settings_revision=self.bridge.settings.revision)
        body.pop("expected_turn_id")
        def completed(ticket):
            self.bridge.on_event({"method": "turn/completed", "params": {"threadId": "thread-a", "turn": {"id": "new-turn", "status": "completed"}}})
            self.client.finish(ticket, {"turn": {"id": "new-turn", "status": "inProgress"}})
        self.client.on_send = completed
        result = self.bridge.start_turn(body)
        self.assertEqual(result["submission"]["state"], "accepted")
        self.assertEqual(self.bridge.codex_state, "completed")
        self.assertIsNone(self.bridge.turn_id)
        self.assertEqual(self.client.tickets[0].params["clientUserMessageId"], body["client_user_message_id"])

    def test_unknown_approval_blocks_but_unclassified_native_error_stays_unknown(self):
        self.bridge.pending_requests["approval"] = {"response_state": "unknown"}
        self.assertEqual(self.steer()["error"]["code"], "APPROVAL_RESPONSE_UNKNOWN")
        self.bridge.pending_requests.clear()
        self.client.on_send = lambda ticket: self.client.finish(ticket, error=CodexRPCError("turn/steer", {"code": -32603, "message": "ambiguous internal failure"}))
        self.assertEqual(self.steer()["state"], "unknown")

    def test_stop_is_dispatched_while_original_send_waits_for_ack(self):
        forwarded, result = threading.Event(), []
        self.client.on_send = lambda _ticket: forwarded.set()
        def wait(ticket, timeout_seconds=None):
            if not ticket.event.wait(2):
                raise BridgeError("CODEX_REQUEST_TIMEOUT", "test ACK remained held", 504)
            return ticket.result
        self.client.wait_prepared = wait
        worker = threading.Thread(target=lambda: result.append(self.steer()))
        worker.start()
        try:
            self.assertTrue(forwarded.wait(1))
            self.bridge.stop()
            self.assertTrue(worker.is_alive(), "Stop incorrectly waited for the input ACK")
            self.assertIn(("turn/interrupt", {"threadId": "thread-a", "turnId": "turn-a"}), self.client.calls)
            self.client.finish(self.client.tickets[0], {"turnId": "turn-a"})
            worker.join(1)
            self.assertFalse(worker.is_alive())
            self.assertEqual(result[0]["state"], "accepted")
            self.assertEqual(self.bridge.codex_state, "stopping")
            self.assertTrue(self.bridge.stop_requested)
        finally:
            if self.client.tickets:
                self.client.tickets[0].event.set()
            worker.join(3)

    def test_start_validation_cannot_erase_a_stop_that_won_before_forward(self):
        self.bridge.turn_id, self.bridge.codex_state = None, "idle"
        self.runtime.health.update(main_thread_busy=False, active_operation_id=None)
        self.bridge.models.validate = lambda *_args: self.bridge.stop()
        body = self.body(model="image-model", settings_revision=self.bridge.settings.revision)
        body.pop("expected_turn_id")
        result = self.bridge.start_turn(body)["submission"]
        self.assertEqual((result["state"], result["error"]["code"]), ("not_submitted", "TURN_STATE_CHANGED"))
        self.assertTrue(self.bridge.stop_requested)
        self.assertTrue(self.bridge.owner_stopped)
        self.assertFalse(any(ticket.forward_attempted for ticket in self.client.tickets))
        with self.assertRaises(StudioError) as failure:
            self.bridge.start_turn({"text": "legacy caller", "model": "image-model"})
        self.assertEqual(failure.exception.code, "TURN_STATE_CHANGED")
        self.assertFalse(any(method == "turn/start" for method, _ in self.client.calls))

    def test_compact_ids_survive_thread_account_and_stop_changes_until_new_generation(self):
        body = self.body()
        self.steer(body)
        for thread in ("thread-b", "thread-a"):
            self.bridge.thread_id = thread
            self.assertEqual(self.steer(body)["state"], "accepted")
        self.bridge.account.revision += 1
        self.bridge.stop()
        self.assertEqual(self.steer(body)["state"], "accepted")
        self.assertEqual(len(self.client.tickets), 1)
        self.bridge.on_event({"type": "process_started"})
        with self.assertRaises(StudioError):
            self.steer(body)
        with self.assertRaises(StudioError):
            self.steer({**body, "connection_generation": self.bridge.history.generation})
        self.assertEqual(len(self.client.tickets), 1)

    def test_native_items_release_rpc_capacity_and_waiters_beyond_sixteen_missing_acks(self):
        def native_item(ticket):
            self.bridge.on_event({"method": "item/completed", "params": {"threadId": "thread-a", "turnId": "turn-a",
                "item": {"id": "item-" + str(ticket.request_id), "type": "userMessage",
                         "clientId": ticket.params["clientUserMessageId"], "content": []}}})
        self.client.on_send = native_item
        for _ in range(18):
            result = self.steer()
            self.assertEqual((result["state"], result["confirmation_source"]), ("accepted", "native_item"))
            self.assertEqual(self.client.active_tickets, {})
            self.assertEqual(self.bridge.submission_tickets, {})
        self.assertEqual(len(self.client.tickets), 18)
        self.assertTrue(all(ticket.event.is_set() for ticket in self.client.tickets))

    def test_recovery_absence_account_change_and_changed_read_generation_never_confirm(self):
        self.client.on_send = lambda _ticket: None
        body = self.body()
        self.steer(body)
        client = Native()
        restarted = self.make_bridge(client)
        client.history = {"id": "thread-a", "cwd": str(restarted.cwd), "status": {"type": "idle"}, "turns": []}
        query = {"client_user_message_id": body["client_user_message_id"]}
        record = restarted.reconcile(query)["submission"]
        self.assertEqual(record["state"], "unknown")
        self.assertEqual(record["snapshot"]["draft_text"], body["draft_text"])
        restarted.account.value["account"]["email"] = "different@example.invalid"
        before = len(client.calls)
        with self.assertRaises(StudioError) as failure:
            restarted.reconcile(query)
        self.assertEqual(failure.exception.code, "INPUT_ACCOUNT_CHANGED")
        self.assertEqual(len(client.calls), before)
        restarted.account.value["account"]["email"] = "fixture@example.invalid"
        client.history["turns"] = [{"id": "turn-a", "status": "completed", "items": [{"id": "native-item",
            "type": "userMessage", "clientId": body["client_user_message_id"], "content": []}]}]
        original_request = client.request
        for change in (lambda: restarted.history.reset(), lambda: setattr(restarted.account, "revision", restarted.account.revision + 1)):
            def changed_read(method, params):
                value = original_request(method, params)
                change()
                return value
            client.request = changed_read
            result = restarted.reconcile(query)
            self.assertFalse(result["reconciled"])
            self.assertEqual(result["submission"]["state"], "unknown")
            self.assertIn("snapshot", result["submission"])
        self.assertEqual(client.tickets, [])

    def test_corrupt_and_failed_pending_storage_preserves_original_bytes_and_never_forwards(self):
        path = self.bridge.submissions.path
        path.write_text("{corrupt original pending input", encoding="utf-8")
        corrupt = path.read_bytes()
        client = Native()
        damaged = self.make_bridge(client)
        generation = damaged.history.generation
        body = self.body(connection_generation=generation, client_user_message_id=generation + "." + new_id())
        result = damaged.route("POST", "/turn/steer", {}, body)["submission"]
        self.assertEqual(result["state"], "not_submitted")
        self.assertEqual(path.read_bytes(), corrupt)
        self.assertTrue(damaged.submissions.fault)
        self.assertEqual(client.tickets, [])
        # A separate, valid fixture snapshot is not replaced when a first write fails.
        path.write_text('{"format":1,"pending":[]}', encoding="utf-8")
        original = path.read_bytes()
        fresh_client = Native()
        fresh = self.make_bridge(fresh_client)
        generation = fresh.history.generation
        body = self.body(connection_generation=generation, client_user_message_id=generation + "." + new_id())
        with patch("studio.submissions.atomic_json", side_effect=OSError("fixture disk failure")):
            result = fresh.route("POST", "/turn/steer", {}, body)["submission"]
        self.assertEqual(result["state"], "not_submitted")
        self.assertTrue(fresh.submissions.fault)
        self.assertTrue(all(not ticket.forward_attempted for ticket in fresh_client.tickets))
        self.assertEqual(path.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
