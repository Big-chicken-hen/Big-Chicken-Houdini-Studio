"""Diagnostic safety gates only; no Qt application or Houdini host is created."""
from pathlib import Path
import runpy
import types
import unittest
from unittest.mock import Mock


probe = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'scripts/inspect_houdini_help.py'))


class HelpInspectionTests(unittest.TestCase):
    def test_wrong_thread_does_not_touch_hom_or_create_an_application(self):
        hou = Mock()
        app = Mock()
        app.thread.return_value = 'gui'
        widgets = types.SimpleNamespace(QApplication=types.SimpleNamespace(instance=lambda: app))
        core = types.SimpleNamespace(QThread=types.SimpleNamespace(currentThread=lambda: 'worker'))
        result = probe['collect'](hou, core, widgets, {}, case='studio')
        self.assertEqual(result['status'], 'unavailable')
        self.assertEqual(hou.mock_calls, [])

    def test_embedded_or_shared_help_does_not_inspect_other_windows(self):
        pane = Mock()
        for panel in (None, Mock()):
            if panel is not None:
                panel.paneTabs.return_value = (pane, Mock())
            pane.floatingPanel.return_value = panel
            result = probe['help_window_facts'](pane, Mock(), {})
            self.assertFalse(result['available'])
            pane.qtParentWindow.assert_not_called()

    def test_failed_qml_does_not_create_an_engine_or_query_unknown_getters(self):
        widget = Mock(spec=['status', 'source', 'errors', 'rootObject'])
        widget.status.return_value = 'Error'
        widget.source.return_value.toString.return_value = 'qrc:/help/Browser.qml'
        error = Mock()
        error.toString.return_value = 'file:///qml/Browser.qml:4: module absent'
        widget.errors.return_value = [error]
        widget.rootObject.return_value = None
        qml = Mock()
        result = probe['quick_facts'](widget, qml)
        self.assertEqual(result['status'], 'Error')
        self.assertEqual(len(result['errors']), 1)
        self.assertFalse(result['engine']['available'])
        qml.qmlEngine.assert_not_called()

    def test_existing_root_reports_its_real_engine_and_redacts_url_credentials(self):
        widget = Mock(spec=['status', 'source', 'errors', 'rootObject'])
        widget.status.return_value = 'Ready'
        widget.source.return_value.toString.return_value = 'https://user:secret@localhost/help?token=private#x'
        widget.errors.return_value = []
        qml = Mock()
        qml.qmlEngine.return_value.importPathList.return_value = ['Houdini/qml', 'custom/qml']
        qml.qmlEngine.return_value.pluginPathList.return_value = ['Houdini/plugins']
        result = probe['quick_facts'](widget, qml)
        qml.qmlEngine.assert_called_once_with(widget.rootObject.return_value)
        self.assertEqual(result['engine']['import_paths'], ['Houdini/qml', 'custom/qml'])
        self.assertEqual(result['source'], 'https://localhost/help')
        self.assertNotIn('BCS_SESSION_TOKEN', probe['ENVIRONMENT_FIELDS'])
        self.assertNotIn('CODEX_HOME', probe['ENVIRONMENT_FIELDS'])

    def test_only_the_help_window_subtree_is_visited_with_a_hard_bound(self):
        class Widget:
            def isVisible(self):
                return True

            def children(self):
                return [Widget() for _ in range(8)]

        pane = Mock()
        pane.floatingPanel.return_value.paneTabs.return_value = (pane,)
        pane.qtParentWindow.return_value = Widget()
        result = probe['help_window_facts'](pane, types.SimpleNamespace(QWidget=Widget), {})
        self.assertLessEqual(result['visited'], 192)
        self.assertTrue(result['truncated'])
        self.assertFalse(result['carrier']['available'])


if __name__ == '__main__':
    unittest.main()
