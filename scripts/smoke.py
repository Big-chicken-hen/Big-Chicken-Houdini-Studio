"""Offline import/installation smoke. Does not start Houdini or request AI work."""
import argparse
import importlib
import json
import os
from pathlib import Path
import sqlite3
import sys

sys.dont_write_bytecode = True
root = Path(os.environ.get("HIA_PROJECT_ROOT") or Path(__file__).resolve().parents[1]).resolve()
sys.path.insert(0, str(root / "src"))

from studio.common import AppPaths, StudioError  # noqa: E402
from studio.launcher import check_codex, render_output_directory, storage_environment  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex", help="Optionally check the selected native executable's version")
    parser.add_argument("--ui", action="store_true", help="Check optional PySide6 availability without opening a window")
    args = parser.parse_args()
    paths = AppPaths(root)
    os.environ.update(storage_environment(paths))
    try:
        for name in ("common", "workspace", "ledger", "runtime", "scene", "runtime_server", "bridge", "mcp", "launcher"):
            importlib.import_module("studio." + name)
        connection = sqlite3.connect(":memory:")
        try:
            connection.execute("CREATE VIRTUAL TABLE documents USING fts5(body)")
        finally:
            connection.close()
        result = {"backend_imports": "passed", "sqlite_fts5": "available", "app_root": str(paths.root),
                  "render_output_directory": str(render_output_directory(paths)),
                  "houdini_gui": "not run", "codex_inference": "not run"}
        if args.ui:
            from PySide6 import __version__
            result["pyside6"] = __version__
        if args.codex:
            result["codex"] = check_codex(args.codex, paths)
            result["codex_version"] = "0.153.4"
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ImportError, OSError, sqlite3.DatabaseError, StudioError) as exc:
        print("Smoke failed: " + (exc.message if isinstance(exc, StudioError) else type(exc).__name__), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
