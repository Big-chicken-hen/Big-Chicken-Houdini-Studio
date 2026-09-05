"""Native HOM capabilities; all public scene methods run on Houdini's main thread."""
from __future__ import annotations

import contextlib
import math
import re
import threading
from pathlib import Path

from .common import StudioError, new_id, now


def json_value(value, depth=0):
    if depth > 12:
        return "[nested value omitted]"
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    if isinstance(value, dict):
        return {str(k): json_value(v, depth + 1) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(v, depth + 1) for v in value]
    return repr(value)[:2000]


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
        self.refresh_cached()
        self.hou.hipFile.addEventCallback(self._hip_event)

    def _hip_event(self, event):
        changes = {getattr(self.hou.hipFileEventType, name, None)
                   for name in ("BeforeLoad", "BeforeClear")}
        if event in changes:
            self.epoch = new_id()
        self.refresh_cached()

    def refresh_cached(self):
        with self.lock:
            self._cached = {"scene_epoch": self.epoch, "hip_path": self.hou.hipFile.path(),
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
        if not isinstance(path, str) or not path.startswith("/") or ".." in path.split("/"):
            raise StudioError("INVALID_ARGUMENTS", "Node paths must be absolute")
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
        if not isinstance(view, dict):
            raise StudioError("INVALID_ARGUMENTS", "A view must be an object")
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
                    values[name] = json_value(parm.eval())
            return {**base, "values": values}
        if kind == "children":
            limit = min(200, max(1, int(view.get("limit", 64))))
            children = node.children()
            return {**base, "nodes": [{"path": n.path(), "type": n.type().name(),
                                       "inputs": [x.path() if x else None for x in n.inputs()],
                                       "position": list(n.position())} for n in children[:limit]],
                    "total": len(children), "truncated": len(children) > limit}
        if kind == "geometry":
            geo = node.geometry()
            box = geo.boundingBox()
            return {**base, "points": geo.intrinsicValue("pointcount"),
                    "primitives": geo.intrinsicValue("primitivecount"),
                    "bounds": {"min": list(box.minvec()), "max": list(box.maxvec())},
                    "point_attributes": [a.name() for a in geo.pointAttribs()],
                    "primitive_attributes": [a.name() for a in geo.primAttribs()]}
        if kind == "checks":
            return {**base, "checks": self.checks(view.get("checks", []))}
        raise StudioError("INVALID_ARGUMENTS", "Unknown inspection view")

    def checks(self, definitions):
        if not isinstance(definitions, list) or len(definitions) > 64:
            raise StudioError("INVALID_ARGUMENTS", "At most 64 checks are allowed")
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
                    record["actual"] = json_value(parm.eval()) if parm else None
                    expected = check["expected"]
                    if isinstance(expected, (int, float)) and not isinstance(expected, bool) and parm:
                        record["passed"] = math.isclose(float(record["actual"]), expected,
                                                        rel_tol=0, abs_tol=float(check.get("tolerance", 1e-6)))
                    else:
                        record["passed"] = bool(parm) and record["actual"] == expected
                elif kind == "input_equals":
                    inputs = node.inputs() if node else ()
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
            except StudioError:
                raise
            except Exception as exc:
                record["error"] = self.redact(str(exc))[:400]
            records.append(record)
        return records

    def execute(self, args, cancelled):
        script = args.get("script")
        if not isinstance(script, str) or not script.strip() or len(script) > 256000:
            raise StudioError("INVALID_ARGUMENTS", "Supply a HOM script, up to 256000 characters")
        try:
            code = compile(script, "<Big-Chicken HOM batch>", "exec")
        except (SyntaxError, ValueError) as exc:
            raise StudioError("COMPILE_FAILED", str(exc)) from exc
        for field in ("preconditions", "checks", "observe"):
            if not isinstance(args.get(field, []), list) or len(args.get(field, [])) > 64:
                raise StudioError("INVALID_ARGUMENTS", field + " must contain at most 64 items")
        checks = args.get("checks", [])
        # Validate the schema before executing, without cooking postconditions early.
        allowed = {"node_exists", "node_type", "parm_equals", "input_equals", "cook", "geometry_nonempty"}
        for item in checks + args.get("preconditions", []):
            if not isinstance(item, dict) or item.get("kind") not in allowed:
                raise StudioError("INVALID_ARGUMENTS", "Invalid check definition")
        preconditions = self.checks(args.get("preconditions", []))
        if any(not item["passed"] for item in preconditions):
            raise StudioError("PRECONDITION_FAILED", "A target changed since observation", checks=preconditions)
        before = [self.inspect(view) for view in args.get("observe", [])]

        def checkpoint():
            if cancelled():
                raise StudioError("COOPERATIVE_STOP", "Stopped at an explicit script checkpoint")

        checkpoint()
        namespace = {"hou": self.hou, "result": None, "checkpoint": checkpoint,
                     "cancel_requested": cancelled, "__name__": "__studio_hom__"}
        # An undo group is a convenience for the user, never a Python transaction.
        with self.hou.undos.group(str(args.get("label", "Big-Chicken Studio"))[:100]):
            exec(code, namespace, namespace)
        verified = self.checks(checks)
        return {"value": json_value(namespace.get("result")), "checks": verified,
                "observations": {"before": before, "after": [self.inspect(view) for view in args.get("observe", [])]},
                "_checks_outcome": ("passed" if all(item["passed"] for item in verified) else "failed")
                if verified else "not_run"}

    def lookup(self, args):
        if args.get("source", "metadata") == "hom":
            symbol = args.get("symbol", "")
            parts = symbol.removeprefix("hou.").split(".")
            if not 1 <= len(parts) <= 4 or any(not p.isidentifier() or p.startswith("_") for p in parts):
                raise StudioError("INVALID_ARGUMENTS", "Use a public HOM symbol such as hou.Node.createNode")
            obj = self.hou
            for part in parts:
                obj = getattr(obj, part, None)
                if obj is None:
                    raise StudioError("SYMBOL_NOT_FOUND", "HOM symbol is absent in this installation", 404)
            return {"symbol": symbol, "documentation": (getattr(obj, "__doc__", "") or "")[:18000],
                    "houdini_version": self.hou.applicationVersionString()}
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
            self.hou.setFrame(frame)
            settings = viewer.flipbookSettings().stash()
            settings.frameRange((frame, frame))
            settings.output(str(pattern))
            settings.resolution((width, height))
            settings.useResolution(True)
            settings.outputZoom(100)
            settings.useSheetSize(False)
            settings.outputToMPlay(False)
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
