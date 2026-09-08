"""TC-1 discovery/observation contracts through the real adapter and queue."""
import io
import json
from pathlib import Path
import tempfile
from types import ModuleType, SimpleNamespace as NS
import unittest
from unittest.mock import patch

from studio.common import StudioError, encoded
from studio.inspection import geometry_facts, parameter_instances, working_context
from studio.ledger import Ledger
from studio.lookup import installed_lookup
from studio.mcp import Adapter, TOOLS, serve_stdio, validate_schema
from studio.runtime import OperationRuntime
from studio.scene import HoudiniScene, validate_arguments
from test_operations import FakeHou, RouteClient


def template(name="value#"):
    return NS(name=lambda: name, label=lambda: "Value", type=lambda: "Float",
              numComponents=lambda: 1, defaultValue=lambda: (0.0,),
              minValue=lambda: 0, maxValue=lambda: 10, minIsStrict=lambda: True,
              menuItems=lambda: ("alpha", "beta"), menuLabels=lambda: ("Alpha", "Beta"),
              itemGeneratorScript=lambda: "raise Exception('must never execute')")


def node(name="asset", category="Sop", parent=None):
    return NS(path=lambda: "/obj/" + name, name=lambda: name, parent=lambda: parent,
              type=lambda: NS(name=lambda: "null", category=lambda: NS(name=lambda: category)),
              inputs=lambda: (), children=lambda: (), globParms=lambda *a, **kw: ())


class InstalledType:
    def __init__(self, category, name, label="", aliases=(), hidden=None, deprecated=None):
        self.category = lambda: category
        self.name = lambda: name
        self.description = lambda: label
        self.aliases = lambda: aliases
        if hidden is not None:
            self.hidden = lambda: hidden
        if deprecated is not None:
            self.deprecated = lambda: deprecated
        self.nameComponents = lambda: ("", "", name, "")
        self.parmTemplates = lambda: (template(),)


class CapabilityTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1] / ".runtime" / "tc1-tests"
        root.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=root)
        self.addCleanup(self.temp.cleanup)
        self.hou = FakeHou()
        self.types = {}
        self.category = NS(name=lambda: "Sop", label=lambda: "Geometry", nodeTypes=lambda: self.types)
        self.hou.nodeTypeCategories = lambda: {"Sop": self.category}
        self.scene = HoudiniScene(self.hou, Path(self.temp.name) / "captures")
        self.addCleanup(self.scene.close)

    def add_type(self, name, **kwargs):
        item = InstalledType(self.category, name, **kwargs)
        self.types[name] = item
        return item

    def lookup(self, *requests):
        return installed_lookup(self.hou, {"source": "metadata", "requests": list(requests)},
                                self.scene.redact, self.scene.error)

    def test_wire_list_then_canonical_and_legacy_calls_reach_same_backend(self):
        self.add_type("unknown_exact", label="Even Spacing", aliases=("stride",))
        runtime = OperationRuntime(Ledger(Path(self.temp.name) / "receipts.sqlite"), self.scene,
                                   lambda callback: callback(), workspace_id="workspace", session_id="session")
        self.addCleanup(runtime.close)
        client = RouteClient(runtime)
        adapter = Adapter(client, None, {"workspace_id": "workspace", "runtime_id": runtime.runtime_id}, "owner")
        requests = [{"id": 1, "method": "tools/list"}]
        arguments = [
            {"source": "metadata", "requests": [{"kind": "search", "category": "Sop", "query": "stride"}]},
            {"category": "Sop", "query": "stride"},
            {"source": "metadata", "requests": [{"kind": "search", "category": "Sop", "query": "stride", "limit": True}]},
        ]
        requests.extend({"id": index + 2, "method": "tools/call", "params": {
            "name": "hia_lookup", "arguments": args}} for index, args in enumerate(arguments))
        output = io.StringIO()
        serve_stdio(adapter, io.BytesIO(("\n".join(encoded(r) for r in requests) + "\n").encode()), output)
        replies = [json.loads(line)["result"] for line in output.getvalue().splitlines()]
        self.assertEqual(len(replies[0]["tools"]), 7)
        canonical, legacy = [json.loads(r["content"][0]["text"])["result"] for r in replies[1:3]]
        self.assertEqual(canonical["requests"][0]["types"], legacy["types"])
        self.assertEqual(canonical["requests"][0]["types"][0]["name"], "unknown_exact")
        self.assertTrue(replies[3]["isError"])
        self.assertEqual(len(client.posts), 2, "Invalid wire calls must never enter the queue")

    def test_schema_and_runtime_reject_mixed_or_incomplete_shapes_before_hom(self):
        schema = next(t["inputSchema"] for t in TOOLS if t["name"] == "hia_lookup")
        malformed = [
            {"source": "metadata", "requests": []},
            {"requests": [{"kind": "categories"}]},
            {"source": "metadata", "requests": [{"kind": "type", "category": "Sop"}]},
            {"source": "metadata", "requests": [{"kind": "search", "category": "Sop", "query": "--"}]},
            {"source": "metadata", "requests": [{"kind": "categories"}], "query": "x"},
            {"source": "metadata", "requests": [{"kind": "categories"}] * 5},
            {"source": "hom", "symbol": "hou", "members": True, "offset": True},
            {"type_name": "x", "help_limit": True}, {"source": "hom", "symbol": ""},
        ]
        for args in malformed:
            with self.subTest(args=args):
                for validator in (lambda: validate_schema(args, schema), lambda: validate_arguments("lookup", args)):
                    with self.assertRaises(StudioError):
                        validator()

    def test_runtime_observation_summary_retains_redacted_raw_detail_and_receipt(self):
        secret = "synthetic-summary-secret"
        self.scene.secrets = (secret,)
        ledger = Ledger(Path(self.temp.name) / "receipts.sqlite")
        runtime = OperationRuntime(ledger, self.scene, lambda callback: callback(),
                                   workspace_id="workspace", session_id="session")
        self.addCleanup(runtime.close)
        data = {"status": "ok", "views": [{"index": 0, "view": "parameters", "path": "/obj/asset",
            "status": "ok", "parameters": [{"name": "value" + str(i), "help": "x" * 500 + secret} for i in range(100)],
            "offset": 0, "total": 100, "next_offset": None, "truncated": False}]}
        with patch.object(self.scene, "run", return_value=data):
            client = RouteClient(runtime)
            adapter = Adapter(client, None, {"workspace_id": "workspace", "runtime_id": runtime.runtime_id}, "owner")
            adapter.scene_epoch = self.scene.epoch
            value = adapter.call("hia_inspect", {"views": [{"path": "/obj/asset"}]})
        receipt = json.loads(value["content"][0]["text"])
        self.assertEqual(receipt["state"], "finished")
        self.assertEqual(receipt["mutation_outcome"], "none")
        self.assertEqual(receipt["result_ref"], receipt["operation_id"])
        self.assertNotIn(secret, encoded(receipt))
        self.assertTrue(receipt["result"]["views"][0]["parameters"])
        offset, pieces = 0, []
        while offset is not None:
            page = ledger.detail(receipt["operation_id"], offset)
            pieces.append(page["text"])
            offset = page["next_offset"]
        raw = json.loads("".join(pieces))
        self.assertEqual(len(raw["views"][0]["parameters"]), 100)
        self.assertIn("[REDACTED]", raw["views"][0]["parameters"][0]["help"])
        self.assertNotIn(secret, encoded(raw))

    def test_alias_label_order_filters_unknown_and_no_stale_catalog(self):
        self.add_type("a", label="Offset Normal", hidden=False, deprecated=False)
        self.add_type("b", label="Offset", aliases=("normal",))
        self.add_type("normal", hidden=False, deprecated=False)
        self.add_type("hidden", label="Normal", hidden=True)
        self.add_type("old", label="Normal", deprecated=True)
        search = {"kind": "search", "category": "Sop", "query": "normal", "limit": 2}
        first = self.lookup(search)["requests"][0]
        second = self.lookup({**search, "offset": first["next_offset"]})["requests"][0]
        self.assertEqual([r["name"] for r in first["types"] + second["types"]], ["normal", "b", "a"])
        self.assertEqual(first["types"][1]["matched_on"], ["alias"])
        self.assertIsNone(first["types"][1]["hidden"])
        self.assertEqual(first["filters"]["filtered_matches"], {"hidden": 1, "deprecated": 1, "total": 2})
        self.assertIsNone(second["next_offset"])
        self.add_type("new", label="Normal")
        self.assertEqual(self.lookup(search)["requests"][0]["total"], 4)
        del self.types["new"]
        self.assertEqual(self.lookup(search)["requests"][0]["total"], 3)

    def test_exact_legacy_lifecycle_missing_replacement_and_batch_errors(self):
        old = self.add_type("legacy", hidden=True, deprecated=True)
        replacement = InstalledType(self.category, "uninstalled")
        old.deprecationInfo = lambda: {"new_type": replacement}
        result = self.lookup(
            {"kind": "type", "category": "Sop", "type_name": "legacy", "include_help": False},
            {"kind": "type", "category": "Sop", "type_name": "missing"},
            {"kind": "search", "category": "wrong", "query": "anything"})
        self.assertEqual(result["status"], "partial")
        legacy, missing, category = result["requests"]
        self.assertTrue(legacy["hidden"] and legacy["deprecated"])
        self.assertFalse(legacy["deprecation"]["replacement"]["installed"])
        self.assertFalse(legacy["deprecation"]["metadata_complete"])
        self.assertEqual(legacy["parameters"][0]["name_kind"], "template_pattern")
        self.assertEqual(missing["error"]["index"], 1)
        self.assertEqual(missing["error"]["target"]["type_name"], "missing")
        self.assertEqual(category["error"]["code"], "CATEGORY_NOT_FOUND")

    def test_parameter_metadata_never_evaluates_and_values_only_evaluate_page(self):
        calls = []
        def parm(i):
            def evaluate():
                calls.append(i)
                if i == 2:
                    raise RuntimeError("evaluation failed")
                return i
            return NS(name=lambda: "v" + str(i), parmTemplate=template, isMultiParmInstance=lambda: True,
                      multiParmInstanceIndices=lambda: (i,), componentIndex=lambda: 0,
                      tuple=lambda: NS(name=lambda: "v" + str(i)), eval=evaluate,
                      menuItems=lambda: self.fail("Dynamic menu evaluated"))
        target = NS(globParms=lambda *a, **kw: [parm(i) for i in range(4)])
        view = {"path": "/obj/asset", "view": "parameters", "offset": 1, "limit": 2}
        default = parameter_instances(target, view)
        self.assertEqual(calls, [])
        self.assertEqual(default["parameters"][0]["menu"]["items"][1]["token"], "beta")
        self.assertTrue(default["parameters"][0]["menu"]["dynamic"])
        values = parameter_instances(target, {**view, "include_values": True}, strict=False)
        self.assertEqual(calls, [1, 2])
        self.assertEqual(values["status"], "partial")
        self.assertEqual(values["parameters"][0]["value"], 1)
        self.assertEqual(values["parameters"][1]["error"]["index"], 2)
        with self.assertRaises(RuntimeError):
            parameter_instances(target, {**view, "include_values": True})

    def test_inspect_partial_and_strict_execute_missing_or_evaluation_failure(self):
        target = node()
        target.parm = lambda name: None if name == "missing" else NS(eval=lambda: 1 / 0)
        reads = []
        def get(path):
            reads.append(path)
            return target if path == "/obj/asset" else None
        self.hou.node = get
        with self.assertRaises(StudioError):
            self.scene.run("inspect", {"views": [{"path": "/obj/asset"}, {"view": "children", "limit": True}]}, lambda: False)
        self.assertEqual(reads, [])
        result = self.scene.run("inspect", {"views": [{"path": "/obj/missing"}, {"path": "/obj/asset"}]}, lambda: False)
        self.assertEqual([r["status"] for r in result["views"]], ["error", "ok"])
        self.assertEqual(result["views"][0]["error"]["index"], 0)
        for view in ({"path": "/obj/missing"}, {"path": "/obj/asset", "view": "parms", "names": ["missing"]},
                     {"path": "/obj/asset", "view": "parms", "names": ["bad"]}):
            outcome = self.scene.execute({"script": "hou.mutate()", "observe": [view]}, lambda: False)
            self.assertEqual(outcome.mutation_outcome, "not_run")
            self.assertEqual(self.hou.count, 0)

    def test_children_paging_ports_diagnostics_and_context_fallback(self):
        target, source = node("target"), node("source")
        target.inputConnections = lambda: (NS(inputNode=lambda: source, outputIndex=lambda: 2, inputIndex=lambda: 4),)
        target.inputs = lambda: (None, source)
        target.errors = lambda: ("last cook failure",)
        target.needsToCook = lambda: True
        target.cook = lambda *a, **kw: self.fail("Graph read forced a cook")
        root = node("root", "Object")
        root.children = lambda: (target, source)
        root.childTypeCategory = lambda: self.category
        self.hou.node = lambda p: root
        result = self.scene.inspect({"view": "children", "path": "/obj/root", "offset": 1, "limit": 1})
        self.assertEqual(result["nodes"][0]["connections"][0], {
            "source": "/obj/source", "source_output_index": 2, "destination_input_index": 4})
        self.assertEqual(result["nodes"][0]["errors"], ["last cook failure"])
        self.assertFalse(result["nodes"][0]["cook"]["verified_by_this_read"])
        self.assertIsNone(result["nodes"][0]["flags"]["display"])
        self.hou.selectedNodes = lambda: [target] * 20
        self.hou.isUIAvailable = lambda: False
        context = working_context(self.hou)
        self.assertEqual(context["selection_summary"]["total"], 20)
        self.assertEqual(len(context["selection_summary"]["nodes"]), 16)
        self.assertFalse(context["network_summary"]["observed"])
        self.hou.isUIAvailable = lambda: True
        self.hou.paneTabType = NS(NetworkEditor="network")
        self.hou.ui = NS(paneTabOfType=lambda kind: NS(pwd=lambda: root, name=lambda: "pane1"))
        self.assertEqual(working_context(self.hou)["network_summary"]["source"], "first_network_editor")

    def test_geometry_bounds_stay_local_and_groups_do_not_expand_members(self):
        parent = node("transformed_object", "Object")
        parent.worldTransform = lambda: self.fail("Bounds must not claim world conversion")
        target = node("transformed_object/OUT", parent=parent)
        groups = [NS(name=lambda i=i: "g" + str(i), points=lambda: self.fail("Expanded group")) for i in range(5)]
        target.geometry = lambda: NS(intrinsicValue=lambda k: 0,
            boundingBox=lambda: NS(minvec=lambda: (0, 0, 0), maxvec=lambda: (1, 1, 1)),
            pointAttribs=lambda: (), primAttribs=lambda: (), pointGroups=lambda: groups, primGroups=lambda: (), edgeGroups=lambda: ())
        result = geometry_facts(target, {"include_groups": True, "group_limit": 2})
        self.assertEqual(result["bounds"]["space"], "object_local")
        self.assertEqual(result["bounds"]["space_path"], "/obj/transformed_object")
        self.assertEqual(result["groups"]["point"], {"available": True, "names": ["g0", "g1"], "total": 5, "truncated": True})

    def test_hom_root_discovery_and_explicit_missing_signature(self):
        self.scene.hou = ModuleType("hou")
        self.scene.hou.WorkingType = type("WorkingType", (), {})
        result = self.scene.lookup({"source": "hom", "symbol": "hou", "members": True, "query": "WorkingType"})
        self.assertEqual(result["members"][0]["name"], "WorkingType")
        with patch("studio.scene.inspect.signature", side_effect=ValueError):
            result = self.scene._hom_symbol_info(lambda: None)
        self.assertEqual(result["signature_status"], "unavailable")
        self.assertIsNone(result["signature"])


if __name__ == "__main__":
    unittest.main()
