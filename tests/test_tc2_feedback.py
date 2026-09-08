"""Execution feedback boundaries via the existing queue and stdio dispatcher."""
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace as NS
import unittest

from studio.common import encoded
from studio.ledger import Ledger
from studio.mcp import Adapter, serve_stdio
from studio.runtime import OperationRuntime
from studio.scene import HoudiniScene
from test_operations import FakeHou, RouteClient
from test_tc1_contracts import node, template


class FeedbackTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1] / ".runtime" / "tc2-tests"
        root.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=root)
        self.addCleanup(self.temp.cleanup)
        self.hou, self.nodes, self.evaluations = FakeHou(), {}, []
        self.scene = HoudiniScene(self.hou, Path(self.temp.name) / "artifacts")
        self.addCleanup(self.scene.close)
        self.hou.node = self.nodes.get
        self.hou.make = self.make
        self.hou.cancelled = False
        self.hou.replace = lambda: setattr(self.scene, "epoch", "replacement")

    def make(self):
        target = node("new")
        def evaluate():
            self.evaluations.append("eval")
            return 12
        target.globParms = lambda *a, **kw: [NS(name=lambda: "angle", parmTemplate=template,
            isMultiParmInstance=lambda: False, eval=evaluate)]
        target.geometry = lambda: self.evaluations.append("geometry")
        self.nodes[target.path()] = target

    def execute(self, script, **args):
        return self.scene.execute({"script": script, **args}, lambda: self.hou.cancelled)

    def test_stdio_new_target_is_observed_in_original_receipt_and_local_failure_is_retained(self):
        runtime = OperationRuntime(Ledger(Path(self.temp.name) / "operations.sqlite"), self.scene,
                                   lambda f: f(), workspace_id="workspace", session_id="session")
        self.addCleanup(runtime.close)
        adapter = Adapter(RouteClient(runtime), None,
                          {"workspace_id": "workspace", "runtime_id": runtime.runtime_id}, "owner")
        messages = [{"id": 1, "method": "tools/list"},
            {"id": 2, "method": "tools/call", "params": {"name": "hia_context", "arguments": {}}},
            {"id": 3, "method": "tools/call", "params": {"name": "hia_execute_hom", "arguments": {
                "script": "hou.make()", "observe_after": [{"path": "/obj/new"}, {"path": "/obj/missing"}]}}}]
        output = io.StringIO()
        serve_stdio(adapter, io.BytesIO(("\n".join(encoded(m) for m in messages) + "\n").encode()), output)
        reply = json.loads(output.getvalue().splitlines()[-1])["result"]
        receipt = json.loads(reply["content"][0]["text"])
        self.assertEqual(receipt["mutation_outcome"], "completed")
        self.assertEqual(receipt["state"], "finished")
        self.assertEqual(receipt["result_ref"], receipt["operation_id"])
        after = receipt["result"]["observe_after"]
        self.assertEqual([r["status"] for r in after["views"]], ["ok", "error"])
        self.assertEqual(after["views"][0]["scene_epoch"], self.scene.epoch)
        self.assertEqual(after["views"][0]["frame"], 1)
        self.assertEqual(after["views"][1]["error"]["index"], 1)

    def test_partial_only_reads_passive_metadata_keeps_original_error_and_small_value(self):
        views = [{"path": "/obj/new"}, {"path": "/obj/new", "view": "parameters", "include_values": True},
                 {"path": "/obj/new", "view": "geometry"}, {"path": "/obj/new", "view": "parms", "names": ["angle"]},
                 {"view": "checks", "checks": [{"kind": "cook", "path": "/obj/new"}]}]
        outcome = self.execute("hou.make()\nresult={'created':'/obj/new'}\nraise RuntimeError('deliberate failure')",
                               observe_after=views)
        self.assertEqual(outcome.mutation_outcome, "partial")
        self.assertEqual(outcome.detail["failure_phase"], "script")
        self.assertEqual(outcome.error["message"], "deliberate failure")
        self.assertEqual(self.evaluations, [])
        after = outcome.detail["observe_after"]
        self.assertEqual([r["status"] for r in after["views"]], ["ok", "ok", "skipped", "skipped", "skipped"])
        self.assertTrue(after["views"][1]["values_skipped"])
        self.assertEqual(outcome.detail["value_status"], "partial_script_value")
        self.assertEqual(outcome.detail["value"], {"created": "/obj/new"})
        original = self.nodes["/obj/new"]
        self.execute("result={'kept':True}", observe_after=[{"path": "/obj/new"}])
        self.assertIs(self.nodes["/obj/new"], original)

    def test_cancel_or_scene_replacement_skips_post_reads_without_reclassifying_mutation(self):
        for script, reason in (("hou.make(); hou.cancelled=True", "CANCEL_REQUESTED"),
                               ("hou.make(); hou.replace()", "SCENE_REPLACED")):
            self.hou.cancelled = False
            outcome = self.execute(script, checks=[{"kind": "cook", "path": "/obj/new"}],
                                   observe_after=[{"view": "geometry", "path": "/obj/new"}])
            self.assertEqual(outcome.mutation_outcome, "completed")
            self.assertEqual(outcome.detail["checks_skip_reason"], reason)
            self.assertEqual(outcome.detail["observe_after"]["views"][0]["reason"], reason)
        self.assertEqual(self.evaluations, [])

    def test_input_compile_precondition_and_before_failures_never_run_after_or_script(self):
        for args in ({"script": "invalid syntax !"}, {"script": "hou.make()", "observe": [{"path": "/obj/absent"}]},
                     {"script": "hou.make()", "preconditions": [{"kind": "node_exists", "path": "/obj/absent"}]},
                     {"script": "hou.make()", "observe_after": [{"path": "/obj/new"}] * 17}):
            outcome = self.scene.execute({"observe_after": [{"path": "/obj/new"}], **args}, lambda: False)
            self.assertEqual(outcome.mutation_outcome, "not_run")
            self.assertNotIn("observe_after", outcome.detail)
            self.assertEqual(self.nodes, {})

    def test_partial_serialization_does_not_call_custom_repr_or_emit_large_data(self):
        self.hou.BadValue = type("BadValue", (), {"__repr__": lambda _: self.fail("Invoked repr after failure")})
        outcome = self.execute("result=hou.BadValue(); raise RuntimeError('failure')")
        self.assertIn("omitted", outcome.detail["value"])
        outcome = self.execute("result={'x':'x'*100000}; raise RuntimeError('failure')")
        self.assertLess(len(encoded(outcome.detail["value"])), 4096)


if __name__ == "__main__":
    unittest.main()
