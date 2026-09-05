"""Seven decision-oriented tools. Scene observations are never silently refreshed."""
from __future__ import annotations

import json
import math
import os
import sys
import threading
import time

from .common import TERMINAL, AppPaths, StudioError, encoded, new_id, read_json
from .http import MAX_BODY, Client, redact
from .scene import validate_arguments


def schema(properties=None, required=()):
    return {"type": "object", "properties": properties or {}, "required": list(required), "additionalProperties": False}


STRING = {"type": "string"}
ARRAY = {"type": "array", "items": {"type": "object"}, "maxItems": 64}
TOOLS = [
    {"name": "hia_context", "description": "Observe the current HIP, selection and network. Binds subsequent operations to this scene generation. Explicitly call again after a scene replacement.", "inputSchema": schema()},
    {"name": "hia_inspect", "description": "Read targeted live facts in one batch. views: {view: node|parms|children|geometry|checks, path, names?, checks?}. Geometry may cook; all views share the scene queue.", "inputSchema": schema({"views": ARRAY}, ["views"])},
    {"name": "hia_lookup", "description": "Look up installed node/parameter metadata, exact HOM documentation or imported versioned documents. Live metadata uses the HOM queue without requiring a scene observation. Docstrings and documents bypass it. No search is required for known deterministic edits.", "inputSchema": schema({"source": {"enum": ["metadata", "hom", "documents"]}, "query": STRING, "category": STRING, "type_name": STRING, "symbol": STRING, "version": STRING})},
    {"name": "hia_execute_hom", "description": "Run a semantic HOM batch against the observed scene. Set result to a JSON value. Optional preconditions/checks: node_exists, node_type, parm_equals, input_equals, cook, geometry_nonempty. Checks use path, parm?, expected?, index?, tolerance?. observe accepts targeted inspect views. General Python has unknown external effects; never blindly retry. checkpoint() cooperatively stops; Undo is not a filesystem transaction.", "inputSchema": schema({"script": {"type": "string", "maxLength": 256000}, "label": STRING, "preconditions": ARRAY, "checks": ARRAY, "observe": ARRAY}, ["script"])},
    {"name": "hia_capture", "description": "Capture the current viewport at a meaningful milestone. Returns native image content. Optional frame and resolution; restores the previous frame. Uses the same scene queue.", "inputSchema": schema({"frame": {"type": "number"}, "resolution": {"type": "array", "items": {"type": "integer"}, "minItems": 2, "maxItems": 2}})},
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
        if value.get("kind") == "capture" and value.get("state") == "finished":
            artifact_id = value.get("result", {}).get("artifact_id")
            if artifact_id:
                try:
                    image = self.runtime.call("GET", "/artifacts/" + artifact_id)
                    content.append({"type": "image", "mimeType": image["mime_type"], "data": image["data"]})
                except StudioError as exc:
                    content.append({"type": "text", "text": encoded(exc.payload())})
        return {"content": content, "isError": value.get("state") in {"failed", "rejected", "unknown"}}

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


def validate_schema(value, definition):
    kind = definition.get("type")
    valid = {"object": lambda: isinstance(value, dict), "array": lambda: isinstance(value, list),
             "string": lambda: isinstance(value, str), "integer": lambda: type(value) is int,
             "number": lambda: type(value) in (int, float) and math.isfinite(value)}
    if (kind in valid and not valid[kind]()) or ("enum" in definition and value not in definition["enum"]):
        raise StudioError("INVALID_TOOL_CALL", "Tool argument type or value does not match the schema")
    if kind == "object":
        properties = definition.get("properties", {})
        if ((definition.get("additionalProperties") is False and set(value) - set(properties)) or
                set(definition.get("required", [])) - set(value)):
            raise StudioError("INVALID_TOOL_CALL", "Tool arguments do not match the schema")
        for key in value.keys() & properties.keys():
            validate_schema(value[key], properties[key])
    if kind == "array":
        if not definition.get("minItems", 0) <= len(value) <= definition.get("maxItems", MAX_BODY):
            raise StudioError("INVALID_TOOL_CALL", "Invalid array length")
        for item in value:
            validate_schema(item, definition.get("items", {}))
    if kind == "string" and len(value) > definition.get("maxLength", MAX_BODY):
        raise StudioError("INVALID_TOOL_CALL", "String is too long")
    if kind in {"number", "integer"} and value < definition.get("minimum", -math.inf):
        raise StudioError("INVALID_TOOL_CALL", "Number is below the minimum")


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
