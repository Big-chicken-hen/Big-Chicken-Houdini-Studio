"""Fixed scene-source flow. Only the Launch sink admits a launch request."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import threading

from PySide6 import QtCore, QtGui, QtWidgets

from ..common import AppPaths, StudioError, atomic_json, new_id, read_json
from ..codex.protocol import SUPPORTED_CODEX_VERSION
from ..release import identity_details, local_identity
from .launcher_pages import project_page
from .launcher_visuals import ElidedLabel, RecentRow
from .launcher_flow import FLOW_STYLE, FlowPage, font_diagnostics
from .shared import ApiFailure, ErrorDetails, Task, button, label
from .launcher_palette import ACCENT, ARTWORK, INK, style_launcher_popup
from .icons import LoadingIcon, icon_diagnostics, set_button_icon


def read_minimize_preference(paths):
    try:
        value = read_json(paths.data("launcher-preferences.json"))
        return value.get("minimize_after_open", True) is not False
    except FileNotFoundError:
        return True


def write_minimize_preference(paths, enabled):
    atomic_json(paths.data("launcher-preferences.json"), {"minimize_after_open": bool(enabled)})


class _OnboardingOwner:
    """One generation's client; the guard is acquired only by worker functions."""
    def __init__(self, factory, guard, previous=None):
        self.factory, self.guard = factory, guard
        self.cancelled = threading.Event()
        self.backend = None
        self.previous = previous

    def _close_previous(self):
        if self.previous is not None:
            self.previous._close()
            self.previous = None

    def _close(self):
        self._close_previous()
        if self.backend is not None:
            backend = self.backend
            backend.close()
            self.backend = None

    def probe(self, overrides):
        with self.guard:
            self._close_previous()
            if self.cancelled.is_set():
                return None
            self.backend = self.factory()
            try:
                result = self.backend.probe(**overrides)
                return None if self.cancelled.is_set() else result
            finally:
                if self.cancelled.is_set():
                    self._close()

    def call(self, method, *args):
        with self.guard:
            if self.cancelled.is_set():
                self._close()
                return None
            if self.backend is None:
                raise StudioError("ONBOARDING_REQUIRED", "请重新检查启动环境")
            try:
                result = getattr(self.backend, method)(*args)
                return None if self.cancelled.is_set() else result
            finally:
                if self.cancelled.is_set():
                    self._close()

    def close(self):
        with self.guard:
            self._close()


class _TaskReply(QtCore.QObject):
    """Bound QObject slots disconnect when the window is destroyed."""
    def __init__(self, owner, kind, serial, generation, done, failed):
        super().__init__(owner)
        self.owner, self.kind, self.serial, self.generation = owner, kind, serial, generation
        self.done, self.failed = done, failed
        self.task = None

    @QtCore.Slot(object)
    def success(self, value):
        self.owner._completed(self, value, False)

    @QtCore.Slot(object)
    def failure(self, value):
        self.owner._completed(self, value, True)


class StudioLauncher(QtWidgets.QWidget):
    def __init__(self, paths=None, *, onboarding_factory=None, catalog=None, target_factory=None,
                 launch_function=None, status_function=None, browser_open=None, reveal_path=None,
                 preference_reader=None, preference_writer=None, auto_probe=True):
        super().__init__()
        self.paths = paths if paths is not None else AppPaths.for_user()
        self._release_identity = local_identity(self.paths)
        if onboarding_factory is None:
            from ..onboarding import Onboarding
            onboarding_factory = lambda bound=self.paths: Onboarding(bound)
        if catalog is None or target_factory is None:
            from ..targets import SceneCatalog, SceneTarget
            catalog = catalog if catalog is not None else SceneCatalog(self.paths)
            target_factory = target_factory or SceneTarget
        if launch_function is None or status_function is None:
            from ..launcher import launch_target, launch_status
            launch_function, status_function = launch_function or launch_target, status_function or launch_status
        self.catalog, self.target_factory = catalog, target_factory
        self._factory, self._launch, self._query = onboarding_factory, launch_function, status_function
        self._browser_open = browser_open or QtGui.QDesktopServices.openUrl
        self._reveal_path = reveal_path or self.reveal_in_folder
        self._preference_reader = preference_reader or read_minimize_preference
        self._preference_writer = preference_writer or write_minimize_preference
        self._guard, self._preference_guard = threading.Lock(), threading.Lock()
        self._onboarding = None
        self._generation, self._serial, self._preference_revision = 0, 0, 0
        self._pending, self._tasks = {}, {}
        self._closed = False
        self._snapshot, self._overrides_dirty = {}, set()
        self._needs_probe = False
        self._target = None
        self._source_branch, self._selection_path, self._open_path = None, None, None
        self._selection_generation, self._selection_valid = 0, False
        self._selection_message = ""
        self._launch_snapshot = None
        self._popup_rows = []
        self._recent_records, self._recent_rows = [], []
        self._recent_path = None
        self._request_id = self._launch_target = self._launch_paths = None
        self._launch_record = self._launch_error = self._launch_phase = self._prepared = None
        self._launch_label = ""
        self._host_trial_confirmation = None
        self._launch_version, self._remembered = 0, False
        self._failure = None
        self._secondary = self._secondary_return = None
        self._minimize_after_open, self._preference_loaded = True, False
        self._minimize_attempted_id = self._minimize_scheduled_id = None
        self.setObjectName("studioLauncher")
        self.setWindowTitle("Big-Chicken Studio")
        self.setWindowIcon(QtGui.QIcon(str(ARTWORK / "studio.ico")))
        self.setMinimumSize(600, 480)
        available = self.screen().availableGeometry()
        self.resize(min(1120, available.width() - 24), min(760, available.height() - 48))
        self.setAcceptDrops(True)
        self.build_ui()
        self.setStyleSheet(FLOW_STYLE)
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.setFocus(QtCore.Qt.OtherFocusReason)
        for widget in self.findChildren(QtWidgets.QPushButton):
            if widget.property("studioRole") == "primary":
                widget.setFixedHeight(40)
        self.probe_delay = QtCore.QTimer(self)
        self.probe_delay.setSingleShot(True)
        self.probe_delay.setInterval(250)
        self.probe_delay.timeout.connect(self.probe)
        self.poll = QtCore.QTimer(self)
        self.poll.setInterval(1500)
        self.poll.timeout.connect(self.query_launch)
        self.account_poll = QtCore.QTimer(self)
        self.account_poll.setInterval(2000)
        self.account_poll.timeout.connect(self.refresh_account)
        self.minimize_timer = QtCore.QTimer(self)
        self.minimize_timer.setSingleShot(True)
        self.minimize_timer.setInterval(500)
        self.minimize_timer.timeout.connect(self.minimize_opened_request)
        self._account_polls = 0
        self.reload_recents()
        self._submit("preference", lambda: self._preference_reader(self.paths),
                     self.preference_loaded, self.preference_failed)
        self.render()
        if auto_probe:
            self.probe()

    def action_button(self, text, callback, icon=None, *, primary=False, icon_only=False):
        widget = button(text, callback, "primary" if primary else "quiet")
        widget.setProperty("studioRole", "primary" if primary else "icon" if icon_only else "quiet")
        if primary:
            widget.setMinimumHeight(40)
        if icon:
            set_button_icon(widget, icon, text=text, icon_only=icon_only, color="#FFFFFF" if primary else INK)
        return widget

    def secondary_page(self, name, title):
        page = QtWidgets.QWidget()
        outer = QtWidgets.QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(16)
        back = self.action_button("返回", self.back_secondary, "arrow-left")
        outer.addWidget(back, 0, QtCore.Qt.AlignLeft)
        outer.addWidget(label(title, "sectionTitle"))
        scroll = QtWidgets.QScrollArea()
        scroll.viewport().setObjectName("secondaryViewport")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        body = QtWidgets.QWidget()
        body.setObjectName("secondaryBody")
        content = QtWidgets.QVBoxLayout(body)
        content.setContentsMargins(0, 0, 4, 0)
        content.setSpacing(12)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)
        self.pages[name] = page
        self.stack.addWidget(page)
        return content

    def build_ui(self):
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(16, 4, 16, 12)
        root.setSpacing(4)
        toolbar = QtWidgets.QWidget()
        toolbar.setFixedHeight(44)
        header = QtWidgets.QHBoxLayout(toolbar)
        header.setContentsMargins(10, 0, 6, 0)
        header.addWidget(label("Big-Chicken Studio", "toolbarBrand"), 1)
        self.settings_button = self.action_button("设置", lambda: self.show_secondary("settings"), "settings")
        self.diagnostics_button = self.action_button("诊断", self.show_details)
        for widget in (self.settings_button, self.diagnostics_button):
            widget.setProperty("studioRole", "toolbar")
            header.addWidget(widget)
        root.addWidget(toolbar)
        self.stack = QtWidgets.QStackedWidget()
        self.pages = {}
        root.addWidget(self.stack, 1)
        self.flow_scroll = QtWidgets.QScrollArea()
        self.flow_scroll.setObjectName("flowScroll")
        self.flow_scroll.viewport().setObjectName("flowViewport")
        self.flow_scroll.setWidgetResizable(True)
        self.flow_scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.flow_page = FlowPage()
        self.flow = self.flow_page.flow
        self.flow_scroll.setWidget(self.flow_page)
        self.pages["flow"] = self.flow_scroll
        self.stack.addWidget(self.flow_scroll)

        account = self.flow.nodes["account"].content
        self.flow.nodes["account"].setMinimumHeight(300)
        self.account_name = ElidedLabel("正在检查")
        self.account_name.setObjectName("flowTitle")
        self.auth_message = label("", "flowSecondary", True)
        self.setup_title = label("", "flowSecondary", True)
        self.setup_message = label("", "flowSecondary", True)
        for widget in (self.account_name, self.auth_message, self.setup_title, self.setup_message):
            account.addWidget(widget)
        self.login = self.action_button("使用 ChatGPT 继续", lambda: self.account_action("login_start"), primary=True)
        self.auth_query = self.action_button("查询账号状态", self.refresh_account, "refresh-cw")
        self.reopen_login = self.action_button("重新打开登录页", lambda: self.account_action("reopen_login"), "external-link")
        self.cancel_login = self.action_button("取消本次登录", lambda: self.account_action("cancel_login"))
        self.install_guide = self.action_button("查看安装步骤", self.open_install_guide, "external-link")
        self.setup_codex = self.action_button("选择 Codex", self.choose_codex)
        self.setup_retry = self.action_button("重新检查", self.retry_setup, "refresh-cw")
        self.account_manage = self.action_button("账号详情", lambda: self.show_secondary("account"))
        for widget in (self.login, self.auth_query, self.reopen_login, self.cancel_login,
                       self.install_guide, self.setup_codex, self.setup_retry, self.account_manage):
            account.addWidget(widget)
        account.addStretch()

        empty = self.flow.nodes["empty"]
        empty.chosen.connect(self.select_empty)
        self.empty_button = self.action_button("空场景", self.select_empty, "file-plus-2")
        self.empty_button.setFocusPolicy(QtCore.Qt.NoFocus)
        self.empty_button.setObjectName("flowNodeAction")
        empty.content.addWidget(self.empty_button)
        empty.content.addWidget(label("从新的 Houdini 场景开始", "flowSecondary", True))

        opening = self.flow.nodes["open"].content
        self.open_button = self.action_button("选择 HIP…", self.choose_hip, "folder-open")
        self.open_button.setObjectName("flowNodeAction")
        self.open_filename = ElidedLabel("尚未选择文件")
        self.open_filename.setObjectName("flowSecondary")
        self.open_directory = ElidedLabel("", middle=True)
        self.open_directory.setObjectName("flowSecondary")
        for widget in (self.open_filename, self.open_directory):
            widget.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
            widget.customContextMenuRequested.connect(self.open_path_menu)
        opening.addWidget(self.open_button)
        opening.addWidget(self.open_filename)
        opening.addWidget(self.open_directory)

        recent = self.flow.nodes["recent"].content
        self.recents = QtWidgets.QListWidget()
        self.recents.setObjectName("recentList")
        self.recents.setAccessibleName("最近场景，最多三项")
        self.recents.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.recents.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.recents.setSpacing(2)
        self.recents.setAcceptDrops(False)
        self.recents.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.recents.customContextMenuRequested.connect(self.recent_context_menu)
        self.recents.itemClicked.connect(self.activate_recent)
        self.recents.itemActivated.connect(self.activate_recent)
        self.recents.itemDoubleClicked.connect(self.activate_recent)
        recent.addWidget(self.recents)
        self.empty_hint = label("打开已有 HIP，或从空场景开始", "flowSecondary", True)
        recent.addWidget(self.empty_hint)
        self.view_all = self.action_button("查看全部", self.show_all_recents)
        recent.addWidget(self.view_all, 0, QtCore.Qt.AlignLeft)

        launch = self.flow.nodes["launch"].content
        self.flow.nodes["launch"].setMinimumHeight(300)
        self.launch_filename = ElidedLabel("请选择场景来源")
        self.launch_filename.setObjectName("flowTitle")
        self.launch_houdini = label("", "flowSecondary", True)
        self.launch_title = label("", wrap=True)
        self.launch_message = label("", "flowSecondary", True)
        launch.addWidget(self.launch_filename)
        launch.addWidget(self.launch_houdini)
        status_row = QtWidgets.QHBoxLayout()
        self.launch_loader = LoadingIcon(size=18, color=ACCENT) if LoadingIcon else None
        if self.launch_loader:
            status_row.addWidget(self.launch_loader)
        status_row.addWidget(self.launch_title, 1)
        launch.addLayout(status_row)
        launch.addWidget(self.launch_message)
        launch.addStretch()
        self.launch_button = self.action_button("启动 Houdini", self.launch_selected, primary=True)
        self.launch_query = self.action_button("查询启动状态", self.query_launch, "refresh-cw", primary=True)
        self.launch_back = self.action_button("重新准备", self.return_after_launch, primary=True)
        self.setup_houdini = self.action_button("选择 Houdini", self.choose_houdini, primary=True)
        for widget in (self.launch_button, self.launch_query, self.launch_back, self.setup_houdini):
            launch.addWidget(widget)
        self.drop_hint = label("释放以选择 HIP", "flowSecondary", True)
        launch.addWidget(self.drop_hint)
        self.drop_hint.hide()

        settings = self.secondary_page("settings", "设置")
        settings.addWidget(label("程序选择", "sectionTitle"))
        settings.addWidget(label("Codex 路径覆盖 · 留空并重新检查，恢复使用随包版本", "muted", True))
        row = QtWidgets.QHBoxLayout()
        self.codex = QtWidgets.QLineEdit()
        self.codex.setAccessibleName("Codex 路径覆盖")
        self.codex.textEdited.connect(lambda _value: self.overrides_changed("codex"))
        self.codex_browse = self.action_button("选择…", self.choose_codex)
        row.addWidget(self.codex, 1)
        row.addWidget(self.codex_browse)
        settings.addLayout(row)
        settings.addWidget(label("Houdini 安装", "muted"))
        row = QtWidgets.QHBoxLayout()
        self.houdini = QtWidgets.QComboBox()
        self.houdini.setMinimumContentsLength(12)
        self.houdini.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.houdini.addItem("自动选择", "")
        self.houdini.currentIndexChanged.connect(lambda _index: self.overrides_changed("houdini"))
        self.houdini_browse = self.action_button("选择…", self.choose_houdini)
        row.addWidget(self.houdini, 1)
        row.addWidget(self.houdini_browse)
        settings.addLayout(row)
        self.recheck = self.action_button("重新检查环境", self.probe, "refresh-cw")
        settings.addWidget(self.recheck, 0, QtCore.Qt.AlignLeft)
        self.minimize_choice = QtWidgets.QCheckBox("启动成功后最小化")
        self.minimize_choice.setChecked(True)
        self.minimize_choice.toggled.connect(self.save_minimize_preference)
        settings.addWidget(self.minimize_choice)
        self.settings_error = label("", wrap=True)
        self.settings_error.setProperty("tone", "error")
        settings.addWidget(self.settings_error)
        settings.addWidget(self.action_button("诊断", self.show_details), 0, QtCore.Qt.AlignLeft)
        settings.addStretch()

        account = self.secondary_page("account", "账号")
        self.account_summary = label("", wrap=True)
        account.addWidget(self.account_summary)
        self.account_query = self.action_button("重新检查账号", self.refresh_account, "refresh-cw")
        self.logout = self.action_button("退出登录", lambda: self.account_action("logout"))
        account.addWidget(self.account_query, 0, QtCore.Qt.AlignLeft)
        account.addWidget(self.logout, 0, QtCore.Qt.AlignLeft)
        account.addWidget(self.action_button("诊断", self.show_details), 0, QtCore.Qt.AlignLeft)
        account.addStretch()

        diagnostics = self.secondary_page("diagnostics", "诊断")
        self.error_details = ErrorDetails()
        diagnostics.addWidget(self.error_details)
        self.diagnostics_text = QtWidgets.QPlainTextEdit()
        self.diagnostics_text.setReadOnly(True)
        self.diagnostics_text.setAccessibleName("原始启动诊断")
        diagnostics.addWidget(self.diagnostics_text, 1)
        self.export_diagnostics_button = self.action_button("导出诊断…", self.export_diagnostics)
        diagnostics.addWidget(self.export_diagnostics_button, 0, QtCore.Qt.AlignLeft)

    def projection(self):
        return project_page(self._snapshot, request_id=self._request_id, launch_record=self._launch_record,
                            launch_phase=self._launch_phase, checking="probe" in self._pending)

    @property
    def current_page(self):
        return self._secondary or "flow"

    def show_secondary(self, name):
        if name not in {"account", "settings", "diagnostics"}:
            return
        self._secondary_return = self._secondary if name == "diagnostics" and self._secondary != "diagnostics" else None
        self._secondary = name
        self.minimize_timer.stop()
        self.render()

    def back_secondary(self):
        self._secondary = self._secondary_return if self._secondary == "diagnostics" else None
        self._secondary_return = None
        self.render()

    def show_details(self):
        self.show_secondary("diagnostics")

    def export_diagnostics(self):
        from ..release import export_diagnostics
        default = Path(QtCore.QStandardPaths.writableLocation(QtCore.QStandardPaths.DocumentsLocation)) / "Studio-diagnostics.zip"
        target, _ = QtWidgets.QFileDialog.getSaveFileName(self, "导出诊断", str(default), "ZIP (*.zip)")
        if not target:
            return
        answer = QtWidgets.QMessageBox.question(self, "确认导出内容",
            "将导出版本、安装完整性、连接与账号确认状态、最近失败代码和阶段。\n"
            "不包含聊天、脚本、账号凭证、场景或图片；不会自动上传。\n\n位置：" + target)
        if answer != QtWidgets.QMessageBox.Yes:
            return
        snapshot, failure, phase = copy.deepcopy(self._snapshot), self._failure, self.projection().name
        launch = self._launch_record or {}
        snapshot['host'] = copy.deepcopy(launch.get('host')) if launch.get('runtime_connected') else None
        self._submit("diagnostic-export", lambda: export_diagnostics(self.paths, Path(target).resolve(), snapshot,
            failure=failure, phase=phase), lambda path: QtWidgets.QMessageBox.information(self, "诊断已导出", path))

    def failure_message(self):
        code = self._failure.get("code") if isinstance(self._failure, dict) else getattr(self._failure, "code", None)
        messages = {
            "PYTHON_REQUIRED": "Studio 的运行组件缺失，请使用安装器修复后重新打开。",
            "CODEX_REQUIRED": "未找到可用的 Codex，请修复 Studio 安装或选择兼容程序。",
            "CODEX_UNAVAILABLE": "无法启动 Codex，请重新检查；仍失败时可查看详情。",
            "CODEX_VERSION_UNTESTED": f"需要 Codex {SUPPORTED_CODEX_VERSION}，请选择兼容程序。",
            "HOUDINI_REQUIRED": "未找到 Houdini，请选择本机已有安装，再重新检测。",
            "HOUDINI_UNSUPPORTED": "当前 Houdini 不满足本版本的集成要求，请选择受支持的安装并查看详情。",
            "HOUDINI_CONFIRMATION_REQUIRED": "此 Houdini 组合尚未验证，请确认后再尝试启动。",
            "HIP_INVALID": "请选择已有的 Houdini 场景文件（.hip、.hiplc 或 .hipnc）。",
            "LAUNCH_FAILED": "Studio 启动进程未能启动。请查看详情；确认原因后可重新打开场景。",
            "RUNTIME_START_FAILED": "Houdini 已启动，但 Studio 未能连接。请查看详情并确认该 Houdini 会话的状态。",
            "LAUNCH_STATE_UNKNOWN": "启动结果尚未确认。请查询原启动请求，避免重复打开。",
            "LAUNCH_STATUS_UNCONFIRMED": "启动状态尚未确认，请查询原启动请求。",
            "CONNECTION_LOST": "暂时无法连接。请检查网络，并查询当前账号或启动请求的状态。",
        }
        if code in messages:
            return messages[code]
        if isinstance(self._failure, dict):
            return str(self._failure.get("message", "需要查看详情"))
        return str(self._failure or "").splitlines()[0] if self._failure else ""

    def render(self):
        if self._closed:
            return
        view = self.projection()
        active = self._launch_active()
        locked = self._request_id is not None
        snapshot = self._launch_snapshot if active and self._launch_snapshot else self._snapshot
        account, codex, houdini = (snapshot.get(key) or {} for key in ("account", "codex", "houdini"))
        status, codex_state = account.get("status", "unknown"), codex.get("state")
        checking = not active and ("probe" in self._pending or codex_state in {None, "checking"})
        busy = "probe" in self._pending or "account" in self._pending
        pending_login = bool(account.get("login_pending", status == "waiting"))
        uncertain = bool(account.get("action_unknown"))
        title = ("正在检查" if checking else "请在浏览器中完成登录" if pending_login else
                 str(account.get("email") or "ChatGPT") if status == "signed_in" and not uncertain else
                 "需要登录" if status in {"signed_out", "other"} and not uncertain else "暂时无法确认账号")
        self.account_name.set_full_text(title)
        self.auth_message.setText("Checking · 确认账号与 Codex" if checking else
            "本次启动已确认账号" if active else "账号已确认" if status == "signed_in" and not uncertain else
            "在系统浏览器中完成后返回这里。" if pending_login else
            "使用你的 ChatGPT 账号继续。" if status in {"signed_out", "other"} and not uncertain else
            "请查询原账号状态。")
        codex_messages = {"ready": "Codex " + str(codex.get("version") or SUPPORTED_CODEX_VERSION) + " · Ready",
                          "missing": "未找到 Codex", "incompatible": "Codex 版本不兼容", "error": "暂时无法连接 Codex"}
        self.setup_title.setText(codex_messages.get(codex_state, "正在确认 Codex"))
        external_failed = codex.get('source') == 'explicit_external' and codex_state != 'ready'
        self.setup_message.setText("显式选择的外部 Codex 未通过检查。" if external_failed else
                                   f"需要兼容的 Codex {SUPPORTED_CODEX_VERSION}。")
        codex_problem = not checking and codex_state != "ready" and not active
        self.setup_message.setVisible(codex_problem)
        self.login.setVisible(not checking and not active and codex_state == "ready" and
                              status in {"signed_out", "other"} and not uncertain and not pending_login)
        self.auth_query.setVisible(not checking and not active and codex_state == "ready" and
                                   (status == "unknown" or uncertain))
        self.reopen_login.setVisible(pending_login and not active)
        self.cancel_login.setVisible(pending_login and not active)
        self.install_guide.setVisible(codex_problem and codex_state == "missing")
        self.setup_codex.setVisible(codex_problem)
        self.setup_retry.setVisible(codex_problem and (external_failed or codex_state != "missing"))
        self.setup_retry.setText("恢复使用随包版本" if external_failed else "重新检查")
        self.setup_retry.setAccessibleName(self.setup_retry.text())
        for widget in (self.login, self.auth_query, self.reopen_login, self.cancel_login,
                       self.install_guide, self.setup_codex, self.setup_retry):
            widget.setEnabled(not active and not busy)
        self.reopen_login.setEnabled(not active and not busy and not uncertain)
        self.cancel_login.setEnabled(not active and not busy and not uncertain)
        self.recents.setVisible(bool(self._recent_records))
        self.empty_hint.setVisible(not self._recent_records)
        self.view_all.setVisible(bool(self._recent_records))
        for name in ("empty", "open", "recent"):
            self.flow.nodes[name].setEnabled(not locked)
        self.open_filename.set_full_text(Path(self._open_path).name if self._open_path else "尚未选择文件")
        self.open_directory.set_full_text(str(Path(self._open_path).parent) if self._open_path else "")
        if self._open_path:
            for widget in (self.open_filename, self.open_directory):
                widget.setToolTip(self._open_path)
        target_label = self._launch_label if locked else ("空场景" if self._source_branch == "empty" else
                       Path(self._selection_path).name if self._selection_path else "尚未选择场景")
        self.launch_filename.set_full_text(target_label)
        self.launch_filename.setToolTip(self._selection_path or target_label)
        compatibility = houdini.get("compatibility") or {}
        host_status = compatibility.get("status", "unknown").title()
        self.launch_houdini.setText(("Houdini " + str(houdini.get("version") or "Unknown") + " · " + host_status)
                                   if houdini.get("state") == "found" else "尚未选择 Houdini")
        ready = self._ready() and self._selection_valid and not busy and "selection" not in self._pending
        mode = view.mode if locked else ""
        if locked:
            self.launch_title.setText({"opened": "Opened · 已在 Houdini 中打开", "unknown": "启动结果尚未确认",
                "failed": "未能打开场景", "scene": "已连接，正在确认场景", "connecting": "正在连接 Studio",
                "validate": "确认目标文件", "prepare": "确认启动条件", "submit": "正在启动 Houdini"}.get(mode, "正在确认启动状态"))
            self.launch_message.setText({"unknown": "Houdini 可能已经启动。查询同一请求，避免重复打开。",
                "opened": "目标已确认打开。", "failed": self.failure_message() or "已确认进程未存活，可以重新准备。",
                "scene": "Runtime 已连接，目标尚未确认。"}.get(mode, "本次目标已锁定。"))
        else:
            reason = ("请选择场景来源" if self._source_branch is None else self._selection_message if not self._selection_valid else
                      "正在确认账号与环境" if busy else "请先确认 Codex 可用" if codex_state != "ready" else
                      "暂时无法确认账号" if uncertain or status == "unknown" else "请先完成账号登录" if status != "signed_in" else
                      "请选择可用的 Houdini" if houdini.get("state") != "found" or compatibility.get("can_launch") is False else
                      "Untested · 本次启动需要确认" if compatibility.get("confirmation_required") else "Ready · 可以启动")
            self.launch_title.setText(reason)
            self.launch_message.setText(self.failure_message() or ("已选择 · " + {"empty": "Empty", "open": "Open", "recent": "Recent"}.get(self._source_branch, "")
                if self._source_branch else "先选择本地场景，再从这里启动。"))
        if active and self._host_trial_confirmation and self._host_trial_confirmation.get('accepted') is False:
            self.launch_title.setText("本次试用未确认")
            self.launch_message.setText("请通过 Houdini 正常关闭本次会话；Studio 不会重复启动。")
        missing_houdini = not locked and not checking and (houdini.get("state") != "found" or compatibility.get("can_launch") is False)
        self.launch_button.setVisible(not locked and not missing_houdini)
        self.launch_button.setText("确认并启动" if compatibility.get("confirmation_required") else "启动 Houdini")
        self.launch_button.setAccessibleName(self.launch_button.text())
        tone = "warning" if mode == "unknown" or compatibility.get("confirmation_required") else "error" if mode == "failed" else ""
        if self.launch_title.property("tone") != tone:
            self.launch_title.setProperty("tone", tone)
            self.launch_title.style().unpolish(self.launch_title)
            self.launch_title.style().polish(self.launch_title)
        self.launch_button.setEnabled(ready and not locked)
        self.setup_houdini.setVisible(missing_houdini)
        self.setup_houdini.setEnabled(not busy)
        self.launch_query.setVisible(locked and mode == "unknown")
        self.launch_query.setEnabled("status" not in self._pending)
        self.launch_back.setVisible(locked and mode == "failed")
        if self.launch_loader:
            self.launch_loader.set_busy(locked and mode in {"validate", "prepare", "submit", "connecting", "scene"})
        self.flow.set_selection(self._source_branch, ready or active and mode not in {"unknown", "failed"})
        for widget in (self.codex, self.codex_browse, self.houdini, self.houdini_browse, self.recheck):
            widget.setEnabled(not active)
        self.recheck.setEnabled(not active and not busy)
        self.account_summary.setText(("已登录 ChatGPT\n" + str(account.get("email") or "")) if status == "signed_in" else
                                     "等待浏览器登录" if pending_login else "尚未登录" if status == "signed_out" else "账号状态尚未确认")
        if active:
            self.account_summary.setText(self.account_summary.text() + "\n启动期间不能更改账号。")
        self.account_query.setEnabled(not active and not busy)
        self.logout.setVisible(status == "signed_in")
        self.logout.setEnabled(not active and not busy and not uncertain)
        self.settings_error.setText(self.failure_message())
        self.settings_error.setVisible(bool(self._failure))
        self._sync_environment_controls()
        self.error_details.set_failure(self._failure)
        details = {"requirements": {"codex_version": SUPPORTED_CODEX_VERSION},
                   "environment": self._snapshot, "launch": self._launch_record,
                   "houdini_trial_confirmation": self._host_trial_confirmation,
                   "request_id": self._request_id, "icons": icon_diagnostics(), "hero_font": font_diagnostics()}
        launch = self._launch_record or {}
        identity = {**self._release_identity, 'codex': self._snapshot.get('codex') or {}}
        rendered = identity_details(identity, selected=self._snapshot.get('houdini'), host=launch.get('host'),
                                    connected=launch.get('runtime_connected') is True)
        rendered += "\n\n" + json.dumps(details, ensure_ascii=False, indent=2, default=str)
        if self.diagnostics_text.toPlainText() != rendered:
            self.diagnostics_text.setPlainText(rendered)
        page = self.pages[self.current_page]
        if self.stack.currentWidget() is not page:
            self.stack.setCurrentWidget(page)

    def _sync_environment_controls(self):
        houdini = self._snapshot.get("houdini", {})
        selected = self.houdini.currentData() if "houdini" in self._overrides_dirty else houdini.get("path")
        self.houdini.blockSignals(True)
        for item in houdini.get("installations", []):
            if self.houdini.findData(item["path"]) < 0:
                self.houdini.addItem(item["label"], item["path"])
                self.houdini.setItemData(self.houdini.count() - 1, item["path"], QtCore.Qt.ToolTipRole)
        index = self.houdini.findData(selected)
        if index >= 0:
            self.houdini.setCurrentIndex(index)
        self.houdini.blockSignals(False)
        if "codex" not in self._overrides_dirty:
            self.codex.setText(self._snapshot.get("codex", {}).get("path") or "")

    def show_failure(self, failure):
        self._failure = failure

    def _submit(self, kind, function, done, failed=None):
        if self._closed:
            return
        self._serial += 1
        relay = _TaskReply(self, kind, self._serial, self._generation, done, failed or self.show_failure)
        task = relay.task = Task(function)
        self._pending[kind] = relay.serial
        self._tasks[relay.serial] = relay
        task.signals.result.connect(relay.success)
        task.signals.error.connect(relay.failure)
        QtCore.QThreadPool.globalInstance().start(task)

    def _completed(self, relay, value, failed):
        same_generation = relay.kind not in {"probe", "account", "prepare", "remember"} or relay.generation == self._generation
        current = (not self._closed and same_generation and
                   self._pending.get(relay.kind) == relay.serial)
        self._tasks.pop(relay.serial, None)
        if self._pending.get(relay.kind) == relay.serial:
            self._pending.pop(relay.kind, None)
        if current:
            (relay.failed if failed else relay.done)(value)
            self.render()
        relay.deleteLater()

    def _launch_active(self):
        return bool(self._request_id and (self._launch_phase or not self._launch_record or
                    self._launch_record.get("state") not in {"closed", "rejected"} or
                    self._launch_record.get("process_may_exist")))

    def _ready(self):
        return (self._snapshot.get("codex", {}).get("state") == "ready" and
                self._snapshot.get("houdini", {}).get("state") == "found" and
                (self._snapshot.get("houdini", {}).get("compatibility") or {}).get("can_launch") is not False and
                self._snapshot.get("account", {}).get("status") == "signed_in" and
                not self._snapshot.get("account", {}).get("action_unknown"))

    def probe(self):
        if self._closed or self._launch_active():
            return
        self.probe_delay.stop()
        self.account_poll.stop()
        self._needs_probe = False
        self._generation += 1
        previous = self._onboarding
        if previous:
            previous.cancelled.set()
        owner = self._onboarding = _OnboardingOwner(self._factory, self._guard, previous)
        overrides = {"codex_override": self.codex.text().strip() if "codex" in self._overrides_dirty else None,
                     "houdini_override": (self.houdini.currentData() or "") if "houdini" in self._overrides_dirty else None}
        self._snapshot = {"codex": {"state": "checking"}, "account": {"status": "unknown"},
                          "houdini": self._snapshot.get("houdini", {})}
        self._submit("probe", lambda: owner.probe(overrides), self.apply_snapshot, self.probe_failed)
        self.render()

    def retry_setup(self):
        codex = self._snapshot.get('codex') or {}
        if codex.get('source') == 'explicit_external' and codex.get('state') != 'ready':
            self.codex.clear()
            self._overrides_dirty.add('codex')
        self.probe()

    def probe_failed(self, failure):
        self._snapshot["codex"] = {**self._snapshot.get("codex", {}), "state": "error"}
        self._snapshot["account"] = {"status": "unknown"}
        self.show_failure(failure)

    def overrides_changed(self, field):
        if self._closed or self._launch_active():
            return
        self._generation += 1
        self._overrides_dirty.add(field)
        if self._onboarding:
            self._onboarding.cancelled.set()
        self._snapshot = {"codex": {"state": "checking"}, "account": {"status": "unknown"},
                          "houdini": self._snapshot.get("houdini", {})}
        self.probe_delay.start()
        self.render()

    def apply_snapshot(self, value):
        if not isinstance(value, dict):
            return
        self._snapshot = {key: value.get(key) or {} for key in ("codex", "houdini", "account")}
        self._snapshot.update(revision=value.get("revision"), error=value.get("error"))
        if value.get("error"):
            self.show_failure(value["error"])
        else:
            self._failure = None
        account = value.get("account", {})
        if account.get("login_pending", account.get("status") == "waiting"):
            self.account_poll.start()
        else:
            self.account_poll.stop()

    def account_action(self, method):
        if self._launch_active() or self._closed or self._onboarding is None:
            return
        account = self._snapshot.get("account", {})
        if "account" in self._pending or account.get("action_unknown"):
            return
        if method == "login_start" and account.get("login_pending"):
            return
        self._account_polls = 0
        if method == "login_start":
            self._secondary = None
        owner = self._onboarding
        def complete(value):
            if isinstance(value, dict):
                self.apply_snapshot(value)
            if method == "logout":
                self._secondary = None
            if method in {"login_start", "reopen_login"}:
                url = value.get("auth_url") if isinstance(value, dict) else value
                if url:
                    self.open_url(url)
        self._submit("account", lambda: owner.call(method), complete,
                     lambda failure: self.account_failed(failure, action_unknown=method in {
                         "login_start", "cancel_login", "logout"}))
        self.render()

    def account_failed(self, failure, *, action_unknown=False):
        self.account_poll.stop()
        account = self._snapshot["account"] = {**self._snapshot.get("account", {}), "status": "unknown"}
        if action_unknown:
            account["action_unknown"] = True
        self.show_failure(failure)

    def refresh_account(self):
        if self._closed or self._launch_active() or "account" in self._pending or self._onboarding is None:
            return
        if self.account_poll.isActive():
            self._account_polls += 1
            if self._account_polls >= 150:
                self.account_poll.stop()
                self._snapshot["account"] = {**self._snapshot.get("account", {}), "status": "unknown",
                                             "message": "请主动重新检查登录状态"}
                self.render()
                return
        owner = self._onboarding
        self._submit("account", lambda: owner.call("account_read"), self.apply_snapshot, self.account_failed)
        self.render()

    def preference_loaded(self, enabled):
        self._preference_loaded = True
        if self._preference_revision == 0:
            self._minimize_after_open = bool(enabled)
            self.minimize_choice.blockSignals(True)
            self.minimize_choice.setChecked(bool(enabled))
            self.minimize_choice.blockSignals(False)
        self.schedule_minimize()

    def preference_failed(self, failure):
        self._preference_loaded = True
        self._minimize_after_open = False
        self.minimize_choice.blockSignals(True)
        self.minimize_choice.setChecked(False)
        self.minimize_choice.blockSignals(False)
        self.show_failure(failure)

    def save_minimize_preference(self, enabled):
        self._minimize_after_open = bool(enabled)
        self._preference_revision += 1
        revision = self._preference_revision
        if not enabled:
            self.minimize_timer.stop()
        def write():
            with self._preference_guard:
                if revision == self._preference_revision:
                    self._preference_writer(self.paths, enabled)
        self._submit("preference-write", write, lambda _value: None)

    def schedule_minimize(self):
        if not self._preference_loaded or not self._request_id or self.projection().mode != "opened":
            return
        if self._host_trial_confirmation and self._host_trial_confirmation.get('accepted') is not True:
            return
        if self._minimize_attempted_id == self._request_id:
            return
        self._minimize_attempted_id = self._request_id
        if self._minimize_after_open and self._secondary is None and not self.isMinimized():
            self._minimize_scheduled_id = self._request_id
            self.minimize_timer.start()

    def minimize_opened_request(self):
        if (not self._closed and self._minimize_scheduled_id == self._request_id and
                self.projection().mode == "opened" and self._secondary is None and
                (not self._host_trial_confirmation or self._host_trial_confirmation.get('accepted') is True) and
                self._minimize_after_open and self.isVisible() and not self.isMinimized()):
            self.showMinimized()

    def reload_recents(self):
        self._submit("recent", lambda: self.catalog.recent(limit=20), self.recents_loaded)

    def fill_recents(self, listing, records, *, compact):
        listing.clear()
        rows = []
        for record in records:
            item = QtWidgets.QListWidgetItem()
            item.setSizeHint(QtCore.QSize(0, 56 if compact else 64))
            item.setData(QtCore.Qt.UserRole, record)
            item.setToolTip(record["path"])
            listing.addItem(item)
            row = RecentRow(record, compact=compact)
            row.selected.connect(self.select_recent_record)
            row.activated.connect(self.activate_recent_record)
            row.menu_requested.connect(self.show_recent_menu)
            set_button_icon(row.more_button, "ellipsis", text="更多", icon_only=True, color=INK)
            row.more_button.setAccessibleName(record["name"] + " 的操作")
            listing.setItemWidget(item, row)
            row.set_selected(self._source_branch == "recent" and record["path"] == self._recent_path)
            rows.append(row)
        return rows

    def recents_loaded(self, records):
        incoming = list(records or [])
        if incoming != self._recent_records or not self._recent_rows:
            self._recent_records = incoming
            self._recent_rows = self.fill_recents(self.recents, incoming[:3], compact=True)
            self.recents.setFixedHeight(min(3, len(incoming)) * 60 + 4)
            if hasattr(self, 'recent_popup') and self.recent_popup.isVisible():
                self._popup_rows = self.fill_recents(self.popup_recents, incoming, compact=False)
        self.render()

    def select_recent_record(self, record):
        self.select_path(record["path"], source="recent")

    def activate_recent(self, item):
        if item is not None:
            self.activate_recent_record(item.data(QtCore.Qt.UserRole))

    def activate_recent_record(self, record):
        self.select_recent_record(record)
        if hasattr(self, 'recent_popup'):
            self.recent_popup.hide()
        self.launch_button.setFocus(QtCore.Qt.OtherFocusReason)

    def show_all_recents(self):
        if self._request_id is not None:
            return
        if not hasattr(self, 'recent_popup'):
            self.recent_popup = QtWidgets.QFrame(self, QtCore.Qt.Popup)
            self.recent_popup.setObjectName("recentPopup")
            self.recent_popup.setWindowTitle("最近场景")
            layout = QtWidgets.QVBoxLayout(self.recent_popup)
            layout.setContentsMargins(12, 12, 12, 12)
            layout.addWidget(label("最近场景", "sectionTitle"))
            self.popup_recents = QtWidgets.QListWidget()
            self.popup_recents.setObjectName("recentList")
            self.popup_recents.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
            self.popup_recents.itemClicked.connect(self.activate_recent)
            self.popup_recents.itemActivated.connect(self.activate_recent)
            layout.addWidget(self.popup_recents)
        self._popup_rows = self.fill_recents(self.popup_recents, self._recent_records, compact=False)
        screen = self.screen().availableGeometry()
        width, height = min(520, screen.width() - 32), min(440, screen.height() - 48)
        self.recent_popup.resize(width, height)
        anchor = self.flow.nodes['recent'].mapToGlobal(self.flow.nodes['recent'].rect().bottomLeft())
        self.recent_popup.move(max(screen.left(), min(anchor.x(), screen.right() - width)),
                               max(screen.top(), min(anchor.y(), screen.bottom() - height)))
        self.recent_popup.show()

    def open_path_menu(self, _position):
        if not self._open_path:
            return
        menu = QtWidgets.QMenu(self)
        style_launcher_popup(menu)
        menu.addAction("复制完整路径", lambda: QtWidgets.QApplication.clipboard().setText(self._open_path))
        menu.popup(QtGui.QCursor.pos())
        self._menu = menu

    def recent_context_menu(self, position):
        item = self.recents.itemAt(position) if position is not None else self.recents.currentItem()
        if item is not None:
            location = (self.recents.viewport().mapToGlobal(position) if position is not None else
                        self.recents.viewport().mapToGlobal(self.recents.visualItemRect(item).center()))
            self.show_recent_menu(item.data(QtCore.Qt.UserRole), location)

    def show_recent_menu(self, record, location):
        menu = QtWidgets.QMenu(self)
        menu.setObjectName("studioRecentMenu")
        style_launcher_popup(menu)
        if record.get("missing"):
            menu.addAction("重新定位", lambda: self.relocate_recent(record))
            menu.addAction("复制原路径", lambda: QtWidgets.QApplication.clipboard().setText(record["path"]))
        else:
            menu.addAction("选择", lambda: self.activate_recent_record(record))
            menu.addAction("在资源管理器中显示", lambda: self._reveal_path(record["path"]))
            menu.addAction("复制路径", lambda: QtWidgets.QApplication.clipboard().setText(record["path"]))
        menu.addAction("从最近列表移除", lambda: self.forget_recent(record))
        menu.popup(location)
        self._menu = menu

    def relocate_recent(self, record):
        if self._request_id is not None:
            return
        old_path = record["path"]
        generation = self._selection_generation
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "重新定位 HIP", "", "Houdini scenes (*.hip *.hiplc *.hipnc)")
        if path:
            def done(_value):
                if (generation == self._selection_generation and self._source_branch == "recent"
                        and self._selection_path == old_path):
                    self.select_path(path, source="recent")
                self._failure = None
                self.reload_recents()
            self._submit("recent-edit", lambda: self.catalog.relocate_recent(old_path, path), done)

    def forget_recent(self, record):
        if self._request_id is not None:
            return
        path = record["path"]
        def done(_value):
            if self._recent_path == path:
                self._recent_path = None
            self._failure = None
            self.reload_recents()
        self._submit("recent-edit", lambda: self.catalog.remove_recent(path), done)

    @staticmethod
    def reveal_in_folder(path):
        if os.name == "nt":
            return QtCore.QProcess.startDetached("explorer.exe", ["/select,", str(Path(path))])
        return QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(Path(path).parent)))

    def choose_hip(self):
        if self._closed or self._request_id is not None:
            return
        generation = self._selection_generation
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "选择 HIP", "", "Houdini scenes (*.hip *.hiplc *.hipnc)")
        if path and generation == self._selection_generation:
            self.select_path(path)

    def select_empty(self):
        if self._closed or self._request_id is not None:
            return
        self._selection_generation += 1
        self._pending.pop("selection", None)
        self._source_branch, self._selection_path = "empty", None
        self._selection_message, self._selection_valid = "", True
        self._target = self.target_factory.empty()
        self._failure = None
        self.update_selected_rows()
        self.render()

    def update_selected_rows(self):
        for row in [*self._recent_rows, *self._popup_rows]:
            row.set_selected(self._source_branch == "recent" and row.record["path"] == self._recent_path)

    def select_path(self, path, *, source="open"):
        """Resolve a local target, never admit it or start services."""
        if self._closed or self._request_id is not None:
            return
        self._selection_generation += 1
        generation = self._selection_generation
        self._source_branch, self._selection_path = source, str(path)
        self._target, self._selection_valid = None, False
        self._selection_message, self._failure = "正在确认文件", None
        if source == "open":
            self._open_path = str(path)
        else:
            self._recent_path = str(path)
        self.update_selected_rows()
        def selected(target):
            if generation == self._selection_generation and self._request_id is None:
                self._target, self._selection_valid, self._selection_message = target, True, ""
        def failed(failure):
            if generation == self._selection_generation and self._request_id is None:
                self._selection_message = "找不到有效 HIP，请重新选择或定位。"
                self.show_failure(failure)
        self._submit("selection", lambda: self.target_factory.hip(path), selected, failed)
        self.render()

    def launch_selected(self):
        if not self._selection_valid or self._target is None:
            return
        # Read the HIP again at Launch: a previously selected file may be gone.
        self.activate_target(self._target if self._target.kind == 'empty' else None,
                             path=self._target.path if self._target.kind == 'hip' else None)

    def activate_target(self, target=None, *, path=None):
        if (self._closed or self.current_page != "flow" or not self._ready() or self._request_id is not None
                or any(kind in self._pending for kind in ("probe", "account", "selection"))):
            return
        if target is None and path is None:
            return
        self._pending.pop("selection", None)
        self._selection_generation += 1
        self._request_id = new_id()
        self._launch_paths = self.paths
        self._launch_target = target
        self._launch_snapshot = copy.deepcopy(self._snapshot)
        self._launch_label = Path(path).name if path else ("空场景" if target.kind == "empty" else Path(target.path).name)
        self._launch_record = self._launch_error = self._prepared = None
        self._host_trial_confirmation = None
        self._launch_version += 1
        self._launch_phase = "validate" if path else "prepare"
        self._remembered = False
        self._failure = None
        self.account_poll.stop()
        if hasattr(self, 'recent_popup'):
            self.recent_popup.hide()
        if path:
            self._submit("target", lambda: self.target_factory.hip(path), self.target_activated, self.activation_failed)
        else:
            self.target_activated(target)
        self.render()

    def target_activated(self, target):
        self._target = self._launch_target = target
        self._launch_phase = "prepare"
        owner = self._onboarding
        houdini = copy.deepcopy(self._snapshot.get('houdini') or {})
        confirmation = None
        if (houdini.get('compatibility') or {}).get('confirmation_required') is True:
            message = (houdini.get('compatibility') or {}).get('message') or '此 Houdini 组合尚未验证。'
            answer = QtWidgets.QMessageBox.question(self, '尝试未验证的 Houdini',
                f"Untested · {houdini.get('version') or 'Unknown'}\n{message}\n\n"
                "启动成功仍属于 Untested。此确认仅允许尝试启动，不改变场景或文件操作许可。\n\n继续启动？",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No, QtWidgets.QMessageBox.No)
            if answer != QtWidgets.QMessageBox.Yes:
                self._request_id = self._launch_target = self._launch_paths = self._launch_phase = None
                self.render()
                return
            confirmation = {'request_id': self._request_id, 'path': houdini.get('path'), 'version': houdini.get('version')}
        self._submit("prepare", lambda: owner.call("prepare_launch", confirmation) if confirmation else
                     owner.call("prepare_launch"), self.prepared, self.prepare_failed)

    def activation_failed(self, failure):
        # No launch submission has run. This is local preflight evidence.
        if getattr(failure, 'code', '') in {'HIP_INVALID', 'HIP_MISSING'}:
            self._selection_valid = False
            self._selection_message = "目标文件已不可用，请重新选择或定位。"
        self._launch_phase = None
        self._launch_record = {"request_id": self._request_id, "state": "rejected", "process_may_exist": False,
                               "submission_state": "not_submitted", "message": str(failure)}
        self.show_failure(failure)

    def prepared(self, choices):
        self._needs_probe = True  # prepare_launch ends this onboarding connection.
        if not isinstance(choices, dict):
            self.prepare_failed(ApiFailure("启动条件尚未确认，请重新检查", code="PREPARE_UNCONFIRMED"))
            return
        if Path(choices.get("codex_home") or "").resolve() != self._launch_paths.codex_home:
            self.prepare_failed(ApiFailure("账号与启动的数据位置不一致，请重新检查环境", code="PROFILE_MISMATCH"))
            return
        self._prepared = choices
        request_id, target, paths = self._request_id, self._launch_target, self._launch_paths
        self._launch_phase = "submit"
        options = {'request_id': request_id}
        if choices.get('houdini_confirmation') is not None:
            options['houdini_confirmation'] = copy.deepcopy(choices['houdini_confirmation'])
        self._submit("launch", lambda: self._launch(paths, target, choices["houdini_path"],
                     choices["codex_path"], **options), self.launched, self.launch_failed)

    def prepare_failed(self, failure):
        self._needs_probe = True
        self._snapshot["account"] = {**self._snapshot.get("account", {}), "status": "unknown"}
        self.activation_failed(failure)

    def launched(self, value):
        self._launch_phase = None
        self._launch_version += 1
        self.apply_launch_status(value)
        if self._launch_active():
            self.poll.start()

    def launch_failed(self, failure):
        self._launch_phase = None
        self._launch_record = {"request_id": self._request_id, "state": "unknown", "process_may_exist": True,
                               "target": self._launch_target.to_dict()}
        self._launch_error = failure
        self.show_failure(failure)
        self.poll.start()

    def query_launch(self):
        if self._closed or not self._request_id or self._launch_phase or "status" in self._pending:
            return
        request_id, version, paths = self._request_id, self._launch_version, self._launch_paths
        def done(value):
            if request_id == self._request_id and version == self._launch_version:
                self.apply_launch_status(value)
        def failed(value):
            if request_id == self._request_id and version == self._launch_version:
                self.query_failed(value)
        self._submit("status", lambda: self._query(paths, request_id), done, failed)
        self.render()

    def query_failed(self, failure):
        self._launch_record = {**(self._launch_record or {}), "request_id": self._request_id,
                               "state": "unknown", "process_may_exist": True}
        self._launch_error = failure
        self.show_failure(failure)

    def apply_launch_status(self, value):
        if not isinstance(value, dict) or value.get("request_id") != self._request_id:
            self.launch_failed(ApiFailure("无法关联启动状态，请查询原请求", code="LAUNCH_STATUS_UNCONFIRMED"))
            return
        self._launch_record = value
        host = value.get('host') or {}
        if value.get('houdini_confirmation') is True:
            self._host_trial_confirmation = {'request_id': self._request_id, 'source': 'before_launch', 'accepted': True}
        elif (value.get('runtime_connected') is True and (host.get('compatibility') or {}).get('status') == 'untested'
              and self._host_trial_confirmation is None):
            request_id = self._request_id
            self._host_trial_confirmation = {'request_id': request_id, 'source': 'running_host', 'accepted': None}
            self.minimize_timer.stop()
            answer = QtWidgets.QMessageBox.question(self, '确认本次 Houdini 试用',
                f"正在运行: {host.get('version') or 'Unknown'} · Untested\n"
                f"{(host.get('compatibility') or {}).get('message') or '实际宿主组合尚未验证。'}\n\n"
                "继续仅确认本次试用，不改变场景或文件操作许可。\n"
                "若不继续，请通过 Houdini 正常关闭本次会话；Studio 不会强制关闭它。\n\n继续试用？",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No, QtWidgets.QMessageBox.No)
            if self._closed or self._request_id != request_id:
                return
            self._host_trial_confirmation['accepted'] = answer == QtWidgets.QMessageBox.Yes
        if value.get("error"):
            self._launch_error = value["error"]
            self.show_failure(value["error"])
        elif self._launch_error is not None:
            if self._failure is self._launch_error:
                self._failure = None
            self._launch_error = None
        if (self.projection().mode == "opened" and
                (not self._host_trial_confirmation or self._host_trial_confirmation.get('accepted') is True)):
            if not self._remembered:
                self._remembered = True
                owner, path = self._onboarding, (self._prepared or {}).get("houdini_path")
                if owner is not None and path:
                    self._submit("remember", lambda: owner.call("remember_houdini", path), lambda _value: None)
                self.reload_recents()
            self.schedule_minimize()
        if value.get("state") in {"closed", "rejected"} and not value.get("process_may_exist"):
            self.poll.stop()
            self.minimize_timer.stop()

    def return_after_launch(self):
        if self._request_id is None or self.projection().mode != "failed" or self._launch_active():
            return
        self._request_id = self._launch_record = self._launch_phase = None
        self._host_trial_confirmation = None
        self._launch_version += 1
        self._failure = None
        if self._needs_probe:
            self.probe()
        self.render()

    def choose_codex(self):
        if self._launch_active():
            return
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "选择 Codex", "", "Codex (codex.exe codex)")
        if path:
            self.codex.setText(path)
            self.overrides_changed("codex")

    def choose_houdini(self):
        if self._launch_active():
            return
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "选择 Houdini", "", "Houdini (houdini.exe houdinifx.exe houdini)")
        if path:
            index = self.houdini.findData(path)
            if index < 0:
                self.houdini.addItem(Path(path).parent.parent.name, path)
                index = self.houdini.count() - 1
            self.houdini.setCurrentIndex(index)

    def open_url(self, value):
        url = QtCore.QUrl(str(value))
        if url.scheme() not in {"https", "http"} or not url.host() or url.userInfo():
            self.show_failure(ApiFailure("登录地址无效，请重新检查账号", code="LOGIN_URL_INVALID"))
            return
        if not self._browser_open(url):
            self.show_failure(ApiFailure("未能打开浏览器，可重新打开登录页", code="BROWSER_UNAVAILABLE"))

    def open_install_guide(self):
        QtWidgets.QMessageBox.information(self, "Studio 安装帮助",
            f"Studio 安装包包含所需运行组件和 Codex {SUPPORTED_CODEX_VERSION}。\n\n"
            "组件缺失时，请使用同版本 Studio 安装器修复；也可以选择已有的兼容 Codex 程序。\n"
            "Houdini 需要在本机单独安装。完成后返回启动器，重新检查。")

    @staticmethod
    def dropped_path(mime):
        urls = mime.urls()
        if len(urls) != 1 or not urls[0].isLocalFile() or urls[0].hasQuery() or urls[0].hasFragment():
            return None
        path = urls[0].toLocalFile()
        return path if Path(path).suffix.lower() in {".hip", ".hiplc", ".hipnc"} else None

    def dragEnterEvent(self, event):
        if self.dropped_path(event.mimeData()) and self._request_id is None:
            self.drop_hint.setVisible(self.current_page == "flow")
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self.drop_hint.hide()
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        self.drop_hint.hide()
        path = self.dropped_path(event.mimeData())
        if not path or self._request_id is not None:
            event.ignore()
            return
        self.select_path(path)
        event.acceptProposedAction()

    def closeEvent(self, event):
        self._closed = True
        self._generation += 1
        for timer in (self.poll, self.account_poll, self.probe_delay, self.minimize_timer):
            timer.stop()
        owner = self._onboarding
        if owner is not None:
            owner.cancelled.set()
            QtCore.QThreadPool.globalInstance().start(Task(owner.close))
        super().closeEvent(event)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QtCore.QEvent.WindowStateChange and self.isMinimized():
            for node in self.flow.nodes.values():
                node._selection_animation.stop()
                node._hover_animation.stop()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'flow'):
            compact = self.width() < 980
            self.flow.set_compact(compact)
            scrollbar = self.flow_scroll.verticalScrollBar().sizeHint().width() if compact else 0
            self.flow.setFixedWidth(min(1000, self.width() - 32 - scrollbar))
            from .launcher_flow import hero_font
            self.flow_page.hero.setFont(hero_font(compact))
