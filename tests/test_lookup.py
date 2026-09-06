"""Installed symbol discovery stays static, optional and bounded; no real HOM."""
from types import SimpleNamespace
import unittest

from studio.common import StudioError
from studio.mcp import TOOLS, validate_schema
from studio.scene import HoudiniScene, validate_arguments


class LookupTests(unittest.TestCase):
    def setUp(self):
        self.scene = object.__new__(HoudiniScene)
        self.scene.secrets = ()
        self.scene.houdini_version = "fake-installed-metadata"
        class ViewCamera:
            def setRotation(self, mat): pass
            setRotation.__annotations__ = {"mat": "Matrix3", "return": "void"}

        class Guides:
            XYPlane = "XY"
            XZPlane = "XZ"
            YZPlane = "YZ"

            @property
            def NeverRead(self):
                raise AssertionError("Discovery invoked a live descriptor")

        self.scene.hou = SimpleNamespace(GeometryViewportCamera=ViewCamera, viewportGuide=Guides)

    def test_signature_exposes_missing_docstring_type_and_discovery_never_calls_descriptors(self):
        result = self.scene.lookup({"source": "hom", "symbol": "hou.GeometryViewportCamera.setRotation"})
        self.assertEqual(result["documentation"], "")
        self.assertIn("mat: 'Matrix3'", result["signature"])
        self.assertIn("void", result["signature"])
        result = self.scene.lookup({"source": "hom", "symbol": "hou.viewportGuide", "members": True})
        self.assertEqual([item["name"] for item in result["members"]], ["NeverRead", "XYPlane", "XZPlane", "YZPlane"])
        self.assertEqual(result["members"][0]["kind"], "property")

    def test_member_pages_filter_names_and_limit_metadata_reads(self):
        schema = next(t["inputSchema"] for t in TOOLS if t["name"] == "hia_lookup")
        arguments = {"source": "hom", "symbol": "hou.viewportGuide", "members": True,
                     "query": "plane", "offset": 1, "limit": 1}
        validate_schema(arguments, schema)
        info_calls = []
        original = self.scene._hom_symbol_info
        def info(obj, short=False):
            info_calls.append(short)
            return original(obj, short)
        self.scene._hom_symbol_info = info
        result = self.scene.lookup(arguments)
        self.assertEqual(result["total"], 3)
        self.assertEqual(result["next_offset"], 2)
        self.assertEqual([m["name"] for m in result["members"]], ["XZPlane"])
        self.assertEqual(info_calls, [False, True])
        for changes in ({"limit": 65}, {"offset": -1}, {"limit": True}, {"members": "yes"},
                        {"query": "x" * 129}, {"source": "metadata"}, {"members": False}):
            with self.subTest(changes=changes), self.assertRaises(StudioError):
                validate_arguments("lookup", {**arguments, **changes})

    def test_absent_private_and_non_namespace_symbols_are_not_evaluated(self):
        for args in ({"symbol": "hou.viewportGuide.Grid"}, {"symbol": "hou.viewportGuide.__dict__"},
                     {"symbol": "hou.viewportGuide.NeverRead", "members": True}):
            with self.subTest(args=args), self.assertRaises(StudioError):
                self.scene.lookup({"source": "hom", **args})


if __name__ == "__main__":
    unittest.main()
