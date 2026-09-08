"""Bounded linear steps on the existing worker; no recovery execution or planner."""
from __future__ import annotations

import copy
import json
import math
import re
import time

from .common import TERMINAL, StudioError, encoded, now

STEP_ID = r"^[A-Za-z0-9_-]{1,64}$"


def step_id(value):
    if not isinstance(value, str) or not re.fullmatch(STEP_ID, value):
        raise StudioError("INVALID_STEP_ID", "Use a unique 1–64 character step ID: letters, digits, underscore or hyphen")
    return value


def json_data(value, limit=16384):
    """Validate before copying; never stringify HOM/custom objects or use summaries."""
    def check(item, depth=0):
        if depth > 32:
            raise StudioError("STEP_VALUE_INVALID", "Step JSON nesting exceeds 32 levels")
        kind = type(item)
        if item is None or kind in {str, bool, int}:
            return
        if kind is float and math.isfinite(item):
            return
        if kind is list:
            for child in item:
                check(child, depth + 1)
            return
        if kind is dict and all(type(key) is str for key in item):
            for child in item.values():
                check(child, depth + 1)
            return
        raise StudioError("STEP_VALUE_INVALID", "Step handoff requires finite builtin JSON values, not live Python/HOM objects")
    check(value)
    try:
        raw = encoded(value)
    except (TypeError, ValueError, RecursionError) as exc:
        raise StudioError("STEP_VALUE_INVALID", "Step result is not finite JSON") from exc
    if len(raw.encode("utf-8")) > limit:
        raise StudioError("STEP_VALUE_LIMIT", f"Step handoff exceeds {limit} bytes")
    return json.loads(raw)


def validate_staged(args):
    from .scene import validate_arguments
    if set(args) - {"steps", "label", "inputs"}:
        raise StudioError("INVALID_ARGUMENTS", "Staged mode accepts steps/label/inputs; checks and observations belong to steps")
    steps = args.get("steps")
    if not isinstance(steps, list) or not 2 <= len(steps) <= 8:
        raise StudioError("INVALID_ARGUMENTS", "Supply two to eight ordered HOM steps")
    if not isinstance(args.get("label", ""), str) or len(args.get("label", "")) > 160:
        raise StudioError("INVALID_ARGUMENTS", "Batch label must be at most 160 characters")
    if type(args.get("inputs", {})) is not dict:
        raise StudioError("INVALID_ARGUMENTS", "Staged inputs must be a JSON object")
    json_data({"inputs": args.get("inputs", {}), "results": {}}, 65536)
    seen, length = set(), 0
    for step in steps:
        if not isinstance(step, dict) or not {"id", "label", "script"} <= set(step):
            raise StudioError("INVALID_ARGUMENTS", "Each step requires id, label and script")
        identity = step_id(step["id"])
        if identity in seen:
            raise StudioError("INVALID_STEP_ID", "Step IDs must be unique within the request")
        seen.add(identity)
        validate_arguments("execute", {k: v for k, v in step.items() if k != "id"})
        if len(step["label"]) > 160 or len(step.get("observe", [])) + len(step.get("observe_after", [])) > 8:
            raise StudioError("INVALID_ARGUMENTS", "Each step permits a 160-character label and eight combined observations")
        length += len(step["script"])
    if length > 256000:
        raise StudioError("INVALID_ARGUMENTS", "All staged scripts together must fit 256000 characters")


def initial_detail(args):
    return {"mode": "staged", "active_step": None, "completed_steps": [], "stopped_at": None,
            "stop_reason": None, "steps": [{"id": s["id"], "label": s["label"], "state": "not_run",
                "mutation_outcome": "not_run", "checks_outcome": "not_run", "observation_status": "not_run",
                "error": None, "value_status": "not_run", "timings": {}} for s in args["steps"]]}


def summary(detail):
    result = {k: copy.deepcopy(v) for k, v in detail.items() if k != "steps"}
    result["steps"] = []
    for step in detail["steps"]:
        row = {k: copy.deepcopy(v) for k, v in step.items() if k not in {"detail", "context_before", "context_after"}}
        if "value" in row and len(encoded(row["value"]).encode("utf-8")) > 512:
            row.pop("value")
            row["value_summary_omitted"] = True
        row["step_detail_available"] = step["state"] not in {"not_run", "running"}
        result["steps"].append(row)
    from .observation_results import observation_summary
    return observation_summary("execute", result)


def interrupted(detail, code, message):
    """Only use the last durable detail when a step's completion is uncertain."""
    value = copy.deepcopy(detail)
    for step in value["steps"]:
        if step["state"] == "running":
            step.update(state="unknown", mutation_outcome="unknown", error={"code": code, "message": message},
                        failure_phase="confirmation", value_status="unknown")
    value.update(stopped_at=value.get("active_step") or next(
        (s["id"] for s in value["steps"] if s["state"] == "not_run"), None), stop_reason=code, active_step=None)
    return value


class StagedExecution:
    def __init__(self, runtime, op):
        self.runtime, self.op, self.op_id = runtime, op, op["operation_id"]
        self.args, self.scene = op["arguments"], runtime.scene
        self.detail = initial_detail(self.args)
        self.results, self.context = {}, None
        self.inputs = json_data(self.args.get("inputs", {}), 65536)
        self.started = time.monotonic()

    def mutation(self):
        values = [s["mutation_outcome"] for s in self.detail["steps"]]
        if "unknown" in values:
            return "unknown"
        if all(v == "completed" for v in values):
            return "completed"
        return "partial" if any(v != "not_run" for v in values) else "not_run"

    def publish(self, **changes):
        clean = self.runtime.ledger.sanitize(self.detail)
        brief = summary(clean)
        return self.runtime._commit(self.op_id, detail=clean, result=brief,
            **{k: brief[k] for k in ("mode", "active_step", "completed_steps", "stopped_at", "stop_reason", "steps")},
            mutation_outcome=self.mutation(), **changes)

    def finish(self, reason=None, error=None):
        with self.runtime.lock:
            receipt = self.runtime.ledger.get(self.op_id)
            if receipt["state"] in TERMINAL:
                return
            cancelled = self.op_id in self.runtime.cancelled or self.op["owner_id"] in self.runtime.paused or self.runtime.closed
            reason = "CANCEL_REQUESTED" if cancelled else reason
            self.detail["stop_reason"] = reason
            if reason and self.detail["stopped_at"] is None:
                self.detail["stopped_at"] = self.detail["active_step"] or next(
                    (s["id"] for s in self.detail["steps"] if s["state"] == "not_run"), self.detail["steps"][-1]["id"])
            self.detail["active_step"] = None
            state = "cancelled" if cancelled else "failed" if reason else "finished"
            if reason and self.mutation() == "not_run" and not cancelled:
                state = "rejected"
            self.publish(state=state, error=error or ({"code": reason, "message": "Staged operation stopped; read step facts before a new targeted operation"} if reason else None),
                checks_outcome="failed" if reason else "passed" if any(s["checks_outcome"] == "passed" for s in self.detail["steps"]) else "not_run",
                cancel_requested=bool(cancelled or receipt.get("cancel_requested")), finished_at=now(),
                timings={"queue_seconds": round(receipt.get("started_at", now()) - receipt["created_at"], 6),
                         "execution_seconds": round(time.monotonic() - self.started, 6)})

    def run(self):
        from .scene import SCRIPT_FILENAME
        self.codes = []
        # No callback/mutation occurs until every script compiles.
        for index, step in enumerate(self.args["steps"]):
            try:
                self.codes.append(compile(step["script"], SCRIPT_FILENAME, "exec"))
            except (SyntaxError, ValueError) as exc:
                error = self.scene.error(exc, "COMPILE_FAILED")
                self.detail["steps"][index].update(state="rejected", error=error, failure_phase="compile")
                self.detail["stopped_at"] = step["id"]
                self.finish("COMPILE_FAILED", error)
                return
        for index in range(len(self.codes)):
            if not self.runtime.dispatch(lambda index=index: self.step(index)):
                return
        self.finish()

    def step(self, index):
        step = self.detail["steps"][index]
        with self.runtime.lock:
            receipt = self.runtime.ledger.get(self.op_id)
            if receipt["state"] in TERMINAL:
                return False
            reason = None
            if self.runtime.storage_fault:
                raise StudioError("RECEIPT_UNAVAILABLE", "Cannot advance after receipt persistence failed")
            if self.runtime.closed or self.op_id in self.runtime.cancelled or self.op["owner_id"] in self.runtime.paused:
                reason = "CANCEL_REQUESTED"
            elif self.op["runtime_id"] != self.runtime.runtime_id or self.op["scene_epoch"] != self.scene.epoch:
                reason = "STALE_SCENE"
            try:
                context = self.scene.staged_context() if reason is None else None
                if self.context is not None and context != self.context and reason is None:
                    reason = "STEP_CONTEXT_CHANGED"
            except Exception as exc:
                reason = "STEP_CONTEXT_UNAVAILABLE"
                step["error"] = self.scene.error(exc, reason)
            if reason:
                self.detail["stopped_at"] = step["id"]
                self.finish(reason, step.get("error"))
                return False
            # This durable start covers the entire callback, including mutation.
            # Until it commits a result, do not project a definite 'not_run'.
            step.update(state="running", mutation_outcome="unknown", context_before=context)
            self.detail["active_step"] = step["id"]
            self.publish(state="running", **({"started_at": now()} if index == 0 else {}))
            self.runtime.active = self.op_id
        started = time.monotonic()
        arguments = {k: v for k, v in self.args["steps"][index].items() if k != "id"}
        outcome = self.scene.execute(arguments, lambda: self.op_id in self.runtime.cancelled,
            handoff={"inputs": copy.deepcopy(self.inputs), "results": copy.deepcopy(self.results)}, compiled=self.codes[index])
        detail = outcome.detail
        after = detail.get("observe_after", {})
        observation = (after.get("status", "ok") if arguments.get("observe_after") else "ok")
        observed_views = [*after.get("views", []), *detail.get("observations", {}).get("after", [])]
        if any(v.get("view") == "checks" and any(c.get("passed") is not True for c in v.get("checks", [])) for v in observed_views):
            observation = "error"
        if detail.get("observation_error") or detail.get("observe_after_error"):
            observation = "error"
        elif detail.get("observation_skip_reason"):
            observation = "skipped"
        if not arguments.get("observe") and not arguments.get("observe_after"):
            observation = "not_run"
        step.update(state=outcome.state, mutation_outcome=outcome.mutation_outcome, checks_outcome=outcome.checks_outcome,
                    observation_status=observation, error=outcome.error, detail=detail,
                    value=detail.get("value"), value_status=detail.get("value_status", "not_run"),
                    failure_phase=detail.get("failure_phase"), timings={"execution_seconds": round(time.monotonic() - started, 6)})
        reason = outcome.error.get("code", "STEP_FAILED") if outcome.error else None
        if reason is None and (outcome.state != "finished" or outcome.mutation_outcome != "completed"):
            reason = "STEP_EXECUTION_UNCONFIRMED"
        if reason is None and (outcome.checks_outcome == "failed" or detail.get("checks_error") or detail.get("checks_skip_reason")):
            reason = detail.get("checks_skip_reason") or "STEP_CHECK_FAILED"
        if reason is None and observation not in {"ok", "not_run"}:
            reason = "STEP_OBSERVATION_FAILED"
        if reason is None and detail.get("result_error"):
            reason = detail["result_error"]["code"]
        try:
            if self.scene.epoch != self.op["scene_epoch"]:
                reason = reason or "SCENE_REPLACED"
                step["context_after"] = {"scene_epoch": self.scene.epoch, "frame": None, "take_path": None}
            else:
                step["context_after"] = self.scene.staged_context()
            if reason is None:
                candidate = {**self.results, step["id"]: outcome.transfer}
                json_data({"inputs": self.inputs, "results": candidate}, 65536)
        except Exception as exc:
            reason = reason or (exc.code if isinstance(exc, StudioError) else "STEP_CONTEXT_UNAVAILABLE")
            step["handoff_error"] = self.scene.error(exc, reason)
        if reason:
            step.update(state="cancelled" if reason in {"CANCEL_REQUESTED", "COOPERATIVE_STOP"} else
                        "failed" if outcome.mutation_outcome != "not_run" else "rejected",
                        error=step["error"] or detail.get("result_error") or {"code": reason, "message": "Step did not pass its declared handoff gate"},
                        failure_phase=step.get("failure_phase") or "handoff")
            self.detail["stopped_at"] = step["id"]
        else:
            self.detail["completed_steps"].append(step["id"])
        self.detail["active_step"] = None
        with self.runtime.lock:
            self.publish(state="running")  # Commit this result before any further callback.
            cancelled = self.op_id in self.runtime.cancelled or self.op["owner_id"] in self.runtime.paused or self.runtime.closed
            if reason or cancelled:
                self.detail["stopped_at"] = step["id"]
                self.finish(reason, step["error"])
                return False
        self.results, self.context = candidate, step["context_after"]
        return True
