"""Houdini runtime startup and durable operation routes."""
from __future__ import annotations

import base64
import os

from .common import AppPaths, StudioError, atomic_json, identifier
from .http import serve
from .ledger import Ledger
from .runtime import OperationRuntime
from .scene import HoudiniScene

_session = None


def runtime_router(runtime):
    def route(method, path, query, body):
        if method == "GET" and path == "/health":
            return runtime.health()
        if method == "GET" and path == "/operations":
            return {"operations": runtime.ledger.recent()}
        if method == "POST" and path == "/operations":
            return runtime.submit(body)
        parts = path.strip("/").split("/")
        if parts[0] == "operations" and len(parts) >= 2:
            op_id = identifier(parts[1])
            if method == "GET" and len(parts) == 2:
                return runtime.ledger.get(op_id)
            if method == "GET" and parts[2:] == ["detail"]:
                return runtime.ledger.detail(op_id, int(query.get("offset", [0])[0]))
            if method == "POST" and parts[2:] == ["cancel"]:
                return runtime.cancel(op_id)
        if method == "POST" and path == "/owner/stop":
            return runtime.stop_owner(body["owner_id"])
        if method == "POST" and path == "/owner/resume":
            return runtime.resume_owner(body["owner_id"])
        if method == "GET" and len(parts) == 2 and parts[0] == "artifacts":
            return {"mime_type": "image/png", "data": base64.b64encode(
                runtime.scene.artifact(identifier(parts[1]))).decode("ascii")}
        raise StudioError("ROUTE_NOT_FOUND", "Unknown runtime route", 404)
    return route


def start():
    global _session
    if _session is not None:
        return _session
    import hou
    import hdefereval
    paths = AppPaths()
    workspace_id, session_id = os.environ["BCS_WORKSPACE_ID"], os.environ["BCS_SESSION_ID"]
    token = os.environ["BCS_SESSION_TOKEN"]
    scene = HoudiniScene(hou, paths.session(session_id) / "captures", secrets=(token,))
    ledger = Ledger(paths.workspace(workspace_id) / "operations.sqlite")
    runtime = OperationRuntime(ledger, scene, hdefereval.executeInMainThreadWithResult,
                               workspace_id=workspace_id, session_id=session_id)
    server = serve(runtime_router(runtime), token)
    atomic_json(paths.session(session_id) / "runtime.json", {
        "url": "http://127.0.0.1:" + str(server.server_port),
        "runtime_id": runtime.runtime_id, "workspace_id": workspace_id,
        "launcher_session_id": session_id, "houdini_pid": os.getpid()})
    _session = (runtime, server)
    return _session
