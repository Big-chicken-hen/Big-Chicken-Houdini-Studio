"""Small shared protocol and project-local storage primitives."""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
import uuid
from pathlib import Path

PROTOCOL = 1
TERMINAL = frozenset({"finished", "failed", "cancelled", "rejected", "unknown"})


class StudioError(Exception):
    def __init__(self, code, message, status=400, **details):
        super().__init__(message)
        self.code, self.message, self.status, self.details = code, message, status, details

    def payload(self):
        return {"error": {"code": self.code, "message": self.message, **self.details}}


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,96}", value):
        raise StudioError("INVALID_ID", "Invalid identifier")
    return value


def new_id():
    return uuid.uuid4().hex


def encoded(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def payload_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     allow_nan=False, separators=(",", ":")).encode()).hexdigest()


def inside(path, root):
    target, base = Path(path).resolve(), Path(root).resolve()
    if target != base and base not in target.parents:
        raise StudioError("PATH_OUTSIDE_ROOT", "Internal storage must remain under the app root")
    return target


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + new_id() + ".tmp")
    with temporary.open("x", encoding="utf-8") as stream:
        stream.write(encoded(value))
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def now():
    return time.time()


class AppPaths:
    def __init__(self, root=None):
        self.root = Path(root or os.environ.get("HIA_PROJECT_ROOT") or
                         Path(__file__).resolve().parents[2]).resolve()
        if not (self.root / "pyproject.toml").is_file():
            raise StudioError("APP_ROOT_INVALID", "Select the Big-Chicken Studio installation directory")
        self.runtime = inside(self.root / ".runtime", self.root)

    def local(self, *parts):
        return inside(self.runtime.joinpath(*parts), self.root)

    def workspace(self, workspace_id):
        return self.local("workspaces", identifier(workspace_id))

    def session(self, session_id):
        return self.local("sessions", identifier(session_id))
