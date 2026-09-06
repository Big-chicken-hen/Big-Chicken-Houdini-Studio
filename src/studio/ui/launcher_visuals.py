"""Small native presentation widgets for the staged Launcher."""
from __future__ import annotations

from pathlib import Path

from PySide6 import QtCore, QtWidgets

from .shared import button, label
from .theme import studio_stylesheet

LAUNCHER_STYLE = studio_stylesheet("studioLauncher")


class ElidedLabel(QtWidgets.QLabel):
    def __init__(self, text, *, middle=False, parent=None):
        super().__init__(parent)
        self.full_text = str(text)
        self.elide = QtCore.Qt.ElideMiddle if middle else QtCore.Qt.ElideRight
        self.setTextFormat(QtCore.Qt.PlainText)
        self.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Preferred)
        self.setToolTip(self.full_text)
        self.setText(self.full_text)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.setText(self.fontMetrics().elidedText(self.full_text, self.elide, self.width()))

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QtCore.QEvent.FontChange and hasattr(self, "full_text"):
            self.setText(self.fontMetrics().elidedText(self.full_text, self.elide, self.width()))


class RecentRow(QtWidgets.QFrame):
    selected = QtCore.Signal(object)
    activated = QtCore.Signal(object)
    menu_requested = QtCore.Signal(object, object)

    def __init__(self, record, parent=None):
        super().__init__(parent)
        self.record = record
        self._hovered, self._selected = False, False
        self.setObjectName("recentRow")
        self.setProperty("studioRole", "recentRow")
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.setFixedHeight(64)
        self.setAccessibleName(record["name"] + ("，找不到文件" if record.get("missing") else ""))
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 8, 6)
        layout.setSpacing(12)
        text = QtWidgets.QVBoxLayout()
        text.setSpacing(4)
        first = QtWidgets.QHBoxLayout()
        self.name = ElidedLabel(record["name"] + (" · 找不到文件" if record.get("missing") else ""))
        self.name.setObjectName("recentName")
        first.addWidget(self.name, 1)
        stamp = record.get("last_used_at")
        moment = QtCore.QDateTime.fromSecsSinceEpoch(int(stamp)) if stamp else None
        self.time = label(moment.toString("MM-dd") if moment else "", "muted")
        first.addWidget(self.time)
        text.addLayout(first)
        self.directory = ElidedLabel(record["directory"], middle=True)
        self.directory.setObjectName("muted")
        text.addWidget(self.directory)
        layout.addLayout(text, 1)
        controls = QtWidgets.QWidget()
        controls.setFixedWidth(116)
        actions = QtWidgets.QHBoxLayout(controls)
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(4)
        self.open_button = button("打开", lambda: self.activated.emit(self.record), "quiet")
        self.open_button.setAccessibleName("打开 " + record["name"])
        self.open_button.setEnabled(not record.get("missing"))
        self.more_button = button("更多", self.show_menu, "quiet")
        self.more_button.setMinimumWidth(40)
        self.more_button.setFixedHeight(32)
        self.more_button.setAccessibleName(record["name"] + " 的操作")
        actions.addWidget(self.open_button, 1)
        actions.addWidget(self.more_button)
        layout.addWidget(controls)
        exact = moment.toString("yyyy-MM-dd HH:mm:ss") if moment else "没有最近使用时间"
        self.setToolTip(str(Path(record["path"])) + "\n" + exact)
        self.name.setToolTip(self.toolTip())
        self.directory.setToolTip(self.toolTip())
        self.time.setToolTip(exact)
        QtWidgets.QApplication.instance().focusChanged.connect(self.update_actions)
        self.update_actions()

    def set_selected(self, value):
        self._selected = value
        self.setProperty("selected", value)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update_actions()

    def update_actions(self, *_args):
        focus = QtWidgets.QApplication.focusWidget()
        focused = focus is self or focus is not None and self.isAncestorOf(focus)
        if self.property("focused") != focused:
            self.setProperty("focused", focused)
            self.style().unpolish(self)
            self.style().polish(self)
        visible = self._hovered or self._selected or focused
        self.open_button.setVisible(visible)
        self.more_button.setVisible(visible)

    def show_menu(self):
        self.menu_requested.emit(self.record, self.more_button.mapToGlobal(self.more_button.rect().bottomLeft()))

    def enterEvent(self, event):
        self._hovered = True
        self.update_actions()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self.update_actions()
        super().leaveEvent(event)

    def focusInEvent(self, event):
        self.selected.emit(self.record)
        self.update_actions()
        super().focusInEvent(event)

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.selected.emit(self.record)
            self.setFocus(QtCore.Qt.MouseFocusReason)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.activated.emit(self.record)
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event):
        if event.key() in {QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter}:
            self.activated.emit(self.record)
            event.accept()
        elif event.key() == QtCore.Qt.Key_Menu or (event.key() == QtCore.Qt.Key_F10 and
                                                  event.modifiers() & QtCore.Qt.ShiftModifier):
            self.show_menu()
            event.accept()
        else:
            super().keyPressEvent(event)
