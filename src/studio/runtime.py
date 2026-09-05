"""One bounded queue and one execution authority for every scene interaction."""
from __future__ import annotations

import queue
import threading
import time

from .common import PROTOCOL, TERMINAL, StudioError, encoded, identifier, new_id, now


class OperationRuntime:
    def __init__(self, ledger, scene, dispatch, *, workspace_id, session_id, capacity=16):
        self.ledger, self.scene, self.dispatch = ledger, scene, dispatch
        self.workspace_id, self.session_id = workspace_id, session_id
        self.runtime_id = new_id()
        self.capacity = capacity
        self.queue = queue.Queue()
        self.lock = threading.RLock()
        self.active = None
        self.pending = set()
        self.cancelled = set()
        self.paused = set()
        self.closed = False
        self.storage_fault = None
        self.ledger.recover()
        self.worker = threading.Thread(target=self._worker, name="studio-scene-queue", daemon=True)
        self.worker.start()

    def health(self):
        with self.lock:
            return {"protocol": PROTOCOL, "alive": True, "runtime_id": self.runtime_id,
                    "launcher_session_id": self.session_id, "workspace_id": self.workspace_id,
                    "main_thread_busy": bool(self.pending), "active_operation_id": self.active,
                    "queue_depth": len(self.pending), "capacity": self.capacity,
                    "scene": self.scene.cached(), "storage_fault": self.storage_fault}

    def submit(self, op):
        if not isinstance(op, dict):
            raise StudioError("INVALID_OPERATION", "An operation must be an object")
        for field in ("operation_id", "workspace_id", "owner_id", "runtime_id"):
            identifier(op.get(field))
        if op.get("kind") not in {"context", "inspect", "lookup", "execute", "capture"}:
            raise StudioError("INVALID_OPERATION", "Unknown operation kind")
        if not isinstance(op.get("arguments", {}), dict):
            raise StudioError("INVALID_ARGUMENTS", "Operation arguments must be an object")
        if op["workspace_id"] != self.workspace_id or op["runtime_id"] != self.runtime_id:
            raise StudioError("RUNTIME_MISMATCH", "Operation belongs to another runtime or workspace", 409)
        if op["kind"] != "context" and not op.get("scene_epoch"):
            raise StudioError("OBSERVATION_REQUIRED", "Read context before interacting with the scene", 409)
        with self.lock:
            # Resolve duplicates before admission checks, including after Stop.
            try:
                self.ledger.get(op["operation_id"])
            except StudioError as exc:
                if exc.code != "OPERATION_NOT_FOUND":
                    raise
            else:
                return self.ledger.accept(op)[0]
            if self.closed or self.storage_fault:
                raise StudioError("RUNTIME_UNAVAILABLE", "The runtime cannot accept operations", 503)
            if op["owner_id"] in self.paused:
                raise StudioError("OWNER_STOPPED", "Future scene operations have been stopped", 409)
            if len(self.pending) >= self.capacity:
                raise StudioError("QUEUE_FULL", "Scene queue is full; no operation was accepted", 429)
            receipt, _ = self.ledger.accept(op)
            self.pending.add(op["operation_id"])
            self.queue.put(op)
            return receipt

    def cancel(self, operation_id):
        with self.lock:
            receipt = self.ledger.get(operation_id)
            if receipt["state"] in TERMINAL:
                return receipt
            self.cancelled.add(operation_id)
            if receipt["state"] == "queued":
                self.pending.discard(operation_id)
                return self.ledger.update(operation_id, state="cancelled", cancel_requested=True,
                                          mutation_outcome="not_run", finished_at=now())
            return self.ledger.update(operation_id, cancel_requested=True)

    def stop_owner(self, owner_id):
        with self.lock:
            self.paused.add(identifier(owner_id))
            receipts = [self.cancel(op_id) for op_id in list(self.pending)
                        if self.ledger.get(op_id)["owner_id"] == owner_id]
            return {"owner_id": owner_id, "future_operations_stopped": True, "operations": receipts}

    def resume_owner(self, owner_id):
        with self.lock:
            if self.pending:
                raise StudioError("SCENE_BUSY", "Wait for the current scene operation to finish", 409)
            self.paused.discard(identifier(owner_id))
            return {"resumed": True}

    def _worker(self):
        while True:
            op = self.queue.get()
            if op is None:
                return
            try:
                self.dispatch(lambda: self._on_main_thread(op))
            except BaseException as exc:
                # A dispatch/commit failure cannot establish whether HOM ran.
                try:
                    receipt = self.ledger.get(op["operation_id"])
                    if receipt["state"] not in TERMINAL:
                        self.ledger.update(op["operation_id"], state="unknown", mutation_outcome="unknown",
                                           error={"code": "DISPATCH_FAILED", "message": str(exc)[:400]},
                                           finished_at=now())
                except BaseException:
                    self.storage_fault = "Receipt persistence failed; execution outcome may be unknown"
            finally:
                with self.lock:
                    self.pending.discard(op["operation_id"])
                    self.cancelled.discard(op["operation_id"])
                    self.active = None
                self.queue.task_done()

    def _on_main_thread(self, op):
        op_id = op["operation_id"]
        started = time.monotonic()
        with self.lock:
            if self.ledger.get(op_id)["state"] != "queued":
                return
            # These checks run in the SAME main-thread callback as the HOM batch.
            if op["kind"] != "context" and op["scene_epoch"] != self.scene.epoch:
                self.ledger.update(op_id, state="rejected", mutation_outcome="not_run", finished_at=now(),
                                   error={"code": "STALE_SCENE", "message": "The observed scene was replaced; read context again"})
                return
            self.active = op_id
            receipt = self.ledger.update(op_id, state="running", started_at=now())
        mutation, checks = "not_run", "not_run"
        try:
            value = self.scene.run(op["kind"], op.get("arguments", {}),
                                   lambda: op_id in self.cancelled)
            mutation = "completed" if op["kind"] == "execute" else "none"
            checks = value.pop("_checks_outcome", "not_run")
            # The full result is committed before the transport can observe completion.
            raw = encoded(value)
            summary = value if len(raw.encode("utf-8")) <= 16000 else {
                "detail_available": True, "message": "Execution completed; read the detailed result by operation ID"}
            self.ledger.update(op_id, detail=value, state="finished", mutation_outcome=mutation,
                               checks_outcome=checks, result=summary, finished_at=now(),
                               timings={"queue_seconds": round(now() - receipt["created_at"] -
                                                               (time.monotonic() - started), 6),
                                        "execution_seconds": round(time.monotonic() - started, 6)})
        except BaseException as exc:
            before_write = isinstance(exc, StudioError) and exc.code in {"PRECONDITION_FAILED", "INVALID_ARGUMENTS", "COMPILE_FAILED"}
            if op["kind"] == "execute":
                mutation = "not_run" if before_write else "partial"
            code = exc.code if isinstance(exc, StudioError) else "HOM_FAILED"
            self.ledger.update(op_id, state="rejected" if before_write else "failed", mutation_outcome=mutation,
                               checks_outcome=checks, error={"code": code, "message": self.scene.redact(str(exc))[:1600]},
                               finished_at=now(), timings={"execution_seconds": round(time.monotonic() - started, 6)})
        finally:
            self.scene.refresh_cached()

    def close(self):
        with self.lock:
            self.closed = True
            for op_id in list(self.pending):
                self.cancel(op_id)
            self.queue.put(None)
        self.worker.join(timeout=2)
        # Do not close SQLite underneath a main-thread operation still in progress.
        if not self.worker.is_alive():
            self.ledger.close()
