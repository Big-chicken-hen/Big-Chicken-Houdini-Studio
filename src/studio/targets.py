"""Scene selection and a small HIP-to-workspace index, independent of live HOM."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import os
from pathlib import Path
import re
import sqlite3

from .common import AppPaths, StudioError, identifier, now
from .workspace import Workspaces


def hip_path(value, *, must_exist=True):
    if not isinstance(value, (str, os.PathLike)) or not str(value).strip():
        raise StudioError("HIP_INVALID", "Choose one local Houdini scene file")
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", str(value)):
        raise StudioError("HIP_INVALID", "Choose a local file, not a URL")
    path = Path(value).expanduser().resolve()
    if path.suffix.lower() not in {".hip", ".hiplc", ".hipnc"} or (must_exist and not path.is_file()):
        raise StudioError("HIP_INVALID", "Choose an existing .hip, .hiplc or .hipnc file")
    return path


def path_key(path):
    return os.path.normcase(str(Path(path).resolve()))


@dataclass(frozen=True)
class SceneTarget:
    kind: str
    path: str | None = None

    def __post_init__(self):
        if self.kind == "hip":
            object.__setattr__(self, "path", str(hip_path(self.path)))
        elif self.kind != "empty" or self.path is not None:
            raise StudioError("SCENE_TARGET_INVALID", "Choose a HIP file or Start Empty")

    @classmethod
    def hip(cls, path):
        return cls("hip", path)

    @classmethod
    def empty(cls):
        return cls("empty")

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict) or set(value) - {"kind", "path"}:
            raise StudioError("SCENE_TARGET_INVALID", "Choose one scene target")
        return cls(value.get("kind"), value.get("path"))

    @property
    def hip_path(self):
        return self.path

    def to_dict(self):
        return {"kind": self.kind, "path": self.path}


class SceneCatalog:
    def __init__(self, paths):
        self.paths = paths
        self.path = paths.data("scene-index.sqlite")

    @contextmanager
    def _database(self, write=False):
        db = None
        try:
            if write:
                self.path.parent.mkdir(parents=True, exist_ok=True)
            db = sqlite3.connect(str(self.path) if write else self.path.as_uri() + "?mode=ro",
                                 uri=not write, timeout=0.25)
            if write:
                db.execute("PRAGMA synchronous=FULL")
                db.execute("CREATE TABLE IF NOT EXISTS hips (path_key TEXT PRIMARY KEY, path TEXT NOT NULL, "
                           "workspace_id TEXT NOT NULL, last_used REAL NOT NULL, visible INTEGER NOT NULL, event TEXT)")
                db.execute("CREATE TABLE IF NOT EXISTS scenes (workspace_id TEXT PRIMARY KEY, path TEXT, "
                           "scene_epoch TEXT, event TEXT, session_id TEXT, updated REAL NOT NULL)")
                db.execute("BEGIN IMMEDIATE")
            yield db
            if write:
                db.commit()
        except sqlite3.Error as exc:
            raise StudioError("SCENE_INDEX_UNAVAILABLE", "Scene history is unavailable; existing scene data was preserved", 503) from exc
        finally:
            if db is not None:
                db.close()

    def admit(self, target):
        """Called after launch preflight, never when a target is merely selected."""
        if not isinstance(target, SceneTarget):
            target = SceneTarget.from_dict(target)
        if target.kind == "empty":
            return Workspaces(self.paths).create("未保存场景")
        path = hip_path(target.path)
        with self._database(write=True) as db:
            row = db.execute("SELECT workspace_id FROM hips WHERE path_key=?", (path_key(path),)).fetchone()
            if row:
                return Workspaces(self.paths).get(row[0])
            workspace = Workspaces(self.paths).create(path.stem[:120] or path.name[:120])
            db.execute("INSERT INTO hips VALUES (?,?,?,?,?,?)", (path_key(path), str(path),
                       workspace["workspace_id"], now(), 0, "admitted"))
            return workspace

    def record_scene(self, workspace_id, snapshot, session_id=None):
        """Index a confirmed file event; never change an active workspace or ledger."""
        Workspaces(self.paths).get(workspace_id)
        path = snapshot.get("saved_hip_path")
        event = snapshot.get("file_event") or {}
        kind = event.get("kind", "observed")
        if event.get("autosave"):
            return {"status": "unchanged", "workspace_id": workspace_id}
        path = str(hip_path(path)) if path else None
        conflict = None
        with self._database(write=True) as db:
            if path:
                key = path_key(path)
                row = db.execute("SELECT workspace_id FROM hips WHERE path_key=?", (key,)).fetchone()
                if row and row[0] != workspace_id:
                    conflict = row[0]
                else:
                    db.execute("INSERT INTO hips VALUES (?,?,?,?,?,?) ON CONFLICT(path_key) DO UPDATE SET "
                               "path=excluded.path, last_used=excluded.last_used, visible=1, event=excluded.event",
                               (key, path, workspace_id, now(), 1, kind))
            db.execute("INSERT INTO scenes VALUES (?,?,?,?,?,?) ON CONFLICT(workspace_id) DO UPDATE SET "
                       "path=excluded.path, scene_epoch=excluded.scene_epoch, event=excluded.event, "
                       "session_id=excluded.session_id, updated=excluded.updated",
                       (identifier(workspace_id), path, snapshot.get("scene_epoch"), kind, session_id, now()))
        result = {"status": "conflict" if conflict else "associated" if path else "unbound", "workspace_id": workspace_id}
        if conflict:
            result["conflicting_workspace_id"] = conflict
        return result

    def recent(self, limit=20):
        if not self.path.is_file():
            return []
        with self._database() as db:
            rows = db.execute("SELECT path,workspace_id,last_used FROM hips WHERE visible=1 "
                              "ORDER BY last_used DESC LIMIT ?", (min(100, max(1, int(limit))),)).fetchall()
        return [{"path": path, "name": Path(path).name, "directory": str(Path(path).parent),
                 "last_used_at": used, "workspace_id": workspace_id, "missing": not Path(path).is_file()}
                for path, workspace_id, used in rows]

    def remove_recent(self, path):
        key = path_key(hip_path(path, must_exist=False))
        if not self.path.is_file():
            return {"removed": False}
        with self._database(write=True) as db:
            cursor = db.execute("UPDATE hips SET visible=0 WHERE path_key=?", (key,))
            return {"removed": bool(cursor.rowcount)}

    def relocate_recent(self, old_path, new_path):
        old = hip_path(old_path, must_exist=False)
        new = hip_path(new_path)
        with self._database(write=True) as db:
            row = db.execute("SELECT workspace_id FROM hips WHERE path_key=?", (path_key(old),)).fetchone()
            if not row:
                raise StudioError("SCENE_NOT_FOUND", "The previous scene association is no longer available", 404)
            other = db.execute("SELECT workspace_id FROM hips WHERE path_key=?", (path_key(new),)).fetchone()
            if other and other[0] != row[0]:
                raise StudioError("SCENE_CONTEXT_CONFLICT", "This file is already associated with another scene context", 409)
            db.execute("UPDATE hips SET visible=0 WHERE path_key=?", (path_key(old),))
            db.execute("INSERT INTO hips VALUES (?,?,?,?,?,?) ON CONFLICT(path_key) DO UPDATE SET "
                       "path=excluded.path, last_used=excluded.last_used, visible=1, event=excluded.event",
                       (path_key(new), str(new), row[0], now(), 1, "relocated"))
        return SceneTarget.hip(new)

    def legacy_workspaces(self):
        legacy = AppPaths.for_legacy(self.paths.root)
        return [{**entry, "data_root": str(legacy.data_root), "cache_root": str(legacy.cache_root),
                 "work_directory": str(legacy.workspace(entry["workspace_id"]) / "work"),
                 "codex_home": str(legacy.codex_home)}
                for entry in Workspaces(legacy).list()]
