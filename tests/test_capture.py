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
from studio.scene import HoudiniScene


def png_bytes(width=64, height=64, rgb=(72, 104, 136)):
    def chunk(kind, payload):
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xffffffff)
    pixels = (b"\0" + bytes(rgb) * width) * height
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(pixels)) + chunk(b"IEND", b""))


class Settings:
    def __init__(self, values):
        self.values = dict(values)

    def stash(self):
        return Settings(self.values)

    def __getattr__(self, name):
        return lambda value: self.values.__setitem__(name, value)


class FakeHou:
    def __init__(self):
        self.current_frame, self.original_frame = 7.0, 7.0
        self.used, self.frame_calls = [], []
        self.capture_error = self.restore_error = False
        self.drift_before = self.drift_after = False
        self.output_bytes = None
        self.output_size = None
        self.original = Settings({"initializeSimulations": True, "useMotionBlur": True,
                                  "scopeChannelKeyframesOnly": True, "renderAllViewports": True,
                                  "gamma": 1.8, "lut": "existing-display-transform"})
        self.viewport = SimpleNamespace(size=lambda: (0, 0, 320, 180))
        self.viewer = SimpleNamespace(curViewport=lambda: self.viewport, flipbookSettings=lambda: self.original,
                                      flipbook=self.flipbook)
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
        if self.capture_error:
            raise RuntimeError("original capture failure")
        width, height = self.output_size or settings.values["resolution"]
        Path(settings.values["output"]).write_bytes(self.output_bytes if self.output_bytes is not None else png_bytes(width, height))
        if self.drift_after:
            self.current_frame += 1


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

    def test_stashed_settings_actual_png_dimensions_and_fractional_frame(self):
        original = dict(self.hou.original.values)
        outcome = self.capture()
        self.assertEqual((outcome.state, outcome.checks_outcome), ("finished", "passed"))
        result = outcome.detail
        self.assertEqual(result["requested_resolution"], [320, 180])
        self.assertEqual(result["actual_resolution"], [320, 180])
        self.assertEqual(result["resolution_source"], "viewport")
        self.assertEqual((result["requested_frame"], result["frame_before_capture"], result["actual_frame"]), (2.5, 2.5, 2.5))
        self.assertEqual(result["restored_frame"], 7)
        self.assertEqual(self.hou.original.values, original)
        for name in ("initializeSimulations", "useMotionBlur", "scopeChannelKeyframesOnly", "renderAllViewports",
                     "outputToMPlay", "useSheetSize", "cropOutMaskOverlay"):
            self.assertIs(self.hou.used[0][name], False)
        self.assertNotIn("$F", self.hou.used[0]["output"])
        self.assertEqual(png_dimensions(self.scene.artifact(result["artifact_id"])), (320, 180))
        self.assertNotIn("path", result)

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
