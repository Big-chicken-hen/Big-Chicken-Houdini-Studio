"""Run the actual Windows EXE against a recording runtime in isolated roots."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


@unittest.skipUnless(sys.platform == 'win32', 'Windows executable entry')
class ReleaseEntryTests(unittest.TestCase):
    def test_development_and_package_resolve_their_own_runtime_from_another_cwd(self):
        root = Path(__file__).resolve().parents[1]
        base = root / '.runtime/release-entry-tests'
        base.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as temporary:
            folder = Path(temporary)
            source = folder / 'Recorder.cs'
            source.write_text('''using System;
using System.IO;
class Recorder {
    static void Main(string[] args) {
        File.WriteAllLines(Environment.GetEnvironmentVariable("STUDIO_ENTRY_RECORD"),
            new string[] {Environment.CurrentDirectory,
                Environment.GetEnvironmentVariable("HIA_PROJECT_ROOT"),
                Environment.GetEnvironmentVariable("BCS_DATA_ROOT"),
                Environment.GetEnvironmentVariable("BCS_CACHE_ROOT"),
                Environment.GetEnvironmentVariable("BCS_CODEX_PATH"),
                String.Join("|", args)});
    }
}''', encoding='utf-8')
            compiler = Path(os.environ['WINDIR']) / 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
            recorder = folder / 'Recorder.exe'
            subprocess.run([str(compiler), '/nologo', '/target:winexe', '/out:' + str(recorder), str(source)], check=True)
            for installed in (False, True):
                with self.subTest(installed=installed):
                    app = folder / ('安装 版本' if installed else '开发 目录')
                    runtime = app / ('runtime' if installed else '.runtime/venv/Scripts')
                    runtime.mkdir(parents=True)
                    (runtime / 'pythonw.exe').write_bytes(recorder.read_bytes())
                    entry = app / ('runtime/start_release.pyw' if installed else 'scripts/launch_window.pyw')
                    entry.parent.mkdir(parents=True, exist_ok=True)
                    entry.write_text('# recording fixture', encoding='utf-8')
                    if installed:
                        (app / 'release-manifest.json').write_text('{}', encoding='utf-8')
                    else:
                        codex = app / '.runtime/toolchains/codex/bin/codex.exe'
                        codex.parent.mkdir(parents=True)
                        codex.touch()
                    exe = app / 'Studio.exe'
                    subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                                    str(root / 'scripts/build_studio_entry.ps1'), '-Output', str(exe)], check=True)
                    record = folder / ('installed.txt' if installed else 'development.txt')
                    environment = dict(os.environ, STUDIO_ENTRY_RECORD=str(record), HIA_PROJECT_ROOT='stale-root',
                                       BCS_DATA_ROOT=str(folder / 'state'), BCS_CACHE_ROOT=str(folder / 'cache'))
                    subprocess.run([str(exe)], cwd=folder, env=environment, check=True, timeout=10)
                    lines = record.read_text(encoding='utf-8-sig').splitlines()
                    self.assertEqual(lines[:2], [str(app), str(app)])
                    self.assertEqual(lines[2:4], [str(folder / 'state'), str(folder / 'cache')] if installed else
                                     [str(app / '.runtime'), str(app / '.runtime/cache')])
                    if not installed:
                        self.assertEqual(lines[4], str(codex))
                    self.assertEqual(lines[5], ('-I|-B|' if installed else '-B|') + str(entry))
