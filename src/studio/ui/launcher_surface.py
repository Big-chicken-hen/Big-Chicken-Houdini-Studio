"""One cached backdrop and native caption styling for the Launcher window."""
from __future__ import annotations

import sys

from PySide6 import QtCore, QtGui, QtWidgets

from .launcher_palette import ARTWORK, BACKGROUND
from .launcher_windows import clear_launcher_taskbar, set_launcher_taskbar


def white_native_caption(window):
    """Set this HWND only; Windows retains caption buttons and window behavior."""
    if sys.platform != 'win32' or QtGui.QGuiApplication.platformName() != 'windows':
        return False
    import ctypes
    from ctypes import wintypes
    try:
        setter = ctypes.WinDLL('dwmapi').DwmSetWindowAttribute
        setter.argtypes = (wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD)
        setter.restype = ctypes.c_long
        hwnd = int(window.winId())
        # DWMWA_USE_IMMERSIVE_DARK_MODE, CAPTION_COLOR, TEXT_COLOR (Win11).
        values = ((20, wintypes.BOOL(0)), (35, wintypes.DWORD(0xFFFFFF)),
                  (36, wintypes.DWORD(0x5D3B20)))
        return all(setter(hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value)) >= 0
                   for attribute, value in values)
    except (AttributeError, OSError):
        return False


class LauncherSurface(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._background = QtGui.QPixmap(str(ARTWORK / 'background.png'))
        self._background_scaled = QtGui.QPixmap()
        self._background_key = None
        self._taskbar_bound = False
        palette = self.palette()
        palette.setColor(QtGui.QPalette.Window, QtGui.QColor(BACKGROUND))
        self.setPalette(palette)

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.fillRect(self.rect(), QtGui.QColor(BACKGROUND))
        area = self.stack.geometry() if hasattr(self, 'stack') else self.rect()
        # The toolbar joins the native white caption, outside the illustration.
        painter.fillRect(QtCore.QRect(0, 0, self.width(), area.top()), QtCore.Qt.white)
        if self._background.isNull() or area.isEmpty():
            return
        dpr = self.devicePixelRatioF()
        key = (area.width(), area.height(), dpr)
        if key != self._background_key:
            self._background_scaled = self._background.scaled(
                QtCore.QSize(round(area.width() * dpr), round(area.height() * dpr)),
                QtCore.Qt.KeepAspectRatioByExpanding, QtCore.Qt.SmoothTransformation)
            self._background_scaled.setDevicePixelRatio(dpr)
            self._background_key = key
        painter.setClipRect(area)
        painter.translate(area.topLeft())
        size = self._background_scaled.deviceIndependentSize()
        painter.setOpacity(0.58)
        painter.drawPixmap(QtCore.QPointF((area.width() - size.width()) / 2,
                                         (area.height() - size.height()) / 2), self._background_scaled)
        painter.setOpacity(1)
        rect = QtCore.QRect(0, 0, area.width(), area.height())
        heading = QtGui.QLinearGradient(0, 0, 0, 190)
        heading.setColorAt(0, QtGui.QColor(238, 246, 252, 165))
        heading.setColorAt(1, QtGui.QColor(238, 246, 252, 0))
        painter.fillRect(QtCore.QRect(0, 0, area.width(), 190), heading)
        fade = QtGui.QLinearGradient(0, area.height() * 0.60, 0, area.height())
        fade.setColorAt(0, QtGui.QColor(238, 246, 252, 0))
        fade.setColorAt(1, QtGui.QColor(BACKGROUND))
        painter.fillRect(rect, fade)
        if getattr(self, '_secondary', None):
            # Existing secondary-page text keeps its position and a quiet ground.
            readable = QtGui.QLinearGradient(0, 0, area.width() * 0.70, 0)
            readable.setColorAt(0, QtGui.QColor(248, 252, 255, 200))
            readable.setColorAt(1, QtGui.QColor(248, 252, 255, 0))
            painter.fillRect(rect, readable)

    def showEvent(self, event):
        super().showEvent(event)
        white_native_caption(self)
        if not self._taskbar_bound and hasattr(self, 'paths'):
            self._taskbar_bound = set_launcher_taskbar(self, self.paths.root)

    def closeEvent(self, event):
        super().closeEvent(event)
        if event.isAccepted() and self._taskbar_bound:
            clear_launcher_taskbar(self)
            self._taskbar_bound = False

    def changeEvent(self, event):
        super().changeEvent(event)
        if self.isVisible() and event.type() in (QtCore.QEvent.ActivationChange,
                                                QtCore.QEvent.PaletteChange):
            white_native_caption(self)
