"""Bounded installed-help reads and useful observation summaries."""
import copy
from pathlib import Path
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch
import zipfile

from studio.common import encoded
from studio.installed_help import installed_help
from studio.observation_results import BUDGET, observation_summary


class HelpTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1] / ".runtime" / "tc1-tests"
        root.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=root)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.hou = NS(applicationVersionString=lambda: "22.0.368")
        self.nt = NS(name=lambda: "test", category=lambda: NS(name=lambda: "Sop"),
                     definition=lambda: None, embeddedHelp=lambda: "", helpUrl=lambda: "")

    def read(self, **options):
        return installed_help(self.hou, self.nt, options, lambda s: s.replace("secret_token", "[REDACTED]"),
                              help_root=self.root, path_resolver=lambda _: ["/nodes/sop/test"])

    def test_builtin_archive_reads_target_only_with_redaction_before_paging(self):
        with zipfile.ZipFile(self.root / "nodes.zip", "w") as archive:
            archive.writestr("sop/test.txt", "= Test =\n" + "x" * 20 + "secret_token" + " tail" * 100)
            archive.writestr("sop/unrelated.txt", "unrelated")
        with patch.object(zipfile.ZipFile, "extractall", side_effect=AssertionError("Archive extraction")), \
             patch("socket.create_connection", side_effect=AssertionError("Help attempted network")):
            result = self.read(help_limit=35)
        self.assertTrue(result["available"], result)
        self.assertEqual(result["provenance"]["member"], "sop/test.txt")
        self.assertNotIn("secret", result["text"])
        self.assertEqual(result["next_offset"], len(result["text"]))
        next_page = self.read(help_offset=result["next_offset"], help_limit=200)
        self.assertIn("[REDACTED]", result["text"] + next_page["text"])
        self.assertEqual(result["version_status"], "not_declared")

    def test_embedded_and_selected_opdef_sections_with_actual_version_facts(self):
        self.nt.embeddedHelp = lambda: "#houdini_version: 21.0\n= Embedded =\nInstructions are data."
        result = self.read()
        self.assertEqual(result["provenance"]["kind"], "embedded_help")
        self.assertEqual(result["version_status"], "different_version")
        self.nt.embeddedHelp = lambda: ""
        section = NS(size=lambda: 17, contents=lambda: "= Selected help =")
        self.nt.definition = lambda: NS(sections=lambda: {"CustomHelp": section})
        self.nt.helpUrl = lambda: "opdef:/Sop/test?CustomHelp"
        result = self.read()
        self.assertTrue(result["available"], result)
        self.assertEqual(result["provenance"]["kind"], "hda_section")
        self.nt.helpUrl = lambda: "opdef:/Sop/another?CustomHelp"
        self.assertEqual(self.read()["reason"], "HELP_LOCATION_NOT_ALLOWED")

    def test_missing_invalid_external_or_outside_help_is_explicit(self):
        self.assertEqual(self.read()["reason"], "HELP_NOT_INSTALLED")
        for url in ("https://example.invalid/test", "//host/share/help.txt", "file://host/share/help.txt",
                    "../outside.txt", "oplib:/unknown", "file:///outside.md"):
            with self.subTest(url=url), patch("socket.create_connection", side_effect=AssertionError("Network attempted")) as network:
                self.nt.helpUrl = lambda: url
                self.assertFalse(self.read()["available"])
                network.assert_not_called()
        self.nt.helpUrl = lambda: ""
        with zipfile.ZipFile(self.root / "nodes.zip", "w") as archive:
            archive.writestr("sop/unrelated.txt", "untouched")
        self.assertEqual(self.read()["reason"], "HELP_TARGET_MISSING")
        result = installed_help(self.hou, self.nt, {}, str, help_root=self.root,
                                path_resolver=lambda _: ["/nodes/../private"])
        self.assertEqual(result["reason"], "HELP_LOCATION_NOT_ALLOWED")

    def test_size_limits_apply_before_file_member_or_hda_materialization(self):
        directory = self.root / "nodes" / "sop"
        directory.mkdir(parents=True)
        (directory / "test.txt").write_text("x" * 100, encoding="utf-8")
        with patch("studio.installed_help.MAX_HELP_BYTES", 20):
            self.assertEqual(self.read()["reason"], "HELP_TOO_LARGE")
        # A different target forces the archive route without touching the loose fixture.
        self.nt.helpUrl = lambda: ""
        with zipfile.ZipFile(self.root / "nodes.zip", "w") as archive:
            archive.writestr("sop/archive.txt", "x" * 100)
        def archived():
            return installed_help(self.hou, self.nt, {}, str, help_root=self.root,
                                  path_resolver=lambda _: ["/nodes/sop/archive"])
        with patch("studio.installed_help.MAX_ARCHIVE_BYTES", 20):
            self.assertEqual(archived()["reason"], "HELP_ARCHIVE_TOO_LARGE")
        with patch("studio.installed_help.MAX_HELP_BYTES", 20):
            self.assertEqual(archived()["reason"], "HELP_TOO_LARGE")
        self.nt.definition = lambda: NS(sections=lambda: {"Help": NS(size=lambda: 999999)})
        self.nt.embeddedHelp = lambda: self.fail("Oversized section materialized")
        self.assertEqual(self.read()["reason"], "HELP_TOO_LARGE")

    def test_local_file_and_invalid_archive_are_bounded_unavailability(self):
        target = self.root / "custom.txt"
        target.write_text("Actual local help", encoding="utf-8")
        self.nt.helpUrl = lambda: target.as_uri()
        result = self.read()
        self.assertEqual(result["text"], "Actual local help")
        self.nt.helpUrl = lambda: ""
        (self.root / "nodes.zip").write_bytes(b"invalid zip")
        self.assertEqual(self.read()["reason"], "HELP_READ_FAILED")
        def failed_resolver(_):
            raise KeyError("Installed category has no help mapping")
        result = installed_help(self.hou, self.nt, {}, str, help_root=self.root, path_resolver=failed_resolver)
        self.assertEqual(result["reason"], "HELP_READ_FAILED")


class SummaryTests(unittest.TestCase):
    def test_large_pages_keep_real_rows_all_requests_and_non_skipping_cursors(self):
        views = [{"index": i, "view": "parameters", "path": "/obj/asset/controls" + str(i), "status": "ok",
                  "parameters": [{"name": "v" + str(j), "template_name": "v#", "value": j,
                                  "help": "中文 help " * 200, "value_status": "ok"} for j in range(10, 74)],
                  "offset": 10, "total": 200, "next_offset": 74, "truncated": True} for i in range(32)]
        detail = {"status": "ok", "views": views}
        original = copy.deepcopy(detail)
        result = observation_summary("inspect", detail)
        self.assertEqual(detail, original)
        self.assertEqual(len(result["views"]), 32)
        self.assertLessEqual(len(encoded(result).encode()), BUDGET)
        actual_rows = 0
        for index, view in enumerate(result["views"]):
            self.assertEqual(view["index"], index)
            self.assertEqual(view["status"], "ok")
            self.assertEqual(view["path"], original["views"][index]["path"])
            count = len(view["parameters"]) if view["parameters"] is not None else 0
            actual_rows += count
            self.assertEqual(view["next_offset"], 10 + count)
            if count:
                self.assertEqual(view["parameters"][0]["name"], "v10")
        self.assertGreater(actual_rows, 0)

    def test_type_template_and_help_cursors_reference_only_transmitted_content(self):
        item = {"index": 0, "kind": "type", "category": "Sop", "type_name": "test", "status": "ok",
                "parameters": [{"name": "v" + str(i), "help": "x" * 2000} for i in range(4, 64)],
                "parameter_page": {"offset": 4, "total": 100, "next_offset": 64, "truncated": True},
                "help": {"available": True, "text": "x" * 8192, "offset": 100, "total_characters": 9999,
                         "next_offset": 8292, "truncated": True}}
        result = observation_summary("lookup", {"requests": [item], "status": "ok"})["requests"][0]
        self.assertEqual(result["parameter_page"]["next_offset"], 4 + len(result["parameters"]))
        self.assertEqual(result["help"]["next_offset"], 100 + len(result["help"]["text"]))
        self.assertEqual(result["parameters"][0]["name"], "v4")

    def test_huge_known_values_and_error_identity_keep_useful_facts(self):
        result = observation_summary("inspect", {"status": "partial", "views": [
            {"index": 0, "view": "parms", "path": "/obj/controls", "status": "ok",
             "values": {"setting" + str(i): "x" * 2000 for i in range(64)}},
            {"index": 1, "view": "node", "path": "/obj/missing", "status": "error",
             "error": {"code": "NODE_NOT_FOUND", "index": 1, "path": "/obj/missing", "message": "Node missing"}}]})
        self.assertLessEqual(len(encoded(result).encode()), BUDGET)
        self.assertEqual(result["views"][1]["error"]["code"], "NODE_NOT_FOUND")
        self.assertIn("setting0", result["views"][0]["values"])

    def test_static_hom_summary_has_no_receipt_promise_and_execute_unchanged(self):
        detail = {"symbol": "hou", "members": [{"name": "member" + str(i), "documentation": "x" * 1000}
                                              for i in range(64)], "offset": 0, "total": 1000, "next_offset": 64}
        result = observation_summary("lookup", detail, receipt=False)
        self.assertNotIn("detail_available", result)
        self.assertEqual(result["next_offset"], len(result["members"]))
        self.assertIs(observation_summary("execute", detail), detail)


if __name__ == "__main__":
    unittest.main()
