"""Focused launcher interactions; explicit fixtures, no real Houdini launch."""
import os
import threading
import time
import unittest
from pathlib import Path
import tempfile
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6 import QtCore, QtGui, QtWidgets  # noqa: E402

from scripts.preview_launcher import PreviewServices, PreviewTarget, configure_fonts, make_fixture_window, process_until  # noqa: E402
from studio.common import AppPaths  # noqa: E402
from studio.ui.launcher import StudioLauncher, read_minimize_preference, write_minimize_preference
from studio.ui.launcher_pages import project_page  # noqa: E402
from studio.common import StudioError  # noqa: E402
from studio.ui.shared import ApiFailure, ErrorDetails, Task  # noqa: E402
from studio.ui.theme import apply_theme  # noqa: E402


class ThemeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        configure_fonts(cls.app)

    def test_theme_is_local_and_error_details_preserve_the_original_failure(self):
        app_font, app_style = self.app.font().toString(), self.app.styleSheet()
        unrelated = QtWidgets.QLabel("Host label")
        old_font = unrelated.font().toString()
        root = QtWidgets.QWidget()
        root.setObjectName("studioLauncher")
        layout = QtWidgets.QVBoxLayout(root)
        error = ErrorDetails()
        layout.addWidget(error)
        apply_theme(root)
        root.show()
        failure = ApiFailure("<not markup> Cannot confirm launch\nPrivate detail", code="LAUNCH_UNKNOWN",
                             status=503, submission_state="unknown")
        error.set_failure(failure, {"request_id": "fixture-request"})
        self.app.processEvents()
        self.assertIs(error.failure, failure)
        self.assertEqual(error.summary.textFormat(), QtCore.Qt.PlainText)
        self.assertEqual(error.summary.text(), "<not markup> Cannot confirm launch")
        self.assertTrue(error.body.isHidden())
        error.toggle.click()
        self.assertFalse(error.body.isHidden())
        self.assertIn('"submission_state": "unknown"', error.details.toPlainText())
        self.assertIn("fixture-request", error.details.toPlainText())
        error.set_failure(None)
        self.assertTrue(error.isHidden())
        self.assertIsNone(error.failure)
        self.assertEqual((self.app.font().toString(), self.app.styleSheet()), (app_font, app_style))
        self.assertEqual(unrelated.font().toString(), old_font)
        root.close()
        root.deleteLater()
        unrelated.deleteLater()

    def test_worker_error_keeps_submission_classification(self):
        def fail():
            raise StudioError("LAUNCH_UNKNOWN", "Launch result unknown", 503,
                              submission_state="unknown", request_id="fixture-request")
        values = []
        task = Task(fail)
        task.signals.error.connect(values.append)
        task.run()
        self.assertEqual(len(values), 1)
        self.assertIsInstance(values[0], ApiFailure)
        self.assertEqual((values[0].code, values[0].status, values[0].submission_state),
                         ("LAUNCH_UNKNOWN", 503, "unknown"))
        self.assertEqual(values[0].details["request_id"], "fixture-request")

    def test_worker_can_finish_after_its_signal_object_is_destroyed(self):
        completed = []
        task = Task(lambda: completed.append("closed-owned-client"))
        task.signals.deleteLater()
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
        task.run()
        self.assertEqual(completed, ["closed-owned-client"])


class ProjectionTests(unittest.TestCase):
    def test_existing_facts_select_only_the_required_stage_and_launch_always_wins(self):
        base = {"codex": {"state": "ready"}, "houdini": {"state": "found"},
                "account": {"status": "signed_in"}}
        cases = [
            ({}, "checking", ""),
            ({**base, "codex": {"state": "missing"}}, "setup", "codex_missing"),
            ({**base, "codex": {"state": "error"}}, "setup", "codex_error"),
            ({**base, "codex": {"state": "incompatible", "attempts": [{"code": "CODEX_VERSION_UNSUPPORTED"}]}},
             "setup", "codex_incompatible"),
            ({**base, "codex": {"state": "incompatible", "attempts": [{"code": "CODEX_START_FAILED"}]}},
             "setup", "codex_error"),
            ({**base, "codex": {"state": "incompatible", "attempts": [{"code": "CODEX_REQUIRED"}]}},
             "setup", "codex_unconfirmed"),
            ({**base, "houdini": {"state": "missing"}}, "setup", "houdini"),
            ({**base, "account": {"status": "signed_out"}}, "authentication", "signed_out"),
            ({**base, "account": {"status": "waiting", "login_pending": True}}, "authentication", "waiting"),
            ({**base, "account": {"status": "unknown"}}, "authentication", "attention"),
            (base, "home", ""),
        ]
        for snapshot, name, mode in cases:
            with self.subTest(name=name, mode=mode):
                self.assertEqual((project_page(snapshot).name, project_page(snapshot).mode), (name, mode))
                self.assertEqual(project_page(snapshot, request_id="original",
                    launch_record={"state": "unknown", "process_may_exist": True}).mode, "unknown")
        self.assertEqual(project_page(base, request_id="original", launch_record={
            "state": "target_opened", "runtime_connected": False, "target_opened": True}).mode, "unknown")
        self.assertEqual(project_page(base, request_id="original", launch_record={
            "state": "rejected", "process_may_exist": True}).mode, "unknown")


class LauncherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        configure_fonts(cls.app)
        cls.paths = AppPaths(Path(__file__).resolve().parents[1])

    def setUp(self):
        picker = patch("studio.ui.launcher.QtWidgets.QFileDialog.getOpenFileName",
                       side_effect=AssertionError("Unexpected native picker in fixture"))
        picker.start()
        self.addCleanup(picker.stop)

    def window(self, state="ready", records=None, services=None):
        window, services = make_fixture_window(self.paths, state, records, services)
        self.addCleanup(window.deleteLater)
        self.addCleanup(window.close)
        return window, services

    def test_returning_user_never_flashes_auth_or_waits_for_the_checking_display_delay(self):
        services = PreviewServices()
        services.probe_gate = threading.Event()
        self.addCleanup(services.probe_gate.set)
        window = StudioLauncher(paths=self.paths, onboarding_factory=services.factory, catalog=services,
            target_factory=PreviewTarget, launch_function=services.launch, status_function=services.query,
            browser_open=services.open_browser, preference_reader=services.read_preference,
            preference_writer=services.write_preference)
        self.addCleanup(window.deleteLater)
        self.addCleanup(window.close)
        window.show()
        seen = []
        window.stack.currentChanged.connect(lambda _index: seen.append(window.current_page))
        self.assertEqual(window.current_page, "checking")
        self.assertFalse(window.checking_box.isVisible())
        services.probe_gate.set()
        process_until(lambda: not window._pending)
        self.assertEqual(window.current_page, "home")
        self.assertNotIn("authentication", seen)
        self.assertFalse(hasattr(window, "primary_action"))
        self.assertEqual(window.size().toTuple(), (760, 560))
        count = len(services.probes)
        for name in ("settings", "diagnostics", "account"):
            window.show_secondary(name)
            window.back_secondary()
        self.assertEqual(len(services.probes), count)
        self.assertEqual(services.launches, [])

    def test_auth_actions_keep_the_original_login_and_completion_goes_to_home(self):
        window, services = self.window("signed_out", records=[])
        size = window.size()
        self.assertEqual(window.current_page, "authentication")
        self.assertFalse(window.open_button.isVisible())
        self.assertEqual(services.opened_urls, [])
        window.login.click()
        process_until(lambda: "account" not in window._pending)
        self.assertEqual(window.projection().mode, "waiting")
        window.reopen_login.click()
        process_until(lambda: "account" not in window._pending)
        self.assertEqual(services.login_starts, 1)
        self.assertEqual(len(services.opened_urls), 2)
        window.account_failed(ApiFailure("暂时无法查询账号", code="ACCOUNT_UNAVAILABLE"))
        window.render()
        self.assertEqual(window.projection().mode, "attention")
        self.assertTrue(window.cancel_login.isEnabled())
        window._snapshot["account"]["action_unknown"] = True
        window.render()
        window.account_action("cancel_login")
        self.assertFalse(window.cancel_login.isEnabled())
        self.assertNotIn("account", window._pending)
        window._snapshot["account"]["action_unknown"] = False
        window.render()
        window.cancel_login.click()
        process_until(lambda: "account" not in window._pending)
        self.assertEqual(window.projection().mode, "signed_out")
        services.state = "ready"
        window.refresh_account()
        process_until(lambda: "account" not in window._pending)
        self.assertEqual(window.current_page, "home")
        self.assertEqual(window.size(), size)
        self.assertEqual(services.launches, [])

    def test_open_and_empty_are_direct_activations_but_selection_remains_pure(self):
        window, services = self.window(records=[])
        window.select_path("D:/fixture/selected.hip")
        process_until(lambda: "selection" not in window._pending)
        self.assertIsNone(window._request_id)
        self.assertEqual(services.admissions, {})
        with patch("studio.ui.launcher.QtWidgets.QFileDialog.getOpenFileName", return_value=("", "")):
            window.open_button.click()
        self.assertEqual(window.current_page, "home")
        with patch("studio.ui.launcher.QtWidgets.QFileDialog.getOpenFileName",
                   return_value=("D:/fixture/explicit.hip", "")):
            window.open_button.click()
        self.assertEqual(window.current_page, "launching")
        request = window._request_id
        process_until(lambda: window._launch_phase is None)
        self.assertEqual(services.launches[0][0], {"kind": "hip", "path": "D:/fixture/explicit.hip"})
        self.assertEqual(services.launches[0][1], request)
        empty, empty_services = self.window(records=[])
        empty.empty_button.click()
        process_until(lambda: empty._launch_phase is None)
        self.assertEqual(empty_services.launches[0][0]["kind"], "empty")

    def test_recent_selects_without_launch_and_duplicate_activation_signals_share_one_request(self):
        window, services = self.window()
        window.recents.setCurrentRow(1)
        item = window.recents.currentItem()
        self.assertEqual(services.launches, [])
        self.assertIsNone(window._request_id)
        window.recents.itemDoubleClicked.emit(item)
        request = window._request_id
        window.recents.itemActivated.emit(item)
        window._recent_rows[1].open_button.click()
        process_until(lambda: window._launch_phase is None)
        self.assertEqual(len(services.launches), 1)
        self.assertEqual(services.launches[0][1], request)
        keyboard, keyboard_services = self.window()
        key = QtGui.QKeyEvent(QtCore.QEvent.KeyPress, QtCore.Qt.Key_Return, QtCore.Qt.NoModifier)
        keyboard._recent_rows[0].keyPressEvent(key)
        keyboard.recents.itemActivated.emit(keyboard.recents.item(0))
        process_until(lambda: keyboard._launch_phase is None)
        self.assertEqual(len(keyboard_services.launches), 1)

    def test_non_home_drop_waits_for_explicit_activation_and_home_drop_opens(self):
        window, services = self.window("signed_out", records=[])
        mime = QtCore.QMimeData()
        mime.setUrls([QtCore.QUrl.fromLocalFile("D:/fixture/dropped.hip")])
        drop = QtGui.QDropEvent(QtCore.QPointF(30, 30), QtCore.Qt.CopyAction, mime,
                               QtCore.Qt.LeftButton, QtCore.Qt.NoModifier)
        window.dropEvent(drop)
        process_until(lambda: "selection" not in window._pending)
        self.assertTrue(drop.isAccepted())
        services.state = "ready"
        window.apply_snapshot(services.snapshot())
        window.render()
        self.assertEqual(window.current_page, "home")
        self.assertTrue(window.deferred_row.isVisible())
        self.assertEqual(services.launches, [])
        window.activate_deferred()
        process_until(lambda: window._launch_phase is None)
        self.assertEqual(len(services.launches), 1)
        direct, direct_services = self.window(records=[])
        enter = QtGui.QDragEnterEvent(QtCore.QPoint(30, 30), QtCore.Qt.CopyAction, mime,
                                    QtCore.Qt.LeftButton, QtCore.Qt.NoModifier)
        direct.dragEnterEvent(enter)
        self.assertTrue(direct.drop_hint.isVisible())
        direct.dropEvent(QtGui.QDropEvent(QtCore.QPointF(30, 30), QtCore.Qt.CopyAction, mime,
                                         QtCore.Qt.LeftButton, QtCore.Qt.NoModifier))
        process_until(lambda: direct._launch_phase is None)
        self.assertEqual(len(direct_services.launches), 1)
        mime.setUrls([QtCore.QUrl("https://example.invalid/asset.hip")])
        self.assertIsNone(direct.dropped_path(mime))

    def test_missing_recent_has_only_object_actions_and_relocating_does_not_activate(self):
        records = [{"path": "D:/fixture/missing.hip", "name": "missing.hip", "directory": "D:/fixture",
                    "last_used_at": 1, "missing": True}]
        window, services = self.window(records=records)
        row = window._recent_rows[0]
        row.setFocus()
        row.keyPressEvent(QtGui.QKeyEvent(QtCore.QEvent.KeyPress, QtCore.Qt.Key_F10, QtCore.Qt.ShiftModifier))
        self.assertEqual([action.text() for action in window._menu.actions()],
                         ["重新定位", "复制原路径", "从最近列表移除"])
        window._menu.close()
        self.assertEqual(row.height(), 64)
        self.assertNotEqual(row.more_button.focusPolicy(), QtCore.Qt.NoFocus)
        window.activate_recent_record(records[0])
        self.assertEqual(window.current_page, "home")
        self.assertIsNone(window._request_id)
        with patch("studio.ui.launcher.QtWidgets.QFileDialog.getOpenFileName",
                   return_value=("D:/fixture/relocated.hip", "")):
            window.relocate_recent(records[0])
        process_until(lambda: not window._pending)
        self.assertEqual(services.records[0]["path"], "D:/fixture/relocated.hip")
        self.assertEqual(services.launches, [])
        window.forget_recent(services.records[0])
        process_until(lambda: not window._pending)
        self.assertEqual(services.records, [])

    def test_unknown_launch_stays_on_original_request_despite_account_and_page_changes(self):
        services = PreviewServices(records=[])
        services.lose_launch = True
        window, services = self.window(services=services)
        window.empty_button.click()
        request = window._request_id
        process_until(lambda: window._launch_phase is None)
        self.assertEqual(window.projection().mode, "unknown")
        services.state = "signed_out"
        window.apply_snapshot(services.snapshot())
        window.show_secondary("settings")
        window.back_secondary()
        window.activate_target(PreviewTarget.empty())
        window.return_after_launch()
        self.assertEqual(window.current_page, "launching")
        self.assertEqual(window._request_id, request)
        services.admissions[request].update(state="runtime_connected", runtime_connected=True, target_opened=False)
        window.query_launch()
        process_until(lambda: "status" not in window._pending)
        self.assertEqual(window.projection().mode, "scene")
        self.assertFalse(window.minimize_timer.isActive())
        self.assertEqual(services.queries, [request])
        self.assertEqual(len(services.launches), 1)

    def test_opened_minimizes_once_and_details_prevent_focus_stealing(self):
        services = PreviewServices(records=[])
        services.launch_state = "target_opened"
        window, services = self.window(services=services)
        window.empty_button.click()
        process_until(window.isMinimized, timeout=1500)
        window.showNormal()
        window.apply_launch_status(services.admissions[window._request_id])
        window.render()
        self.assertFalse(window.minimize_timer.isActive())
        self.assertFalse(window.isMinimized())
        detail_services = PreviewServices(records=[])
        detail_services.launch_state = "target_opened"
        details, detail_services = self.window(services=detail_services)
        details.empty_button.click()
        process_until(lambda: details._launch_phase is None)
        details.show_details()
        details.back_secondary()
        details.apply_launch_status(detail_services.admissions[details._request_id])
        self.assertFalse(details.minimize_timer.isActive())

    def test_minimize_preference_is_one_local_field_and_does_not_touch_environment_preferences(self):
        with tempfile.TemporaryDirectory(dir=self.paths.local()) as directory:
            paths = AppPaths(self.paths.root, data_root=Path(directory) / "state", cache_root=Path(directory) / "cache")
            self.assertTrue(read_minimize_preference(paths))
            write_minimize_preference(paths, False)
            self.assertFalse(read_minimize_preference(paths))
            self.assertFalse(paths.data("environment-preferences.json").exists())
        window, services = self.window()
        window.show_secondary("settings")
        window.minimize_choice.setChecked(False)
        process_until(lambda: "preference-write" not in window._pending)
        self.assertEqual(services.preference_writes, [False])

    def test_preflight_failure_has_an_explicit_safe_return_and_no_launch(self):
        window, services = self.window(records=[])
        backend = services.backends[0]
        prepare = backend.prepare_launch
        backend.prepare_launch = lambda: {**prepare(), "codex_home": str(self.paths.local("different-profile"))}
        window.empty_button.click()
        process_until(lambda: window._launch_phase is None)
        self.assertEqual(window.projection().mode, "failed")
        self.assertEqual(window.error_details.failure.code, "PROFILE_MISMATCH")
        self.assertEqual(services.launches, [])
        self.assertTrue(window.launch_back.isVisible())
        window.launch_back.click()
        process_until(lambda: not window._pending)
        self.assertEqual(window.current_page, "home")
        self.assertIsNone(window._request_id)
        self.assertEqual(len(services.backends), 2)

    def test_close_during_login_does_not_block_or_open_a_late_browser(self):
        window, services = self.window("signed_out", records=[])
        gate, entered = threading.Event(), threading.Event()
        self.addCleanup(gate.set)
        backend = services.backends[0]
        original = backend.login_start
        def delayed():
            entered.set()
            gate.wait(1)
            return original()
        backend.login_start = delayed
        window.login.click()
        process_until(entered.is_set)
        start = time.monotonic()
        window.close()
        self.assertLess(time.monotonic() - start, 0.2)
        gate.set()
        process_until(lambda: backend.closed and not window._tasks)
        self.assertEqual(services.opened_urls, [])

    def test_recheck_preserves_failed_owner_close_and_pages_do_not_replace_it(self):
        window, services = self.window(records=[])
        backend = services.backends[0]
        close = backend.close
        backend.close = lambda: (_ for _ in ()).throw(StudioError("CLOSE_UNKNOWN", "连接关闭未确认"))
        self.addCleanup(setattr, backend, "close", close)
        window.probe()
        process_until(lambda: not window._pending)
        self.assertEqual(len(services.backends), 1)
        window.show_secondary("settings")
        window.show_details()
        window.back_secondary()
        self.assertEqual(len(services.backends), 1)
        backend.close = close
        window.probe()
        process_until(lambda: not window._pending)
        self.assertTrue(backend.closed)
        self.assertEqual(len(services.backends), 2)


if __name__ == "__main__":
    unittest.main()
