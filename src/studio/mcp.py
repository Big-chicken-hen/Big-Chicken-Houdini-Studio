"""Seven decision-oriented tools. Scene observations are never silently refreshed."""
from __future__ import annotations

import json
import os
import sys
import threading
import time

from .common import TERMINAL, AppPaths, StudioError, encoded, new_id, read_json
from .http import MAX_BODY, Client, redact
from .scene import validate_arguments
from .staged import STEP_ID
from .tool_schema import LOOKUP_SCHEMA, schema, validate_schema



STRING = {"type": "string"}
NODE_PATH = {"type": "string", "pattern": "^/", "description": "Absolute Houdini node path; no '..' segments."}
CHECK = {"oneOf": [
    schema({"kind": {"enum": ["node_exists"]}, "path": NODE_PATH,
            "expected": {"type": "boolean", "default": True}}, ["kind", "path"]),
    schema({"kind": {"enum": ["node_type"]}, "path": NODE_PATH,
            "expected": STRING}, ["kind", "path", "expected"]),
    schema({"kind": {"enum": ["parm_equals"]}, "path": NODE_PATH,
            "parm": {"type": "string", "minLength": 1},
            "expected": {"description": "Expected JSON value from parm.eval(); numeric values use absolute tolerance."},
            "tolerance": {"type": "number", "minimum": 0, "default": 1e-6}},
           ["kind", "path", "parm", "expected"]),
    schema({"kind": {"enum": ["input_equals"]}, "path": NODE_PATH,
            "index": {"type": "integer", "minimum": 0, "default": 0},
            "expected": {"oneOf": [NODE_PATH, {"type": "null"}],
                         "description": "Connected source node path, or null for an existing target's unconnected input."}},
           ["kind", "path", "expected"]),
    schema({"kind": {"enum": ["cook"]}, "path": NODE_PATH}, ["kind", "path"]),
    schema({"kind": {"enum": ["geometry_nonempty"]}, "path": NODE_PATH}, ["kind", "path"]),
]}
CHECKS = {"type": "array", "items": {"$ref": "#/$defs/check"}, "maxItems": 64}
VIEW_PATH = {**NODE_PATH, "default": "/obj"}
VIEW = {"oneOf": [
    schema({"view": {"enum": ["node"], "default": "node"}, "path": VIEW_PATH}),
    schema({"view": {"enum": ["parms"]}, "path": VIEW_PATH,
            "names": {"type": "array", "items": {"type": "string", "minLength": 1}, "minItems": 1, "maxItems": 64}},
           ["view", "names"]),
    schema({"view": {"enum": ["children"]}, "path": VIEW_PATH,
            "offset": {"type": "integer", "minimum": 0, "maximum": 1000000, "default": 0},
            "limit": {"type": "integer", "minimum": 1, "maximum": 200, "default": 64}}, ["view"]),
    schema({"view": {"enum": ["parameters"]}, "path": VIEW_PATH,
            "pattern": {"type": "string", "minLength": 1, "maxLength": 128, "default": "*"},
            "offset": {"type": "integer", "minimum": 0, "maximum": 1000000, "default": 0},
            "limit": {"type": "integer", "minimum": 1, "maximum": 128, "default": 64},
            "include_values": {"type": "boolean", "default": False}}, ["view"]),
    schema({"view": {"enum": ["geometry"]}, "path": VIEW_PATH,
            "owners": {"type": "array", "items": {"enum": ["point", "primitive", "vertex", "detail"]},
                       "minItems": 1, "maxItems": 4},
            "attributes": {"type": "array", "items": {"type": "string", "minLength": 1, "maxLength": 128},
                           "minItems": 1, "maxItems": 16},
            "samples": {"type": "integer", "minimum": 0, "maximum": 16, "default": 0},
            "include_groups": {"type": "boolean", "default": False},
            "group_limit": {"type": "integer", "minimum": 1, "maximum": 64, "default": 32}}, ["view"]),
    schema({"view": {"enum": ["checks"]}, "path": VIEW_PATH, "checks": CHECKS}, ["view"]),
]}
SCENE_DEFINITIONS = {"check": CHECK, "view": VIEW}
VIEWS = {"type": "array", "items": {"$ref": "#/$defs/view"}, "minItems": 1, "maxItems": 32}
OBSERVE = {"type": "array", "items": {"$ref": "#/$defs/view"}, "maxItems": 64,
           "description": "Reads BEFORE and AFTER the script. Targets must already exist. For nodes created by this batch use post-execution checks or result readback."}
OBSERVE_AFTER = {"type": "array", "items": {"$ref": "#/$defs/view"}, "maxItems": 16,
                 "description": "Read only AFTER execution; targets may be created by this script. Partial failure permits passive node/children/parameter metadata only; cancellation or scene replacement skips further reads."}
EXECUTE_FIELDS = {"script": {"type": "string", "minLength": 1, "maxLength": 256000}, "label": STRING,
                  "preconditions": CHECKS, "checks": CHECKS, "observe": OBSERVE, "observe_after": OBSERVE_AFTER}
STEP_SCHEMA = schema({**EXECUTE_FIELDS, "id": {"type": "string", "pattern": STEP_ID},
    "label": {"type": "string", "maxLength": 160}, "observe": {**OBSERVE, "maxItems": 8},
    "observe_after": {**OBSERVE_AFTER, "maxItems": 8}}, ["id", "label", "script"])
EXECUTE_SCHEMA = {"type": "object", "$defs": SCENE_DEFINITIONS, "oneOf": [schema(EXECUTE_FIELDS, ["script"]),
    schema({"label": {"type": "string", "maxLength": 160}, "inputs": {"type": "object"},
            "steps": {"type": "array", "items": STEP_SCHEMA, "minItems": 2, "maxItems": 8}}, ["steps"])]}
CAPTURE_COMMON = {"frame": {"type": "number"}, "resolution": {"type": "array", "items": {
    "type": "integer", "minimum": 64, "maximum": 2560}, "minItems": 2, "maxItems": 2}}
CAPTURE_BOUNDS = {"type": "array", "items": {"type": "number"}, "minItems": 6, "maxItems": 6,
    "description": "Review only: min XYZ then max XYZ in the current view's scene space. Mutually exclusive with target. Use target for backend conversion of object-local bounds."}
CAPTURE_TARGET = {"oneOf": [schema({"paths": {"type": "array", "items": NODE_PATH, "minItems": 1, "maxItems": 8}}, ["paths"]),
    schema({"selection": {"type": "boolean", "enum": [True]}}, ["selection"])],
    "description": "SOP geometry or an OBJ geometry object's display SOP. selection means current node selection, resolved when the queued operation starts. Framing only, never isolation."}
CAPTURE_VIEWS = {"enum": ["front", "right", "top", "three_quarter"]}
CAPTURE_SCHEMA = {"type": "object", "oneOf": [
    schema({**CAPTURE_COMMON, "purpose": {"enum": ["diagnostic"], "default": "diagnostic"},
            "view": {"enum": ["current"], "default": "current"}}),
    schema({**CAPTURE_COMMON, "purpose": {"enum": ["review"]}, "bounds": CAPTURE_BOUNDS,
            "view": {"enum": ["current"], "default": "current"}}, ["purpose"]),
    schema({**CAPTURE_COMMON, "purpose": {"enum": ["review"]}, "target": CAPTURE_TARGET,
            "view": {"enum": ["current", *CAPTURE_VIEWS["enum"]], "default": "current"}}, ["purpose", "target"]),
    schema({**CAPTURE_COMMON, "purpose": {"enum": ["review"]}, "bounds": CAPTURE_BOUNDS,
            "view": CAPTURE_VIEWS}, ["purpose", "bounds", "view"]),
]}
TOOLS = [
    {"name": "hia_context", "description": "Low-cost working context: saved-HIP facts, bounded selected-node identities, observed network child category/editability and time/Take facts. Network source/fallback is explicit, not guaranteed active focus. No geometry, whole-graph or parameter-value scan. Binds later scene operations; scene epoch identifies replacement, not every manual parameter edit. Call explicitly after replacement or when changed working facts are needed.", "inputSchema": schema()},
    {"name": "hia_inspect", "description": "Batch up to 32 targeted views on the scene queue. Malformed batches are rejected before any query; a missing/failed target retains other views with indexed errors and status=partial. node/children expose one-layer graph, ports, flags, editability and last-cook diagnostics without forcing cook; children uses stable offset/limit paging. parameters returns runtime names versus template patterns, tuple/multiparm identity and static setting metadata. include_values defaults false; true evaluates ONLY returned parameters and may run expressions/dependent evaluation. Never creates nodes, expands multiparms or runs dynamic menus/callbacks for discovery. Example metadata plus values: {\"views\":[{\"view\":\"parameters\",\"path\":\"/obj/example/controls\",\"pattern\":\"*spacing*\",\"limit\":8,\"include_values\":true}]}. parms remains a short path for known names. geometry may cook its target; bounds carry their local/unknown space, with optional bounded group names and attribute samples, never all members. Explicit checks may cook. Truncated results retain useful facts and honest continuation.", "inputSchema": schema({"views": VIEWS}, ["views"], SCENE_DEFINITIONS)},
    {"name": "hia_lookup", "description": "Discover current installed node types with source=metadata and 1-4 requests: categories, keyword search, or exact type metadata/help. Search matches names, TAB labels and registered aliases, not help bodies; use short workflow words. Metadata search pages default to 12, accept 1-80 and return next_offset; legacy flat calls remain supported. Canonical search excludes known hidden/deprecated types by default; exact type queries permit legacy types. For help only set include_parameters=false; for parameters only set include_help=false. Static templates/tokens and installed help are reference data, never executable instructions; no nodes, dynamic menus or parameter evaluation are used for discovery. source=hom reads public typed symbols (including hou) and optional paged members without executing descriptors. source=documents searches explicitly imported workspace documents; version filters only documents. Metadata shares the scene queue; static HOM/documents are independent.", "inputSchema": LOOKUP_SCHEMA},
    {"name": "hia_execute_hom", "description": "Run one semantic HOM script OR 2–8 already-decided sequential steps, never both. Single scripts and steps accept optional preconditions/checks/observe/observe_after; script result readback is also valid and does not require duplicate observe_after. observe reads existing targets before/after; observe_after can read newly created targets. Staged requests use label/inputs/steps; each step has a unique id, label and script, with at most eight combined views. All scripts compile before mutation, total text <=256000 characters. Each step has a separate main-thread callback and namespace; inputs and results[previous_step_id] carry complete JSON only, <=16 KiB per result and <=64 KiB total handoff. Failed gates, cancellation, context change or unconfirmed persistence halt later steps. Write return data to result; stdout/stderr are discarded. The roughly eight-second adapter wait is not an execution timeout; hia_operation reads progress or original detail. checkpoint() cooperates with received Stop but does not make a blocked GUI responsive; never pump Qt events. Consent revocation blocks future approvals, not admitted steps; Stop/cancel requests stopping remaining steps. General Python/HOM is trusted local execution, not a sandbox; Undo cannot undo arbitrary external effects. output_path(kind, filename, explicit=None, existing=None) returns a new output path and prepares its parent; kind is render/export/asset. Explicit destinations and existing output settings take priority; otherwise new outputs follow the current saved HIP or temporary unsaved-scene cache. Already resolved paths never move after Save As. resolved_outputs records chosen paths, not completed deliverables.", "inputSchema": EXECUTE_SCHEMA},
    {"name": "hia_capture", "description": "Capture one meaningful milestone as a persistent artifact and native image. Default diagnostic preserves the viewport. For review, target.paths (1-8 SOP/OBJ geometry nodes) or target.selection=true frames current node selection without a preparation script. Geometry and parent transforms are read at the requested frame. target and bounds are mutually exclusive; named front/right/top/three_quarter views require review and target or bounds. Named directions use world axes; unsupported spaces/views fail explicitly. Target is framing only: no node flags, selection, network, materials or camera-node changes, no asset hiding or visibility guarantee; non-display SOP targets return a warning and actual display source. Review temporarily hides known grid/axis decorations only. Frame, viewpoint/projection and camera binding/lock are restored, with capture and restore errors separate. A viewport image does not prove final Karma quality, other frames or simulation correctness. Re-query the original operation/image; do not recapture to recover a response.", "inputSchema": CAPTURE_SCHEMA},
    {"name": "hia_operation", "description": "Query the SAME receipt for queued/running, unknown, partial or detailed results. Staged progress preserves each step's facts; detail with step_id reads a closed step without replay. Whole staged detail is paged only after termination; running progress uses get. Never concatenate changing running whole-detail pages. get/detail/list cannot execute or resume work. cancel stops queued work or future steps at cooperative boundaries; cancellation is not rollback. After reviewing prior facts and current targets, submit a NEW targeted correction, not the old batch again.", "inputSchema": schema({"action": {"enum": ["get", "detail", "cancel", "list"]}, "operation_id": STRING, "offset": {"type": "integer", "minimum": 0}, "step_id": {"type": "string", "pattern": STEP_ID}}, ["action"])},
    {"name": "hia_project_memory", "description": "Read workspace decisions or explicitly record, supersede or delete a decision ONLY when the user requests durable memory. Independent of live Houdini. No automatic summaries or embeddings.", "inputSchema": schema({"action": {"enum": ["list", "record", "supersede", "delete"]}, "body": STRING, "record_id": STRING}, ["action"])},
]


class Adapter:
    def __init__(self, runtime_client, bridge_client, identity, owner_id, wait_seconds=8, runtime_loader=None):
        self.runtime, self.bridge = runtime_client, bridge_client
        self.identity, self.owner_id = identity, owner_id
        self.wait_seconds = wait_seconds
        self.scene_epoch = None
        self.context_operation_id = None
        self.lock = threading.Lock()
        self.runtime_loader = runtime_loader

    def _ensure_runtime(self):
        if self.runtime is None:
            self.runtime, self.identity = self.runtime_loader()

    def _receipt(self, value):
        result = value.get("result")
        epoch = result.get("scene_epoch") if isinstance(result, dict) else None
        if (value.get("kind") == "context" and value.get("state") == "finished" and
                value.get("runtime_id") == self.identity["runtime_id"] and
                value.get("owner_id") == self.owner_id and isinstance(epoch, str) and epoch):
            with self.lock:
                if self.context_operation_id is not None and value.get("operation_id") == self.context_operation_id:
                    self.scene_epoch = epoch
        content = [{"type": "text", "text": encoded(value)}]
        image_unavailable = False
        if value.get("kind") == "capture" and isinstance(result, dict):
            artifact_id = result.get("artifact_id")
            if artifact_id:
                try:
                    from .common import identifier
                    image = self.runtime.call("GET", "/artifacts/" + identifier(artifact_id))
                    content.append({"type": "image", "mimeType": image["mime_type"], "data": image["data"]})
                except StudioError as exc:
                    image_unavailable = True
                    content.append({"type": "text", "text": encoded(exc.payload())})
        # A valid image can accompany a failed restoration. Missing artifact bytes
        # fail this retrieval without rewriting the original operation's receipt.
        return {"content": content, "isError": image_unavailable or value.get("state") in {"failed", "rejected", "unknown"}}

    def call(self, name, args):
        tool = next((t for t in TOOLS if t["name"] == name), None)
        if tool is None:
            raise StudioError("UNKNOWN_TOOL", "Unknown tool")
        validate_schema(args, tool["inputSchema"])
        if name == "hia_project_memory":
            value = self.bridge.call("POST", "/memory", args)
            return {"content": [{"type": "text", "text": encoded(value)}]}
        if name == "hia_lookup" and args.get("source") == "documents":
            if {"members", "offset", "limit"}.intersection(args):
                raise StudioError("INVALID_TOOL_CALL", "Member discovery applies only to HOM symbols")
            value = self.bridge.call("POST", "/lookup", args)
            return {"content": [{"type": "text", "text": encoded(value)}]}
        self._ensure_runtime()
        if name == "hia_lookup" and args.get("source") == "hom":
            validate_arguments("lookup", args)
            return {"content": [{"type": "text", "text": encoded(self.runtime.call("POST", "/lookup", args))}]}
        if name == "hia_operation":
            action = args.get("action")
            if "step_id" in args and action != "detail":
                raise StudioError("INVALID_ARGUMENTS", "step_id is only available for original step detail")
            if action == "list":
                value = self.runtime.call("GET", "/operations")
            else:
                from .common import identifier
                op_id = identifier(args.get("operation_id"))
                path = "/operations/" + op_id
                if action == "detail":
                    path += "/detail?offset=" + str(max(0, int(args.get("offset", 0))))
                    if "step_id" in args:
                        from .staged import step_id
                        path += "&step_id=" + step_id(args["step_id"])
                elif action == "cancel":
                    path += "/cancel"
                elif action != "get":
                    raise StudioError("INVALID_ARGUMENTS", "Unknown operation action")
                value = self.runtime.call("POST" if action == "cancel" else "GET", path,
                                          {} if action == "cancel" else None)
            return self._receipt(value)
        kind = {"hia_context": "context", "hia_inspect": "inspect", "hia_lookup": "lookup",
                "hia_execute_hom": "execute", "hia_capture": "capture"}.get(name)
        if kind is None:
            raise StudioError("UNKNOWN_TOOL", "Unknown tool")
        validate_arguments(kind, args)
        with self.lock:
            epoch = self.scene_epoch
        if kind not in {"context", "lookup"} and not epoch:
            raise StudioError("OBSERVATION_REQUIRED", "Call hia_context before working on a scene", 409)
        op_id = new_id()  # Allocated before transmission and always returned after uncertainty.
        if kind == "context":
            with self.lock:
                # Only the latest context requested by this adapter may bind its writes.
                self.context_operation_id = op_id
        op = {"operation_id": op_id, "workspace_id": self.identity["workspace_id"],
              "runtime_id": self.identity["runtime_id"], "owner_id": self.owner_id,
              "scene_epoch": epoch, "kind": kind, "arguments": args, "label": args.get("label", kind)}
        deadline = time.monotonic() + self.wait_seconds
        try:
            value = self.runtime.call("POST", "/operations", op)
        except StudioError as exc:
            if exc.status < 500 and exc.code not in {"CONNECTION_LOST", "RESPONSE_LIMIT"}:
                raise
            try:
                value = self.runtime.call("GET", "/operations/" + op_id)
            except StudioError:
                return self._receipt({"operation_id": op_id, "state": "unknown", "mutation_outcome": "unknown",
                                      "automatic_retry_safe": False, "message": "Submission was not confirmed; query this ID. Do not replay the script."})
        while value.get("state") not in TERMINAL and time.monotonic() < deadline:
            time.sleep(0.08)
            try:
                value = self.runtime.call("GET", "/operations/" + op_id)
            except StudioError:
                value = {"operation_id": op_id, "state": "unknown", "mutation_outcome": "unknown",
                         "receipt_confirmed": False, "last_confirmed_state": value.get("state"),
                         "automatic_retry_safe": False,
                         "message": "The latest receipt could not be read; query this ID. Do not replay the script."}
                break
        return self._receipt(value)



def serve_stdio(adapter, source, output, token=""):

    def send(value):
        output.write(encoded(redact(value, token)) + "\n")
        output.flush()

    def process(message):
        request_id, method = message.get("id"), message.get("method")
        if request_id is None:
            return
        try:
            if method == "initialize":
                result = {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}},
                          "serverInfo": {"name": "big-chicken-studio", "version": "0.1.0"}}
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": TOOLS}
            elif method == "tools/call":
                params = message.get("params", {})
                name, args = params.get("name"), params.get("arguments", {})
                tool = next((t for t in TOOLS if t["name"] == name), None)
                if tool is None or not isinstance(args, dict):
                    raise StudioError("INVALID_TOOL_CALL", "Unknown tool or invalid arguments")
                definition = tool["inputSchema"]
                validate_schema(args, definition)
                result = adapter.call(name, args)
            else:
                send({"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": "Unknown method"}})
                return
            send({"jsonrpc": "2.0", "id": request_id, "result": result})
        except Exception as exc:
            error = exc.payload() if isinstance(exc, StudioError) else {"error": {"code": "TOOL_ERROR", "message": "Tool request could not be completed"}}
            send({"jsonrpc": "2.0", "id": request_id, "result": {"isError": True,
                 "content": [{"type": "text", "text": encoded(error)}]}})

    # Direct processing provides pipe backpressure and preserves observation/write ordering.
    # No executor queue; even a missing newline cannot allocate an unbounded line.
    while True:
        line = source.readline(MAX_BODY + 1)
        if not line:
            return
        if len(line) > MAX_BODY:
            while line and not line.endswith(b"\n"):
                line = source.readline(MAX_BODY + 1)
            send({"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Request exceeds 2 MB"}})
            continue
        try:
            message = json.loads(line.decode("utf-8"), parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
            if not isinstance(message, dict):
                raise ValueError()
            process(message)
        except (ValueError, RecursionError):
            send({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Invalid JSON"}})


def main():
    # MCP wire encoding is UTF-8 even when Windows or the launcher selects a legacy code page.
    sys.stdout.reconfigure(encoding="utf-8", errors="strict", newline="\n")
    paths = AppPaths()
    directory = paths.session(os.environ["BCS_SESSION_ID"])
    token = os.environ["BCS_SESSION_TOKEN"]
    bridge = read_json(directory / "bridge.json")
    def load_runtime():
        try:
            identity = read_json(directory / "runtime.json")
        except (OSError, ValueError):
            raise StudioError("HOUDINI_STARTING", "Houdini has not connected yet", 503)
        if (identity.get("launcher_session_id") != os.environ["BCS_SESSION_ID"] or
                identity.get("workspace_id") != os.environ["BCS_WORKSPACE_ID"]):
            raise StudioError("RUNTIME_MISMATCH", "Runtime descriptor belongs to another session", 409)
        return Client(identity["url"], token), identity
    adapter = Adapter(None, Client(bridge["url"], token), {}, os.environ["BCS_OWNER_ID"], runtime_loader=load_runtime)
    serve_stdio(adapter, sys.stdin.buffer, sys.stdout, token)


if __name__ == "__main__":
    main()
