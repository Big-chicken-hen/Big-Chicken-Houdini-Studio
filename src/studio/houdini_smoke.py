"""Opt-in node smoke in a newly launched, dedicated Houdini GUI workspace.

``python -m studio.houdini_smoke prepare`` creates only a not-run manifest.
Inside that workspace's new GUI, ``start()`` returns without blocking Qt.
Only the production MCP/runtime queue touches the scene. No HIP replacement,
capture, script replay, model request, or automatic invocation at startup.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import queue
import subprocess
import threading
import time

from .common import TERMINAL, AppPaths, atomic_json, identifier, new_id, read_json
from .http import Client, redact
from .launcher import helper_environment, hidden_flags
from .workspace import Workspaces

_running = threading.Lock()
_panel = None  # Real registered QWidget; only access it on Houdini's GUI thread.
_pane = None


class SmokeFailure(RuntimeError):
    """A bounded diagnostic written by this harness, without raw host exceptions."""


def prepare(paths=None):
    paths = paths or AppPaths()
    run_id = new_id()
    workspace = Workspaces(paths).create("Houdini GUI smoke " + run_id[:8])
    marker = {"purpose": "houdini-gui-smoke", "workspace_id": workspace["workspace_id"], "run_id": run_id}
    folder = paths.local("houdini-smoke", run_id)
    folder.mkdir(parents=True, exist_ok=False)
    atomic_json(paths.workspace(workspace["workspace_id"]) / "gui-smoke.json", marker)
    atomic_json(folder / "report.json", {**marker, "status": "not_run"})
    return {**marker, "status": "not_run", "report": str(folder / "report.json")}


def validate_session(marker, launch, identity, environment, pid):
    workspace_id, session_id = environment["BCS_WORKSPACE_ID"], environment["BCS_SESSION_ID"]
    identifier(marker.get("run_id"))
    if marker.get("purpose") != "houdini-gui-smoke" or marker.get("workspace_id") != workspace_id:
        raise SmokeFailure("Use a dedicated workspace created by houdini_smoke prepare")
    for value in (launch, identity):
        if value.get("workspace_id") != workspace_id or value.get("launcher_session_id") != session_id:
            raise SmokeFailure("Launch and runtime identities must match this workspace and session")
    if launch.get("hip") or identity.get("houdini_pid") != pid:
        raise SmokeFailure("Use this dedicated workspace's new GUI process without an initial HIP")


def example_batch(root):
    if not root.startswith("/obj/bcs_smoke_") or not root[5:].isidentifier():
        raise ValueError("Expected a unique owned smoke root")
    return "\n".join([
        "from PySide6 import QtCore, QtWidgets",
        "assert hou.isUIAvailable(), 'A real Houdini GUI is required'",
        "assert QtCore.QThread.currentThread() == QtWidgets.QApplication.instance().thread()",
        "assert hou.hipFile.isNewFile() and not hou.hipFile.hasUnsavedChanges(), 'Use a fresh empty GUI'",
        "assert not hou.node('/obj').children(), 'Do not touch an existing scene'",
        f"assert hou.node({root!r}) is None, 'Do not replay this creation'",
        f"g = hou.node('/obj').createNode('geo', {root.rsplit('/', 1)[-1]!r}, run_init_scripts=False)",
        "b = g.createNode('box', 'source_box')",
        "b.parmTuple('size').set((2, 2, 2))",
        "w = g.createNode('attribwrangle', 'stamp_attribute')",
        "w.setInput(0, b)",
        "w.parm('snippet').set('f@studio_smoke = 1.0;')",
        "o = g.createNode('null', 'OUT_SMOKE')",
        "o.setInput(0, w)",
        "o.setDisplayFlag(True)",
        "o.setRenderFlag(True)",
        "g.layoutChildren()",
        "geo = o.geometry()",
        "attribute = geo.findPointAttrib('studio_smoke')",
        "result = {'root': g.path(), 'main_thread': True, 'size': list(b.parmTuple('size').eval()),",
        "          'points': geo.intrinsicValue('pointcount'), 'primitives': geo.intrinsicValue('primitivecount'),",
        "          'attribute_values': sorted(set(geo.pointFloatAttribValues('studio_smoke'))) if attribute else [],",
        "          'errors': list(o.errors())}",
    ])


def creation_arguments(root):
    return {"script": example_batch(root), "label": "GUI smoke: Box size 2, connections and attribute",
            "checks": [{"kind": "parm_equals", "path": root + "/source_box", "parm": "size" + axis,
                        "expected": 2} for axis in "xyz"] + [
                {"kind": "input_equals", "path": root + "/stamp_attribute", "index": 0,
                 "expected": root + "/source_box"},
                {"kind": "input_equals", "path": root + "/OUT_SMOKE", "index": 0,
                 "expected": root + "/stamp_attribute"},
                {"kind": "geometry_nonempty", "path": root + "/OUT_SMOKE"}]}


def tool_value(result):
    content = result.get("content", [])
    if not content or content[0].get("type") != "text":
        raise SmokeFailure("MCP did not return a text receipt")
    value = json.loads(content[0]["text"])
    if not isinstance(value, dict) or not value.get("operation_id"):
        raise SmokeFailure("MCP did not return an operation ID; do not replay the script")
    identifier(value["operation_id"])
    return value


def verify_created(receipt, root):
    value = receipt.get("result", {}).get("value", {})
    if (receipt.get("state") != "finished" or receipt.get("mutation_outcome") != "completed" or
            receipt.get("checks_outcome") != "passed" or value.get("root") != root or
            value.get("main_thread") is not True or value.get("size") != [2, 2, 2] or
            value.get("points", 0) <= 0 or value.get("primitives", 0) <= 0 or
            value.get("attribute_values") != [1.0] or value.get("errors") != []):
        raise SmokeFailure("The receipt did not prove the native Box, connections, geometry and attribute")


class StdioMCP:
    """One finite production MCP child; requests and receipts stay strictly ordered."""
    def __init__(self, paths, environment, calls):
        self.calls, self.counter = calls, 0
        self.responses = queue.Queue(maxsize=2)
        # Houdini may inject its own PYTHONHOME/PYTHONPATH after launch. The
        # console helper must use its own stdlib and the current Studio source.
        child_environment = helper_environment(paths)
        for name in ("BCS_SESSION_ID", "BCS_WORKSPACE_ID", "BCS_SESSION_TOKEN", "BCS_OWNER_ID"):
            child_environment[name] = environment[name]
        self.child = subprocess.Popen([environment["BCS_PYTHON_EXECUTABLE"], "-m", "studio.mcp"],
            cwd=paths.root, env=child_environment, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, encoding="utf-8", creationflags=hidden_flags())
        self.reader = threading.Thread(target=self._read, name="smoke-mcp-reader", daemon=True)
        self.reader.start()

    def _read(self):
        try:
            while True:
                line = self.child.stdout.readline(2 * 1024 * 1024 + 1)
                if not line or len(line) > 2 * 1024 * 1024:
                    self.responses.put(None, timeout=1)
                    return
                self.responses.put(json.loads(line), timeout=1)
        except (ValueError, OSError, queue.Full):
            try:
                self.responses.put(None, timeout=1)
            except queue.Full:
                pass

    def request(self, method, params):
        self.counter += 1
        started = time.monotonic()
        if method == "tools/call":
            self.calls.append({"tool": params["name"], "request_id": self.counter})
        self.child.stdin.write(json.dumps({"jsonrpc": "2.0", "id": self.counter,
                                          "method": method, "params": params}) + "\n")
        self.child.stdin.flush()
        try:
            response = self.responses.get(timeout=20)
        except queue.Empty as exc:
            raise SmokeFailure("MCP response timed out; inspect the recorded owner and never replay") from exc
        if response is None or response.get("id") != self.counter or "error" in response:
            raise SmokeFailure("MCP ended or returned an unexpected response; no script replay")
        if method == "tools/call":
            self.calls[-1]["seconds"] = round(time.monotonic() - started, 6)
        return response["result"]

    def call(self, name, arguments):
        return self.request("tools/call", {"name": name, "arguments": arguments})

    def close(self):
        self.child.stdin.close()
        try:
            self.child.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.child.kill()  # This MCP child only. Houdini work can still be running.
            self.child.wait(timeout=2)
        self.reader.join(timeout=1)
        self.child.stdout.close()


def operation(mcp, name, arguments, record, seconds=30):
    receipt = tool_value(mcp.call(name, arguments))
    record(receipt)  # Preserve the ID even if a later wait/check fails.
    deadline = time.monotonic() + seconds
    while receipt.get("state") not in TERMINAL:
        if time.monotonic() >= deadline:
            raise SmokeFailure("Operation is still unconfirmed; query its recorded ID, never replay")
        time.sleep(0.1)
        # Query through the SAME adapter so a completed context binds its writes.
        receipt = tool_value(mcp.call("hia_operation", {"action": "get", "operation_id": receipt["operation_id"]}))
        record(receipt)
    if receipt.get("state") != "finished":
        raise SmokeFailure("Operation did not finish successfully; inspect its recorded receipt")
    return receipt


def start():
    """Return immediately; call only inside the dedicated newly launched GUI."""
    paths, environment = AppPaths(), dict(os.environ)
    required = ("BCS_SESSION_ID", "BCS_SESSION_TOKEN", "BCS_WORKSPACE_ID", "BCS_PYTHON_EXECUTABLE")
    if any(not environment.get(key) for key in required):
        raise SmokeFailure("Use a new Studio-launched GUI in the prepared smoke workspace")
    workspace = paths.workspace(environment["BCS_WORKSPACE_ID"])
    directory = paths.session(environment["BCS_SESSION_ID"])
    marker, launch, identity = (read_json(workspace / "gui-smoke.json"), read_json(directory / "launch.json"),
                                read_json(directory / "runtime.json"))
    validate_session(marker, launch, identity, environment, os.getpid())
    report_path = paths.local("houdini-smoke", marker["run_id"], "report.json")
    if read_json(report_path).get("status") != "not_run":
        raise SmokeFailure("This prepared run has already started; do not replay it")
    if not _running.acquire(blocking=False):
        raise SmokeFailure("A smoke is already running in this GUI")
    try:
        with (workspace / "gui-smoke.claim.json").open("x", encoding="utf-8") as claim:
            json.dump({"launcher_session_id": environment["BCS_SESSION_ID"], "houdini_pid": os.getpid()}, claim)
        thread = threading.Thread(target=_run, args=(paths, environment, launch, identity, marker, report_path),
                                  name="studio-gui-smoke", daemon=True)
        thread.start()
    except BaseException:
        _running.release()
        raise
    return str(report_path)


def _run(paths, environment, launch, identity, marker, report_path):
    global _panel, _pane
    started, mcp = time.monotonic(), None
    token = environment["BCS_SESSION_TOKEN"]
    report = {**marker, "status": "running", "mode": "real GUI / registered pypanel / production MCP stdio",
              "cases": [], "operations": {}, "tool_calls": [], "codex_inference": "not_run",
              "hip_replacement": "not_run", "capture": "not_run", "runtime_id": identity["runtime_id"],
              "launcher_session_id": environment["BCS_SESSION_ID"], "houdini_pid": os.getpid()}

    def save():
        atomic_json(report_path, redact(report, token))

    def record(receipt):
        report["operations"][receipt["operation_id"]] = receipt
        save()

    try:
        save()
        import hou
        import hdefereval
        import PySide6
        from PySide6 import QtCore, QtWidgets
        on_main = hdefereval.executeInMainThreadWithResult
        bridge = Client(read_json(paths.session(environment["BCS_SESSION_ID"]) / "bridge.json")["url"], token)
        deadline = time.monotonic() + 15
        while True:
            state = bridge.call("GET", "/state")
            if state["codex"]["state"] not in {"idle", "completed", "interrupted", "failed"}:
                raise SmokeFailure("Codex must be idle before deterministic GUI smoke")
            runtime = state["runtime"]
            if runtime.get("connection") == "connected" and not runtime.get("main_thread_busy") and not runtime.get("queue_depth"):
                break
            if time.monotonic() >= deadline:
                raise SmokeFailure("Runtime did not become idle after the main-thread bootstrap returned")
            time.sleep(0.1)

        def prepare_panel():
            global _pane
            if not hou.isUIAvailable() or QtCore.QThread.currentThread() != QtWidgets.QApplication.instance().thread():
                raise SmokeFailure("A real Houdini GUI main thread is required")
            interface = hou.pypanel.interfaces().get("big_chicken_studio")
            expected = paths.root / "houdini/python_panels/big_chicken_studio.pypanel"
            if interface is None or Path(interface.filePath()).resolve() != expected.resolve():
                raise SmokeFailure("This installation's actual pypanel must be registered")
            _pane = hou.ui.curDesktop().createFloatingPaneTab(hou.paneTabType.PythonPanel,
                python_panel_interface="big_chicken_studio", immediate=True)
            return {"houdini": hou.applicationVersionString(), "python": platform.python_version(),
                    "qt": QtCore.qVersion(), "pyside6": PySide6.__version__, "codex": launch.get("codex_version")}

        report["environment"] = on_main(prepare_panel)
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=paths.root, capture_output=True,
                                text=True, timeout=5, creationflags=hidden_flags(), check=True)
        report["commit"] = commit.stdout.strip()

        def panel_ready():
            global _panel
            if _pane.activeInterfaceScriptErrors():
                raise SmokeFailure("The registered Python Panel reported script errors")
            widget = _pane.activeInterfaceRootWidget()
            if widget is not None:
                from .ui.panel import StudioPanel
                if not isinstance(widget, StudioPanel):
                    raise SmokeFailure("The registered interface returned an unexpected QWidget")
                _panel = widget
                return True
            return False

        deadline = time.monotonic() + 10
        while not on_main(panel_ready):
            if time.monotonic() >= deadline:
                raise SmokeFailure("The registered Python Panel did not create its QWidget")
            time.sleep(0.1)
        report["cases"].append({"case": "registered_pypanel", "status": "passed"})
        report["test_root"] = "/obj/bcs_smoke_" + new_id()[:16]
        environment["BCS_OWNER_ID"] = "smoke_" + marker["run_id"]
        report["owner_id"] = environment["BCS_OWNER_ID"]
        mcp = StdioMCP(paths, environment, report["tool_calls"])
        mcp.request("initialize", {"protocolVersion": "2024-11-05", "capabilities": {},
                                  "clientInfo": {"name": "studio-gui-smoke", "version": "1"}})
        context = operation(mcp, "hia_context", {}, record)
        if context.get("runtime_id") != identity["runtime_id"] or not context.get("result", {}).get("scene_epoch"):
            raise SmokeFailure("The observed context did not identify this runtime and scene")
        created = operation(mcp, "hia_execute_hom", creation_arguments(report["test_root"]), record)
        verify_created(created, report["test_root"])
        report["cases"].append({"case": "native_box_connections_geometry_attribute", "status": "passed",
                                "operation_id": created["operation_id"]})
        # Exercise the actual QWidget's Qt HTTP read through Bridge; no fake Api.
        on_main(lambda: _panel.read_operation(created["operation_id"]))
        deadline = time.monotonic() + 10
        while not on_main(lambda: _panel.operation_id == created["operation_id"] and
                          _panel.receipts.get(created["operation_id"], {}).get("state") == "finished" and
                          created["operation_id"] in _panel.operation_detail.toPlainText()):
            if time.monotonic() >= deadline:
                raise SmokeFailure("Panel did not receive the real receipt through Bridge")
            time.sleep(0.1)
        report["cases"].append({"case": "receipt_to_bridge_to_panel", "status": "passed",
                                "operation_id": created["operation_id"]})
        report["status"] = "passed"
    except BaseException as exc:
        report["status"] = "failed"
        report["error"] = str(exc)[:600] if isinstance(exc, SmokeFailure) else type(exc).__name__
        report["instruction"] = "Inspect the recorded operation IDs and unique root. Never replay an unconfirmed script."
    finally:
        try:
            if mcp is not None:
                mcp.close()
        except Exception:
            report["cleanup"] = "MCP child exit was not confirmed; Houdini was left running"
        report["elapsed_seconds"] = round(time.monotonic() - started, 6)
        try:
            save()
        finally:
            _running.release()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare"])
    parser.parse_args()
    print(json.dumps(prepare(), ensure_ascii=False, indent=2))
