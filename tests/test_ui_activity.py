"""R3 chronology, visible failure and receipt-derived progress in native Qt."""
import copy
import json
import os
from pathlib import Path
import unittest

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from PySide6 import QtCore, QtWidgets  # noqa: E402
from scripts.preview_ui import PreviewApi, configure_preview_fonts, process_until  # noqa: E402
from studio.common import AppPaths  # noqa: E402
from studio.ui.conversation import Transcript  # noqa: E402
from studio.ui.panel import StudioPanel  # noqa: E402


def tool(identity, *, state='finished', mutation='none'):
    return {'id': identity, 'type': 'mcpToolCall', 'tool': 'hia_execute_hom', 'status': 'completed',
            'result': {'content': [{'type': 'text', 'text': json.dumps({'operation_id': identity,
                'state': state, 'mutation_outcome': mutation, 'kind': 'execute'})}]}}


class ActivityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        configure_preview_fonts(cls.app)
        cls.root = Path(__file__).resolve().parents[1] / '.runtime/r3-tests'
        cls.root.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self.app.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)

    def test_collapsed_segments_preserve_explanations_and_visible_failures(self):
        view = Transcript(self.root)
        self.addCleanup(view.deleteLater)
        self.addCleanup(view.close)
        view.resize(440, 720)
        view.show()
        view.reset('a')
        first = {'id': 'user', 'type': 'userMessage', 'content': [{'type': 'text', 'text': '第一轮'}]}
        explanation = {'id': 'explain', 'type': 'agentMessage', 'text': '需要继续调整这个部位。'}
        view.hydrate({'id': 'a', 'turns': [
            {'id': 'one', 'status': 'completed', 'itemsView': 'full', 'items': [first, tool('query'), explanation,
                tool('partial', state='failed', mutation='partial'), tool('later')]},
            {'id': 'two', 'status': 'completed', 'itemsView': 'full', 'items': [
                {**first, 'id': 'user2'}, tool('unknown', state='unknown', mutation='unknown')]}]})
        self.app.processEvents()
        self.assertEqual(len(view.tool_groups), 3)
        controls = list(view.tool_groups.values())
        self.assertLess(view.layout.indexOf(controls[0]), view.layout.indexOf(view.card('explain')))
        self.assertLess(view.layout.indexOf(view.card('explain')), view.layout.indexOf(controls[1]))
        self.assertTrue(view.card('query').isHidden())
        self.assertTrue(view.card('later').isHidden())
        self.assertFalse(view.card('partial').isHidden())
        self.assertFalse(view.card('unknown').isHidden())
        self.assertIn('部分修改', view.card('partial').activity_warning.text())
        controls[0].click()
        self.assertFalse(view.card('query').isHidden())
        self.assertTrue(view.card('later').isHidden(), 'Expanding one segment must not open another')
        self.assertEqual(len(view.turn_gaps), 1)
        user = view.card('user')
        self.assertAlmostEqual(user.width()/view.viewport().width(), .86, delta=.02)
        self.assertGreater(user.x(), view.card('explain').x())
        retired = list(view.cards.values())
        view.reset('b')
        self.assertTrue(all(card.isHidden() for card in retired), 'Retired cards must hide before deferred deletion')

    def test_tool_recovery_is_visible_even_with_collapsed_activity(self):
        view = Transcript(self.root)
        self.addCleanup(view.deleteLater)
        self.addCleanup(view.close)
        view.resize(360, 600)
        view.show()
        view.reset('a')
        view.put(tool('recovering'), turn_id='one')
        card = view.card('recovering')
        self.assertTrue(card.isHidden())
        card.set_recovering(True)
        self.assertFalse(card.isHidden())
        self.assertFalse(card.sync_note.isHidden())
        card.set_recovering(False)
        self.assertTrue(card.isHidden())

    def test_progress_uses_current_receipt_and_retains_running_houdini_after_codex_ends(self):
        api = PreviewApi(self.root)
        paths = AppPaths(self.root.parents[1], data_root=self.root / 'state', cache_root=self.root / 'cache')
        panel = StudioPanel(api=api, paths=paths, auto_poll=False, image_roots=(self.root,))
        self.addCleanup(panel.deleteLater)
        self.addCleanup(panel.close)
        self.addCleanup(api.close)
        panel.show()
        process_until(lambda: panel.transcript.history_known)
        panel.resize(360, 720)
        process_until(lambda: all(not c.fit_timer.isActive() and (c.text.isHidden() or
            c.text.viewport().height() >= c.text.document().size().height()) for c in panel.transcript.cards.values()))
        api.state['codex'].update(state='completed', stop_requested=False)
        api.state['runtime'].update(main_thread_busy=True, active_operation_id='preview_operation', queue_depth=0)
        api.operation.update(state='running', kind='execute', active_step='assemble', steps=[
            {'id': 'inputs', 'label': '准备输入'}, {'id': 'assemble', 'label': '生成铺装'},
            {'id': 'controls', 'label': '连接参数'}, {'id': 'check', 'label': '确认输出'}])
        panel.apply_state(copy.deepcopy(api.state))
        process_until(lambda: '阶段 2 / 4' in panel.work_status.text())
        self.assertIn('生成铺装', panel.work_status.text())
        self.assertIs(panel.action_slot.currentWidget(), panel.stop_button)
        panel.stop_pending = True
        panel.update_work_status()
        self.assertIn('等待当前步骤结束', panel.work_status.text())
        panel.stop_pending = False
        api.operation['active_step'] = 'controls'
        panel.operation_progress_due = 0
        panel.apply_state(copy.deepcopy(api.state))
        process_until(lambda: '阶段 3 / 4' in panel.work_status.text())
        api.operation.update(kind='capture', steps=[], active_step=None)
        panel.operation_progress_due = 0
        panel.apply_state(copy.deepcopy(api.state))
        process_until(lambda: panel.runtime_status.text() == '正在获取视图')
