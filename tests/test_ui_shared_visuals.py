"""Shared presentation keeps host settings and structured error facts intact."""
import os
import unittest

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6 import QtCore, QtWidgets  # noqa: E402

from studio.ui.icons import icon_diagnostics  # noqa: E402
from studio.ui.shared import ApiFailure, ErrorDetails  # noqa: E402
from studio.ui.theme import COLORS, apply_theme, studio_stylesheet  # noqa: E402


class SharedVisualTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_popup_and_root_style_do_not_change_the_host_application(self):
        original = (self.app.font().toString(), self.app.palette().cacheKey(), self.app.styleSheet())
        host_label = QtWidgets.QLabel("Host content")
        host_font = host_label.font().toString()
        root = QtWidgets.QWidget()
        root.setObjectName("studioVisualFixture")
        root.setLayout(QtWidgets.QVBoxLayout())
        root.layout().addWidget(QtWidgets.QPushButton("普通动作"))
        root.layout().addWidget(QtWidgets.QLineEdit("独立输入"))
        apply_theme(root)
        popup = QtWidgets.QMenu(root)
        popup.setObjectName("studioPopupFixture")
        popup.addAction("现有动作")
        apply_theme(popup, popup=True)
        self.assertEqual(popup.property("studioRole"), "popup")
        for rule in popup.styleSheet().split("}"):
            if "{" in rule:
                selectors = rule.split("{", 1)[0]
                self.assertTrue(all("#studioPopupFixture" in selector for selector in selectors.split(",")))
        sheet = studio_stylesheet("studioVisualFixture")
        self.assertIn("border: 1px solid " + COLORS["border_control"], sheet)
        self.assertNotIn("border: 2px solid", sheet)
        self.assertEqual(COLORS["border_subtle"], "#333640")
        root.show()
        self.app.processEvents()
        self.assertEqual((self.app.font().toString(), self.app.palette().cacheKey(), self.app.styleSheet()), original)
        self.assertEqual(host_label.font().toString(), host_font)
        root.deleteLater()
        host_label.deleteLater()
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)

    def test_error_disclosure_preserves_original_failure_without_adding_actions(self):
        frame = ErrorDetails()
        error = ApiFailure("暂时无法确认\n原始信息", code="QUERY_UNKNOWN", status=503,
                           submission_state="unknown", details={"request_id": "fixture"})
        frame.set_failure(error)
        frame.show()
        self.app.processEvents()
        self.assertIs(frame.failure, error)
        self.assertEqual(frame.summary.text(), "暂时无法确认")
        self.assertTrue(frame.body.isHidden())
        self.assertEqual(len(frame.findChildren(QtWidgets.QAbstractButton)), 1)
        self.assertFalse(frame.toggle.icon().isNull())
        frame.toggle.click()
        self.assertFalse(frame.body.isHidden())
        self.assertIn('"submission_state": "unknown"', frame.details.toPlainText())
        self.assertIn('"request_id": "fixture"', frame.details.toPlainText())
        self.assertEqual(frame.toggle.text(), "收起详情")
        if icon_diagnostics():
            self.assertIn('"ui_resources"', frame.details.toPlainText())
        frame.set_failure(None)
        self.assertTrue(frame.isHidden())
        frame.deleteLater()
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)


if __name__ == "__main__":
    unittest.main()
