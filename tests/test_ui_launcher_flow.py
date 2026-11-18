"""Selection races, native topology, focus and resources in isolated fixtures."""
import os
import threading
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ['QT_QPA_PLATFORM'] = 'offscreen'

from PySide6 import QtCore, QtGui, QtWidgets  # noqa: E402
from scripts.preview_launcher import PreviewServices, PreviewTarget, configure_fonts, make_fixture_window, process_until  # noqa: E402
from studio.common import AppPaths  # noqa: E402
from studio.targets import SceneCatalog, SceneTarget  # noqa: E402
from studio.ui.launcher_flow import font_diagnostics  # noqa: E402


class FlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        configure_fonts(cls.app)

    def window(self, **options):
        window, services = make_fixture_window(**options)
        self.addCleanup(window.deleteLater)
        self.addCleanup(window.close)
        return window, services

    def test_late_validation_does_not_replace_newer_selection(self):
        window, services = self.window()
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        original = PreviewTarget.hip
        def validate(path):
            if path.endswith('first.hip'):
                entered.set()
                release.wait(2)
            return original(path)
        with patch.object(PreviewTarget, 'hip', side_effect=validate):
            window.select_path('D:/fixture/first.hip')
            process_until(entered.is_set)
            window.select_path('D:/fixture/second.hip')
            process_until(lambda: 'selection' not in window._pending)
            release.set()
            process_until(lambda: not window._tasks)
        self.assertEqual(window._source_branch, 'open')
        self.assertEqual(window._target.path, 'D:/fixture/second.hip')
        self.assertTrue(window._selection_valid)
        self.assertEqual(services.launches, [])
        self.assertEqual(services.admissions, {})

    def test_real_selection_does_not_create_workspace_and_deleted_file_cannot_launch(self):
        root = Path(__file__).resolve().parents[1]
        base = root / '.runtime/flow-selection-tests'
        base.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as folder:
            temporary = Path(folder)
            paths = AppPaths(root, data_root=temporary / 'state', cache_root=temporary / 'cache')
            services = PreviewServices(records=[])
            window, _ = self.window(paths=paths, services=services)
            catalog = SceneCatalog(paths)
            hip = temporary / '中文 场景.hip'
            hip.write_bytes(b'fixture, selection checks existence only')
            window.catalog, window.target_factory = catalog, SceneTarget
            with patch.object(catalog, 'admit', side_effect=AssertionError('Selection must not admit')):
                window.select_path(str(hip))
                process_until(lambda: 'selection' not in window._pending)
                self.assertTrue(window._selection_valid)
                self.assertFalse(paths.data('workspaces').exists())
                hip.unlink()
                window.launch_button.click()
                process_until(lambda: window._launch_phase is None)
            self.assertEqual(window.projection().mode, 'failed')
            self.assertFalse(window._selection_valid)
            self.assertEqual(services.launches, [])
            self.assertFalse(paths.data('workspaces').exists())
            window.close()

    def test_account_and_environment_changes_block_launch_and_return_preserves_selection(self):
        window, services = self.window()
        window.select_empty()
        target = window._target
        for status in ('signed_out', 'unknown'):
            services.state = status if status == 'signed_out' else 'account_unknown'
            window.apply_snapshot(services.snapshot())
            window.render()
            window.launch_button.click()
            self.assertFalse(window.launch_button.isEnabled())
        services.state = 'ready'
        window.apply_snapshot(services.snapshot())
        window.render()
        for page in ('settings', 'account', 'diagnostics'):
            window.show_secondary(page)
            window.back_secondary()
        self.assertIs(window._target, target)
        self.assertEqual(window._source_branch, 'empty')
        self.assertEqual(len(services.probes), 1)
        window._snapshot['houdini']['compatibility'] = {'status': 'unsupported', 'can_launch': False}
        window.render()
        window.launch_selected()
        self.assertFalse(window.launch_button.isEnabled())
        self.assertEqual(services.launches, [])

    def test_topology_font_and_narrow_focus_are_native_without_horizontal_overflow(self):
        window, services = self.window()
        window.select_empty()
        nodes = dict(window.flow.nodes)
        for size, compact in (((1120, 760), False), ((600, 480), True), ((980, 760), False)):
            window.resize(*size)
            for _ in range(6):
                self.app.processEvents()
            self.assertEqual(window.flow.compact, compact)
            self.assertLessEqual(window.flow_page.width(), window.flow_scroll.viewport().width())
            self.assertEqual(window.flow.nodes, nodes)
            self.assertEqual(set(window.flow.paths), {'empty', 'open', 'recent'})
            for paths in window.flow.paths.values():
                for path in paths:
                    for index in range(1, 40):
                        point = path.pointAtPercent(index / 40)
                        self.assertFalse(any(QtCore.QRectF(node.geometry()).adjusted(3, 3, -3, -3).contains(point)
                                             for node in nodes.values()), 'Wire crosses a node interior')
        self.assertTrue(font_diagnostics()['loaded'])
        raw = QtGui.QRawFont.fromFont(window.flow_page.hero.font())
        self.assertEqual(raw.familyName(), 'Changa One')
        self.assertIn('Italic', raw.styleName())
        window.resize(600, 480)
        self.app.processEvents()
        window.empty_button.parentWidget().setFocus()
        for _ in range(35):
            focus = QtWidgets.QApplication.focusWidget()
            if focus is window.launch_button:
                break
            self.app.sendEvent(focus or window, QtGui.QKeyEvent(QtCore.QEvent.KeyPress, QtCore.Qt.Key_Tab, QtCore.Qt.NoModifier))
            self.app.processEvents()
        self.assertIs(QtWidgets.QApplication.focusWidget(), window.launch_button)
        position = window.launch_button.mapTo(window.flow_scroll.viewport(), QtCore.QPoint())
        self.assertTrue(window.flow_scroll.viewport().rect().contains(QtCore.QRect(position, window.launch_button.size())))
        self.assertEqual(services.launches, [])

    def test_recent_popup_limits_inline_rows_and_opening_it_has_no_selection_side_effect(self):
        records = [dict(path=f'D:/fixture/项目-{i}/scene.hip', name='scene.hip', directory=f'D:/fixture/项目-{i}',
                        last_used_at=i, missing=False) for i in range(8)]
        window, services = self.window(records=records)
        self.assertEqual(window.recents.count(), 3)
        window.show_all_recents()
        self.app.processEvents()
        self.assertEqual(window.popup_recents.count(), 8)
        self.assertIsNone(window._source_branch)
        window._popup_rows[7].selected.emit(records[7])
        process_until(lambda: 'selection' not in window._pending)
        self.assertEqual(window._target.path, records[7]['path'])
        self.assertEqual(services.launches, [])
        self.assertEqual(len(services.probes), 1)
        window.recent_popup.close()
