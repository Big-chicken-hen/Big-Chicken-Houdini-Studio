"""Opt-in GUI smoke using the installed Panel, MCP stdio and live runtime.

Run inside a Studio-launched Houdini: ``from studio.houdini_smoke import start;
report_path = start(capture=True)``. Returns immediately: never block the UI
thread waiting for its own HTTP/HOM queue. Leaves one uniquely named test root.
No HIP load/clear/save, no user-node deletion, no Codex inference claim.
"""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import subprocess
import threading
import time

from .common import TERMINAL, AppPaths, StudioError, atomic_json, new_id, read_json
from .http import Client
from .mcp import Adapter

_running = threading.Lock()


def example_batch(root):
    """A deterministic, editable native graph; also compile-checked by backend CI."""
    if not root.startswith('/obj/bcs_smoke_') or not root[5:].isidentifier():
        raise ValueError('Expected an owned smoke root')
    name = root.rsplit('/', 1)[-1]
    return '\n'.join([
        'from PySide6 import QtCore, QtWidgets',
        'assert QtCore.QThread.currentThread() == QtWidgets.QApplication.instance().thread()',
        f'assert hou.node({root!r}) is None, "Smoke root already exists; do not replay"',
        f'g = hou.node("/obj").createNode("geo", {name!r}, run_init_scripts=False)',
        'b = g.createNode("box", "source_box")',
        'b.parmTuple("size").set((2, 2, 2))',
        'w = g.createNode("attribwrangle", "stamp_attribute")',
        'w.setInput(0, b)',
        'w.parm("snippet").set("f@studio_smoke = 1.0;")',
        'o = g.createNode("null", "OUT_SMOKE")',
        'o.setInput(0, w)',
        'o.setDisplayFlag(True)',
        'o.setRenderFlag(True)',
        'g.layoutChildren()',
        'geo = o.geometry()',
        'result = {"root": g.path(), "main_thread": True,',
        '          "attribute": geo.findPointAttrib("studio_smoke") is not None,',
        '          "size": list(b.parmTuple("size").eval())}',
    ])


def wire_call(request_id, name, arguments):
    return {'jsonrpc': '2.0', 'id': request_id, 'method': 'tools/call',
            'params': {'name': name, 'arguments': arguments}}


def tool_value(response):
    value = response.get('result', response)
    content = value.get('content', [])
    if not content or content[0].get('type') != 'text':
        raise RuntimeError('MCP returned no structured text receipt')
    return json.loads(content[0]['text'])


def wait_receipt(client, value, seconds=30):
    operation_id = value.get('operation_id')
    if not operation_id:
        raise RuntimeError('Missing operation receipt: ' + str(value.get('error', 'unknown')))
    deadline = time.monotonic() + seconds
    while value.get('state') not in TERMINAL:
        if time.monotonic() >= deadline:
            raise RuntimeError('Operation still unconfirmed; query ' + operation_id + '; do not replay')
        time.sleep(0.05)
        value = client.call('GET', '/operations/' + operation_id)
    return value


class DiscardAdmissionResponse:
    """Deliberate response-loss fault, AFTER the real runtime accepted the call."""
    def __init__(self, client):
        self.client, self.dropped = client, False

    def call(self, method, path, payload=None):
        value = self.client.call(method, path, payload)
        if method == 'POST' and path == '/operations' and payload.get('kind') == 'execute' and not self.dropped:
            self.dropped = True
            raise StudioError('CONNECTION_LOST', 'Injected loss of the admission response', 503)
        return value


def start(*, capture=False, open_panel=True):
    """Start one finite smoke run; use only in an idle, disposable Studio session."""
    paths = AppPaths()
    required = ('BCS_SESSION_ID', 'BCS_SESSION_TOKEN', 'BCS_WORKSPACE_ID', 'BCS_PYTHON_EXECUTABLE')
    if any(not os.environ.get(key) for key in required):
        raise RuntimeError('Open Houdini through the Studio launcher first')
    if not _running.acquire(blocking=False):
        raise RuntimeError('A Houdini smoke is already running')
    report_path = paths.local('smoke', new_id(), 'report.json')
    environment = dict(os.environ)
    thread = threading.Thread(target=_run, args=(paths, environment, report_path, capture, open_panel),
                              name='studio-gui-smoke', daemon=True)
    try:
        thread.start()
    except BaseException:
        _running.release()
        raise
    return str(report_path)


def _run(paths, environment, report_path, capture, open_panel):
    report = {'status': 'running', 'mode': 'real Houdini GUI / production MCP stdio', 'cases': [],
              'codex_inference_verified': False, 'hip_replacement_verified': False,
              'capture_requested': bool(capture), 'panel_requested': bool(open_panel)}
    token = environment['BCS_SESSION_TOKEN']
    child = None
    try:
        atomic_json(report_path, report)
        import hou
        import hdefereval
        from PySide6 import QtCore, QtWidgets
        on_main = hdefereval.executeInMainThreadWithResult
        directory = paths.session(environment['BCS_SESSION_ID'])
        identity = read_json(directory / 'runtime.json')
        if identity['launcher_session_id'] != environment['BCS_SESSION_ID'] or identity['workspace_id'] != environment['BCS_WORKSPACE_ID']:
            raise RuntimeError('Runtime identity does not match this launch')
        runtime = Client(identity['url'], token)
        bridge = Client(read_json(directory / 'bridge.json')['url'], token)
        state = bridge.call('GET', '/state')
        if state['codex']['state'] not in {'idle', 'completed', 'interrupted', 'failed'} or state['runtime'].get('queue_depth'):
            raise RuntimeError('Finish or stop current work before running the smoke')
        panes = []

        def prepare():
            if not hou.isUIAvailable() or QtCore.QThread.currentThread() != QtWidgets.QApplication.instance().thread():
                raise RuntimeError('A real Houdini GUI main thread is required')
            if open_panel:
                pane = hou.ui.curDesktop().createFloatingPaneTab(
                    hou.paneTabType.PythonPanel, python_panel_interface='big_chicken_studio', immediate=True)
                panes.append(pane)
            return {'houdini': hou.applicationVersionString(), 'qt': QtCore.qVersion()}

        report['environment'] = on_main(prepare)
        if open_panel:
            def panel_ready():
                errors = panes[0].activeInterfaceScriptErrors()
                if errors:
                    raise RuntimeError('Python Panel failed to load: ' + errors[:1000])
                widget = panes[0].activeInterfaceRootWidget()
                return widget is not None and widget.objectName() == 'studioPanel'
            deadline = time.monotonic() + 10
            while not on_main(panel_ready):
                if time.monotonic() > deadline:
                    raise RuntimeError('Registered Python Panel did not create its root widget')
                time.sleep(0.1)
            report['cases'].append({'case': 'registered_python_panel', 'passed': True})

        root = '/obj/bcs_smoke_' + new_id()[:12]
        report['test_root'] = root
        owner = 'smoke_' + new_id()
        environment['BCS_OWNER_ID'] = owner
        creation = {'script': example_batch(root), 'label': 'Smoke: native Box size 2 and attribute', 'checks': [
            {'kind': 'parm_equals', 'path': root + '/source_box', 'parm': 'sizex', 'expected': 2},
            {'kind': 'parm_equals', 'path': root + '/source_box', 'parm': 'sizey', 'expected': 2},
            {'kind': 'parm_equals', 'path': root + '/source_box', 'parm': 'sizez', 'expected': 2},
            {'kind': 'input_equals', 'path': root + '/OUT_SMOKE', 'expected': root + '/stamp_attribute'},
            {'kind': 'cook', 'path': root + '/OUT_SMOKE'},
            {'kind': 'geometry_nonempty', 'path': root + '/OUT_SMOKE'}]}
        messages = [
            {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {
                'protocolVersion': '2024-11-05', 'capabilities': {},
                'clientInfo': {'name': 'studio-gui-smoke', 'version': '1'}}},
            wire_call(2, 'hia_context', {}),
            wire_call(3, 'hia_execute_hom', creation),
            wire_call(4, 'hia_inspect', {'views': [{'view': 'geometry', 'path': root + '/OUT_SMOKE'}]}),
        ]
        if capture:
            messages.append(wire_call(5, 'hia_capture', {'resolution': [640, 360]}))
        # Finite stdin and a bounded child wait: no permanent test service/thread pool.
        child = subprocess.Popen([environment['BCS_PYTHON_EXECUTABLE'], '-m', 'studio.mcp'],
                                 cwd=paths.root, env=environment, stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        raw, _ = child.communicate(('\n'.join(json.dumps(m) for m in messages) + '\n').encode(), timeout=60)
        if child.returncode:
            raise RuntimeError('MCP subprocess failed; no script will be replayed')
        replies = {v['id']: v for v in (json.loads(line) for line in raw.splitlines())}
        created = wait_receipt(runtime, tool_value(replies[3]))
        report['cases'].append({'case': 'mcp_stdio_create_connect_parms_cook', 'receipt': created,
                                'passed': created.get('mutation_outcome') == 'completed' and created.get('checks_outcome') == 'passed'})
        value = created.get('result', {}).get('value', {})
        if not report['cases'][-1]['passed'] or not value.get('main_thread') or not value.get('attribute'):
            raise RuntimeError('Real node creation, attribute or targeted checks failed')
        geometry = wait_receipt(runtime, tool_value(replies[4]))
        if geometry.get('state') != 'finished':
            raise RuntimeError('Real geometry inspection failed')
        report['cases'].append({'case': 'geometry_inspection', 'passed': True, 'receipt': geometry})
        if capture:
            captured = wait_receipt(runtime, tool_value(replies[5]))
            if captured.get('state') != 'finished':
                raise RuntimeError('Real viewport capture failed')
            image = runtime.call('GET', '/artifacts/' + captured['result']['artifact_id'])
            if not base64.b64decode(image['data'], validate=True).startswith(b'\x89PNG\r\n\x1a\n'):
                raise RuntimeError('Capture is not a decodable PNG payload')
            report['cases'].append({'case': 'viewport_png', 'passed': True, 'receipt': captured,
                                    'visual_quality_verified': False})

        fault = DiscardAdmissionResponse(runtime)
        adapter = Adapter(fault, bridge, identity, owner)
        context = wait_receipt(runtime, tool_value(adapter.call('hia_context', {})))
        adapter._receipt(context)
        recovered = wait_receipt(runtime, tool_value(adapter.call('hia_execute_hom', {
            'label': 'Smoke: discarded response; same receipt recovery',
            'script': f'n = hou.node({root!r})\nv = int(n.userData("receipt_smoke_count") or "0") + 1\nn.setUserData("receipt_smoke_count", str(v))\nresult = v'})))
        again = runtime.call('GET', '/operations/' + recovered['operation_id'])
        if not fault.dropped or recovered['operation_id'] != again['operation_id'] or again.get('result', {}).get('value') != 1:
            raise RuntimeError('Lost-response recovery did not return the same one-time effect')
        report['cases'].append({'case': 'discarded_response_same_receipt', 'passed': True, 'receipt': again,
                                'fault': 'injected loss after real admission; no POST retry'})
        edited = wait_receipt(runtime, tool_value(adapter.call('hia_execute_hom', {
            'script': f'g = hou.node({root!r})\ng.node("source_box").parm("sizex").set(3)\nt = g.createNode("null", "disposable")\nt.destroy()',
            'label': 'Smoke: edit parameter and delete owned temporary node',
            'checks': [{'kind': 'parm_equals', 'path': root + '/source_box', 'parm': 'sizex', 'expected': 3},
                       {'kind': 'node_exists', 'path': root + '/disposable', 'expected': False}]})))
        if edited.get('checks_outcome') != 'passed':
            raise RuntimeError('Parameter edit or owned-node deletion failed')
        report['cases'].append({'case': 'edit_delete', 'passed': True, 'receipt': edited})
        if open_panel:
            on_main(lambda: panes[0].activeInterfaceRootWidget().read_operation(edited['operation_id']))
            deadline = time.monotonic() + 10
            while not on_main(lambda: panes[0].activeInterfaceRootWidget().receipts.get(edited['operation_id'], {}).get('state') == 'finished'):
                if time.monotonic() > deadline:
                    raise RuntimeError('Panel did not read the real operation receipt through Bridge')
                time.sleep(0.1)
            report['cases'].append({'case': 'runtime_receipt_to_bridge_to_panel', 'passed': True})
        report['status'] = 'passed'
    except BaseException as exc:
        report['status'] = 'failed'
        report['error'] = str(exc).replace(token, '[REDACTED]')[:2000]
        report['instruction'] = 'Inspect receipts and the unique test root. Never replay to recover an unknown result.'
    finally:
        if child is not None and child.poll() is None:
            child.kill()  # Only our MCP child, never Houdini or the user Codex process.
            child.communicate()
        try:
            atomic_json(report_path, report)
        finally:
            _running.release()
