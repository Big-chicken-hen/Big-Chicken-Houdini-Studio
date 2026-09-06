"""Approved packaged SVGs and native widget lifetimes, without Launcher/Houdini."""
import os
from pathlib import Path
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6 import QtCore, QtGui, QtWidgets  # noqa: E402
from shiboken6 import isValid  # noqa: E402

from studio.ui import icons  # noqa: E402


class IconTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        icons._icons.clear()
        icons._diagnostics.clear()

    def test_only_the_approved_subset_and_full_license_notices_are_packaged(self):
        folder = Path(icons.__file__).parent / icons.RESOURCE_DIRECTORY
        self.assertEqual(len(icons.APPROVED_ICONS), 23)
        self.assertEqual({path.stem for path in folder.glob("*.svg")}, icons.APPROVED_ICONS)
        for name in icons.APPROVED_ICONS:
            root = ET.fromstring((folder / (name + ".svg")).read_bytes())
            self.assertEqual(root.attrib, {"width": "24", "height": "24", "viewBox": "0 0 24 24",
                "fill": "none", "stroke": "currentColor", "stroke-width": "2",
                "stroke-linecap": "round", "stroke-linejoin": "round"})
            self.assertTrue(all(node.tag.rsplit("}", 1)[-1] in
                {"svg", "path", "circle", "rect", "line", "polyline", "polygon"} for node in root.iter()))
        isc = (folder / "LICENSE").read_text(encoding="utf-8")
        mit = (folder / "LICENSE-Feather").read_text(encoding="utf-8")
        self.assertIn("ISC License", isc)
        self.assertIn("Lucide Contributors 2022", isc)
        self.assertIn("permission notice appear in all copies", isc)
        self.assertIn("The MIT License (MIT)", mit)
        self.assertIn("Cole Bemis", mit)
        self.assertIn("The above copyright notice and this permission notice", mit)
        self.assertIn("SOFTWARE", mit.splitlines()[-1])

    def test_rendering_reuses_cache_and_preserves_logical_size_at_fractional_dpr(self):
        for name in icons.APPROVED_ICONS:
            rendered = icons.icon(name)
            self.assertFalse(rendered.isNull(), name)
            image = rendered.pixmap(20, 20).toImage().convertToFormat(QtGui.QImage.Format_ARGB32)
            self.assertGreater(max(bytes(image.constBits())[3::4]), 0, name)
        for dpr in (1.0, 1.25, 1.5, 2.0):
            with self.subTest(dpr=dpr):
                rendered = icons.icon("folder-open", size=20, color="#F4F4F6", dpr=dpr)
                again = icons.icon("folder-open", size=20, color="#f4f4f6", dpr=dpr)
                self.assertEqual(rendered.cacheKey(), again.cacheKey())
                pixmap = rendered.pixmap(QtCore.QSize(20, 20), dpr)
                self.assertEqual(pixmap.size(), QtCore.QSize(round(20 * dpr), round(20 * dpr)))
                self.assertEqual(pixmap.deviceIndependentSize(), QtCore.QSizeF(20, 20))
        self.assertEqual(icons.icon_diagnostics(), ())

    def test_missing_resources_keep_the_same_button_action_and_readable_text(self):
        button = QtWidgets.QPushButton("打开 HIP")
        calls = []
        button.clicked.connect(lambda: calls.append("open"))
        with patch.object(icons, "_svg", side_effect=FileNotFoundError()):
            icons.set_button_icon(button, "folder-open", text="打开 HIP", icon_only=True)
        self.assertTrue(button.icon().isNull())
        self.assertEqual(button.text(), "打开 HIP")
        self.assertEqual(button.accessibleName(), "打开 HIP")
        button.click()
        self.assertEqual(calls, ["open"])
        self.assertEqual(icons.icon_diagnostics()[0]["code"], "ICON_RESOURCE_MISSING")
        icons.set_button_icon(button, "not-approved", text="已有动作", icon_only=True)
        self.assertTrue(button.icon().isNull())
        self.assertEqual(button.text(), "已有动作")
        button.deleteLater()
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)

    def test_display_change_and_hidden_minimized_idle_destroyed_loading_lifetimes(self):
        root = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(root)
        button = QtWidgets.QPushButton("发送")
        icons.set_button_icon(button, "arrow-up", text="发送", icon_only=True)
        layout.addWidget(button)
        # Attaching a previously parentless button must keep its own event filter.
        before_disable = button.icon().cacheKey()
        button.setEnabled(False)
        self.assertNotEqual(button.icon().cacheKey(), before_disable)
        button.setEnabled(True)
        previous = button.icon().cacheKey()
        with patch.object(button, "devicePixelRatioF", return_value=2.0):
            QtWidgets.QApplication.sendEvent(button, QtCore.QEvent(QtCore.QEvent.DevicePixelRatioChange))
            self.assertNotEqual(button.icon().cacheKey(), previous)
            self.assertEqual(button.icon().pixmap(QtCore.QSize(20, 20), 2.0).size(), QtCore.QSize(40, 40))
        loading = icons.LoadingIcon()
        layout.addWidget(loading)
        loading.set_busy(True)
        self.assertFalse(loading._timer.isActive())
        root.show()
        self.app.processEvents()
        self.assertTrue(loading._timer.isActive())
        root.showMinimized()
        self.app.processEvents()
        self.assertFalse(loading._timer.isActive())
        root.showNormal()
        self.app.processEvents()
        self.assertTrue(loading._timer.isActive())
        root.hide()
        self.app.processEvents()
        self.assertFalse(loading._timer.isActive())
        root.show()
        loading.set_busy(False)
        self.assertFalse(loading._timer.isActive())
        loading.set_busy(True)
        timer = loading._timer
        root.deleteLater()
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
        self.assertFalse(isValid(timer))
        self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
