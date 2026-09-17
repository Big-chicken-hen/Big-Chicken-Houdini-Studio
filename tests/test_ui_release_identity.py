"""Local identity projections and one-launch Untested consent; no host launch."""
import copy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ['QT_QPA_PLATFORM'] = 'offscreen'

from PySide6 import QtCore, QtWidgets  # noqa: E402

from scripts.preview_launcher import make_fixture_window, process_until  # noqa: E402
from scripts.preview_ui import PreviewApi  # noqa: E402
from studio.common import AppPaths  # noqa: E402
from studio.ui.panel import StudioPanel  # noqa: E402


class ReleaseIdentityUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        root = Path(__file__).resolve().parents[1]
        base = root / '.runtime/ui-release-identity-tests'
        base.mkdir(parents=True, exist_ok=True)
        directory = tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(directory.cleanup)
        self.evidence = Path(directory.name)
        self.paths = AppPaths(root, data_root=self.evidence/'state', cache_root=self.evidence/'cache')

    def window(self):
        window, services = make_fixture_window(self.paths, records=[])
        self.addCleanup(window.deleteLater)
        self.addCleanup(window.close)
        return window, services

    def test_selected_and_actual_running_stay_distinct_and_render_does_not_read_installation(self):
        window, services = self.window()
        window._release_identity.update(build_id='0.1.0-rc.1-aaaaaaaaaaaa')
        window._snapshot['codex']['source'] = 'bundled'
        window._snapshot['houdini']['compatibility'] = {'status': 'unknown'}
        with patch('studio.ui.launcher.local_identity', side_effect=AssertionError('No polling metadata reads')):
            window.render()
            before = window.diagnostics_text.toPlainText()
            self.assertIn('Houdini · 已选择: 22.0.368 · Unknown', before)
            self.assertIn('Houdini · 正在运行: Unknown（尚未连接）', before)
            self.assertIn('Codex · Bundled · 已确认版本: 0.153.4', before)
            self.assertIn('Build ID: 0.1.0-rc.1-aaaaaaaaaaaa', before)
            self.assertIn(str(self.paths.data_root), before)
            window._launch_record = {'runtime_connected': True, 'host': {'version': '22.0.400',
                'application': 'houdini', 'license_category': 'Commercial', 'compatibility': {'status': 'untested'}}}
            window.render()
            self.assertIn('Houdini · 正在运行: 22.0.400 · Untested', window.diagnostics_text.toPlainText())
            window._launch_record['runtime_connected'] = False
            window.render()
            self.assertIn('Houdini · 正在运行: Unknown（尚未连接）', window.diagnostics_text.toPlainText())
        self.assertEqual(services.launches, [])

    def test_untested_decline_does_not_prepare_or_launch_and_yes_binds_only_one_request(self):
        window, services = self.window()
        window._snapshot['houdini'].update(version='22.0.400', compatibility={
            'status': 'untested', 'confirmation_required': True, 'message': '相邻 build 尚未验证。'})
        backend = services.backends[-1]
        prepare = backend.prepare_launch
        confirmations, launched_confirmations = [], []

        def confirmed_prepare(confirmation):
            confirmations.append(copy.deepcopy(confirmation))
            return {**prepare(), 'houdini_confirmation': confirmation}

        def confirmed_launch(*args, houdini_confirmation, **kwargs):
            launched_confirmations.append(copy.deepcopy(houdini_confirmation))
            return services.launch(*args, **kwargs)

        backend.prepare_launch = confirmed_prepare
        window._launch = confirmed_launch
        with patch('studio.ui.launcher.QtWidgets.QMessageBox.question', return_value=QtWidgets.QMessageBox.No):
            window.empty_button.click()
            window.launch_button.click()
        self.assertIsNone(window._request_id)
        self.assertEqual(window.current_page, 'flow')
        self.assertEqual(confirmations, [])
        self.assertEqual(services.launches, [])
        with patch('studio.ui.launcher.QtWidgets.QMessageBox.question', return_value=QtWidgets.QMessageBox.Yes) as question:
            window.empty_button.click()
            window.launch_button.click()
        request = window._request_id
        process_until(lambda: window._launch_phase is None)
        expected = {'request_id': request, 'path': 'C:/fixture/houdini.exe', 'version': '22.0.400'}
        self.assertEqual(confirmations, [expected])
        self.assertEqual(launched_confirmations, [expected])
        self.assertEqual(len(services.launches), 1)
        self.assertEqual(question.call_args.args[-1], QtWidgets.QMessageBox.No)
        self.assertEqual(window._snapshot['houdini']['compatibility']['status'], 'untested')
        window.empty_button.click()
        window.launch_button.click()
        self.assertEqual(len(services.launches), 1)

    def test_failed_external_override_offers_explicit_bundled_recovery_without_automatic_probe(self):
        window, services = self.window()
        snapshot = copy.deepcopy(window._snapshot)
        snapshot['codex'].update(state='incompatible', source='explicit_external',
                                 attempts=[{'code': 'CODEX_VERSION_UNSUPPORTED'}])
        window.apply_snapshot(snapshot)
        count = len(services.probes)
        window.render()
        self.assertIn('显式选择的外部 Codex 未通过检查', window.setup_message.text())
        self.assertEqual(window.setup_retry.text(), '恢复使用随包版本')
        self.assertTrue(window.setup_retry.isVisible())
        self.assertEqual(len(services.probes), count)
        window.setup_retry.click()
        process_until(lambda: not window._pending)
        self.assertEqual(services.probes[-1]['codex_override'], '')
        self.assertEqual(len(services.probes), count + 1)
        self.assertEqual(services.launches, [])

    def test_runtime_only_untested_fact_gets_one_explicit_confirmation_without_killing_or_relaunching(self):
        for answer, before_launch in ((QtWidgets.QMessageBox.No, False),
                                      (QtWidgets.QMessageBox.Yes, False), (QtWidgets.QMessageBox.Yes, True)):
            with self.subTest(answer=answer, before_launch=before_launch):
                window, services = self.window()
                window.empty_button.click()
                window.launch_button.click()
                process_until(lambda: window._launch_phase is None)
                record = {**window._launch_record, 'state': 'target_opened', 'target_opened': True,
                    'runtime_connected': True, 'houdini_confirmation': before_launch,
                    'host': {'version': '22.0.368', 'application': 'houdini', 'license_category': 'Indie',
                             'compatibility': {'status': 'untested', 'message': 'Indie 尚未验证。'}}}
                with patch('studio.ui.launcher.QtWidgets.QMessageBox.question', return_value=answer) as question:
                    window.apply_launch_status(copy.deepcopy(record))
                    window.apply_launch_status(copy.deepcopy(record))
                    window.render()
                self.assertEqual(question.call_count, 0 if before_launch else 1)
                self.assertEqual(window._host_trial_confirmation['source'], 'before_launch' if before_launch else 'running_host')
                self.assertEqual(window._host_trial_confirmation['accepted'], before_launch or answer == QtWidgets.QMessageBox.Yes)
                self.assertEqual(window._launch_record['state'], 'target_opened')
                self.assertTrue(window._launch_record['process_may_exist'])
                self.assertEqual(window._launch_record['host']['compatibility']['status'], 'untested')
                if answer == QtWidgets.QMessageBox.No:
                    self.assertIn('本次试用未确认', window.launch_title.text())
                    self.assertIn('正常关闭', window.launch_message.text())
                    self.assertFalse(window.minimize_timer.isActive())
                    self.assertEqual(services.remembered, [])
                window.empty_button.click()
                window.launch_button.click()
                self.assertEqual(len(services.launches), 1)

    def test_panel_uses_registered_host_only_and_disconnect_removes_running_claim(self):
        api = PreviewApi(self.evidence)
        panel = StudioPanel(paths=self.paths, api=api, auto_poll=False, image_roots=(self.evidence,))
        self.addCleanup(api.close)
        self.addCleanup(panel.deleteLater)
        self.addCleanup(panel.close)
        process_until(lambda: len(panel.transcript.cards) == 3)
        state = copy.deepcopy(api.state)
        state['release_identity'] = {'build_id': '0.1.0-rc.1-aaaaaaaaaaaa',
            'installation_root': str(self.paths.root), 'state_root': str(self.paths.data_root),
            'cache_root': str(self.paths.cache_root), 'codex': {'path': 'C:/fixture/codex.exe',
                'version': '0.153.4', 'source': 'explicit_external'},
            'houdini_selected': {'version': '22.0.368', 'compatibility': {'status': 'unknown'}}}
        state['runtime']['host'] = {'version': '22.0.400', 'application': 'houdini',
            'license_category': 'Commercial', 'compatibility': {'status': 'untested'}}
        panel.apply_state(state)
        text = panel.identity_details.toPlainText()
        self.assertTrue(panel.identity_details.isReadOnly())
        self.assertIn('Codex · Explicit external · 已确认版本: 0.153.4', text)
        self.assertIn('Houdini · 已选择: 22.0.368 · Unknown', text)
        self.assertIn('Houdini · 正在运行: 22.0.400 · Untested', text)
        panel.connection_failed('fixture connection lost')
        self.assertIn('Houdini · 正在运行: Unknown（尚未连接）', panel.identity_details.toPlainText())
        self.assertNotIn('正在运行: 22.0.400', panel.identity_details.toPlainText())
        self.app.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
