"""Workspace identity, explicit memory and opt-in local FTS; independent of Houdini."""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from contextlib import closing
from pathlib import Path

from .common import StudioError, atomic_json, identifier, new_id, now, read_json


class Workspaces:
    def __init__(self, paths):
        self.paths = paths

    def list(self):
        base = self.paths.data("workspaces")
        if not base.exists():
            return []
        values = []
        for path in base.glob("*/workspace.json"):
            try:
                value = read_json(path)
                self.get(value["workspace_id"])
                values.append(value)
            except (ValueError, OSError, KeyError, StudioError):
                continue
        return sorted(values, key=lambda v: v["created_at"], reverse=True)

    def create(self, name):
        if not isinstance(name, str) or not name.strip() or len(name) > 120:
            raise StudioError("INVALID_NAME", "Use a workspace name of 1 to 120 characters")
        workspace_id = new_id()
        directory = self.paths.workspace(workspace_id)
        directory.mkdir(parents=True, exist_ok=False)
        (directory / "work").mkdir()
        value = {"workspace_id": workspace_id, "name": name.strip(), "created_at": now(),
                 "work_directory": "work"}
        atomic_json(directory / "workspace.json", value)
        return value

    def get(self, workspace_id):
        path = self.paths.workspace(workspace_id) / "workspace.json"
        if not path.is_file():
            raise StudioError("WORKSPACE_NOT_FOUND", "Select or create a workspace", 404)
        value = read_json(path)
        if value.get("workspace_id") != workspace_id:
            raise StudioError("WORKSPACE_ID_MISMATCH", "Workspace identity does not match its directory", 409)
        return value


class WorkspaceData:
    def __init__(self, paths, workspace_id):
        Workspaces(paths).get(workspace_id)
        self.root = paths.workspace(workspace_id)
        self.workspace_id = workspace_id

    def memory(self, action, **args):
        path = self.root / "memory.sqlite"
        if action == "list" and not path.exists():
            return {"workspace_id": self.workspace_id, "records": []}
        with closing(sqlite3.connect(path, timeout=5)) as db, db:
            db.execute("CREATE TABLE IF NOT EXISTS memory (id TEXT PRIMARY KEY, body TEXT NOT NULL, "
                       "created REAL NOT NULL, supersedes TEXT, deleted INTEGER NOT NULL DEFAULT 0)")
            if action == "list":
                rows = db.execute("SELECT id,body,created,supersedes FROM memory WHERE deleted=0 "
                                  "AND id NOT IN (SELECT supersedes FROM memory WHERE supersedes IS NOT NULL) "
                                  "ORDER BY created DESC LIMIT 100").fetchall()
                return {"workspace_id": self.workspace_id, "records": [dict(zip(
                    ("id", "body", "created_at", "supersedes"), row)) for row in rows]}
            if action in {"record", "supersede"}:
                body = args.get("body", "")
                if not isinstance(body, str) or not body.strip() or len(body) > 12000:
                    raise StudioError("INVALID_MEMORY", "A decision must contain 1 to 12000 characters")
                previous = identifier(args.get("record_id")) if action == "supersede" else None
                if previous and not db.execute("SELECT 1 FROM memory WHERE id=? AND deleted=0", (previous,)).fetchone():
                    raise StudioError("MEMORY_NOT_FOUND", "Decision no longer exists", 404)
                record_id = new_id()
                db.execute("INSERT INTO memory VALUES (?,?,?,?,0)", (record_id, body.strip(), now(), previous))
                return {"id": record_id, "committed": True, "supersedes": previous}
            if action == "delete":
                cursor = db.execute("UPDATE memory SET deleted=1 WHERE id=?", (identifier(args.get("record_id")),))
                if not cursor.rowcount:
                    raise StudioError("MEMORY_NOT_FOUND", "Decision does not exist", 404)
                return {"deleted": True}
            raise StudioError("INVALID_ACTION", "Use list, record, supersede, or delete")

    def import_document(self, path, version, source):
        path = Path(path).resolve()
        if path.suffix.lower() not in {".txt", ".md", ".html", ".htm"} or path.stat().st_size > 4 * 1024 * 1024:
            raise StudioError("DOCUMENT_UNSUPPORTED", "Import a text, Markdown or HTML document below 4 MB")
        text = path.read_text(encoding="utf-8")
        digest = hashlib.sha256(text.encode()).hexdigest()
        with closing(sqlite3.connect(self.root / "documents.sqlite")) as db, db:
            db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS documents USING fts5(symbol, body, source UNINDEXED, "
                       "version UNINDEXED, content_hash UNINDEXED)")
            if not db.execute("SELECT 1 FROM documents WHERE content_hash=? AND source=? AND version=?",
                              (digest, source, version)).fetchone():
                for i in range(0, len(text), 4000):
                    db.execute("INSERT INTO documents VALUES (?,?,?,?,?)", (path.stem, text[i:i + 4000],
                                                                           source, version, digest))
        return {"imported": True, "content_hash": digest, "source": source, "version": version}

    def lookup(self, query, version=None):
        path = self.root / "documents.sqlite"
        if not path.exists():
            return {"available": False, "matches": [], "message": "No documents imported; live metadata remains available"}
        terms = re.findall(r"[\w.]+", str(query))[:12]
        if not terms:
            return {"available": True, "matches": []}
        match = " OR ".join('"' + term.replace('"', '""') + '"' for term in terms)
        try:
            with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
                clause, args = (" AND version=?", [match, str(version)]) if version else ("", [match])
                rows = db.execute("SELECT symbol,snippet(documents,1,'','', ' ... ',60),source,version,content_hash "
                                  "FROM documents WHERE documents MATCH ?" + clause + " ORDER BY rank LIMIT 6", args).fetchall()
                return {"available": True, "matches": [dict(zip(
                    ("symbol", "excerpt", "source", "version", "content_hash"), row)) for row in rows]}
        except sqlite3.DatabaseError:
            return {"available": False, "matches": [], "message": "Document index is unavailable; use live metadata or repair it explicitly"}

    def export_memory(self, path):
        # Explicit export only. No launch-time import, migration or automatic summarization.
        value = self.memory("list")
        target = Path(path)
        with target.open("x", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
        return {"path": str(target.resolve()), "records": len(value["records"])}
