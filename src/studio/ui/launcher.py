from __future__ import annotations

from pathlib import Path

from PySide6 import QtCore, QtWidgets

from ..common import AppPaths, StudioError, read_json
from ..launcher import codex_executable, discover_houdini, launch, render_output_directory
from ..workspace import Workspaces
from .portal import LAUNCHER_STYLE, PortalArt
from .shared import Task, button, label


class StudioLauncher(QtWidgets.QWidget):
    def __init__(self, paths=None):
        super().__init__()
        self.paths = paths or AppPaths()
        self.workspaces = Workspaces(self.paths)
        self.busy = False
        self.status_pending = False
        self.sessions = {}
        self.launch_workspace = None
        self.setObjectName("studioLauncher")
        self.setWindowTitle("Big-Chicken · Houdini Studio")
        self.setStyleSheet(LAUNCHER_STYLE)
        self.resize(1160, 800)
        self.setMinimumSize(940, 700)
        root = QtWidgets.QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        hero = QtWidgets.QWidget()
        hero.setMinimumWidth(340)
        side = QtWidgets.QVBoxLayout(hero)
        side.setContentsMargins(36, 32, 30, 28)
        side.setSpacing(8)
        side.addWidget(label("BC /  BIG-CHICKEN", "brand"))
        side.addWidget(label("HOUDINI + CODEX     /     CREATIVE SYSTEMS", "eyebrow"))
        side.addSpacing(23)
        side.addWidget(label("CREATE\nBEYOND.", "portalTitle"))
        side.addWidget(label("把想象，写进现实。", "portalSubtitle"))
        self.portal = PortalArt()
        side.addWidget(self.portal, 1)
        self.workspace_identity = label("选择你的创作坐标", "portalSubtitle", True)
        side.addWidget(self.workspace_identity)
        side.addWidget(label("NATURAL LANGUAGE  →  EDITABLE WORLDS", "eyebrow"))
        side.addSpacing(9)
        side.addWidget(label("原生桌面  /  独立工作空间  /  可追踪执行", "muted"))
        root.addWidget(hero, 5)

        deck = QtWidgets.QFrame()
        deck.setObjectName("launchDeck")
        deck.setMinimumWidth(480)
        main = QtWidgets.QVBoxLayout(deck)
        main.setContentsMargins(28, 28, 28, 24)
        main.setSpacing(15)
        heading = QtWidgets.QHBoxLayout()
        heading.addWidget(label("01   /   工作空间", "brand"), 1)
        create = button("＋ 新建", self.create_workspace)
        create.setAccessibleName("新建工作空间")
        heading.addWidget(create)
        main.addLayout(heading)
        main.addWidget(label("每一次创作，都有自己的会话与执行记录。", "muted", True))
        self.projects = QtWidgets.QListWidget()
        self.projects.setAccessibleName("工作空间")
        self.projects.setMinimumHeight(112)
        self.projects.setMaximumHeight(166)
        self.projects.itemSelectionChanged.connect(self.update_selection)
        main.addWidget(self.projects)

        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        body = QtWidgets.QWidget()
        body.setObjectName("deckBody")
        body_layout = QtWidgets.QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(14)
        sheet = QtWidgets.QFrame()
        sheet.setObjectName("runtimeSheet")
        form = QtWidgets.QGridLayout(sheet)
        form.setContentsMargins(18, 18, 18, 18)
        form.setSpacing(12)
        form.addWidget(label("02   /   接入创作现场", "eyebrow"), 0, 0, 1, 3)
        self.houdini = QtWidgets.QComboBox()
        self.houdini.setAccessibleName("Houdini 可执行文件")
        self.houdini.setMinimumContentsLength(8)
        self.houdini.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        for item in discover_houdini():
            self.houdini.addItem(item["label"], item["path"])
        form.addWidget(label("Houdini"), 1, 0)
        form.addWidget(self.houdini, 1, 1)
        form.addWidget(button("浏览", self.choose_houdini), 1, 2)
        self.codex = QtWidgets.QLineEdit(codex_executable(self.paths))
        self.codex.setAccessibleName("Codex 可执行文件")
        self.codex.setPlaceholderText("Codex 0.153.4 · 原生可执行文件")
        form.addWidget(label("Codex"), 2, 0)
        form.addWidget(self.codex, 2, 1)
        form.addWidget(button("浏览", self.choose_codex), 2, 2)
        self.hip = QtWidgets.QLineEdit()
        self.hip.setAccessibleName("可选起始 HIP")
        self.hip.setPlaceholderText("空白场景，或选择已有 HIP")
        form.addWidget(label("起始 HIP"), 3, 0)
        form.addWidget(self.hip, 3, 1)
        form.addWidget(button("浏览", self.choose_hip), 3, 2)
        self.output_path = QtWidgets.QLineEdit(str(render_output_directory(self.paths)))
        self.output_path.setAccessibleName("默认渲染输出目录")
        self.output_path.setReadOnly(True)
        self.output_path.setToolTip("默认新渲染输出目录；已有 HIP 的输出参数保持原值。")
        form.addWidget(label("输出目录"), 4, 0)
        form.addWidget(self.output_path, 4, 1, 1, 2)
        form.setColumnStretch(1, 1)
        body_layout.addWidget(sheet)
        self.status = label("工作空间将单独保存会话、附件与执行记录。", "statusMessage", True)
        self.status.setTextFormat(QtCore.Qt.PlainText)
        self.status.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        self.status.setAccessibleName("启动状态与错误")
        body_layout.addWidget(self.status)
        body_layout.addStretch()
        scroll.setWidget(body)
        main.addWidget(scroll, 1)
        main.addWidget(label("03   /   ENTER YOUR CREATIVE SPACE", "eyebrow"))
        self.launch_button = button("启动工作室    →", self.start_session, "launchPrimary")
        self.launch_button.setAccessibleName("启动 Houdini 工作室")
        self.launch_button.setMinimumHeight(54)
        main.addWidget(self.launch_button)
        main.addWidget(label("HOM 现场执行  ·  CODEX 原生会话  ·  STUDIO 0.1", "muted"))
        root.addWidget(deck, 6)
        self.poll = QtCore.QTimer(self)
        self.poll.setInterval(1500)
        self.poll.timeout.connect(self.session_status)
        self.reload_workspaces()

    def reload_workspaces(self):
        current = self.projects.currentItem()
        workspace_id = current.data(QtCore.Qt.UserRole) if current else None
        self.projects.blockSignals(True)
        self.projects.clear()
        for value in self.workspaces.list():
            item = QtWidgets.QListWidgetItem(value["name"] + "\n独立会话  ·  项目决策  ·  执行记录")
            item.setData(QtCore.Qt.UserRole, value["workspace_id"])
            item.setToolTip(value["name"] + "\n" + value["workspace_id"])
            self.projects.addItem(item)
        if self.projects.count():
            self.projects.setCurrentRow(0)
            for index in range(self.projects.count()):
                if self.projects.item(index).data(QtCore.Qt.UserRole) == workspace_id:
                    self.projects.setCurrentRow(index)
        else:
            item = QtWidgets.QListWidgetItem("还没有工作空间。点击“＋ 新建”开始。")
            item.setFlags(QtCore.Qt.NoItemFlags)
            self.projects.addItem(item)
        self.projects.blockSignals(False)
        self.update_selection()

    def update_selection(self):
        item = self.projects.currentItem()
        workspace_id = item.data(QtCore.Qt.UserRole) if item else None
        session = self.sessions.get(workspace_id, {})
        self.workspace_identity.setText(item.text().split("\n", 1)[0] if workspace_id else "选择你的创作坐标")
        self.output_path.setText(session.get("render_output_directory") or str(render_output_directory(self.paths)))
        active = session.get("state") in {"starting", "ready", "unknown"}
        self.launch_button.setEnabled(bool(workspace_id) and not self.busy and not active)
        self.launch_button.setText("正在启动…" if self.busy else "工作室已打开" if active else "启动工作室    →")
        self.portal.set_launching(self.busy or session.get("state") == "starting")
        if self.busy:
            self.status.setText("检查环境，准备启动…")
        elif session:
            state = session.get("state")
            text = {"starting": "Houdini 正在打开。运行时连接后即可进入 Panel。",
                    "ready": "● 工作室已连接。请在 Houdini 的 Python Panel 中打开 Big-Chicken Studio。",
                    "closed": "Houdini 已退出，会话与执行记录已保留。",
                    "unknown": "会话状态暂时无法读取。正在等待下一次状态更新。"}.get(state)
            self.status.setText(text or session.get("message", "启动失败，请检查所选环境。"))
        else:
            self.status.setText("工作空间将单独保存会话、附件与执行记录。")

    def create_workspace(self):
        name, ok = QtWidgets.QInputDialog.getText(self, "新建工作空间", "给这次创作起个名字")
        if ok and name.strip():
            try:
                value = self.workspaces.create(name)
            except (StudioError, OSError) as exc:
                self.status.setText(str(exc))
                return
            self.reload_workspaces()
            for i in range(self.projects.count()):
                if self.projects.item(i).data(QtCore.Qt.UserRole) == value["workspace_id"]:
                    self.projects.setCurrentRow(i)

    def choose_houdini(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "选择 Houdini", "", "Houdini (houdini.exe houdinifx.exe)")
        if path:
            self.houdini.addItem(Path(path).parent.parent.name, path)
            self.houdini.setCurrentIndex(self.houdini.count() - 1)

    def choose_codex(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "选择 Codex 0.153.4", "", "Codex (codex.exe)")
        if path:
            self.codex.setText(path)

    def choose_hip(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "选择场景", "", "Houdini scenes (*.hip *.hiplc *.hipnc)")
        if path:
            self.hip.setText(path)

    def start_session(self):
        if not self.launch_button.isEnabled() or self.busy:
            return
        item = self.projects.currentItem()
        if not item or not item.data(QtCore.Qt.UserRole):
            return
        values = (item.data(QtCore.Qt.UserRole), self.houdini.currentData() or "", self.codex.text(), self.hip.text() or None)
        self.busy = True
        self.launch_workspace = values[0]
        self.update_selection()
        self.task = Task(lambda: launch(self.paths, *values))
        self.task.signals.result.connect(self.launched)
        self.task.signals.error.connect(self.failed)
        QtCore.QThreadPool.globalInstance().start(self.task)

    def launched(self, value):
        self.busy = False
        self.sessions[self.launch_workspace] = {**value, "state": "starting"}
        self.update_selection()
        self.poll.start()

    def session_status(self):
        if self.status_pending:
            return
        self.status_pending = True
        sessions = {key: dict(value) for key, value in self.sessions.items()}

        def read_statuses():
            result = {}
            for key, session in sessions.items():
                if session.get("state") in {"closed", "failed"}:
                    continue
                file = Path(session["directory"]) / "status.json"
                try:
                    if file.is_file():
                        value = read_json(file)
                        if not isinstance(value, dict) or "state" not in value:
                            raise ValueError("Invalid session status")
                        result[key] = {**session, **value}
                except (ValueError, OSError):
                    result[key] = {**session, "state": "unknown"}
            return result

        self.status_task = Task(read_statuses)
        self.status_task.signals.result.connect(self.statuses_read)
        self.status_task.signals.error.connect(self.status_read_failed)
        QtCore.QThreadPool.globalInstance().start(self.status_task)

    def statuses_read(self, values):
        self.status_pending = False
        self.sessions.update(values)
        self.update_selection()
        if all(value.get("state") in {"closed", "failed"} for value in self.sessions.values()):
            self.poll.stop()

    def status_read_failed(self, message):
        self.status_pending = False
        self.status.setText("状态读取失败：" + message)

    def failed(self, message):
        self.busy = False
        self.update_selection()
        self.status.setText(message)

    def closeEvent(self, event):
        self.poll.stop()
        self.portal.set_launching(False)
        super().closeEvent(event)
