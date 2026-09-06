"""Targeted capture integrity and durable-image tests; no real Houdini or Qt."""
import base64
import json
from pathlib import Path
import struct
import tempfile
from types import SimpleNamespace
import unittest
import zlib

from studio.artifacts import ArtifactStore, capture_resolution, png_dimensions
from studio.common import StudioError
from studio.mcp import Adapter
from studio.scene import HoudiniScene, validate_arguments


def png_bytes(width=64, height=64, rgb=(72, 104, 136)):
    def chunk(kind, payload):
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xffffffff)
    pixels = (b"\0" + bytes(rgb) * width) * height
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(pixels)) + chunk(b"IEND", b""))


class Settings:
    def __init__(self, values, round_range=False):
        self.values = dict(values)
        self.round_range = round_range

    def stash(self):
        return Settings(self.values, self.round_range)

    def frameRange(self, value=None):
        if value is not None:
            self.values["frameRange"] = tuple(round(item) for item in value) if self.round_range else value
        return self.values.get("frameRange")

    def __getattr__(self, name):
        return lambda value: self.values.__setitem__(name, value)


class ViewSettings:
    def __init__(self):
        self.guides = dict.fromkeys(("XYPlane", "XZPlane", "YZPlane", "OriginGnomon", "FloatingGnomon",
                                    "CurrentGeometry", "DisplayNodes", "TemplateGeometry"), True)
        self.ortho = True
        self.writes = []
        self.fail_restore = False

    def colorScheme(self): return "Light"
    def displayBackgroundImage(self): return True
    def displayEnvironmentBackgroundImage(self): return True
    def guideEnabled(self, guide): return self.guides[guide]
    def displayOrthoGrid(self): return self.ortho

    def setDisplayOrthoGrid(self, enabled):
        self.writes.append(("ortho_grid", enabled))
        self.ortho = enabled

    def enableGuide(self, guide, enabled):
        self.writes.append((guide, enabled))
        if self.fail_restore and guide == "XZPlane" and enabled:
            raise RuntimeError("guide restore failure")
        self.guides[guide] = enabled


class ViewCamera:
    def __init__(self, position=4.0, width=6.0):
        self.position, self.width = position, width

    def stash(self): return ViewCamera(self.position, self.width)
    def orthoWidth(self): return self.width


class Viewport:
    def __init__(self):
        self.options = ViewSettings()
        self.view = ViewCamera()
        self.camera_node = None
        self.locked = False
        self.extra = False
        self.node_writes = 0
        self.fail_default_restore = False
        self.fail_unlock = False
        self.framed = []

    def size(self): return (0, 0, 320, 180)
    def name(self): return "persp1"
    def type(self): return "Perspective"
    def settings(self): return self.options
    def camera(self): return self.camera_node
    def cameraPath(self): return self.camera_node.path() if self.camera_node else ""
    def isViewingThroughExtraCamera(self): return self.extra
    def isCameraLockedToView(self): return self.locked
    def defaultCamera(self): return self.camera_node.view if self.camera_node else self.view
    def draw(self): pass

    def lockCameraToView(self, value):
        if not value and self.fail_unlock:
            return
        self.locked = value

    def useDefaultCamera(self): self.camera_node = None
    def setCamera(self, camera): self.camera_node = camera

    def setDefaultCamera(self, saved):
        if self.camera_node and self.locked:
            self.node_writes += 1
        if self.fail_default_restore:
            raise RuntimeError("view restore failure")
        self.view = saved.stash()

    def viewTransform(self):
        return SimpleNamespace(asTuple=lambda: (self.defaultCamera().position,) + (0.0,) * 15)

    def frameBoundingBox(self, bounds):
        self.framed.append(bounds)
        if self.camera_node and self.locked:
            self.node_writes += 1
        self.defaultCamera().position = 42.0
        self.defaultCamera().width = 100.0


class FakeHou:
    def __init__(self):
        self.current_frame, self.original_frame = 7.0, 7.0
        self.used, self.frame_calls = [], []
        self.capture_error = self.restore_error = False
        self.drift_before = self.drift_after = self.round_capture = False
        self.output_bytes = None
        self.output_size = None
        self.original = Settings({"initializeSimulations": True, "useMotionBlur": True,
                                  "scopeChannelKeyframesOnly": True, "renderAllViewports": True,
                                  "gamma": 1.8, "lut": "existing-display-transform", "leaveFrameAtEnd": False})
        self.viewport = Viewport()
        self.viewportGuide = SimpleNamespace(**{key: key for key in self.viewport.options.guides})
        self.BoundingBox = lambda *bounds: tuple(bounds)
        self.plane_visible = True
        self.plane = SimpleNamespace(isVisible=lambda: self.plane_visible,
                                     setIsVisible=lambda value: setattr(self, "plane_visible", value))
        self.viewer = SimpleNamespace(curViewport=lambda: self.viewport, flipbookSettings=lambda: self.original,
                                      flipbook=self.flipbook, constructionPlane=lambda: self.plane)
        self.ui = SimpleNamespace(paneTabOfType=lambda kind: self.viewer)
        self.paneTabType = SimpleNamespace(SceneViewer="SceneViewer")
        self.hipFile = SimpleNamespace(path=lambda: "untitled.hip", hasUnsavedChanges=lambda: False,
            addEventCallback=lambda callback: None, removeEventCallback=lambda callback: None)

    def applicationVersionString(self):
        return "fake-capture-contract"

    def frame(self):
        if self.drift_before and self.current_frame != self.original_frame and not self.used:
            return self.current_frame + 1
        return self.current_frame

    def setFrame(self, value):
        self.frame_calls.append(value)
        if self.restore_error and value == self.original_frame:
            raise RuntimeError("restore failed independently")
        self.current_frame = value

    def flipbook(self, viewport, settings, open_dialog):
        assert viewport is self.viewport and open_dialog is False
        self.used.append(settings.values)
        self.captured_view = {"guides": dict(self.viewport.options.guides), "ortho": self.viewport.options.ortho,
                              "plane": self.plane_visible, "position": self.viewport.defaultCamera().position,
                              "camera": self.viewport.cameraPath()}
        if self.capture_error:
            raise RuntimeError("original capture failure")
        width, height = self.output_size or settings.values["resolution"]
        Path(settings.values["output"]).write_bytes(self.output_bytes if self.output_bytes is not None else png_bytes(width, height))
        frame_before = self.current_frame
        if self.round_capture:
            self.current_frame = round(self.current_frame)
        elif self.drift_after:
            self.current_frame += 1
        if not settings.values.get("leaveFrameAtEnd", False):
            self.current_frame = frame_before


class CaptureTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1] / ".runtime" / "tests"
        root.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix="capture 中文 ", dir=root)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.hou = FakeHou()
        self.scene = HoudiniScene(self.hou, self.root / "workspace" / "artifacts")
        self.addCleanup(self.scene.close)

    def capture(self, **arguments):
        return self.scene.capture({"frame": 2.5, **arguments})

    def test_diagnostic_default_preserves_view_and_review_restores_only_known_decorations(self):
        diagnostic = self.capture()
        self.assertEqual(diagnostic.detail["purpose"], "diagnostic")
        self.assertEqual(self.hou.viewport.options.writes, [])
        self.assertTrue(self.hou.captured_view["plane"])
        before = dict(self.hou.viewport.options.guides)
        review = self.capture(purpose="review", bounds=[-1, 0, -1, 1, 2, 1])
        self.assertEqual(review.state, "finished")
        self.assertEqual(self.hou.captured_view["position"], 42)
        self.assertFalse(self.hou.captured_view["plane"])
        self.assertFalse(self.hou.captured_view["ortho"])
        for name in ("XYPlane", "XZPlane", "YZPlane", "OriginGnomon", "FloatingGnomon"):
            self.assertFalse(self.hou.captured_view["guides"][name])
        for name in ("CurrentGeometry", "DisplayNodes", "TemplateGeometry"):
            self.assertTrue(self.hou.captured_view["guides"][name])
        self.assertEqual(self.hou.viewport.options.guides, before)
        self.assertTrue(self.hou.plane_visible)
        self.assertEqual(self.hou.viewport.view.position, 4)
        self.assertEqual(self.hou.viewport.view.width, 6)
        self.assertTrue(review.detail["view"]["restored"]["transform_matches"])
        self.assertTrue(review.detail["view"]["restored"]["ortho_width_matches"])
        self.assertTrue(all(r["restored"] == r["before"] for r in review.detail["display_adjustments"]))
        self.assertEqual(review.detail["background"], {"color_scheme": "Light", "images_enabled": True,
                         "environment_enabled": True, "horizon": "unclassified", "policy": "preserved"})

    def test_locked_camera_is_detached_and_rebound_without_camera_parameter_writes(self):
        vp = self.hou.viewport
        original = SimpleNamespace(path=lambda: "/obj/user_camera", view=ViewCamera(12, 8))
        vp.camera_node, vp.locked = original, True
        result = self.capture(purpose="review", bounds=[-1, 0, -1, 1, 2, 1])
        self.assertEqual(result.state, "finished")
        self.assertEqual(self.hou.captured_view["camera"], "")
        self.assertIs(vp.camera_node, original)
        self.assertEqual((vp.node_writes, original.view.position, original.view.width), (0, 12, 8))
        self.assertEqual((vp.view.position, vp.view.width), (4, 6))
        self.assertTrue(vp.locked)

        vp.fail_unlock = True
        vp.framed.clear()
        result = self.capture(purpose="review", bounds=[-1, 0, -1, 1, 2, 1])
        self.assertEqual(result.error["code"], "REVIEW_CAMERA_LOCKED")
        self.assertEqual(vp.framed, [])
        self.assertEqual(vp.node_writes, 0)
        self.assertTrue(all(vp.options.guides.values()))

    def test_review_restores_originally_disabled_guide_if_capture_changes_it(self):
        self.hou.viewport.options.guides["XYPlane"] = False
        original_flipbook = self.hou.viewer.flipbook
        def drift(*args, **kwargs):
            original_flipbook(*args, **kwargs)
            self.hou.viewport.options.guides["XYPlane"] = True
        self.hou.viewer.flipbook = drift
        outcome = self.capture(purpose="review")
        self.assertEqual(outcome.state, "finished")
        self.assertFalse(self.hou.viewport.options.guides["XYPlane"])
        self.assertEqual(outcome.detail["display_adjustments"][0],
                         {"setting": "XYPlane", "before": False, "during": False, "restored": False})

    def test_review_capture_and_each_restore_failure_keep_independent_evidence(self):
        self.hou.capture_error = True
        self.hou.viewport.fail_default_restore = True
        self.hou.viewport.options.fail_restore = True
        result = self.capture(purpose="review", bounds=[-1, 0, -1, 1, 2, 1])
        self.assertEqual(result.state, "failed")
        self.assertEqual(result.mutation_outcome, "unknown")
        self.assertIn("original capture failure", result.detail["capture_error"]["message"])
        phases = [e["phase"] for e in result.detail["restore_errors"]]
        self.assertIn("default_view", phases)
        self.assertIn("verify_view", phases)
        self.assertIn("XZPlane", phases)
        self.assertTrue(self.hou.viewport.options.guides["XYPlane"])
        self.assertTrue(self.hou.plane_visible)
        self.assertEqual(result.detail["restored_frame"], 7)

        self.hou.capture_error = False
        self.hou.viewport.options.guides["XZPlane"] = True
        result = self.capture(purpose="review")
        self.assertEqual(result.state, "failed")
        self.assertIsNone(result.detail["capture_error"])
        self.assertIn("artifact_id", result.detail)
        self.assertEqual(png_dimensions(self.scene.artifact(result.detail["artifact_id"])), (320, 180))

    def test_review_bounds_are_validated_before_view_changes(self):
        for arguments in ({"bounds": [-1, 0, -1, 1, 2, 1]},
                          {"purpose": "review", "bounds": [1, 0, 0, -1, 1, 1]},
                          {"purpose": "review", "bounds": [0] * 6},
                          {"purpose": "review", "bounds": [False, 0, 0, 1, 1, 1]},
                          {"purpose": "review", "bounds": [0, 0, 0, float("inf"), 1, 1]},
                          {"purpose": "review", "bounds": [0, 1]}, {"purpose": []}):
            with self.subTest(arguments=arguments), self.assertRaises(StudioError):
                validate_arguments("capture", arguments)
        self.hou.viewport.extra = True
        outcome = self.capture(purpose="review", bounds=[-1, 0, -1, 1, 2, 1])
        self.assertEqual(outcome.error["code"], "REVIEW_FRAMING_UNSUPPORTED")
        self.assertEqual(self.hou.viewport.options.writes, [])
        self.assertEqual(self.hou.used, [])

    def test_optional_arguments_cross_schema_adapter_router_runtime_and_scene(self):
        from studio.ledger import Ledger
        from studio.runtime import OperationRuntime
        from studio.runtime_server import runtime_router
        from urllib.parse import parse_qs, urlsplit

        class InstalledCamera:
            def setRotation(self, mat): pass
            setRotation.__annotations__ = {"mat": "Matrix3", "return": "void"}

        self.hou.GeometryViewportCamera = InstalledCamera
        dispatched, submitted = [], []
        def dispatch(callback):
            dispatched.append(True)
            return callback()
        runtime = OperationRuntime(Ledger(self.root / "route.sqlite"), self.scene, dispatch,
                                   workspace_id="workspace", session_id="session")
        self.addCleanup(runtime.close)
        route = runtime_router(runtime)
        def call(method, path, payload=None):
            parts = urlsplit(path)
            if method == "POST" and path == "/operations": submitted.append(payload)
            return route(method, parts.path, parse_qs(parts.query), payload or {})
        adapter = Adapter(SimpleNamespace(call=call), None,
                          {"workspace_id": "workspace", "runtime_id": runtime.runtime_id}, "owner")
        adapter.scene_epoch = self.scene.epoch  # Represents an existing explicit observation.
        lookup = adapter.call("hia_lookup", {"source": "hom", "symbol": "hou.GeometryViewportCamera",
                              "members": True, "query": "Rotation", "offset": 0, "limit": 1})
        info = json.loads(lookup["content"][0]["text"])
        self.assertIn("Matrix3", info["members"][0]["signature"])
        self.assertEqual(dispatched, [])  # Static metadata never invokes a HOM callback.
        arguments = {"purpose": "review", "bounds": [-1, 0, -1, 1, 2, 1],
                     "frame": 2.5, "resolution": [128, 96]}
        reply = adapter.call("hia_capture", arguments)
        receipt = json.loads(reply["content"][0]["text"])
        self.assertFalse(reply["isError"])
        self.assertEqual(submitted[0]["arguments"], arguments)
        self.assertEqual(receipt["result"]["view"]["bounds"], arguments["bounds"])
        self.assertEqual(receipt["result"]["actual_resolution"], [128, 96])
        self.assertEqual(receipt["scene_epoch"], self.scene.epoch)
        self.assertEqual(reply["content"][1]["type"], "image")
        self.assertEqual(len(dispatched), 1)
        self.assertEqual(runtime.get(receipt["operation_id"]), receipt)
        adapter.scene_epoch = "stale-observation"
        rejected = adapter.call("hia_capture", arguments)
        self.assertTrue(rejected["isError"])
        self.assertEqual(len(self.hou.used), 1)

    def test_stashed_settings_actual_png_dimensions_and_fractional_frame(self):
        original = dict(self.hou.original.values)
        outcome = self.capture()
        self.assertEqual((outcome.state, outcome.checks_outcome), ("finished", "passed"))
        result = outcome.detail
        self.assertEqual(result["requested_resolution"], [320, 180])
        self.assertEqual(result["actual_resolution"], [320, 180])
        self.assertEqual(result["resolution_source"], "viewport")
        self.assertEqual((result["requested_frame"], result["frame_before_capture"], result["actual_frame"]), (2.5, 2.5, 2.5))
        self.assertEqual(result["configured_frame_range"], [2.5, 2.5])
        self.assertEqual(result["restored_frame"], 7)
        self.assertIs(self.hou.used[0]["leaveFrameAtEnd"], True)
        self.assertEqual(self.hou.original.values, original)
        for name in ("initializeSimulations", "useMotionBlur", "scopeChannelKeyframesOnly", "renderAllViewports",
                     "outputToMPlay", "useSheetSize", "cropOutMaskOverlay"):
            self.assertIs(self.hou.used[0][name], False)
        self.assertNotIn("$F", self.hou.used[0]["output"])
        self.assertEqual(png_dimensions(self.scene.artifact(result["artifact_id"])), (320, 180))
        self.assertNotIn("path", result)

    def test_native_rounding_is_rejected_and_flipbook_cannot_hide_it_by_restoring_the_playbar(self):
        for rounding_at in ("configuration", "render"):
            with self.subTest(rounding_at=rounding_at):
                hou = FakeHou()
                hou.original.round_range = rounding_at == "configuration"
                hou.round_capture = rounding_at == "render"
                scene = HoudiniScene(hou, self.root / rounding_at)
                try:
                    outcome = scene.capture({"frame": 1.5})
                    self.assertEqual(outcome.state, "failed")
                    self.assertEqual(outcome.error["code"], "CAPTURE_FRAME_MISMATCH")
                    self.assertEqual(outcome.detail["requested_frame"], 1.5)
                    self.assertEqual(outcome.detail["restored_frame"], 7)
                    self.assertNotIn("artifact_id", outcome.detail)
                    self.assertIs(hou.original.values["leaveFrameAtEnd"], False)
                    if rounding_at == "configuration":
                        self.assertEqual(outcome.detail["configured_frame_range"], [2, 2])
                        self.assertEqual(hou.used, [])
                    else:
                        self.assertEqual(outcome.detail["configured_frame_range"], [1.5, 1.5])
                        self.assertEqual(outcome.detail["actual_frame"], 2)
                        self.assertIs(hou.used[0]["leaveFrameAtEnd"], True)
                finally:
                    scene.close()

    def test_default_resolution_preserves_viewport_aspect_and_explicit_size_needs_no_viewport_size(self):
        self.assertEqual(capture_resolution({}, SimpleNamespace(size=lambda: (0, 0, 4000, 2000))), (2560, 1280, "viewport"))
        self.assertEqual(capture_resolution({"resolution": [64, 96]}, object()), (64, 96, "requested"))
        with self.assertRaises(StudioError):
            capture_resolution({}, SimpleNamespace(size=lambda: (0, 0, 0, 0)))

    def test_frame_drift_is_not_reported_as_the_requested_frame(self):
        for field in ("drift_before", "drift_after"):
            with self.subTest(boundary=field):
                hou = FakeHou()
                setattr(hou, field, True)
                scene = HoudiniScene(hou, self.root / field)
                try:
                    outcome = scene.capture({"frame": 2.5})
                    self.assertEqual(outcome.state, "failed")
                    self.assertEqual(outcome.error["code"], "CAPTURE_FRAME_MISMATCH")
                    self.assertEqual(outcome.detail["restored_frame"], 7)
                    self.assertNotIn("artifact_id", outcome.detail)
                    self.assertEqual(len(hou.used), 0 if field == "drift_before" else 1)
                finally:
                    scene.close()

    def test_capture_and_restore_failures_remain_separate(self):
        self.hou.capture_error = self.hou.restore_error = True
        outcome = self.capture()
        self.assertEqual(outcome.state, "failed")
        self.assertEqual(outcome.mutation_outcome, "unknown")
        self.assertIn("original capture failure", outcome.error["message"])
        self.assertEqual(outcome.error, outcome.detail["capture_error"])
        self.assertEqual(outcome.detail["restore_errors"][0]["phase"], "set_frame")
        self.assertEqual(outcome.detail["restore_errors"][1]["phase"], "verify_frame")
        self.assertNotIn("artifact_id", outcome.detail)

    def test_resolution_mismatch_and_incomplete_file_cannot_register_an_image(self):
        for label, data, size in (("mismatch", None, (64, 64)), ("signature", b"\x89PNG\r\n\x1a\n", None),
                                  ("truncated", png_bytes(64, 64)[:-5], None)):
            with self.subTest(case=label):
                hou = FakeHou()
                hou.output_bytes, hou.output_size = data, size
                scene = HoudiniScene(hou, self.root / label)
                try:
                    outcome = scene.capture({"frame": 2.5})
                    self.assertEqual(outcome.state, "failed")
                    self.assertEqual(outcome.detail["restored_frame"], 7)
                    self.assertNotIn("artifact_id", outcome.detail)
                    self.assertEqual(list(scene.artifact_root.glob("*/manifest.json")), [])
                    if label == "mismatch":
                        self.assertEqual(outcome.detail["actual_resolution"], [64, 64])
                finally:
                    scene.close()

    def test_png_validator_rejects_corruption_and_header_only_impostors(self):
        valid = png_bytes()
        corrupted = bytearray(valid)
        corrupted[-5] ^= 1
        for value in (bytes(corrupted), valid[:33] + valid[-12:], valid + b"trailing"):
            with self.assertRaises(StudioError):
                png_dimensions(value)
        # A correct header and valid chunk CRCs cannot hide an invalid zlib payload.
        payload = b"not a zlib image"
        idat = struct.pack(">I", len(payload)) + b"IDAT" + payload + struct.pack(">I", zlib.crc32(b"IDAT" + payload) & 0xffffffff)
        with self.assertRaises(StudioError):
            png_dimensions(valid[:33] + idat + valid[-12:])

    def test_durable_reference_survives_new_scene_and_old_receipt_returns_native_image(self):
        created = self.capture()
        artifact_id = created.detail["artifact_id"]
        expected = self.scene.artifact(artifact_id)
        new_hou = FakeHou()
        new_scene = HoudiniScene(new_hou, self.scene.artifact_root)
        self.addCleanup(new_scene.close)
        requests = []
        def call(method, path):
            requests.append((method, path))
            return {"mime_type": "image/png", "data": base64.b64encode(new_scene.artifact(path.rsplit("/", 1)[-1])).decode()}
        adapter = Adapter(SimpleNamespace(call=call), None, {"runtime_id": "new-runtime"}, "new-owner")
        old_receipt = {"kind": "capture", "state": created.state, "runtime_id": "old-runtime",
                       "operation_id": "old-capture", "result": created.detail}
        content = adapter._receipt(old_receipt)
        self.assertFalse(content["isError"])
        self.assertEqual(base64.b64decode(content["content"][1]["data"]), expected)
        self.assertEqual(content["content"][1]["type"], "image")
        self.assertEqual(requests, [("GET", "/artifacts/" + artifact_id)])
        self.assertEqual(new_hou.used, [])
        self.assertIsNone(adapter.scene_epoch)

    def test_restore_failure_preserves_valid_png_and_missing_artifact_does_not_rewrite_receipt(self):
        self.hou.restore_error = True
        outcome = self.capture()
        self.assertEqual(outcome.state, "failed")
        self.assertIsNone(outcome.detail["capture_error"])
        self.assertIn("artifact_id", outcome.detail)
        def call(method, path):
            return {"mime_type": "image/png", "data": base64.b64encode(self.scene.artifact(path.rsplit("/", 1)[-1])).decode()}
        adapter = Adapter(SimpleNamespace(call=call), None, {}, "owner")
        reply = adapter._receipt({"kind": "capture", "state": outcome.state, "result": outcome.detail})
        self.assertTrue(reply["isError"])
        self.assertEqual(reply["content"][1]["type"], "image")
        receipt = {"kind": "capture", "state": "finished", "result": {"artifact_id": "0" * 32}}
        missing = adapter._receipt(receipt)
        self.assertTrue(missing["isError"])
        self.assertEqual(json.loads(missing["content"][0]["text"])["state"], "finished")
        self.assertEqual(json.loads(missing["content"][1]["text"])["error"]["code"], "ARTIFACT_NOT_FOUND")

    def test_artifact_id_boundary_uncommitted_files_and_changed_bytes(self):
        store = self.scene._artifacts
        for invalid in ("../image", "/absolute/path.png", "0" * 32 + "/image.png", "file.png"):
            with self.assertRaises(StudioError):
                store.read(invalid)
        artifact_id, image = store.allocate()
        image.write_bytes(png_bytes())
        with self.assertRaises(StudioError):
            store.read(artifact_id)
        store.commit(artifact_id, {"actual_frame": 1}, (64, 64))
        with self.assertRaises(StudioError):
            ArtifactStore(self.root / "different-workspace").read(artifact_id)
        image.write_bytes(png_bytes(rgb=(12, 34, 56)))
        with self.assertRaises(StudioError) as changed:
            store.read(artifact_id)
        self.assertEqual(changed.exception.code, "ARTIFACT_CHANGED")
