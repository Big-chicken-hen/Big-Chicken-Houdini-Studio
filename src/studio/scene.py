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
               "capture": {"frame", "resolution"},
               "lookup": {"source", "query", "category", "type_name", "symbol", "version"}}
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
    if kind == "lookup" and (any(not isinstance(v, str) for v in args.values()) or
                             args.get("source", "metadata") not in {"metadata", "hom"}):
        raise StudioError("INVALID_ARGUMENTS", "Use installed metadata or a public HOM symbol")


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
    def __init__(self, hou, artifact_root, secrets=()):
        self.hou = hou
        self.artifact_root = Path(artifact_root).resolve()
        self.artifact_root.mkdir(parents=True, exist_ok=True)
        self.secrets = tuple(value for value in secrets if value)
        self.epoch = new_id()
        self.lock = threading.RLock()
        self._cached = {}
        self._artifacts = {}
        self.houdini_version = self.hou.applicationVersionString()
        self.refresh_cached()
        self.hou.hipFile.addEventCallback(self._hip_event)

    def _hip_event(self, event, **_kwargs):
        changes = {getattr(self.hou.hipFileEventType, name, None)
                   for name in ("BeforeLoad", "BeforeClear")}
        if event in changes:
            with self.lock:
                self.epoch = new_id()
                self._cached["scene_epoch"] = self.epoch
        with contextlib.suppress(Exception):
            self.refresh_cached()

    def refresh_cached(self):
        with self.lock:
            self._cached = {"scene_epoch": self.epoch, "hip_path": self.redact(self.hou.hipFile.path()),
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
        def checkpoint():
            if cancelled():
                raise StudioError("COOPERATIVE_STOP", "Stopped at an explicit script checkpoint")
        namespace = {"hou": self.hou, "result": None, "checkpoint": checkpoint,
                     "cancel_requested": cancelled, "__name__": "__studio_hom__"}
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
            return {"symbol": symbol, "documentation": self.redact(getattr(obj, "__doc__", "") or "")[:18000],
                    "houdini_version": self.houdini_version}
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

    def capture(self, args):
        viewer = self.hou.ui.paneTabOfType(self.hou.paneTabType.SceneViewer)
        if viewer is None:
            raise StudioError("VIEWPORT_UNAVAILABLE", "Open a Scene Viewer pane before capturing")
        frame = float(args.get("frame", self.hou.frame()))
        if not math.isfinite(frame):
            raise StudioError("INVALID_ARGUMENTS", "Frame must be finite")
        width, height = [min(2560, max(64, int(v))) for v in args.get("resolution", [1280, 720])]
        viewport = viewer.curViewport()
        previous_frame = self.hou.frame()
        artifact_id = new_id()
        pattern = self.artifact_root / (artifact_id + "-$F4.png")
        output = self.artifact_root / (artifact_id + f"-{int(round(frame)):04d}.png")
        try:
            settings = viewer.flipbookSettings().stash()
            # A still capture must not inherit simulation resets, subframe blur or
            # keyframe-only/multiple-viewport playback from an earlier flipbook.
            settings.initializeSimulations(False)
            settings.useMotionBlur(False)
            settings.scopeChannelKeyframesOnly(False)
            settings.renderAllViewports(False)
            settings.frameRange((frame, frame))
            settings.output(str(pattern))
            settings.resolution((width, height))
            settings.useResolution(True)
            settings.outputZoom(100)
            settings.useSheetSize(False)
            settings.outputToMPlay(False)
            self.hou.setFrame(frame)
            viewer.flipbook(viewport, settings, open_dialog=False)
            if not output.is_file() or output.stat().st_size == 0:
                raise StudioError("CAPTURE_MISSING", "Houdini did not produce the requested PNG")
        finally:
            self.hou.setFrame(previous_frame)
        with self.lock:
            self._artifacts[artifact_id] = output
        return {"artifact_id": artifact_id, "mime_type": "image/png", "frame": frame,
                "restored_frame": self.hou.frame(), "path": str(output)}

    def artifact(self, artifact_id):
        with self.lock:
            path = self._artifacts.get(artifact_id)
        if path is None:
            raise StudioError("ARTIFACT_NOT_FOUND", "Unknown capture", 404)
        if path.stat().st_size > 12 * 1024 * 1024:
            raise StudioError("IMAGE_TOO_LARGE", "Capture exceeds 12 MB; request a smaller resolution", 413)
        return path.read_bytes()

    def close(self):
        with contextlib.suppress(Exception):
            self.hou.hipFile.removeEventCallback(self._hip_event)
