"""Five fixed native nodes; selection geometry only, never services or admission."""
from __future__ import annotations

from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from .shared import label
from .launcher_palette import ARTWORK, BACKGROUND, launcher_stylesheet

_FONT = None


def hero_font(compact=False):
    global _FONT
    if _FONT is None:
        source = Path(__file__).parent / 'assets/changa-one/ChangaOne-Italic.ttf'
        handle = QtGui.QFontDatabase.addApplicationFont(str(source))
        families = QtGui.QFontDatabase.applicationFontFamilies(handle) if handle >= 0 else []
        _FONT = (handle, families[0] if families else '')
    font = QtGui.QFont(_FONT[1]) if _FONT[1] else QtGui.QFont()
    font.setPointSizeF(35 if compact else 44)
    if _FONT[1]:
        font.setStyleName('Italic')
        font.setItalic(True)
    font.setKerning(True)
    return font


def font_diagnostics():
    return {'loaded': bool(_FONT and _FONT[0] >= 0), 'family': _FONT[1] if _FONT else '', 'style': 'Italic'}


FLOW_STYLE = launcher_stylesheet('studioLauncher') + '''
QWidget#studioLauncher { background: #EEF6FC; color: #203B5D; }
QWidget#studioLauncher QWidget#secondaryViewport, QWidget#studioLauncher QWidget#secondaryBody {
    background: #EEF6FC;
}
QWidget#studioLauncher QWidget#flowPage, QWidget#studioLauncher QWidget#flowCanvas,
QWidget#studioLauncher QScrollArea#flowScroll, QWidget#studioLauncher QWidget#flowViewport {
    background: transparent; border: none;
}
QWidget#studioLauncher QLabel#toolbarBrand { font-size: 10pt; font-weight: 500; color: #46607A; }
QWidget#studioLauncher QPushButton[studioRole="toolbar"] {
    background: transparent; border: 1px solid transparent; border-radius: 6px;
    color: #46607A; padding: 5px 10px; min-width: 0px;
}
QWidget#studioLauncher QPushButton[studioRole="toolbar"]:hover { background: #DEEDF8; }
QWidget#studioLauncher QPushButton[studioRole="toolbar"]:focus { border-color: #416EB2; }
QWidget#studioLauncher QFrame#flowNode { background: transparent; border: none; }
QWidget#studioLauncher QLabel#flowCategory { font-size: 9pt; color: #60768C; letter-spacing: 1px; }
QWidget#studioLauncher QLabel#flowTitle { font-size: 13pt; font-weight: 600; color: #203B5D; }
QWidget#studioLauncher QLabel#flowSecondary { font-size: 10pt; color: #46607A; }
QWidget#studioLauncher QLabel#flowHero { color: #416EB2; background: transparent;
    font-family: "Changa One"; font-style: italic; font-size: 44pt; font-weight: 400; }
QWidget#studioLauncher QLabel#flowHero[compact="true"] { font-size: 35pt; }
QWidget#studioLauncher QPushButton#flowNodeAction { background: transparent; border: 1px solid transparent;
    color: #203B5D; font-size: 13pt; text-align: left; padding: 0px; }
QWidget#studioLauncher QPushButton#flowNodeAction:hover { color: #416EB2; }
QWidget#studioLauncher QPushButton#flowNodeAction:focus { border-color: #416EB2; }
QWidget#studioLauncher QLabel#creatorCredit { font-size: 9pt; color: #60768C; }
QWidget#studioLauncher QListWidget#recentList { background: transparent; border: none; outline: none; }
QWidget#studioLauncher QListWidget#recentList::item { background: transparent; border: none; }
QWidget#studioLauncher QFrame#recentRow { background: transparent; border: 1px solid transparent; border-radius: 5px; }
QWidget#studioLauncher QFrame#recentRow:hover { background: #DEEDF8; }
QWidget#studioLauncher QFrame#recentRow[selected="true"] { background: #D5E9FA; }
QWidget#studioLauncher QFrame#recentRow[focused="true"] { border-color: #416EB2; }
QWidget#studioLauncher QLabel#recentName { font-size: 10.5pt; font-weight: 500; }
QWidget#studioLauncher QFrame#recentRow QLabel#muted { font-size: 9.5pt; }
QWidget#studioLauncher QFrame#recentPopup { background: #F8FCFF; border: 1px solid #C5D8E8; border-radius: 8px; }
'''


class FlowNode(QtWidgets.QFrame):
    chosen = QtCore.Signal()
    geometry_changed = QtCore.Signal()

    def __init__(self, category, parent=None, *, selectable=False):
        super().__init__(parent)
        self.setObjectName('flowNode')
        self.setAccessibleName(category)
        self.selectable, self.selected, self.hovered = selectable, False, False
        self._selection, self._hover = 0.0, 0.0
        self._selection_animation = QtCore.QPropertyAnimation(self, b'selectionAmount', self)
        self._hover_animation = QtCore.QPropertyAnimation(self, b'hoverAmount', self)
        for animation in (self._selection_animation, self._hover_animation):
            animation.setDuration(140)
        self.setFocusPolicy(QtCore.Qt.StrongFocus if selectable else QtCore.Qt.NoFocus)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        self.content = QtWidgets.QVBoxLayout(self)
        self.content.setContentsMargins(18, 16, 18, 16)
        self.content.setSpacing(8)
        self.content.addWidget(label(category, 'flowCategory'))

    def _set_selection(self, value):
        self._selection = value
        self.update()

    def _set_hover(self, value):
        self._hover = value
        self.update()

    selectionAmount = QtCore.Property(float, lambda self: self._selection, _set_selection)
    hoverAmount = QtCore.Property(float, lambda self: self._hover, _set_hover)

    def transition(self, animation, value):
        animation.stop()
        if self.isVisible() and not self.window().isMinimized():
            animation.setStartValue(self.property(bytes(animation.propertyName()).decode()))
            animation.setEndValue(value)
            animation.start()
        else:
            self.setProperty(bytes(animation.propertyName()).decode(), value)

    def set_selected(self, selected):
        if self.selected != selected:
            self.selected = selected
            self.transition(self._selection_animation, float(selected))

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        rect = QtCore.QRectF(self.rect()).adjusted(1, 1, -1, -1)
        painter.setPen(QtGui.QPen(QtGui.QColor('#B7CFE3'), 1))
        painter.setBrush(QtGui.QColor(248, 252, 255, 222))
        painter.drawRoundedRect(rect, 10, 10)
        for amount, color in ((self._hover, '#EFF8FF'), (self._selection, '#DAEDFC')):
            if amount:
                painter.setOpacity(amount)
                painter.setPen(QtCore.Qt.NoPen)
                painter.setBrush(QtGui.QColor(color))
                painter.drawRoundedRect(rect, 10, 10)
        painter.setOpacity(1)
        if self._selection:
            border = QtGui.QColor('#416EB2')
            border.setAlphaF(0.65 * self._selection)
            painter.setPen(QtGui.QPen(border, 1))
            painter.setBrush(QtCore.Qt.NoBrush)
            painter.drawRoundedRect(rect, 10, 10)
        if self.hasFocus():
            painter.setPen(QtGui.QPen(QtGui.QColor('#416EB2'), 2))
            painter.setBrush(QtCore.Qt.NoBrush)
            painter.drawRoundedRect(rect.adjusted(2, 2, -2, -2), 8, 8)

    def enterEvent(self, event):
        if self.selectable and self.isEnabled():
            self.transition(self._hover_animation, 1.0)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.transition(self._hover_animation, 0.0)
        super().leaveEvent(event)

    def focusInEvent(self, event):
        self.update()
        super().focusInEvent(event)

    def focusOutEvent(self, event):
        self.update()
        super().focusOutEvent(event)

    def mouseReleaseEvent(self, event):
        if self.selectable and self.isEnabled() and event.button() == QtCore.Qt.LeftButton and self.rect().contains(event.position().toPoint()):
            self.chosen.emit()
            self.setFocus(QtCore.Qt.MouseFocusReason)
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if self.selectable and event.key() in {QtCore.Qt.Key_Space, QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter}:
            self.chosen.emit()
            event.accept()
        else:
            super().keyPressEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.geometry_changed.emit()

    def moveEvent(self, event):
        super().moveEvent(event)
        self.geometry_changed.emit()

    def hideEvent(self, event):
        self._selection_animation.stop()
        self._hover_animation.stop()
        self._selection, self._hover = float(self.selected), 0.0
        super().hideEvent(event)


class LauncherFlow(QtWidgets.QWidget):
    """Fixed topology; native layouts place nodes before anchors are measured."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('flowCanvas')
        self.compact = None
        self.branch, self.path_ready = None, False
        self.paths, self.anchors = {}, {}
        self.grid = QtWidgets.QGridLayout(self)
        self.grid.setContentsMargins(24, 8, 24, 16)
        self.grid.setHorizontalSpacing(0)
        self.grid.setVerticalSpacing(12)
        self.project_label = label('PROJECT', 'flowCategory')
        self.nodes = {name: FlowNode(name.upper(), self, selectable=name == 'empty')
                      for name in ('account', 'empty', 'open', 'recent', 'launch')}
        for node in self.nodes.values():
            node.geometry_changed.connect(self.rebuild_paths)
        self.set_compact(False)

    def set_compact(self, compact):
        if self.compact == compact:
            return
        self.compact = compact
        while self.grid.count():
            self.grid.takeAt(0)
        for column in range(5):
            self.grid.setColumnMinimumWidth(column, 0)
            self.grid.setColumnStretch(column, 0)
        for node in self.nodes.values():
            node.setMaximumWidth(16777215)
        for name in ('account', 'launch'):
            self.nodes[name].setMinimumHeight(220 if compact else 300)
        if compact:
            self.grid.setColumnMinimumWidth(0, 28)
            self.grid.setColumnMinimumWidth(2, 28)
            self.grid.setColumnStretch(1, 1)
            self.grid.addWidget(self.nodes['account'], 0, 1)
            self.grid.addWidget(self.project_label, 1, 1)
            for row, name in enumerate(('empty', 'open', 'recent', 'launch'), 2):
                self.grid.addWidget(self.nodes[name], row, 1)
        else:
            for column, width in ((0, 220), (1, 64), (2, 264), (3, 64), (4, 280)):
                self.grid.setColumnMinimumWidth(column, width)
            self.grid.setColumnStretch(2, 1)
            self.grid.addWidget(self.project_label, 0, 2)
            for row, name in enumerate(('empty', 'open', 'recent'), 1):
                self.grid.addWidget(self.nodes[name], row, 2)
            self.grid.addWidget(self.nodes['account'], 1, 0, 3, 1, QtCore.Qt.AlignVCenter)
            self.grid.addWidget(self.nodes['launch'], 1, 4, 3, 1, QtCore.Qt.AlignVCenter)
        self.grid.invalidate()
        self.updateGeometry()
        self.rebuild_paths()

    def set_selection(self, branch, ready):
        if (self.branch, self.path_ready) == (branch, ready):
            return
        self.branch, self.path_ready = branch, ready
        for name in ('empty', 'open', 'recent'):
            self.nodes[name].set_selected(name == branch)
        self.update()

    def anchor(self, name, right):
        rect = self.nodes[name].geometry()
        return QtCore.QPointF(rect.right() if right else rect.left(), rect.center().y())

    def rebuild_paths(self):
        if not hasattr(self, 'nodes'):
            return
        start = self.anchor('account', not self.compact)
        end = self.anchor('launch', bool(self.compact))
        self.paths, self.anchors = {}, {'account': start, 'launch': end}
        for name in ('empty', 'open', 'recent'):
            incoming, outgoing = self.anchor(name, False), self.anchor(name, True)
            self.anchors[name] = (incoming, outgoing)
            first, second = QtGui.QPainterPath(start), QtGui.QPainterPath(outgoing)
            if self.compact:
                first.cubicTo(start + QtCore.QPointF(-38, 0), incoming + QtCore.QPointF(-38, 0), incoming)
                second.cubicTo(outgoing + QtCore.QPointF(38, 0), end + QtCore.QPointF(38, 0), end)
            else:
                x1, x2 = (start.x() + incoming.x()) / 2, (outgoing.x() + end.x()) / 2
                first.cubicTo(QtCore.QPointF(x1, start.y()), QtCore.QPointF(x1, incoming.y()), incoming)
                second.cubicTo(QtCore.QPointF(x2, outgoing.y()), QtCore.QPointF(x2, end.y()), end)
            self.paths[name] = (first, second)
        self.update()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        for name in [key for key in self.paths if key != self.branch] + ([self.branch] if self.branch in self.paths else []):
            selected = name == self.branch
            color = QtGui.QColor('#416EB2' if selected else '#5B7D9D')
            color.setAlphaF((0.9 if self.path_ready else 0.5) if selected else 0.65)
            painter.setPen(QtGui.QPen(color, 1.5 if selected else 1, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap))
            painter.setBrush(QtCore.Qt.NoBrush)
            for path in self.paths[name]:
                painter.drawPath(path)
            painter.setBrush(QtGui.QColor('#EEF6FC'))
            for point in (self.anchors['account'], *self.anchors[name], self.anchors['launch']):
                painter.drawEllipse(point, 3, 3)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.rebuild_paths()


class FlowPage(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('flowPage')
        self._background = QtGui.QPixmap(str(ARTWORK / 'background.png'))
        self._background_scaled = QtGui.QPixmap()
        self._background_size = QtCore.QSize()
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.hero = label('Chicken', 'flowHero')
        self.hero.setAlignment(QtCore.Qt.AlignCenter)
        self.hero.setMargin(8)
        self.hero.setFont(hero_font())
        layout.addWidget(self.hero)
        credit = label('bilibili  Chicken-houdini', 'creatorCredit')
        credit.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(credit)
        layout.addSpacing(12)
        self.flow = LauncherFlow()
        self.flow.setMaximumWidth(1000)
        layout.addWidget(self.flow, 0, QtCore.Qt.AlignHCenter)
        layout.addStretch(1)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        compact = self.window().width() < 980
        if self.flow.compact != compact:
            self.hero.setFont(hero_font(compact))
            self.flow.set_compact(compact)
        if self.hero.property('compact') != compact:
            self.hero.setProperty('compact', compact)
            self.hero.style().unpolish(self.hero)
            self.hero.style().polish(self.hero)
        self.flow.setFixedWidth(min(1000, self.width()))

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.fillRect(self.rect(), QtGui.QColor(BACKGROUND))
        if self._background.isNull():
            return
        # Decode once and rescale only with the viewport; polling never reloads art.
        height = min(self.height(), max(680, self.window().height() - 64))
        size = QtCore.QSize(self.width(), height)
        if size != self._background_size:
            self._background_scaled = self._background.scaled(
                size, QtCore.Qt.KeepAspectRatioByExpanding, QtCore.Qt.SmoothTransformation)
            self._background_size = size
        painter.setOpacity(0.58)
        painter.drawPixmap((self.width() - self._background_scaled.width()) // 2,
                           (height - self._background_scaled.height()) // 2, self._background_scaled)
        painter.setOpacity(1)
        heading_veil = QtGui.QLinearGradient(0, 0, 0, 190)
        heading_veil.setColorAt(0, QtGui.QColor(238, 246, 252, 165))
        heading_veil.setColorAt(1, QtGui.QColor(238, 246, 252, 0))
        painter.fillRect(QtCore.QRect(0, 0, self.width(), 190), heading_veil)
        fade = QtGui.QLinearGradient(0, height * 0.60, 0, height)
        fade.setColorAt(0, QtGui.QColor(238, 246, 252, 0))
        fade.setColorAt(1, QtGui.QColor(BACKGROUND))
        painter.fillRect(self.rect(), fade)
