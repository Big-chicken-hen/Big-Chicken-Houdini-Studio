"""Shared protocol and separate install, persistent state and cache paths."""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
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
        raise StudioError("PATH_OUTSIDE_ROOT", "Internal storage must remain under its selected storage root")
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
    def __init__(self, root=None, *, data_root=None, cache_root=None):
        # Explicit installation roots retain the isolated development/legacy
        # default. The standalone launcher selects for_user() once; children
        # reconstruct the same roots from its controlled environment.
        explicit_root = root is not None
        self.root = Path(root or os.environ.get("HIA_PROJECT_ROOT") or
                         Path(__file__).resolve().parents[2]).resolve()
        if not (self.root / "pyproject.toml").is_file():
            raise StudioError("APP_ROOT_INVALID", "Select the Big-Chicken Studio installation directory")
        self.runtime = inside(self.root / ".runtime", self.root)
        data_root = data_root or (None if explicit_root else os.environ.get("BCS_DATA_ROOT")) or self.runtime
        cache_root = cache_root or (None if explicit_root else os.environ.get("BCS_CACHE_ROOT")) or self.runtime / "cache"
        if not Path(data_root).is_absolute() or not Path(cache_root).is_absolute():
            raise StudioError("STORAGE_ROOT_INVALID", "Choose absolute paths for user data and cache")
        self.data_root, self.cache_root = Path(data_root).resolve(), Path(cache_root).resolve()
        if self.data_root == self.cache_root or self.cache_root in self.data_root.parents:
            raise StudioError("STORAGE_ROOT_INVALID", "Persistent data cannot be inside disposable cache")

    @classmethod
    def for_user(cls, root=None):
        if os.environ.get("BCS_DATA_ROOT") and os.environ.get("BCS_CACHE_ROOT"):
            return cls(root, data_root=os.environ["BCS_DATA_ROOT"], cache_root=os.environ["BCS_CACHE_ROOT"])
        data, cache = user_storage_roots()
        return cls(root, data_root=os.environ.get("BCS_DATA_ROOT") or data,
                   cache_root=os.environ.get("BCS_CACHE_ROOT") or cache)

    @classmethod
    def for_legacy(cls, root):
        legacy = Path(root).resolve() / ".runtime"
        return cls(root, data_root=legacy, cache_root=legacy / "cache")

    def install(self, *parts):
        return inside(self.root.joinpath(*parts), self.root)

    def local(self, *parts):
        """Installation-local dependencies and development files, never user state."""
        return inside(self.runtime.joinpath(*parts), self.root)

    def data(self, *parts):
        return inside(self.data_root.joinpath(*parts), self.data_root)

    def cache(self, *parts):
        return inside(self.cache_root.joinpath(*parts), self.cache_root)

    @property
    def codex_home(self):
        return self.data("codex-home")

    def workspace(self, workspace_id):
        return self.data("workspaces", identifier(workspace_id))

    def session(self, session_id):
        return self.data("sessions", identifier(session_id))


def user_storage_roots():
    """Resolve platform locations without changing a host QApplication's identity."""
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        folder_id = ctypes.create_string_buffer(uuid.UUID("F1B32785-6FBA-4FCF-9D55-7B8E7F157091").bytes_le)
        value = ctypes.c_wchar_p()
        shell = ctypes.WinDLL("shell32", use_last_error=True)
        shell.SHGetKnownFolderPath.argtypes = [ctypes.c_void_p, wintypes.DWORD, wintypes.HANDLE,
                                              ctypes.POINTER(ctypes.c_wchar_p)]
        shell.SHGetKnownFolderPath.restype = ctypes.c_long
        result = shell.SHGetKnownFolderPath(folder_id, 0, None, ctypes.byref(value))
        if result != 0:
            raise StudioError("USER_STORAGE_UNAVAILABLE", "Windows could not locate local application data")
        try:
            base = Path(value.value) / "BigChickenStudio"
        finally:
            ole = ctypes.WinDLL("ole32")
            ole.CoTaskMemFree.argtypes = [ctypes.c_void_p]
            ole.CoTaskMemFree(value)
        return base / "state", base / "cache"
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/BigChickenStudio", Path.home() / "Library/Caches/BigChickenStudio"
    return (Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state") / "BigChickenStudio",
            Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "BigChickenStudio")
