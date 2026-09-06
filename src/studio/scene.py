"""Native HOM capabilities; all public scene methods run on Houdini's main thread."""
from __future__ import annotations

import contextlib
import inspect
import math
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path

from .common import StudioError, new_id, now
from .artifacts import ArtifactStore, capture_resolution

SCRIPT_FILENAME = "<Big-Chicken HOM batch>"


@dataclass
class ExecutionResult:
    """Facts set at the execution boundary, never inferred from exception names."""
    detail: dict = field(default_factory=dict)
    mutation_outcome: str = "not_run"
    checks_outcome: str = "not_run"
    state: str = "finished"
    error: dict | None = None


class DiscardOutput:
    """Do not forward arbitrary script output to process logs or protocol stdout."""
    def write(self, text):
        return len(text)

    def flush(self):
        pass


def node_path(value):
    if not isinstance(value, str) or not value.startswith("/") or ".." in value.split("/"):
        raise StudioError("INVALID_ARGUMENTS", "Node paths must be absolute")


def validate_checks(definitions):
    if not isinstance(definitions, list) or len(definitions) > 64:
        raise StudioError("INVALID_ARGUMENTS", "At most 64 checks are allowed")
    fields = {"node_exists": {"expected"}, "node_type": {"expected"},
              "parm_equals": {"parm", "expected", "tolerance"},
              "input_equals": {"index", "expected"}, "cook": set(), "geometry_nonempty": set()}
    for check in definitions:
        if not isinstance(check, dict) or not isinstance(check.get("kind"), str) or check["kind"] not in fields:
            raise StudioError("INVALID_ARGUMENTS", "Invalid check kind")
        kind = check["kind"]
        if set(check) - ({"kind", "path"} | fields[kind]):
            raise StudioError("INVALID_ARGUMENTS", "Unknown check field")
        node_path(check.get("path"))
        if kind == "node_exists" and not isinstance(check.get("expected", True), bool):
            raise StudioError("INVALID_ARGUMENTS", "node_exists expected must be boolean")
        if kind == "node_type" and not isinstance(check.get("expected"), str):
            raise StudioError("INVALID_ARGUMENTS", "node_type requires an expected type name")
        if kind == "parm_equals":
            if not isinstance(check.get("parm"), str) or not check["parm"] or "expected" not in check:
                raise StudioError("INVALID_ARGUMENTS", "parm_equals requires parm and expected")
            tolerance = check.get("tolerance", 1e-6)
            if type(tolerance) not in (int, float) or not math.isfinite(tolerance) or tolerance < 0:
                raise StudioError("INVALID_ARGUMENTS", "Tolerance must be finite and nonnegative")
        if kind == "input_equals":
            if "expected" not in check or type(check.get("index", 0)) is not int or check.get("index", 0) < 0:
                raise StudioError("INVALID_ARGUMENTS", "input_equals requires expected and a nonnegative index")
            if check["expected"] is not None:
                node_path(check["expected"])


def validate_view(view):
    if not isinstance(view, dict):
        raise StudioError("INVALID_ARGUMENTS", "A view must be an object")
    kind = view.get("view", "node")
    fields = {"node": set(), "parms": {"names"}, "children": {"limit"},
              "parameters": {"pattern", "offset", "limit"},
              "geometry": {"owners", "attributes", "samples"}, "checks": {"checks"}}
    if not isinstance(kind, str) or kind not in fields or set(view) - ({"view", "path"} | fields[kind]):
        raise StudioError("INVALID_ARGUMENTS", "Invalid inspection view")
    node_path(view.get("path", "/obj"))
    if kind == "parms":
        names = view.get("names")
        if not isinstance(names, list) or not 1 <= len(names) <= 64 or any(not isinstance(n, str) or not n for n in names):
            raise StudioError("INVALID_ARGUMENTS", "Supply 1 to 64 parameter names")
    if kind == "children" and (type(view.get("limit", 64)) is not int or not 1 <= view.get("limit", 64) <= 200):
        raise StudioError("INVALID_ARGUMENTS", "Child limit must be between 1 and 200")
    if kind == "parameters":
        if not isinstance(view.get("pattern", "*"), str) or not 1 <= len(view.get("pattern", "*")) <= 128:
            raise StudioError("INVALID_ARGUMENTS", "Supply a parameter name pattern of 1 to 128 characters")
        if type(view.get("offset", 0)) is not int or not 0 <= view.get("offset", 0) <= 1000000:
            raise StudioError("INVALID_ARGUMENTS", "Parameter offset must be an integer from 0 to 1000000")
        if type(view.get("limit", 64)) is not int or not 1 <= view.get("limit", 64) <= 128:
            raise StudioError("INVALID_ARGUMENTS", "Parameter page size must be between 1 and 128")
    if kind == "geometry":
        owners = view.get("owners", ["point", "primitive"])
        if (not isinstance(owners, list) or not 1 <= len(owners) <= 4 or
                any(not isinstance(v, str) or v not in {"point", "primitive", "vertex", "detail"} for v in owners) or
                len(set(owners)) != len(owners)):
            raise StudioError("INVALID_ARGUMENTS", "Supply unique geometry attribute owners")
        if "attributes" in view:
            names = view["attributes"]
            if (not isinstance(names, list) or not 1 <= len(names) <= 16 or
                    any(not isinstance(n, str) or not 1 <= len(n) <= 128 for n in names)):
                raise StudioError("INVALID_ARGUMENTS", "Supply 1 to 16 attribute names")
        if type(view.get("samples", 0)) is not int or not 0 <= view.get("samples", 0) <= 16:
            raise StudioError("INVALID_ARGUMENTS", "Geometry samples must be between 0 and 16")
    if kind == "checks":
        validate_checks(view.get("checks", []))


def validate_arguments(kind, args):
    """Pure validation: no node lookup, cook, observation or side effect."""
    allowed = {"context": set(), "inspect": {"views"},
               "execute": {"script", "label", "preconditions", "checks", "observe"},
               "capture": {"frame", "resolution", "purpose", "bounds"},
               "lookup": {"source", "query", "category", "type_name", "symbol", "version",
                          "members", "offset", "limit"}}
    if not isinstance(args, dict) or kind not in allowed or set(args) - allowed[kind]:
        raise StudioError("INVALID_ARGUMENTS", "Arguments do not match the operation")
    if kind == "execute":
        script = args.get("script")
        if not isinstance(script, str) or not script.strip() or len(script) > 256000:
            raise StudioError("INVALID_ARGUMENTS", "Supply a HOM script, up to 256000 characters")
        if not isinstance(args.get("label", ""), str):
            raise StudioError("INVALID_ARGUMENTS", "Label must be a string")
        validate_checks(args.get("preconditions", []))
        validate_checks(args.get("checks", []))
    if kind in {"inspect", "execute"}:
        views = args.get("views" if kind == "inspect" else "observe", [])
        low, high = (1, 32) if kind == "inspect" else (0, 64)
        if not isinstance(views, list) or not low <= len(views) <= high:
            raise StudioError("INVALID_ARGUMENTS", "Invalid number of targeted views")
        for view in views:
            validate_view(view)
    if kind == "capture":
        frame, resolution = args.get("frame", 1), args.get("resolution", [1280, 720])
        if type(frame) not in (int, float) or not math.isfinite(frame):
            raise StudioError("INVALID_ARGUMENTS", "Frame must be finite")
        if not isinstance(resolution, list) or len(resolution) != 2 or any(type(v) is not int or not 64 <= v <= 2560 for v in resolution):
            raise StudioError("INVALID_ARGUMENTS", "Resolution requires two integers from 64 to 2560")
        if args.get("purpose", "diagnostic") not in ("review", "diagnostic"):
            raise StudioError("INVALID_ARGUMENTS", "Capture purpose must be review or diagnostic")
        if "bounds" in args:
            bounds = args["bounds"]
            if (args.get("purpose", "diagnostic") != "review" or not isinstance(bounds, list) or
                    len(bounds) != 6 or any(type(v) not in (int, float) or not math.isfinite(v) for v in bounds) or
                    any(bounds[i] > bounds[i + 3] for i in range(3)) or
                    all(bounds[i] == bounds[i + 3] for i in range(3))):
                raise StudioError("INVALID_ARGUMENTS", "Review bounds require finite min XYZ then max XYZ with nonzero extent")
    if kind == "lookup":
        discovery = {"members", "offset", "limit"}
        if (any(not isinstance(v, str) for k, v in args.items() if k not in discovery) or
                args.get("source", "metadata") not in {"metadata", "hom"}):
            raise StudioError("INVALID_ARGUMENTS", "Use installed metadata or a public HOM symbol")
        if discovery.intersection(args) and args.get("source") != "hom":
            raise StudioError("INVALID_ARGUMENTS", "Member discovery applies only to HOM symbols")
        if type(args.get("members", False)) is not bool:
            raise StudioError("INVALID_ARGUMENTS", "members must be boolean")
        if (type(args.get("offset", 0)) is not int or not 0 <= args.get("offset", 0) <= 1000000 or
                type(args.get("limit", 32)) is not int or not 1 <= args.get("limit", 32) <= 64 or
                len(args.get("query", "")) > 128 and args.get("members", False)):
            raise StudioError("INVALID_ARGUMENTS", "HOM member pages require offset 0..1000000, limit 1..64 and query up to 128 characters")
        if {"offset", "limit"}.intersection(args) and not args.get("members", False):
            raise StudioError("INVALID_ARGUMENTS", "Member pagination requires members=true")


def json_value(value, depth=0, redact=lambda text: text):
    if depth > 12:
        return "[nested value omitted]"
    if isinstance(value, str):
        return redact(value)
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    if isinstance(value, dict):
        return {redact(str(k)): json_value(v, depth + 1, redact) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(v, depth + 1, redact) for v in value]
    return redact(repr(value))[:2000]


class HoudiniScene:
    def __init__(self, hou, artifact_root, secrets=(), paths=None, workspace_id=None, session_id=None):
        self.hou = hou
        self._artifacts = ArtifactStore(artifact_root)
        self.artifact_root = self._artifacts.root
        self.secrets = tuple(value for value in secrets if value)
        self.epoch = new_id()
        self.lock = threading.RLock()
        self._cached = {}
        self.paths, self.workspace_id, self.session_id = paths, workspace_id, session_id
        self.file_publisher = None
        self._confirmed_hip_path = None
        self._file_transition = False
        self._file_event = {"kind": "initial", "old_path": None, "new_path": None, "autosave": False}
        self._association = {"status": "unbound", "workspace_id": workspace_id}
        self.houdini_version = self.hou.applicationVersionString()
        # At initial UI attachment isNewFile() is native evidence about the
        # current scene. Subsequent name changes alone cannot confirm a save.
        initial = self._file_state()
        if initial["is_new_file"] is False and Path(initial["hip_path"]).is_file():
            self._confirmed_hip_path = initial["hip_path"]
        self._file_event["new_path"] = self.redact(initial["hip_path"])
        self.refresh_cached()
        self._record_file_state()
        self.hou.hipFile.addEventCallback(self._hip_event)

    def _hip_event(self, event, **kwargs):
        if kwargs.get("autosave"):
            return
        name = next((name for name in ("BeforeLoad", "BeforeClear", "AfterLoad", "AfterClear", "AfterSave")
                     if getattr(self.hou.hipFileEventType, name, None) is not None and
                     event == getattr(self.hou.hipFileEventType, name)), None)
        if not name:
            with contextlib.suppress(Exception):
                self.refresh_cached()
            return
        with self.lock:
            if name in {"BeforeLoad", "BeforeClear"}:
                self.epoch = new_id()
                self._file_transition = True
                self._cached["scene_epoch"] = self.epoch
            else:
                self._file_transition = False
            kind = {"BeforeLoad": "before_load", "BeforeClear": "before_clear", "AfterLoad": "load",
                    "AfterClear": "clear", "AfterSave": "save"}[name]
            self._file_event = {"kind": kind,
                                "old_path": self.redact(kwargs["old_hip_file"]) if isinstance(kwargs.get("old_hip_file"), str) else None,
                                "new_path": self.redact(kwargs["new_hip_file"]) if isinstance(kwargs.get("new_hip_file"), str) else None,
                                "autosave": False}
            if name == "AfterClear":
                self._confirmed_hip_path = None
            elif name in {"AfterLoad", "AfterSave"}:
                state = self._file_state()
                expected = kwargs.get("new_hip_file") or state["hip_path"]
                from .targets import path_key
                if (state["is_new_file"] is False and Path(state["hip_path"]).is_file() and
                        path_key(expected) == path_key(state["hip_path"])):
                    self._confirmed_hip_path = state["hip_path"]
                else:
                    self._confirmed_hip_path = None
        with contextlib.suppress(Exception):
            self.refresh_cached()
            if name in {"AfterLoad", "AfterClear", "AfterSave"}:
                self._record_file_state()
            if self.file_publisher:
                self.file_publisher(self.cached())

    def _file_state(self):
        path = self.hou.hipFile.path()
        is_new = None
        try:
            if getattr(self.hou, "isUIAvailable", lambda: True)():
                value = self.hou.hipFile.isNewFile()
                is_new = value if type(value) is bool else None
        except Exception:
            pass
        from .targets import path_key
        saved = self._confirmed_hip_path
        if self._file_transition or not saved or path_key(saved) != path_key(path):
            saved = None
        name = "未保存场景" if is_new is True else Path(path).name
        if is_new is None or (is_new is False and not saved):
            name += "（保存位置未确认）"
        return {"hip_path": path, "is_new_file": is_new, "saved_hip_path": saved, "display_name": name}

    def _record_file_state(self):
        if self.paths is None or self.workspace_id is None:
            return
        from .targets import SceneCatalog
        try:
            self._association = SceneCatalog(self.paths).record_scene(self.workspace_id, self.cached(), self.session_id)
        except Exception:
            self._association = {"status": "unavailable", "workspace_id": self.workspace_id,
                                 "message": "Scene history could not be updated; existing contexts were preserved"}
        with self.lock:
            self._cached["association"] = self._association

    def refresh_cached(self):
        with self.lock:
            file_state = self._file_state()
            self._cached = {"scene_epoch": self.epoch,
                            **{k: self.redact(v) if isinstance(v, str) else v for k, v in file_state.items()},
                              "file_event": dict(self._file_event), "association": self._association,
                            "dirty": self.hou.hipFile.hasUnsavedChanges(), "frame": self.hou.frame(),
                            "observed_at": now()}

    def cached(self):
        with self.lock:
            return dict(self._cached)

    def redact(self, text):
        for value in self.secrets:
            text = text.replace(value, "[REDACTED]")
        return re.sub(r"\bsk-[A-Za-z0-9_-]{16,}\b", "[REDACTED]", text)

    def _node(self, path):
        node_path(path)
        node = self.hou.node(path)
        if node is None:
            raise StudioError("NODE_NOT_FOUND", "Node does not exist: " + path)
        return node

    def run(self, kind, args, cancelled):
        if kind == "context":
            self.refresh_cached()
            network = self.hou.ui.paneTabOfType(self.hou.paneTabType.NetworkEditor)
            return {**self.cached(), "selected": [n.path() for n in self.hou.selectedNodes()][:64],
                    "network": network.pwd().path() if network else "/obj",
                    "houdini_version": self.hou.applicationVersionString()}
        if kind == "inspect":
            views = args.get("views", [])
            if not isinstance(views, list) or not 1 <= len(views) <= 32:
                raise StudioError("INVALID_ARGUMENTS", "Supply between 1 and 32 targeted views")
            return {"views": [self.inspect(view) for view in views]}
        if kind == "lookup":
            return self.lookup(args)
        if kind == "execute":
            return self.execute(args, cancelled)
        if kind == "capture":
            return self.capture(args)
        raise StudioError("INVALID_ARGUMENTS", "Unknown scene operation")

    def inspect(self, view):
        validate_view(view)
        kind, path = view.get("view", "node"), view.get("path", "/obj")
        node = self._node(path)
        base = {"path": path, "view": kind}
        if kind == "node":
            return {**base, "type": node.type().name(), "name": node.name(),
                    "inputs": [n.path() if n else None for n in node.inputs()],
                    "errors": list(node.errors()), "warnings": list(node.warnings()),
                    "position": list(node.position())}
        if kind == "parms":
            names = view.get("names", [])
            if not isinstance(names, list) or not 1 <= len(names) <= 64:
                raise StudioError("INVALID_ARGUMENTS", "Supply 1 to 64 parameter names")
            values = {}
            for name in names:
                parm = node.parm(name)
                if parm is None:
                    values[name] = {"error": "PARM_NOT_FOUND"}
                else:
                    values[name] = json_value(parm.eval(), redact=self.redact)
            return {**base, "values": values}
        if kind == "children":
            limit = min(200, max(1, int(view.get("limit", 64))))
            children = node.children()
            return {**base, "nodes": [{"path": n.path(), "type": n.type().name(),
                                       "inputs": [x.path() if x else None for x in n.inputs()],
                                       "position": list(n.position())} for n in children[:limit]],
                    "total": len(children), "truncated": len(children) > limit}
        if kind == "parameters":
            from .inspection import parameter_instances
            return {**base, **parameter_instances(node, view, self.redact)}
        if kind == "geometry":
            from .inspection import geometry_facts
            return {**base, **geometry_facts(node, view, self.redact)}
        if kind == "checks":
            return {**base, "checks": self.checks(view.get("checks", []))}
        raise StudioError("INVALID_ARGUMENTS", "Unknown inspection view")

    def checks(self, definitions):
        validate_checks(definitions)
        records = []
        for check in definitions:
            if not isinstance(check, dict):
                raise StudioError("INVALID_ARGUMENTS", "A check must be an object")
            kind, path = check.get("kind"), check.get("path")
            record = {"kind": kind, "path": path, "passed": False}
            try:
                node = self.hou.node(path)
                if kind == "node_exists":
                    record["actual"] = node is not None
                    record["passed"] = record["actual"] == check.get("expected", True)
                elif kind == "node_type":
                    record["actual"] = node.type().name() if node else None
                    record["passed"] = record["actual"] == check["expected"]
                elif kind == "parm_equals":
                    parm = node.parm(check["parm"]) if node else None
                    record["actual"] = json_value(parm.eval(), redact=self.redact) if parm else None
                    expected = check["expected"]
                    if isinstance(expected, (int, float)) and not isinstance(expected, bool) and parm:
                        record["passed"] = math.isclose(float(record["actual"]), expected,
                                                        rel_tol=0, abs_tol=float(check.get("tolerance", 1e-6)))
                    else:
                        record["passed"] = bool(parm) and record["actual"] == expected
                elif kind == "input_equals":
                    if node is None:
                        raise StudioError("NODE_NOT_FOUND", "Input target node does not exist")
                    inputs = node.inputs()
                    index = int(check.get("index", 0))
                    record["actual"] = inputs[index].path() if 0 <= index < len(inputs) and inputs[index] else None
                    record["passed"] = record["actual"] == check["expected"]
                elif kind == "cook":
                    self._node(path).cook(force=True)
                    record["errors"] = list(node.errors())
                    record["passed"] = not record["errors"]
                elif kind == "geometry_nonempty":
                    geo = self._node(path).geometry()
                    record["points"] = geo.intrinsicValue("pointcount")
                    record["passed"] = record["points"] > 0
                else:
                    raise StudioError("INVALID_ARGUMENTS", "Unknown check kind: " + str(kind))
            except Exception as exc:
                diagnostic = self.error(exc, "CHECK_FAILED")
                record["error"] = diagnostic["message"][:400]
                record["error_code"] = diagnostic["code"]
            records.append(record)
        return records

    def execute(self, args, cancelled):
        outcome = ExecutionResult()
        def output_path(kind, filename, *, explicit=None, existing=None):
            from .output import resolve_output
            if self.paths is None or self.workspace_id is None:
                raise StudioError("OUTPUT_CONTEXT_UNAVAILABLE", "Studio output context is unavailable")
            # Called inside this already admitted main-thread HOM batch. A
            # returned path is fixed; a later call reads a new Save As location.
            resolved = resolve_output(self._file_state(), self.paths.cache("outputs", self.workspace_id),
                                      kind, filename, explicit=explicit, existing=existing, expand=self.hou.expandString)
            records = outcome.detail.setdefault("resolved_outputs", [])
            if len(records) < 64:
                records.append(resolved)
            else:
                outcome.detail["resolved_outputs_truncated"] = True
            try:
                Path(resolved["path"]).parent.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                raise StudioError("OUTPUT_DIRECTORY_UNWRITABLE", "Cannot create the output directory; choose another location") from exc
            return resolved["path"]
        def checkpoint():
            if cancelled():
                raise StudioError("COOPERATIVE_STOP", "Stopped at an explicit script checkpoint")
        namespace = {"hou": self.hou, "result": None, "checkpoint": checkpoint,
                       "cancel_requested": cancelled, "output_path": output_path, "__name__": "__studio_hom__"}
        # Redirect only for this batch; no raw print/traceback reaches the host log.
        with contextlib.redirect_stdout(DiscardOutput()), contextlib.redirect_stderr(DiscardOutput()):
            try:
                validate_arguments("execute", args)
                try:
                    code = compile(args["script"], SCRIPT_FILENAME, "exec")
                except (SyntaxError, ValueError) as exc:
                    outcome.state = "rejected"
                    outcome.error = self.error(exc, "COMPILE_FAILED")
                    return outcome
                preconditions = self.checks(args.get("preconditions", []))
                if any(not item["passed"] for item in preconditions):
                    outcome.detail["preconditions"] = preconditions
                    raise StudioError("PRECONDITION_FAILED", "A target changed since observation")
                before = [self.inspect(view) for view in args.get("observe", [])]
                outcome.detail["observations"] = {"before": before}
                checkpoint()
                # Undo grouping is a user convenience, never a Python transaction.
                with self.hou.undos.group(self.redact(args.get("label", "Big-Chicken Studio"))[:100]):
                    outcome.mutation_outcome = "partial"
                    exec(code, namespace, namespace)
                    outcome.mutation_outcome = "completed"
            except BaseException as exc:
                outcome.state = "rejected" if outcome.mutation_outcome == "not_run" else "failed"
                outcome.error = self.error(exc, "HOM_FAILED")
                return outcome

            # Script completion survives postcondition, observation and conversion failures.
            try:
                verified = self.checks(args.get("checks", []))
                outcome.detail["checks"] = verified
                outcome.checks_outcome = ("passed" if all(c["passed"] for c in verified) else "failed") if verified else "not_run"
            except BaseException as exc:
                outcome.checks_outcome = "failed"
                outcome.detail["checks_error"] = self.error(exc, "CHECKS_FAILED")
            try:
                outcome.detail["observations"]["after"] = [self.inspect(view) for view in args.get("observe", [])]
            except BaseException as exc:
                outcome.detail["observation_error"] = self.error(exc, "OBSERVATION_FAILED")
            try:
                outcome.detail["value"] = json_value(namespace.get("result"), redact=self.redact)
            except BaseException as exc:
                outcome.detail["result_error"] = self.error(exc, "RESULT_CONVERSION_FAILED")
        return outcome

    def error(self, exc, fallback):
        try:
            # SyntaxError.__str__ adds filename/source context; only its reason is needed.
            message = self.redact(str(exc.msg) if isinstance(exc, SyntaxError) else str(exc))
            if re.search(r"\benviron\s*\(|['\"](?:PATH|Path|USERPROFILE|SYSTEMROOT)['\"]\s*:", message):
                message = "Environment details omitted from exception message"
            else:
                # Exception reasons may contain filenames. Never emit absolute OS paths,
                # traceback source lines, frame locals or environment values collected here.
                message = re.sub(r"(?i)\b(?:[A-Z][A-Z0-9_]*_)?(?:TOKEN|SECRET|PASSWORD|API_KEY)\b\s*[:=]\s*\S+",
                                 "[credential omitted]", message)
                message = re.sub(r"(?i)(?:[a-z]:[\\/]|\\\\)[^\r\n'\"<>|]*", "[path omitted]", message)
                message = re.sub(r"(?<![\w:])/(?:[^\s'\"<>:,;\)\]]+/?)+", "[path omitted]", message)
            message = message[:1200]
        except BaseException:
            message = "Exception message unavailable"
        code = exc.code if isinstance(exc, StudioError) and isinstance(exc.code, str) else fallback
        diagnostic = {"code": self.redact(code)[:80], "message": message,
                      "exception_type": self.redact(type(exc).__name__)[:80]}
        if isinstance(exc, SyntaxError) and exc.filename == SCRIPT_FILENAME:
            diagnostic.update(script_line=exc.lineno, script_column=exc.offset)
        else:
            frame = exc.__traceback__
            while frame is not None:
                if frame.tb_frame.f_code.co_filename == SCRIPT_FILENAME:
                    diagnostic["script_line"] = frame.tb_lineno
                frame = frame.tb_next
        return diagnostic

    def lookup(self, args):
        validate_arguments("lookup", args)
        if args.get("source", "metadata") == "hom":
            symbol = args.get("symbol", "")
            parts = symbol.removeprefix("hou.").split(".")
            if not 1 <= len(parts) <= 4 or any(not p.isidentifier() or p.startswith("_") for p in parts):
                raise StudioError("INVALID_ARGUMENTS", "Use a public HOM symbol such as hou.Node.createNode")
            obj = self.hou
            for part in parts:
                obj = inspect.getattr_static(obj, part, None)
                if obj is None:
                    raise StudioError("SYMBOL_NOT_FOUND", "HOM symbol is absent in this installation", 404)
            result = {"symbol": symbol, **self._hom_symbol_info(obj), "houdini_version": self.houdini_version}
            if args.get("members", False):
                # Static namespaces only: no instance getters, HOM calls, custom
                # __dir__, recursive installation scan or descriptor evaluation.
                if inspect.isclass(obj):
                    namespaces = [vars(base) for base in inspect.getmro(obj)]
                elif inspect.ismodule(obj):
                    namespaces = [vars(obj)]
                else:
                    raise StudioError("INVALID_ARGUMENTS", "Discover members of a public HOM class or module")
                query = args.get("query", "").casefold()
                names = sorted({name for namespace in namespaces for name in namespace
                                if not name.startswith("_") and query in name.casefold()})
                offset, limit = args.get("offset", 0), args.get("limit", 32)
                page = names[offset:offset + limit]
                result.update(members=[{"name": name, **self._hom_symbol_info(
                    inspect.getattr_static(obj, name), short=True)} for name in page],
                    total=len(names), offset=offset,
                    next_offset=offset + limit if offset + limit < len(names) else None)
            return result
        category = args.get("category", "Sop")
        category_object = self.hou.nodeTypeCategories().get(category)
        if category_object is None:
            return {"categories": list(self.hou.nodeTypeCategories())}
        name, query = args.get("type_name"), str(args.get("query", "")).lower()
        types = category_object.nodeTypes()
        if not name:
            return {"types": [{"name": key, "label": val.description()} for key, val in types.items()
                              if query in key.lower() or query in val.description().lower()][:80]}
        node_type = types.get(name)
        if node_type is None:
            raise StudioError("NODE_TYPE_NOT_FOUND", "Node type is absent in this installation", 404)
        templates = []

        def visit(template):
            templates.append({"name": template.name(), "label": template.label(),
                              "type": str(template.type()), "components": template.numComponents()})
            if hasattr(template, "parmTemplates"):
                for child in template.parmTemplates():
                    visit(child)

        for template in node_type.parmTemplates():
            visit(template)
        return {"name": name, "category": category, "parameters": templates[:300],
                "houdini_version": self.hou.applicationVersionString()}

    def _hom_symbol_info(self, obj, short=False):
        kind = ("class" if inspect.isclass(obj) else "module" if inspect.ismodule(obj) else
                "property" if isinstance(obj, property) else "callable" if inspect.isroutine(obj) else "value")
        doc = getattr(obj, "__doc__", "") if kind != "value" else ""
        result = {"kind": kind, "documentation": self.redact(doc or "")[:240 if short else 18000]}
        if inspect.isroutine(obj):
            # H22's setRotation has no docstring; its Matrix3 annotation is the
            # authoritative installed type hint. Never evaluate string annotations.
            try:
                signature = inspect.signature(obj, follow_wrapped=False, eval_str=False)
                result["signature"] = self.redact(str(signature))[:600 if short else 2000]
            except (TypeError, ValueError):
                result["signature"] = None
        return result

    def _capture_view(self, viewer, viewport, args, detail, restorers):
        # Optional review metadata must not become a dependency of the default
        # diagnostic capture, which uses the current view unchanged.
        if args.get("purpose", "diagnostic") == "diagnostic":
            return
        settings = viewport.settings()
        camera_path = viewport.cameraPath()
        detail["view"] = {"viewport": self.redact(viewport.name()), "type": str(viewport.type()),
                          "camera_path": self.redact(camera_path), "framing": "current"}
        # These are settings, not a classification of pixels. An environment
        # option being enabled does not prove that it caused a visible horizon.
        detail["background"] = {"color_scheme": str(settings.colorScheme()),
                                "images_enabled": bool(settings.displayBackgroundImage()),
                                "environment_enabled": bool(settings.displayEnvironmentBackgroundImage()),
                                "horizon": "unclassified", "policy": "preserved"}
        framing = None
        if "bounds" in args:
            camera = viewport.camera()
            if viewport.isViewingThroughExtraCamera() or (camera_path and camera is None):
                raise StudioError("REVIEW_FRAMING_UNSUPPORTED", "Use diagnostic capture or a free/OBJ camera view for review bounds")
            framing = (camera, viewport.defaultCamera().stash(), bool(viewport.isCameraLockedToView()),
                       tuple(viewport.viewTransform().asTuple()))

        # Only known decorations; CurrentGeometry/DisplayNodes/TemplateGeometry
        # and other guides that actually show user geometry must stay untouched.
        displays = []
        for name in ("XYPlane", "XZPlane", "YZPlane", "OriginGnomon", "FloatingGnomon"):
            guide = getattr(self.hou.viewportGuide, name)
            displays.append((name, lambda guide=guide: settings.guideEnabled(guide),
                             lambda value, guide=guide: settings.enableGuide(guide, value)))
        plane = viewer.constructionPlane()
        displays.extend([("ortho_grid", settings.displayOrthoGrid, settings.setDisplayOrthoGrid),
                         ("construction_plane", plane.isVisible, plane.setIsVisible)])
        saved = [(name, getter, setter, bool(getter())) for name, getter, setter in displays]
        detail["display_adjustments"] = []
        for name, getter, setter, previous in saved:
            record = {"setting": name, "before": previous, "during": None, "restored": None}
            detail["display_adjustments"].append(record)

            def restore_display(getter=getter, setter=setter, previous=previous, record=record):
                try:
                    if bool(getter()) != previous:
                        setter(previous)
                finally:
                    record["restored"] = bool(getter())
                if record["restored"] != previous:
                    raise StudioError("VIEW_RESTORE_MISMATCH", "A viewport decoration was not restored")

            # Register before writing: even a setter that partially fails needs
            # restoration. Other restorers still run if this one fails.
            restorers.append((name, restore_display))
            if previous:
                setter(False)
            record["during"] = bool(getter())
            if record["during"]:
                raise StudioError("REVIEW_DISPLAY_MISMATCH", "A requested viewport decoration remains enabled")

        if framing is not None:
            camera, saved_view, locked, transform = framing
            free_view = {"saved": saved_view if camera is None else None}
            restorers.append(("view", lambda: self._restore_capture_view(
                viewport, camera, saved_view, free_view, locked, transform, camera_path, detail)))
            # H22 defaultCamera() is live and can edit a locked camera node.
            # Disconnect and verify before framing; never write camera parameters.
            viewport.lockCameraToView(False)
            if viewport.isCameraLockedToView():
                raise StudioError("REVIEW_CAMERA_LOCKED", "Could not unlock the viewport for temporary framing")
            viewport.useDefaultCamera()
            if viewport.cameraPath() or viewport.isViewingThroughExtraCamera():
                raise StudioError("REVIEW_CAMERA_BOUND", "Could not detach the viewport for temporary framing")
            if camera is not None:
                free_view["saved"] = viewport.defaultCamera().stash()
            viewport.frameBoundingBox(self.hou.BoundingBox(*args["bounds"]))
            detail["view"].update(framing="bounds", bounds=list(args["bounds"]), capture_camera_path="")
        viewport.draw()

    def _restore_capture_view(self, viewport, camera, saved_view, free_view, locked, transform, camera_path, detail):
        def attempt(phase, action):
            try:
                action()
                return True
            except BaseException as exc:
                detail["restore_errors"].append({"phase": phase, "error": self.error(exc, "VIEW_RESTORE_FAILED")})
                return False

        def detach():
            viewport.lockCameraToView(False)
            if viewport.isCameraLockedToView():
                raise StudioError("VIEW_RESTORE_LOCKED", "Restoration cannot safely change a locked view")
            viewport.useDefaultCamera()
            if viewport.cameraPath() or viewport.isViewingThroughExtraCamera():
                raise StudioError("VIEW_RESTORE_BOUND", "Restoration could not detach the viewport")

        if attempt("detach_view", detach) and free_view["saved"] is not None:
            attempt("default_view", lambda: viewport.setDefaultCamera(free_view["saved"]))
        if camera is not None:
            attempt("camera_binding", lambda: viewport.setCamera(camera))
        attempt("camera_lock", lambda: viewport.lockCameraToView(locked))

        def verify():
            observed = tuple(viewport.viewTransform().asTuple())
            restored_path, restored_lock = viewport.cameraPath(), bool(viewport.isCameraLockedToView())
            matches = len(observed) == len(transform) and all(
                math.isclose(a, b, rel_tol=0, abs_tol=1e-6) for a, b in zip(observed, transform))
            width_matches = math.isclose(viewport.defaultCamera().orthoWidth(), saved_view.orthoWidth(),
                                         rel_tol=0, abs_tol=1e-6)
            detail["view"]["restored"] = {"camera_path": self.redact(restored_path), "locked": restored_lock,
                                           "transform_matches": matches, "ortho_width_matches": width_matches}
            if restored_path != camera_path or restored_lock != locked or not matches or not width_matches:
                raise StudioError("VIEW_RESTORE_MISMATCH", "Original viewport or camera binding was not restored")

        attempt("verify_view", verify)

    def capture(self, args):
        # Adapted frame/camera restore separation from HIA 6d9a2d7. No multi-frame
        # orchestration, scene cleanup or heuristic visual quality gate.
        detail = {"capture_api": "SceneViewer.flipbook", "requested_frame": args.get("frame"),
                  "purpose": args.get("purpose", "diagnostic"),
                  "configured_frame_range": None, "frame_before": None,
                  "frame_before_capture": None, "actual_frame": None,
                  "restored_frame": None, "capture_error": None, "restore_errors": []}
        previous_frame, artifact_id = None, None
        restorers = []
        try:
            validate_arguments("capture", args)
            previous_frame = float(self.hou.frame())
            if not math.isfinite(previous_frame):
                raise StudioError("FRAME_UNAVAILABLE", "Current frame is not finite")
            frame = float(args.get("frame", previous_frame))
            detail.update(requested_frame=frame, frame_before=previous_frame)
            viewer = self.hou.ui.paneTabOfType(self.hou.paneTabType.SceneViewer)
            if viewer is None:
                raise StudioError("VIEWPORT_UNAVAILABLE", "Open a Scene Viewer pane before capturing")
            viewport = viewer.curViewport()
            width, height, source = capture_resolution(args, viewport)
            detail.update(requested_resolution=[width, height], resolution_source=source)
            self._capture_view(viewer, viewport, args, detail, restorers)
            artifact_id, output = self._artifacts.allocate()
            settings = viewer.flipbookSettings().stash()
            # Mutate only the stash. Do not reset simulation or inherit costly
            # subframe/keyframe/multiple-viewport options from a user's flipbook.
            settings.initializeSimulations(False)
            settings.useMotionBlur(False)
            settings.scopeChannelKeyframesOnly(False)
            settings.renderAllViewports(False)
            # Observe the last rendered frame before our own finally restores the
            # playbar; inherited flipbook auto-restoration could conceal rounding.
            settings.leaveFrameAtEnd(True)
            settings.frameRange((frame, frame))
            configured = settings.frameRange()
            if not isinstance(configured, (tuple, list)) or len(configured) != 2:
                raise StudioError("CAPTURE_FRAME_RANGE_UNAVAILABLE", "Flipbook frame range could not be verified")
            detail["configured_frame_range"] = [
                float(value) if type(value) in (int, float) and math.isfinite(value) else None
                for value in configured]
            if any(value is None or not math.isclose(value, frame, rel_tol=0, abs_tol=1e-6)
                   for value in detail["configured_frame_range"]):
                raise StudioError("CAPTURE_FRAME_MISMATCH", "Configured flipbook range does not match the requested frame")
            # A single still uses a literal unique path, not guessed $F rounding.
            settings.output(str(output))
            settings.resolution((width, height))
            settings.useResolution(True)
            settings.outputZoom(100)
            settings.useSheetSize(False)
            settings.outputToMPlay(False)
            if callable(getattr(settings, "cropOutMaskOverlay", None)):
                settings.cropOutMaskOverlay(False)
            self.hou.setFrame(frame)
            observed = float(self.hou.frame())
            detail["frame_before_capture"] = observed if math.isfinite(observed) else None
            if not math.isclose(observed, frame, rel_tol=0, abs_tol=1e-6):
                raise StudioError("CAPTURE_FRAME_MISMATCH", "Requested frame was not established before capture")
            viewer.flipbook(viewport, settings, open_dialog=False)
            observed = float(self.hou.frame())
            detail["actual_frame"] = observed if math.isfinite(observed) else None
            if not math.isclose(observed, frame, rel_tol=0, abs_tol=1e-6):
                raise StudioError("CAPTURE_FRAME_MISMATCH", "Observed frame changed during capture")
        except BaseException as exc:
            detail["capture_error"] = self.error(exc, "CAPTURE_FAILED")
        finally:
            if previous_frame is not None and math.isfinite(previous_frame):
                try:
                    self.hou.setFrame(previous_frame)
                except BaseException as exc:
                    detail["restore_errors"].append({"phase": "set_frame", "error": self.error(exc, "FRAME_RESTORE_FAILED")})
                # Verify even if setFrame raised; do not replace the capture error.
                try:
                    restored = float(self.hou.frame())
                    detail["restored_frame"] = restored if math.isfinite(restored) else None
                    if not math.isclose(restored, previous_frame, rel_tol=0, abs_tol=1e-6):
                        raise StudioError("FRAME_RESTORE_MISMATCH", "Original frame was not restored")
                except BaseException as exc:
                    detail["restore_errors"].append({"phase": "verify_frame", "error": self.error(exc, "FRAME_RESTORE_FAILED")})
            for phase, restore in reversed(restorers):
                try:
                    restore()
                except BaseException as exc:
                    detail["restore_errors"].append({"phase": phase, "error": self.error(exc, "VIEW_RESTORE_FAILED")})
        if detail["capture_error"] is None:
            try:
                # Verify real PNG scanlines/dimensions before registering an immutable
                # workspace reference. A restoration failure does not discard a valid image.
                info = self._artifacts.commit(artifact_id, dict(detail), detail["requested_resolution"])
                detail.update(info, frame=detail["actual_frame"], actual_resolution=[info["width"], info["height"]])
            except BaseException as exc:
                detail["capture_error"] = self.error(exc, "CAPTURE_FAILED")
                if isinstance(exc, StudioError) and exc.code == "CAPTURE_RESOLUTION_MISMATCH":
                    detail["actual_resolution"] = exc.details["actual_resolution"]
        error = detail["capture_error"] or (detail["restore_errors"][0]["error"] if detail["restore_errors"] else None)
        return ExecutionResult(detail=detail, state="failed" if error else "finished", error=error,
                               mutation_outcome="unknown" if detail["restore_errors"] else "none",
                               checks_outcome="failed" if error else "passed")

    def artifact(self, artifact_id):
        # Pure bounded file read: survives a new Runtime without touching HOM.
        return self._artifacts.read(artifact_id)

    def close(self):
        with contextlib.suppress(Exception):
            self.hou.hipFile.removeEventCallback(self._hip_event)
