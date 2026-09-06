"""Explicit product entry points. Non-GUI commands use only the standard library."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import __version__
from .common import AppPaths, StudioError, inside, read_json


def parser():
    root = argparse.ArgumentParser(prog="python -m studio", description="Big-Chicken Houdini Studio")
    root.add_argument("--version", action="version", version=__version__)
    root.add_argument("--app-root", help="Installation checkout; otherwise HIA_PROJECT_ROOT or this source tree")
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("launcher", help="Open the optional PySide6 launcher")
    supervisor = commands.add_parser("supervise", help="Internal: run with the launcher's session environment")
    supervisor.add_argument("--session", required=True)
    session = commands.add_parser("status", help="Read saved process status; not live scene health")
    session.add_argument("--session", required=True)
    start = commands.add_parser("launch", help="Explicitly start a new owned Houdini GUI session")
    start.add_argument("--workspace", required=True)
    start.add_argument("--houdini", required=True)
    start.add_argument("--codex", required=True)
    start.add_argument("--hip")
    workspaces = commands.add_parser("workspace", help="Manage local workspaces without Houdini")
    work = workspaces.add_subparsers(dest="action", required=True)
    work.add_parser("list")
    create = work.add_parser("create")
    create.add_argument("name")
    memory = commands.add_parser("memory", help="Explicit workspace decisions; no automatic memory")
    memory.add_argument("--workspace", required=True)
    decisions = memory.add_subparsers(dest="action", required=True)
    decisions.add_parser("list")
    for action in ("record", "supersede"):
        item = decisions.add_parser(action)
        text = item.add_mutually_exclusive_group(required=True)
        text.add_argument("--body")
        text.add_argument("--body-file", type=Path, help="UTF-8 text file")
        if action == "supersede":
            item.add_argument("--record-id", required=True)
    remove = decisions.add_parser("delete")
    remove.add_argument("--record-id", required=True)
    export = decisions.add_parser("export")
    export.add_argument("--output", type=Path, required=True, help="New JSON file below app root/.runtime")
    documents = commands.add_parser("document", help="Opt-in workspace text import and FTS lookup")
    documents.add_argument("--workspace", required=True)
    docs = documents.add_subparsers(dest="action", required=True)
    document = docs.add_parser("import")
    document.add_argument("path", type=Path)
    document.add_argument("--source", required=True)
    document.add_argument("--version", required=True)
    lookup = docs.add_parser("lookup")
    lookup.add_argument("query")
    lookup.add_argument("--version")
    return root


def run_launcher(paths):
    try:
        from PySide6 import QtWidgets
    except ImportError as exc:
        raise StudioError("UI_NOT_INSTALLED", "Launcher needs PySide6. Run Setup Studio.cmd or scripts/setup.ps1") from exc
    from .ui.launcher import StudioLauncher
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["Big-Chicken Houdini Studio"])
    app.setOrganizationName("Big-Chicken")
    app.setApplicationName("Houdini Studio")
    window = StudioLauncher(paths)
    window.show()
    return app.exec()


def dispatch(args, paths):
    if args.command == "launcher":
        return run_launcher(paths)
    if args.command in {"launch", "supervise"}:
        from .launcher import launch, supervise
        if args.command == "supervise":
            return supervise(paths, args.session)
        return launch(paths, args.workspace, args.houdini, args.codex, args.hip)
    if args.command == "status":
        return read_json(paths.session(args.session) / "status.json")
    from .workspace import WorkspaceData, Workspaces
    if args.command == "workspace":
        store = Workspaces(paths)
        return store.create(args.name) if args.action == "create" else {"workspaces": store.list()}
    data = WorkspaceData(paths, args.workspace)
    if args.command == "document":
        if args.action == "import":
            return data.import_document(args.path, args.version, args.source)
        return data.lookup(args.query, args.version)
    if args.action == "export":
        # Keep generated data under this installation; never overwrite a user file.
        output = inside(args.output if args.output.is_absolute() else paths.root / args.output, paths.runtime)
        output.parent.mkdir(parents=True, exist_ok=True)
        return data.export_memory(output)
    values = {}
    if hasattr(args, "body"):
        values["body"] = args.body_file.read_text(encoding="utf-8") if args.body_file else args.body
    if hasattr(args, "record_id"):
        values["record_id"] = args.record_id
    return data.memory(args.action, **values)


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        paths = AppPaths.for_user(args.app_root) if args.command == "launcher" else AppPaths(args.app_root)
        from .launcher import storage_environment
        os.environ.update(storage_environment(paths))
        result = dispatch(args, paths)
        if isinstance(result, int):
            return result
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except StudioError as exc:
        print(json.dumps(exc.payload(), ensure_ascii=False), file=sys.stderr)
        return 1
    except (OSError, ValueError) as exc:
        # Do not echo environment values or exception payloads into supervisor logs.
        print(json.dumps({"error": {"code": "LOCAL_DATA_ERROR", "message":
              "Could not read or write the selected local data", "type": type(exc).__name__}}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
