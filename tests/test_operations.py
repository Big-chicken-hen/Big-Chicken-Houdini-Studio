"""Focused protocol faults using fake HOM, never a Houdini GUI/AI end-to-end test."""
from __future__ import annotations

import base64
import contextlib
import io
import json
import sqlite3
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from studio.common import StudioError, encoded, new_id
from studio.http import MAX_BODY, Client, serve
from studio.ledger import Ledger
from studio.mcp import Adapter, serve_stdio, validate_schema
from studio.runtime import OperationRuntime
from studio.runtime_server import runtime_router
from studio.scene import ExecutionResult, HoudiniScene


TOKEN = "test-session-secret-0123456789abcdef"
TEST_ROOT = Path(__file__).resolve().parents[1] / ".runtime" / "operation-tests"


class FakeHou:
    def __init__(self):
        self.count = 0
        self.started, self.release = threading.Event(), threading.Event()
        self.hipFile = SimpleNamespace(path=lambda: "/same/scene.hip", hasUnsavedChanges=lambda: False,
                                       addEventCallback=lambda callback: None, removeEventCallback=lambda callback: None)
        self.hipFileEventType = SimpleNamespace(BeforeLoad="load", BeforeClear="clear")
        self.undos = SimpleNamespace(group=lambda label: contextlib.nullcontext())

    def applicationVersionString(self):
        return "fake-HOM"

    def frame(self):
        return 1

    def node(self, path):
        return None

    def mutate(self):
        self.count += 1

    def block(self):
        self.started.set()
        if not self.release.wait(3):
            raise RuntimeError("Test release was not signalled")


class GatedDispatch:
    def __init__(self):
        self.entered, self.release = threading.Event(), threading.Event()

    def __call__(self, callback):
        self.entered.set()
        if not self.release.wait(3):
            raise RuntimeError("Test dispatch was not released")
        return callback()


class FaultLedger(Ledger):
    fail = False
    persistent = False

    def update(self, operation_id, **changes):
        if self.fail and (changes.get("state") == "finished" or self.persistent):
            if not self.persistent:
                self.fail = False
            raise sqlite3.OperationalError("simulated storage failure")
        return super().update(operation_id, **changes)


class RouteClient:
    def __init__(self, runtime, lose_post=False):
        self.route = runtime_router(runtime)
        self.posts = []
        self.lose_post = lose_post

    def call(self, method, path, payload=None):
        from urllib.parse import parse_qs, urlsplit
        parts = urlsplit(path)
        value = self.route(method, parts.path, parse_qs(parts.query), payload or {})
        if method == "POST" and path == "/operations":
            self.posts.append(payload)
            if self.lose_post:
                raise StudioError("CONNECTION_LOST", "Response was lost", 503)
        return value


class OperationsTests(unittest.TestCase):
    def setUp(self):
        TEST_ROOT.mkdir(parents=True, exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(dir=TEST_ROOT)
        self.root = Path(self.directory.name)
        self.hou = FakeHou()
        self.scene = HoudiniScene(self.hou, self.root / "captures", secrets=(TOKEN,))
        self.runtime = None
        self.dispatch = None

    def tearDown(self):
        self.hou.release.set()
        if isinstance(self.dispatch, GatedDispatch):
            self.dispatch.release.set()
        if self.runtime is not None:
            self.runtime.close()
            self.assertFalse(self.runtime.worker.is_alive(), "Test worker must close SQLite before cleanup")
        self.scene.close()
        self.directory.cleanup()

    def start(self, capacity=16, gated=False, ledger_type=Ledger):
        self.dispatch = GatedDispatch() if gated else lambda callback: callback()
        ledger = ledger_type(self.root / "receipts.sqlite")
        self.runtime = OperationRuntime(ledger, self.scene, self.dispatch, workspace_id="workspace",
                                        session_id="session", capacity=capacity)
        return self.runtime

    def op(self, script="hou.mutate()", **changes):
        return {"operation_id": new_id(), "workspace_id": "workspace", "owner_id": "owner",
                "runtime_id": self.runtime.runtime_id, "scene_epoch": self.scene.epoch,
                "kind": "execute", "arguments": {"script": script}, **changes}

    def drain(self):
        deadline = time.monotonic() + 3
        while self.runtime.health()["queue_depth"] and time.monotonic() < deadline:
            time.sleep(0.005)
        self.assertEqual(self.runtime.health()["queue_depth"], 0)

    def run_op(self, script="hou.mutate()", **arguments):
        op = self.op(arguments={"script": script, **arguments}, label=arguments.get("label", "execute"))
        self.runtime.submit(op)
        self.drain()
        return self.runtime.get(op["operation_id"])

    def assert_code(self, code, call):
        with self.assertRaises(StudioError) as raised:
            call()
        self.assertEqual(raised.exception.code, code)

    def test_readiness_input_equals_distinguishes_missing_disconnected_connected(self):
        source = SimpleNamespace(path=lambda: "/obj/source")
        nodes = {"/obj/disconnected": SimpleNamespace(inputs=lambda: (None,)),
                 "/obj/connected": SimpleNamespace(inputs=lambda: (source,))}
        cases = [("/obj/missing", None, False), ("/obj/disconnected", None, True),
                 ("/obj/connected", "/obj/source", True)]
        with patch.object(self.hou, "node", side_effect=nodes.get):
            for path, expected, passed in cases:
                with self.subTest(path=path):
                    record = self.scene.checks([{"kind": "input_equals", "path": path, "expected": expected}])[0]
                    self.assertEqual(record["passed"], passed)
                    if not passed:
                        self.assertEqual(record["error_code"], "NODE_NOT_FOUND")
                    else:
                        self.assertEqual(record["actual"], expected)
            outcome = self.scene.execute({"script": "hou.mutate()", "preconditions": [
                {"kind": "input_equals", "path": "/obj/missing", "expected": None}]}, lambda: False)
        self.assertEqual((outcome.state, outcome.mutation_outcome), ("rejected", "not_run"))
        self.assertEqual(self.hou.count, 0)

    def test_readiness_tool_schema_declares_targeted_shapes(self):
        output = io.StringIO()
        serve_stdio(None, io.BytesIO(b'{"id":1,"method":"tools/list"}\n'), output)
        exported = {tool["name"]: tool["inputSchema"] for tool in json.loads(output.getvalue())["result"]["tools"]}
        execute = exported["hia_execute_hom"]
        shapes = {s["properties"]["kind"]["enum"][0]: s for s in execute["$defs"]["check"]["oneOf"]}
        self.assertEqual(set(shapes), {"node_exists", "node_type", "parm_equals", "input_equals", "cook", "geometry_nonempty"})
        self.assertEqual(set(shapes["parm_equals"]["required"]), {"kind", "path", "parm", "expected"})
        self.assertEqual(set(shapes["input_equals"]["required"]), {"kind", "path", "expected"})
        checks = [{"kind": "node_exists", "path": "/obj"},
                  {"kind": "node_type", "path": "/obj/geo", "expected": "geo"},
                  {"kind": "parm_equals", "path": "/obj/geo", "parm": "tx", "expected": 2},
                  {"kind": "input_equals", "path": "/obj/geo", "expected": None},
                  {"kind": "cook", "path": "/obj/geo/out"},
                  {"kind": "geometry_nonempty", "path": "/obj/geo/out"}]
        views = [{"path": "/obj"}, {"view": "parms", "path": "/obj/geo", "names": ["tx"]},
                 {"view": "children", "limit": 20}, {"view": "geometry", "path": "/obj/geo/out"},
                 {"view": "checks", "checks": checks}]
        validate_schema({"script": "pass", "checks": checks, "preconditions": checks, "observe": views}, execute)
        validate_schema({"views": views}, exported["hia_inspect"])
        self.assertIn("BEFORE and AFTER", execute["properties"]["observe"]["description"])
        adapter = Adapter(None, None, {}, "owner", runtime_loader=lambda: self.fail("Invalid schema reached runtime"))
        bad = [{"checks": [{"kind": "parm_equals", "path": "/obj", "expected": 1}]},
               {"checks": [{"kind": "input_equals", "path": "/obj"}]},
               {"preconditions": [{"kind": "node_exists", "expected": True}]},
               {"observe": [{"view": "parms", "names": []}]},
               {"checks": [{"kind": "node_exists", "path": "/obj", "expected": "yes"}]}]
        for arguments in bad:
            with self.subTest(arguments=arguments):
                self.assert_code("INVALID_TOOL_CALL", lambda: adapter.call("hia_execute_hom", {"script": "pass", **arguments}))
        self.assert_code("INVALID_TOOL_CALL", lambda: adapter.call("hia_inspect", {"views": []}))

    def test_readiness_script_diagnostics_preserve_location_without_sensitive_context(self):
        self.start()
        receipt = self.run_op("hou.mutate()\nif True print('broken')")
        self.assertEqual((receipt["state"], receipt["mutation_outcome"]), ("rejected", "not_run"))
        self.assertEqual(receipt["error"]["code"], "COMPILE_FAILED")
        self.assertEqual(receipt["error"]["exception_type"], "SyntaxError")
        self.assertEqual(receipt["error"]["script_line"], 2)
        self.assertGreater(receipt["error"]["script_column"], 0)
        self.assertNotIn("print('broken')", encoded(receipt["error"]))
        self.assertEqual(self.hou.count, 0)
        receipt = self.run_op("def build():\n hou.mutate()\n return missing_node_type\nbuild()")
        self.assertEqual(receipt["mutation_outcome"], "partial")
        self.assertEqual(receipt["error"]["exception_type"], "NameError")
        self.assertEqual(receipt["error"]["script_line"], 3)
        self.assertIn("missing_node_type", receipt["error"]["message"])
        sensitive_path = str(self.root / "private file.png")
        receipt = self.run_op(f"raise FileNotFoundError(2, 'Cannot open cache', {sensitive_path!r})")
        self.assertNotIn(sensitive_path, encoded(receipt["error"]))
        self.assertNotIn(str(self.root), receipt["error"]["message"])
        self.assertIn("Cannot open cache", receipt["error"]["message"])
        reason = f"Cannot use {TOKEN}; /private/user/cache.exr; TOKEN=unrelated-secret " + "x" * 2000
        receipt = self.run_op(f"raise RuntimeError({reason!r})")
        self.assertLessEqual(len(receipt["error"]["message"]), 1200)
        for private in (TOKEN, "/private/user/cache.exr", "unrelated-secret"):
            self.assertNotIn(private, encoded(receipt["error"]))
        receipt = self.run_op("raise RuntimeError(\"environ({'PATH': '/private/bin'})\")")
        self.assertEqual(receipt["error"]["message"], "Environment details omitted from exception message")

    def test_readiness_observe_reads_both_sides_and_requires_existing_targets(self):
        with patch.object(self.scene, "inspect", side_effect=lambda view: {"count": self.hou.count}):
            outcome = self.scene.execute({"script": "hou.mutate()", "observe": [{"path": "/obj/existing"}]}, lambda: False)
        self.assertEqual(outcome.detail["observations"], {"before": [{"count": 0}], "after": [{"count": 1}]})
        outcome = self.scene.execute({"script": "hou.mutate()", "observe": [{"path": "/obj/not_created_yet"}]}, lambda: False)
        self.assertEqual(outcome.mutation_outcome, "not_run")
        self.assertEqual(outcome.error["code"], "NODE_NOT_FOUND")
        self.assertEqual(self.hou.count, 1)

    def test_readiness_capture_changes_only_stashed_settings_and_restores_frame(self):
        from test_capture import png_bytes

        class Settings:
            def __init__(self, values):
                self.values = dict(values)

            def stash(self):
                return Settings(self.values)

            def __getattr__(self, name):
                return lambda value: self.values.__setitem__(name, value)

        expensive = {"initializeSimulations": True, "useMotionBlur": True,
                     "scopeChannelKeyframesOnly": True, "renderAllViewports": True}
        original = Settings(expensive)
        used, current_frame = [], [7]
        def flipbook(viewport, settings, open_dialog):
            used.append(settings.values)
            self.assertFalse(open_dialog)
            self.assertIs(viewport, active_viewport)
            for option in expensive:
                self.assertIs(settings.values[option], False)
            if len(used) == 2:
                raise RuntimeError("simulated viewport failure")
            Path(settings.values["output"]).write_bytes(png_bytes(*settings.values["resolution"]))
        active_viewport = SimpleNamespace(size=lambda: (0, 0, 320, 180))
        viewer = SimpleNamespace(flipbookSettings=lambda: original, curViewport=lambda: active_viewport, flipbook=flipbook)
        with patch.multiple(self.hou, create=True, frame=lambda: current_frame[0],
                            setFrame=lambda value: current_frame.__setitem__(0, value),
                            ui=SimpleNamespace(paneTabOfType=lambda kind: viewer),
                            paneTabType=SimpleNamespace(SceneViewer="SceneViewer")):
            result = self.scene.capture({"frame": 24})
            self.assertEqual(result.state, "finished")
            self.assertEqual(result.detail["actual_resolution"], [320, 180])
            self.assertEqual(result.detail["restored_frame"], 7)
            self.assertEqual(current_frame[0], 7)
            self.assertEqual(original.values, expensive)
            failed = self.scene.capture({"frame": 30})
            self.assertEqual(failed.state, "failed")
            self.assertIn("simulated viewport failure", failed.detail["capture_error"]["message"])
            self.assertEqual(failed.detail["restore_errors"], [])
            self.assertEqual(current_frame[0], 7)
        self.assertEqual(original.values, expensive)

    def test_stale_after_queue_same_path_reload_and_cancel_capacity(self):
        runtime = self.start(capacity=2, gated=True)
        stale = self.op()
        runtime.submit(stale)
        self.assertTrue(self.dispatch.entered.wait(1))
        cancelled = self.op()
        runtime.submit(cancelled)
        runtime.cancel(cancelled["operation_id"])
        self.assertEqual(runtime.health()["queue_depth"], 2)
        self.assertEqual(runtime.queue.maxsize, 2)
        self.assert_code("QUEUE_FULL", lambda: runtime.submit(self.op()))
        old_path, old_epoch = self.scene.cached()["hip_path"], self.scene.epoch
        self.scene._hip_event("load", old_hip_file=old_path, new_hip_file=old_path)
        self.assertNotEqual(old_epoch, self.scene.epoch)
        self.assertEqual(old_path, self.scene.cached()["hip_path"])
        self.dispatch.release.set()
        self.drain()
        self.assertEqual(runtime.get(stale["operation_id"])["error"]["code"], "STALE_SCENE")
        self.assertEqual(runtime.get(cancelled["operation_id"])["mutation_outcome"], "not_run")
        self.assertEqual(self.hou.count, 0)

    def test_lost_response_queries_same_id_and_conflicting_payload_never_runs(self):
        runtime = self.start()
        client = RouteClient(runtime, lose_post=True)
        adapter = Adapter(client, None, {"runtime_id": runtime.runtime_id, "workspace_id": "workspace"}, "owner")
        adapter.scene_epoch = self.scene.epoch
        response = adapter.call("hia_execute_hom", {"script": "hou.mutate(); result = 42"})
        receipt = json.loads(response["content"][0]["text"])
        self.assertEqual(receipt["state"], "finished")
        self.assertEqual(len(client.posts), 1)
        op = client.posts[0]
        self.assertEqual(runtime.submit(op)["operation_id"], receipt["operation_id"])
        changed = {**op, "arguments": {"script": "hou.mutate(); result = 43"}}
        self.assert_code("OPERATION_ID_CONFLICT", lambda: runtime.submit(changed))
        self.assertEqual(self.hou.count, 1)
        # Even an unaccepted/lost submission returns its preallocated ID, never a second POST.
        class LostClient:
            calls = []
            def call(self, method, path, payload=None):
                self.calls.append((method, path))
                raise StudioError("CONNECTION_LOST", "Lost", 503)
        lost = LostClient()
        adapter.runtime = lost
        response = adapter.call("hia_execute_hom", {"script": "hou.mutate()"})
        unknown = json.loads(response["content"][0]["text"])
        self.assertEqual(unknown["state"], "unknown")
        self.assertEqual(lost.calls, [("POST", "/operations"), ("GET", "/operations/" + unknown["operation_id"])])
        class PollFailure:
            def call(self, method, path, payload=None):
                if method == "POST":
                    return {"operation_id": payload["operation_id"], "state": "queued", "mutation_outcome": "not_run"}
                raise StudioError("RECEIPT_UNAVAILABLE", "Receipt commit was not confirmed", 503)
        adapter.runtime = PollFailure()
        response = adapter.call("hia_execute_hom", {"script": "hou.mutate()"})
        unknown = json.loads(response["content"][0]["text"])
        self.assertEqual(unknown["state"], "unknown")
        self.assertEqual(unknown["mutation_outcome"], "unknown")
        self.assertEqual(unknown["last_confirmed_state"], "queued")
        self.assertFalse(unknown["receipt_confirmed"])

    def test_stop_fences_queued_work_but_running_hom_remains_running(self):
        runtime = self.start()
        running = self.op("hou.mutate(); hou.block()")
        runtime.submit(running)
        self.assertTrue(self.hou.started.wait(1))
        queued = self.op()
        runtime.submit(queued)
        stopped = runtime.stop_owner("owner")
        self.assertTrue(stopped["future_operations_stopped"])
        self.assertEqual(runtime.get(running["operation_id"])["state"], "running")
        self.assertTrue(runtime.get(running["operation_id"])["cancel_requested"])
        self.assertTrue(runtime.health()["main_thread_busy"])
        self.assertEqual(runtime.get(queued["operation_id"])["state"], "cancelled")
        self.assert_code("OWNER_STOPPED", lambda: runtime.submit(self.op()))
        self.hou.release.set()
        self.drain()
        self.assertEqual(runtime.get(running["operation_id"])["mutation_outcome"], "completed")
        self.assertEqual(self.hou.count, 1)

    def test_post_execution_failures_do_not_reclassify_mutation(self):
        self.start()
        with patch.object(self.scene, "checks", side_effect=[[], RuntimeError("postcheck failure")]):
            receipt = self.run_op(checks=[{"kind": "node_exists", "path": "/obj/test"}])
        self.assertEqual((receipt["mutation_outcome"], receipt["checks_outcome"]), ("completed", "failed"))
        with patch.object(self.scene, "inspect", side_effect=[{"path": "/obj/test"}, StudioError("INVALID_ARGUMENTS", "after read")]):
            receipt = self.run_op(observe=[{"path": "/obj/test"}])
        self.assertEqual(receipt["mutation_outcome"], "completed")
        self.assertIn("observation_error", receipt["result"])
        receipt = self.run_op("hou.mutate()\nclass Broken:\n def __repr__(self): raise ValueError('cannot render')\nresult = Broken()")
        self.assertEqual(receipt["mutation_outcome"], "completed")
        self.assertIn("result_error", receipt["result"])
        with patch.object(self.scene, "run", return_value=ExecutionResult(detail={"bad": object()}, mutation_outcome="completed")), \
                patch.object(self.scene, "refresh_cached", side_effect=RuntimeError("cache unavailable")):
            receipt = self.run_op()
        self.assertEqual(receipt["mutation_outcome"], "completed")
        self.assertEqual(receipt["result"]["result_error"]["code"], "RESULT_SERIALIZATION_FAILED")

    def test_bad_check_and_observe_arguments_reject_before_admission(self):
        runtime = self.start()
        invalid = [{"checks": [{"kind": "input_equals", "path": "/obj", "expected": None, "index": "bad"}]},
                   {"checks": [{"kind": "parm_equals", "path": "/obj", "parm": "tx", "tolerance": -1}]},
                   {"observe": [{"view": "children", "path": "/obj", "limit": "bad"}]},
                   {"checks": [{"kind": "node_exists", "path": None}]}]
        for args in invalid:
            with self.subTest(args=args):
                self.assert_code("INVALID_ARGUMENTS", lambda: runtime.submit(self.op(arguments={"script": "hou.mutate()", **args})))
        self.assertEqual(runtime.recent(), [])
        self.assertEqual(self.hou.count, 0)

    def test_external_file_effect_then_exception_never_claims_safe_retry(self):
        self.start()
        target = self.root / "external-effect.txt"
        script = ("from pathlib import Path\nfrom studio.common import StudioError\n"
                  f"Path({str(target)!r}).write_text('effect', encoding='utf-8')\n"
                  "hou.mutate()\nraise StudioError('INVALID_ARGUMENTS', 'raised inside the script')")
        receipt = self.run_op(script)
        self.assertEqual(target.read_text(), "effect")
        self.assertEqual(receipt["mutation_outcome"], "partial")
        self.assertEqual(receipt["external_side_effects"], "unknown")
        self.assertFalse(receipt["automatic_retry_safe"])

    def test_commit_failure_records_unknown_and_stops_next_hom(self):
        runtime = self.start(gated=True, ledger_type=FaultLedger)
        first, second = self.op(), self.op()
        runtime.submit(first)
        runtime.submit(second)
        runtime.ledger.fail = True
        self.dispatch.release.set()
        self.drain()
        self.assertEqual(runtime.get(first["operation_id"])["state"], "unknown")
        self.assertEqual(runtime.get(first["operation_id"])["mutation_outcome"], "unknown")
        self.assertEqual(runtime.get(second["operation_id"])["mutation_outcome"], "not_run")
        self.assertTrue(runtime.health()["storage_fault"])
        self.assert_code("RUNTIME_UNAVAILABLE", lambda: runtime.submit(self.op()))
        self.assertEqual(self.hou.count, 1)

    def test_total_storage_failure_never_exposes_stale_running_as_confirmed(self):
        runtime = self.start(ledger_type=FaultLedger)
        op = self.op("hou.mutate(); hou.block()")
        runtime.submit(op)
        self.assertTrue(self.hou.started.wait(1))
        runtime.ledger.fail = runtime.ledger.persistent = True
        self.hou.release.set()
        self.drain()
        self.assert_code("RECEIPT_UNAVAILABLE", lambda: runtime.get(op["operation_id"]))
        projected = runtime.recent()[0]
        self.assertEqual(projected["state"], "unknown")
        self.assertFalse(projected["receipt_confirmed"])
        self.assertEqual(self.hou.count, 1)

    def test_crash_recovery_never_replays_running_or_queued_operations(self):
        ledger = Ledger(self.root / "receipts.sqlite")
        base = {"workspace_id": "workspace", "runtime_id": "previous", "owner_id": "owner",
                "scene_epoch": "previous_scene", "kind": "execute", "arguments": {"script": "hou.mutate()"}}
        running, queued = {**base, "operation_id": "running"}, {**base, "operation_id": "queued"}
        ledger.accept(running)
        ledger.accept(queued)
        ledger.update("running", state="running")
        ledger.close()
        runtime = self.start()
        self.assertEqual(runtime.get("running")["state"], "unknown")
        self.assertEqual(runtime.get("queued")["mutation_outcome"], "not_run")
        self.assertEqual(runtime.submit(running)["state"], "unknown")
        self.assertEqual(self.hou.count, 0)

    def test_large_success_details_are_paged_and_outputs_redacted_before_truncation(self):
        runtime = self.start()
        stdout, stderr = io.StringIO(), io.StringIO()
        script = f"import sys\nprint({TOKEN!r})\nprint({TOKEN!r}, file=sys.stderr)\nhou.mutate()\nresult = {{'large': 'x' * 100000, {TOKEN!r}: {TOKEN!r}}}"
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            receipt = self.run_op(script, label="x" * 150 + TOKEN)
        self.assertEqual(receipt["state"], "finished")
        self.assertTrue(receipt["result"]["detail_available"])
        offset, pages = 0, []
        while offset is not None:
            page = runtime.ledger.detail(receipt["operation_id"], offset, 24000)
            pages.append(page["text"])
            offset = page["next_offset"]
        detail = "".join(pages)
        self.assertEqual(len(json.loads(detail)["value"]["large"]), 100000)
        self.assertNotIn(TOKEN, detail + encoded(receipt) + stdout.getvalue() + stderr.getvalue())
        self.assertNotIn(TOKEN[:10], encoded(receipt))
        failed = self.run_op(f"raise RuntimeError({TOKEN!r})")
        self.assertNotIn(TOKEN, encoded(failed))

    def test_native_image_and_non_scene_tools_do_not_reexecute_hom(self):
        runtime = self.start(gated=True)
        bridge_calls = []
        bridge = SimpleNamespace(call=lambda *args: bridge_calls.append(args) or {"ok": True})
        adapter = Adapter(None, bridge, {}, "owner", runtime_loader=lambda: self.fail("Bridge-only tool loaded runtime"))
        adapter.call("hia_project_memory", {"action": "list"})
        adapter.call("hia_lookup", {"source": "documents", "query": "noise"})
        self.assertEqual(len(bridge_calls), 2)
        adapter.runtime, adapter.identity = RouteClient(runtime), {"runtime_id": runtime.runtime_id, "workspace_id": "workspace"}
        with patch.object(self.scene, "lookup", return_value={"documentation": "pure docstring"}):
            adapter.call("hia_lookup", {"source": "hom", "symbol": "hou.Node"})
        self.assertFalse(self.dispatch.entered.is_set())
        from test_capture import png_bytes
        png = png_bytes()
        artifact_id, image_path = self.scene._artifacts.allocate()
        image_path.write_bytes(png)
        self.scene._artifacts.commit(artifact_id, {"actual_frame": 1}, (64, 64))
        content = adapter._receipt({"kind": "capture", "state": "finished", "result": {"artifact_id": artifact_id}})["content"]
        self.assertEqual(content[1], {"type": "image", "mimeType": "image/png", "data": base64.b64encode(png).decode()})
        self.assertEqual(self.hou.count, 0)

    def test_context_binding_accepts_only_own_context_and_survives_missing_result(self):
        class ContextClient:
            def __init__(self):
                self.receipts = {}
                self.result = {"scene_epoch": "own-scene"}
                self.lose_response = True

            def call(self, method, path, payload=None):
                if method == "POST":
                    op_id = payload["operation_id"]
                    self.receipts[op_id] = {**payload, "state": "finished", "result": self.result}
                    if self.lose_response:
                        raise StudioError("CONNECTION_LOST", "Lost context response", 503)
                    return self.receipts[op_id]
                return self.receipts[path.rsplit("/", 1)[-1]]

        client = ContextClient()
        adapter = Adapter(client, None, {"runtime_id": "runtime", "workspace_id": "workspace"}, "session")
        adapter.scene_epoch = "prior-scene"
        foreign = {"operation_id": "panel-context", "kind": "context", "state": "finished",
                   "owner_id": "session", "runtime_id": "runtime", "result": {"scene_epoch": "panel-scene"}}
        client.receipts["panel-context"] = foreign
        adapter.call("hia_operation", {"action": "get", "operation_id": "panel-context"})
        self.assertEqual(adapter.scene_epoch, "prior-scene")
        adapter._receipt({key: value for key, value in foreign.items() if key != "operation_id"})
        self.assertEqual(adapter.scene_epoch, "prior-scene")
        adapter.call("hia_context", {})  # Lost POST recovers through a GET of its own ID.
        self.assertEqual(adapter.scene_epoch, "own-scene")
        own_id = adapter.context_operation_id
        for missing in ({}, None, {"scene_epoch": None}, {"scene_epoch": ""}):
            with self.subTest(result=missing):
                client.receipts[own_id]["result"] = missing
                adapter.call("hia_operation", {"action": "get", "operation_id": own_id})
                self.assertEqual(adapter.scene_epoch, "own-scene")
        client.receipts[own_id]["result"] = {"scene_epoch": "recovered-scene"}
        adapter.call("hia_operation", {"action": "get", "operation_id": own_id})
        self.assertEqual(adapter.scene_epoch, "recovered-scene")
        adapter.call("hia_operation", {"action": "get", "operation_id": "panel-context"})
        self.assertEqual(adapter.scene_epoch, "recovered-scene")
        client.result = {"scene_epoch": "latest-scene"}
        adapter.call("hia_context", {})
        adapter.call("hia_operation", {"action": "get", "operation_id": own_id})
        self.assertEqual(adapter.scene_epoch, "latest-scene")

    def test_stdio_bounded_lines_and_http_partial_response_are_uncertain(self):
        class BoundedSource(io.BytesIO):
            def readline(self, size=-1):
                self_size = size
                if not 0 < self_size <= MAX_BODY + 1:
                    raise AssertionError("Unbounded readline")
                return super().readline(size)
        source = BoundedSource(b"x" * (MAX_BODY + 50) + b'\n{"id":1,"method":"ping"}\n')
        output = io.StringIO()
        serve_stdio(None, source, output, TOKEN)
        messages = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(messages[0]["error"]["code"], -32600)
        self.assertEqual(messages[1]["result"], {})
        import http.client
        client = Client("http://127.0.0.1:12345", TOKEN)
        response = SimpleNamespace(read=lambda size: (_ for _ in ()).throw(http.client.IncompleteRead(b"partial", 20)))
        with patch.object(client.opener, "open", return_value=contextlib.nullcontext(response)):
            self.assert_code("CONNECTION_LOST", lambda: client.call("POST", "/operations", {}))

    def test_real_loopback_receipt_query_and_error_redaction(self):
        runtime = self.start()
        route = runtime_router(runtime)
        def router(method, path, query, body):
            if path == "/fault":
                raise StudioError("FAULT", TOKEN)
            return route(method, path, query, body)
        server = serve(router, TOKEN)
        try:
            client = Client("http://127.0.0.1:" + str(server.server_port), TOKEN)
            op = self.op()
            client.call("POST", "/operations", op)
            self.drain()
            receipt = client.call("GET", "/operations/" + op["operation_id"])
            self.assertEqual(receipt["mutation_outcome"], "completed")
            with self.assertRaises(StudioError) as fault:
                client.call("GET", "/fault")
            self.assertNotIn(TOKEN, str(fault.exception))
            self.assertEqual(self.hou.count, 1)
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
