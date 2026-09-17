"""Storage-role separation without touching real user profiles or native clients."""
import os
from pathlib import Path
import runpy
import sys
import tempfile
import unittest
from unittest.mock import patch

from studio.common import AppPaths, StudioError
from studio.launcher import child_environment, helper_environment
from studio.workspace import Workspaces


class StoragePathsTests(unittest.TestCase):
    def setUp(self):
        base = Path(__file__).resolve().parents[1] / ".runtime" / "tests"
        base.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.install = self.base / "install"
        self.install.mkdir()
        (self.install / "pyproject.toml").write_text("# fixture", encoding="utf-8")
        self.data, self.cache = self.base / "state", self.base / "cache"

    def test_explicit_fixture_root_ignores_ambient_user_profile(self):
        with patch.dict(os.environ, {"BCS_DATA_ROOT": str(self.data), "BCS_CACHE_ROOT": str(self.cache)}):
            paths = AppPaths(self.install)
        self.assertEqual(paths.workspace("fixture"), self.install / ".runtime/workspaces/fixture")
        self.assertFalse(self.data.exists())
        self.assertFalse(self.cache.exists())
        self.assertEqual(AppPaths.for_legacy(self.install).codex_home, paths.codex_home)

    def test_user_factory_resolves_roots_once_and_children_reconstruct_same_profile(self):
        with patch.dict(os.environ, {"BCS_DATA_ROOT": "", "BCS_CACHE_ROOT": "", "BCS_HOUDINI_PREF_MODE": ""}), \
                patch("studio.common.user_storage_roots", return_value=(self.data, self.cache)):
            paths = AppPaths.for_user(self.install)
        env = child_environment(paths, "workspace", "session", "test-only-credential")
        self.assertEqual(env["CODEX_HOME"], str(self.data / "codex-home"))
        self.assertEqual(Path(env["HOUDINI_TEMP_DIR"]), self.cache / "tmp")
        self.assertFalse("HOUDINI_USER_PREF_DIR" in env)
        with patch.dict(os.environ, env):
            child = AppPaths()
        self.assertEqual((child.root, child.data_root, child.cache_root), (paths.root, paths.data_root, paths.cache_root))
        self.assertEqual(child.session("session"), self.data / "sessions/session")
        self.assertEqual(paths.local("venv"), self.install / ".runtime/venv")

    def test_user_preferences_override_survives_bootstrap_and_supervisor_without_copying(self):
        preferences = self.base / '日常配置/__HVER__'
        with patch.dict(os.environ, {"BCS_DATA_ROOT": str(self.data), "BCS_CACHE_ROOT": str(self.cache),
                                     "BCS_HOUDINI_PREF_MODE": "", "HOUDINI_USER_PREF_DIR": str(preferences)}):
            paths = AppPaths.for_user(self.install)
            bootstrap = helper_environment(paths)
            with patch.dict(os.environ, bootstrap, clear=True):
                reconstructed = AppPaths()
                child = child_environment(reconstructed, 'workspace', 'session', 'test-only-credential')
            self.assertEqual(child['HOUDINI_USER_PREF_DIR'], str(preferences))
        self.assertFalse(preferences.parent.exists(), 'Never copy, create or rewrite user preferences')
        self.assertFalse((self.data / 'houdini-prefs').exists())

    def test_fixture_and_explicit_test_launcher_remain_isolated_under_user_environment(self):
        with patch.dict(os.environ, {"BCS_HOUDINI_PREF_MODE": "user", "HOUDINI_USER_PREF_DIR": "real-user-sentinel"}):
            fixture = AppPaths(self.install)
            env = child_environment(fixture, 'workspace', 'session', 'test-only-credential')
            self.assertEqual(Path(env['HOUDINI_USER_PREF_DIR']), self.install / '.runtime/houdini-prefs/__HVER__')
            with patch.dict(os.environ, env, clear=True):
                launcher = AppPaths.for_user(self.install)
                again = child_environment(launcher, 'workspace', 'session-2', 'test-only-credential')
                self.assertEqual(again['HOUDINI_USER_PREF_DIR'], env['HOUDINI_USER_PREF_DIR'])

    def test_each_root_keeps_its_own_containment_and_cache_cannot_own_data(self):
        paths = AppPaths(self.install, data_root=self.data, cache_root=self.cache)
        for resolver in (paths.install, paths.data, paths.cache):
            with self.subTest(resolver=resolver.__name__), self.assertRaises(StudioError):
                resolver("..", "outside")
        with self.assertRaises(StudioError):
            AppPaths(self.install, data_root=self.cache / "persistent", cache_root=self.cache)
        with self.assertRaises(StudioError):
            AppPaths(self.install, data_root="relative", cache_root=self.cache)

    def test_installation_change_keeps_workspace_and_codex_home_in_selected_state_root(self):
        first = AppPaths(self.install, data_root=self.data, cache_root=self.cache)
        workspace = Workspaces(first).create("Stored context")
        second_install = self.base / "another-install"
        second_install.mkdir()
        (second_install / "pyproject.toml").write_text("# fixture", encoding="utf-8")
        second = AppPaths(second_install, data_root=self.data, cache_root=self.cache)
        self.assertEqual(Workspaces(second).get(workspace["workspace_id"]), workspace)
        self.assertEqual(second.workspace(workspace["workspace_id"]), first.workspace(workspace["workspace_id"]))
        self.assertEqual(second.codex_home, first.codex_home)
        self.assertNotEqual(second.local("venv"), first.local("venv"))
        with patch.dict(os.environ, {"HIA_RENDER_OUTPUT_DIR": ""}):
            self.assertNotIn("HIA_RENDER_OUTPUT_DIR", helper_environment(second))

    def test_windowed_bootstrap_uses_explicit_user_cache_before_opening_ui(self):
        def launcher_main(args):
            self.assertEqual(args, ["launcher"])
            self.assertEqual(Path(os.environ["TEMP"]), self.cache / "tmp")
            self.assertEqual(Path(os.environ["CODEX_HOME"]), self.data / "codex-home")
            self.assertEqual(Path(sys.stderr.name), self.cache / "logs/launcher.log")
            print("Fixture reached the launcher entry")
            return 0

        script = Path(__file__).resolve().parents[1] / "scripts/launch_window.pyw"
        with patch.dict(os.environ, {"HIA_PROJECT_ROOT": str(self.install),
                                     "BCS_DATA_ROOT": str(self.data), "BCS_CACHE_ROOT": str(self.cache)}), \
                patch.object(sys, "path", list(sys.path)), patch("studio.__main__.main", side_effect=launcher_main):
            entry = runpy.run_path(str(script), run_name="bootstrap_fixture")
            self.assertEqual(entry["start"](), 0)
        self.assertIn("Fixture reached", (self.cache / "logs/launcher.log").read_text(encoding="utf-8"))
        self.assertEqual([path.name for path in self.install.iterdir()], ["pyproject.toml"])


if __name__ == "__main__":
    unittest.main()
