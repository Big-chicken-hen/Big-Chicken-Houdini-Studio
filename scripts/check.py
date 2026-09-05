"""One static correctness check and the repository's small unittest set."""
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tests-only", action="store_true", help="Skip Ruff when only the stdlib is installed")
    parser.add_argument("--pattern", default="test_*.py", help="Select a focused unittest file")
    args = parser.parse_args()
    paths = AppPaths(root)
    env = helper_environment(paths)
    env["RUFF_CACHE_DIR"] = str(paths.local("ruff"))
    commands = []
    if not args.tests_only:
        commands.append([sys.executable, "-m", "ruff", "check", "src", "scripts", "tests"])
    commands.append([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", args.pattern, "-v"])
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
