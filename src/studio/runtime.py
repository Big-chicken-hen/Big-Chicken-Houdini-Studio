"""One bounded queue and one execution authority for every scene interaction."""
from __future__ import annotations

import json
import queue
import threading
import time

from .common import PROTOCOL, TERMINAL, StudioError, encoded, identifier, new_id, now
from .scene import ExecutionResult, validate_arguments


class OperationRuntime:
    def __init__(self, ledger, scene, dispatch, *, workspace_id, session_id, capacity=16):
        if type(capacity) is not int or capacity < 1:
            raise ValueError("Queue capacity must be positive")
        self.ledger, self.scene, self.dispatch = ledger, scene, dispatch
        self.ledger.redact = scene.redact
        self.workspace_id, self.session_id = workspace_id, session_id
        self.runtime_id = new_id()
        self.capacity = capacity
        self.queue = queue.Queue(maxsize=capacity)
        self.lock = threading.RLock()
        self.active = None
        self.pending = set()
        self.cancelled = set()
        self.paused = set()
        self.closed = False
        self.storage_fault = None
        self.unconfirmed = set()
        self.ledger.recover()
        self.worker = threading.Thread(target=self._worker, name="studio-scene-queue", daemon=True)
        self.worker.start()

    def health(self):
        with self.lock:
            return {"protocol": PROTOCOL, "alive": True, "runtime_id": self.runtime_id,
                    "launcher_session_id": self.session_id, "workspace_id": self.workspace_id,
                    "main_thread_busy": self.active is not None, "active_operation_id": self.active,
                    "queue_depth": len(self.pending), "capacity": self.capacity,
                    "scene": self.scene.cached(), "storage_fault": self.storage_fault}

    def get(self, operation_id):
        with self.lock:
            if operation_id in self.unconfirmed:
                raise StudioError("RECEIPT_UNAVAILABLE", "Receipt commit was not confirmed; execution outcome is unknown",
                                  503, operation_id=operation_id, mutation_outcome="unknown", automatic_retry_safe=False)
            return self.ledger.get(operation_id)

    def recent(self):
        with self.lock:
            rows = self.ledger.recent()
            for row in rows:
                if row["operation_id"] in self.unconfirmed:
                    row.update(state="unknown", mutation_outcome="unknown", receipt_confirmed=False,
                               error={"code": "RECEIPT_UNAVAILABLE", "message": self.storage_fault})
            return rows

    def lookup(self, arguments):
        validate_arguments("lookup", arguments)
        if arguments.get("source") != "hom":
            raise StudioError("INVALID_ARGUMENTS", "Live installation metadata uses the bounded operation queue")
        return self.ledger.sanitize(self.scene.lookup(arguments))

    def submit(self, op):
        if not isinstance(op, dict):
            raise StudioError("INVALID_OPERATION", "An operation must be an object")
        try:
            raw = encoded(op)
            if len(raw.encode("utf-8")) > 2 * 1024 * 1024:
                raise StudioError("REQUEST_LIMIT", "Operation exceeds 2 MB", 413)
            op = json.loads(raw)  # Freeze the payload against caller mutation.
        except (ValueError, TypeError, RecursionError) as exc:
            raise StudioError("INVALID_OPERATION", "An operation must contain finite JSON values") from exc
        for field in ("operation_id", "workspace_id", "owner_id", "runtime_id"):
            identifier(op.get(field))
        with self.lock:
            # Resolve duplicates before admission checks, including after Stop.
            try:
                self.get(op["operation_id"])
            except StudioError as exc:
                if exc.code != "OPERATION_NOT_FOUND":
                    raise
            else:
                return self.ledger.accept(op)[0]
            if op.get("kind") not in ("context", "inspect", "execute", "capture", "lookup"):
                raise StudioError("INVALID_OPERATION", "Unknown operation kind")
            validate_arguments(op["kind"], op.get("arguments", {}))
            if op["workspace_id"] != self.workspace_id or op["runtime_id"] != self.runtime_id:
                raise StudioError("RUNTIME_MISMATCH", "Operation belongs to another runtime or workspace", 409)
            if op["kind"] not in {"context", "lookup"}:
                if not op.get("scene_epoch"):
                    raise StudioError("OBSERVATION_REQUIRED", "Read context before interacting with the scene", 409)
                identifier(op["scene_epoch"])
            if self.closed or self.storage_fault:
                raise StudioError("RUNTIME_UNAVAILABLE", "The runtime cannot accept operations", 503)
            if op["owner_id"] in self.paused:
                raise StudioError("OWNER_STOPPED", "Future scene operations have been stopped", 409)
            if len(self.pending) >= self.capacity:
                raise StudioError("QUEUE_FULL", "Scene queue is full; no operation was accepted", 429)
            try:
                receipt, _ = self.ledger.accept(op)
            except Exception:
                self._persistence_failed(op["operation_id"])
                raise StudioError("RECEIPT_UNAVAILABLE", "Operation admission could not be persisted", 503)
            self.pending.add(op["operation_id"])
            self.queue.put_nowait(op)
            return receipt

    def cancel(self, operation_id):
        with self.lock:
            receipt = self.get(operation_id)
            if receipt["state"] in TERMINAL:
                return receipt
            self.cancelled.add(operation_id)
            if receipt["state"] == "queued":
                # Keep the slot until the actual queue item is drained.
                return self._commit(operation_id, state="cancelled", cancel_requested=True,
                                          mutation_outcome="not_run", finished_at=now())
            return self._commit(operation_id, cancel_requested=True)

    def stop_owner(self, owner_id):
        with self.lock:
            self.paused.add(identifier(owner_id))
            receipts = [self.cancel(op_id) for op_id in list(self.pending)
                        if self.ledger.get(op_id)["owner_id"] == owner_id]
            return {"owner_id": owner_id, "future_operations_stopped": True, "operations": receipts}

    def resume_owner(self, owner_id):
        with self.lock:
            if self.storage_fault or self.closed:
                raise StudioError("RUNTIME_UNAVAILABLE", "Runtime requires attention before resuming", 503)
            if self.pending:
                raise StudioError("SCENE_BUSY", "Wait for the current scene operation to finish", 409)
            self.paused.discard(identifier(owner_id))
            return {"resumed": True}

    def _worker(self):
        while True:
            try:
                op = self.queue.get(timeout=0.1)
            except queue.Empty:
                if self.closed:
                    self.ledger.close()
                    return
                continue
            try:
                self.dispatch(lambda: self._on_main_thread(op))
            except BaseException:
                # A dispatch/commit failure cannot establish whether HOM ran.
                try:
                    receipt = self.ledger.get(op["operation_id"])
                    if receipt["state"] not in TERMINAL:
                        self.ledger.update(op["operation_id"], state="unknown", mutation_outcome="unknown",
                                           error={"code": "EXECUTION_UNCONFIRMED", "message": "Execution could not be confirmed; do not replay"},
                                           finished_at=now())
                    with self.lock:
                        self.unconfirmed.discard(op["operation_id"])
                except BaseException:
                    self._persistence_failed(op["operation_id"])
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
            if self.storage_fault or self.closed or op["owner_id"] in self.paused or op_id in self.cancelled:
                self._commit(op_id, state="cancelled", mutation_outcome="not_run", finished_at=now())
                return
            if op["kind"] not in {"context", "lookup"} and op["scene_epoch"] != self.scene.epoch:
                self._commit(op_id, state="rejected", mutation_outcome="not_run", finished_at=now(),
                                   error={"code": "STALE_SCENE", "message": "The observed scene was replaced; read context again"})
                return
            receipt = self._commit(op_id, state="running", started_at=now())
            self.active = op_id
        outcome = ExecutionResult(mutation_outcome="unknown" if op["kind"] == "execute" else "none")
        try:
            value = self.scene.run(op["kind"], op.get("arguments", {}),
                                   lambda: op_id in self.cancelled)
            outcome = value if isinstance(value, ExecutionResult) else ExecutionResult(detail=value, mutation_outcome="none")
        except BaseException as exc:
            outcome.state = "failed"
            outcome.error = self.scene.error(exc, "HOM_FAILED")
        try:
            self.scene.refresh_cached()
        except BaseException:
            outcome.detail["cache_refresh_error"] = "Cached scene facts could not be refreshed"
        try:
            detail = self.ledger.sanitize(outcome.detail)
            size = len(encoded(detail).encode("utf-8"))
        except BaseException:
            detail = {"result_error": {"code": "RESULT_SERIALIZATION_FAILED",
                                       "message": "Result could not be serialized; execution facts are unchanged"}}
            size = 0
        summary = detail if size <= 16000 else {
            "detail_available": True, "message": "Read the detailed result by operation ID"}
        if op["kind"] == "context" and "scene_epoch" in detail:
            summary["scene_epoch"] = detail["scene_epoch"]
        # A failed commit must never be caught and relabelled as a script failure.
        self._commit(op_id, detail=detail, state=outcome.state, mutation_outcome=outcome.mutation_outcome,
                     checks_outcome=outcome.checks_outcome, error=outcome.error, result=summary, finished_at=now(),
                     timings={"queue_seconds": round(receipt["started_at"] - receipt["created_at"], 6),
                              "execution_seconds": round(time.monotonic() - started, 6)})

    def _persistence_failed(self, operation_id):
        with self.lock:
            self.storage_fault = "Receipt persistence failed; new scene operations are disabled"
            self.unconfirmed.add(operation_id)

    def _commit(self, op_id, **changes):
        try:
            return self.ledger.update(op_id, **changes)
        except BaseException:
            self._persistence_failed(op_id)
            raise

    def close(self):
        with self.lock:
            self.closed = True
            for op_id in list(self.pending):
                try:
                    self.cancel(op_id)
                except Exception:
                    pass
        self.worker.join(timeout=2)
        # The worker closes SQLite when it actually exits, including delayed HOM completion.
