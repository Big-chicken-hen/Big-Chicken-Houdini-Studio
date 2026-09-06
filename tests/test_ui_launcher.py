"""Focused launcher interactions; explicit fixtures, no real Houdini launch."""
import os
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6 import QtCore, QtGui, QtWidgets  # noqa: E402

from scripts.preview_launcher import PreviewServices, PreviewTarget, configure_fonts, make_fixture_window, process_until  # noqa: E402
from studio.common import AppPaths  # noqa: E402
from studio.ui.launcher import StudioLauncher  # noqa: E402
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


class LauncherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        configure_fonts(cls.app)
        cls.paths = AppPaths(Path(__file__).resolve().parents[1])

    def setUp(self):
        picker = patch("studio.ui.launcher.QtWidgets.QFileDialog.getOpenFileName",
                       side_effect=AssertionError("Unexpected file picker in offscreen test"))
        picker.start()
        self.addCleanup(picker.stop)

    def window(self, state="ready", records=None, services=None):
        window, services = make_fixture_window(self.paths, state, records, services)
        self.addCleanup(window.deleteLater)
        self.addCleanup(window.close)
        return window, services

    def test_target_selection_does_not_admit_or_create_a_workspace(self):
        window, services = self.window(records=[])
        self.assertEqual(services.launches, [])
        self.assertEqual(services.admissions, {})
        window.empty_button.click()
        window.empty_button.click()
        self.assertEqual(window._target.kind, "empty")
        with patch("studio.ui.launcher.QtWidgets.QFileDialog.getOpenFileName",
                   return_value=("D:/fixture/bookcase.hip", "")):
            window.open_button.click()
        process_until(lambda: "target" not in window._pending)
        self.assertEqual(window._target.to_dict(), {"kind": "hip", "path": "D:/fixture/bookcase.hip"})
        self.assertEqual(services.launches, [])
        self.assertEqual(services.admissions, {})
        self.assertEqual(len(services.probes), 1)
        self.assertEqual(window.launch_button.text(), "Launch Studio")

    def test_drop_accepts_one_local_hip_and_empty_selection_fences_a_late_path(self):
        window, services = self.window(records=[])
        mime = QtCore.QMimeData()
        mime.setUrls([QtCore.QUrl("https://example.invalid/asset.hip")])
        self.assertIsNone(window.dropped_path(mime))
        mime.setUrls([QtCore.QUrl.fromLocalFile("D:/fixture/a.hip"),
                      QtCore.QUrl.fromLocalFile("D:/fixture/b.txt")])
        self.assertIsNone(window.dropped_path(mime))
        mime.setUrls([QtCore.QUrl.fromLocalFile("D:/fixture/a.hiplc")])
        self.assertTrue(window.dropped_path(mime).endswith("a.hiplc"))
        drop = QtGui.QDropEvent(QtCore.QPointF(20, 20), QtCore.Qt.CopyAction, mime,
                               QtCore.Qt.LeftButton, QtCore.Qt.NoModifier)
        window.dropEvent(drop)
        process_until(lambda: "target" not in window._pending)
        self.assertTrue(drop.isAccepted())
        self.assertTrue(window._target.path.endswith("a.hiplc"))
        gate = threading.Event()
        self.addCleanup(gate.set)
        class DelayedTarget(PreviewTarget):
            @classmethod
            def hip(cls, path):
                gate.wait(1)
                return super().hip(path)
        window.target_factory = DelayedTarget
        window.select_path("D:/fixture/old.hip")
        window.select_empty()
        gate.set()
        process_until(lambda: not window._tasks)
        self.assertEqual(window._target.kind, "empty")
        self.assertEqual(services.launches, [])

    def test_missing_recent_can_be_removed_without_a_launch(self):
        rows = [{"path": "D:/missing/bookcase.hip", "name": "bookcase.hip", "directory": "D:/missing",
                 "last_used_at": 1788670800, "workspace_id": "keep-association", "missing": True}]
        window, services = self.window(records=rows)
        self.assertIsNone(window._target)
        self.assertFalse(window.launch_button.isEnabled())
        self.assertTrue(window.relocate.isVisible())
        window.remove_recent.click()
        process_until(lambda: not window._pending)
        self.assertEqual(services.records, [])
        self.assertEqual(window._target.kind, "empty")
        self.assertEqual(services.admissions, {})
        self.assertEqual(services.launches, [])

    def test_lost_launch_response_queries_same_id_and_connection_is_not_opened(self):
        services = PreviewServices(records=[])
        services.launch_gate = gate = threading.Event()
        services.lose_launch = True
        services.launch_state = "runtime_connected"
        self.addCleanup(gate.set)
        window, services = self.window(services=services)
        beats = []
        timer = QtCore.QTimer()
        timer.setInterval(5)
        timer.timeout.connect(lambda: beats.append(True))
        timer.start()
        window.start_session()
        window.start_session()
        process_until(lambda: bool(services.launches))
        self.assertTrue(services.backends[0].closed)
        self.assertFalse(window.launch_button.isEnabled())
        QtCore.QTimer.singleShot(40, gate.set)
        process_until(lambda: window._launch_phase is None)
        timer.stop()
        self.assertGreater(len(beats), 1)
        self.assertEqual(window._launch_record["state"], "unknown")
        request_id = window._request_id
        window.start_session()
        window.primary_action()
        process_until(lambda: "status" not in window._pending)
        self.assertEqual(window._launch_record["state"], "runtime_connected")
        self.assertNotEqual(window.launch_button.text(), "Studio 已打开")
        services.admissions[request_id].update(state="target_opened", target_opened=True, runtime_connected=True)
        window.query_launch()
        process_until(lambda: not window._pending)
        self.assertEqual(window.launch_button.text(), "Studio 已打开")
        self.assertFalse(window.launch_button.isEnabled())
        self.assertEqual(len(services.launches), 1)
        self.assertTrue(all(value == request_id for value in services.queries))

    def test_login_requires_a_click_and_unknown_account_is_not_signed_out(self):
        window, services = self.window(state="signed_out", records=[])
        self.assertEqual(services.opened_urls, [])
        window.launch_button.click()
        process_until(lambda: "account" not in window._pending)
        self.assertEqual(window._snapshot["account"]["status"], "waiting")
        self.assertEqual(len(services.opened_urls), 1)
        self.assertNotIn("state=fixture", window.error_details.details.toPlainText())
        window.account_failed(ApiFailure("暂时无法查询账号", code="ACCOUNT_UNAVAILABLE"))
        window.render()
        self.assertEqual((window._snapshot["account"]["login_pending"], window.reopen_login.isVisible(),
                          window.cancel_login.isEnabled()), (True, True, True))
        window._snapshot["account"]["action_unknown"] = True
        window.render()
        window.account_action("cancel_login")
        self.assertFalse(window.cancel_login.isEnabled())
        self.assertNotIn("account", window._pending)
        window._snapshot["account"]["action_unknown"] = False
        window.render()
        window.cancel_login.click()
        process_until(lambda: "account" not in window._pending)
        self.assertEqual(window._snapshot["account"]["status"], "signed_out")
        services.state = "account_unknown"
        window.refresh_account()
        process_until(lambda: "account" not in window._pending)
        self.assertEqual(window._snapshot["account"]["status"], "unknown")
        self.assertEqual(window.launch_button.text(), "重新检查账号")
        self.assertEqual(services.launches, [])

    def test_override_replaces_closed_owner_and_clear_is_an_explicit_override(self):
        window, services = self.window(records=[])
        self.assertEqual(services.probes[0], {"codex_override": None, "houdini_override": None})
        window.codex.clear()
        window.overrides_changed("codex")
        window.probe()
        process_until(lambda: "probe" not in window._pending)
        self.assertEqual(len(services.backends), 2)
        self.assertTrue(services.backends[0].closed)
        self.assertFalse(services.backends[1].closed)
        self.assertEqual(services.probes[-1]["codex_override"], "")

    def test_failed_account_query_stays_unknown_and_prepare_failure_never_submits(self):
        window, services = self.window(records=[])
        def fail_account():
            raise StudioError("ACCOUNT_UNCONFIRMED", "暂时无法确认账号", 503)
        services.backends[0].account_read = fail_account
        window.refresh_account()
        process_until(lambda: "account" not in window._pending)
        self.assertEqual(window._snapshot["account"]["status"], "unknown")
        self.assertEqual(window.launch_button.text(), "重新检查账号")
        window.apply_snapshot(services.snapshot())
        window.render()
        services.backends[0].prepare_launch = fail_account
        window.start_session()
        process_until(lambda: "prepare" not in window._pending)
        self.assertEqual(services.launches, [])
        self.assertIsNone(window._request_id)
        self.assertEqual(window.launch_button.text(), "重新检查环境")

    def test_close_during_login_does_not_wait_or_open_a_late_browser(self):
        window, services = self.window(state="signed_out", records=[])
        gate = threading.Event()
        entered = threading.Event()
        self.addCleanup(gate.set)
        backend = services.backends[0]
        original = backend.login_start
        def delayed():
            entered.set()
            gate.wait(1)
            return original()
        backend.login_start = delayed
        window.launch_button.click()
        process_until(entered.is_set)
        start = time.monotonic()
        window.close()
        self.assertLess(time.monotonic() - start, 0.2)
        gate.set()
        process_until(lambda: backend.closed and not window._tasks)
        self.assertEqual(services.opened_urls, [])
        self.assertEqual(services.launches, [])

    def test_compact_layout_keeps_primary_action_visible_with_long_details(self):
        window, services = self.window()
        window.resize(560, 600)
        window.show_failure(ApiFailure("<Failure> 请查看下一步\n" + "较长诊断文字。" * 200, code="FIXTURE"))
        window.error_details.toggle.setChecked(True)
        window.advanced_toggle.click()
        self.app.processEvents()
        corner = window.launch_button.mapTo(window, QtCore.QPoint(window.launch_button.width(), window.launch_button.height()))
        self.assertLessEqual(corner.x(), window.width())
        self.assertLessEqual(corner.y(), window.height())
        self.assertGreaterEqual(window.launch_button.height(), 40)
        self.assertGreaterEqual(window.open_button.height(), 32)
        self.assertTrue(window.launch_button.isVisible())
        self.assertEqual(services.launches, [])

    def test_first_use_keeps_all_three_readiness_rows_visible(self):
        window, _services = self.window(state="signed_out", records=[])
        for width, height in ((780, 740), (560, 600)):
            window.resize(width, height)
            for _ in range(3):
                self.app.processEvents()
            previous_bottom = -1
            for row in (window.account_row, window.codex_row, window.houdini_row):
                with self.subTest(width=width, row=row.title.text()):
                    self.assertTrue(row.parentWidget().rect().contains(row.geometry()))
                    self.assertGreater(row.y(), previous_bottom)
                    self.assertGreaterEqual(row.text.height(), row.text.heightForWidth(row.text.width()))
                    self.assertEqual(row.text.visibleRegion().boundingRect(), row.text.rect())
                    previous_bottom = row.geometry().bottom()

    def test_mismatched_account_profile_never_launches(self):
        window, services = self.window(records=[])
        backend = services.backends[0]
        prepare = backend.prepare_launch
        backend.prepare_launch = lambda: {**prepare(), "codex_home": str(self.paths.local("different-profile"))}
        window.start_session()
        process_until(lambda: not window._pending)
        self.assertEqual(window.error_details.failure.code, "PROFILE_MISMATCH")
        self.assertIsNone(window._request_id)
        self.assertEqual(services.launches, [])

    def test_failed_onboarding_close_is_retained_until_a_successful_explicit_recheck(self):
        window, services = self.window(records=[])
        backend = services.backends[0]
        close = backend.close
        def fail_close():
            raise StudioError("ONBOARDING_CLOSE_FAILED", "旧账号连接尚未关闭", 503)
        backend.close = fail_close
        self.addCleanup(setattr, backend, "close", close)
        window.probe()
        process_until(lambda: not window._pending)
        self.assertEqual(len(services.backends), 1)
        self.assertFalse(backend.closed)
        self.assertEqual(window._snapshot["account"]["status"], "unknown")
        self.assertEqual(services.launches, [])
        backend.close = close
        window.probe()
        process_until(lambda: not window._pending)
        self.assertTrue(backend.closed)
        self.assertEqual(len(services.backends), 2)
        self.assertEqual([event for event, _paths in services.lifecycle], ["created", "closed", "created"])


if __name__ == "__main__":
    unittest.main()
