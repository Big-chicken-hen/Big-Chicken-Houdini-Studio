"""Native launcher drawing and lifecycle checks; not Houdini verification."""
import os
import unittest
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6 import QtCore, QtWidgets  # noqa: E402
from scripts.preview_ui import configure_preview_fonts  # noqa: E402
from studio.ui.launcher import StudioLauncher  # noqa: E402


class PortalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        configure_preview_fonts(cls.app)

    def test_native_render_and_motion_only_while_visible_and_launching(self):
        with patch("studio.ui.launcher.discover_houdini", return_value=[]):
            window = StudioLauncher()
        try:
            window.resize(940, 700)
            window.show()
            self.app.processEvents()
            self.assertFalse(window.portal.motion.isActive())
            image = window.grab().toImage()
            self.assertFalse(image.isNull())
            self.assertEqual(window.status.textFormat(), QtCore.Qt.PlainText)
            self.assertTrue(window.output_path.isReadOnly())
            self.assertGreater(window.launch_button.width(), 200)
            window.portal.set_launching(True)
            self.assertTrue(window.portal.motion.isActive())
            window.hide()
            self.assertFalse(window.portal.motion.isActive())
            window.show()
            self.assertTrue(window.portal.motion.isActive())
            window.portal.set_launching(False)
            self.assertFalse(window.portal.motion.isActive())
            window.failed("<ERROR> a long native error must remain literal and readable")
            self.assertIn("<ERROR>", window.status.text())
        finally:
            window.close()
            window.deleteLater()
            self.app.processEvents()
