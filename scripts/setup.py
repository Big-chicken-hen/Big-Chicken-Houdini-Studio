"""Explicit installation only. Nothing here is imported by the daily launcher."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import venv

sys.dont_write_bytecode = True
APP_ROOT = Path(os.environ.get("HIA_PROJECT_ROOT") or Path(__file__).resolve().parents[1]).resolve()
sys.path.insert(0, str(APP_ROOT / "src"))

from studio.common import AppPaths, StudioError, atomic_json  # noqa: E402
from studio.launcher import helper_environment, hidden_flags  # noqa: E402


def setup(args):
    paths = AppPaths(APP_ROOT)
    env = helper_environment(paths)
    # venv/ensurepip uses this process's temporary directory too.
    os.environ.update(env)
    tempfile.tempdir = str(paths.local("tmp"))
    target = paths.local("venv")
    executable = target / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not executable.is_file():
        if (target / "pyvenv.cfg").exists():
            raise StudioError("VENV_INCOMPLETE", "Existing venv has no Python; preserve it and repair it explicitly")
        venv.EnvBuilder(with_pip=True).create(target)
    extras = []
    if not args.backend_only:
        extras.append("ui")
    if args.dev:
        extras.append("dev")
    pip_args = [str(executable), "-m", "pip", "--disable-pip-version-check", "install"]
    if args.no_index:
        pip_args.append("--no-index")
    if args.find_links:
        pip_args.extend(["--find-links", str(Path(args.find_links).resolve())])
    # Build metadata, wheels and temporary sources stay below .runtime, including
    # setuptools' egg-info. Install from a staging copy, never from the user's src.
    with tempfile.TemporaryDirectory(prefix="setup-", dir=paths.local("tmp")) as staging:
        source = Path(staging)
        for filename in ("pyproject.toml", "README.md", "LICENSE"):
            shutil.copy2(paths.root / filename, source / filename)
        shutil.copytree(paths.root / "src", source / "src", ignore=shutil.ignore_patterns("__pycache__", "*.egg-info"))
        requirement = str(source) + ("[" + ",".join(extras) + "]" if extras else "")
        print("Installing Studio into " + str(target) + " ...", flush=True)
        installed = subprocess.run([*pip_args, requirement], cwd=paths.root, env=env,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                   encoding="utf-8", errors="replace", creationflags=hidden_flags())
        print(installed.stdout, end="", flush=True)
        installed.check_returncode()
    probe = subprocess.run([str(executable), "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"],
                           cwd=paths.root, env=env, text=True, capture_output=True, check=True,
                           creationflags=hidden_flags())
    site = Path(probe.stdout.strip()).resolve()
    if target.resolve() not in site.parents:
        raise StudioError("VENV_INVALID", "Python did not report a project-local installation directory")
    # Always run the current checkout, and calculate its location relative to this
    # venv so moving the app does not bake an old source path into the launcher.
    (site / "big_chicken_source.pth").write_text(
        'import os, sys; sys.path.insert(0, os.path.abspath(os.path.join(sys.prefix, "..", "..", "src")))\n',
        encoding="utf-8")
    result = {"installed": True, "python": str(executable), "extras": extras,
              "codex_version": "0.153.4", "app_root": str(paths.root),
              "render_output_directory": env["HIA_RENDER_OUTPUT_DIR"]}
    atomic_json(paths.local("setup.json"), result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def main():
    parser = argparse.ArgumentParser(description="Install Studio once into this checkout's .runtime/venv")
    parser.add_argument("--backend-only", action="store_true", help="Skip the optional PySide6 launcher")
    parser.add_argument("--dev", action="store_true", help="Install the small Ruff static checker")
    parser.add_argument("--no-index", action="store_true", help="Install only from a local wheel directory")
    parser.add_argument("--find-links", help="Local dependency wheels, including setuptools")
    args = parser.parse_args()
    try:
        return setup(args)
    except (StudioError, OSError, subprocess.SubprocessError) as exc:
        message = exc.message if isinstance(exc, StudioError) else "Setup failed; inspect the installer output above"
        print(message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
