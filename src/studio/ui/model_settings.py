"""Ephemeral projection of native settings and the user's next-turn override."""
from PySide6 import QtCore, QtGui, QtWidgets

from .icons import icon, set_button_icon
from .shared import label
from .theme import COLORS, apply_theme


class ChoiceBox(QtWidgets.QComboBox):
    """Keep the native combo interaction, drawing only the approved dropdown SVG."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("QComboBox::down-arrow { image: none; }")

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QtGui.QPainter(self)
        color = COLORS["text_secondary"] if self.isEnabled() else COLORS["disabled_text"]
        approved = icon("chevron-down", size=16, color=color, dpr=self.devicePixelRatioF())
        approved.paint(painter, QtCore.QRect(self.width() - 22, (self.height() - 16) // 2, 16, 16))
        painter.end()


class ModelPopup(QtWidgets.QFrame):
    def resizeEvent(self, event):
        super().resizeEvent(event)
        owner = self.parentWidget()
        if getattr(owner, "popup", None) is self:
            owner.position_popup()

    def keyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key_Escape:
            self.hide()
            event.accept()
        else:
            super().keyPressEvent(event)


class ModelSettings(QtWidgets.QWidget):
    changed = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.thread_id = None
        self.settings_revision = None
        self.account_revision = None
        self.catalog_revision = -1
        self.selection_revision = 0
        self.catalog = {}
        self.catalog_loaded = False
        self.next_model = None
        self.next_effort = None
        self.user_override = False
        self.native_source = "unknown"
        self._adjustment = ""
        self._constraint = ""
        self._base_note = ""
        self._interactive = False
        self._active = False
        self._current_caption = ""
        self._caption = ""
        self.current_turn_id = None
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.setMinimumWidth(0)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.button = QtWidgets.QToolButton()
        self.button.setObjectName("modelEntry")
        self.button.setProperty("studioRole", "quiet")
        self.button.setMinimumHeight(32)
        self.button.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed)
        self.button.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self.button.setLayoutDirection(QtCore.Qt.RightToLeft)
        self.button.clicked.connect(self.open_popup)
        set_button_icon(self.button, "chevron-down", text="选择模型与推理档位", size=16)
        outer.addWidget(self.button)
        self.popup = ModelPopup(self, QtCore.Qt.Popup)
        self.popup.setObjectName("studioModelPopup")
        apply_theme(self.popup, popup=True)
        body = QtWidgets.QVBoxLayout(self.popup)
        body.setContentsMargins(12, 12, 12, 12)
        body.setSpacing(8)
        body.addWidget(label("下一轮模型", "sectionTitle"))
        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText("搜索模型")
        self.search.setAccessibleName("搜索可用模型")
        self.search.textChanged.connect(self.filter_models)
        self.search.hide()
        body.addWidget(self.search)
        self.models = QtWidgets.QListWidget()
        self.models.setAccessibleName("下一轮模型")
        self.models.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.models.setTextElideMode(QtCore.Qt.ElideRight)
        body.addWidget(self.models, 1)
        effort_row = QtWidgets.QHBoxLayout()
        effort_row.addWidget(label("Effort"))
        self.efforts = ChoiceBox()
        self.efforts.setAccessibleName("下一轮推理档位")
        self.efforts.setMinimumWidth(0)
        self.efforts.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.efforts.setMinimumContentsLength(6)
        effort_row.addWidget(self.efforts, 1)
        body.addLayout(effort_row)
        self.note = label("下一轮选择 · 等待会话设置", "muted", True)
        body.addWidget(self.note)
        body.addWidget(label("选择对下一轮生效", "muted"))
        self.current = label("", "muted", True)
        self.current.hide()
        body.addWidget(self.current)
        self.models.currentRowChanged.connect(self.model_changed)
        self.efforts.currentIndexChanged.connect(self.effort_changed)
        self.render_button()

    def set_thread(self, thread_id):
        if thread_id == self.thread_id:
            return
        self.popup.hide()
        self.search.clear()
        self.thread_id = thread_id
        self.settings_revision = None
        self.next_model = self.next_effort = None
        self.user_override = False
        self.native_source = "unknown"
        self.selection_revision += 1
        self._adjustment = ""
        self.current.hide()
        self.render()

    def set_account_revision(self, revision):
        if revision == self.account_revision:
            return
        self.popup.hide()
        self.account_revision = revision
        self.catalog_revision = -1
        self.catalog_loaded = False
        self.catalog = {}
        self.render()

    def reset_connection(self):
        self.popup.hide()
        self.settings_revision = None
        self.native_source = "unknown"
        self.current.hide()
        self.render()

    def apply_native(self, settings, *, restore=False):
        if not isinstance(settings, dict) or settings.get("thread_id") != self.thread_id:
            return False
        revision = settings.get("revision")
        if type(revision) is not int or (self.settings_revision is not None and revision < self.settings_revision):
            return False
        if revision == self.settings_revision and not restore:
            return True
        self.settings_revision = revision
        self.native_source = settings.get("source", "unknown")
        if restore or not self.user_override:
            self.next_model = settings.get("model")
            self.next_effort = settings.get("effort")
            self.user_override = False
            self._adjustment = ""
        self.render()
        return True

    def apply_catalog(self, value):
        if value.get("account_revision") != self.account_revision:
            return False
        revision = value.get("catalog_revision")
        if type(revision) is not int or revision < self.catalog_revision or value.get("nextCursor"):
            return False
        catalog = {item["model"]: item for item in value.get("data", [])
                   if isinstance(item, dict) and isinstance(item.get("model"), str)
                   and item["model"] and not item.get("hidden")}
        if self.catalog_loaded and catalog == self.catalog:
            self.catalog_revision = revision
            return True
        self.catalog_revision = revision
        self.catalog = catalog
        self.catalog_loaded = True
        # Read the current intent, never the selection captured before this request.
        self.render()
        return True

    @staticmethod
    def supported_efforts(model):
        return [item["reasoningEffort"] for item in model.get("supportedReasoningEfforts", [])
                if isinstance(item, dict) and isinstance(item.get("reasoningEffort"), str)
                and item["reasoningEffort"]]

    def render(self):
        self.models.blockSignals(True)
        self.efforts.blockSignals(True)
        try:
            rows = list(self.catalog.items())
            if self.next_model and self.next_model not in self.catalog:
                suffix = "（不可用）" if self.catalog_loaded else "（等待目录）"
                rows.append((self.next_model, {"model": self.next_model, "displayName": self.next_model + suffix,
                                              "unavailable": True}))
            existing = [self.models.item(i).data(QtCore.Qt.UserRole) for i in range(self.models.count())]
            if existing != [model for _slug, model in rows]:
                self.models.clear()
                for slug, model in rows:
                    item = QtWidgets.QListWidgetItem(model.get("displayName") or slug)
                    item.setData(QtCore.Qt.UserRole, model)
                    item.setToolTip(str(model.get("description") or slug))
                    item.setSizeHint(QtCore.QSize(0, 36))
                    if model.get("unavailable"):
                        item.setFlags(item.flags() & ~QtCore.Qt.ItemIsEnabled)
                    self.models.addItem(item)
            self.models.setCurrentRow(next((i for i, (slug, _model) in enumerate(rows) if slug == self.next_model), -1))
            self.models.setMinimumHeight(72)
            self.models.setMaximumHeight(min(216, max(72, len(rows) * 36)))
            self.search.setVisible(len(self.catalog) > 8)
            self.filter_models()
            self.efforts.clear()
            model = self.catalog.get(self.next_model)
            if model:
                efforts = self.supported_efforts(model)
                if self.next_effort is not None and self.next_effort not in efforts:
                    default = model.get("defaultReasoningEffort")
                    self.next_effort = default if default in efforts else None
                    self._adjustment = "原档位不适用于此模型，已采用其原生默认值。"
                if self.next_effort is None:
                    self.efforts.addItem("默认", None)
                for effort in efforts:
                    self.efforts.addItem(effort, effort)
                self.efforts.setCurrentIndex(self.efforts.findData(self.next_effort))
            elif self.next_effort is not None:
                self.efforts.addItem(str(self.next_effort), self.next_effort)
            if self.catalog_loaded and self.next_model and not model:
                note = "此对话的模型不在可用列表中，请选择下一轮模型。"
            elif not self.thread_id or self.settings_revision is None:
                note = "下一轮选择 · 等待原生会话设置"
            elif not self.catalog_loaded:
                note = "下一轮选择 · 正在确认可用模型"
            elif not self.next_model:
                note = "请明确选择下一轮模型。"
            else:
                note = self._adjustment or "下一轮选择 · 不改变正在执行的工作"
            self._base_note = note
            self.note.setText(self._constraint or note)
        finally:
            self.models.blockSignals(False)
            self.efforts.blockSignals(False)
        self.render_button()
        self.changed.emit()

    def model_changed(self, _index=None):
        if not self._interactive:
            return
        item = self.models.currentItem()
        item = item.data(QtCore.Qt.UserRole) if item else {}
        slug = item.get("model")
        if slug not in self.catalog:
            return
        self.next_model = slug
        self.user_override = True
        self.selection_revision += 1
        self._adjustment = ""
        if self.next_effort is None:
            self.next_effort = self.catalog[slug].get("defaultReasoningEffort")
        self.render()

    def effort_changed(self, _index=None):
        if not self._interactive:
            return
        self.next_effort = self.efforts.currentData()
        self.user_override = True
        self.selection_revision += 1
        self._adjustment = ""
        self._base_note = "下一轮选择 · 不改变正在执行的工作"
        self.note.setText(self._constraint or self._base_note)
        self.render_button()
        self.changed.emit()

    def request_settings(self):
        if (not self.thread_id or type(self.settings_revision) is not int
                or not self.catalog_loaded or self.next_model not in self.catalog):
            return None
        model = self.catalog[self.next_model]
        if self.next_effort is not None and self.next_effort not in self.supported_efforts(model):
            return None
        value = {"expected_thread_id": self.thread_id, "settings_revision": self.settings_revision,
                 "model": self.next_model}
        if self.next_effort is not None:
            value["effort"] = self.next_effort
        return value

    def set_constraint(self, message):
        self._constraint = message
        self.note.setText(message or self._base_note)
        self.render_button()

    def apply_turn(self, settings, *, active, turn_id=None):
        self._active = active
        if not active:
            self.current.hide()
            self._current_caption = ""
            self.render_button()
            return
        if self.current_turn_id != turn_id:
            self.current.hide()
            self._current_caption = ""
        if (not isinstance(settings, dict) or settings.get("thread_id") != self.thread_id
                or turn_id is not None and settings.get("turn_id") != turn_id):
            self.render_button()
            return
        requested = str(settings.get("requested_model") or "未指定")
        effort = str(settings.get("requested_effort") or "默认")
        text = "本轮已请求：" + requested + " · " + effort
        if settings.get("confirmation") == "rerouted":
            text += "\n原生重路由：" + str(settings.get("model") or "未确认")
        self.current.setText(text)
        self.current_turn_id = turn_id
        self.current.setToolTip("请求模型：" + requested + "\n" + str(settings.get("reason") or ""))
        self.current.show()
        requested_name = (self.catalog.get(requested) or {}).get("displayName") or requested
        routed = str(settings.get("model") or "未确认")
        routed_name = (self.catalog.get(routed) or {}).get("displayName") or routed
        self._current_caption = ("重路由：" + routed_name + " · 已请求档位 " + effort
                                 if settings.get("confirmation") == "rerouted" else "已请求：" + requested_name + " · " + effort)
        self.render_button()

    def set_interactive(self, enabled):
        self._interactive = bool(enabled)
        self.button.setEnabled(self._interactive)
        self.models.setEnabled(self._interactive)
        self.efforts.setEnabled(self._interactive and self.efforts.count() > 0)
        if not self._interactive:
            self.popup.hide()

    def filter_models(self, _text=None):
        text = self.search.text().casefold() if len(self.catalog) > 8 else ""
        for index in range(self.models.count()):
            item = self.models.item(index)
            model = item.data(QtCore.Qt.UserRole)
            item.setHidden(bool(text and text not in (item.text() + " " + model["model"]).casefold()))

    def render_button(self):
        model = self.catalog.get(self.next_model) or {}
        title = model.get("displayName") or self.next_model or "选择模型"
        if self.catalog_loaded and self.next_model and not model:
            title += "（不可用）"
        choice = title + " · " + str(self.next_effort or "默认")
        self._caption = (self._current_caption or "本轮模型尚未确认") if self._active else choice
        set_button_icon(self.button, "chevron-down", text=self._caption, size=16)
        self.button.setText(self.button.fontMetrics().elidedText(self._caption, QtCore.Qt.ElideRight,
                                                                max(64, self.button.width() - 56)))
        self.button.setAccessibleName(self._caption)
        self.button.setToolTip((self.current.text() + "\n" + self.current.toolTip() if self._active else choice)
                               + "\n" + (self._constraint or self._base_note))

    def open_popup(self):
        if not self._interactive:
            return
        if self.popup.isVisible():
            self.popup.hide()
            return
        screen = self.button.screen().availableGeometry()
        width = min(360, max(1, screen.width() - 16))
        self.popup.ensurePolished()
        self.popup.setFixedWidth(width)
        self.popup.layout().activate()
        height = min(max(220, self.popup.sizeHint().height()), max(1, screen.height() - 16))
        self.popup.resize(width, height)
        self.position_popup()
        self.popup.show()
        self.popup.layout().activate()
        self.position_popup()
        self.models.setFocus(QtCore.Qt.PopupFocusReason)

    def position_popup(self):
        screen = self.button.screen().availableGeometry()
        if self.popup.height() > screen.height() - 16:
            self.popup.resize(self.popup.width(), max(1, screen.height() - 16))
        width, height = self.popup.width(), self.popup.height()
        top = self.button.mapToGlobal(QtCore.QPoint(0, 0))
        bottom = self.button.mapToGlobal(QtCore.QPoint(self.button.width(), self.button.height()))
        x = max(screen.left() + 8, min(bottom.x() - width, screen.right() - width - 7))
        y = bottom.y() + 4
        if y + height > screen.bottom() - 7:
            y = top.y() - height - 4
        y = max(screen.top() + 8, min(y, screen.bottom() - height - 7))
        self.popup.move(x, y)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.render_button()

    def sizeHint(self):
        return QtCore.QSize(min(320, max(180, self.button.fontMetrics().horizontalAdvance(self._caption) + 56)), 32)
