"""Focused static, backend, and native Qt checks; no real Houdini execution."""
import argparse
import os
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
root = Path(os.environ.get("HIA_PROJECT_ROOT") or Path(__file__).resolve().parents[1]).resolve()
sys.path.insert(0, str(root / "src"))

from studio.common import AppPaths  # noqa: E402
from studio.launcher import helper_environment, hidden_flags  # noqa: E402


_TEST_RUNNER = """
import faulthandler
import sys
import unittest
faulthandler.enable(all_threads=True)
if sys.platform == 'win32':
    import ctypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetErrorMode.restype = ctypes.c_uint
    kernel.SetErrorMode.argtypes = [ctypes.c_uint]
    kernel.SetErrorMode.restype = ctypes.c_uint
    # This isolated worker reports native faults through stderr/exit status,
    # without leaving a Windows error dialog blocking a background check.
    kernel.SetErrorMode(kernel.GetErrorMode() | 0x0002)  # SEM_NOGPFAULTERRORBOX
loader = unittest.TestLoader()
suite = unittest.TestSuite()
for pattern in sys.argv[1:]:
    suite.addTests(loader.discover('tests', pattern=pattern))
if not suite.countTestCases():
    raise SystemExit('No tests selected')
result = unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(0 if result.wasSuccessful() else 1)
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tests-only", action="store_true", help="Skip Ruff when only the stdlib is installed")
    parser.add_argument("--pattern", default="test_*.py", help="Select focused unittest files")
    parser.add_argument("--suite", choices=("backend", "ui", "all"), default="backend",
                        help="Default: backend. Native Qt files use test_ui*.py; excluded before import")
    args = parser.parse_args()
    paths = AppPaths(root)
    env = helper_environment(paths)
    env["RUFF_CACHE_DIR"] = str(paths.local("ruff"))
    if args.suite in {"ui", "all"}:
        env["QT_QPA_PLATFORM"] = "offscreen"
    patterns = [p.name for p in sorted((root / "tests").glob(args.pattern))
                if p.is_file() and (args.suite == "all" or
                                   p.name.startswith("test_ui") == (args.suite == "ui"))]
    if not patterns:
        parser.error("No test files match the requested suite and pattern")
    commands = []
    if not args.tests_only:
        commands.append([sys.executable, "-m", "ruff", "check", "src", "scripts", "tests"])
    commands.append([sys.executable, "-c", _TEST_RUNNER, *patterns])
    for command in commands:
        result = subprocess.run(command, cwd=paths.root, env=env, creationflags=hidden_flags(),
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                encoding="utf-8", errors="replace")
        print(result.stdout, end="", flush=True)
        if result.returncode:
            return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
