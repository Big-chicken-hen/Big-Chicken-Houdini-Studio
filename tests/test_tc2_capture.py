"""Target transforms, requested-frame ordering and existing artifact boundaries."""
import io
import json
import math
from pathlib import Path
import tempfile
from types import SimpleNamespace as NS
import unittest

from studio.capture_targets import transformed_bounds
from studio.common import StudioError, encoded
from studio.mcp import Adapter, CAPTURE_SCHEMA, serve_stdio, validate_schema
from studio.observation_results import capture_manifest_summary, observation_summary
from studio.scene import HoudiniScene, validate_arguments
from test_capture import FakeHou


class Vector(tuple):
    def __new__(cls, values): return super().__new__(cls, values)
    def __mul__(self, matrix):
        return Vector(sum(self[j] * matrix[j * 4 + i] for j in range(3)) + matrix[12 + i] for i in range(3))
    def __neg__(self): return Vector(-v for v in self)
    def normalized(self):
        scale = math.sqrt(sum(v * v for v in self))
        return Vector(v / scale for v in self)


def identity_matrix():
    return (1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1)


class TargetCaptureTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1] / ".runtime" / "tc2-tests"
        root.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=root)
        self.addCleanup(self.temp.cleanup)
        self.hou = FakeHou()
        self.hou.Vector3 = Vector
        self.hou.geometryViewportType = NS(Perspective="Perspective")
        def transform():
            values = list(identity_matrix())
            values[14] = self.hou.viewport.defaultCamera().position
            return NS(asTuple=lambda: tuple(values))
        self.hou.viewport.viewTransform = transform
        self.hou.viewer.pwd = lambda: NS(path=lambda: "/obj", childTypeCategory=lambda: NS(name=lambda: "Object"))
        self.hou.viewer.isWorldSpaceLocal = lambda: False
        self.read_frames = []
        self.owner = NS(path=lambda: "/obj/asset", type=lambda: NS(category=lambda: NS(name=lambda: "Object")),
                        childTypeCategory=lambda: NS(name=lambda: "Sop"), worldTransform=identity_matrix,
                        isDisplayFlagSet=lambda: True)
        def geometry():
            self.read_frames.append(self.hou.frame())
            frame = self.hou.frame()
            return NS(intrinsicValue=lambda _: 8, boundingBox=lambda: NS(minvec=lambda: (frame, 0, 0), maxvec=lambda: (frame + 2, 3, 4)))
        self.target = NS(path=lambda: "/obj/asset/OUT", type=lambda: NS(category=lambda: NS(name=lambda: "Sop")),
                         parent=lambda: self.owner, geometry=geometry)
        self.owner.displayNode = lambda: self.target
        self.nodes = {self.target.path(): self.target, self.owner.path(): self.owner}
        self.hou.node = self.nodes.get
        self.selected = [self.target]
        self.hou.selectedNodes = lambda: self.selected
        self.scene = HoudiniScene(self.hou, Path(self.temp.name) / "artifacts")
        self.addCleanup(self.scene.close)

    def test_eight_corners_include_rotation_and_nonuniform_parent_scale(self):
        bounds = NS(minvec=lambda: (-1, -2, -3), maxvec=lambda: (1, 2, 3))
        matrix = (0, 2, 0, 0, -.5, 0, 0, 0, 0, 0, 3, 0, 8, 4, -3, 1)
        local, world = transformed_bounds(self.hou, bounds, matrix)
        self.assertEqual(world, [7, 2, -12, 9, 6, 6])
        self.assertEqual(local, [-1, -2, -3, 1, 2, 3])

    def test_selection_resolves_at_execution_and_bounds_use_requested_frame(self):
        args = {"purpose": "review", "target": {"selection": True}, "frame": 72, "resolution": [64, 64]}
        validate_schema(args, CAPTURE_SCHEMA)
        self.selected = [self.owner]
        outcome = self.scene.capture(args)
        self.assertEqual(outcome.state, "finished", outcome.detail)
        self.assertEqual(self.read_frames, [72])
        self.assertEqual(outcome.detail["target"]["resolved_paths"], ["/obj/asset"])
        self.assertEqual(outcome.detail["target"]["bounds"], [72, 0, 0, 74, 3, 4])
        self.assertEqual(self.hou.current_frame, self.hou.original_frame)
        self.assertEqual(self.selected, [self.owner])
        artifact = outcome.detail["artifact_id"]
        before = len(self.hou.used)
        self.assertTrue(self.scene.artifact(artifact).startswith(b"\x89PNG"))
        self.assertEqual(len(self.hou.used), before)

    def test_multiple_targets_and_non_display_warning_preserve_sources(self):
        other = NS(path=lambda: "/obj/asset/other", type=self.target.type, parent=lambda: self.owner,
                   geometry=lambda: NS(intrinsicValue=lambda _: 8,
                       boundingBox=lambda: NS(minvec=lambda: (-10, -2, -3), maxvec=lambda: (-5, 1, 2))))
        self.nodes[other.path()] = other
        outcome = self.scene.capture({"purpose": "review", "target": {"paths": [self.target.path(), other.path()]},
                                      "frame": 24, "resolution": [64, 64]})
        target = outcome.detail["target"]
        self.assertEqual(target["bounds"], [-10, -2, -3, 26, 3, 4])
        self.assertEqual(target["warnings"][0]["code"], "TARGET_NOT_DISPLAY_OUTPUT")
        self.assertIs(self.owner.displayNode(), self.target)
        self.assertFalse(target["visibility_verified"])

    def test_invalid_relations_reject_through_wire_before_runtime_access(self):
        bad = [{"target": {"selection": True}}, {"purpose": "review", "target": {"selection": 1}},
               {"purpose": "review", "target": {"paths": []}}, {"purpose": "review", "view": "front"},
               {"purpose": "review", "target": {"paths": ["/obj"]}, "bounds": [0, 0, 0, 1, 1, 1]},
               {"purpose": "diagnostic", "view": "right", "bounds": [0, 0, 0, 1, 1, 1]}]
        adapter = Adapter(None, None, {}, "owner", runtime_loader=lambda: self.fail("Invalid request reached runtime"))
        for args in bad:
            with self.subTest(args=args):
                with self.assertRaises(StudioError):
                    validate_arguments("capture", args)
                source = io.BytesIO((encoded({"id": 1, "method": "tools/call", "params": {"name": "hia_capture", "arguments": args}}) + "\n").encode())
                output = io.StringIO()
                serve_stdio(adapter, source, output)
                self.assertTrue(json.loads(output.getvalue())["result"]["isError"])

    def test_missing_empty_unsupported_space_or_fixed_named_view_never_captures(self):
        cases = [("missing", {"paths": ["/obj/missing"]}, "REVIEW_TARGET_MISSING"),
                 ("empty", {"paths": [self.target.path()]}, "REVIEW_EMPTY_GEOMETRY"),
                 ("space", {"paths": [self.target.path()]}, "REVIEW_SPACE_UNSUPPORTED"),
                 ("fixed", {"paths": [self.target.path()]}, "REVIEW_VIEW_UNSUPPORTED")]
        original_geo = self.target.geometry
        for mode, target, code in cases:
            self.target.geometry = original_geo
            self.hou.viewer.isWorldSpaceLocal = lambda: mode == "space"
            if mode == "empty":
                self.target.geometry = lambda: NS(intrinsicValue=lambda _: 0)
            self.hou.viewport.type = lambda: "Top" if mode == "fixed" else "Perspective"
            args = {"purpose": "review", "target": target, "resolution": [64, 64]}
            if mode == "fixed":
                args["view"] = "right"
            outcome = self.scene.capture(args)
            self.assertEqual(outcome.error["code"], code)
            self.assertEqual(self.hou.used, [])
            self.assertEqual(self.hou.current_frame, self.hou.original_frame)

    def test_large_capture_manifest_and_execute_summary_keep_receipt_facts_and_complete_ids(self):
        path = "/obj/" + "long_address/" * 3000
        metadata = capture_manifest_summary({"target": {"resolved_paths": [path]}, "requested_frame": 72,
            "actual_frame": 72, "capture_error": None, "restore_errors": []})
        self.assertLess(len(encoded(metadata).encode()), 16384)
        self.assertTrue(metadata["metadata_in_operation_detail"])
        detail = {"failure_phase": "script", "value_status": "partial_script_value",
            "value": {"huge": "x" * 50000}, "observe_after": {"status": "partial", "views": [
                {"index": 0, "path": path, "view": "node", "status": "ok", "type": "box", "warnings": ["text " * 10000]}]}}
        result = observation_summary("execute", detail)
        self.assertEqual(result["failure_phase"], "script")
        self.assertEqual(result["observe_after"]["views"][0]["path"], path)
        self.assertEqual(result["observe_after"]["views"][0]["type"], "box")
        self.assertTrue(result["detail_available"])

    def test_restore_preserves_inactive_ortho_width_with_h22_copy_semantics(self):
        class Camera:
            def __init__(self, position, width, perspective):
                self.position, self.width, self.perspective = position, width, perspective
            def orthoWidth(self): return self.width
            def isPerspective(self): return self.perspective
            def rotation(self): return NS(asTuple=lambda: (1, 0, 0, 0, 1, 0, 0, 0, 1))
            def translation(self): return (0, 0, self.position)
            def pivot(self): return (1000, 0, 0)
            def focalLength(self): return 50
            def aperture(self): return 41
            def setPerspective(self, value): self.perspective = value
            def setOrthoWidth(self, value):
                if not self.perspective:
                    self.width = value
        live, saved = Camera(42, 100, False), Camera(4, 6, True)
        viewport = self.hou.viewport
        viewport.view = live
        def copy_camera(value):
            live.position, live.perspective = value.position, value.perspective
            if not value.perspective:
                live.width = value.width
        viewport.setDefaultCamera = copy_camera
        matrix = list(identity_matrix())
        matrix[14] = 4
        detail = {"view": {}, "restore_errors": []}
        self.scene._restore_capture_view(viewport, None, saved, {"saved": saved}, False, matrix, "", detail, True)
        self.assertEqual(detail["restore_errors"], [])
        self.assertEqual((live.position, live.width, live.perspective), (4, 6, True))
        self.assertTrue(detail["view"]["restored"]["camera_components_match"])
        def wrong_pose(value):
            copy_camera(value)
            live.position += 1e-5
        viewport.setDefaultCamera = wrong_pose
        detail = {"view": {}, "restore_errors": []}
        self.scene._restore_capture_view(viewport, None, saved, {"saved": saved}, False, matrix, "", detail, True)
        self.assertFalse(detail["view"]["restored"]["camera_components_match"])
        self.assertEqual(detail["restore_errors"][0]["error"]["code"], "VIEW_RESTORE_MISMATCH")


if __name__ == "__main__":
    unittest.main()
