"""Step gates/receipt durability with controlled HOM, not real GUI evidence."""
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
from types import SimpleNamespace as NS
import unittest

from studio.common import StudioError, encoded, new_id
from studio.ledger import Ledger
from studio.mcp import Adapter, TOOLS, serve_stdio
from studio.runtime import OperationRuntime
from studio.scene import HoudiniScene, validate_arguments
from studio.staged import initial_detail
from studio.tool_schema import validate_schema
from test_operations import FakeHou, RouteClient


class TraceLedger(Ledger):
    def __init__(self, path):
        super().__init__(path)
        self.trace, self.fail_step = [], None

    def update(self, operation_id, **changes):
        detail = changes.get("detail", {})
        steps = detail.get("steps", [])
        if self.fail_step is not None and any(s["id"] == self.fail_step and s["state"] == "finished" for s in steps):
            self.fail_step = None
            raise sqlite3.OperationalError("Controlled step result commit failure")
        result = super().update(operation_id, **changes)
        self.trace.append(("persist", [(s["id"], s["state"]) for s in steps]))
        return result


class StagedTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1] / ".runtime" / "tc3-tests"
        root.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=root)
        self.hou, self.frame, self.take = FakeHou(), 1.0, "Main"
        self.hou.frame = lambda: self.frame
        self.hou.setFrame = lambda f: setattr(self, "frame", f)
        self.hou.takes = NS(currentTake=lambda: NS(name=lambda: self.take, parent=lambda: None))
        self.scene = HoudiniScene(self.hou, Path(self.temp.name) / "artifacts", secrets=("fixture-private-value",))
        self.ledger = TraceLedger(Path(self.temp.name) / "operations.sqlite")
        self.callbacks, self.after_callback = 0, lambda index: None
        def dispatch(callback):
            self.callbacks += 1
            result = callback()
            self.after_callback(self.callbacks)
            return result
        self.runtime = OperationRuntime(self.ledger, self.scene, dispatch, workspace_id="workspace", session_id="session")
        self.hou.record = lambda value: self.ledger.trace.append(("script", value))
        self.hou.stop = lambda: self.runtime.stop_owner("owner")

    def tearDown(self):
        self.hou.release.set()
        self.runtime.close()
        self.assertFalse(self.runtime.worker.is_alive())
        self.scene.close()
        self.temp.cleanup()

    def args(self, scripts, **extra):
        return {"steps": [{"id": "s" + str(i), "label": "Stage " + str(i), "script": script}
                          for i, script in enumerate(scripts)], **extra}

    def submit(self, args):
        op = {"operation_id": new_id(), "owner_id": "owner", "workspace_id": "workspace",
              "runtime_id": self.runtime.runtime_id, "scene_epoch": self.scene.epoch, "kind": "execute", "arguments": args}
        self.runtime.submit(op)
        return op

    def drain(self, op):
        deadline = time.monotonic() + 5
        while self.runtime.health()["queue_depth"] and time.monotonic() < deadline:
            time.sleep(0.005)
        self.assertEqual(self.runtime.health()["queue_depth"], 0)
        return self.runtime.get(op["operation_id"])

    def test_stdio_contract_and_full_handoff_uses_independent_namespaces(self):
        args = self.args(["local_only=5; inputs['x']=99; result='fixture-private-value'",
            "assert 'local_only' not in globals(); assert inputs['x']==3; assert results['s0']=='fixture-private-value'; result={'actual':True}"], inputs={"x": 3})
        adapter = Adapter(RouteClient(self.runtime), None, {"runtime_id": self.runtime.runtime_id, "workspace_id": "workspace"}, "owner")
        messages = [{"id": 1, "method": "tools/call", "params": {"name": "hia_context", "arguments": {}}},
                    {"id": 2, "method": "tools/call", "params": {"name": "hia_execute_hom", "arguments": args}}]
        output = io.StringIO()
        serve_stdio(adapter, io.BytesIO(("\n".join(encoded(v) for v in messages) + "\n").encode()), output)
        receipt = json.loads(json.loads(output.getvalue().splitlines()[-1])["result"]["content"][0]["text"])
        self.assertEqual(receipt["state"], "finished")
        self.assertEqual(receipt["completed_steps"], ["s0", "s1"])
        self.assertEqual(receipt["steps"][0]["value"], "[REDACTED]")
        self.assertEqual(receipt["steps"][1]["value"], {"actual": True})
        self.assertEqual(receipt["checks_outcome"], "not_run")
        self.assertEqual(self.callbacks, 3)  # context plus two separate callbacks

    def test_all_compile_before_first_mutation_and_shape_limits(self):
        outcome = self.drain(self.submit(self.args(["hou.mutate()", "broken ! syntax"])))
        self.assertEqual((self.hou.count, self.callbacks), (0, 0))
        self.assertEqual(outcome["stop_reason"], "COMPILE_FAILED")
        self.assertEqual(outcome["steps"][1]["error"]["script_line"], 1)
        schema = next(t["inputSchema"] for t in TOOLS if t["name"] == "hia_execute_hom")
        malformed = [self.args(["pass", "pass"], script="pass"), self.args(["pass"]),
                     self.args(["pass", "pass"], checks=[])]
        for args in malformed:
            with self.assertRaises(StudioError):
                validate_arguments("execute", args)
            with self.assertRaises(StudioError):
                validate_schema(args, schema)
        args = self.args(["pass", "pass"])
        args["steps"][1]["id"] = "s0"
        with self.assertRaises(StudioError):
            self.runtime.submit({"operation_id": new_id(), "owner_id": "owner", "workspace_id": "workspace",
                "runtime_id": self.runtime.runtime_id, "scene_epoch": self.scene.epoch, "kind": "execute", "arguments": args})

    def test_declared_check_or_observation_failure_stops_following_step(self):
        for gate in ({"checks": [{"kind": "node_exists", "path": "/obj/missing"}]},
                     {"observe_after": [{"path": "/obj/missing"}]},
                     {"observe": [{"path": "/obj/missing"}]}):
            self.hou.count = 0
            args = self.args(["hou.mutate()", "hou.mutate()"])
            args["steps"][0].update(gate)
            outcome = self.drain(self.submit(args))
            self.assertEqual(self.hou.count, 0 if "observe" in gate else 1)
            self.assertEqual(outcome["steps"][1]["state"], "not_run")
            self.assertNotEqual(outcome["state"], "finished")
            self.assertEqual(outcome["checks_outcome"], "failed" if "checks" in gate else "not_run")

    def test_each_begin_and_result_commit_precedes_next_execution(self):
        outcome = self.drain(self.submit(self.args(["hou.record('one')", "hou.record('two')"])))
        self.assertEqual(outcome["state"], "finished")
        trace = self.ledger.trace
        first = trace.index(("script", "one"))
        second = trace.index(("script", "two"))
        self.assertIn(("s0", "running"), trace[first - 1][1])
        self.assertTrue(any(("s0", "finished") in t[1] for t in trace[first + 1:second] if t[0] == "persist"))
        self.assertIn(("s1", "running"), trace[second - 1][1])

    def test_partial_retains_prior_work_and_new_correction_does_not_replay(self):
        args = self.args(["hou.mutate(); result={'node':'retained'}", "hou.mutate()",
                          "hou.mutate(); raise RuntimeError('third fails')", "hou.mutate()"])
        op = self.submit(args)
        receipt = self.drain(op)
        self.assertEqual(receipt["completed_steps"], ["s0", "s1"])
        self.assertEqual((receipt["state"], receipt["mutation_outcome"]), ("failed", "partial"))
        self.assertEqual(receipt["steps"][2]["mutation_outcome"], "partial")
        self.assertEqual(receipt["steps"][3]["state"], "not_run")
        self.runtime.submit(op)
        self.assertEqual(self.hou.count, 3)
        correction = self.submit({"script": "result={'retained':hou.count==3}"})
        self.assertTrue(self.drain(correction)["result"]["value"]["retained"])
        self.assertEqual(self.hou.count, 3)

    def test_strict_json_and_total_handoff_budget(self):
        self.hou.bad = type("NotJson", (), {"__repr__": lambda _: self.fail("Must not stringify a live object")})()
        for expression in ("hou.bad", "float('nan')", "'x'*16385"):
            self.hou.count = 0
            receipt = self.drain(self.submit(self.args(["hou.mutate(); result=" + expression, "hou.mutate()"])))
            self.assertEqual(self.hou.count, 1)
            self.assertEqual(receipt["steps"][0]["value_status"], "invalid")
            self.assertEqual(receipt["steps"][1]["state"], "not_run")
        self.hou.count = 0
        receipt = self.drain(self.submit(self.args(["hou.mutate(); result='x'*15000"] * 6)))
        self.assertEqual(self.hou.count, 5)
        self.assertEqual(receipt["stop_reason"], "STEP_VALUE_LIMIT")
        self.assertEqual(receipt["steps"][5]["state"], "not_run")
        self.assertTrue(receipt["steps"][0]["value_summary_omitted"])

    def test_context_change_between_callbacks_stops_without_restoring_artist_state(self):
        for edit, reason in ((lambda: setattr(self, "frame", 24), "STEP_CONTEXT_CHANGED"),
                             (lambda: setattr(self, "take", "Artist"), "STEP_CONTEXT_CHANGED"),
                             (lambda: setattr(self.scene, "epoch", new_id()), "STALE_SCENE")):
            self.callbacks, self.hou.count = 0, 0
            self.after_callback = lambda i: edit() if i == 1 else None
            receipt = self.drain(self.submit(self.args(["hou.mutate()", "hou.mutate()"])))
            self.assertEqual(self.hou.count, 1)
            self.assertEqual(receipt["stop_reason"], reason)
        self.after_callback = lambda _: None
        receipt = self.drain(self.submit(self.args(["hou.setFrame(72)", "assert hou.frame()==72"])))
        self.assertEqual(receipt["state"], "finished")
        self.assertEqual(self.frame, 72)
        self.assertEqual(self.runtime.health()["scene"]["frame"], 72)

    def test_cancel_between_steps_and_at_last_step_preserves_completed_mutations(self):
        for stop_at in (1, 2):
            self.runtime.resume_owner("owner")
            self.callbacks, self.hou.count = 0, 0
            self.after_callback = lambda i: self.runtime.stop_owner("owner") if i == stop_at else None
            receipt = self.drain(self.submit(self.args(["hou.mutate()", "hou.mutate()"])))
            self.assertEqual(receipt["state"], "cancelled")
            self.assertEqual(self.hou.count, stop_at)
            self.assertEqual(receipt["mutation_outcome"], "partial" if stop_at == 1 else "completed")

    def test_queued_cancel_and_in_step_stop_do_not_start_later_work(self):
        entered, release = threading.Event(), threading.Event()
        def delayed(callback):
            entered.set()
            if not release.wait(2):
                raise RuntimeError("Test dispatch not released")
            return callback()
        self.runtime.dispatch = delayed
        op = self.submit(self.args(["hou.mutate()", "hou.mutate()"] ))
        self.assertTrue(entered.wait(1))
        try:
            receipt = self.runtime.cancel(op["operation_id"])
            self.assertEqual(receipt["stop_reason"], "CANCEL_REQUESTED")
        finally:
            release.set()
        self.assertEqual(self.drain(op)["mutation_outcome"], "not_run")
        self.assertEqual(self.hou.count, 0)
        self.runtime.dispatch = lambda callback: callback()
        receipt = self.drain(self.submit(self.args(["hou.mutate(); hou.stop(); checkpoint()", "hou.mutate()"])))
        self.assertEqual((receipt["state"], self.hou.count), ("cancelled", 1))
        self.assertEqual(receipt["steps"][0]["state"], "cancelled")
        self.assertEqual(receipt["steps"][1]["state"], "not_run")

    def test_step_preconditions_and_total_request_budgets(self):
        args = self.args(["hou.mutate()", "hou.mutate()"])
        args["steps"][1]["preconditions"] = [{"kind": "node_exists", "path": "/obj/current_target"}]
        receipt = self.drain(self.submit(args))
        self.assertEqual(self.hou.count, 1)
        self.assertEqual(receipt["steps"][1]["failure_phase"], "preconditions")
        for args in (self.args(["#" + "x" * 128000] * 2),
                     self.args(["pass", "pass"], inputs={"x": "x" * 65536})):
            with self.assertRaises(StudioError):
                validate_arguments("execute", args)
        args = self.args(["pass", "pass"])
        args["steps"][0].update(observe=[{"path": "/obj"}] * 5, observe_after=[{"path": "/obj"}] * 4)
        with self.assertRaises(StudioError):
            validate_arguments("execute", args)

    def test_result_commit_failure_preserves_previous_step_and_stops(self):
        self.ledger.fail_step = "s1"
        receipt = self.drain(self.submit(self.args(["hou.mutate()", "hou.mutate()", "hou.mutate()"])))
        self.assertEqual(self.hou.count, 2)
        self.assertEqual(receipt["state"], "unknown")
        self.assertEqual(receipt["steps"][0]["state"], "finished")
        self.assertEqual(receipt["steps"][1]["state"], "unknown")
        self.assertEqual(receipt["steps"][2]["state"], "not_run")
        self.assertIsNotNone(self.runtime.storage_fault)

    def test_running_detail_reads_only_closed_steps(self):
        op = self.submit(self.args(["result={'done':True}", "hou.block()" ]))
        self.assertTrue(self.hou.started.wait(1))
        running = self.runtime.get(op["operation_id"])
        self.assertEqual(running["steps"][1]["mutation_outcome"], "unknown")
        with self.assertRaises(StudioError) as error:
            self.ledger.detail(op["operation_id"])
        self.assertEqual(error.exception.code, "DETAIL_NOT_SEALED")
        self.assertFalse(self.ledger.detail(op["operation_id"], step_id="s1")["available"])
        original = self.ledger.detail(op["operation_id"], step_id="s0")
        self.assertTrue(json.loads(original["text"])["value"]["done"])
        self.hou.release.set()
        self.drain(op)
        self.assertEqual(original, self.ledger.detail(op["operation_id"], step_id="s0"))

    def test_restart_reconciles_step_states_without_reexecution(self):
        for active in (True, False):
            path = Path(self.temp.name) / ("restart-" + str(active) + ".sqlite")
            ledger = Ledger(path)
            op = {"operation_id": new_id(), "workspace_id": "workspace", "owner_id": "owner", "runtime_id": "old",
                  "scene_epoch": "old", "kind": "execute", "arguments": self.args(["pass"] * 3)}
            ledger.accept(op)
            detail = initial_detail(op["arguments"])
            detail["completed_steps"] = ["s0"]
            detail["steps"][0].update(state="finished", mutation_outcome="completed", value={"kept": True})
            if active:
                detail["active_step"] = "s1"
                detail["steps"][1]["state"] = "running"
            ledger.update(op["operation_id"], state="running", detail=detail)
            ledger.close()
            ledger = Ledger(path)
            try:
                ledger.recover()
                receipt = ledger.get(op["operation_id"])
                self.assertEqual(receipt["steps"][0]["value"], {"kept": True})
                self.assertEqual(receipt["steps"][1]["state"], "unknown" if active else "not_run")
                self.assertIsNone(receipt["active_step"])
            finally:
                ledger.close()
        self.assertEqual(self.hou.count, 0)


if __name__ == "__main__":
    unittest.main()
