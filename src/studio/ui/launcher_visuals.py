"""Launcher-specific presentation. Static illustration is cached at device resolution."""
from __future__ import annotations

from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets


LAUNCHER_STYLE = """
QWidget#studioLauncher { background: #0C191D; color: #ECEDF7; font-family: 'Microsoft YaHei UI'; font-size: 13px; }
QWidget#studioLauncher QLabel { color: #ECEDF7; background: transparent; }
QWidget#studioLauncher QLabel#brand { font-size: 19px; font-weight: 800; letter-spacing: 1px; }
QWidget#studioLauncher QLabel#heroTitle { font-size: 37px; font-weight: 800; color: #F6F1F1; }
QWidget#studioLauncher QLabel#heroSubtitle { font-size: 14px; color: #D1D7E9; }
QWidget#studioLauncher QLabel#heroCaption { font-size: 21px; font-weight: 700; }
QWidget#studioLauncher QLabel#eyebrow { color: #8DA4B8; font-size: 10px; letter-spacing: 1.5px; }
QWidget#studioLauncher QLabel#heroEyebrow { color: #91D9DC; font-size: 10px; letter-spacing: 1.7px; }
QWidget#studioLauncher QLabel#deckTitle { font-size: 26px; font-weight: 700; }
QWidget#studioLauncher QLabel#sectionTitle { font-size: 15px; font-weight: 700; }
QWidget#studioLauncher QLabel#sectionNumber { color: #8FDEE4; font-size: 11px; font-weight: 700; }
QWidget#studioLauncher QLabel#muted { color: #9AA7C1; font-size: 12px; }
QWidget#studioLauncher QLabel#hint { color: #AEB8CE; font-size: 12px; }
QWidget#studioLauncher QLabel#emptyTitle { font-size: 18px; font-weight: 700; }
QWidget#studioLauncher QLabel#environmentHint { color: #EEAAA4; font-size: 12px; }
QWidget#studioLauncher QFrame#launchDeck { background: #18292E; border: 1px solid #344D55; border-radius: 18px; }
QWidget#studioLauncher QFrame#environment { background: #203238; border: 1px solid #3B535B; border-radius: 11px; }
QWidget#studioLauncher QFrame#emptyWorkspace { background: #233B42; border: 1px solid #4A6870; border-radius: 11px; }
QWidget#studioLauncher QFrame#statusCard { background: #12232A; border: 1px solid #354F59; border-radius: 9px; }
QWidget#studioLauncher QFrame#statusCard[tone="error"] { background: #2B202E; border-color: #865261; }
QWidget#studioLauncher QFrame#statusCard[tone="ready"] { border-color: #456F7E; }
QWidget#studioLauncher QLabel#statusTitle { font-size: 12px; font-weight: 700; }
QWidget#studioLauncher QLabel#statusCode { color: #8FA8C4; font-size: 10px; letter-spacing: 1px; }
QWidget#studioLauncher QLineEdit, QWidget#studioLauncher QComboBox {
 background: #122229; color: #EEF0FB; border: 1px solid #425D65; border-radius: 6px;
 padding: 9px 10px; min-height: 20px; selection-background-color: #445F79;
}
QWidget#studioLauncher QLineEdit:focus, QWidget#studioLauncher QComboBox:focus { border: 1px solid #83D8E0; }
QWidget#studioLauncher QLineEdit:disabled, QWidget#studioLauncher QComboBox:disabled { color: #7F8DA7; border-color: #30394E; }
QWidget#studioLauncher QLineEdit:read-only { color: #9FAFC6; }
QWidget#studioLauncher QComboBox::drop-down { border: none; width: 26px; }
QWidget#studioLauncher QComboBox QAbstractItemView { background: #203A42; color: #ECF1FA; selection-background-color: #41636B; }
QWidget#studioLauncher QListWidget { background: #15272E; border: 1px solid #3A5660; border-radius: 9px; outline: none; color: #EBEDF7; }
QWidget#studioLauncher QListWidget::item { padding: 11px 13px; margin: 3px; border-left: 3px solid transparent; border-radius: 4px; }
QWidget#studioLauncher QListWidget::item:selected { background: #2D474E; border-left-color: #8DDBDE; }
QWidget#studioLauncher QListWidget::item:hover { background: #29434B; }
QWidget#studioLauncher QPushButton, QWidget#studioLauncher QToolButton {
 background: #2B444B; color: #DDE7F7; border: 1px solid #496972; border-radius: 6px; padding: 8px 12px;
}
QWidget#studioLauncher QPushButton:hover, QWidget#studioLauncher QToolButton:hover { background: #38555C; border-color: #8BBACA; }
QWidget#studioLauncher QPushButton:focus, QWidget#studioLauncher QToolButton:focus { border: 1px solid #A2E7EC; }
QWidget#studioLauncher QPushButton:pressed { background: #172B3F; }
QWidget#studioLauncher QPushButton:disabled, QWidget#studioLauncher QToolButton:disabled { color: #74829D; background: #263C43; border-color: #39545D; }
QWidget#studioLauncher QPushButton#quiet, QWidget#studioLauncher QToolButton#settingsToggle { background: transparent; border: 1px solid transparent; color: #A9BBCF; }
QWidget#studioLauncher QPushButton#quiet:hover, QWidget#studioLauncher QToolButton#settingsToggle:hover { background: #29434B; color: #E7EFF9; }
QWidget#studioLauncher QPushButton#copyStatus { background: transparent; border: 0; padding: 3px 10px; color: #A9BBCF; font-size: 11px; }
QWidget#studioLauncher QPushButton#copyStatus:hover { background: #29434B; color: #E7EFF9; }
QWidget#studioLauncher QPushButton#createPrimary { background: #A0C9C7; border-color: #A0C9C7; color: #142631; font-weight: 700; }
QWidget#studioLauncher QPushButton#launchPrimary { background: #A0C9C7; color: #142937; border: 1px solid #B6D8D5; font-size: 17px; font-weight: 700; padding: 15px 22px; border-radius: 10px; }
QWidget#studioLauncher QPushButton#launchPrimary:hover { background: #B6D8D5; }
QWidget#studioLauncher QPushButton#launchPrimary:pressed { background: #70BCC9; }
QWidget#studioLauncher QPushButton#launchPrimary:disabled { background: #304A52; color: #849DB3; border-color: #3D566B; }
QWidget#studioLauncher QPlainTextEdit#statusDetails { border: none; color: #C5D0E4; background: transparent; selection-background-color: #506680; font-size: 12px; }
QWidget#studioLauncher QScrollArea { border: none; background: transparent; }
QWidget#studioLauncher QWidget#deckBody { background: #18292E; }
QWidget#studioLauncher QScrollBar:vertical { background: transparent; width: 7px; }
QWidget#studioLauncher QScrollBar::handle:vertical { background: #4A5D79; min-height: 25px; border-radius: 3px; }
QWidget#studioLauncher QScrollBar::add-line:vertical, QWidget#studioLauncher QScrollBar::sub-line:vertical { height: 0; }
QToolTip { color: #EDF2FB; background: #253249; border: 1px solid #53758E; padding: 6px; }
"""


class StationArtwork(QtWidgets.QWidget):
    """One original local image, composited once per logical size and device ratio."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(250)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.source = QtGui.QPixmap(str(Path(__file__).parent / "assets" / "rain-night-studio.png"))
        self._cache = QtGui.QPixmap()
        self._cache_key = None
        self.setAccessibleName("原创雨夜便利店插画")

    def rebuild_cache(self):
        ratio = self.devicePixelRatioF()
        key = (self.width(), self.height(), ratio)
        if key == self._cache_key:
            return
        self._cache_key = key
        self._cache = QtGui.QPixmap(max(1, round(self.width() * ratio)), max(1, round(self.height() * ratio)))
        self._cache.setDevicePixelRatio(ratio)
        self._cache.fill(QtCore.Qt.transparent)
        painter = QtGui.QPainter(self._cache)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        bounds = QtCore.QRectF(self.rect())
        clip = QtGui.QPainterPath()
        clip.addRoundedRect(bounds, 18, 18)
        painter.setClipPath(clip)
        painter.fillRect(bounds, QtGui.QColor("#16292D"))
        if not self.source.isNull():
            scaled = self.source.scaled(self._cache.size(), QtCore.Qt.KeepAspectRatioByExpanding,
                                        QtCore.Qt.SmoothTransformation)
            source_rect = QtCore.QRectF((scaled.width() - self._cache.width()) / 2,
                                       (scaled.height() - self._cache.height()) / 2,
                                       self._cache.width(), self._cache.height())
            painter.drawPixmap(bounds, scaled, source_rect)
        shade = QtGui.QLinearGradient(0, 0, 0, self.height())
        shade.setColorAt(0, QtGui.QColor(9, 15, 31, 225))
        shade.setColorAt(0.34, QtGui.QColor(11, 16, 32, 20))
        shade.setColorAt(0.66, QtGui.QColor(10, 17, 32, 0))
        shade.setColorAt(1, QtGui.QColor(8, 14, 29, 242))
        painter.fillRect(bounds, shade)
        painter.setClipping(False)
        painter.setPen(QtGui.QPen(QtGui.QColor(131, 160, 186, 70), 1))
        painter.setBrush(QtCore.Qt.NoBrush)
        painter.drawRoundedRect(bounds.adjusted(0.5, 0.5, -0.5, -0.5), 18, 18)
        painter.end()

    def paintEvent(self, event):
        self.rebuild_cache()
        painter = QtGui.QPainter(self)
        painter.drawPixmap(0, 0, self._cache)
        painter.end()


class LaunchActivity(QtWidgets.QWidget):
    """Small activity dots, never a fabricated percent or full-window animation."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(32, 12)
        self.requested = False
        self.step = 0
        self.motion = QtCore.QTimer(self)
        self.motion.setInterval(180)
        self.motion.timeout.connect(self.advance)
        self.setAccessibleName("启动活动指示，不代表完成百分比")

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
            painter.setBrush(QtGui.QColor("#A0C9C7" if self.requested and index == self.step else "#40516D"))
            painter.drawEllipse(QtCore.QRectF(2 + index * 10, 3, 5, 5))
        painter.end()

