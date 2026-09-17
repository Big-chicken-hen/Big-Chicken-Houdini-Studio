"""Explicit package diagnostics cannot include user material or escape the install."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest
from unittest.mock import patch
import zipfile

from studio.common import AppPaths, StudioError
from studio.release import export_diagnostics, local_identity


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        base = Path(__file__).resolve().parents[1] / '.runtime/release-tests'
        base.mkdir(parents=True, exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.install = self.root / '程序 安装'
        self.install.mkdir()
        (self.install / 'pyproject.toml').write_text('[project]', encoding='utf-8')
        self.paths = AppPaths(self.install, data_root=self.root/'state', cache_root=self.root/'cache')
        self.paths.data_root.mkdir()
        self.paths.cache_root.mkdir()
        self.secret = 'PRIVATE-CHAT-LOGIN-TOKEN-AND-HOM-SCRIPT'
        (self.paths.data_root/'auth.json').write_text(self.secret, encoding='utf-8')
        self.output = self.paths.cache_root/'unsaved-scene-output.hip'
        self.output.write_bytes(b'fixture-user-output')

    def manifest(self, files):
        (self.install/'release-manifest.json').write_text(json.dumps({'version':'0.1.0-rc.1',
            'build_id':'0.1.0-rc.1-' + 'a'*12, 'source_commit':'a'*40, 'files':files}),encoding='utf-8')

    def test_export_whitelist_and_tamper_report_preserve_user_state_and_outputs(self):
        asset = self.install/'payload.py'
        asset.write_bytes(b'original')
        self.manifest({'payload.py':hashlib.sha256(b'original').hexdigest()})
        asset.write_bytes(b'changed')
        snapshot = {'account':{'status':'signed_in','token':self.secret,'auth_url':self.secret},
                    'codex':{'state':'ready','version':'0.153.4','path':self.secret,'source':'bundled'},
                    'houdini':{'state':'found','version':'22.0.368','compatibility':{'status':'unknown'}},
                    'host':{'version':'22.0.400','compatibility':{'status':'untested'},
                            'application':'houdini','license_category':'Commercial','path':self.secret},
                    'chat':self.secret,'script':self.secret,
                    'environment':{'PASSWORD':self.secret}}
        target = self.root/'diagnostics.zip'
        export_diagnostics(self.paths, target, snapshot, failure={'code':'FIXTURE_FAILURE','message':self.secret}, phase='home')
        with zipfile.ZipFile(target) as archive:
            self.assertEqual(archive.namelist(), ['diagnostics.json'])
            raw = archive.read('diagnostics.json').decode('utf-8')
        self.assertNotIn(self.secret, raw)
        self.assertNotIn(str(self.paths.data_root), raw)
        report = json.loads(raw)
        self.assertEqual(report['package_integrity']['status'], 'mismatch')
        self.assertEqual(report['package_integrity']['changed_files'], 1)
        self.assertTrue(report['account_confirmed'])
        self.assertEqual(report['failure_code'], 'FIXTURE_FAILURE')
        self.assertEqual(report['build_id'], '0.1.0-rc.1-' + 'a'*12)
        self.assertEqual(report['codex_source'], 'bundled')
        self.assertEqual(report['houdini_version'], '22.0.368')
        self.assertEqual(report['houdini_running_version'], '22.0.400')
        self.assertEqual(report['houdini_compatibility'], 'unknown')
        self.assertEqual(report['houdini_running_compatibility'], 'untested')
        self.assertEqual(report['houdini_application'], 'houdini')
        self.assertEqual(report['houdini_license_category'], 'Commercial')
        self.assertIsNone(report['tool_counts'])
        self.assertEqual((self.paths.data_root/'auth.json').read_text(), self.secret)
        self.assertEqual(self.output.read_bytes(), b'fixture-user-output')
        with self.assertRaises(FileExistsError):
            export_diagnostics(self.paths, target, snapshot)

    def test_manifest_cannot_hash_a_file_outside_installation(self):
        self.manifest({'../state/auth.json':'0'*64})
        with self.assertRaises(StudioError) as failure:
            export_diagnostics(self.paths,self.root/'refused.zip',{})
        self.assertEqual(failure.exception.code,'PATH_OUTSIDE_ROOT')
        self.assertFalse((self.root/'refused.zip').exists())

    def test_development_export_does_not_open_or_scan_real_user_locations(self):
        with patch('os.scandir',side_effect=AssertionError('No directory scan permitted')):
            export_diagnostics(self.paths,self.root/'development.zip',{'account':{'status':'unknown'},
                'codex':{'version':self.secret,'source':self.secret},
                'houdini':{'compatibility':{'status':self.secret}},
                'host':{'version':self.secret,'application':self.secret,'license_category':self.secret,
                        'compatibility':{'status':self.secret}}},failure={'code':self.secret},phase=self.secret)
        with zipfile.ZipFile(self.root/'development.zip') as archive:
            value=json.loads(archive.read('diagnostics.json'))
        self.assertEqual(value['package_integrity']['status'],'development_checkout')
        self.assertFalse(value['account_confirmed'])
        self.assertIsNone(value['codex_version'])
        self.assertIsNone(value['failure_code'])
        self.assertIsNone(value['phase'])
        for key in ('build_id', 'codex_source', 'houdini_running_version', 'houdini_compatibility',
                    'houdini_running_compatibility', 'houdini_application', 'houdini_license_category'):
            self.assertIsNone(value[key])

    def test_local_identity_reads_only_bounded_manifest_metadata_without_integrity_or_discovery(self):
        self.manifest({'not-read.py': 'a'*64})
        with patch('studio.release.integrity', side_effect=AssertionError('No hashes during identity projection')), \
                patch('os.scandir', side_effect=AssertionError('No discovery during identity projection')):
            value = local_identity(self.paths)
        self.assertEqual(value['build_id'], '0.1.0-rc.1-' + 'a'*12)
        self.assertEqual(value['installation_root'], str(self.install))
        self.assertEqual(value['state_root'], str(self.paths.data_root))
        self.assertEqual(value['cache_root'], str(self.paths.cache_root))
        (self.install/'release-manifest.json').write_text('{invalid', encoding='utf-8')
        value = local_identity(self.paths)
        self.assertIsNone(value['build_id'])
        self.assertIsNone(value['source_commit'])

    def test_packaged_preflight_rejects_an_unsupported_houdini_major(self):
        from studio.launcher import preflight
        self.manifest({'pyproject.toml': '0'*64})
        executable = self.install / 'houdini.exe'
        executable.write_bytes(b'fixture, not an executable')
        with patch('studio.release.installed_houdini_version', return_value='21.0.123'), \
                patch('studio.launcher.check_codex', side_effect=AssertionError('Must reject incompatible Houdini first')):
            with self.assertRaises(StudioError) as failure:
                preflight(executable, 'unused-codex', self.paths)
        self.assertEqual(failure.exception.code, 'HOUDINI_UNSUPPORTED')

    @unittest.skipUnless(os.name == 'nt', 'Windows installer mutex')
    def test_installer_mutex_tracks_a_live_owned_process(self):
        import ctypes
        from ctypes import wintypes
        self.manifest({'pyproject.toml': '0'*64})
        code = ('from studio.common import AppPaths; import sys; '
                'AppPaths(sys.argv[1], data_root=sys.argv[2], cache_root=sys.argv[3]); '
                'print("LEASE_READY",flush=True); input()')
        process = subprocess.Popen([sys.executable, '-c', code, str(self.install), str(self.paths.data_root), str(self.paths.cache_root)],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            self.assertEqual(process.stdout.readline().strip(), 'LEASE_READY')
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel.OpenMutexW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
            kernel.OpenMutexW.restype = wintypes.HANDLE
            kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            handle = kernel.OpenMutexW(0x100000, False, 'Local\\BigChickenStudio.ReleaseInUse')
            self.assertTrue(handle, 'Installer must detect the running packaged process')
            kernel.CloseHandle(handle)
            process.communicate('\n', timeout=5)
            self.assertEqual(process.returncode, 0)
            # This test owns the only packaged lease in its isolated worker.
            handle = kernel.OpenMutexW(0x100000, False, 'Local\\BigChickenStudio.ReleaseInUse')
            if handle:
                kernel.CloseHandle(handle)
            self.assertFalse(handle, 'A normal exit must release the installer guard')
        finally:
            if process.poll() is None:
                process.terminate()
                process.communicate(timeout=5)
