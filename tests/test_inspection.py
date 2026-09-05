"""Targeted reads must not materialize every geometry element or evaluate all parms."""
import unittest
from types import SimpleNamespace as NS

from studio.common import StudioError
from studio.inspection import geometry_facts, parameter_instances
from studio.mcp import TOOLS, validate_schema
from studio.scene import validate_view


class InspectionTests(unittest.TestCase):
    def test_parameter_page_exposes_real_multiparm_names_without_evaluation(self):
        visited = []
        def parm(index):
            def template():
                visited.append(index)
                return NS(name=lambda: "value#", label=lambda: "Value", type=lambda: "Float",
                          numComponents=lambda: 1, defaultValue=lambda: (0.0,))
            return NS(name=lambda: "value" + str(index), parmTemplate=template,
                      isMultiParmInstance=lambda: True, multiParmInstanceIndices=lambda: (index - 1,))
        def glob(pattern, **kwargs):
            self.assertEqual(pattern, "value*")
            self.assertTrue(kwargs["single_pattern"])
            return tuple(parm(i) for i in range(1, 7))
        result = parameter_instances(NS(globParms=glob), {"pattern": "value*", "offset": 2, "limit": 2})
        self.assertEqual(visited, [3, 4])
        self.assertEqual(result["next_offset"], 4)
        self.assertEqual(result["parameters"][0]["name"], "value3")
        self.assertEqual(result["parameters"][0]["template_name"], "value#")
        self.assertEqual(result["parameters"][0]["multiparm_indices"], [2])

    def test_large_geometry_reads_only_requested_elements_and_skips_array_values(self):
        accesses, reads = [], []
        scalar = NS(name=lambda: "Cd", dataType=lambda: "Float", size=lambda: 3,
                    qualifier=lambda: "Color", isArrayType=lambda: False)
        array = NS(name=lambda: "weights", dataType=lambda: "Float", size=lambda: 1,
                   qualifier=lambda: "None", isArrayType=lambda: True)
        def value(attribute):
            self.assertIs(attribute, scalar, "Array values must not be fetched then sliced")
            reads.append(attribute.name())
            return (0.1, 0.2, 0.3)
        def element(index):
            accesses.append(index)
            return NS(attribValue=value)
        geometry = NS(intrinsicValue=lambda key: 100000000,
                      boundingBox=lambda: NS(minvec=lambda: (0, 0, 0), maxvec=lambda: (1, 1, 1)),
                      findPointAttrib=lambda name: {"Cd": scalar, "weights": array}.get(name), point=element)
        result = geometry_facts(NS(geometry=lambda: geometry),
                                {"owners": ["point"], "attributes": ["Cd", "weights", "absent"], "samples": 2})
        self.assertEqual(accesses, [0, 1])
        self.assertEqual(reads, ["Cd", "Cd"])
        self.assertEqual(result["missing_attributes"]["point"], ["absent"])
        self.assertTrue(result["samples"]["point"]["truncated"])
        self.assertEqual(result["attributes"]["point"][0]["tuple_size"], 3)
        self.assertIn("omitted", result["samples"]["point"]["elements"][0]["values"]["weights"])

    def test_inspect_schema_accepts_targeted_views_and_rejects_unbounded_samples(self):
        schema = next(t["inputSchema"] for t in TOOLS if t["name"] == "hia_inspect")
        views = [{"view": "parameters", "path": "/obj/asset", "pattern": "shelf*", "limit": 20},
                 {"view": "geometry", "path": "/obj/asset/OUT", "owners": ["vertex", "detail"], "samples": 2}]
        validate_schema({"views": views}, schema)
        for view in views:
            validate_view(view)
        for bad in ({"view": "geometry", "samples": 100000}, {"view": "geometry", "samples": True},
                    {"view": "geometry", "owners": ["point", "point"]},
                    {"view": "parameters", "offset": -1}):
            with self.assertRaises(StudioError):
                validate_view(bad)


if __name__ == "__main__":
    unittest.main()
