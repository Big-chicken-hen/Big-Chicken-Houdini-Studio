"""Focused launcher interactions; explicit fixtures, no real Houdini launch."""
import os
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6 import QtCore, QtWidgets  # noqa: E402

from scripts.preview_launcher import PreviewWorkspaces, configure_fonts, process_until  # noqa: E402
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

    def make_window(self, names=("Test workspace",), launch_function=None):
        window = StudioLauncher(paths=self.paths, workspaces=PreviewWorkspaces(names),
                                installations=[{"label": "Fixture Houdini", "path": "C:/fixture/houdini.exe"}],
                                codex_path="C:/fixture/codex.exe", launch_function=launch_function)
        window.show()
        self.app.processEvents()
        self.addCleanup(window.deleteLater)
        self.addCleanup(window.close)
        return window

    def test_empty_workspace_leads_to_explicit_create_and_settings_stay_secondary(self):
        window = self.make_window(names=())
        self.assertTrue(window.empty_workspace.isVisible())
        self.assertTrue(window.projects.isHidden())
        self.assertFalse(window.launch_button.isEnabled())
        window.workspace_name.setText("新作品")
        window.create_first.click()
        self.assertEqual(window.workspaces.records, [{"workspace_id": "preview_0", "name": "新作品"}])
        self.assertEqual(window.selected_workspace(), "preview_0")
        self.assertTrue(window.environment.isVisible())
        self.assertTrue(window.launch_button.isEnabled())
        self.assertTrue(window.settings.isHidden())
        window.settings_toggle.click()
        self.assertFalse(window.settings.isHidden())
        self.assertTrue(window.output_path.isReadOnly())

    def test_error_text_survives_polls_is_copyable_and_small_window_keeps_actions(self):
        window = self.make_window()
        text = "<ERROR> 真实文字不作HTML解析\n" + "可复制的完整诊断。" * 250 + "\nEND"
        window.failed(text)
        window.update_selection()
        window.statuses_read({"another_workspace": {"directory": "old", "state": "ready"}})
        self.assertEqual(window.status_details.toPlainText(), text)
        window.copy_status.click()
        self.assertEqual(QtWidgets.QApplication.clipboard().text(), text)
        window.resize(800, 620)
        self.app.processEvents()
        self.assertTrue(window.status_card.isVisible())
        self.assertTrue(window.launch_button.isVisible())
        top = window.launch_button.mapTo(window, QtCore.QPoint(0, 0))
        self.assertLess(top.y() + window.launch_button.height(), window.height())
        self.assertLessEqual(window.width(), 800)
        self.assertLessEqual(window.height(), 620)

    def test_launch_is_nonblocking_cannot_duplicate_and_waits_for_runtime_fact(self):
        gate = threading.Event()
        calls = []

        def launch_fixture(paths, workspace, houdini, codex, hip):
            calls.append((workspace, houdini, codex, hip))
            gate.wait(1)
            return {"directory": str(paths.local("launcher-fixture-session")), "session_id": "fixture_session"}

        window = self.make_window(launch_function=launch_fixture)
        window.hip.setText("C:/fixture/start.hip")
        beats = []
        timer = QtCore.QTimer()
        timer.setInterval(10)
        timer.timeout.connect(lambda: beats.append(True))
        timer.start()
        window.start_session()
        window.start_session()
        self.assertTrue(window.busy)
        self.assertFalse(window.launch_button.isEnabled())
        QtCore.QTimer.singleShot(70, gate.set)
        process_until(lambda: not window.busy)
        timer.stop()
        self.assertEqual(calls, [("preview_0", "C:/fixture/houdini.exe", "C:/fixture/codex.exe", "C:/fixture/start.hip")])
        self.assertGreater(len(beats), 1)
        self.assertEqual(window.status_code.text(), "CONNECTING")
        self.assertIn("正在连接", window.launch_button.text())
        self.assertFalse(window.launch_button.isEnabled())
        directory = window.sessions["preview_0"]["directory"]
        window.statuses_read({"preview_0": {"directory": "older_session", "state": "ready"}})
        self.assertEqual(window.status_code.text(), "CONNECTING")
        window.statuses_read({"preview_0": {"directory": directory, "state": "ready"}})
        self.assertEqual(window.status_code.text(), "CONNECTED")

    def test_activity_stops_hidden_minimized_and_idle_and_art_cache_is_reused(self):
        window = self.make_window()
        self.assertFalse(window.artwork.source.isNull())
        window.grab()
        cached = window.artwork._cache.cacheKey()
        window.artwork.update()
        self.app.processEvents()
        self.assertEqual(window.artwork._cache.cacheKey(), cached)
        self.assertFalse(window.activity.motion.isActive())
        window.activity.set_active(True)
        self.assertTrue(window.activity.motion.isActive())
        window.hide()
        self.assertFalse(window.activity.motion.isActive())
        window.show()
        self.app.processEvents()
        self.assertTrue(window.activity.motion.isActive())
        window.showMinimized()
        self.app.processEvents()
        self.assertFalse(window.activity.motion.isActive())
        window.showNormal()
        self.app.processEvents()
        self.assertTrue(window.activity.motion.isActive())
        window.activity.set_active(False)
        self.assertFalse(window.activity.motion.isActive())

    def test_missing_environment_has_visible_guidance_without_a_fake_launch(self):
        window = self.make_window()
        window.houdini.clear()
        window.codex.clear()
        self.assertEqual(window.status_code.text(), "SETUP")
        self.assertIn("Houdini", window.status_details.toPlainText())
        self.assertFalse(window.busy)
        self.assertFalse(window.activity.motion.isActive())
        window.houdini.addItem("Fixture Houdini", "C:/fixture/houdini.exe")
        window.houdini.setCurrentIndex(0)
        window.start_session()
        self.assertTrue(window.settings_toggle.isChecked())
        self.assertFalse(window.settings.isHidden())
        self.assertFalse(window.busy)


if __name__ == "__main__":
    unittest.main()
