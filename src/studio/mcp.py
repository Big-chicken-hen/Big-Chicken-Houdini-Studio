"""Seven decision-oriented tools. Scene observations are never silently refreshed."""
from __future__ import annotations

import json
import math
import os
import re
import sys
import threading
import time

from .common import TERMINAL, AppPaths, StudioError, encoded, new_id, read_json
from .http import MAX_BODY, Client, redact
from .scene import validate_arguments


def schema(properties=None, required=(), definitions=None):
    value = {"type": "object", "properties": properties or {}, "required": list(required), "additionalProperties": False}
    if definitions:
        value["$defs"] = definitions
    return value


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
            "limit": {"type": "integer", "minimum": 1, "maximum": 200, "default": 64}}, ["view"]),
    schema({"view": {"enum": ["parameters"]}, "path": VIEW_PATH,
            "pattern": {"type": "string", "minLength": 1, "maxLength": 128, "default": "*"},
            "offset": {"type": "integer", "minimum": 0, "maximum": 1000000, "default": 0},
            "limit": {"type": "integer", "minimum": 1, "maximum": 128, "default": 64}}, ["view"]),
    schema({"view": {"enum": ["geometry"]}, "path": VIEW_PATH,
            "owners": {"type": "array", "items": {"enum": ["point", "primitive", "vertex", "detail"]},
                       "minItems": 1, "maxItems": 4},
            "attributes": {"type": "array", "items": {"type": "string", "minLength": 1, "maxLength": 128},
                           "minItems": 1, "maxItems": 16},
            "samples": {"type": "integer", "minimum": 0, "maximum": 16, "default": 0}}, ["view"]),
    schema({"view": {"enum": ["checks"]}, "path": VIEW_PATH, "checks": CHECKS}, ["view"]),
]}
SCENE_DEFINITIONS = {"check": CHECK, "view": VIEW}
VIEWS = {"type": "array", "items": {"$ref": "#/$defs/view"}, "minItems": 1, "maxItems": 32}
OBSERVE = {"type": "array", "items": {"$ref": "#/$defs/view"}, "maxItems": 64,
           "description": "Reads BEFORE and AFTER the script. Targets must already exist. For nodes created by this batch use post-execution checks or result readback."}
TOOLS = [
    {"name": "hia_context", "description": "Observe the current HIP, selection and network. Binds subsequent operations to this scene generation. Explicitly call again after a scene replacement.", "inputSchema": schema()},
    {"name": "hia_inspect", "description": "Read targeted live facts in one batch. parameters discovers actual instance names, native template metadata and multiparm indices without evaluating values; parms reads named values. geometry reports owner/type/tuple metadata and optional bounded element samples (arrays/dicts metadata only); may cook. All views share the scene queue.", "inputSchema": schema({"views": VIEWS}, ["views"], SCENE_DEFINITIONS)},
    {"name": "hia_lookup", "description": "Look up installed node/parameter metadata, exact HOM documentation or imported versioned documents. Live metadata uses the HOM queue without requiring a scene observation. Docstrings and documents bypass it. No search is required for known deterministic edits.", "inputSchema": schema({"source": {"enum": ["metadata", "hom", "documents"]}, "query": STRING, "category": STRING, "type_name": STRING, "symbol": STRING, "version": STRING})},
    {"name": "hia_execute_hom", "description": "Run a semantic HOM batch against the observed scene. Set result to a JSON value. Preconditions run before the script; checks run after. observe reads BEFORE and AFTER, so targets must already exist; use checks/result readback for newly created nodes. General Python has unknown external effects; never blindly retry. checkpoint() cooperatively stops; Undo is not a filesystem transaction.", "inputSchema": schema({"script": {"type": "string", "minLength": 1, "maxLength": 256000}, "label": STRING, "preconditions": CHECKS, "checks": CHECKS, "observe": OBSERVE}, ["script"], SCENE_DEFINITIONS)},
    {"name": "hia_capture", "description": "Capture the current viewport at a meaningful milestone. Returns native image content. Optional frame and resolution; restores the previous frame. Disables inherited simulation initialization and motion blur on copied flipbook settings. Uses the same scene queue.", "inputSchema": schema({"frame": {"type": "number"}, "resolution": {"type": "array", "items": {"type": "integer", "minimum": 64, "maximum": 2560}, "minItems": 2, "maxItems": 2}})},
    {"name": "hia_operation", "description": "Retrieve the SAME operation receipt after a long operation or lost response, read paged details, or request cancellation. Query never reruns HOM. Queued work can be cancelled; running HOM stops only at cooperative boundaries.", "inputSchema": schema({"action": {"enum": ["get", "detail", "cancel", "list"]}, "operation_id": STRING, "offset": {"type": "integer", "minimum": 0}}, ["action"])},
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
            value = self.bridge.call("POST", "/lookup", args)
            return {"content": [{"type": "text", "text": encoded(value)}]}
        self._ensure_runtime()
        if name == "hia_lookup" and args.get("source") == "hom":
            validate_arguments("lookup", args)
            return {"content": [{"type": "text", "text": encoded(self.runtime.call("POST", "/lookup", args))}]}
        if name == "hia_operation":
            action = args.get("action")
            if action == "list":
                value = self.runtime.call("GET", "/operations")
            else:
                from .common import identifier
                op_id = identifier(args.get("operation_id"))
                path = "/operations/" + op_id
                if action == "detail":
                    path += "/detail?offset=" + str(max(0, int(args.get("offset", 0))))
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


def validate_schema(value, definition, definitions=None):
    definitions = definitions if definitions is not None else definition.get("$defs", {})
    if "$ref" in definition:
        return validate_schema(value, definitions[definition["$ref"].removeprefix("#/$defs/")], definitions)
    if "oneOf" in definition:
        matches = 0
        for option in definition["oneOf"]:
            try:
                validate_schema(value, option, definitions)
                matches += 1
            except StudioError:
                pass
        if matches != 1:
            raise StudioError("INVALID_TOOL_CALL", "Argument must match one declared check or view shape")
        return
    kind = definition.get("type")
    valid = {"object": lambda: isinstance(value, dict), "array": lambda: isinstance(value, list),
             "string": lambda: isinstance(value, str), "integer": lambda: type(value) is int,
             "number": lambda: type(value) in (int, float) and math.isfinite(value),
             "boolean": lambda: type(value) is bool, "null": lambda: value is None}
    if (kind in valid and not valid[kind]()) or ("enum" in definition and value not in definition["enum"]):
        raise StudioError("INVALID_TOOL_CALL", "Tool argument type or value does not match the schema")
    if kind == "object":
        properties = definition.get("properties", {})
        if ((definition.get("additionalProperties") is False and set(value) - set(properties)) or
                set(definition.get("required", [])) - set(value)):
            raise StudioError("INVALID_TOOL_CALL", "Tool arguments do not match the schema")
        for key in value.keys() & properties.keys():
            validate_schema(value[key], properties[key], definitions)
    if kind == "array":
        if not definition.get("minItems", 0) <= len(value) <= definition.get("maxItems", MAX_BODY):
            raise StudioError("INVALID_TOOL_CALL", "Invalid array length")
        for item in value:
            validate_schema(item, definition.get("items", {}), definitions)
    if kind == "string":
        if not definition.get("minLength", 0) <= len(value) <= definition.get("maxLength", MAX_BODY):
            raise StudioError("INVALID_TOOL_CALL", "Invalid string length")
        if "pattern" in definition and re.search(definition["pattern"], value) is None:
            raise StudioError("INVALID_TOOL_CALL", "Node paths must be absolute")
    if kind in {"number", "integer"} and not definition.get("minimum", -math.inf) <= value <= definition.get("maximum", math.inf):
        raise StudioError("INVALID_TOOL_CALL", "Number is outside the permitted range")


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
                if set(args) - set(definition["properties"]) or set(definition["required"]) - set(args):
                    raise StudioError("INVALID_TOOL_CALL", "Tool arguments do not match the schema")
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
            message = json.loads(line, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
            if not isinstance(message, dict):
                raise ValueError()
            process(message)
        except (ValueError, RecursionError):
            send({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Invalid JSON"}})


def main():
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
