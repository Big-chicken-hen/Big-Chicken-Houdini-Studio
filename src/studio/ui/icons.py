"""Only the approved Lucide 0.468.0 SVG subset; no system-icon fallback."""
from __future__ import annotations

from collections import OrderedDict
from functools import lru_cache
from importlib.resources import files
import math
import weakref

from PySide6 import QtCore, QtGui, QtWidgets
from shiboken6 import isValid

try:
    from PySide6.QtSvg import QSvgRenderer
except ImportError:
    QSvgRenderer = None

from .theme import COLORS

APPROVED_ICONS = frozenset({
    "folder-open", "file-plus-2", "ellipsis", "square-pen", "paperclip", "mouse-pointer-2",
    "arrow-up", "square", "x", "chevron-down", "chevron-right", "arrow-left", "arrow-down",
    "search", "settings", "external-link", "check", "triangle-alert", "circle-alert",
    "loader-circle", "refresh-cw", "maximize-2", "copy",
})
RESOURCE_DIRECTORY = "assets/lucide-0.468.0"
_icons = OrderedDict()
_diagnostics = OrderedDict()
_application = None


def _report(code, name, message):
    key = (code, str(name)[:80])
    _diagnostics[key] = {"code": code, "icon": key[1], "message": message}
    if len(_diagnostics) > 64:
        _diagnostics.popitem(last=False)


def icon_diagnostics():
    """Read-only records for existing diagnostics; never create a product alert."""
    return tuple(dict(record) for record in _diagnostics.values())


@lru_cache(maxsize=23)
def _svg(name):
    return files("studio.ui").joinpath(RESOURCE_DIRECTORY, name + ".svg").read_bytes()


def _clear_icons(*_args):
    global _application
    _icons.clear()
    _application = None


def icon(name, size=20, color=None, dpr=1.0):
    """Render one approved source; a null icon means the caller must show text."""
    global _application
    if not isinstance(name, str) or name not in APPROVED_ICONS:
        _report("ICON_NOT_APPROVED", name, "Use text for this action; the icon is not approved")
        return QtGui.QIcon()
    app = QtWidgets.QApplication.instance()
    if app is None or QtCore.QThread.currentThread() != app.thread():
        _report("ICON_GUI_UNAVAILABLE", name, "Render Studio icons on the existing Qt GUI thread")
        return QtGui.QIcon()
    if QSvgRenderer is None:
        _report("ICON_SVG_UNAVAILABLE", name, "QtSvg is unavailable; action text remains available")
        return QtGui.QIcon()
    try:
        size, dpr = int(size), float(dpr)
        tint = QtGui.QColor(color or COLORS["text_primary"])
        if not 1 <= size <= 128 or not math.isfinite(dpr) or not 0 < dpr <= 8 or not tint.isValid():
            raise ValueError()
    except (TypeError, ValueError, OverflowError):
        _report("ICON_ARGUMENT_INVALID", name, "The icon size, color or display scale is invalid")
        return QtGui.QIcon()
    if _application is None or _application() is not app:
        _icons.clear()
        _application = weakref.ref(app)
        app.aboutToQuit.connect(_clear_icons)
    key = (name, size, tint.name(QtGui.QColor.HexArgb), dpr)
    if key in _icons:
        _icons.move_to_end(key)
        return QtGui.QIcon(_icons[key])
    try:
        # The vendored bytes stay untouched. Only the runtime stroke color changes.
        source = _svg(name).replace(b"currentColor", tint.name().encode("ascii"))
    except (OSError, ValueError):
        _report("ICON_RESOURCE_MISSING", name, "The approved SVG resource is missing or unreadable")
        return QtGui.QIcon()
    renderer = QSvgRenderer(QtCore.QByteArray(source))
    renderer.setAnimationEnabled(False)
    if not renderer.isValid():
        _report("ICON_RESOURCE_INVALID", name, "The approved SVG could not be rendered")
        return QtGui.QIcon()
    pixels = max(1, math.ceil(size * dpr))
    pixmap = QtGui.QPixmap(pixels, pixels)
    pixmap.setDevicePixelRatio(dpr)
    pixmap.fill(QtCore.Qt.transparent)
    painter = QtGui.QPainter(pixmap)
    painter.setRenderHint(QtGui.QPainter.Antialiasing)
    painter.setOpacity(tint.alphaF())
    renderer.render(painter, QtCore.QRectF(0, 0, size, size))
    painter.end()
    result = QtGui.QIcon(pixmap)
    _icons[key] = result
    if len(_icons) > 256:
        _icons.popitem(last=False)
    return QtGui.QIcon(result)


class _ButtonIcon(QtCore.QObject):
    def __init__(self, button):
        super().__init__(button)
        self._updating = False
        self._window = None
        button.installEventFilter(self)
        button.objectNameChanged.connect(self.refresh)

    def configure(self, name, text, size, color, icon_only):
        self.name, self.text, self.size, self.color, self.icon_only = name, text, size, color, icon_only
        self.refresh()

    def refresh(self, *_args):
        if self._updating:
            return
        self._updating = True
        try:
            button = self.parent()
            previous = self._window() if self._window else None
            window = button.window()
            if previous is not window:
                if previous is not None and isValid(previous):
                    previous.removeEventFilter(self)
                if window is not button:
                    window.installEventFilter(self)
                self._window = weakref.ref(window)
            role = button.property("studioRole") or button.objectName()
            color = self.color or (COLORS["disabled_text"] if not button.isEnabled() else
                COLORS["on_primary"] if role == "primary" else COLORS["background"] if role == "stop" else
                COLORS["text_secondary"] if role == "quiet" else COLORS["text_primary"])
            result = icon(self.name, self.size, color, button.devicePixelRatioF())
            only = self.icon_only and not result.isNull()
            button.setIcon(result)
            button.setIconSize(QtCore.QSize(self.size, self.size))
            button.setText("" if only else self.text)
            button.setToolTip(self.text)
            button.setAccessibleName(self.text)
            if isinstance(button, QtWidgets.QToolButton):
                button.setToolButtonStyle(QtCore.Qt.ToolButtonIconOnly if only else QtCore.Qt.ToolButtonTextBesideIcon)
            if button.property("studioIconOnly") != only:
                button.setProperty("studioIconOnly", only)
                button.style().unpolish(button)
                button.style().polish(button)
            button.updateGeometry()
        finally:
            self._updating = False

    def eventFilter(self, watched, event):
        kind = event.type()
        if kind in {QtCore.QEvent.DevicePixelRatioChange, QtCore.QEvent.Show, QtCore.QEvent.ParentChange,
                    QtCore.QEvent.EnabledChange, QtCore.QEvent.StyleChange, QtCore.QEvent.PaletteChange}:
            self.refresh()
        elif kind == QtCore.QEvent.DynamicPropertyChange and event.propertyName() == b"studioRole":
            self.refresh()
        return False


def set_button_icon(button, name, *, text=None, size=20, color=None, icon_only=False):
    """Decorate the same button, preserving actions and a readable text fallback."""
    binding = getattr(button, "_studio_icon_binding", None)
    text = text or button.text() or (binding.text if binding else "")
    if not text:
        raise ValueError("Provide action text for the icon's accessible name and missing-resource fallback")
    if binding is None:
        binding = _ButtonIcon(button)
        button._studio_icon_binding = binding
    binding.configure(name, text, size, color, icon_only)


class LoadingIcon(QtWidgets.QLabel):
    """Rotate only loader-circle, while busy, visible and outside a minimized window."""
    def __init__(self, parent=None, size=20, color=None):
        super().__init__(parent)
        self._size, self._color = size, color
        self._busy, self._angle, self._window = False, 0, None
        self._pixmap = QtGui.QPixmap()
        self.setObjectName("loadingIcon")
        self.setAlignment(QtCore.Qt.AlignCenter)
        self.setAccessibleName("正在处理")
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self._advance)
        self._reload()
        self.hide()

    def _reload(self):
        dpr = self.devicePixelRatioF()
        source = icon("loader-circle", self._size, self._color, dpr)
        self._pixmap = source.pixmap(QtCore.QSize(self._size, self._size), dpr)
        fallback = "处理中" if self._pixmap.isNull() else ""
        self.setText(fallback)
        self.setFixedSize(max(self._size, self.fontMetrics().horizontalAdvance(fallback)),
                          max(self._size, self.fontMetrics().height() if fallback else self._size))

    def set_busy(self, busy):
        self._busy = bool(busy)
        if not self._busy:
            self._angle = 0
        self.setVisible(self._busy)
        self._sync()

    def _sync(self):
        window = self.window()
        previous = self._window() if self._window else None
        if previous is not window:
            if previous is not None and isValid(previous):
                previous.removeEventFilter(self)
            if window is not self:
                window.installEventFilter(self)
            self._window = weakref.ref(window)
        running = self._busy and self.isVisible() and not window.isMinimized() and not self._pixmap.isNull()
        if running and not self._timer.isActive():
            self._timer.start()
        elif not running:
            self._timer.stop()
        self.update()

    def _advance(self):
        self._sync()
        if self._timer.isActive():
            self._angle = (self._angle + 20) % 360
            self.update()

    def showEvent(self, event):
        super().showEvent(event)
        self._reload()
        self._sync()

    def hideEvent(self, event):
        self._timer.stop()
        super().hideEvent(event)

    def changeEvent(self, event):
        super().changeEvent(event)
        if hasattr(self, "_timer") and event.type() in {QtCore.QEvent.DevicePixelRatioChange,
                QtCore.QEvent.StyleChange, QtCore.QEvent.FontChange, QtCore.QEvent.ParentChange}:
            self._reload()
            self._sync()

    def eventFilter(self, watched, event):
        if event.type() == QtCore.QEvent.DevicePixelRatioChange:
            self._reload()
        if event.type() in {QtCore.QEvent.WindowStateChange, QtCore.QEvent.Hide, QtCore.QEvent.Show,
                            QtCore.QEvent.DevicePixelRatioChange}:
            self._sync()
        return False

    def paintEvent(self, event):
        if self._pixmap.isNull():
            return super().paintEvent(event)
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.SmoothPixmapTransform)
        painter.translate(self.width() / 2, self.height() / 2)
        painter.rotate(self._angle)
        painter.drawPixmap(QtCore.QPointF(-self._size / 2, -self._size / 2), self._pixmap)
        painter.end()
