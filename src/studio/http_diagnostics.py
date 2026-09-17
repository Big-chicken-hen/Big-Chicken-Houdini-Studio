"""Opt-in, bounded local transport facts. Never serialize HTTP content or secrets."""
from __future__ import annotations

import hashlib
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import threading
import time
import traceback


_ROUTES = frozenset({"/state", "/events", "/account", "/models", "/turn", "/turn/steer", "/stop",
                     "/reconcile", "/thread", "/thread/history", "/threads", "/threads/select",
                     "/operations", "/attachments", "/selection", "/memory", "/requests/respond",
                     "/account/login", "/account/login/cancel", "/account/logout"})
_logs = {}
_logs_lock = threading.Lock()


def route_label(path):
    path = path.split("?", 1)[0] if isinstance(path, str) else ""
    if path in _ROUTES:
        return path
    for prefix in ("/operations/", "/threads/", "/artifacts/"):
        if path.startswith(prefix):
            return prefix + "<id>"
    return "<other>"


def message_fingerprint(body):
    value = body.get("client_user_message_id") if isinstance(body, dict) else None
    return hashlib.sha256(value.encode()).hexdigest()[:24] if isinstance(value, str) and len(value) <= 128 else None


def exception_facts(error):
    # No exception message, source lines, locals, full filenames or chained errors.
    frames = []
    source = Path(__file__).resolve().parent
    for frame, line in traceback.walk_tb(error.__traceback__):
        path = Path(frame.f_code.co_filename)
        try:
            filename = path.relative_to(source).as_posix()
        except ValueError:
            filename = "<external>"
        frames.append({"file": filename, "function": frame.f_code.co_name[:80], "line": line})
    return {"exception_type": type(error).__name__, "errno": getattr(error, "errno", None),
            "winerror": getattr(error, "winerror", None), "stack": frames[-12:]}


class HttpDiagnostics:
    """A shared sink per process/cache root; at most two 256 KiB files per process."""
    window_seconds = 30
    session_seconds = 15 * 60

    @classmethod
    def enabled(cls, paths):
        try:
            marker = paths.cache("diagnostics", "http-trace.enabled")
            if not marker.is_file():
                return None
            expires_at = marker.stat().st_mtime + cls.session_seconds
            if time.time() >= expires_at:
                return None
            with _logs_lock:
                key = (os.getpid(), str(marker.parent))
                if key not in _logs or time.time() >= _logs[key].expires_at:
                    if key in _logs:
                        _logs[key].handler.close()
                    _logs[key] = cls(marker.parent, expires_at=expires_at)
                return _logs[key]
        except OSError:
            return None  # A diagnostic location must never prevent normal startup.

    def __init__(self, directory, *, max_bytes=256 * 1024, expires_at=None):
        directory.mkdir(parents=True, exist_ok=True)
        self.expires_at = expires_at if expires_at is not None else time.time() + self.session_seconds
        self.handler = RotatingFileHandler(directory / f"panel-http-{os.getpid()}.jsonl",
                                           maxBytes=max_bytes, backupCount=1, encoding="utf-8")
        self.handler.setFormatter(logging.Formatter("%(message)s"))
        self.lock = threading.Lock()
        self.counters = {}
        self.window_start = time.monotonic()
        self._write({"kind": "identity", "diagnostic_version": 1,
                     "module_path": str(Path(__file__).resolve()),
                     "shared_path": str(Path(__file__).parent / "ui" / "shared.py"),
                     "panel_path": str(Path(__file__).parent / "ui" / "panel.py")})

    def _write(self, value):
        if time.time() >= self.expires_at:
            return
        try:
            data = json.dumps({"time_unix": time.time(), "pid": os.getpid(), **value}, ensure_ascii=True)
            self.handler.emit(logging.LogRecord("studio.local_http", logging.INFO, "", 0, data, (), None))
        except Exception:
            pass  # Collection failure cannot change a request's classification.

    def started(self, route):
        with self.lock:
            row = self.counters.setdefault(route, {"started": 0, "completed": 0, "failed": 0,
                                                   "cancelled": 0, "inflight": 0, "peak": 0})
            row["started"] += 1
            row["inflight"] += 1
            row["peak"] = max(row["peak"], row["inflight"])

    def finished(self, facts, *, failed, cancelled):
        with self.lock:
            row = self.counters[facts["route"]]
            row["completed"] += 1
            row["failed"] += int(failed)
            row["cancelled"] += int(cancelled)
            row["inflight"] -= 1
            if failed:
                self._write({"kind": "failure", **facts})
            elapsed = time.monotonic() - self.window_start
            if elapsed >= self.window_seconds:
                self._write({"kind": "window", "duration_seconds": round(elapsed, 3), "routes": self.counters})
                for row in self.counters.values():
                    row.update(started=0, completed=0, failed=0, cancelled=0, peak=row["inflight"])
                self.window_start = time.monotonic()
