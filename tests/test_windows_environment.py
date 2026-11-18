"""Real Windows environment serialization, without Houdini, Qt or user state."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from studio.launcher import hidden_flags, houdini_host_environment


class WindowsEnvironmentTests(unittest.TestCase):
    def test_absent_keys_are_not_invented_and_non_windows_mapping_is_unchanged(self):
        for platform in ('nt', 'posix'):
            with self.subTest(platform=platform), patch.dict(os.environ, {'UNRELATED': 'same'}, clear=True), \
                    patch('os.name', platform):
                self.assertEqual(houdini_host_environment(), {'UNRELATED': 'same'})
        with patch.dict(os.environ, {'PATH': 'unchanged'}, clear=True), patch('os.name', 'posix'):
            self.assertEqual(houdini_host_environment(), {'PATH': 'unchanged'})

    @unittest.skipUnless(os.name == 'nt', 'Requires the real Win32 environment block')
    def test_real_child_retains_case_and_values_that_python_environ_hides(self):
        root = Path(__file__).resolve().parents[1]
        base = root / '.runtime/tests'
        base.mkdir(parents=True, exist_ok=True)
        # A source-equivalent model of the pinned Chromium allowlist/filter,
        # not a Chromium renderer or Houdini GUI acceptance test.
        renderer_keys = {'Path', 'SystemRoot', 'SystemDrive', 'TEMP', 'TMP',
                         'LOCALAPPDATA', 'CHROME_CRASHPAD_PIPE_NAME'}
        source = """
import json, os, runpy, sys
read = runpy.run_path(sys.argv[1])['raw_windows_environment']
initial = read()
normalized = {key: os.environ[key] for key in ('PATH', 'SYSTEMROOT', 'SYSTEMDRIVE')}
os.environ['PATH'] = 'python-added;' + os.environ['PATH']
print(json.dumps({'raw': initial, 'normalized': normalized, 'after_python_set': read()}))
"""
        with tempfile.TemporaryDirectory(prefix='raw-env ', dir=base) as temporary:
            environment = {'PATH': str(Path(temporary) / 'Qt 插件') + ';;native Qt;',
                           'SYSTEMROOT': os.environ['SYSTEMROOT'],
                           'SYSTEMDRIVE': os.environ['SYSTEMDRIVE'],
                           'TEMP': temporary, 'TMP': temporary, 'LOCALAPPDATA': temporary}
            with patch.dict(os.environ, environment, clear=True):
                corrected = houdini_host_environment()
            for label, candidate in (('old', environment), ('corrected', corrected)):
                with self.subTest(environment=label):
                    child = subprocess.run([sys.executable, '-I', '-S', '-B', '-c', source,
                                            str(root / 'scripts/inspect_houdini_help.py')],
                                           env=candidate, cwd=temporary, capture_output=True,
                                           text=True, encoding='utf-8', timeout=10,
                                           creationflags=hidden_flags(), check=True)
                    observed = json.loads(child.stdout)
                    self.assertTrue(observed['raw']['available'])
                    raw = {entry['name']: entry['value'] for entry in observed['raw']['entries']}
                    self.assertEqual(observed['normalized'], {key: environment[key] for key in
                                                             ('PATH', 'SYSTEMROOT', 'SYSTEMDRIVE')})
                    kept = {key: value for key, value in raw.items() if key in renderer_keys}
                    if label == 'old':
                        self.assertEqual(kept, {})
                    else:
                        self.assertEqual(kept, {key: environment[key.upper()] for key in
                                               ('Path', 'SystemRoot', 'SystemDrive')})
                    after = {entry['name']: entry['value'] for entry in
                             observed['after_python_set']['entries']}
                    # Updating a present key through Python does not erase its
                    # original spelling in the process's Win32 environment.
                    path_key = 'Path' if label == 'corrected' else 'PATH'
                    self.assertEqual(after.pop(path_key), 'python-added;' + environment['PATH'])
                    self.assertEqual(after, {key: value for key, value in raw.items() if key != path_key})


if __name__ == '__main__':
    unittest.main()
