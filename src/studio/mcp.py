"""Seven decision-oriented tools. Scene observations are never silently refreshed."""
from __future__ import annotations

import concurrent.futures
import json
import os
import sys
import threading
import time

from .common import TERMINAL, AppPaths, StudioError, encoded, new_id, read_json
from .http import Client


def schema(properties=None, required=()):
    return {"type": "object", "properties": properties or {}, "required": list(required), "additionalProperties": False}


STRING = {"type": "string"}
ARRAY = {"type": "array", "items": {"type": "object"}, "maxItems": 64}
TOOLS = [
    {"name": "hia_context", "description": "Observe the current HIP, selection and network. Binds subsequent operations to this scene generation. Explicitly call again after a scene replacement.", "inputSchema": schema()},
    {"name": "hia_inspect", "description": "Read targeted live facts in one batch. views: {view: node|parms|children|geometry|checks, path, names?, checks?}. Geometry may cook; all views share the scene queue.", "inputSchema": schema({"views": ARRAY}, ["views"])},
    {"name": "hia_lookup", "description": "Look up installed node/parameter metadata, exact HOM documentation or explicitly imported versioned local documents. No search is required for known deterministic edits.", "inputSchema": schema({"source": {"enum": ["metadata", "hom", "documents"]}, "query": STRING, "category": STRING, "type_name": STRING, "symbol": STRING, "version": STRING})},
    {"name": "hia_execute_hom", "description": "Run a semantic HOM batch against the observed scene. Set result to a JSON value. Optional preconditions/checks: node_exists, node_type, parm_equals, input_equals, cook, geometry_nonempty. Checks use path, parm?, expected?, index?, tolerance?. observe accepts targeted inspect views. General Python has unknown external effects; never blindly retry. checkpoint() cooperatively stops; Undo is not a filesystem transaction.", "inputSchema": schema({"script": {"type": "string", "maxLength": 256000}, "label": STRING, "preconditions": ARRAY, "checks": ARRAY, "observe": ARRAY}, ["script"])},
    {"name": "hia_capture", "description": "Capture the current viewport at a meaningful milestone. Returns native image content. Optional frame and resolution; restores the previous frame. Uses the same scene queue.", "inputSchema": schema({"frame": {"type": "number"}, "resolution": {"type": "array", "items": {"type": "integer"}, "minItems": 2, "maxItems": 2}})},
    {"name": "hia_operation", "description": "Retrieve the SAME operation receipt after a long operation or lost response, read paged details, or request cancellation. Query never reruns HOM. Queued work can be cancelled; running HOM stops only at cooperative boundaries.", "inputSchema": schema({"action": {"enum": ["get", "detail", "cancel", "list"]}, "operation_id": STRING, "offset": {"type": "integer", "minimum": 0}}, ["action"])},
    {"name": "hia_project_memory", "description": "Read workspace decisions or explicitly record, supersede or delete a decision ONLY when the user requests durable memory. Independent of live Houdini. No automatic summaries or embeddings.", "inputSchema": schema({"action": {"enum": ["list", "record", "supersede", "delete"]}, "body": STRING, "record_id": STRING}, ["action"])},
]


class Adapter:
    def __init__(self, runtime_client, bridge_client, identity, owner_id, wait_seconds=8):
        self.runtime, self.bridge = runtime_client, bridge_client
        self.identity, self.owner_id = identity, owner_id
        self.wait_seconds = wait_seconds
        self.scene_epoch = None
        self.lock = threading.Lock()

    def _receipt(self, value):
        if value.get("kind") == "context" and value.get("state") == "finished":
            with self.lock:
                self.scene_epoch = value["result"]["scene_epoch"]
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
        if name == "hia_project_memory":
            value = self.bridge.call("POST", "/memory", args)
            return {"content": [{"type": "text", "text": encoded(value)}]}
        if name == "hia_lookup" and args.get("source") == "documents":
            value = self.bridge.call("POST", "/lookup", args)
            return {"content": [{"type": "text", "text": encoded(value)}]}
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
        with self.lock:
            epoch = self.scene_epoch
        if kind != "context" and not epoch:
            raise StudioError("OBSERVATION_REQUIRED", "Call hia_context before working on a scene", 409)
        op_id = new_id()  # Allocated before transmission and always returned after uncertainty.
        op = {"operation_id": op_id, "workspace_id": self.identity["workspace_id"],
              "runtime_id": self.identity["runtime_id"], "owner_id": self.owner_id,
              "scene_epoch": epoch, "kind": kind, "arguments": args, "label": args.get("label", kind)}
        deadline = time.monotonic() + self.wait_seconds
        try:
            value = self.runtime.call("POST", "/operations", op)
        except StudioError as exc:
            if exc.code != "CONNECTION_LOST":
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
                break
        return self._receipt(value)


def main():
    paths = AppPaths()
    directory = paths.session(os.environ["BCS_SESSION_ID"])
    token = os.environ["BCS_SESSION_TOKEN"]
    identity = read_json(directory / "runtime.json")
    bridge = read_json(directory / "bridge.json")
    adapter = Adapter(Client(identity["url"], token), Client(bridge["url"], token), identity,
                      os.environ["BCS_OWNER_ID"])
    output_lock = threading.Lock()

    def send(value):
        with output_lock:
            sys.stdout.write(encoded(value) + "\n")
            sys.stdout.flush()

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
            error = exc.payload() if isinstance(exc, StudioError) else {"error": {"code": "TOOL_ERROR", "message": str(exc)[:400]}}
            send({"jsonrpc": "2.0", "id": request_id, "result": {"isError": True,
                 "content": [{"type": "text", "text": encoded(error)}]}})

    # A single adapter worker also preserves the observation/write ordering of this conversation.
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as worker:
        for line in sys.stdin:
            if len(line) > 2 * 1024 * 1024:
                continue
            try:
                message = json.loads(line)
                if isinstance(message, dict):
                    worker.submit(process, message)
            except ValueError:
                send({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Invalid JSON"}})


if __name__ == "__main__":
    main()
