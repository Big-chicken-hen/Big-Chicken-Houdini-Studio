"""HIP association and stable launch admission; no Houdini or Codex process."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from studio import launcher as launcher_module
from studio.common import AppPaths, StudioError, atomic_json, read_json
from studio.launcher import launch_status, launch_target
from studio.targets import SceneCatalog, SceneTarget
from studio.workspace import Workspaces


class SceneTargetTests(unittest.TestCase):
    def setUp(self):
        base = Path(__file__).resolve().parents[1] / ".runtime/tests"
        base.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / "pyproject.toml").write_text("# fixture", encoding="utf-8")
        self.paths = AppPaths(self.root)
        self.catalog = SceneCatalog(self.paths)
        self.a, self.b = self.root / "场景 A.hip", self.root / "Scene B.hiplc"
        self.a.touch()
        self.b.touch()
        self.checked = {"houdini": str(self.root / "houdini.exe"), "codex": str(self.root / "codex.exe"),
                        "codex_version": "0.153.4"}

    def record(self, workspace, path):
        return self.catalog.record_scene(workspace["workspace_id"], {"scene_epoch": "epoch",
            "saved_hip_path": str(path), "file_event": {"kind": "save", "autosave": False}}, "session")

    def launch(self, target, request_id="request"):
        return launch_target(self.paths, target, self.checked["houdini"], self.checked["codex"], request_id=request_id)

    def test_selecting_target_or_listing_recent_does_not_allocate_context(self):
        SceneTarget.hip(self.a)
        SceneTarget.empty()
        self.assertEqual(self.catalog.recent(), [])
        self.assertFalse(self.paths.runtime.exists())
        for invalid in ["https://example.com/A.hip", [str(self.a), str(self.b)], self.root, self.root / "gone.hip"]:
            with self.subTest(invalid=invalid), self.assertRaises(StudioError):
                SceneTarget.hip(invalid)

    def test_reopen_uses_association_but_empty_admissions_get_independent_identity(self):
        target = SceneTarget.hip(self.a)
        first = self.catalog.admit(target)
        second = self.catalog.admit(SceneTarget.hip(self.root / "." / self.a.name))
        self.assertEqual(first, second)
        self.assertEqual(self.catalog.recent(), [])  # Admission is not an opened-file fact.
        empty1, empty2 = self.catalog.admit(SceneTarget.empty()), self.catalog.admit(SceneTarget.empty())
        self.assertNotEqual(empty1["workspace_id"], empty2["workspace_id"])

    def test_save_as_and_recent_removal_preserve_identity_and_conflicts(self):
        workspace = self.catalog.admit(SceneTarget.empty())
        cwd = self.paths.workspace(workspace["workspace_id"]) / "work"
        self.record(workspace, self.a)
        self.record(workspace, self.b)
        self.assertEqual(self.catalog.admit(SceneTarget.hip(self.b)), workspace)
        self.assertTrue(cwd.is_dir())
        self.catalog.remove_recent(self.a)
        self.assertTrue(self.a.is_file())
        self.assertEqual(self.catalog.admit(SceneTarget.hip(self.a)), workspace)
        self.assertEqual([r["path"] for r in self.catalog.recent()], [str(self.b)])
        other = self.catalog.admit(SceneTarget.empty())
        conflict = self.record(other, self.b)
        self.assertEqual(conflict["status"], "conflict")
        self.assertEqual(self.catalog.admit(SceneTarget.hip(self.b)), workspace)

    def test_relocation_checks_existing_association_without_moving_files(self):
        first = self.catalog.admit(SceneTarget.hip(self.a))
        second = self.catalog.admit(SceneTarget.hip(self.b))
        self.record(first, self.a)
        with self.assertRaises(StudioError):
            self.catalog.relocate_recent(self.a, self.b)
        self.assertEqual(self.catalog.admit(SceneTarget.hip(self.b)), second)
        relocated = self.root / "Relocated.hip"
        relocated.touch()
        self.catalog.relocate_recent(self.a, relocated)
        self.assertEqual(self.catalog.admit(SceneTarget.hip(relocated)), first)
        self.assertTrue(self.a.exists())

    def test_launch_id_survives_lost_reply_without_another_process_or_empty_workspace(self):
        with patch("studio.launcher.preflight", return_value=self.checked), \
                patch("studio.launcher.subprocess.Popen", return_value=Mock(pid=11)) as spawn:
            first = self.launch(SceneTarget.empty())
            again = self.launch(SceneTarget.empty())
            self.assertEqual(first["session_id"], again["session_id"])
            self.assertEqual(spawn.call_count, 1)
            self.assertEqual(len(Workspaces(self.paths).list()), 1)
            with self.assertRaises(StudioError):
                self.launch(SceneTarget.hip(self.a))
            token = spawn.call_args.kwargs["env"]["BCS_SESSION_TOKEN"]
        for path in self.paths.session("request").iterdir():
            self.assertNotIn(token, path.read_text(encoding="utf-8"))

    def test_rejected_preflight_never_allocates_workspace_and_same_id_is_query_only(self):
        with patch("studio.launcher.preflight", side_effect=StudioError("CODEX_REQUIRED", "Choose Codex")) as check, \
                patch("studio.launcher.subprocess.Popen") as spawn:
            result = self.launch(SceneTarget.empty())
            self.launch(SceneTarget.empty())
        self.assertEqual((result["state"], result["process_may_exist"]), ("rejected", False))
        self.assertEqual(check.call_count, 1)
        spawn.assert_not_called()
        self.assertEqual(Workspaces(self.paths).list(), [])

    def test_spawn_close_or_return_loss_stays_unknown_and_same_id_never_spawns_again(self):
        original_spawn, original_open = launcher_module._spawn_session, Path.open

        def lose_return(*args, **kwargs):
            original_spawn(*args, **kwargs)
            raise OSError("Fixture lost the reply after Popen returned")

        class CloseFailure:
            def __init__(self, stream): self.stream = stream
            def __enter__(self): return self.stream
            def __exit__(self, *_args):
                self.stream.close()
                raise OSError("Fixture could not close the supervisor log")

        def open_with_close_failure(path, *args, **kwargs):
            stream = original_open(path, *args, **kwargs)
            return CloseFailure(stream) if path.name == "supervisor.log" else stream

        faults = {"close-loss": patch.object(Path, "open", open_with_close_failure),
                  "return-loss": patch.object(launcher_module, "_spawn_session", side_effect=lose_return)}
        for request_id, fault in faults.items():
            with self.subTest(fault=request_id), fault, \
                    patch("studio.launcher.preflight", return_value=self.checked), \
                    patch("studio.launcher.subprocess.Popen", return_value=Mock(pid=11)) as spawn:
                first = self.launch(SceneTarget.empty(), request_id)
                again = self.launch(SceneTarget.empty(), request_id)
                self.assertEqual((first["state"], again["state"]), ("unknown", "unknown"))
                self.assertTrue(first["process_may_exist"])
                self.assertTrue(again["process_may_exist"])
                self.assertEqual(spawn.call_count, 1)
        self.assertEqual(len(Workspaces(self.paths).list()), 2)
        with patch("studio.launcher.preflight", return_value=self.checked), \
                patch("studio.launcher.subprocess.Popen", side_effect=OSError("fixture executable missing")) as spawn:
            failed = self.launch(SceneTarget.empty(), "spawn-failed")
            self.launch(SceneTarget.empty(), "spawn-failed")
        self.assertEqual((failed["state"], failed["process_may_exist"]), ("rejected", False))
        self.assertEqual(spawn.call_count, 1)

    def test_registration_needs_matching_runtime_scene_and_closed_status_wins(self):
        with patch("studio.launcher.preflight", return_value=self.checked), \
                patch("studio.launcher.subprocess.Popen", return_value=Mock(pid=11)):
            result = self.launch(SceneTarget.hip(self.a))
        folder = self.paths.session("request")
        atomic_json(folder / "status.json", {"state": "starting", "houdini_pid": 42})
        descriptor = {"launcher_session_id": "request", "workspace_id": result["workspace_id"],
                      "houdini_pid": 42, "runtime_id": "runtime"}
        atomic_json(folder / "runtime.json", descriptor)
        self.assertEqual(launch_status(self.paths, "request")["state"], "runtime_connected")
        descriptor["scene"] = {"hip_path": str(self.b), "saved_hip_path": str(self.b), "is_new_file": False}
        atomic_json(folder / "runtime.json", descriptor)
        self.assertFalse(launch_status(self.paths, "request")["target_opened"])
        descriptor["scene"].update(hip_path=str(self.a), saved_hip_path=str(self.a))
        atomic_json(folder / "runtime.json", descriptor)
        self.assertTrue(launch_status(self.paths, "request")["target_opened"])
        atomic_json(folder / "status.json", {"state": "failed", "houdini_left_running": True})
        self.assertEqual(launch_status(self.paths, "request")["state"], "unknown")
        atomic_json(folder / "status.json", {"state": "closed"})
        self.assertFalse(launch_status(self.paths, "request")["process_may_exist"])
        self.assertEqual(read_json(folder / "launch.json")["workspace_id"], result["workspace_id"])


if __name__ == "__main__":
    unittest.main()
