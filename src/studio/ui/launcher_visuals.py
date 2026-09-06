"""Small Launcher presentation widgets. No artwork, services or execution state."""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from .shared import label
from .theme import COLORS, studio_stylesheet

LAUNCHER_STYLE = studio_stylesheet("studioLauncher") + (
    "\nQWidget#studioLauncher QPushButton#primary { min-height: 26px; }"
    "\nQWidget#studioLauncher QWidget#launcherBody { background: " + COLORS["background"] + "; }")


class _StatusMark(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(18, 20)
        self.tone = "neutral"

    def set_tone(self, tone):
        self.tone = tone
        self.update()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        color = COLORS.get(self.tone, COLORS["text_muted"])
        painter.setPen(QtGui.QPen(QtGui.QColor(color), 1.5))
        painter.setBrush(QtCore.Qt.NoBrush)
        if self.tone == "success":
            painter.drawLine(QtCore.QPointF(3, 10), QtCore.QPointF(7, 14))
            painter.drawLine(QtCore.QPointF(7, 14), QtCore.QPointF(14, 6))
        else:
            painter.drawEllipse(QtCore.QRectF(3, 4, 12, 12))
            if self.tone in {"error", "warning", "unknown"}:
                painter.drawLine(QtCore.QPointF(9, 7), QtCore.QPointF(9, 10))
                painter.drawPoint(QtCore.QPointF(9, 13))
        painter.end()


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


class LaunchActivity(QtWidgets.QWidget):
    """A small indeterminate indicator; no fabricated completion percentage."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(32, 12)
        self.requested = False
        self.step = 0
        self.motion = QtCore.QTimer(self)
        self.motion.setInterval(180)
        self.motion.timeout.connect(self.advance)
        self.setAccessibleName("操作正在进行")

    def set_active(self, active):
        self.requested = bool(active)
        self.sync_motion()

    def sync_motion(self):
        active = self.requested and self.isVisible() and not self.window().isMinimized()
        if active and not self.motion.isActive():
            self.motion.start()
        elif not active:
            self.motion.stop()
        self.update()

    def advance(self):
        if not self.isVisible() or self.window().isMinimized():
            self.motion.stop()
            return
        self.step = (self.step + 1) % 3
        self.update()

    def showEvent(self, event):
        self.sync_motion()
        super().showEvent(event)

    def hideEvent(self, event):
        self.motion.stop()
        super().hideEvent(event)

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.setPen(QtCore.Qt.NoPen)
        for index in range(3):
            active = self.requested and index == self.step
            painter.setBrush(QtGui.QColor(COLORS["primary_pink"] if active else COLORS["border_subtle"]))
            painter.drawEllipse(QtCore.QRectF(2 + index * 10, 3, 5, 5))
        painter.end()
