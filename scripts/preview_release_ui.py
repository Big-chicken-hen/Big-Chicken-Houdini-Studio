"""R3 native Qt fixtures, optionally importing an assembled production package."""
from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--install-root', type=Path, default=ROOT)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    output = args.out.resolve()
    if ROOT / '.runtime' not in output.parents:
        raise ValueError('Review outputs must remain in this checkout .runtime')
    output.mkdir(parents=True, exist_ok=True)
    install = args.install_root.resolve()
    sys.path.insert(0, str(install / 'src'))
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    from PySide6 import QtCore, QtWidgets
    from studio.ui import panel as panel_module
    from studio.common import AppPaths
    if install not in Path(panel_module.__file__).resolve().parents:
        raise AssertionError('Wrong production source was loaded')
    sys.path.insert(0, str(ROOT))
    from scripts.preview_ui import PreviewApi, configure_preview_fonts, process_until
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    configure_preview_fonts(app)
    api = PreviewApi(output)
    api.state['runtime'].update(active_operation_id=None, main_thread_busy=False, queue_depth=0)
    api.state['runtime']['scene'].update(display_name='r3-layout.hip', hip_path=str(output/'r3-layout.hip'))
    api.state['codex'].update(state='completed', stop_requested=False)
    def user(identity, text):
        return {'id': identity, 'type': 'userMessage', 'content': [{'type': 'text', 'text': text}]}
    def assistant(identity, text):
        return {'id': identity, 'type': 'agentMessage', 'text': text}
    def tool(identity, name, receipt=None):
        item = {'id': identity, 'type': 'mcpToolCall', 'tool': name, 'status': 'completed', 'arguments': {}}
        if receipt:
            item['result'] = {'content': [{'type': 'text', 'text': json.dumps({'operation_id': identity, **receipt})}]}
        return item
    normal = [user('user', '把铺装宽度改为 2.4 米，保留现有排布和输入曲线。'),
        tool('context', 'hia_context'), tool('read', 'hia_inspect'),
        assistant('reason', '先确认当前宽度和输入连接，再在现有节点上修改。'),
        tool('edit', 'hia_execute_hom'),
        assistant('reply', '宽度已调整。输入曲线和排布设置保持不变。\n\n这是固定的**排版测试文本**，不代表运行了模型或修改了场景。')]
    api.thread = {'id': 'preview_thread', 'turns': [{'id': 'preview_turn', 'status': 'completed', 'itemsView': 'full', 'items': normal}]}
    paths = AppPaths(install, data_root=output / 'state', cache_root=output / 'cache')
    panel = panel_module.StudioPanel(api=api, paths=paths, auto_poll=False, image_roots=(output,))
    records = []
    try:
        panel.show()
        process_until(lambda: panel.transcript.history_known and panel.models_loaded)
        baseline = copy.deepcopy(api.state)
        for case in ('timeline', 'failure', 'long-reply', 'progress', 'stop', 'recovery'):
            api.state = copy.deepcopy(baseline)
            items = copy.deepcopy(normal)
            panel.stop_pending = False
            panel.receipts.clear()
            panel.observed_operations.clear()
            api.operation = {'operation_id': 'preview_operation', 'state': 'finished', 'kind': 'execute',
                             'mutation_outcome': 'completed', 'checks_outcome': 'not_run'}
            if case == 'failure':
                items[4] = tool('failed', 'hia_execute_hom', {'state': 'failed', 'mutation_outcome': 'partial',
                    'error': {'code': 'FIXTURE_PARTIAL', 'message': 'Explicit test fixture'}})
                items[5] = assistant('reply', '这一步留下了部分修改。需要先查看原结果，再做局部修正。')
            elif case == 'long-reply':
                items[5] = assistant('reply', '\n\n'.join(f'{i}. 中文与 English 长正文，保留完整阅读和复制。' for i in range(1, 61))
                    + '\n\n```python\n' + '\n'.join(f'point_{i} = {i}' for i in range(30)) + '\n```\n\nR3_END')
            elif case in ('progress', 'stop'):
                api.state['runtime'].update(active_operation_id='preview_operation', main_thread_busy=True)
                api.operation.update(state='running', mutation_outcome='partial', active_step='assemble', steps=[
                    {'id': 'inputs', 'label': '准备输入'}, {'id': 'assemble', 'label': '生成铺装'},
                    {'id': 'controls', 'label': '连接参数'}, {'id': 'verify', 'label': '确认输出'}])
                panel.stop_pending = case == 'stop'
            api.thread['turns'][0]['items'] = items
            panel.transcript.reset('preview_thread', generation=panel.connection_generation)
            panel.transcript.hydrate(api.thread, generation=panel.connection_generation)
            panel.apply_operations({'operations': [api.operation]})
            panel.apply_state(copy.deepcopy(api.state))
            for width in (360, 720):
                panel.resize(width, 800)
                app.processEvents()
                app.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
                app.processEvents()
                process_until(lambda: all(not c.fit_timer.isActive() and (c.text.isHidden() or
                    c.text.viewport().height() >= c.text.document().size().height()) for c in panel.transcript.cards.values()))
                if case == 'recovery':
                    panel.transcript.card('edit').set_recovering(True)
                if case == 'long-reply':
                    panel.transcript.to_bottom()
                else:
                    panel.transcript.cancel_scroll_restore()
                    panel.transcript.verticalScrollBar().setValue(0)
                app.processEvents()
                path = output / f'panel-{width}-{case}.png'
                assert panel.grab().save(str(path))
                records.append({'file': path.name, 'width': panel.width(), 'case': case,
                    'status': panel.work_status.text(), 'segments': len(panel.transcript.tool_groups),
                    'full_reply_characters': len(panel.transcript.card('reply').source_text()),
                    'inner_scroll_disabled': panel.transcript.card('reply').text.verticalScrollBarPolicy() == QtCore.Qt.ScrollBarAlwaysOff})
        (output / 'report.json').write_text(json.dumps({'qt': QtCore.qVersion(), 'install_root': str(install),
            'panel_module': panel_module.__file__, 'mode': 'Explicit offscreen native Qt fixtures; no model or real Houdini claim',
            'captures': records}, ensure_ascii=False, indent=2), encoding='utf-8')
        print(str(output))
    finally:
        api.close()
        panel.close()
        panel.deleteLater()
        app.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)


if __name__ == '__main__':
    main()
