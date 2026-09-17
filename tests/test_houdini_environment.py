"""User search paths survive launcher hops; helpers and fixtures stay isolated."""
import os
from pathlib import Path
import runpy
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

from studio.common import AppPaths
from studio.launcher import child_environment, helper_environment, houdini_host_environment


class HoudiniEnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.source = Path(__file__).resolve().parents[1]
        base = self.source / '.runtime/tests'
        base.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix='host-env ', dir=base)
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / 'pyproject.toml').write_text('# fixture', encoding='utf-8')
        self.paths = AppPaths(self.root, user_houdini_preferences=True)
        self.search = {name: str(self.root / ('插件 paths/' + name)) + os.pathsep + '&'
                       for name in ('HOUDINI_PATH', 'HOUDINI_OTLSCAN_PATH', 'HOUDINI_OTL_PATH',
                                    'HOUDINI_OPLIBRARIES_PATH', 'HOUDINI_DSO_PATH')}
        self.search['HOUDINI_PACKAGE_DIR'] = str(self.root / 'extra packages') + os.pathsep + '$PIPELINE/packages'
        self.preferences = str(self.root / 'prefs/__HVER__')
        self.ambient = {**self.search, 'HOUDINI_USER_PREF_DIR': self.preferences,
                        'HFS': 'old Houdini', 'PYTHONHOME': 'old Python',
                        'PYTHONPATH': 'old source', 'QT_PLUGIN_PATH': 'old Qt',
                        'PYSIDE_DESIGNER_PLUGINS': 'old Qt', 'HIA_OLD_CONFIG': 'old project',
                        'FXHOUDINIMCP_URL': 'old service', 'BCS_SESSION_TOKEN': 'stale-fixture-only',
                        'HOUDINI_PACKAGE_SKIP': '1', 'HTTP_PROXY': 'http://127.0.0.1:54321',
                        'PATH': str(self.root / 'Qt 插件') + os.pathsep + os.pathsep + 'native Qt' + os.pathsep,
                        'SYSTEMROOT': 'C:\\Windows', 'SYSTEMDRIVE': 'C:'}

    def final_host(self):
        child = child_environment(AppPaths(), 'workspace', 'session', 'fresh-fixture-only')
        # The supervisor is another Python hop: an earlier re-spelling would
        # be lost here. Both bootstraps must reach the final host correction.
        with patch.dict(os.environ, child, clear=True):
            result = houdini_host_environment()
        for native in ('Path', 'SystemRoot', 'SystemDrive'):
            key = native if os.name == 'nt' else native.upper()
            self.assertEqual(result[key], self.ambient[native.upper()])
        return result

    def assert_host(self, environment):
        for name, value in self.search.items():
            if name != 'HOUDINI_PACKAGE_DIR':
                self.assertEqual(environment.get(name), value, name)
        self.assertEqual(environment['HOUDINI_PACKAGE_DIR'], self.search['HOUDINI_PACKAGE_DIR'] +
                         os.pathsep + str(self.root / 'houdini/packages'))
        self.assertEqual(environment['HOUDINI_USER_PREF_DIR'], self.preferences)
        self.assertEqual(environment['BCS_SESSION_TOKEN'], 'fresh-fixture-only')
        self.assertEqual(environment['HTTP_PROXY'], self.ambient['HTTP_PROXY'])
        for name in ('HFS', 'PYTHONHOME', 'QT_PLUGIN_PATH', 'PYSIDE_DESIGNER_PLUGINS',
                     'HIA_OLD_CONFIG', 'FXHOUDINIMCP_URL', 'HOUDINI_PACKAGE_SKIP'):
            self.assertNotIn(name, environment)
        self.assertEqual(environment['PYTHONPATH'], str(self.root / 'src'))

    def test_user_host_keeps_search_paths_but_helper_does_not(self):
        with patch.dict(os.environ, self.ambient, clear=True):
            before = dict(os.environ)
            helper = helper_environment(self.paths)
            for name in self.search:
                self.assertNotIn(name, helper)
            self.assert_host(child_environment(self.paths, 'workspace', 'session', 'fresh-fixture-only'))
            self.assertEqual(dict(os.environ), before)
        self.assertFalse((self.root / 'prefs').exists())

    def test_installed_bootstrap_preserves_search_paths_until_host_creation(self):
        entry = self.root / 'runtime/start_release.pyw'
        entry.parent.mkdir()
        shutil.copyfile(self.source / 'release/start_release.pyw', entry)

        observed = []
        def launcher_main(args):
            observed.append((args, os.environ['BCS_CODEX_PATH'],
                             self.final_host()))
            return 0

        with patch.dict(os.environ, {**self.ambient, 'BCS_DATA_ROOT': str(self.paths.data_root),
                                     'BCS_CACHE_ROOT': str(self.paths.cache_root)}, clear=True), \
                patch('studio.__main__.main', side_effect=launcher_main), \
                patch('ctypes.windll', create=True) as windows:
            runpy.run_path(str(entry))
        windows.user32.MessageBoxW.assert_not_called()
        self.assertEqual(len(observed), 1)
        self.assertEqual(observed[0][:2], (['launcher'], str(self.root / 'tools/codex/bin/codex.exe')))
        self.assert_host(observed[0][2])

    def test_development_bootstrap_preserves_search_paths_until_host_creation(self):
        observed = []
        def launcher_main(args):
            observed.append((args, self.final_host()))
            return 0

        with patch.dict(os.environ, {**self.ambient, 'HIA_PROJECT_ROOT': str(self.root),
                                     'BCS_DATA_ROOT': str(self.paths.data_root),
                                     'BCS_CACHE_ROOT': str(self.paths.cache_root)}, clear=True), \
                patch('studio.__main__.main', side_effect=launcher_main), \
                patch('sys.path', list(sys.path)), patch('ctypes.windll', create=True) as windows:
            entry = runpy.run_path(str(self.source / 'scripts/launch_window.pyw'))
            self.assertEqual(entry['start'](), 0)
        windows.user32.MessageBoxW.assert_not_called()
        self.assertEqual(len(observed), 1)
        self.assertEqual(observed[0][0], ['launcher'])
        self.assert_host(observed[0][1])

    def test_explicit_isolation_still_discards_user_plugin_paths(self):
        paths = AppPaths(self.root)
        with patch.dict(os.environ, self.ambient, clear=True):
            environment = child_environment(paths, 'workspace', 'session', 'fresh-fixture-only')
        for name in self.search:
            if name != 'HOUDINI_PACKAGE_DIR':
                self.assertNotIn(name, environment)
        self.assertEqual(environment['HOUDINI_PACKAGE_DIR'], str(self.root / 'houdini/packages'))
        self.assertEqual(environment['HOUDINI_USER_PREF_DIR'], str(paths.data('houdini-prefs', '__HVER__')))

    def test_reconstructed_child_does_not_duplicate_the_studio_package_directory(self):
        with patch.dict(os.environ, self.ambient, clear=True):
            first = child_environment(self.paths, 'workspace', 'session', 'fresh-fixture-only')
        with patch.dict(os.environ, first, clear=True):
            again = child_environment(AppPaths(), 'workspace', 'session-2', 'fresh-fixture-only')
        self.assert_host(again)


if __name__ == '__main__':
    unittest.main()
