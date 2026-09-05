"""Native workspace entrance. Process ownership remains in the launcher backend."""
from __future__ import annotations

from pathlib import Path

from PySide6 import QtCore, QtWidgets

from ..common import AppPaths, StudioError, read_json
from ..codex.protocol import SUPPORTED_CODEX_VERSION
from ..launcher import codex_executable, discover_houdini, launch, render_output_directory
from ..workspace import Workspaces
from .launcher_visuals import LAUNCHER_STYLE, LaunchActivity, StationArtwork
from .shared import Task, button, label


class StudioLauncher(QtWidgets.QWidget):
    def __init__(self, paths=None, *, workspaces=None, installations=None, codex_path=None, launch_function=None):
        super().__init__()
        self.paths = paths or AppPaths()
        self.workspaces = workspaces if workspaces is not None else Workspaces(self.paths)
        self._launch = launch_function or launch
        self.busy = False
        self.status_pending = False
        self.sessions = {}
        self.errors = {}
        self.launch_workspace = None
        self._closed = False
        self.setObjectName("studioLauncher")
        self.setWindowTitle("Big-Chicken · Houdini Studio")
        self.setStyleSheet(LAUNCHER_STYLE)
        self.resize(1180, 850)
        self.setMinimumSize(800, 620)
        self.build_ui(installations if installations is not None else discover_houdini(),
                      codex_path if codex_path is not None else codex_executable(self.paths))
        self.poll = QtCore.QTimer(self)
        self.poll.setInterval(1500)
        self.poll.timeout.connect(self.session_status)
        self.reload_workspaces()

    def build_ui(self, installations, codex_path):
        root = QtWidgets.QHBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(18)
        self.artwork = StationArtwork()
        self.hero_layout = QtWidgets.QVBoxLayout(self.artwork)
        self.hero_layout.setContentsMargins(30, 30, 30, 27)
        self.hero_layout.setSpacing(8)
        self.hero_layout.addWidget(label("BC /  BIG-CHICKEN", "brand"))
        self.hero_layout.addWidget(label("HOUDINI STUDIO", "heroEyebrow"))
        self.hero_layout.addSpacing(36)
        self.hero_title = label("让灵感\n亮一盏灯。", "heroTitle")
        self.hero_layout.addWidget(self.hero_title)
        self.hero_layout.addWidget(label("一个想法，一处新的创作现场。", "heroSubtitle", True))
        self.hero_layout.addStretch(1)
        self.hero_layout.addWidget(label("AFTER HOURS / CREATIVE STUDIO", "heroEyebrow"))
        self.hero_layout.addSpacing(3)
        self.workspace_identity = label("今晚，从这里开始。", "heroCaption", True)
        self.workspace_identity.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Preferred)
        self.hero_layout.addWidget(self.workspace_identity)
        self.hero_layout.addSpacing(7)
        self.hero_layout.addWidget(label("由 Codex 驱动  ·  在 Houdini 创作", "heroSubtitle", True))
        root.addWidget(self.artwork, 5)

        deck = QtWidgets.QFrame()
        deck.setObjectName("launchDeck")
        deck.setMinimumWidth(440)
        layout = QtWidgets.QVBoxLayout(deck)
        layout.setContentsMargins(27, 26, 27, 23)
        layout.setSpacing(10)
        heading = QtWidgets.QHBoxLayout()
        heading.addWidget(label("SESSION ENTRY", "eyebrow"), 1)
        heading.addWidget(label("STUDIO / 0.1", "eyebrow"))
        layout.addLayout(heading)
        layout.addWidget(label("进入工作室", "deckTitle"))
        layout.addWidget(label("选择工作空间，接上你的 Houdini。", "muted"))

        self.form_scroll = QtWidgets.QScrollArea()
        self.form_scroll.setWidgetResizable(True)
        self.form_scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        body = QtWidgets.QWidget()
        body.setObjectName("deckBody")
        form = QtWidgets.QVBoxLayout(body)
        form.setContentsMargins(0, 0, 3, 0)
        form.setSpacing(13)
        row = self.section_heading("01", "工作空间")
        self.create_button = button("＋ 新建", self.create_workspace, "quiet")
        self.create_button.setAccessibleName("新建工作空间")
        row.addWidget(self.create_button)
        form.addLayout(row)
        self.projects = QtWidgets.QListWidget()
        self.projects.setAccessibleName("选择工作空间")
        self.projects.setTextElideMode(QtCore.Qt.ElideRight)
        self.projects.setMinimumHeight(86)
        self.projects.setMaximumHeight(136)
        self.projects.itemSelectionChanged.connect(self.update_selection)
        form.addWidget(self.projects)
        self.empty_workspace = QtWidgets.QFrame()
        self.empty_workspace.setObjectName("emptyWorkspace")
        empty = QtWidgets.QVBoxLayout(self.empty_workspace)
        empty.setContentsMargins(17, 15, 17, 16)
        empty.setSpacing(9)
        empty.addWidget(label("为第一份作品，留一个位置。", "emptyTitle", True))
        empty.addWidget(label("工作空间会保存你的会话、附件与项目决策。", "muted", True))
        self.workspace_name = QtWidgets.QLineEdit()
        self.workspace_name.setPlaceholderText("给这次创作起个名字")
        self.workspace_name.setMaxLength(120)
        self.workspace_name.setAccessibleName("首个工作空间名称")
        self.workspace_name.returnPressed.connect(self.create_first_workspace)
        empty.addWidget(self.workspace_name)
        self.create_first = button("创建工作空间    ＋", self.create_first_workspace, "createPrimary")
        empty.addWidget(self.create_first)
        form.addWidget(self.empty_workspace)

        environment = self.environment = QtWidgets.QFrame()
        environment.setObjectName("environment")
        env = QtWidgets.QVBoxLayout(environment)
        env.setContentsMargins(17, 15, 17, 16)
        env.setSpacing(11)
        env.addLayout(self.section_heading("02", "启动现场"))
        env.addWidget(label("Houdini", "hint"))
        row = QtWidgets.QHBoxLayout()
        self.houdini = QtWidgets.QComboBox()
        self.houdini.setAccessibleName("Houdini 可执行文件")
        self.houdini.setPlaceholderText("选择 Houdini 环境")
        self.houdini.setMinimumContentsLength(12)
        self.houdini.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        for item in installations:
            self.houdini.addItem(item["label"], item["path"])
            self.houdini.setItemData(self.houdini.count() - 1, item["path"], QtCore.Qt.ToolTipRole)
        if self.houdini.count():
            self.houdini.setCurrentIndex(0)
        self.houdini_browse = button("选择…", self.choose_houdini)
        row.addWidget(self.houdini, 1)
        row.addWidget(self.houdini_browse)
        env.addLayout(row)
        self.environment_hint = label("", "environmentHint", True)
        env.addWidget(self.environment_hint)
        env.addWidget(label("起始场景  /  可选", "hint"))
        row = QtWidgets.QHBoxLayout()
        self.hip = QtWidgets.QLineEdit()
        self.hip.setPlaceholderText("从空白开始，或打开已有 HIP")
        self.hip.setClearButtonEnabled(True)
        self.hip.setAccessibleName("可选起始 HIP")
        self.hip_browse = button("选择…", self.choose_hip)
        row.addWidget(self.hip, 1)
        row.addWidget(self.hip_browse)
        env.addLayout(row)
        form.addWidget(environment)

        self.settings_toggle = QtWidgets.QToolButton()
        self.settings_toggle.setObjectName("settingsToggle")
        self.settings_toggle.setText("启动设置 · Codex 与输出目录")
        self.settings_toggle.setCheckable(True)
        self.settings_toggle.setArrowType(QtCore.Qt.RightArrow)
        self.settings_toggle.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self.settings_toggle.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.settings_toggle.toggled.connect(self.toggle_settings)
        form.addWidget(self.settings_toggle)
        self.settings = QtWidgets.QWidget()
        settings = QtWidgets.QVBoxLayout(self.settings)
        settings.setContentsMargins(0, 0, 0, 0)
        settings.setSpacing(9)
        settings.addWidget(label("Codex " + SUPPORTED_CODEX_VERSION + "  /  可执行文件", "hint"))
        row = QtWidgets.QHBoxLayout()
        self.codex = QtWidgets.QLineEdit(codex_path)
        self.codex.setAccessibleName("Codex 可执行文件")
        self.codex.setPlaceholderText("选择本机 Codex 可执行文件")
        self.codex_browse = button("选择…", self.choose_codex)
        row.addWidget(self.codex, 1)
        row.addWidget(self.codex_browse)
        settings.addLayout(row)
        settings.addWidget(label("默认渲染输出目录", "hint"))
        self.output_path = QtWidgets.QLineEdit(str(render_output_directory(self.paths)))
        self.output_path.setAccessibleName("默认渲染输出目录")
        self.output_path.setReadOnly(True)
        self.output_path.setToolTip("新渲染的默认目录；已有 HIP 的输出参数保持原值。")
        settings.addWidget(self.output_path)
        settings.addWidget(label("这些设置仅供 Studio 启动使用。", "muted"))
        self.settings.hide()
        form.addWidget(self.settings)
        form.addStretch(1)
        self.form_scroll.setWidget(body)
        layout.addWidget(self.form_scroll, 1)

        self.status_card = QtWidgets.QFrame()
        self.status_card.setObjectName("statusCard")
        status_layout = QtWidgets.QVBoxLayout(self.status_card)
        status_layout.setContentsMargins(13, 11, 13, 10)
        status_layout.setSpacing(5)
        row = QtWidgets.QHBoxLayout()
        self.activity = LaunchActivity()
        row.addWidget(self.activity)
        self.status = label("准备你的创作空间", "statusTitle")
        self.status.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        row.addWidget(self.status, 1)
        self.status_code = label("STANDBY", "statusCode")
        row.addWidget(self.status_code)
        status_layout.addLayout(row)
        self.status_details = QtWidgets.QPlainTextEdit()
        self.status_details.setObjectName("statusDetails")
        self.status_details.setAccessibleName("完整启动状态和错误详情，可选择并复制")
        self.status_details.setReadOnly(True)
        self.status_details.setFixedHeight(52)
        self.status_details.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.status_details.setTabChangesFocus(True)
        status_layout.addWidget(self.status_details)
        row = QtWidgets.QHBoxLayout()
        row.addStretch()
        self.copy_status = button("复制详情", self.copy_details, "copyStatus")
        self.copy_status.setAccessibleName("复制完整状态或错误信息")
        self.copy_status.setMaximumHeight(26)
        row.addWidget(self.copy_status)
        status_layout.addLayout(row)
        layout.addWidget(self.status_card)
        self.launch_button = button("进入工作室    ↗", self.start_session, "launchPrimary")
        self.launch_button.setAccessibleName("进入 Houdini 工作室")
        self.launch_button.setMinimumHeight(55)
        layout.addWidget(self.launch_button)
        layout.addWidget(label("本地工作空间  /  原生 Houdini  /  Codex 会话", "eyebrow"))
        root.addWidget(deck, 6)
        self.configuration_controls = [self.houdini, self.houdini_browse, self.hip, self.hip_browse,
                                       self.codex, self.codex_browse]
        self.houdini.currentIndexChanged.connect(self.inputs_changed)
        self.codex.textChanged.connect(self.inputs_changed)
        self.hip.textChanged.connect(self.inputs_changed)
        self.setTabOrder(self.projects, self.houdini)
        self.setTabOrder(self.houdini, self.houdini_browse)
        self.setTabOrder(self.houdini_browse, self.hip)
        self.setTabOrder(self.hip, self.hip_browse)
        self.setTabOrder(self.hip_browse, self.settings_toggle)
        self.setTabOrder(self.settings_toggle, self.launch_button)

    @staticmethod
    def section_heading(number, text):
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(9)
        row.addWidget(label(number, "sectionNumber"))
        row.addWidget(label(text, "sectionTitle"), 1)
        return row

    def selected_workspace(self):
        item = self.projects.currentItem()
        return item.data(QtCore.Qt.UserRole) if item else None

    def reload_workspaces(self):
        selected = self.selected_workspace()
        try:
            values = self.workspaces.list()
        except (OSError, ValueError, StudioError) as exc:
            self.errors[selected] = str(exc)
            self.update_selection()
            return
        self.projects.blockSignals(True)
        self.projects.clear()
        for value in values:
            item = QtWidgets.QListWidgetItem(value["name"] + "\n会话 · 附件 · 项目决策")
            item.setData(QtCore.Qt.UserRole, value["workspace_id"])
            item.setToolTip(value["name"] + "\n" + value["workspace_id"])
            self.projects.addItem(item)
        if values:
            self.projects.setCurrentRow(0)
            for index in range(self.projects.count()):
                if self.projects.item(index).data(QtCore.Qt.UserRole) == selected:
                    self.projects.setCurrentRow(index)
        self.projects.blockSignals(False)
        self.update_selection()

    def update_selection(self):
        workspace_id = self.selected_workspace()
        session = self.sessions.get(workspace_id, {})
        has_projects = self.projects.count() > 0
        self.projects.setVisible(has_projects)
        self.projects.setFixedHeight(min(136, max(68, self.projects.count() * 65)))
        self.empty_workspace.setVisible(not has_projects)
        self.environment.setVisible(has_projects)
        self.settings_toggle.setVisible(has_projects)
        self.create_button.setVisible(has_projects)
        self.projects.setEnabled(not self.busy)
        self.create_button.setEnabled(not self.busy)
        self.create_first.setEnabled(not self.busy)
        self.workspace_name.setEnabled(not self.busy)
        self.output_path.setText(session.get("render_output_directory") or str(render_output_directory(self.paths)))
        current = self.projects.currentItem()
        title = current.text().split("\n", 1)[0] if workspace_id else "今晚，从这里开始。"
        self.workspace_identity.setText(title if len(title) <= 30 else title[:29] + "…")
        self.workspace_identity.setToolTip(title)
        active = session.get("state") in {"starting", "ready", "unknown"} or bool(session.get("houdini_left_running"))
        for control in self.configuration_controls:
            control.setEnabled(not self.busy and not active)
        missing = not self.houdini.currentData() or not self.codex.text().strip()
        hint = ("尚未找到 Houdini，请选择安装中的可执行文件。" if not self.houdini.currentData() else
                "尚未找到 Codex，请在「启动设置」中选择。" if not self.codex.text().strip() else "")
        self.environment_hint.setText(hint)
        self.environment_hint.setVisible(bool(hint))
        self.launch_button.setEnabled(bool(workspace_id) and not self.busy and not active)
        self.launch_button.setText("检查并启动中…" if self.busy else
                                   "正在连接工作室…" if session.get("state") == "starting" else
                                   "工作室已打开" if session.get("state") == "ready" else
                                   "等待会话状态确认" if active else
                                   "创建后即可进入" if not workspace_id else "补全启动环境    →" if missing else "进入工作室    ↗")
        self.activity.set_active(self.busy or session.get("state") == "starting")
        error = self.errors.get(workspace_id) or self.errors.get(None)
        state = session.get("state")
        if self.busy:
            self.set_status("working", "检查并启动环境", "STARTING", "正在检查所选版本并启动 Studio。完成后会继续等待 Houdini 注册。")
        elif error:
            self.set_status("error", "启动遇到问题", "ATTENTION", error)
        elif state == "failed":
            message = session.get("message", "启动失败，请检查所选环境。")
            if session.get("houdini_left_running"):
                message += "\n上次状态确认 Houdini 仍在运行，当前工作空间保持占用。"
            self.set_status("error", "会话未正常连接", "FAILED", message)
        elif state == "starting":
            self.set_status("working", "等待 Houdini 注册", "CONNECTING", "启动请求已交给 Studio。Houdini 注册 Runtime 后，这里会显示已连接。")
        elif state == "ready":
            self.set_status("ready", "工作室已连接", "CONNECTED", "在 Houdini 的 Python Panel 中选择 Big-Chicken Studio。")
        elif state == "unknown":
            self.set_status("error", "会话状态暂未确认", "UNKNOWN", session.get("message") or "暂时无法读取状态文件，正在等待下次更新。场景结果请查看原操作收据。")
        elif state == "closed":
            self.set_status("idle", "Houdini 已退出", "CLOSED", "会话与执行记录已保留，可以再次进入。场景操作结果以 Runtime 收据为准。")
        elif not workspace_id:
            self.set_status("idle", "先创建一个工作空间", "STANDBY", "写下工作空间名称，点击创建。这里会成为你的会话、参考图和项目决策的归处。")
        elif missing:
            self.set_status("error", "还需要选择启动环境", "SETUP", hint)
        else:
            self.set_status("idle", "可以进入工作室", "STANDBY", "从空白场景开始，或选择一份已有 HIP。点击进入时会检查所选环境。")

    def set_status(self, tone, title, code, details):
        if self.status_card.property("tone") != tone:
            self.status_card.setProperty("tone", tone)
            self.status_card.style().unpolish(self.status_card)
            self.status_card.style().polish(self.status_card)
        self.status.setText(title)
        self.status_code.setText(code)
        # Preserve selection and scroll position when a poll repeats the same text.
        if self.status_details.toPlainText() != str(details):
            self.status_details.setPlainText(str(details))
        self.copy_status.setEnabled(bool(details))

    def copy_details(self):
        QtWidgets.QApplication.clipboard().setText(self.status_details.toPlainText())

    def inputs_changed(self, *_args):
        self.houdini.setToolTip(str(self.houdini.currentData() or ""))
        self.hip.setToolTip(self.hip.text())
        self.codex.setToolTip(self.codex.text())
        self.update_selection()

    def toggle_settings(self, checked):
        self.settings.setVisible(checked)
        self.settings_toggle.setArrowType(QtCore.Qt.DownArrow if checked else QtCore.Qt.RightArrow)
        if checked:
            QtCore.QTimer.singleShot(0, lambda: self.form_scroll.ensureWidgetVisible(self.settings))

    def create_first_workspace(self):
        self.record_workspace(self.workspace_name.text())

    def create_workspace(self):
        name, ok = QtWidgets.QInputDialog.getText(self, "新建工作空间", "给这次创作起个名字")
        if ok:
            self.record_workspace(name)

    def record_workspace(self, name):
        if self.busy:
            return
        if not name.strip():
            self.workspace_name.setFocus()
            self.set_status("error", "给工作空间起个名字", "NAME", "输入一个名称后即可创建。")
            return
        try:
            value = self.workspaces.create(name.strip())
        except (StudioError, OSError, ValueError) as exc:
            self.errors[self.selected_workspace()] = str(exc)
            self.update_selection()
            return
        self.errors.pop(None, None)
        self.workspace_name.clear()
        self.reload_workspaces()
        for index in range(self.projects.count()):
            if self.projects.item(index).data(QtCore.Qt.UserRole) == value["workspace_id"]:
                self.projects.setCurrentRow(index)
        self.houdini.setFocus()

    def choose_houdini(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "选择 Houdini", "", "Houdini (houdini.exe houdinifx.exe houdini)")
        if path:
            index = self.houdini.findData(path)
            if index < 0:
                self.houdini.addItem(Path(path).parent.parent.name, path)
                index = self.houdini.count() - 1
            self.houdini.setCurrentIndex(index)
            self.inputs_changed()

    def choose_codex(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "选择 Codex " + SUPPORTED_CODEX_VERSION, "", "Codex (codex.exe codex)")
        if path:
            self.codex.setText(path)

    def choose_hip(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "选择场景", "", "Houdini scenes (*.hip *.hiplc *.hipnc)")
        if path:
            self.hip.setText(path)

    def start_session(self):
        if not self.launch_button.isEnabled() or self.busy:
            return
        workspace_id = self.selected_workspace()
        if not workspace_id:
            return
        if not self.houdini.currentData():
            self.choose_houdini()
            return
        if not self.codex.text().strip():
            self.settings_toggle.setChecked(True)
            self.codex.setFocus()
            return
        values = (workspace_id, self.houdini.currentData(), self.codex.text().strip(), self.hip.text().strip() or None)
        self.errors.pop(workspace_id, None)
        self.errors.pop(None, None)
        self.busy = True
        self.launch_workspace = workspace_id
        self.update_selection()
        self.task = Task(lambda: self._launch(self.paths, *values))
        self.task.signals.result.connect(self.launched)
        self.task.signals.error.connect(self.failed)
        QtCore.QThreadPool.globalInstance().start(self.task)

    def launched(self, value):
        self.busy = False
        self.sessions[self.launch_workspace] = {**value, "state": "starting"}
        self.update_selection()
        if not self._closed:
            self.poll.start()

    def session_status(self):
        if self.status_pending or self._closed:
            return
        self.status_pending = True
        sessions = {key: dict(value) for key, value in self.sessions.items()}

        def read_statuses():
            results = {}
            for key, session in sessions.items():
                if session.get("state") in {"closed", "failed"}:
                    continue
                file = Path(session["directory"]) / "status.json"
                try:
                    value = read_json(file)
                    if not isinstance(value, dict) or value.get("state") not in {"starting", "ready", "closed", "failed"}:
                        raise ValueError("Invalid session status")
                    results[key] = {**session, **value}
                except (ValueError, OSError):
                    results[key] = {**session, "state": "unknown", "message": "会话状态文件暂时不可读，正在等候重新确认。"}
            return results

        self.status_task = Task(read_statuses)
        self.status_task.signals.result.connect(self.statuses_read)
        self.status_task.signals.error.connect(self.status_read_failed)
        QtCore.QThreadPool.globalInstance().start(self.status_task)

    def statuses_read(self, values):
        self.status_pending = False
        for key, value in values.items():
            # A late read from a previous owned session cannot replace a new one.
            if self.sessions.get(key, {}).get("directory") == value.get("directory"):
                self.sessions[key] = value
        self.update_selection()
        if all(value.get("state") in {"closed", "failed"} for value in self.sessions.values()):
            self.poll.stop()

    def status_read_failed(self, message):
        self.status_pending = False
        self.errors[self.selected_workspace()] = "状态读取失败：" + str(message)
        self.update_selection()

    def failed(self, message):
        self.errors[self.launch_workspace if self.busy else self.selected_workspace()] = str(message)
        self.busy = False
        self.update_selection()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QtCore.QEvent.WindowStateChange:
            self.activity.sync_motion()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        compact = self.width() < 1030
        self.hero_title.setStyleSheet("font-size: 29px;" if compact else "")
        self.hero_layout.setContentsMargins(22 if compact else 30, 28, 22 if compact else 30, 26)

    def showEvent(self, event):
        self._closed = False
        self.activity.sync_motion()
        if self.sessions and any(value.get("state") not in {"closed", "failed"} for value in self.sessions.values()):
            self.poll.start()
        super().showEvent(event)

    def closeEvent(self, event):
        self._closed = True
        self.poll.stop()
        self.activity.set_active(False)
        super().closeEvent(event)
