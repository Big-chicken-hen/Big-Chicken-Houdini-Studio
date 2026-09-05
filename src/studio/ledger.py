"""Runtime-owned durable receipts. A GET never invokes an operation."""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

from .common import StudioError, encoded, now, payload_hash


class Ledger:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("CREATE TABLE IF NOT EXISTS operations (id TEXT PRIMARY KEY, hash TEXT NOT NULL, "
                        "receipt TEXT NOT NULL, detail TEXT)")
        self.db.commit()

    def accept(self, op):
        digest = payload_hash({key: value for key, value in op.items() if key != "operation_id"})
        with self.lock, self.db:
            row = self.db.execute("SELECT hash,receipt FROM operations WHERE id=?",
                                  (op["operation_id"],)).fetchone()
            if row:
                if row[0] != digest:
                    raise StudioError("OPERATION_ID_CONFLICT", "This operation ID belongs to another payload", 409)
                return json.loads(row[1]), False
            receipt = {"operation_id": op["operation_id"], "payload_hash": digest,
                       "workspace_id": op["workspace_id"], "owner_id": op["owner_id"],
                       "runtime_id": op["runtime_id"], "scene_epoch": op.get("scene_epoch"),
                       "kind": op["kind"], "label": str(op.get("label", op["kind"]))[:160],
                       "state": "queued", "mutation_outcome": "not_run", "checks_outcome": "not_run",
                       "external_side_effects": "unknown" if op["kind"] == "execute" else "none",
                       "automatic_retry_safe": False, "cancel_requested": False,
                       "created_at": now(), "result_ref": None, "timings": {}}
            self.db.execute("INSERT INTO operations VALUES (?,?,?,NULL)",
                            (op["operation_id"], digest, encoded(receipt)))
            return receipt, True

    def get(self, operation_id):
        with self.lock:
            row = self.db.execute("SELECT receipt FROM operations WHERE id=?", (operation_id,)).fetchone()
            if not row:
                raise StudioError("OPERATION_NOT_FOUND", "No receipt is available for this ID", 404)
            return json.loads(row[0])

    def update(self, operation_id, *, detail=None, **changes):
        with self.lock, self.db:
            receipt = self.get(operation_id)
            receipt.update(changes)
            if detail is not None:
                receipt["result_ref"] = operation_id
                self.db.execute("UPDATE operations SET detail=? WHERE id=?", (encoded(detail), operation_id))
            self.db.execute("UPDATE operations SET receipt=? WHERE id=?", (encoded(receipt), operation_id))
            return receipt

    def recent(self, limit=30):
        with self.lock:
            return [json.loads(row[0]) for row in self.db.execute(
                "SELECT receipt FROM operations ORDER BY rowid DESC LIMIT ?", (min(100, max(1, limit)),))]

    def detail(self, operation_id, offset=0, limit=24000):
        self.get(operation_id)
        with self.lock:
            raw = self.db.execute("SELECT detail FROM operations WHERE id=?", (operation_id,)).fetchone()[0]
        if raw is None:
            return {"operation_id": operation_id, "available": False}
        offset, limit = max(0, int(offset)), min(48000, max(1, int(limit)))
        return {"operation_id": operation_id, "available": True, "text": raw[offset:offset + limit],
                "offset": offset, "next_offset": offset + limit if offset + limit < len(raw) else None,
                "total_characters": len(raw)}

    def recover(self):
        """Called once by a new runtime, never on an HTTP reconnect."""
        with self.lock:
            rows = self.db.execute("SELECT id,receipt FROM operations").fetchall()
            for op_id, raw in rows:
                state = json.loads(raw)["state"]
                if state in {"running", "queued"}:
                    self.update(op_id, state="unknown" if state == "running" else "cancelled",
                                mutation_outcome="unknown" if state == "running" else "not_run",
                                error={"code": "RUNTIME_RESTARTED", "message": "Previous runtime ended before confirmation"},
                                finished_at=now())

    def close(self):
        with self.lock:
            self.db.close()
