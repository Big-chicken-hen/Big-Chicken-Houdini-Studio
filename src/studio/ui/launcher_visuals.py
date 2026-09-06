"""Small Launcher widgets using Qt standard icons, with no custom artwork."""
from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from .shared import label
from .theme import COLORS, studio_stylesheet

LAUNCHER_STYLE = studio_stylesheet("studioLauncher") + (
    "\nQWidget#studioLauncher QPushButton#primary { min-height: 26px; }"
    "\nQWidget#studioLauncher QWidget#launcherBody { background: " + COLORS["background"] + "; }")


class _StatusMark(QtWidgets.QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(18, 20)
        self.setAlignment(QtCore.Qt.AlignCenter)
        self.tone = None
        self.set_tone("neutral")

    def set_tone(self, tone):
        if tone == self.tone:
            return
        self.tone = tone
        self.refresh_icon()

    def refresh_icon(self):
        standard = {"success": QtWidgets.QStyle.SP_DialogApplyButton,
                    "warning": QtWidgets.QStyle.SP_MessageBoxWarning,
                    "unknown": QtWidgets.QStyle.SP_MessageBoxWarning,
                    "error": QtWidgets.QStyle.SP_MessageBoxCritical}.get(
                        self.tone, QtWidgets.QStyle.SP_MessageBoxInformation)
        icon = self.style().standardIcon(standard)
        self.setPixmap(icon.pixmap(QtCore.QSize(16, 16), self.devicePixelRatioF()))

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() in {QtCore.QEvent.StyleChange, QtCore.QEvent.DevicePixelRatioChange}:
            self.refresh_icon()


class ReadinessRow(QtWidgets.QWidget):
    def __init__(self, title, parent=None):
        super().__init__(parent)
        row = QtWidgets.QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        self.marker = _StatusMark()
        self.title = label(title)
        self.title.setMinimumWidth(76)
        self.text = label("正在检查…", wrap=True)
        self.text.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Preferred)
        row.addWidget(self.marker)
        row.addWidget(self.title)
        row.addWidget(self.text, 1)

    def set_status(self, text, tone="neutral"):
        self.text.setText(text)
        self.marker.set_tone(tone)
        self.setAccessibleName(self.title.text() + "：" + text)
