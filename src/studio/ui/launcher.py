from __future__ import annotations

from pathlib import Path

from PySide6 import QtCore, QtWidgets

from ..common import AppPaths, read_json
from ..launcher import codex_executable, discover_houdini, launch
from ..workspace import Workspaces
from .shared import LIGHT, StudioGlyph, Task, button, label


class StudioLauncher(QtWidgets.QWidget):
    def __init__(self, paths=None):
        super().__init__()
        self.paths = paths or AppPaths()
        self.workspaces = Workspaces(self.paths)
        self.setObjectName("studioLauncher")
        self.setWindowTitle("Big-Chicken · Houdini Studio")
        self.setStyleSheet(LIGHT)
        self.resize(1100, 760)
        self.setMinimumSize(860, 660)
        root = QtWidgets.QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        rail = QtWidgets.QFrame()
        rail.setObjectName("rail")
        rail.setFixedWidth(215)
        side = QtWidgets.QVBoxLayout(rail)
        side.setContentsMargins(26, 34, 26, 28)
        side.addWidget(label("BC /", "brand"))
        side.addSpacing(14)
        side.addWidget(label("Big-Chicken", "brand"))
        side.addWidget(label("HOUDINI STUDIO"))
        side.addSpacing(50)
        side.addWidget(button("01   工作空间", lambda: self.projects.setFocus(), "railButton"))
        side.addSpacing(10)
        side.addWidget(label("把想法变成\n可以继续编辑的作品。", wrap=True))
        side.addStretch()
        side.addWidget(label("LOCAL FIRST\n由 Codex 驱动 · 在 Houdini 创作", wrap=True))
        side.addSpacing(15)
        side.addWidget(label("STUDIO  /  0.1.0"))
        root.addWidget(rail)
        main = QtWidgets.QVBoxLayout()
        main.setContentsMargins(38, 30, 38, 26)
        main.setSpacing(16)
        root.addLayout(main, 1)
        main.addWidget(label("A SPACE FOR YOUR NEXT IDEA", "eyebrow"))
        hero = QtWidgets.QHBoxLayout()
        text = QtWidgets.QVBoxLayout()
        text.addWidget(label("让下一个想法，\n在这里成形。", "title"))
        text.addWidget(label("选择工作空间，进入你的 Houdini 创作现场。", "muted"))
        hero.addLayout(text, 1)
        glyph = StudioGlyph()
        glyph.setFixedWidth(180)
        hero.addWidget(glyph)
        main.addLayout(hero)
        heading = QtWidgets.QHBoxLayout()
        heading.addWidget(label("工作空间  /  WORKSPACES", "eyebrow"))
        heading.addStretch()
        heading.addWidget(button("＋ 新建", self.create_workspace))
        main.addLayout(heading)
        self.projects = QtWidgets.QListWidget()
        self.projects.setMinimumHeight(105)
        self.projects.setMaximumHeight(170)
        self.projects.itemSelectionChanged.connect(self.update_selection)
        main.addWidget(self.projects, 1)
        sheet = QtWidgets.QFrame()
        sheet.setObjectName("sheet")
        form = QtWidgets.QGridLayout(sheet)
        form.setContentsMargins(20, 18, 20, 18)
        form.setSpacing(12)
        form.addWidget(label("运行环境", "eyebrow"), 0, 0, 1, 3)
        self.houdini = QtWidgets.QComboBox()
        for item in discover_houdini():
            self.houdini.addItem(item["label"], item["path"])
        form.addWidget(label("Houdini"), 1, 0)
        form.addWidget(self.houdini, 1, 1)
        form.addWidget(button("选择…", self.choose_houdini), 1, 2)
        self.codex = QtWidgets.QLineEdit(codex_executable(self.paths))
        self.codex.setPlaceholderText("选择 Codex 0.153.4 可执行文件")
        form.addWidget(label("Codex"), 2, 0)
        form.addWidget(self.codex, 2, 1)
        form.addWidget(button("选择…", self.choose_codex), 2, 2)
        self.hip = QtWidgets.QLineEdit()
        self.hip.setPlaceholderText("空白场景，或选择已有 HIP")
        form.addWidget(label("起始场景"), 3, 0)
        form.addWidget(self.hip, 3, 1)
        form.addWidget(button("选择…", self.choose_hip), 3, 2)
        form.setColumnStretch(1, 1)
        main.addWidget(sheet)
        self.status = label("工作空间将单独保存会话、附件与执行记录。", "muted", True)
        main.addWidget(self.status)
        footer = QtWidgets.QHBoxLayout()
        footer.addWidget(label("BIG IDEAS. SMALL BEGINNINGS.", "eyebrow"), 1)
        self.launch_button = button("进入工作室    ↗", self.start_session, "primary")
        footer.addWidget(self.launch_button)
        main.addLayout(footer)
        self.session_dir = None
        self.poll = QtCore.QTimer(self)
        self.poll.setInterval(600)
        self.poll.timeout.connect(self.session_status)
        self.reload_workspaces()

    def reload_workspaces(self):
        self.projects.clear()
        for value in self.workspaces.list():
            item = QtWidgets.QListWidgetItem(value["name"] + "\n独立会话  ·  项目决策  ·  执行记录")
            item.setData(QtCore.Qt.UserRole, value["workspace_id"])
            self.projects.addItem(item)
        if self.projects.count():
            self.projects.setCurrentRow(0)
        else:
            self.projects.addItem("还没有工作空间。点击“＋ 新建”开始。")
        self.update_selection()

    def update_selection(self):
        item = self.projects.currentItem()
        self.launch_button.setEnabled(bool(item and item.data(QtCore.Qt.UserRole)))

    def create_workspace(self):
        name, ok = QtWidgets.QInputDialog.getText(self, "新建工作空间", "给这次创作起个名字")
        if ok and name.strip():
            value = self.workspaces.create(name)
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
        item = self.projects.currentItem()
        if not item or not item.data(QtCore.Qt.UserRole):
            return
        values = (item.data(QtCore.Qt.UserRole), self.houdini.currentData() or "", self.codex.text(), self.hip.text() or None)
        self.launch_button.setEnabled(False)
        self.status.setText("检查环境，准备启动…")
        self.task = Task(lambda: launch(self.paths, *values))
        self.task.signals.result.connect(self.launched)
        self.task.signals.error.connect(self.failed)
        QtCore.QThreadPool.globalInstance().start(self.task)

    def launched(self, value):
        self.session_dir = Path(value["directory"])
        self.status.setText("Houdini 正在打开。连接后在 Python Panel 中选择 Big-Chicken Studio。")
        self.poll.start()

    def session_status(self):
        file = self.session_dir / "status.json"
        if not file.exists():
            return
        value = read_json(file)
        if value["state"] == "ready":
            self.status.setText("● 工作室已就绪。在 Houdini 的 Python Panel 菜单中打开 Big-Chicken Studio。")
            self.poll.stop()
            self.launch_button.setEnabled(True)
        elif value["state"] in {"failed", "closed"}:
            self.failed(value.get("message", "Houdini 已退出。会话和执行记录已经保留。"))

    def failed(self, message):
        self.poll.stop()
        self.status.setText(message)
        self.launch_button.setEnabled(True)
