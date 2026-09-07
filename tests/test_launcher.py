"""Focused launch faults without Houdini, Qt, network access, or a user home write."""
from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from studio import launcher
from studio.__main__ import dispatch, parser
from studio.common import AppPaths, StudioError, atomic_json, read_json
from studio.workspace import Workspaces


class LauncherTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1]
        base = root / ".runtime" / "tests"
        base.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="launcher 空间 ", dir=base)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "pyproject.toml").write_text("[project]\nname='fixture'\n", encoding="utf-8")
        self.paths = AppPaths(self.root)
        self.workspace = Workspaces(self.paths).create("场景项目")["workspace_id"]
        self.houdini = self.root / "Houdini 安装" / "houdini.exe"
        self.houdini.parent.mkdir()
        self.houdini.touch()
        self.codex = self.root / "Codex 工具" / "codex.exe"
        self.codex.parent.mkdir()
        self.codex.touch()
        self.environ = patch.dict(os.environ, {}, clear=False)
        self.environ.start()
        self.addCleanup(self.environ.stop)
        os.environ.pop("HIA_RENDER_OUTPUT_DIR", None)

    def session(self):
        session_id = "test-session"
        folder = self.paths.session(session_id)
        folder.mkdir(parents=True)
        atomic_json(folder / "launch.json", {"launcher_session_id": session_id, "workspace_id": self.workspace,
                                            "houdini": str(self.houdini), "codex": str(self.codex)})
        os.environ.update(launcher.child_environment(self.paths, self.workspace, session_id, "test-secret-token"))
        return session_id, folder

    def test_child_environment_is_local_and_preserves_explicit_render_output(self):
        os.environ.update({"HIA_OLD_CONFIG": "obsolete", "FXHOUDINIMCP_URL": "obsolete",
                           "HOUDINI_PATH": "old plugin", "PYTHONPATH": "old source",
                           "HIA_RENDER_OUTPUT_DIR": "渲染 outputs"})
        env = launcher.child_environment(self.paths, self.workspace, "env-session", "fresh-token")
        self.assertEqual(env["HIA_RENDER_OUTPUT_DIR"], str((self.root / "渲染 outputs").resolve()))
        self.assertEqual(env["BCS_SESSION_TOKEN"], "fresh-token")
        self.assertNotIn("HIA_OLD_CONFIG", env)
        self.assertNotIn("FXHOUDINIMCP_URL", env)
        self.assertNotIn("HOUDINI_PATH", env)
        self.assertEqual(env["PYTHONPATH"], str(self.root / "src"))
        for key in ("CODEX_HOME", "TEMP", "TMP", "TMPDIR", "HOUDINI_USER_PREF_DIR", "XDG_CACHE_HOME"):
            self.assertIn(self.paths.runtime, Path(env[key]).parents)
        self.assertEqual(os.environ["HIA_OLD_CONFIG"], "obsolete")
        os.environ.pop("HIA_RENDER_OUTPUT_DIR")
        self.assertIsNone(launcher.render_output_directory(self.paths))

    def test_pythonw_uses_console_sibling_and_missing_console_is_an_error(self):
        pythonw = self.root / "pythonw.exe"
        pythonw.touch()
        with self.assertRaises(StudioError):
            launcher.console_python(pythonw)
        console = self.root / "python.exe"
        console.touch()
        self.assertEqual(launcher.console_python(pythonw), str(console))

    def test_native_app_server_enables_system_proxy_only_on_windows(self):
        for platform, flags in (("nt", ["--enable", "respect_system_proxy"]), ("posix", [])):
            with self.subTest(platform=platform), patch.object(launcher.os, "name", platform):
                self.assertEqual(launcher.codex_app_server_command(self.codex),
                                 [str(self.codex), *flags, "app-server"])

    def test_version_check_uses_isolated_environment_and_rejects_unverified_codex(self):
        with patch.object(launcher.subprocess, "run", return_value=Mock(stdout="codex-cli 0.153.4\n")) as run:
            value = launcher.preflight(str(self.houdini), str(self.codex), self.paths)
        self.assertEqual(value["codex_version"], "0.153.4")
        self.assertEqual(run.call_args.kwargs["env"]["CODEX_HOME"], str(self.paths.local("codex-home")))
        self.assertEqual(run.call_args.args[0], [str(self.codex), "--version"])
        with patch.object(launcher.subprocess, "run", return_value=Mock(stdout="codex-cli 9.9.9")):
            with self.assertRaisesRegex(StudioError, "requires Codex 0.153.4"):
                launcher.preflight(str(self.houdini), str(self.codex), self.paths)

    def test_launch_preserves_unicode_arguments_and_keeps_fresh_tokens_out_of_files(self):
        hip = self.root / "已有 场景.hiplc"
        hip.touch()
        checked = {"houdini": str(self.houdini), "codex": str(self.codex), "codex_version": "0.153.4"}
        with patch.object(launcher, "preflight", return_value=checked), \
                patch.object(launcher.subprocess, "Popen", return_value=Mock(pid=4321)) as popen, \
                patch("studio.workspace.WorkspaceData", side_effect=AssertionError("No index on launch")):
            first = launcher.launch(self.paths, self.workspace, str(self.houdini), str(self.codex), str(hip))
            second = launcher.launch(self.paths, self.workspace, str(self.houdini), str(self.codex))
        first_call, second_call = popen.call_args_list
        first_token = first_call.kwargs["env"]["BCS_SESSION_TOKEN"]
        self.assertNotEqual(first_token, second_call.kwargs["env"]["BCS_SESSION_TOKEN"])
        self.assertNotEqual(first["session_id"], second["session_id"])
        self.assertNotIn("pythonw.exe", first_call.args[0][0].lower())
        self.assertEqual(first_call.kwargs["creationflags"], launcher.hidden_flags())
        self.assertNotIn(first_token, str(first_call.args[0]))
        self.assertNotIn(first_token, str(first))
        folder = Path(first["directory"])
        self.assertEqual(read_json(folder / "launch.json")["hip"], str(hip))
        self.assertIsNone(first["render_output_directory"])
        for file in folder.iterdir():
            self.assertNotIn(first_token, file.read_text(encoding="utf-8"))

    def test_workspace_lock_rejects_second_owner_and_releases(self):
        path = self.paths.workspace(self.workspace) / "session.lock"
        first = launcher.WorkspaceLock(path)
        try:
            with self.assertRaises(StudioError):
                launcher.WorkspaceLock(path)
        finally:
            first.close()
        launcher.WorkspaceLock(path).close()

    def test_supervisor_checks_runtime_registration_and_closes_only_owned_bridge(self):
        session_id, folder = self.session()
        atomic_json(folder / "runtime.json", {"launcher_session_id": "wrong-session", "workspace_id": self.workspace,
                                             "houdini_pid": 88})
        process = Mock(pid=88, returncode=0)
        process.poll.side_effect = [None, 0]
        with patch("studio.bridge.Bridge") as bridge, patch.object(launcher.subprocess, "Popen", return_value=process), \
                patch.object(launcher.time, "sleep"), patch.object(launcher, "atomic_json", wraps=atomic_json) as write:
            result = launcher.supervise(self.paths, session_id)
        self.assertEqual(result, 0)
        self.assertNotIn("ready", [call.args[1].get("state") for call in write.call_args_list])
        self.assertEqual(read_json(folder / "status.json")["state"], "closed")
        bridge.return_value.close.assert_called_once()
        process.terminate.assert_not_called()
        process.kill.assert_not_called()

    def test_matching_registration_reports_connection_ready_before_process_exit(self):
        session_id, folder = self.session()
        atomic_json(folder / "runtime.json", {"launcher_session_id": session_id, "workspace_id": self.workspace,
                                             "houdini_pid": 88})
        process = Mock(pid=88, returncode=0)
        process.poll.return_value = None
        with patch("studio.bridge.Bridge"), patch.object(launcher.subprocess, "Popen", return_value=process), \
                patch.object(launcher, "atomic_json", wraps=atomic_json) as write:
            self.assertEqual(launcher.supervise(self.paths, session_id), 0)
        self.assertEqual([call.args[1]["state"] for call in write.call_args_list], ["starting", "ready", "closed"])

    def test_supervisor_failure_leaves_live_houdini_alone_and_redacts_error(self):
        session_id, folder = self.session()
        process = Mock(pid=88, returncode=None)
        process.poll.return_value = None
        with patch("studio.bridge.Bridge") as bridge, patch.object(launcher.subprocess, "Popen", return_value=process), \
                patch.object(launcher.time, "sleep", side_effect=RuntimeError("test-secret-token")):
            result = launcher.supervise(self.paths, session_id)
        self.assertEqual(result, 1)
        status = read_json(folder / "status.json")
        self.assertTrue(status["houdini_left_running"])
        self.assertNotIn("test-secret-token", str(status))
        bridge.return_value.close.assert_called_once()
        process.wait.assert_called_once()
        process.terminate.assert_not_called()
        process.kill.assert_not_called()

    def test_supervisor_requires_fresh_launcher_environment(self):
        session_id, folder = self.session()
        os.environ.pop("BCS_SESSION_TOKEN")
        with patch("studio.bridge.Bridge") as bridge:
            self.assertEqual(launcher.supervise(self.paths, session_id), 1)
        bridge.assert_not_called()
        self.assertEqual(read_json(folder / "status.json")["state"], "failed")

    def test_cli_memory_is_available_without_gui_or_documents_and_export_does_not_overwrite(self):
        args = parser().parse_args(["memory", "--workspace", self.workspace, "record", "--body", "单位：米"])
        self.assertTrue(dispatch(args, self.paths)["committed"])
        listed = dispatch(parser().parse_args(["memory", "--workspace", self.workspace, "list"]), self.paths)
        self.assertEqual(listed["records"][0]["body"], "单位：米")
        self.assertFalse((self.paths.workspace(self.workspace) / "documents.sqlite").exists())
        output = self.paths.local("exports", "decisions.json")
        args = parser().parse_args(["memory", "--workspace", self.workspace, "export", "--output", str(output)])
        dispatch(args, self.paths)
        with self.assertRaises(FileExistsError):
            dispatch(args, self.paths)
        args.output = self.root.parent / "outside.json"
        with self.assertRaises(StudioError):
            dispatch(args, self.paths)

    def test_launch_failure_has_saved_status_without_exception_environment(self):
        with patch.object(launcher, "preflight", return_value={"houdini": str(self.houdini), "codex": str(self.codex)}), \
                patch.object(launcher.subprocess, "Popen", side_effect=OSError("private details")):
            with self.assertRaises(StudioError):
                launcher.launch(self.paths, self.workspace, str(self.houdini), str(self.codex))
        status_files = list(self.paths.local("sessions").glob("*/status.json"))
        self.assertEqual(len(status_files), 1)
        self.assertEqual(read_json(status_files[0])["state"], "failed")
        self.assertNotIn("private details", status_files[0].read_text())


if __name__ == "__main__":
    unittest.main()
