"""File-event cache and output policy with a small HOM fixture, never Houdini."""
import contextlib
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from studio.common import AppPaths, StudioError
from studio.output import resolve_output
from studio.scene import HoudiniScene
from studio.targets import SceneCatalog, SceneTarget
from studio.workspace import Workspaces


class HipFixture:
    def __init__(self, path):
        self.filename, self.new = str(path), True
        self.callbacks = []

    def path(self): return self.filename
    def isNewFile(self): return self.new
    def hasUnsavedChanges(self): return False  # Clean is not proof of a saved file.
    def addEventCallback(self, callback): self.callbacks.append(callback)
    def removeEventCallback(self, callback): self.callbacks.remove(callback)


class SceneOutputTests(unittest.TestCase):
    def setUp(self):
        base = Path(__file__).resolve().parents[1] / ".runtime/tests"
        base.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / "pyproject.toml").write_text("# fixture", encoding="utf-8")
        self.paths = AppPaths(self.root)
        self.workspace = Workspaces(self.paths).create("File state fixture")["workspace_id"]
        self.hip = HipFixture(self.root / "untitled.hip")
        events = {name: name for name in ("BeforeLoad", "BeforeClear", "AfterLoad", "AfterClear", "AfterSave")}
        self.hou = SimpleNamespace(hipFile=self.hip, hipFileEventType=SimpleNamespace(**events),
            applicationVersionString=lambda: "22.0.fixture", frame=lambda: 1.0, isUIAvailable=lambda: True,
            expandString=lambda text: text.replace("$HIP", str(Path(self.hip.filename).parent)),
            undos=SimpleNamespace(group=lambda label: contextlib.nullcontext()))
        self.scene = HoudiniScene(self.hou, self.paths.workspace(self.workspace) / "artifacts",
                                   paths=self.paths, workspace_id=self.workspace, session_id="session")
        self.addCleanup(self.scene.close)

    def save(self, filename):
        path = self.root / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture HIP", encoding="utf-8")
        old = self.hip.filename
        self.hip.filename, self.hip.new = str(path), False
        self.scene._hip_event("AfterSave", old_hip_file=old, new_hip_file=str(path), autosave=False)
        return path

    def output(self, filename, write=False):
        script = f"result = output_path('export', {filename!r})"
        if write:
            script += "\nwith open(result, 'w', encoding='utf-8') as file: file.write('fixture output')"
        return self.scene.execute({"script": script}, lambda: False)

    def test_untitled_save_and_save_as_keep_workspace_epoch_and_old_outputs(self):
        epoch = self.scene.epoch
        first = self.output("temporary.txt", write=True)
        self.assertTrue(first.detail["resolved_outputs"][0]["temporary"])
        old_output = Path(first.detail["value"])
        a = self.save("A/asset.hip")
        formal = self.output("formal.txt")
        self.assertEqual(Path(formal.detail["value"]), a.parent / "BigChickenStudio/asset/exports/formal.txt")
        self.assertFalse(Path(formal.detail["value"]).exists())  # Resolution is not a completed file write.
        b = self.save("B/revised.hip")
        following = self.output("next.txt")
        self.assertEqual(Path(following.detail["value"]), b.parent / "BigChickenStudio/revised/exports/next.txt")
        self.assertEqual(self.scene.epoch, epoch)
        self.assertTrue(old_output.exists())
        self.assertEqual(SceneCatalog(self.paths).admit(SceneTarget.hip(b))["workspace_id"], self.workspace)

    def test_name_change_and_autosave_do_not_certify_a_user_save_as(self):
        original = self.save("original.hip")
        before = self.scene.cached()
        autosave = self.root / "autosave/recovery.hip"
        autosave.parent.mkdir()
        autosave.touch()
        self.hip.filename = str(autosave)
        self.scene._hip_event("AfterSave", old_hip_file=str(original), new_hip_file=str(autosave), autosave=True)
        self.assertEqual(self.scene.cached(), before)
        self.assertEqual([r["path"] for r in SceneCatalog(self.paths).recent()], [str(original)])
        self.hip.filename = str(self.root / "named-but-not-saved.hip")
        self.scene.refresh_cached()
        self.assertIsNone(self.scene.cached()["saved_hip_path"])
        result = self.output("new.txt")
        self.assertEqual(result.error["code"], "SCENE_FILE_STATE_UNKNOWN")

    def test_load_and_clear_advance_epoch_and_publish_cached_file_facts(self):
        self.save("initial.hip")
        events = []
        self.scene.file_publisher = events.append
        original_epoch = self.scene.epoch
        self.scene._hip_event("BeforeLoad")
        self.assertNotEqual(self.scene.epoch, original_epoch)
        self.assertIsNone(events[-1]["saved_hip_path"])
        loaded = self.root / "loaded.hip"
        loaded.touch()
        self.hip.filename, self.hip.new = str(loaded), False
        self.scene._hip_event("AfterLoad", new_hip_file=str(loaded))
        self.assertEqual(events[-1]["saved_hip_path"], str(loaded))
        loaded_epoch = self.scene.epoch
        self.scene._hip_event("BeforeClear")
        self.hip.filename, self.hip.new = str(self.root / "untitled.hip"), True
        self.scene._hip_event("AfterClear")
        self.assertNotEqual(self.scene.epoch, loaded_epoch)
        self.assertTrue(events[-1]["is_new_file"])
        self.assertEqual(events[-1]["association"]["status"], "unbound")

    def test_explicit_then_existing_output_wins_and_write_failure_has_no_cache_fallback(self):
        saved = self.save("work/asset.hip")
        state = self.scene.cached()
        explicit, existing = self.root / "chosen/result.exr", self.root / "node/output.exr"
        resolved = resolve_output(state, self.paths.cache("outputs"), "render", "default.exr",
                                  explicit=str(explicit), existing=str(existing))
        self.assertEqual(resolved["path"], str(explicit))
        resolved = resolve_output(state, self.paths.cache("outputs"), "render", "default.exr", existing=str(existing))
        self.assertEqual(resolved["path"], str(existing))
        with patch("studio.scene.Path.mkdir", side_effect=PermissionError("fixture permission failure")):
            outcome = self.output("blocked.txt")
        self.assertEqual(outcome.error["code"], "OUTPUT_DIRECTORY_UNWRITABLE")
        self.assertEqual(outcome.detail["resolved_outputs"][0]["source"], "hip")
        self.assertIn(str(saved.parent), outcome.detail["resolved_outputs"][0]["path"])
        with self.assertRaises(StudioError):
            resolve_output(state, self.paths.cache("outputs"), "export", "../escape.txt")


if __name__ == "__main__":
    unittest.main()
