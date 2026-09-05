"""Big-Chicken Studio Panel: a projection of Codex and runtime facts."""
from __future__ import annotations

import json
import os
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from ..common import AppPaths, StudioError, read_json
from .conversation import ImageTile, Transcript
from .requests import RequestCard
from .shared import DARK, Api, button, clear_layout, label


PANEL_STYLE = DARK + """
QWidget#studioPanel, QWidget#transcript { background: #20231F; }
QFrame#panelHeader { background: #F1F0E8; border-radius: 9px; }
QFrame#panelHeader QLabel { color: #374131; }
QFrame#panelHeader QLabel#brand { color: #334726; font-size: 17px; }
QFrame#panelHeader QLabel#workspaceName { font-size: 21px; font-weight: 700; }
QFrame#messageCard { background: #292D26; border: 1px solid #3B4135; border-radius: 9px; }
QLabel#messageAuthor { color: #C8E889; font-size: 11px; font-weight: 700; }
QLabel#welcome { color: #B6C1AA; font-size: 17px; }
QLabel#warning { color: #F0BC87; }
QFrame#requestCard { background: #353326; border: 1px solid #8B8653; border-radius: 9px; }
QFrame#imageTile { background: #1C2019; border: 1px solid #46533B; border-radius: 7px; }
QFrame#composer { background: #292F23; border: 1px solid #536342; border-radius: 10px; }
QFrame#composer QPlainTextEdit { border: 0; background: transparent; padding: 2px; }
QWidget#attachmentBody { background: #292F23; }
QWidget#requestBody, QWidget#imageBody { background: #20231F; }
QSplitter::handle { background: #343D2D; height: 3px; width: 3px; }
"""

CODEX_STATES = {"idle": "就绪", "starting": "正在提交", "running": "正在工作", "stopping": "已请求停止，等待确认",
                "completed": "本轮已完成", "interrupted": "本轮已中断", "failed": "本轮失败",
                "unknown": "本轮状态未确认", "unavailable": "不可用", "selecting": "正在打开会话"}
OP_STATES = {"queued": "排队中", "running": "执行中", "finished": "执行结束", "failed": "执行失败",
             "cancelled": "已取消", "rejected": "未执行 · 已拒绝", "unknown": "结果未知"}
BUSY_CODEX = {"starting", "running", "stopping", "unknown", "unavailable", "selecting"}


class Composer(QtWidgets.QPlainTextEdit):
    send_requested = QtCore.Signal()

    def keyPressEvent(self, event):
        if event.key() in {QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter} and event.modifiers() & QtCore.Qt.ControlModifier:
            self.send_requested.emit()
            event.accept()
        else:
            super().keyPressEvent(event)


class StudioPanel(QtWidgets.QWidget):
    def __init__(self, parent=None, *, api=None, paths=None, auto_poll=True):
        super().__init__(parent)
        self.paths = paths or AppPaths()
        self.api = api
        self.owns_api = api is None
        self.auto_poll = auto_poll
        self.closed = False
        self.state = {}
        self.bridge_connected = False
        self.logged_in = False
        self.account_known = False
        self.thread_id = None
        self.cursor = 0
        self.revision = 0
        self.hydrating = False
        self.history_again = False
        self.history_request = None
        self.history_thread = None
        self.history_events = []
        self.history_event_bytes = 0
        self.history_repairs_left = 1
        self.history_terminal_pending = False
        self.submitting = False
        self.switching = False
        self.uncertain_send = False
        self.reconciling = False
        self.login_pending = False
        self.login_url = None
        self.memory_busy = False
        self.attachments = []
        self.uploading = 0
        self.request_cards = {}
        self.receipts = {}
        self.operation_id = None
        self.detail_offset = None
        self.detail_generation = 0
        self.selection_pending = None
        self.selection_inflight = False
        self.selection_reference = None
        self.models_loaded = False
        self.setObjectName("studioPanel")
        self.setWindowTitle("Big-Chicken · Houdini Studio")
        self.setStyleSheet(PANEL_STYLE)
        self.resize(880, 960)
        self.setMinimumSize(590, 630)
        self.build_ui()
        self.poll = QtCore.QTimer(self)
        self.poll.setInterval(850)
        self.poll.timeout.connect(self.refresh)
        self.account_poll = QtCore.QTimer(self)
        self.account_poll.setInterval(8000)
        self.account_poll.timeout.connect(self.refresh_account)
        self.history_refresh = QtCore.QTimer(self)
        self.history_refresh.setSingleShot(True)
        self.history_refresh.setInterval(750)
        self.history_refresh.timeout.connect(lambda: self.load_history(automatic=True))
        self.update_controls()
        QtCore.QTimer.singleShot(0, self.connect_bridge)

    def build_ui(self):
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 14)
        root.setSpacing(11)
        header = QtWidgets.QFrame()
        header.setObjectName("panelHeader")
        top = QtWidgets.QHBoxLayout(header)
        top.setContentsMargins(19, 13, 19, 14)
        names = QtWidgets.QVBoxLayout()
        names.addWidget(label("BC /  HOUDINI STUDIO", "brand"))
        self.workspace_name = label("连接工作空间…", "workspaceName")
        names.addWidget(self.workspace_name)
        top.addLayout(names, 1)
        top.addWidget(label("想法 · 现场 · 决策"))
        root.addWidget(header)
        row = QtWidgets.QHBoxLayout()
        self.account_label = label("正在读取账号…", "muted")
        row.addWidget(self.account_label, 1)
        self.login_button = button("登录 ChatGPT", self.login, "primary")
        row.addWidget(self.login_button)
        self.refresh_button = button("刷新连接", self.reconnect)
        row.addWidget(self.refresh_button)
        root.addLayout(row)
        status_row = QtWidgets.QHBoxLayout()
        self.codex_label, self.runtime_label = label("未连接", wrap=True), label("未连接", wrap=True)
        for title, value in (("CODEX", self.codex_label), ("HOUDINI RUNTIME", self.runtime_label)):
            card = QtWidgets.QFrame()
            card.setObjectName("status")
            stack = QtWidgets.QVBoxLayout(card)
            stack.setContentsMargins(12, 9, 12, 9)
            stack.addWidget(label(title, "eyebrow"))
            stack.addWidget(value)
            status_row.addWidget(card, 1)
        root.addLayout(status_row)
        scene_row = QtWidgets.QHBoxLayout()
        self.scene_label = label("场景快照尚不可用", "muted", True)
        scene_row.addWidget(self.scene_label, 1)
        self.reconcile_button = button("校正 Codex 状态", self.reconcile, "quiet")
        scene_row.addWidget(self.reconcile_button)
        root.addLayout(scene_row)
        self.notice = label("", "warning", True)
        self.notice.hide()
        root.addWidget(self.notice)
        self.tabs = QtWidgets.QTabWidget()
        self.tabs.currentChanged.connect(self.tab_changed)
        root.addWidget(self.tabs, 1)
        self.build_conversation()
        self.build_operations()
        self.build_decisions()
        root.addWidget(label("执行记录来自 Houdini runtime  ·  对话保存在 Codex 原生会话", "eyebrow"))

    def build_conversation(self):
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(0, 2, 0, 0)
        layout.setSpacing(9)
        row = QtWidgets.QHBoxLayout()
        self.threads = QtWidgets.QComboBox()
        self.threads.setMinimumWidth(130)
        self.threads.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.threads.setPlaceholderText("选择原生会话")
        self.threads.activated.connect(self.choose_thread)
        row.addWidget(self.threads, 1)
        self.threads_refresh = button("刷新", self.load_threads, "quiet")
        row.addWidget(self.threads_refresh)
        self.new_thread = button("＋ 新对话", lambda: self.select_thread(None))
        row.addWidget(self.new_thread)
        layout.addLayout(row)
        self.transcript = Transcript(self.paths.root)
        layout.addWidget(self.transcript, 1)
        self.request_area = QtWidgets.QScrollArea()
        self.request_area.setWidgetResizable(True)
        self.request_area.setMaximumHeight(300)
        request_body = QtWidgets.QWidget()
        request_body.setObjectName("requestBody")
        self.request_layout = QtWidgets.QVBoxLayout(request_body)
        self.request_layout.setContentsMargins(0, 0, 0, 0)
        self.request_area.setWidget(request_body)
        self.request_area.hide()
        layout.addWidget(self.request_area)
        composer = QtWidgets.QFrame()
        composer.setObjectName("composer")
        controls = QtWidgets.QVBoxLayout(composer)
        controls.setContentsMargins(12, 10, 12, 10)
        controls.setSpacing(8)
        self.attachment_area = QtWidgets.QScrollArea()
        self.attachment_area.setFixedHeight(122)
        self.attachment_area.setWidgetResizable(True)
        attachment_body = QtWidgets.QWidget()
        attachment_body.setObjectName("attachmentBody")
        self.attachment_layout = QtWidgets.QHBoxLayout(attachment_body)
        self.attachment_layout.setContentsMargins(0, 0, 0, 0)
        self.attachment_layout.setAlignment(QtCore.Qt.AlignLeft)
        self.attachment_area.setWidget(attachment_body)
        self.attachment_area.hide()
        controls.addWidget(self.attachment_area)
        self.reference_label = label("", "muted", True)
        self.reference_label.hide()
        reference_row = QtWidgets.QHBoxLayout()
        reference_row.addWidget(self.reference_label, 1)
        self.reference_clear = button("清除引用", self.clear_reference, "quiet")
        self.reference_clear.hide()
        reference_row.addWidget(self.reference_clear)
        controls.addLayout(reference_row)
        self.input = Composer()
        self.input.setPlaceholderText("描述你想完成的工作。Enter 换行，Ctrl + Enter 发送。")
        self.input.setFixedHeight(78)
        self.input.textChanged.connect(self.update_controls)
        self.input.send_requested.connect(self.send)
        controls.addWidget(self.input)
        settings = QtWidgets.QHBoxLayout()
        self.models = QtWidgets.QComboBox()
        self.models.setMinimumWidth(160)
        self.models.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.models.setPlaceholderText("读取可用模型")
        self.models.currentIndexChanged.connect(self.model_changed)
        self.efforts = QtWidgets.QComboBox()
        self.efforts.setMinimumWidth(105)
        self.efforts.setToolTip("模型支持的推理档位")
        settings.addWidget(self.models, 1)
        settings.addWidget(self.efforts)
        controls.addLayout(settings)
        actions = QtWidgets.QHBoxLayout()
        self.attach_button = button("＋ 图片", self.choose_images, "quiet")
        self.selection_button = button("引用选择", self.request_selection, "quiet")
        actions.addWidget(self.attach_button)
        actions.addWidget(self.selection_button)
        actions.addStretch()
        self.stop_button = button("停止", self.stop, "stop")
        self.send_button = button("发送   ↑", self.send, "primary")
        actions.addWidget(self.stop_button)
        actions.addWidget(self.send_button)
        controls.addLayout(actions)
        layout.addWidget(composer)
        self.tabs.addTab(page, "对话")

    def build_operations(self):
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.addWidget(label("以持久化收据确认执行结果。停止 Codex 后，HOM 仍可能继续运行。", "muted", True))
        row = QtWidgets.QHBoxLayout()
        self.operation_lookup = QtWidgets.QLineEdit()
        self.operation_lookup.setPlaceholderText("按 operation_id 读取原操作")
        self.operation_lookup.returnPressed.connect(self.lookup_operation)
        row.addWidget(self.operation_lookup, 1)
        self.lookup_button = button("读取", self.lookup_operation)
        row.addWidget(self.lookup_button)
        self.operations_refresh = button("刷新记录", self.load_operations)
        row.addWidget(self.operations_refresh)
        layout.addLayout(row)
        splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        self.operation_list = QtWidgets.QListWidget()
        self.operation_list.setMinimumHeight(90)
        self.operation_list.currentItemChanged.connect(self.operation_selected)
        splitter.addWidget(self.operation_list)
        detail = QtWidgets.QWidget()
        detail_layout = QtWidgets.QVBoxLayout(detail)
        detail_layout.setContentsMargins(0, 7, 0, 0)
        self.receipt_label = label("选择一条执行记录", wrap=True)
        self.receipt_label.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        detail_layout.addWidget(self.receipt_label)
        self.operation_detail = QtWidgets.QPlainTextEdit()
        self.operation_detail.setReadOnly(True)
        self.operation_detail.setPlaceholderText("原始收据和按需读取的详细结果显示在这里。")
        detail_layout.addWidget(self.operation_detail, 1)
        actions = QtWidgets.QHBoxLayout()
        self.detail_button = button("读取详细结果", lambda: self.load_detail(0))
        self.more_detail = button("下一页", self.next_detail)
        self.cancel_operation = button("取消排队操作", self.cancel_queued, "stop")
        for control in (self.detail_button, self.more_detail, self.cancel_operation):
            control.setEnabled(False)
            actions.addWidget(control)
        actions.addStretch()
        detail_layout.addLayout(actions)
        splitter.addWidget(detail)
        splitter.setSizes([180, 400])
        layout.addWidget(splitter, 1)
        self.tabs.addTab(page, "执行记录")

    def build_decisions(self):
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.addWidget(label("留下项目的明确约定。仅在你点击保存时写入，可独立于 Houdini 使用。", "muted", True))
        self.decisions = QtWidgets.QListWidget()
        self.decisions.currentItemChanged.connect(self.decision_selected)
        layout.addWidget(self.decisions, 1)
        self.decision_input = QtWidgets.QPlainTextEdit()
        self.decision_input.setPlaceholderText("例如：场景以米为单位；最终输出放在工作空间的 renders 目录。")
        self.decision_input.setMaximumHeight(150)
        self.decision_input.textChanged.connect(self.update_controls)
        layout.addWidget(self.decision_input)
        row = QtWidgets.QHBoxLayout()
        self.decision_refresh = button("刷新", self.load_decisions)
        self.decision_save = button("保存新决策", lambda: self.save_decision(False), "primary")
        self.decision_replace = button("替代所选", lambda: self.save_decision(True))
        self.decision_delete = button("删除所选", self.delete_decision)
        for control in (self.decision_refresh, self.decision_save, self.decision_replace, self.decision_delete):
            row.addWidget(control)
        row.addStretch()
        layout.addLayout(row)
        self.tabs.addTab(page, "项目决策")

    def show_notice(self, message):
        self.notice.setText(str(message)[:1500])
        self.notice.setVisible(bool(message))

    def call(self, method, path, body=None, done=None, failed=None, unique=False):
        if self.closed or not self.api:
            return False
        return self.api.call(method, path, body, done=done, failed=failed or self.show_notice, unique=unique)

    def connect_bridge(self):
        if self.closed:
            return
        if self.api is None:
            try:
                session_id = os.environ.get("BCS_SESSION_ID", "")
                token = os.environ.get("BCS_SESSION_TOKEN", "")
                if not session_id or not token:
                    raise ValueError("请从 Studio Launcher 启动 Houdini，再打开此 Panel。")
                descriptor = read_json(self.paths.session(session_id) / "bridge.json")
                if descriptor.get("launcher_session_id") != session_id:
                    raise ValueError("Bridge 会话身份不匹配。请重新打开当前工作空间。")
                self.api = Api(descriptor["url"], token, self)
            except (OSError, ValueError, KeyError, StudioError) as exc:
                self.account_label.setText("工作空间尚未连接")
                self.show_notice(str(exc))
                self.update_controls()
                return
        self.refresh()
        self.refresh_account()
        if self.auto_poll:
            self.poll.start()
            self.account_poll.start()

    def reconnect(self):
        self.show_notice("")
        self.connect_bridge()
        if self.bridge_connected:
            self.load_history()
            if self.logged_in:
                self.load_threads()
                self.load_models()

    def refresh(self):
        revision = self.revision
        self.call("GET", "/state", done=lambda v: self.apply_state(v) if revision == self.revision else None,
                  failed=self.connection_failed, unique=True)
        if not self.hydrating:
            event_thread = self.thread_id
            self.call("GET", "/events?after=" + str(self.cursor),
                      done=lambda v: self.apply_events(v) if self.thread_id == event_thread else None, unique=True)
        if self.tabs.currentIndex() == 1:
            self.load_operations()
        if self.selection_pending:
            operation_id = self.selection_pending
            self.call("GET", "/operations/" + operation_id,
                      done=lambda v: self.selection_receipt(v) if self.selection_pending == operation_id else None,
                      failed=lambda message: self.selection_failed("选择读取未确认，可按 ID " + operation_id + " 查询：" + message), unique=True)

    def connection_failed(self, message):
        self.bridge_connected = False
        self.codex_label.setText("连接中断 · 状态未确认")
        self.runtime_label.setText("连接中断 · 执行结果未确认")
        self.show_notice(message)
        self.update_controls()

    def apply_state(self, value):
        recovered = not self.bridge_connected
        self.bridge_connected = True
        self.state = value
        workspace = value.get("workspace", {})
        self.workspace_name.setText(workspace.get("name", "工作空间"))
        self.workspace_name.setToolTip(str(workspace.get("workspace_id", "")))
        codex = value.get("codex", {})
        native = codex.get("state", "unknown")
        self.codex_label.setText(CODEX_STATES.get(native, native) if codex.get("alive") else "App Server 不可用 · 状态未确认")
        self.codex_label.setToolTip("原生状态：" + native + "\n停止请求：" + str(bool(codex.get("stop_requested"))))
        runtime = value.get("runtime", {})
        if runtime.get("connection") != "connected":
            self.runtime_label.setText("未连接 · 执行结果未确认")
        elif runtime.get("storage_fault"):
            self.runtime_label.setText("收据存储异常 · 结果未确认")
        elif runtime.get("active_operation_id"):
            self.runtime_label.setText("正在执行  ·  队列 " + str(runtime.get("queue_depth", "?")))
        elif runtime.get("main_thread_busy"):
            self.runtime_label.setText("主线程正在运行  ·  队列 " + str(runtime.get("queue_depth", "?")))
        elif runtime.get("queue_depth", 0) > 0:
            self.runtime_label.setText("等待主线程  ·  队列 " + str(runtime["queue_depth"]))
        else:
            self.runtime_label.setText("已连接 · 当前队列空闲")
        self.runtime_label.setToolTip(str(runtime.get("active_operation_id") or runtime.get("message") or ""))
        scene = runtime.get("scene") or {}
        path = scene.get("hip_path")
        self.scene_label.setText((Path(path).name + "  ·  帧 " + str(scene.get("frame", "?")) +
                                 ("  ·  有未保存修改" if scene.get("dirty") else "") + "  ·  最近快照") if path else "场景快照尚不可用")
        self.scene_label.setToolTip(json.dumps(scene, ensure_ascii=False, indent=2))
        if not self.switching and value.get("thread_id") != self.thread_id:
            self.thread_id = value.get("thread_id")
            self.transcript.reset(self.thread_id)
            self.selection_reference = None
            self.load_history()
            if self.logged_in:
                self.load_threads()
        elif recovered and self.thread_id:
            self.load_history()
        self.sync_requests(value.get("pending_requests", []))
        if self.selection_reference and scene.get("scene_epoch") != self.selection_reference.get("scene_epoch"):
            self.reference_label.setText("引用来自较早场景；发送前请重新引用当前选择。")
        self.update_controls()

    def update_controls(self):
        if not hasattr(self, "decision_save"):
            return
        codex = self.state.get("codex", {})
        runtime = self.state.get("runtime", {})
        idle = codex.get("state", "unknown") not in BUSY_CODEX and bool(codex.get("alive"))
        account = self.bridge_connected and self.logged_in
        ready = account and idle and not self.switching and not self.submitting and not self.uncertain_send and not self.reconciling
        scene_ready = runtime.get("connection") == "connected" and not runtime.get("storage_fault")
        self.login_button.setVisible(not self.logged_in)
        self.login_button.setEnabled(self.bridge_connected and (not self.login_pending or self.login_url is not None))
        self.new_thread.setEnabled(ready)
        self.threads.setEnabled(ready)
        self.threads_refresh.setEnabled(account and not self.switching)
        self.input.setEnabled(account and not self.submitting)
        self.models.setEnabled(ready and self.models_loaded)
        self.efforts.setEnabled(ready and self.efforts.count() > 0)
        text_ok = 0 < len(self.input.toPlainText().strip()) <= 64000
        reference_ok = not self.selection_reference or self.selection_reference.get("scene_epoch") == runtime.get("scene", {}).get("scene_epoch")
        self.send_button.setEnabled(ready and bool(self.thread_id) and text_ok and not self.uploading and not self.selection_pending
                                    and not self.selection_inflight and reference_ok)
        self.attach_button.setEnabled(account and not self.submitting and len(self.attachments) + self.uploading < 8)
        self.selection_button.setEnabled(ready and scene_ready and not self.selection_pending and not self.selection_inflight)
        self.reference_clear.setVisible(bool(self.selection_reference))
        self.reference_clear.setEnabled(not self.submitting)
        self.stop_button.setEnabled(self.bridge_connected and (codex.get("state") in {"running", "starting", "stopping", "unknown"}
                                                              or bool(runtime.get("main_thread_busy")) or runtime.get("queue_depth", 0) > 0))
        self.reconcile_button.setEnabled(self.bridge_connected and bool(self.thread_id) and not self.switching
                                         and not self.submitting and not self.reconciling)
        for control in (self.decision_refresh, self.operations_refresh, self.lookup_button):
            control.setEnabled(self.bridge_connected)
        has_text = 0 < len(self.decision_input.toPlainText().strip()) <= 12000
        has_record = bool(self.decisions.currentItem() and self.decisions.currentItem().data(QtCore.Qt.UserRole))
        self.decision_save.setEnabled(self.bridge_connected and has_text and not self.memory_busy)
        self.decision_replace.setEnabled(self.bridge_connected and has_text and has_record and not self.memory_busy)
        self.decision_delete.setEnabled(self.bridge_connected and has_record and not self.memory_busy)

    def refresh_account(self):
        self.call("GET", "/account", done=self.apply_account, failed=self.account_failed, unique=True)

    def account_failed(self, message):
        self.account_known = False
        self.logged_in = False
        self.account_label.setText("账号状态未确认 · " + str(message)[:70])
        self.update_controls()

    def apply_account(self, value):
        before = self.logged_in
        account = value.get("account")
        self.logged_in = isinstance(account, dict) and bool(account)
        self.account_known = True
        if self.logged_in:
            self.login_pending = False
            self.login_url = None
            self.login_button.setText("登录 ChatGPT")
            self.account_label.setText(str(account.get("email") or account.get("type") or "已登录") +
                                       ("  ·  " + str(account["planType"]) if account.get("planType") else ""))
            if not before:
                self.load_threads()
                self.load_models()
                self.load_history()
        else:
            self.account_label.setText("登录 ChatGPT 后即可开始对话" if not self.login_pending else "请在浏览器完成登录")
        self.update_controls()

    def login(self):
        if not self.login_button.isEnabled():
            return
        if self.login_pending and self.login_url:
            QtGui.QDesktopServices.openUrl(self.login_url)
            return
        self.login_pending = True
        self.login_button.setText("等待登录…")
        self.update_controls()

        def opened(value):
            url = QtCore.QUrl(value.get("authUrl", ""))
            if url.scheme() != "https" or not url.host():
                self.login_failed("未收到有效的 ChatGPT 登录链接。")
                return
            if not QtGui.QDesktopServices.openUrl(url):
                self.login_failed("无法打开系统浏览器，请检查默认浏览器设置。")
                return
            self.login_url = url
            self.login_button.setText("重新打开登录")
            self.account_label.setText("请在浏览器完成登录，Panel 会自动刷新账号。")
            self.update_controls()
        self.call("POST", "/account/login", {}, done=opened, failed=self.login_failed)

    def login_failed(self, message):
        self.login_pending = False
        self.login_url = None
        self.login_button.setText("登录 ChatGPT")
        self.show_notice(message)
        self.update_controls()

    def load_models(self):
        if self.logged_in:
            self.call("GET", "/models", done=self.apply_models, unique=True)

    def apply_models(self, value):
        selected = self.models.currentData()
        selected_id = selected.get("id") if isinstance(selected, dict) else None
        self.models.blockSignals(True)
        self.models.clear()
        default = 0
        for model in value.get("data", []):
            if model.get("hidden"):
                continue
            self.models.addItem(model.get("displayName") or model.get("model") or model.get("id", ""), model)
            if model.get("id") == selected_id or not selected_id and model.get("isDefault"):
                default = self.models.count() - 1
        self.models.setCurrentIndex(default)
        self.models.blockSignals(False)
        self.models_loaded = self.models.count() > 0
        self.model_changed()
        self.update_controls()

    def model_changed(self, _index=None):
        self.efforts.clear()
        model = self.models.currentData() or {}
        for item in model.get("supportedReasoningEfforts", []):
            if isinstance(item, dict):
                effort = item.get("reasoningEffort")
                self.efforts.addItem(str(effort), effort)
                self.efforts.setItemData(self.efforts.count() - 1, item.get("description", ""), QtCore.Qt.ToolTipRole)
        default = self.efforts.findData(model.get("defaultReasoningEffort"))
        if default >= 0:
            self.efforts.setCurrentIndex(default)
        self.update_controls()

    def load_threads(self):
        if self.logged_in:
            self.call("GET", "/threads", done=self.apply_threads, unique=True)

    def apply_threads(self, value):
        self.threads.blockSignals(True)
        self.threads.clear()
        for thread in value.get("data", []):
            title = thread.get("name") or thread.get("preview") or "未命名对话"
            self.threads.addItem(str(title).replace("\n", " ")[:90], thread["id"])
            self.threads.setItemData(self.threads.count() - 1, str(title), QtCore.Qt.ToolTipRole)
        index = self.threads.findData(self.thread_id)
        if self.thread_id and index < 0:
            self.threads.addItem("当前对话", self.thread_id)
            index = self.threads.count() - 1
        self.threads.setCurrentIndex(index)
        self.threads.blockSignals(False)

    def choose_thread(self, index):
        thread_id = self.threads.itemData(index)
        if thread_id and thread_id != self.thread_id:
            self.select_thread(thread_id)

    def select_thread(self, thread_id):
        if not self.new_thread.isEnabled():
            return
        self.switching = True
        self.revision += 1
        self.update_controls()
        self.call("POST", "/threads/select", {"thread_id": thread_id} if thread_id else {},
                  done=self.thread_selected, failed=self.thread_failed)

    def thread_selected(self, value):
        self.switching = False
        self.revision += 1
        self.thread_id = value.get("thread", {}).get("id")
        self.uncertain_send = False
        self.selection_reference = None
        self.reference_label.hide()
        self.transcript.hydrate(value.get("thread"))
        self.load_history()
        self.load_threads()
        self.refresh()

    def thread_failed(self, message):
        self.switching = False
        self.revision += 1
        self.show_notice(message)
        self.load_threads()
        self.refresh()
        self.update_controls()

    def load_history(self, *, automatic=False):
        if not self.thread_id or not self.logged_in:
            return
        if self.hydrating and self.history_thread == self.thread_id:
            self.history_again = True
            return
        if not automatic:
            # One repair per explicit read/reconnect, never a full-history polling
            # loop for each delta in an active snapshot. Turn completion is separate.
            self.history_repairs_left = 1
        thread_id = self.thread_id
        request = object()
        self.history_request, self.history_thread = request, thread_id
        self.history_events, self.history_event_bytes = [], 0
        self.history_again = False
        self.history_terminal_pending = False
        self.history_refresh.stop()
        self.hydrating = True

        def loaded(value):
            if self.history_request is not request or self.thread_id != thread_id or self.closed:
                return
            self.hydrating = False
            thread = value.get("thread")
            if value.get("history_available") is False:
                # Native Codex may not have materialized a new thread's rollout.
                # Metadata-only reads are not evidence that existing items vanished.
                if self.thread_id == thread_id:
                    self.show_notice(value.get("history_message", "会话历史尚未物化，可继续当前对话。"))
            elif self.thread_id == thread_id and thread and thread.get("id") == thread_id:
                self.transcript.hydrate(thread)
            buffered, self.history_events = self.history_events, []
            self.history_event_bytes = 0
            for event in buffered:
                if self.transcript.apply_event(event):
                    self.history_again = True
            repair, terminal = self.history_again, self.history_terminal_pending
            self.history_again = self.history_terminal_pending = False
            if repair or terminal:
                self.schedule_history(terminal=terminal)

        def failed(message):
            if self.history_request is not request or self.thread_id != thread_id or self.closed:
                return
            self.hydrating = False
            self.history_again = False
            buffered, self.history_events = self.history_events, []
            self.history_event_bytes = 0
            for event in buffered:
                self.transcript.apply_event(event)
            self.show_notice("原生历史读取失败：" + str(message))
            terminal, self.history_terminal_pending = self.history_terminal_pending, False
            self.schedule_history(terminal=terminal)
        self.call("GET", "/thread", done=loaded, failed=failed)

    def schedule_history(self, *, terminal=False):
        if self.closed or self.history_refresh.isActive():
            return
        if not terminal:
            if self.history_repairs_left <= 0:
                return
            self.history_repairs_left -= 1
        self.history_refresh.start()

    def apply_events(self, value):
        if value.get("resync_required") or value.get("cursor", self.cursor) < self.cursor:
            self.load_history()
        previous_cursor = self.cursor
        self.cursor = value.get("cursor", self.cursor)
        for event in value.get("events", []):
            if event.get("sequence", previous_cursor + 1) <= previous_cursor:
                continue
            params = event.get("params", {})
            method = event.get("method", "")
            if method in {"account/updated", "account/login/completed"}:
                if method == "account/login/completed" and params.get("success") is False:
                    self.login_failed(params.get("error") or "登录未完成，请重试。")
                self.refresh_account()
            if params.get("threadId") != self.thread_id:
                continue
            if self.hydrating:
                size = len(json.dumps(event, ensure_ascii=False).encode("utf-8"))
                if len(self.history_events) < 256 and self.history_event_bytes + size <= 512 * 1024:
                    self.history_events.append(event)
                    self.history_event_bytes += size
                else:
                    self.history_again = True  # Native history recovers bounded buffer overflow.
                    self.show_notice("部分历史事件超出临时缓冲；本轮结束时会读取完整内容，也可手动刷新连接。")
            elif self.transcript.apply_event(event):
                self.schedule_history()
            if method == "turn/completed":
                if self.hydrating:
                    self.history_terminal_pending = True
                else:
                    self.schedule_history(terminal=True)
            if method in {"error", "warning"}:
                error = params.get("error") or {}
                self.show_notice(error.get("message") or params.get("message") or method)

    def send(self):
        if not self.send_button.isEnabled():
            return
        text = self.input.toPlainText().strip()
        if self.selection_reference:
            reference = self.selection_reference
            text += "\n\n用户引用的选择（scene_epoch=" + str(reference["scene_epoch"]) + "）：\n" + "\n".join(reference["nodes"])
        if len(text) > 64000:
            self.show_notice("消息含选择引用后超过 64000 字符，请缩短后发送。")
            return
        body = {"text": text, "attachments": [item["attachment_id"] for item in self.attachments]}
        model = self.models.currentData() or {}
        if model.get("model") or model.get("id"):
            body["model"] = model.get("model") or model["id"]
        if self.efforts.currentData():
            body["effort"] = self.efforts.currentData()
        self.submitting = True
        self.revision += 1
        self.update_controls()
        self.show_notice("")
        self.call("POST", "/turn", body, done=self.sent, failed=self.send_failed)

    def sent(self, value):
        self.submitting = False
        self.revision += 1
        native_status = value.get("turn", {}).get("status", "inProgress")
        self.state["codex"] = {**self.state.get("codex", {}),
                               "state": "running" if native_status == "inProgress" else native_status}
        self.input.clear()
        self.attachments.clear()
        self.render_attachments()
        self.selection_reference = None
        self.reference_label.hide()
        for item in value.get("turn", {}).get("items", []):
            self.transcript.put(item)
        self.refresh()
        self.update_controls()

    def send_failed(self, message):
        self.submitting = False
        self.uncertain_send = getattr(message, "submission_state", None) != "not_submitted"
        self.revision += 1
        prefix = ("提交未确认，输入已保留。请先校正 Codex 状态，查看原生历史。\n" if self.uncertain_send else
                  "提交被拒绝，输入已保留。修正后可以再次发送。\n")
        self.show_notice(prefix + str(message))
        self.refresh()
        self.update_controls()

    def stop(self):
        if not self.stop_button.isEnabled():
            return
        self.stop_button.setEnabled(False)
        self.revision += 1
        self.call("POST", "/stop", {}, done=self.stopped, failed=self.stop_failed)

    def stopped(self, value):
        self.revision += 1
        error = value.get("codex_interrupt_error")
        scene = value.get("scene", {})
        message = "已发送停止请求。Codex 终态与 Houdini 执行结果将分别确认。"
        if error:
            message += "\nCodex 中断未确认：" + str(error)
        if scene.get("confirmed") is False:
            message += "\nHoudini 停止后续操作未确认：" + str(scene.get("message", ""))
        self.show_notice(message)
        self.refresh()

    def stop_failed(self, message):
        self.revision += 1
        self.show_notice("停止请求未确认：" + message)
        self.refresh()

    def reconcile(self):
        if not self.reconcile_button.isEnabled():
            return
        self.reconciling = True
        self.revision += 1
        self.update_controls()
        self.call("POST", "/reconcile", {}, done=self.reconciled, failed=self.reconcile_failed, unique=True)

    def reconciled(self, value):
        self.reconciling = False
        self.revision += 1
        if value.get("reconciled"):
            self.uncertain_send = False
            if value.get("codex_state"):
                self.state["codex"] = {**self.state.get("codex", {}), "state": value["codex_state"]}
            if value.get("history_available") is not False:
                self.history_repairs_left = 1
                self.transcript.hydrate(value.get("thread"))
            self.show_notice("已读取 Codex 原生状态；Houdini 结果以执行记录为准。")
        else:
            self.show_notice(value.get("message", "没有可校正的会话。"))
        self.refresh()

    def reconcile_failed(self, message):
        self.reconciling = False
        self.revision += 1
        self.show_notice(message)
        self.refresh()
        self.update_controls()

    def choose_images(self):
        paths, _ = QtWidgets.QFileDialog.getOpenFileNames(self, "添加参考图片", "", "图片 (*.png *.jpg *.jpeg *.webp)")
        self.add_images(paths)

    def add_images(self, paths):
        room = 8 - len(self.attachments) - self.uploading
        if len(paths) > room:
            self.show_notice("每次最多添加 8 张图片。")
        for path in paths[:room]:
            self.uploading += 1
            self.call("POST", "/attachments", {"path": str(path)}, done=self.attached, failed=self.attach_failed)
        self.update_controls()

    def attached(self, value):
        self.uploading = max(0, self.uploading - 1)
        self.attachments.append(value)
        self.render_attachments()
        self.update_controls()

    def attach_failed(self, message):
        self.uploading = max(0, self.uploading - 1)
        self.show_notice(message)
        self.update_controls()

    def render_attachments(self):
        clear_layout(self.attachment_layout)
        for item in self.attachments:
            tile = ImageTile({"path": item["path"]}, item["name"], removable=True, compact=True)
            tile.removed.connect(lambda attachment_id=item["attachment_id"]: self.remove_attachment(attachment_id))
            self.attachment_layout.addWidget(tile)
        self.attachment_area.setVisible(bool(self.attachments))

    def remove_attachment(self, attachment_id):
        if self.submitting:
            return
        self.attachments = [item for item in self.attachments if item["attachment_id"] != attachment_id]
        self.render_attachments()
        self.update_controls()

    def request_selection(self):
        if not self.selection_button.isEnabled():
            return
        self.selection_inflight = True
        self.update_controls()
        self.call("POST", "/selection", {}, done=self.selection_received, failed=self.selection_failed)

    def selection_received(self, value):
        self.selection_inflight = False
        if value.get("nodes") is not None:
            self.set_selection(value)
        elif value.get("operation_id"):
            self.selection_pending = value["operation_id"]
            self.show_notice("当前选择正在队列中读取…")
        else:
            self.selection_failed("选择接口没有返回可用结果。")
        self.update_controls()

    def selection_receipt(self, value):
        if value.get("state") == "finished":
            self.selection_pending = None
            result = value.get("result") or {}
            self.set_selection({"nodes": result.get("selected", []), "scene_epoch": result.get("scene_epoch")})
        elif value.get("state") not in {"queued", "running"}:
            self.selection_pending = None
            self.selection_failed((value.get("error") or {}).get("message", "选择读取没有完成。"))

    def set_selection(self, value):
        self.selection_pending = None
        self.selection_reference = value if value.get("nodes") and value.get("scene_epoch") else None
        self.reference_label.setText("引用选择  ·  " + "，".join(value.get("nodes", [])))
        self.reference_label.setVisible(bool(self.selection_reference))
        self.show_notice("" if self.selection_reference else "当前没有选中的节点。")
        self.update_controls()

    def selection_failed(self, message):
        self.selection_inflight = False
        self.selection_pending = None
        self.show_notice(message)
        self.update_controls()

    def clear_reference(self):
        self.selection_reference = None
        self.reference_label.hide()
        self.update_controls()

    def sync_requests(self, requests):
        current = {str(r["request_id"]): r for r in requests
                   if r.get("params", {}).get("threadId") == self.thread_id}
        for key in list(self.request_cards):
            if key not in current:
                card = self.request_cards.pop(key)
                self.request_layout.removeWidget(card)
                card.deleteLater()
        for key, request in current.items():
            if key not in self.request_cards:
                card = RequestCard(request)
                card.respond.connect(self.respond_request)
                self.request_cards[key] = card
                self.request_layout.addWidget(card)
        self.request_area.setVisible(bool(current))
        self.tabs.setTabText(0, "对话" + ("  ·  待回应 " + str(len(current)) if current else ""))

    def respond_request(self, request_id, result):
        card = self.request_cards.get(str(request_id))
        self.call("POST", "/requests/respond", {"request_id": request_id, "result": result},
                  done=lambda _: self.refresh(), failed=lambda message: card.failed(message) if str(request_id) in self.request_cards else None)

    def tab_changed(self, index):
        if index == 1:
            self.load_operations()
        elif index == 2:
            self.load_decisions()

    def load_operations(self):
        self.call("GET", "/operations", done=self.apply_operations, unique=True)

    def apply_operations(self, value):
        operations = value.get("operations", [])
        self.operation_list.blockSignals(True)
        self.operation_list.clear()
        for receipt in operations:
            operation_id = receipt["operation_id"]
            self.receipts[operation_id] = receipt
            item = QtWidgets.QListWidgetItem(OP_STATES.get(receipt.get("state"), str(receipt.get("state"))) +
                                            "   /   " + receipt.get("label", receipt.get("kind", "操作")) +
                                            "\n" + operation_id)
            item.setData(QtCore.Qt.UserRole, operation_id)
            self.operation_list.addItem(item)
            if operation_id == self.operation_id:
                self.operation_list.setCurrentItem(item)
                self.show_receipt(receipt, replace=False)
        if not operations:
            item = QtWidgets.QListWidgetItem("还没有执行记录。场景操作接纳后，runtime 会在这里提供收据。")
            item.setFlags(QtCore.Qt.NoItemFlags)
            self.operation_list.addItem(item)
        self.operation_list.blockSignals(False)

    def operation_selected(self, current, _previous=None):
        if current and current.data(QtCore.Qt.UserRole):
            self.read_operation(current.data(QtCore.Qt.UserRole))

    def lookup_operation(self):
        operation_id = self.operation_lookup.text().strip()
        if operation_id:
            self.read_operation(operation_id)

    def read_operation(self, operation_id):
        from ..common import identifier
        try:
            identifier(operation_id)
        except StudioError as exc:
            self.show_notice(exc.message)
            return
        self.operation_id = operation_id
        self.detail_generation += 1
        self.detail_offset = None
        self.more_detail.setEnabled(False)
        self.detail_button.setEnabled(False)
        self.cancel_operation.setEnabled(False)
        self.receipt_label.setText("正在读取操作 " + operation_id)
        self.operation_detail.clear()
        self.call("GET", "/operations/" + operation_id,
                  done=lambda v: self.show_receipt(v) if self.operation_id == operation_id else None)

    def show_receipt(self, receipt, replace=True):
        if receipt.get("operation_id") != self.operation_id:
            return
        self.receipts[self.operation_id] = receipt
        self.receipt_label.setText(OP_STATES.get(receipt.get("state"), str(receipt.get("state"))) + "  ·  " + self.operation_id +
                                  "\n场景修改：" + str(receipt.get("mutation_outcome", "unknown")) +
                                  "   /   检查：" + str(receipt.get("checks_outcome", "not_run")))
        if replace:
            self.operation_detail.setPlainText(json.dumps(receipt, ensure_ascii=False, indent=2))
        self.detail_button.setEnabled(bool(receipt.get("result_ref")))
        self.cancel_operation.setEnabled(receipt.get("state") == "queued" and self.bridge_connected)

    def load_detail(self, offset):
        if not self.operation_id:
            return
        operation_id, generation = self.operation_id, self.detail_generation
        self.detail_button.setEnabled(False)
        self.more_detail.setEnabled(False)

        def loaded(value):
            if generation != self.detail_generation or operation_id != self.operation_id:
                return
            self.detail_button.setEnabled(True)
            if not value.get("available"):
                self.operation_detail.setPlainText("详细结果尚未持久化。")
                return
            # Each page is independently readable; never replay a scene operation.
            self.operation_detail.setPlainText(value.get("text", ""))
            self.detail_offset = value.get("next_offset")
            self.more_detail.setEnabled(self.detail_offset is not None)
            self.more_detail.setToolTip("字符 " + str(value.get("offset", offset)) + " / " + str(value.get("total_characters", "?")))
        self.call("GET", "/operations/" + operation_id + "/detail?offset=" + str(offset), done=loaded)

    def next_detail(self):
        if self.detail_offset is not None:
            self.load_detail(self.detail_offset)

    def cancel_queued(self):
        receipt = self.receipts.get(self.operation_id, {})
        if receipt.get("state") != "queued":
            return
        operation_id = self.operation_id
        self.cancel_operation.setEnabled(False)

        def cancelled(value):
            if operation_id == self.operation_id:
                self.show_receipt(value)
            if value.get("state") == "running":
                self.show_notice("操作已进入 HOM。已请求取消后续边界，当前执行仍需等待收据。")
            self.load_operations()
        self.call("POST", "/operations/" + operation_id + "/cancel", {}, done=cancelled)

    def load_decisions(self):
        self.call("POST", "/memory", {"action": "list"}, done=self.apply_decisions, unique=True)

    def apply_decisions(self, value):
        selected = self.decisions.currentItem()
        selected_id = selected.data(QtCore.Qt.UserRole)["id"] if selected and selected.data(QtCore.Qt.UserRole) else None
        self.decisions.blockSignals(True)
        self.decisions.clear()
        for record in value.get("records", []):
            item = QtWidgets.QListWidgetItem(record["body"])
            item.setData(QtCore.Qt.UserRole, record)
            self.decisions.addItem(item)
            if record["id"] == selected_id:
                self.decisions.setCurrentItem(item)
        if not value.get("records"):
            item = QtWidgets.QListWidgetItem("这个工作空间还没有保存项目决策。")
            item.setFlags(QtCore.Qt.NoItemFlags)
            self.decisions.addItem(item)
        self.decisions.blockSignals(False)
        self.update_controls()

    def decision_selected(self, current, _previous=None):
        if current and current.data(QtCore.Qt.UserRole):
            self.decision_input.setPlainText(current.data(QtCore.Qt.UserRole)["body"])
        self.update_controls()

    def save_decision(self, replace):
        if self.memory_busy:
            return
        text = self.decision_input.toPlainText().strip()
        if not text:
            return
        body = {"action": "supersede" if replace else "record", "body": text}
        if replace:
            item = self.decisions.currentItem()
            if not item or not item.data(QtCore.Qt.UserRole):
                return
            body["record_id"] = item.data(QtCore.Qt.UserRole)["id"]
        self.memory_busy = True
        self.update_controls()

        def saved(value):
            self.memory_busy = False
            if value.get("committed"):
                self.decision_input.clear()
                self.show_notice("项目决策已保存。")
            self.load_decisions()
        self.call("POST", "/memory", body, done=saved, failed=self.memory_failed)

    def memory_failed(self, message):
        self.memory_busy = False
        self.show_notice(message)
        self.update_controls()

    def delete_decision(self):
        item = self.decisions.currentItem()
        if not item or not item.data(QtCore.Qt.UserRole):
            return
        record_id = item.data(QtCore.Qt.UserRole)["id"]
        # A focused confirmation protects an explicitly stored project decision.
        result = QtWidgets.QMessageBox.question(self, "删除项目决策", "将删除所选的项目决策。", QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                                               QtWidgets.QMessageBox.No)
        if result == QtWidgets.QMessageBox.Yes:
            self.call("POST", "/memory", {"action": "delete", "record_id": record_id},
                      done=lambda _: self.load_decisions())

    def closeEvent(self, event):
        self.closed = True
        self.poll.stop()
        self.account_poll.stop()
        self.history_refresh.stop()
        if self.owns_api and self.api:
            self.api.close()
        super().closeEvent(event)
