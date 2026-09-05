"""Offline harness contracts only. These never certify a real Houdini GUI run."""
import ast
import json
from pathlib import Path
import tempfile
import unittest

from studio.common import AppPaths, read_json
from studio.houdini_smoke import (SmokeFailure, creation_arguments, example_batch, operation,
                                  prepare, tool_value, validate_session, verify_created)
from studio.mcp import TOOLS, validate_schema
from studio.scene import validate_arguments


def envelope(value):
    return {"content": [{"type": "text", "text": json.dumps(value)}]}


class SmokeContractTests(unittest.TestCase):
    def test_prepare_only_creates_unique_not_run_workspaces(self):
        base = Path(__file__).resolve().parents[1] / ".runtime" / "tests"
        base.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="smoke 中文 ", dir=base) as folder:
            root = Path(folder)
            (root / "pyproject.toml").touch()
            paths = AppPaths(root)
            first, second = prepare(paths), prepare(paths)
            self.assertNotEqual(first["workspace_id"], second["workspace_id"])
            self.assertNotEqual(first["report"], second["report"])
            self.assertEqual(read_json(first["report"])["status"], "not_run")
            self.assertEqual(list(paths.workspace(first["workspace_id"]).glob("*.sqlite")), [])
            self.assertFalse(paths.local("sessions").exists())

    def test_wrong_workspace_gui_or_initial_hip_is_rejected(self):
        env = {"BCS_WORKSPACE_ID": "dedicated", "BCS_SESSION_ID": "new-session"}
        marker = {"purpose": "houdini-gui-smoke", "workspace_id": "dedicated", "run_id": "one"}
        launch = {"workspace_id": "dedicated", "launcher_session_id": "new-session", "hip": None}
        identity = {**launch, "houdini_pid": 99}
        validate_session(marker, launch, identity, env, 99)
        for changed_marker, changed_launch, changed_identity in (
                ({**marker, "purpose": "user-workspace"}, launch, identity),
                (marker, {**launch, "hip": "user.hip"}, identity),
                (marker, launch, {**identity, "houdini_pid": 100}),
                (marker, launch, {**identity, "launcher_session_id": "old-session"})):
            with self.subTest(marker=changed_marker, launch=changed_launch, identity=changed_identity):
                with self.assertRaises(SmokeFailure):
                    validate_session(changed_marker, changed_launch, changed_identity, env, 99)

    def test_batch_guards_precede_creation_and_match_production_contract(self):
        arguments = creation_arguments("/obj/bcs_smoke_contract")
        source = arguments["script"]
        tree = ast.parse(source)
        compile(tree, "<offline smoke contract>", "exec")
        first_creation = next(node.lineno for node in ast.walk(tree) if isinstance(node, ast.Call)
                              and isinstance(node.func, ast.Attribute) and node.func.attr == "createNode")
        assertions = [node for node in tree.body if isinstance(node, ast.Assert)]
        self.assertTrue(assertions)
        self.assertTrue(all(node.lineno < first_creation for node in assertions))
        for prohibited in ("hipFile.clear", "hipFile.load", "hipFile.save", ".destroy(", "processEvents"):
            self.assertNotIn(prohibited, source)
        validate_arguments("execute", arguments)
        validate_schema(arguments, next(tool["inputSchema"] for tool in TOOLS if tool["name"] == "hia_execute_hom"))
        with self.assertRaises(ValueError):
            example_batch("/obj/user_asset")

    def test_pending_context_is_queried_through_same_mcp_before_write(self):
        class Wire:
            def __init__(self):
                self.calls = []
            def call(self, name, arguments):
                self.calls.append((name, arguments))
                return envelope({"operation_id": "observed", "state": "queued" if len(self.calls) == 1 else "finished"})
        wire, receipts = Wire(), []
        self.assertEqual(operation(wire, "hia_context", {}, receipts.append)["state"], "finished")
        self.assertEqual(wire.calls, [("hia_context", {}), ("hia_operation", {"action": "get", "operation_id": "observed"})])
        self.assertEqual([r["operation_id"] for r in receipts], ["observed", "observed"])

    def test_timeout_keeps_original_operation_id_and_does_not_replay(self):
        class Wire:
            calls = 0
            def call(self, name, arguments):
                self.calls += 1
                return envelope({"operation_id": "pending-write", "state": "running"})
        wire, receipts = Wire(), []
        with self.assertRaises(SmokeFailure):
            operation(wire, "hia_execute_hom", {"script": "fixture"}, receipts.append, seconds=0)
        self.assertEqual(wire.calls, 1)
        self.assertEqual(receipts[0]["operation_id"], "pending-write")
        with self.assertRaises(SmokeFailure):
            tool_value(envelope({"error": {"code": "REJECTED"}}))

    def test_finished_without_geometric_evidence_cannot_pass(self):
        root = "/obj/bcs_smoke_contract"
        receipt = {"operation_id": "fixture", "state": "finished", "mutation_outcome": "completed",
                   "checks_outcome": "passed", "result": {"value": {
                       "root": root, "main_thread": True, "size": [2, 2, 2], "points": 8, "primitives": 6,
                       "attribute_values": [1.0], "errors": []}}}
        verify_created(receipt, root)
        for value in ({"points": 0}, {"attribute_values": []}, {"size": [1, 1, 1]}, {"errors": ["cook failed"]}):
            with self.subTest(value=value):
                with self.assertRaises(SmokeFailure):
                    verify_created({**receipt, "result": {"value": {**receipt["result"]["value"], **value}}}, root)
        with self.assertRaises(SmokeFailure):
            verify_created({**receipt, "mutation_outcome": "unknown"}, root)
