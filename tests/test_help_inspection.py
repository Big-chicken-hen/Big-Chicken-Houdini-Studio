"""Diagnostic safety gates only; no Qt application or Houdini host is created."""
from pathlib import Path
from contextlib import redirect_stdout
import io
import runpy
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch


probe = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'scripts/inspect_houdini_help.py'))


class HelpInspectionTests(unittest.TestCase):
    def test_raw_environment_keeps_original_spelling_and_only_three_allowed_keys(self):
        block = ('=C:=private-directory\0Path=Qt;插件;;\0SYSTEMROOT=C:\\Windows\0'
                 'SystemDrive=C:\0BCS_SESSION_TOKEN=private-fixture\0'
                 'HTTP_PROXY=http://private-fixture\0\0')
        result = probe['selected_raw_environment'](block)
        self.assertEqual(result['entries'], [{'name': 'Path', 'value': 'Qt;插件;;'},
                         {'name': 'SYSTEMROOT', 'value': 'C:\\Windows'},
                         {'name': 'SystemDrive', 'value': 'C:'}])
        self.assertTrue(result['available'])
        self.assertNotIn('private', str(result))
        self.assertEqual(probe['selected_raw_environment']('\0\0')['entries'], [])

    def test_raw_environment_scan_stops_at_its_bound(self):
        result = probe['selected_raw_environment']('Path=ok\0unrelated-long-value', limit=12)
        self.assertFalse(result['available'])
        self.assertTrue(result['truncated'])
        self.assertEqual(result['entries'], [{'name': 'Path', 'value': 'ok'}])

    def test_log_read_never_creates_a_sink_or_reads_unrelated_messages(self):
        logging = Mock(spec=['defaultSink'])
        logging.defaultSink.return_value = None
        self.assertFalse(probe['existing_log_facts'](types.SimpleNamespace(logging=logging))['available'])
        logging.defaultSink.assert_called_once_with(False)
        unrelated = Mock(spec=['source', 'message'])
        unrelated.source.return_value = 'Licensing'
        qt = Mock(spec=['source', 'message', 'time', 'severity'])
        qt.source.return_value = 'Standard Error'
        qt.message.return_value = 'QQml: failed https://user:secret@localhost/help?token=hidden'
        qt.time.return_value = 1.0
        qt.severity.return_value = 'Warning'
        library = Mock(spec=['source', 'message', 'time', 'severity'])
        library.source.return_value = 'Generic Logging'
        library.message.return_value = 'Qt WebEngine process path: C:/Houdini/qt/bin/QtWebEngineProcess.exe'
        library.time.return_value = 2.0
        library.severity.return_value = 'Message'
        command = Mock(spec=['source', 'message'])
        command.source.return_value = 'Standard Error'
        command.message.return_value = 'QtWebEngineProcess.exe --type=renderer --private=value'
        sink = Mock(spec=['connectedSources', 'logEntries'])
        sink.connectedSources.return_value = ['Standard Error', 'Licensing']
        sink.logEntries.return_value = iter([unrelated, qt, command, library])
        logging.defaultSink.return_value = sink
        result = probe['existing_log_facts'](types.SimpleNamespace(logging=logging))
        unrelated.message.assert_not_called()
        self.assertEqual(result['scanned'], 4)
        self.assertEqual(len(result['entries']), 2)
        self.assertEqual(result['entries'][0]['message'], 'QQml: failed https://localhost/help')
        self.assertIn('Qt WebEngine process path:', result['entries'][1]['message'])
        self.assertFalse(result['truncated'])

    def test_log_read_has_a_hard_bound_and_never_drains_the_sink(self):
        entry = Mock(spec=['source'])
        entry.source.return_value = 'Node Errors'

        def entries():
            for _ in range(2048):
                yield entry
            self.fail('The bounded diagnostic advanced past 2048 entries')

        sink = Mock(spec=['connectedSources', 'logEntries'])
        sink.connectedSources.return_value = ['Node Errors']
        sink.logEntries.return_value = entries()
        logging = Mock(spec=['defaultSink'])
        logging.defaultSink.return_value = sink
        result = probe['existing_log_facts'](types.SimpleNamespace(logging=logging))
        self.assertEqual(result['scanned'], 2048)
        self.assertTrue(result['truncated'])
        self.assertEqual(result['entries'], [])

    def test_shell_dispatches_once_and_gui_caller_never_waits_on_itself(self):
        current = ['worker']
        app = Mock()
        app.thread.return_value = 'gui'
        core = types.SimpleNamespace(QThread=types.SimpleNamespace(currentThread=lambda: current[0]))
        widgets = types.SimpleNamespace(QApplication=types.SimpleNamespace(instance=lambda: app))
        hou = Mock()
        hou.isUIAvailable.return_value = False

        def dispatch(callback):
            current[0] = 'gui'
            return callback()

        deferred = types.SimpleNamespace(executeInMainThreadWithResult=Mock(side_effect=dispatch))
        fixtures = Path(__file__).resolve().parents[1] / '.runtime/tests'
        fixtures.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=fixtures) as temporary, \
                patch.dict(probe['capture'].__globals__, ROOT=Path(temporary)), \
                patch.dict(sys.modules, {'hou': hou, 'PySide6.QtCore': core,
                                         'PySide6.QtWidgets': widgets, 'hdefereval': deferred}), \
                redirect_stdout(io.StringIO()):
            first = probe['capture']('native')
            second = probe['capture']('native')
            self.assertNotEqual(first, second)
            self.assertTrue(Path(first).is_file() and Path(second).is_file())
        deferred.executeInMainThreadWithResult.assert_called_once()
        self.assertEqual(hou.isUIAvailable.call_count, 2)

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
