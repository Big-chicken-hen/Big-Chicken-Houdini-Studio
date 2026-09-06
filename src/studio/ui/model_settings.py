"""Ephemeral projection of native settings and the user's next-turn override."""
from PySide6 import QtCore, QtWidgets

from .shared import label


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
        self._narrow = None
        self.current_turn_id = None
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)
        self.row = QtWidgets.QBoxLayout(QtWidgets.QBoxLayout.LeftToRight)
        self.row.setSpacing(8)
        self.model_group = QtWidgets.QWidget()
        model_row = QtWidgets.QHBoxLayout(self.model_group)
        model_row.setContentsMargins(0, 0, 0, 0)
        model_row.addWidget(label("Model"))
        self.models = QtWidgets.QComboBox()
        self.models.setAccessibleName("下一轮模型")
        self.models.setPlaceholderText("等待原生会话设置")
        self.models.setMinimumWidth(0)
        self.models.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.models.setMinimumContentsLength(8)
        self.models.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        model_row.addWidget(self.models, 1)
        self.effort_group = QtWidgets.QWidget()
        effort_row = QtWidgets.QHBoxLayout(self.effort_group)
        effort_row.setContentsMargins(0, 0, 0, 0)
        effort_row.addWidget(label("Effort"))
        self.efforts = QtWidgets.QComboBox()
        self.efforts.setAccessibleName("下一轮推理档位")
        self.efforts.setMinimumWidth(0)
        self.efforts.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.efforts.setMinimumContentsLength(6)
        effort_row.addWidget(self.efforts, 1)
        self.row.addWidget(self.model_group, 3)
        self.row.addWidget(self.effort_group, 2)
        outer.addLayout(self.row)
        self.note = label("下一轮选择 · 等待会话设置", "muted", True)
        outer.addWidget(self.note)
        self.current = label("", "muted", True)
        self.current.hide()
        outer.addWidget(self.current)
        self.models.currentIndexChanged.connect(self.model_changed)
        self.efforts.currentIndexChanged.connect(self.effort_changed)

    def set_thread(self, thread_id):
        if thread_id == self.thread_id:
            return
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
        self.account_revision = revision
        self.catalog_revision = -1
        self.catalog_loaded = False
        self.catalog = {}
        self.render()

    def reset_connection(self):
        self.settings_revision = None
        self.native_source = "unknown"
        self.user_override = self.next_model is not None
        self.current.hide()
        self.render()

    def apply_native(self, settings, *, restore=False, last_requested=None):
        if not isinstance(settings, dict) or settings.get("thread_id") != self.thread_id:
            return False
        revision = settings.get("revision")
        if type(revision) is not int or (self.settings_revision is not None and revision < self.settings_revision):
            return False
        if revision == self.settings_revision and not restore:
            return True
        first = self.settings_revision is None
        self.settings_revision = revision
        self.native_source = settings.get("source", "unknown")
        if restore or not self.user_override:
            self.next_model = settings.get("model")
            self.next_effort = settings.get("effort")
            self.user_override = False
            self._adjustment = ""
            if (first and not restore and isinstance(last_requested, dict)
                    and last_requested.get("thread_id") == self.thread_id
                    and isinstance(last_requested.get("requested_model"), str)
                    and last_requested["requested_model"]
                    and (last_requested["requested_model"], last_requested.get("requested_effort")) != (self.next_model, self.next_effort)):
                self.next_model = last_requested["requested_model"]
                self.next_effort = last_requested.get("requested_effort")
                self.user_override = True
                self._adjustment = "下一轮选择 · 已恢复上次提交的选择"
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
            self.models.clear()
            for slug, model in self.catalog.items():
                self.models.addItem(model.get("displayName") or slug, model)
            selected = next((i for i in range(self.models.count())
                             if self.models.itemData(i)["model"] == self.next_model), -1)
            if selected < 0 and self.next_model:
                suffix = "（不可用）" if self.catalog_loaded else "（等待目录）"
                self.models.addItem(self.next_model + suffix, {"model": self.next_model, "unavailable": True})
                selected = self.models.count() - 1
            self.models.setCurrentIndex(selected)
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
        self.changed.emit()

    def model_changed(self, _index=None):
        item = self.models.currentData() or {}
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
        self.next_effort = self.efforts.currentData()
        self.user_override = True
        self.selection_revision += 1
        self._adjustment = ""
        self._base_note = "下一轮选择 · 不改变正在执行的工作"
        self.note.setText(self._constraint or self._base_note)
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

    def apply_turn(self, settings, *, active, turn_id=None):
        if not active:
            self.current.hide()
            return
        if self.current_turn_id != turn_id:
            self.current.hide()
        if (not isinstance(settings, dict) or settings.get("thread_id") != self.thread_id
                or turn_id is not None and settings.get("turn_id") != turn_id):
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

    def resizeEvent(self, event):
        super().resizeEvent(event)
        narrow = self.width() < 410
        if narrow != self._narrow:
            self._narrow = narrow
            self.row.setDirection(QtWidgets.QBoxLayout.TopToBottom if narrow else QtWidgets.QBoxLayout.LeftToRight)
