"""Big-Chicken Studio Panel: a projection of Codex and runtime facts."""
from __future__ import annotations

import json
import os
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from ..common import AppPaths, StudioError, new_id, read_json
from .conversation import ImageTile, Transcript
from .icons import icon_diagnostics, set_button_icon
from .model_settings import ChoiceBox, ModelSettings
from .requests import RequestCard, SessionTrustControl
from .shared import Api, ErrorDetails, button, label
from .theme import COLORS, apply_theme, studio_stylesheet


PANEL_STYLE = studio_stylesheet("studioPanel") + f"""
QWidget#studioPanel QLabel#workspaceName {{ font-size: 12pt; font-weight: 600; }}
QWidget#studioPanel QLabel#workStatus {{ font-weight: 600; }}
QWidget#studioPanel QLabel#messageAuthor {{ color: {COLORS['text_secondary']}; font-size: 9.5pt; font-weight: 600; }}
QWidget#studioPanel QLabel#warning {{ color: {COLORS['warning']}; }}
QWidget#studioPanel QToolButton::menu-indicator {{ image: none; }}
"""

CODEX_STATES = {"idle": "就绪", "starting": "正在提交", "running": "正在工作", "stopping": "已请求停止，等待确认",
                "completed": "本轮已完成", "interrupted": "本轮已中断", "failed": "本轮失败",
                "unknown": "本轮状态未确认", "unavailable": "不可用", "selecting": "正在打开会话"}
OP_STATES = {"queued": "排队中", "running": "执行中", "finished": "执行结束", "failed": "执行失败",
             "cancelled": "已取消", "rejected": "未执行 · 已拒绝", "unknown": "结果未知"}
BUSY_CODEX = {"starting", "running", "stopping", "unknown", "unavailable", "selecting"}


class Composer(QtWidgets.QTextEdit):
    """Keep Qt's native text/IME path; only images leave the plain-text editor."""
    send_requested = QtCore.Signal()
    image_pasted = QtCore.Signal(object)
    image_paths_pasted = QtCore.Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        # Small adaptation of HIA's ExpandableTextEdit: no keyboard or IME overrides.
        self.setAcceptRichText(False)
        self.height_limit = 160
        self.setMinimumHeight(64)
        self.setMaximumHeight(160)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        self._send_shortcuts = []
        for sequence in ("Ctrl+Return", "Ctrl+Enter"):
            shortcut = QtGui.QShortcut(QtGui.QKeySequence(sequence), self)
            shortcut.setContext(QtCore.Qt.WidgetShortcut)
            shortcut.setAutoRepeat(False)
            shortcut.activated.connect(self.send_requested.emit)
            self._send_shortcuts.append(shortcut)
        # QTextEdit forwards changes from whichever native document is active.
        self.textChanged.connect(self.update_height)
        self.update_height()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_height()

    def update_height(self):
        height = max(64, min(self.height_limit, int(self.document().size().height()) + 14))
        if self.maximumHeight() != height:
            self.setMaximumHeight(height)
            self.updateGeometry()

    def canInsertFromMimeData(self, source):
        return source.hasImage() or bool(self.local_image_paths(source)) or super().canInsertFromMimeData(source)

    @staticmethod
    def local_image_paths(source):
        return [url.toLocalFile() for url in source.urls() if url.isLocalFile()
                and Path(url.toLocalFile()).suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}]

    def insertFromMimeData(self, source):
        if source.hasImage():
            self.image_pasted.emit(source.imageData())
            return  # Mixed clipboard formats must not insert text a second time.
        paths = self.local_image_paths(source)
        if paths:
            self.image_paths_pasted.emit(paths)
            return
        super().insertFromMimeData(source)


class StudioPanel(QtWidgets.QWidget):
    def __init__(self, parent=None, *, api=None, paths=None, auto_poll=True, image_roots=None):
        super().__init__(parent)
        self.paths = paths or AppPaths()
        self.api = api
        self.owns_api = api is None
        self.auto_poll = auto_poll
        self.preview_image_roots = tuple(Path(path).resolve() for path in image_roots) if image_roots is not None else None
        self.closed = False
        self.state = {}
        self.bridge_connected = False
        self.logged_in = False
        self.account_known = False
        self.thread_id = None
        self.draft_key = None
        self.drafts = {}
        self.selection_generation = 0
        self.observed_scene_epoch = None
        self.confirmed_new_thread = None
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
        self.pending_submission = None
        self.stop_pending = False
        self.switching = False
        self.uncertain_send = False
        self.reconciling = False
        self.login_pending = False
        self.login_url = None
        self.memory_busy = False
        self.attachments = []
        self.attachment_tiles = {}
        self.uploading = 0
        self.operation_summary_key = None
        self.observed_operations = set()
        self.observed_turn = None
        self.request_cards = {}
        self.receipts = {}
        self.operation_id = None
        self.detail_offset = None
        self.detail_generation = 0
        self.selection_pending = None
        self.selection_inflight = False
        self.selection_reference = None
        self.models_loaded = False
        self.models_request = None
        self.account_revision = None
        self.connected_api = None
        self.narrow_layout = None
        self.setObjectName("studioPanel")
        self.setWindowTitle("Big-Chicken · Houdini Studio")
        self.setStyleSheet(PANEL_STYLE)
        self.resize(720, 900)
        self.setMinimumSize(280, 420)
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
        self.root_layout = root
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)
        header = QtWidgets.QFrame()
        header.setObjectName("panelHeader")
        top = QtWidgets.QHBoxLayout(header)
        top.setContentsMargins(0, 0, 0, 0)
        self.workspace_name = label("等待场景信息…", "workspaceName")
        self.workspace_name.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Preferred)
        top.addWidget(self.workspace_name, 1)
        self.conversation_button = button("返回对话", lambda: self.tabs.setCurrentIndex(0))
        set_button_icon(self.conversation_button, "arrow-left", text="返回对话", fallback_text="返回", icon_only=True)
        self.conversation_button.setFixedSize(32, 32)
        self.conversation_button.hide()
        top.addWidget(self.conversation_button)
        self.new_thread = button("新对话", lambda: self.select_thread(None), "quiet")
        set_button_icon(self.new_thread, "square-pen", text="新对话", fallback_text="新建", icon_only=True)
        self.new_thread.setFixedSize(32, 32)
        top.addWidget(self.new_thread)
        self.menu_button = QtWidgets.QToolButton()
        self.menu_button.setText("更多")
        self.menu_button.setFixedSize(32, 32)
        set_button_icon(self.menu_button, "ellipsis", text="更多", icon_only=True)
        self.menu_button.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        menu = QtWidgets.QMenu(self.menu_button)
        menu.setObjectName("studioPanelMenu")
        apply_theme(menu, popup=True)
        menu.addAction("设置与连接详情", self.toggle_settings)
        menu.addAction("执行详情", lambda: self.tabs.setCurrentIndex(1))
        menu.addAction("项目约定", lambda: self.tabs.setCurrentIndex(2))
        self.menu_button.setMenu(menu)
        top.addWidget(self.menu_button)
        root.addWidget(header)
        self.threads = ChoiceBox()
        self.threads.setMinimumWidth(0)
        self.threads.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.threads.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.threads.setPlaceholderText("选择对话")
        self.threads.activated.connect(self.choose_thread)
        root.addWidget(self.threads)
        self.scene_context_note = label("", "warning", True)
        self.scene_context_note.hide()
        root.addWidget(self.scene_context_note)
        self.login_area = QtWidgets.QWidget()
        row = QtWidgets.QHBoxLayout(self.login_area)
        row.setContentsMargins(0, 0, 0, 0)
        self.account_label = label("正在读取账号…", "muted", True)
        row.addWidget(self.account_label, 1)
        self.login_button = button("登录 ChatGPT", self.login, "primary")
        row.addWidget(self.login_button)
        root.addWidget(self.login_area)
        self.model_controls = ModelSettings()
        self.models, self.efforts = self.model_controls.models, self.model_controls.efforts
        self.model_controls.changed.connect(self.update_controls)
        self.settings_area = QtWidgets.QFrame()
        self.settings_area.setObjectName("status")
        self.settings_layout = QtWidgets.QVBoxLayout(self.settings_area)
        self.settings_layout.setContentsMargins(10, 8, 10, 8)
        self.settings_layout.addWidget(label("设置与连接详情", "eyebrow"))
        self.account_detail = label("", "muted", True)
        self.settings_layout.addWidget(self.account_detail)
        detail_row = QtWidgets.QHBoxLayout()
        self.refresh_button = button("刷新连接", self.reconnect)
        detail_row.addWidget(self.refresh_button)
        self.threads_refresh = button("刷新会话列表", self.load_threads, "quiet")
        detail_row.addWidget(self.threads_refresh)
        detail_row.addStretch()
        self.settings_layout.addLayout(detail_row)
        self.codex_label, self.runtime_label = label("未连接", wrap=True), label("未连接", wrap=True)
        for title, value in (("CODEX", self.codex_label), ("HOUDINI RUNTIME", self.runtime_label)):
            self.settings_layout.addWidget(label(title, "eyebrow"))
            self.settings_layout.addWidget(value)
        self.scene_label = label("场景快照尚不可用", "muted", True)
        self.settings_layout.addWidget(self.scene_label)
        self.settings_layout.addWidget(label("长操作占用 Houdini 主线程时，停止按钮可能延迟响应；执行结果以收据为准。", "muted", True))
        self.settings_area.hide()
        self.error_details = ErrorDetails()
        self.notice = self.error_details.summary
        self.settings_layout.addWidget(self.error_details)
        self.presentation_notice = ""
        self.tabs = QtWidgets.QTabWidget()
        self.tabs.tabBar().hide()
        self.tabs.currentChanged.connect(self.tab_changed)
        root.addWidget(self.tabs, 1)
        self.build_conversation()
        self.build_operations()
        self.build_decisions()
        self.settings_layout.addStretch()
        self.tabs.addTab(self.settings_area, "设置与连接详情")
        self.settings_layout.insertWidget(self.settings_layout.count() - 1, self.runtime_status)
        root.addWidget(self.status_bar)

    def toggle_settings(self):
        self.tabs.setCurrentIndex(0 if self.tabs.currentIndex() == 3 else 3)

    def build_conversation(self):
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(0, 2, 0, 0)
        layout.setSpacing(8)
        self.transcript = Transcript(self.paths.root, image_roots=self.preview_image_roots or ())
        layout.addWidget(self.transcript, 1)
        self.session_trust = SessionTrustControl(self.api)
        self.session_trust.changed.connect(self.refresh)
        self.request_area = QtWidgets.QScrollArea()
        self.request_area.setWidgetResizable(True)
        self.request_area.setMaximumHeight(int(self.height() * 0.3))
        self.request_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        request_body = QtWidgets.QWidget()
        request_body.setObjectName("requestBody")
        self.request_layout = QtWidgets.QVBoxLayout(request_body)
        self.request_layout.setContentsMargins(0, 0, 0, 0)
        self.request_area.setWidget(request_body)
        request_body.setAutoFillBackground(False)
        self.request_area.viewport().setAutoFillBackground(False)
        self.request_area.hide()
        layout.addWidget(self.request_area)
        self.status_bar = QtWidgets.QWidget()
        status_row = QtWidgets.QBoxLayout(QtWidgets.QBoxLayout.LeftToRight, self.status_bar)
        status_row.setContentsMargins(0, 0, 0, 0)
        self.status_layout = status_row
        self.work_status = label("连接 Studio 后即可发送；现在可以先写草稿。", "workStatus", True)
        status_row.addWidget(self.work_status, 1)
        self.reconcile_button = button("查询上次提交", self.reconcile, "quiet")
        status_row.addWidget(self.reconcile_button)
        self.reconnect_button = button("重新连接", self.reconnect, "quiet")
        status_row.addWidget(self.reconnect_button)
        self.runtime_status = label("", "warning", True)
        self.pending_button = button("查看未确认的原消息", self.toggle_pending_submission, "quiet")
        self.pending_button.hide()
        layout.addWidget(self.pending_button, 0, QtCore.Qt.AlignLeft)
        self.pending_preview = QtWidgets.QPlainTextEdit()
        self.pending_preview.setReadOnly(True)
        self.pending_preview.setMaximumHeight(120)
        self.pending_preview.hide()
        layout.addWidget(self.pending_preview)
        composer = self.composer = QtWidgets.QFrame()
        composer.setObjectName("composer")
        controls = QtWidgets.QVBoxLayout(composer)
        controls.setContentsMargins(8, 8, 8, 8)
        controls.setSpacing(8)
        self.attachment_area = QtWidgets.QScrollArea()
        self.attachment_area.setFixedHeight(72)
        self.attachment_area.setWidgetResizable(True)
        self.attachment_area.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        attachment_body = QtWidgets.QWidget()
        attachment_body.setObjectName("attachmentBody")
        self.attachment_layout = QtWidgets.QHBoxLayout(attachment_body)
        self.attachment_layout.setContentsMargins(0, 0, 0, 0)
        self.attachment_layout.setAlignment(QtCore.Qt.AlignLeft)
        self.attachment_area.setWidget(attachment_body)
        attachment_body.setAutoFillBackground(False)
        self.attachment_area.viewport().setAutoFillBackground(False)
        self.attachment_area.hide()
        controls.addWidget(self.attachment_area)
        self.reference_label = QtWidgets.QToolButton()
        self.reference_label.setProperty("studioRole", "quiet")
        self.reference_label.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self.reference_label.setCheckable(True)
        self.reference_label.setMinimumHeight(32)
        self.reference_label.clicked.connect(self.toggle_reference)
        self.reference_label.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        self.reference_label.hide()
        reference_row = QtWidgets.QHBoxLayout()
        reference_row.addWidget(self.reference_label, 1)
        self.reference_clear = button("清除引用", self.clear_reference, "quiet")
        self.reference_clear.setFixedSize(32, 32)
        set_button_icon(self.reference_clear, "x", text="清除引用", fallback_text="清除", icon_only=True)
        self.reference_clear.hide()
        reference_row.addWidget(self.reference_clear)
        controls.addLayout(reference_row)
        self.reference_paths = QtWidgets.QPlainTextEdit()
        self.reference_paths.setReadOnly(True)
        self.reference_paths.setMaximumHeight(72)
        self.reference_paths.hide()
        controls.addWidget(self.reference_paths)
        self.input = Composer()
        self.input.setPlaceholderText("描述你想完成的工作。Enter 换行，Ctrl + Enter 发送。")
        self.input.textChanged.connect(self.update_controls)
        self.input.send_requested.connect(self.send)
        self.input.image_pasted.connect(self.add_clipboard_image)
        self.input.image_paths_pasted.connect(self.add_images)
        controls.addWidget(self.input)
        self.input.document().setParent(self)
        self.save_draft()
        self.composer_action_layout = QtWidgets.QGridLayout()
        self.composer_action_layout.setContentsMargins(0, 0, 0, 0)
        self.composer_action_layout.setSpacing(4)
        secondary = self.context_actions = QtWidgets.QWidget()
        actions = QtWidgets.QHBoxLayout(secondary)
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(4)
        self.attach_button = button("图片", self.choose_images, "quiet")
        self.selection_button = button("引用选择", self.request_selection, "quiet")
        for control, name, text in ((self.attach_button, "paperclip", "添加图片"),
                                     (self.selection_button, "mouse-pointer-2", "引用选择")):
            set_button_icon(control, name, text=text, fallback_text="附件" if control is self.attach_button else "选择", icon_only=True)
            control.setFixedSize(32, 32)
        actions.addWidget(self.attach_button)
        actions.addWidget(self.selection_button)
        self.retry_attachments = button("添加待传", self.upload_attachments, "quiet")
        self.retry_attachments.setToolTip("将保留的图片添加到当前对话")
        self.retry_attachments.hide()
        actions.addWidget(self.retry_attachments)
        actions.addStretch()
        self.action_slot = QtWidgets.QStackedWidget()
        self.action_slot.setFixedSize(36, 36)
        self.stop_button = button("停止后续工作", self.stop, "stop")
        self.stop_button.setToolTip("请求停止后续工作；长操作占用主线程时，按钮可能延迟响应。")
        self.send_button = button("发送", self.send, "primary")
        for control, name, text, color in ((self.send_button, "arrow-up", "发送", COLORS["on_primary"]),
                                           (self.stop_button, "square", "停止后续工作", COLORS["background"])):
            control.setFixedSize(36, 36)
            set_button_icon(control, name, text=text, fallback_text="发送" if control is self.send_button else "停止", color=color, icon_only=True)
            self.action_slot.addWidget(control)
        self.action_slot.setCurrentWidget(self.send_button)
        controls.addLayout(self.composer_action_layout)
        layout.addWidget(composer)
        footer = QtWidgets.QHBoxLayout()
        self.shortcut_hint = label("Enter 换行 · Ctrl+Enter 发送", "eyebrow")
        footer.addWidget(self.shortcut_hint, 1)
        footer.addWidget(self.session_trust)
        layout.addLayout(footer)
        self.arrange_composer()
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
        self.tabs.addTab(page, "执行详情")

    def build_decisions(self):
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.addWidget(label("留下项目的明确约定。仅在你点击保存时写入，可独立于 Houdini 使用。", "muted", True))
        self.decisions = QtWidgets.QListWidget()
        self.decisions.currentItemChanged.connect(self.decision_selected)
        layout.addWidget(self.decisions, 1)
        self.decision_input = QtWidgets.QPlainTextEdit()
        self.decision_input.setPlaceholderText("例如：场景以米为单位。")
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
        self.tabs.addTab(page, "项目约定")

    def show_notice(self, message, *, failure=None):
        self.presentation_notice = str(message).splitlines()[0] if message else ""
        if not message:
            self.error_details.set_failure(None)
            if hasattr(self, "work_status"):
                self.update_work_status()
            return
        self.error_details.set_failure(failure if failure is not None else message)
        summary = str(message).splitlines()[0]
        self.notice.setText(summary[:180] + ("…" if len(summary) > 180 else ""))
        self.notice.setProperty("tone", "error" if getattr(failure or message, "code", None) else "notice")
        self.notice.style().unpolish(self.notice)
        self.notice.style().polish(self.notice)
        if hasattr(self, "work_status"):
            self.update_work_status()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not hasattr(self, "composer_action_layout"):
            return
        self.arrange_composer()

    def arrange_composer(self):
        narrow = self.width() < 440
        margin = 8 if narrow else 12
        self.root_layout.setContentsMargins(margin, margin, margin, margin)
        self.request_area.setMaximumHeight(max(80, int(self.height() * 0.3)))
        self.input.height_limit = 96 if self.height() < 620 else 160
        self.input.update_height()
        self.attachment_area.setFixedHeight(56 if self.height() < 620 else 72)
        for tile in self.attachment_tiles.values():
            tile.caption.setVisible(self.height() >= 620)
        self.shortcut_hint.setVisible(self.height() >= 620)
        if narrow != self.narrow_layout:
            self.narrow_layout = narrow
            for widget in (self.context_actions, self.model_controls, self.action_slot):
                self.composer_action_layout.removeWidget(widget)
            if narrow:
                self.composer_action_layout.addWidget(self.model_controls, 0, 0, 1, 3)
                self.composer_action_layout.addWidget(self.context_actions, 1, 0, 1, 2)
                self.composer_action_layout.addWidget(self.action_slot, 1, 2)
            else:
                self.composer_action_layout.addWidget(self.context_actions, 0, 0)
                self.composer_action_layout.addWidget(self.model_controls, 0, 1, QtCore.Qt.AlignRight)
                self.composer_action_layout.addWidget(self.action_slot, 0, 2)
            self.composer_action_layout.setColumnStretch(0, 1 if narrow else 0)
            self.composer_action_layout.setColumnStretch(1, 0 if narrow else 1)
            self.status_layout.setDirection(QtWidgets.QBoxLayout.TopToBottom if narrow else QtWidgets.QBoxLayout.LeftToRight)

    def save_draft(self):
        if not hasattr(self, "input"):
            return
        document = self.input.document()
        document.setParent(self)  # QTextEdit must not delete a parked thread's document.
        self.drafts[self.draft_key] = {"document": document, "cursor": QtGui.QTextCursor(self.input.textCursor()),
                                       "attachments": self.attachments, "selection": self.selection_reference}

    def activate_draft(self, thread_id):
        if self.draft_key == thread_id:
            return
        self.save_draft()
        previous = self.drafts[self.draft_key]
        if thread_id not in self.drafts:
            if self.draft_key is None:
                self.drafts[thread_id] = previous
                self.drafts.pop(None)
            else:
                document = QtGui.QTextDocument(self)
                document.setDefaultFont(self.input.font())
                self.drafts[thread_id] = {"document": document, "cursor": QtGui.QTextCursor(document),
                                           "attachments": [], "selection": None}
        self.draft_key = thread_id
        draft = self.drafts[thread_id]
        self.input.blockSignals(True)
        self.input.setDocument(draft["document"])
        self.input.setTextCursor(QtGui.QTextCursor(draft["cursor"]))
        self.input.blockSignals(False)
        self.input.update_height()
        self.attachments = draft["attachments"]
        self.selection_reference = draft["selection"]
        self.selection_generation += 1
        self.selection_pending = None
        self.selection_inflight = False
        self.render_attachments()
        self.render_reference()

    def call(self, method, path, body=None, done=None, failed=None, unique=False):
        if self.closed or not self.api:
            return False
        api = self.api
        failure = failed or self.show_notice
        return api.call(method, path, body,
                        done=lambda value: done(value) if done and not self.closed and api is self.api else None,
                        failed=lambda value: failure(value) if not self.closed and api is self.api else None,
                        unique=unique)

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
                    raise ValueError("Studio 会话身份不匹配，请检查当前连接。")
                self.api = Api(descriptor["url"], token, self)
            except (OSError, ValueError, KeyError, StudioError) as exc:
                self.account_label.setText("Studio 尚未连接")
                self.show_notice(str(exc))
                self.update_controls()
                return
        if self.connected_api is not self.api:
            self.connected_api = self.api
            self.models_request = None
            self.account_revision = None
            self.model_controls.set_account_revision(None)
            self.model_controls.reset_connection()
            self.history_request = None
            self.hydrating = False
            self.history_refresh.stop()
            self.switching = self.reconciling = False
            if self.submitting:
                self.submitting = False
                self.uncertain_send = True
                self.show_notice("连接已更换；上次提交尚未确认，请查询上次提交。")
            self.revision += 1
        self.session_trust.set_api(self.api)
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
                  failed=lambda message: self.connection_failed(message) if revision == self.revision else None,
                  unique=True)
        if not self.hydrating:
            event_thread = self.thread_id
            self.call("GET", "/events?after=" + str(self.cursor),
                      done=lambda v: self.apply_events(v) if self.thread_id == event_thread and revision == self.revision else None,
                      unique=True)
        if self.tabs.currentIndex() == 1:
            self.load_operations()
        if self.selection_pending:
            operation_id = self.selection_pending
            self.call("GET", "/operations/" + operation_id,
                      done=lambda v: self.selection_receipt(v) if self.selection_pending == operation_id else None,
                      failed=lambda message: self.selection_failed("选择读取未确认，可按 ID " + operation_id + " 查询：" + message)
                      if self.selection_pending == operation_id else None, unique=True)

    def connection_failed(self, message):
        self.bridge_connected = False
        self.codex_label.setText("连接中断 · 状态未确认")
        self.runtime_label.setText("连接中断 · 执行结果未确认")
        self.show_notice(message)
        self.update_controls()

    def apply_state(self, value):
        if self.closed or (type(value.get("account_revision")) is int and self.account_revision is not None
                           and value["account_revision"] < self.account_revision):
            return
        recovered = not self.bridge_connected
        self.bridge_connected = True
        self.state = value
        workspace_id = (value.get("workspace") or {}).get("workspace_id")
        if self.preview_image_roots is None and workspace_id:
            workspace = self.paths.workspace(workspace_id)
            self.transcript.set_image_roots((workspace / "attachments", workspace / "artifacts"))
        self.session_trust.apply_state(value)
        account_changed = self.accept_account_revision(value.get("account_revision"))
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
        epoch = scene.get("scene_epoch")
        if epoch is not None and self.observed_scene_epoch not in {None, epoch}:
            self.selection_generation += 1
            self.selection_pending = None
            self.selection_inflight = False
        if epoch is not None:
            self.observed_scene_epoch = epoch
        path = scene.get("hip_path")
        name = scene.get("display_name")
        if not name:
            name = "未保存场景" if scene.get("is_new_file") is True else "场景身份尚未确认"
        self.workspace_name.setText(name + (" · 已修改" if scene.get("dirty") else ""))
        self.workspace_name.setToolTip(str(path or "") if runtime.get("connection") == "connected" else "Houdini 连接未确认")
        self.scene_label.setText((Path(path).name + "  ·  帧 " + str(scene.get("frame", "?")) +
                                 ("  ·  有未保存修改" if scene.get("dirty") else "") + "  ·  最近快照") if path else "场景快照尚不可用")
        self.scene_label.setToolTip(json.dumps({"scene": scene, "scene_context": value.get("scene_context"),
                                               "icons": icon_diagnostics()},
                                              ensure_ascii=False, indent=2))
        if not self.switching and value.get("thread_id") != self.thread_id:
            self.thread_id = value.get("thread_id")
            self.activate_draft(self.thread_id)
            self.model_controls.set_thread(self.thread_id)
            self.transcript.reset(self.thread_id)
            self.load_history()
            if self.logged_in:
                self.load_threads()
        elif recovered and self.thread_id:
            self.load_history()
        self.model_controls.apply_native(value.get("thread_settings"))
        context = value.get("scene_context") or {}
        source_epoch, current_epoch = context.get("scene_epoch"), context.get("current_scene_epoch")
        changed_scene = bool(context.get("thread_id") == self.thread_id and source_epoch and current_epoch
                             and source_epoch != current_epoch)
        self.scene_context_note.setText("此对话来自之前的场景；请确认旧约定是否适用，或新建对话。" if changed_scene else "")
        self.scene_context_note.setVisible(changed_scene)
        self.sync_requests(value.get("pending_requests", []))
        self.render_reference()
        observed_turn = (value.get("thread_id"), value.get("turn_id"))
        if self.observed_turn and (observed_turn[0] != self.observed_turn[0]
                                   or observed_turn[1] and observed_turn != self.observed_turn):
            self.observed_operations.clear()
        if observed_turn[1] or not self.observed_turn or observed_turn[0] != self.observed_turn[0]:
            self.observed_turn = observed_turn
        active = runtime.get("active_operation_id")
        if active:
            self.observed_operations.add(active)
        summary_key = (value.get("thread_id"), value.get("turn_id"), native, active,
                       runtime.get("main_thread_busy"), runtime.get("queue_depth"), runtime.get("connection"))
        if summary_key != self.operation_summary_key:
            self.operation_summary_key = summary_key
            if runtime.get("connection") == "connected":
                self.load_operations()
        self.update_controls()
        if account_changed:
            self.account_known = self.logged_in = False
            self.update_controls()
            self.refresh_account()

    def update_controls(self):
        if not hasattr(self, "decision_save"):
            return
        codex = self.state.get("codex", {})
        runtime = self.state.get("runtime", {})
        idle = codex.get("state", "unknown") not in BUSY_CODEX and bool(codex.get("alive"))
        account = self.bridge_connected and self.logged_in
        response_unknown = any(card.response_unknown for card in self.request_cards.values())
        ready = (account and idle and not self.switching and not self.submitting and not self.uncertain_send
                 and not self.reconciling and not response_unknown)
        scene_ready = runtime.get("connection") == "connected" and not runtime.get("storage_fault")
        self.uploading = sum(item.get("status") == "uploading" for item in self.attachments)
        self.models_loaded = self.model_controls.catalog_loaded and bool(self.model_controls.catalog)
        self.login_button.setVisible(not self.logged_in)
        self.login_area.setVisible(self.bridge_connected and not self.logged_in)
        self.account_detail.setText(self.account_label.text())
        self.login_button.setEnabled(self.bridge_connected and (not self.login_pending or self.login_url is not None))
        self.new_thread.setEnabled(ready)
        self.threads.setEnabled(ready)
        self.threads_refresh.setEnabled(account and not self.switching)
        # Local editing is independent from account, connection and turn state.
        self.input.setEnabled(True)
        text_ok = 0 < len(self.input.toPlainText().strip()) <= 64000
        reference_ok = not self.selection_reference or self.selection_reference.get("scene_epoch") == runtime.get("scene", {}).get("scene_epoch")
        self.send_button.setEnabled(ready and bool(self.thread_id) and text_ok and not self.uploading and not self.selection_pending
                                    and not self.selection_inflight and reference_ok and not runtime.get("storage_fault")
                                    and self.model_controls.request_settings() is not None)
        self.attach_button.setEnabled(len(self.attachments) < 8)
        waiting_images = any(item.get("status") in {"waiting", "failed"} for item in self.attachments)
        self.retry_attachments.setVisible(waiting_images)
        self.retry_attachments.setEnabled(self.bridge_connected)
        if any(item.get("status") in {"waiting", "failed", "uploading"} for item in self.attachments):
            self.send_button.setEnabled(False)
        model = self.model_controls.catalog.get(self.model_controls.next_model, {})
        image_mismatch = bool(self.attachments and "image" not in model.get("inputModalities", ["text", "image"]))
        self.model_controls.set_constraint("当前模型不接收图片；请选择其他模型或移除图片。" if image_mismatch else "")
        if image_mismatch:
            self.send_button.setEnabled(False)
        self.selection_button.setEnabled(ready and scene_ready and not self.selection_pending and not self.selection_inflight)
        self.reference_clear.setVisible(bool(self.selection_reference))
        self.reference_clear.setEnabled(True)
        working = (codex.get("state") in {"running", "starting", "stopping", "unknown"}
                   or bool(runtime.get("main_thread_busy")) or bool(runtime.get("active_operation_id"))
                   or runtime.get("queue_depth", 0) > 0 or self.submitting)
        self.send_button.setEnabled(self.send_button.isEnabled() and not working)
        self.action_slot.setCurrentWidget(self.stop_button if working or self.stop_pending else self.send_button)
        self.stop_button.setEnabled(self.bridge_connected and working and not self.stop_pending)
        self.stop_button.setToolTip("停止请求已发送" if self.stop_pending else "停止后续工作")
        self.model_controls.set_interactive(ready and self.models_loaded and not working)
        self.model_controls.apply_turn(self.state.get("turn_settings"), active=working, turn_id=self.state.get("turn_id"))
        self.reconcile_button.setEnabled(self.bridge_connected and bool(self.thread_id) and not self.switching
                                         and not self.submitting and not self.reconciling)
        self.reconcile_button.setVisible(self.uncertain_send or response_unknown
                                         or codex.get("state") in {"unknown", "unavailable"})
        self.reconnect_button.setVisible(not self.bridge_connected)
        self.pending_button.setVisible(self.uncertain_send and self.pending_submission is not None)
        self.update_work_status()
        for control in (self.decision_refresh, self.operations_refresh, self.lookup_button):
            control.setEnabled(self.bridge_connected)
        has_text = 0 < len(self.decision_input.toPlainText().strip()) <= 12000
        has_record = bool(self.decisions.currentItem() and self.decisions.currentItem().data(QtCore.Qt.UserRole))
        self.decision_save.setEnabled(self.bridge_connected and has_text and not self.memory_busy)
        self.decision_replace.setEnabled(self.bridge_connected and has_text and has_record and not self.memory_busy)
        self.decision_delete.setEnabled(self.bridge_connected and has_record and not self.memory_busy)

    def update_work_status(self):
        codex, runtime = self.state.get("codex", {}), self.state.get("runtime", {})
        native = codex.get("state", "unknown")
        if self.uncertain_send:
            text = "上次提交结果未确认。可继续写草稿，请先查询提交状态。"
        elif any(card.response_unknown for card in self.request_cards.values()):
            text = ""  # The approval card owns this error; the query action remains available.
        elif self.stop_pending or codex.get("stop_requested") and native in {"running", "starting", "stopping"}:
            text = "已请求停止后续工作，等待确认。"
        elif not self.bridge_connected:
            text = "连接未就绪；草稿可继续编辑。"
        elif self.submitting:
            text = "正在提交消息；可以继续写下一段草稿。"
        elif self.request_cards:
            text = "需要你的回应，完成后继续。"
        elif self.selection_pending or self.selection_inflight:
            text = "正在读取当前选择…"
        elif not codex.get("alive"):
            text = "对话服务不可用；草稿已保留。"
        elif native in {"starting", "running", "stopping", "unknown", "failed", "interrupted"}:
            text = {"failed": "本轮对话失败，请查看对话中的原因。", "interrupted": "本轮对话已中断。"}.get(native, CODEX_STATES[native])
        elif not self.logged_in:
            text = ""  # Account feedback stays beside the sign-in action.
        elif not self.thread_id:
            text = "新建或选择对话后即可发送。"
        else:
            text = "可以继续描述下一步。" if native == "completed" else "准备好了。"
        turn_fact = False
        if not self.bridge_connected or runtime.get("connection") != "connected":
            fact = "Houdini 连接未确认，场景修改结果尚未确认。"
        elif runtime.get("storage_fault"):
            fact = "Houdini 执行记录存储异常，修改结果尚未确认。"
        elif runtime.get("main_thread_busy") or runtime.get("active_operation_id"):
            fact = "Houdini 仍在执行，请等待当前操作结束。"
        elif runtime.get("queue_depth", 0):
            fact = "Houdini 还有操作在排队，等待执行。"
        elif any(r.get("state") == "unknown" or r.get("receipt_confirmed") is False
                 or r.get("mutation_outcome") == "unknown" and r.get("state") in {"finished", "failed"}
                 for r in self.receipts.values()):
            fact = "仍有结果未确认的 Houdini 操作；请查看执行详情。"
        elif any(self.receipts.get(key, {}).get("state") in {None, "queued", "running"}
                 for key in self.observed_operations):
            fact = "Houdini 队列已空闲，上次操作的结果仍待确认。"
        elif any(self.receipts[key].get("mutation_outcome") == "partial" for key in self.observed_operations):
            fact = "本轮 Houdini 操作留下了部分修改；请查看执行详情后继续。"
            turn_fact = True
        elif any(self.receipts[key].get("checks_outcome") == "failed" for key in self.observed_operations):
            fact = "本轮 Houdini 操作的检查发现问题；请查看执行详情。"
            turn_fact = True
        elif any(self.receipts[key].get("state") in {"failed", "rejected"} for key in self.observed_operations):
            fact = "本轮有 Houdini 操作失败或被拒绝；请查看执行详情。"
            turn_fact = True
        else:
            fact = ""
        self.runtime_status.setText(fact)
        self.runtime_status.setVisible(bool(fact))
        placed = self.transcript.set_turn_notice(self.state.get("turn_id"), fact if turn_fact else text if native == "failed" else "")
        if fact and not placed:
            prefix = text + " " if self.stop_pending or native in {"interrupted", "stopping"} else ""
            primary = prefix + fact
        elif placed:
            primary = "" if native == "failed" else text
        elif self.uncertain_send or self.request_cards:
            primary = text
        else:
            primary = self.presentation_notice or text
        self.work_status.setText(primary)
        self.work_status.setVisible(bool(primary))

    def toggle_pending_submission(self):
        if self.pending_submission:
            snapshot = self.pending_submission
            names = "、".join(item["name"] for item in snapshot["attachments"])
            self.pending_preview.setPlainText(snapshot["request_text"] + ("\n\n保留的图片：" + names if names else ""))
            self.pending_preview.setVisible(self.pending_preview.isHidden())

    def refresh_account(self):
        revision, api = self.account_revision, self.api
        self.call("GET", "/account", done=self.apply_account,
                  failed=lambda message: self.account_failed(message) if api is self.api and revision == self.account_revision else None,
                  unique=True)

    def accept_account_revision(self, revision):
        if type(revision) is not int or revision == self.account_revision:
            return False
        if self.account_revision is not None and revision < self.account_revision:
            return False
        self.account_revision = revision
        self.model_controls.set_account_revision(revision)
        return True

    def account_failed(self, message):
        self.account_known = False
        self.logged_in = False
        self.account_label.setText("账号状态未确认 · " + str(message)[:70])
        self.show_notice("暂时无法确认账号，请刷新连接。", failure=message)
        self.update_controls()

    def apply_account(self, value):
        revision = value.get("account_revision")
        if type(revision) is int and self.account_revision is not None and revision < self.account_revision:
            return
        changed = self.accept_account_revision(revision)
        before = self.logged_in
        account = value.get("account")
        status = value.get("status")
        self.logged_in = isinstance(account, dict) and (status == "signed_in" if status is not None else bool(account))
        self.account_known = status != "unknown"
        if self.logged_in:
            self.login_pending = False
            self.login_url = None
            self.login_button.setText("登录 ChatGPT")
            self.account_label.setText(str(account.get("email") or account.get("type") or "已登录") +
                                       ("  ·  " + str(account["planType"]) if account.get("planType") else ""))
            if not before or changed:
                self.load_threads()
                self.load_models()
                self.load_history()
        else:
            self.account_label.setText("请在浏览器完成登录" if self.login_pending else
                                       "账号状态尚未确认，请刷新连接。" if status == "unknown" else
                                       "请在 Launcher 中检查当前认证方式。" if status == "other" else
                                       "登录 ChatGPT 后即可开始对话")
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
        if not self.logged_in or self.models_request is not None:
            return
        request, api, account = object(), self.api, self.account_revision
        self.models_request = request

        def finished(value=None, failure=None):
            if self.closed or self.models_request is not request:
                return
            self.models_request = None
            if api is not self.api:
                return
            if account != self.account_revision:
                self.load_models()
                return
            if failure is not None:
                self.show_notice("暂时无法读取模型列表，请在连接详情重新检查。", failure=failure)
            else:
                self.apply_models(value)
        if not self.call("GET", "/models", done=lambda value: finished(value),
                         failed=lambda message: finished(failure=message), unique=True):
            self.models_request = None

    def apply_models(self, value):
        self.model_controls.apply_catalog(value)
        self.update_controls()

    def model_changed(self, _index=None):
        self.model_controls.model_changed(_index)

    def load_threads(self):
        if self.logged_in:
            account = self.account_revision
            self.call("GET", "/threads", done=lambda value: self.apply_threads(value)
                      if account == self.account_revision else None, unique=True)

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
                  done=lambda value: self.thread_selected(value, created=thread_id is None), failed=self.thread_failed)

    def thread_selected(self, value, *, created=False):
        self.switching = False
        self.revision += 1
        self.thread_id = value.get("thread", {}).get("id")
        self.activate_draft(self.thread_id)
        self.model_controls.set_thread(self.thread_id)
        self.model_controls.apply_native(value.get("thread_settings"), restore=True)
        # A successful explicit creation establishes an empty starting boundary;
        # a metadata-only read of an existing conversation does not.
        self.confirmed_new_thread = self.thread_id if created and not value.get("thread", {}).get("turns") else None
        self.uncertain_send = False
        self.render_reference()
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
        settings = self.model_controls.request_settings()
        if settings is None or settings["expected_thread_id"] != self.thread_id:
            return
        text = self.input.toPlainText().strip()
        if self.selection_reference:
            reference = self.selection_reference
            text += "\n\n用户引用的选择（scene_epoch=" + str(reference["scene_epoch"]) + "）：\n" + "\n".join(reference["nodes"])
        if len(text) > 64000:
            self.show_notice("消息含选择引用后超过 64000 字符，请缩短后发送。")
            return
        body = {"text": text, "attachments": [item["attachment_id"] for item in self.attachments]}
        body.update(settings)
        self.save_draft()
        self.submitting = True
        self.pending_submission = {"thread_id": self.thread_id, "text": self.input.toPlainText(),
                                   "document_revision": self.input.document().revision(), "request_text": text,
                                   "attachments": [dict(item) for item in self.attachments],
                                   "selection": self.selection_reference,
                                   "seen_items": set(self.transcript.cards),
                                   "history_known": (self.transcript.history_known and not self.hydrating
                                                     or self.confirmed_new_thread == self.thread_id
                                                     and self.transcript.last_turn_id is None),
                                   "last_turn_id": self.transcript.last_turn_id}
        self.pending_submission.update(draft_key=self.draft_key, draft=self.drafts[self.draft_key],
                                       settings=dict(settings), previous_turn_settings=self.state.get("turn_settings"),
                                       previous_turn_id=self.state.get("turn_id"))
        self.state["turn_id"] = None
        self.state["turn_settings"] = {"thread_id": self.thread_id, "turn_id": None,
                                       "requested_model": settings["model"], "requested_effort": settings.get("effort"),
                                       "model": settings["model"], "effort": settings.get("effort"),
                                       "confirmation": "requested", "from_model": None, "reason": None}
        self.revision += 1
        self.update_controls()
        self.show_notice("")
        if not self.call("POST", "/turn", body, done=self.sent, failed=self.send_failed):
            self.submitting = False
            self.state["turn_settings"] = self.pending_submission.get("previous_turn_settings")
            self.state["turn_id"] = self.pending_submission.get("previous_turn_id")
            self.pending_submission = None
            self.show_notice("连接尚未就绪，消息未发出。草稿已保留。")
            self.update_controls()

    def sent(self, value):
        if self.closed:
            return
        if not (value.get("turn") or {}).get("id"):
            self.send_failed("提交响应缺少原生消息轮次；请查询提交状态。")
            return
        self.submitting = False
        self.revision += 1
        native_status = value.get("turn", {}).get("status", "inProgress")
        self.state["codex"] = {**self.state.get("codex", {}),
                               "state": "running" if native_status == "inProgress" else native_status}
        self.state["turn_id"] = value["turn"]["id"]
        if value.get("turn_settings"):
            self.state["turn_settings"] = value["turn_settings"]
        self.accept_submission()
        for item in value.get("turn", {}).get("items", []):
            self.transcript.put(item)
        self.refresh()
        self.update_controls()

    def accept_submission(self):
        snapshot = self.pending_submission
        if snapshot and snapshot.get("draft_key") == self.draft_key:
            self.save_draft()
        draft = self.drafts.get(snapshot.get("draft_key"), snapshot.get("draft")) if snapshot else None
        if draft and (draft["document"].revision() == snapshot["document_revision"]
                      and draft["document"].toPlainText() == snapshot["text"]
                      and draft["attachments"] == snapshot["attachments"]
                      and draft["selection"] == snapshot["selection"]):
            # One deliberate edit after acknowledgement; native undo remains available.
            cursor = QtGui.QTextCursor(draft["document"])
            cursor.beginEditBlock()
            cursor.select(QtGui.QTextCursor.Document)
            cursor.removeSelectedText()
            cursor.endEditBlock()
            draft["attachments"].clear()
            draft["selection"] = None
            if snapshot.get("draft_key") == self.draft_key:
                self.selection_reference = None
                self.render_attachments()
                self.render_reference()
        elif snapshot:
            self.show_notice("消息已确认提交；等待期间编辑的草稿已保留。")
        self.pending_submission = None
        self.confirmed_new_thread = None
        self.uncertain_send = False
        self.pending_preview.hide()

    def send_failed(self, message):
        self.submitting = False
        self.uncertain_send = getattr(message, "submission_state", None) != "not_submitted"
        if not self.uncertain_send:
            if self.pending_submission:
                self.state["turn_settings"] = self.pending_submission.get("previous_turn_settings")
                self.state["turn_id"] = self.pending_submission.get("previous_turn_id")
            self.pending_submission = None
        self.revision += 1
        prefix = ("提交未确认，原消息和图片已保留。请查询提交状态，避免重复发送。\n" if self.uncertain_send else
                  "提交被拒绝，输入已保留。修正后可以再次发送。\n")
        self.show_notice(prefix + str(message), failure=message)
        self.refresh()
        self.update_controls()
        if self.uncertain_send:
            self.reconcile()  # One read after loss; never submit again or loop over history.

    def stop(self):
        if not self.stop_button.isEnabled():
            return
        self.stop_pending = True
        self.revision += 1
        self.show_notice("正在请求停止后续工作；Houdini 当前操作仍需单独确认。")
        self.update_controls()
        self.call("POST", "/stop", {}, done=self.stopped, failed=self.stop_failed)

    def stopped(self, value):
        self.stop_pending = False
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
        self.update_controls()

    def stop_failed(self, message):
        self.stop_pending = False
        self.revision += 1
        self.show_notice("停止请求未确认：" + str(message), failure=message)
        self.refresh()
        self.update_controls()

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
        if (value.get("thread") or {}).get("id") not in {None, self.thread_id}:
            self.show_notice("收到其他会话的迟到状态；原消息与草稿继续保留。")
            self.refresh()
            self.update_controls()
            return
        if value.get("reconciled"):
            accepted = self.submission_in_history(value)
            if accepted:
                self.accept_submission()
            if value.get("codex_state"):
                self.state["codex"] = {**self.state.get("codex", {}), "state": value["codex_state"]}
            if value.get("history_available") is not False:
                self.history_repairs_left = 1
                self.transcript.hydrate(value.get("thread"))
            self.show_notice("已在原生会话中确认原消息；Houdini 结果以执行详情为准。" if accepted else
                             "已读取会话，但尚不能确认原消息是否提交；草稿和图片继续保留。" if self.uncertain_send else
                             "已读取对话状态；Houdini 结果以执行详情为准。")
        else:
            self.show_notice(value.get("message", "没有可校正的会话。"))
        self.refresh()
        self.update_controls()

    def submission_in_history(self, value):
        snapshot, thread = self.pending_submission, value.get("thread") or {}
        if (not snapshot or not snapshot["history_known"] or value.get("history_available") is False
                or thread.get("id") != snapshot["thread_id"]):
            return False
        turns = thread.get("turns", [])
        previous = snapshot["last_turn_id"]
        start = next((i + 1 for i, turn in enumerate(turns) if turn.get("id") == previous), None) if previous else 0
        if start is None:
            return False  # A truncated read cannot establish what came after our snapshot.
        for turn in turns[start:]:
            for item in turn.get("items", []):
                if item.get("type") != "userMessage" or not item.get("id") or item["id"] in snapshot["seen_items"]:
                    continue
                content = item.get("content") or []
                text = "\n\n".join(block.get("text", "") for block in content if block.get("type") == "text")
                images = [block.get("path") for block in content if block.get("type") == "localImage"]
                if (text == snapshot["request_text"] and images == [image["path"] for image in snapshot["attachments"]]
                        and not any(block.get("type") == "image" for block in content)):
                    return True
        return False

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
        room = max(0, 8 - len(self.attachments))
        if len(paths) > room:
            self.show_notice("每次最多添加 8 张图片。")
        for path in paths[:room]:
            source = Path(path)
            self.attachments.append({"local_key": new_id(), "attachment_id": None,
                                     "name": source.name, "path": str(source), "status": "waiting"})
        self.render_attachments()
        self.upload_attachments()

    def add_clipboard_image(self, image):
        if len(self.attachments) >= 8:
            self.show_notice("每次最多添加 8 张图片。")
            return
        if isinstance(image, QtGui.QPixmap):
            image = image.toImage()
        if not isinstance(image, QtGui.QImage) or image.isNull():
            self.show_notice("剪贴板图片无法读取，请重新复制图片。")
            return
        if image.sizeInBytes() > 64 * 1024 * 1024:
            self.show_notice("剪贴板图片过大，请裁剪后再粘贴。")
            return
        data = QtCore.QByteArray()
        buffer = QtCore.QBuffer(data)
        buffer.open(QtCore.QIODevice.WriteOnly)
        saved = image.save(buffer, "PNG")
        buffer.close()
        if not saved or data.size() > 12 * 1024 * 1024:
            self.show_notice("剪贴板图片无法保存或超过 12 MB，请裁剪后再粘贴。")
            return
        try:
            folder = self.paths.cache("composer")
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / ("clipboard-" + new_id() + ".png")
            with path.open("xb") as stream:
                stream.write(bytes(data))
        except OSError as exc:
            self.show_notice("剪贴板图片保存失败：" + str(exc))
            return
        self.add_images([path])

    def upload_attachments(self):
        if self.bridge_connected:
            items = self.attachments
            for item in items:
                if item.get("status") not in {"waiting", "failed"}:
                    continue
                item["status"] = "uploading"
                self.uploading += 1
                key = item["local_key"]
                if not self.call("POST", "/attachments", {"path": item["path"]},
                                 done=lambda value, key=key, items=items: self.attached(value, key, items),
                                 failed=lambda message, key=key, items=items: self.attach_failed(message, key, items)):
                    self.attach_failed("连接尚未就绪，图片保留在草稿中。", key, items)
        self.render_attachments()
        self.update_controls()

    def attached(self, value, key=None, items=None):
        items = self.attachments if items is None else items
        item = next((item for item in items if item.get("local_key") == key), None)
        if item is not None:
            item.update(value, status="ready")
        if not self.closed and items is self.attachments:
            self.render_attachments()
            self.update_controls()

    def attach_failed(self, message, key=None, items=None):
        items = self.attachments if items is None else items
        item = next((item for item in items if item.get("local_key") == key), None)
        if item is not None:
            item["status"] = "failed"
            item["error"] = str(message)
        if not self.closed and items is self.attachments:
            self.error_details.set_failure(message)
            self.render_attachments()
            self.update_controls()

    def render_attachments(self):
        retained = set()
        for index, item in enumerate(self.attachments):
            key = item.get("local_key") or item["attachment_id"]
            retained.add(key)
            prefix = {"waiting": "待添加 · ", "uploading": "添加中 · ", "failed": "未添加 · "}.get(item.get("status"), "")
            tile = self.attachment_tiles.get(key)
            if tile is None:
                tile = ImageTile({"path": item["path"]}, item["name"], removable=True, compact=True)
                tile.removed.connect(lambda key=key: self.remove_attachment(key))
                self.attachment_tiles[key] = tile
            tile.caption.setText(prefix + item["name"])
            tile.caption.setVisible(self.height() >= 620)
            tile.caption.setToolTip(str(item.get("error") or prefix + item["name"]))
            self.attachment_layout.insertWidget(index, tile)
        for key in set(self.attachment_tiles) - retained:
            tile = self.attachment_tiles.pop(key)
            self.attachment_layout.removeWidget(tile)
            tile.hide()
            tile.deleteLater()
        self.attachment_area.setVisible(bool(self.attachments))

    def remove_attachment(self, attachment_id):
        self.attachments[:] = [item for item in self.attachments
                               if attachment_id not in {item.get("local_key"), item["attachment_id"]}]
        self.render_attachments()
        self.update_controls()

    def request_selection(self):
        if not self.selection_button.isEnabled():
            return
        self.selection_inflight = True
        self.selection_generation += 1
        generation, key = self.selection_generation, self.draft_key
        self.update_controls()
        self.call("POST", "/selection", {},
                  done=lambda value: self.selection_received(value) if generation == self.selection_generation and key == self.draft_key else None,
                  failed=lambda message: self.selection_failed(message) if generation == self.selection_generation and key == self.draft_key else None)

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
        self.save_draft()
        self.render_reference()
        self.show_notice("" if self.selection_reference else "当前没有选中的节点。")
        self.update_controls()

    def selection_failed(self, message):
        self.selection_inflight = False
        self.selection_pending = None
        self.show_notice(message)
        self.update_controls()

    def clear_reference(self):
        self.selection_reference = None
        self.save_draft()
        self.render_reference()
        self.update_controls()

    def render_reference(self):
        reference = self.selection_reference
        current_epoch = (self.state.get("runtime", {}).get("scene") or {}).get("scene_epoch")
        stale = bool(reference and reference.get("scene_epoch") != current_epoch)
        self.reference_label.setText("选择已过期" if stale else
                                     "选择：" + str(len(reference.get("nodes", []))) + " 个节点" if reference else "")
        if reference:
            set_button_icon(self.reference_label, "chevron-down", text=self.reference_label.text(), size=16)
        paths = "\n".join(reference.get("nodes", [])) if reference else ""
        if self.reference_paths.toPlainText() != paths:
            self.reference_paths.setPlainText(paths)
        self.reference_paths.setVisible(bool(reference) and self.reference_label.isChecked())
        self.reference_label.setToolTip(("来自之前的场景，请重新引用。\n" if stale else "") + paths)
        self.reference_label.setVisible(bool(reference))

    def toggle_reference(self):
        self.reference_paths.setVisible(bool(self.selection_reference) and self.reference_label.isChecked())

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
            else:
                self.request_cards[key].update_request(request)
        self.request_area.setVisible(bool(current))
        self.tabs.setTabText(0, "对话" + ("  ·  待回应 " + str(len(current)) if current else ""))
        self.update_controls()

    def respond_request(self, request_id, result):
        self.call("POST", "/requests/respond", {"request_id": request_id, "result": result},
                  done=lambda _: self.refresh(), failed=lambda message: self.request_response_failed(request_id, message))

    def request_response_failed(self, request_id, message):
        card = self.request_cards.get(str(request_id))
        if card:
            card.failed(message)
            self.error_details.set_failure(message)
            self.update_controls()

    def tab_changed(self, index):
        self.conversation_button.setVisible(index != 0)
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
        self.update_work_status()

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
            item = QtWidgets.QListWidgetItem("尚未保存项目约定。")
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
        self.model_controls.popup.hide()
        for card in self.transcript.cards.values():
            for _source, tile in card.image_tiles:
                if tile.viewer is not None:
                    tile.viewer.close()
        self.session_trust.set_api(None)
        self.poll.stop()
        self.account_poll.stop()
        self.history_refresh.stop()
        if self.owns_api and self.api:
            self.api.close()
        super().closeEvent(event)
