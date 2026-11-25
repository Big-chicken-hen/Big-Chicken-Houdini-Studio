"""Native settings/catalog identity and request snapshots; no inference or GUI."""
import tempfile
import unittest
from pathlib import Path

from studio.bridge import Bridge
from studio.codex.errors import BridgeError
from studio.common import AppPaths, StudioError
from studio.workspace import Workspaces


def model(slug, effort="high", **values):
    return {"id": "display-id-" + slug, "model": slug, "displayName": slug, "hidden": False,
            "isDefault": False, "defaultReasoningEffort": effort,
            "supportedReasoningEfforts": [{"reasoningEffort": effort}], "inputModalities": ["text", "image"], **values}


class NativeClient:
    is_running = True

    def __init__(self):
        self.calls, self.pages = [], [{"data": [model("model-a"), model("model-b", "minimal")], "nextCursor": None}]
        self.hook = None
        self.turn_number = 0

    def set_event_sink(self, sink):
        self.sink = sink

    def request(self, method, params):
        self.calls.append((method, params))
        if self.hook:
            value = self.hook(method, params)
            if value is not None:
                return value
        if method == "thread/read":
            return {"thread": {"id": params["threadId"], "cwd": self.cwd}}
        if method in {"thread/start", "thread/resume"}:
            return {"thread": {"id": params.get("threadId", "new-thread"), "cwd": self.cwd,
                               "turns": [], "status": {"type": "idle"}},
                    "model": "model-b", "reasoningEffort": "minimal"}
        if method == "model/list":
            return self.pages[int(params.get("cursor", 0))]
        if method == "turn/start":
            self.turn_number += 1
            return {"turn": {"id": "turn-" + str(self.turn_number)}}
        raise AssertionError(method)


class ModelSettingsTests(unittest.TestCase):
    def setUp(self):
        base = Path(__file__).resolve().parents[1] / ".runtime/tests"
        base.mkdir(parents=True, exist_ok=True)
        temp = tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        (root / "pyproject.toml").write_text("# fixture", encoding="utf-8")
        self.paths = AppPaths(root)
        workspace = Workspaces(self.paths).create("model fixture")
        self.client = NativeClient()
        self.bridge = Bridge(self.paths, workspace["workspace_id"], "fixture", "x" * 40, "codex", self.client)
        self.client.cwd = str(self.bridge.cwd)
        self.bridge.select_thread("restored-thread")

    def body(self, **values):
        return {"text": "preserve this request", "expected_thread_id": self.bridge.thread_id,
                "settings_revision": self.bridge.settings.revision, "model": "model-b", "effort": "minimal", **values}

    def test_resume_settings_and_actual_turn_are_distinct_with_strict_reroute_identity(self):
        settings = self.bridge.state()["thread_settings"]
        self.assertEqual((settings["model"], settings["effort"], settings["source"]), ("model-b", "minimal", "native"))
        value = self.bridge.start_turn(self.body())
        self.assertEqual(value["turn_settings"]["confirmation"], "requested")
        self.bridge.on_event({"method": "model/rerouted", "params": {"threadId": "other", "turnId": "turn-1",
            "fromModel": "model-b", "toModel": "model-a", "reason": "fixture"}})
        self.assertEqual(self.bridge.state()["turn_settings"]["model"], "model-b")
        self.bridge.on_event({"method": "model/rerouted", "params": {"threadId": "restored-thread", "turnId": "turn-1",
            "fromModel": "model-b", "toModel": "model-a", "reason": "fixture"}})
        snapshot = self.bridge.state()["turn_settings"]
        self.assertEqual((snapshot["model"], snapshot["requested_model"], snapshot["confirmation"]),
                         ("model-a", "model-b", "rerouted"))
        self.assertEqual(self.bridge.state()["thread_settings"], settings)

    def test_stale_thread_or_settings_never_resume_owner_or_submit(self):
        self.bridge.owner_stopped = True
        for changes in ({"expected_thread_id": "old"}, {"settings_revision": -1}):
            with self.assertRaises(StudioError) as error:
                self.bridge.start_turn(self.body(**changes))
            self.assertEqual(error.exception.details["submission_state"], "not_submitted")
        self.assertTrue(self.bridge.owner_stopped)
        self.assertFalse(any(method == "turn/start" for method, _ in self.client.calls))

    def test_catalog_paging_uses_native_slug_and_rejects_hidden_missing_or_wrong_effort(self):
        self.client.pages = [{"data": [model("model-a"), model("hidden", hidden=True)], "nextCursor": "1"},
                             {"data": [model("model-b", "minimal", isDefault=True)], "nextCursor": None}]
        result = self.bridge.route("GET", "/models", {}, {})
        self.assertEqual([item["model"] for item in result["data"]], ["model-a", "model-b"])
        self.assertIsNone(result["nextCursor"])
        for values in ({"model": "display-id-model-b"}, {"model": "hidden"}, {"effort": "ultra"}):
            with self.assertRaises(StudioError):
                self.bridge.start_turn(self.body(**values))
        self.assertEqual(sum(method == "model/list" for method, _ in self.client.calls), 2)
        self.bridge.start_turn(self.body())
        submitted = next(params for method, params in self.client.calls if method == "turn/start")
        self.assertEqual((submitted["model"], submitted["effort"]), ("model-b", "minimal"))

    def test_account_change_during_catalog_fetch_does_not_publish_old_catalog(self):
        def changing(method, _params):
            if method == "model/list":
                self.bridge.on_event({"method": "account/updated", "params": {"authMode": "chatgpt"}})
        self.client.hook = changing
        with self.assertRaises(StudioError) as error:
            self.bridge.route("GET", "/models", {}, {})
        self.assertEqual(error.exception.code, "MODEL_CATALOG_CHANGED")
        self.assertIsNone(self.bridge.models.cached)

    def test_fast_tier_uses_catalog_id_and_null_clears_only_on_explicit_request(self):
        fast = model("model-b", "minimal", serviceTiers=[{"id": "priority", "name": "Fast"}])
        self.client.pages = [{"data": [fast, model("standard")], "nextCursor": None}]
        for changes in ({"service_tier": "ultrafast"}, {"service_tier": "fast"},
                        {"model": "standard", "effort": "high", "service_tier": "priority"}):
            with self.assertRaises(StudioError) as failure:
                self.bridge.start_turn(self.body(**changes))
            self.assertEqual(failure.exception.code, "FAST_MODE_UNAVAILABLE")
        for choice in ({}, {"service_tier": "priority"}, {"service_tier": None}):
            result = self.bridge.start_turn(self.body(**choice))
            _, request = self.client.calls[-1]
            self.assertEqual("serviceTier" in request, "service_tier" in choice)
            self.assertEqual(request.get("serviceTier"), choice.get("service_tier"))
            self.assertEqual((request["model"], request["effort"]), ("model-b", "minimal"))
            self.assertEqual(result["turn_settings"]["requested_service_tier"], choice.get("service_tier"))
            self.assertEqual(self.bridge.state()["thread_settings"]["service_tier"], choice.get("service_tier"))
            self.bridge.on_event({"method": "turn/completed", "params": {"threadId": self.bridge.thread_id,
                "turn": {"id": result["turn"]["id"], "status": "completed"}}})

    def test_native_tier_updates_are_bound_to_the_thread_and_fence_stale_sends(self):
        old = self.body()
        def updated(thread, tier):
            self.bridge.on_event({"method": "thread/settings/updated", "params": {
                "threadId": thread, "threadSettings": {"serviceTier": tier}}})
        updated("other", "priority")
        self.assertEqual(self.bridge.settings.revision, old["settings_revision"])
        updated(self.bridge.thread_id, "priority")
        self.assertEqual(self.bridge.state()["thread_settings"]["service_tier"], "priority")
        with self.assertRaises(StudioError) as failure:
            self.bridge.start_turn(old)
        self.assertEqual(failure.exception.code, "MODEL_SETTINGS_STALE")
        updated(self.bridge.thread_id, None)
        self.assertIsNone(self.bridge.state()["thread_settings"]["service_tier"])

    def test_missing_later_page_and_disappearing_selection_do_not_fall_back(self):
        self.client.pages = [{"data": [model("model-b", "minimal")], "nextCursor": "0"}]
        with self.assertRaises(StudioError):
            self.bridge.start_turn(self.body())
        self.client.pages = [{"data": [model("model-a")], "nextCursor": None}]
        self.bridge.models.invalidate()
        with self.assertRaises(StudioError) as error:
            self.bridge.start_turn(self.body())
        self.assertEqual(error.exception.code, "MODEL_UNAVAILABLE")
        self.assertFalse(any(method == "turn/start" for method, _ in self.client.calls))

    def test_reroute_before_reply_waits_for_matching_turn_and_unknown_start_keeps_snapshot(self):
        def during_start(method, _params):
            if method == "turn/start":
                self.bridge.on_event({"method": "model/rerouted", "params": {"threadId": "restored-thread",
                    "turnId": "old-turn", "fromModel": "model-b", "toModel": "wrong", "reason": "fixture"}})
                self.bridge.on_event({"method": "model/rerouted", "params": {"threadId": "restored-thread",
                    "turnId": "turn-1", "fromModel": "model-b", "toModel": "model-a", "reason": "fixture"}})
        self.client.hook = during_start
        result = self.bridge.start_turn(self.body())
        self.assertEqual(result["turn_settings"]["model"], "model-a")
        self.bridge.on_event({"method": "turn/completed", "params": {"threadId": "restored-thread",
            "turn": {"id": "turn-1", "status": "completed"}}})
        def lost(method, _params):
            if method == "turn/start":
                raise BridgeError("CODEX_REQUEST_TIMEOUT", "fixture response loss")
        self.client.hook = lost
        with self.assertRaises(BridgeError):
            self.bridge.start_turn(self.body())
        self.assertEqual(self.bridge.codex_state, "unknown")
        self.assertEqual(self.bridge.state()["turn_settings"]["requested_model"], "model-b")
        self.assertIsNone(self.bridge.state()["turn_settings"]["turn_id"])
