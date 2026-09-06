"""Staged scene Launcher. Pages project facts; explicit actions own side effects."""
from __future__ import annotations

import json
import os
from pathlib import Path
import threading

from PySide6 import QtCore, QtGui, QtWidgets

from ..common import AppPaths, StudioError, atomic_json, new_id, read_json
from .launcher_pages import project_page
from .launcher_visuals import LAUNCHER_STYLE, RecentRow
from .shared import ApiFailure, ErrorDetails, Task, button, label
from .theme import apply_theme
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
        self._closed, self._checking_visible = False, False
        self._snapshot, self._overrides_dirty = {}, set()
        self._needs_probe = False
        self._target = self._deferred_target = None
        self._recent_records, self._recent_rows = [], []
        self._recent_path = None
        self._request_id = self._launch_target = self._launch_paths = None
        self._launch_record = self._launch_error = self._launch_phase = self._prepared = None
        self._launch_label = ""
        self._launch_version, self._remembered = 0, False
        self._failure = None
        self._secondary = self._secondary_return = None
        self._minimize_after_open, self._preference_loaded = True, False
        self._minimize_attempted_id = self._minimize_scheduled_id = None
        self.setObjectName("studioLauncher")
        self.setWindowTitle("Big-Chicken Studio")
        self.setMinimumSize(600, 480)
        self.resize(760, 560)
        self.setAcceptDrops(True)
        self.build_ui()
        self.setStyleSheet(LAUNCHER_STYLE)
        for widget in self.findChildren(QtWidgets.QPushButton):
            if widget.property("studioRole") == "primary":
                widget.setFixedHeight(40)
        self.probe_delay = QtCore.QTimer(self)
        self.probe_delay.setSingleShot(True)
        self.probe_delay.setInterval(250)
        self.probe_delay.timeout.connect(self.probe)
        self.checking_delay = QtCore.QTimer(self)
        self.checking_delay.setSingleShot(True)
        self.checking_delay.setInterval(250)
        self.checking_delay.timeout.connect(self.reveal_checking)
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
            set_button_icon(widget, icon, text=text, icon_only=icon_only)
        return widget

    def center_page(self, name, width=420):
        page = QtWidgets.QWidget()
        page.setObjectName("launcherPage")
        outer = QtWidgets.QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addStretch()
        box = QtWidgets.QWidget()
        box.setFixedWidth(width)
        box.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        content = QtWidgets.QVBoxLayout(box)
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(16)
        outer.addWidget(box, 0, QtCore.Qt.AlignHCenter)
        outer.addStretch()
        self.pages[name] = page
        self.stack.addWidget(page)
        return content, box

    def secondary_page(self, name, title):
        page = QtWidgets.QWidget()
        outer = QtWidgets.QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(16)
        back = self.action_button("返回", self.back_secondary, "arrow-left")
        outer.addWidget(back, 0, QtCore.Qt.AlignLeft)
        outer.addWidget(label(title, "sectionTitle"))
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        body = QtWidgets.QWidget()
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
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(24)
        header = QtWidgets.QHBoxLayout()
        header.addWidget(label("Big-Chicken Studio", "brand"), 1)
        self.more = self.action_button("更多", self.show_main_menu, "ellipsis", icon_only=True)
        self.more.setMinimumWidth(36)
        self.more.setFixedHeight(36)
        header.addWidget(self.more)
        root.addLayout(header)
        self.stack = QtWidgets.QStackedWidget()
        self.page_opacity = QtWidgets.QGraphicsOpacityEffect(self.stack)
        self.page_opacity.setOpacity(1.0)
        self.stack.setGraphicsEffect(self.page_opacity)
        self.page_transition = QtCore.QPropertyAnimation(self.page_opacity, b"opacity", self)
        self.page_transition.setDuration(150)
        self.page_transition.setStartValue(0.0)
        self.page_transition.setEndValue(1.0)
        self.pages = {}
        root.addWidget(self.stack, 1)

        checking, self.checking_box = self.center_page("checking", 360)
        self.checking_loader = LoadingIcon(size=24) if LoadingIcon else None
        if self.checking_loader:
            checking.addWidget(self.checking_loader, 0, QtCore.Qt.AlignHCenter)
        checking.addWidget(label("正在检查必要条件", "title", True))
        checking.addWidget(label("确认后即可继续。", "muted", True))

        setup, _box = self.center_page("setup")
        self.setup_title = label("", "title", True)
        self.setup_message = label("", wrap=True)
        setup.addWidget(self.setup_title)
        setup.addWidget(self.setup_message)
        self.install_guide = self.action_button("查看安装步骤", self.open_install_guide, "external-link", primary=True)
        self.setup_codex = self.action_button("选择已有安装", self.choose_codex)
        self.setup_retry = self.action_button("重新检查", self.probe, "refresh-cw", primary=True)
        self.setup_houdini = self.action_button("选择 Houdini", self.choose_houdini, primary=True)
        self.setup_details = self.action_button("查看详情", self.show_details)
        self.setup_actions = QtWidgets.QVBoxLayout()
        self.setup_actions.setSpacing(12)
        self._setup_mode = None
        for widget in (self.install_guide, self.setup_codex, self.setup_retry, self.setup_houdini, self.setup_details):
            self.setup_actions.addWidget(widget)
        setup.addLayout(self.setup_actions)

        auth, _box = self.center_page("authentication", 360)
        self.auth_title = label("", "title", True)
        self.auth_message = label("", wrap=True)
        auth.addWidget(self.auth_title)
        auth.addWidget(self.auth_message)
        self.login = self.action_button("使用 ChatGPT 继续", lambda: self.account_action("login_start"), primary=True)
        self.auth_query = self.action_button("重新检查", self.refresh_account, "refresh-cw", primary=True)
        self.reopen_login = self.action_button("重新打开登录页", lambda: self.account_action("reopen_login"), "external-link")
        self.cancel_login = self.action_button("取消本次登录", lambda: self.account_action("cancel_login"))
        self.auth_hint = label("登录将在系统浏览器中完成。", "muted", True)
        for widget in (self.login, self.auth_query, self.reopen_login, self.cancel_login, self.auth_hint):
            auth.addWidget(widget)
        auth.addWidget(self.action_button("遇到问题？查看详情", self.show_details))

        home = QtWidgets.QWidget()
        home_layout = QtWidgets.QVBoxLayout(home)
        home_layout.setContentsMargins(0, 0, 0, 0)
        home_layout.setSpacing(16)
        row = QtWidgets.QHBoxLayout()
        row.addWidget(label("最近场景", "sectionTitle"), 1)
        self.open_button = self.action_button("打开 HIP…", self.choose_hip, "folder-open", primary=True)
        self.empty_button = self.action_button("空场景", lambda: self.activate_target(self.target_factory.empty()), "file-plus-2")
        row.addWidget(self.open_button)
        row.addWidget(self.empty_button)
        home_layout.addLayout(row)
        self.deferred_row = QtWidgets.QWidget()
        deferred = QtWidgets.QHBoxLayout(self.deferred_row)
        deferred.setContentsMargins(0, 0, 0, 0)
        self.deferred_label = label("", wrap=True)
        self.deferred_label.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Preferred)
        deferred.addWidget(self.deferred_label, 1)
        deferred.addWidget(self.action_button("打开待选场景", self.activate_deferred))
        home_layout.addWidget(self.deferred_row)
        self.drop_hint = label("释放以打开", "sectionTitle", True)
        self.drop_hint.hide()
        home_layout.addWidget(self.drop_hint)
        self.recents = QtWidgets.QListWidget()
        self.recents.setObjectName("recentList")
        self.recents.setAccessibleName("最近场景")
        self.recents.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.recents.setSpacing(4)
        self.recents.setAcceptDrops(False)
        self.recents.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.recents.customContextMenuRequested.connect(self.recent_context_menu)
        self.recents.currentItemChanged.connect(self.recent_selection_changed)
        self.recents.itemDoubleClicked.connect(self.activate_recent)
        self.recents.itemActivated.connect(self.activate_recent)
        home_layout.addWidget(self.recents, 1)
        self.empty_hint = label("打开已有 HIP，或从空场景开始", "muted", True)
        home_layout.addWidget(self.empty_hint)
        self.home_error = label("", wrap=True)
        self.home_error.setProperty("tone", "error")
        home_layout.addWidget(self.home_error)
        home_layout.addStretch()
        self.pages["home"] = home
        self.stack.addWidget(home)
        self.recent_menu_key = QtGui.QShortcut(QtGui.QKeySequence("Shift+F10"), self.recents)
        self.recent_menu_key.setContext(QtCore.Qt.WidgetWithChildrenShortcut)
        self.recent_menu_key.activated.connect(lambda: self.recent_context_menu(None))

        launching, _box = self.center_page("launching", 460)
        self.launch_loader = LoadingIcon(size=24) if LoadingIcon else None
        if self.launch_loader:
            launching.addWidget(self.launch_loader, 0, QtCore.Qt.AlignHCenter)
        self.launch_title = label("", "title", True)
        self.launch_message = label("", wrap=True)
        launching.addWidget(self.launch_title)
        launching.addWidget(self.launch_message)
        self.launch_query = self.action_button("查询启动状态", self.query_launch, "refresh-cw", primary=True)
        self.launch_back = self.action_button("返回首页，重新打开", self.return_after_launch)
        launching.addWidget(self.launch_query)
        launching.addWidget(self.launch_back)
        launching.addWidget(self.action_button("查看详情", self.show_details))

        settings = self.secondary_page("settings", "设置")
        settings.addWidget(label("程序选择", "sectionTitle"))
        settings.addWidget(label("Codex 路径覆盖 · 留空自动发现", "muted", True))
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

    def projection(self):
        return project_page(self._snapshot, request_id=self._request_id, launch_record=self._launch_record,
                            launch_phase=self._launch_phase, checking="probe" in self._pending)

    @property
    def current_page(self):
        return self._secondary or self.projection().name

    def reveal_checking(self):
        self._checking_visible = True
        self.render()

    def show_main_menu(self):
        menu = QtWidgets.QMenu(self)
        menu.setObjectName("studioLauncherMenu")
        apply_theme(menu, popup=True)
        menu.addAction("账号", lambda: self.show_secondary("account"))
        menu.addAction("设置", lambda: self.show_secondary("settings"))
        menu.popup(self.more.mapToGlobal(self.more.rect().bottomLeft()))
        self._menu = menu

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

    def failure_message(self):
        if isinstance(self._failure, dict):
            return str(self._failure.get("message", "需要查看详情"))
        return str(self._failure or "").splitlines()[0] if self._failure else ""

    @staticmethod
    def set_action_role(widget, primary):
        role = "primary" if primary else "quiet"
        if widget.property("studioRole") != role:
            widget.setProperty("studioRole", role)
            widget.setObjectName(role)
            widget.style().unpolish(widget)
            widget.style().polish(widget)
        widget.setFixedHeight(40 if primary else 32)

    def render(self):
        if self._closed:
            return
        view = self.projection()
        account = self._snapshot.get("account", {})
        status = account.get("status", "unknown")
        active = self._launch_active()
        busy = "probe" in self._pending or "account" in self._pending
        self.checking_box.setVisible(self._checking_visible)
        if self.checking_loader:
            self.checking_loader.set_busy(view.name == "checking" and self._checking_visible)
        if view.name == "setup":
            modes = {
                "codex_missing": ("需要 Codex", "安装 Codex 后即可继续。"),
                "codex_incompatible": ("当前 Codex 版本不受支持", "请选择符合要求的兼容安装。"),
                "codex_error": ("无法启动 Codex", "尚未确认可用的 Codex 连接，请重新检查或选择其他安装。"),
                "codex_unconfirmed": ("无法确认可用安装", "请选择已有 Codex，或查看当前要求。"),
                "houdini": ("需要 Houdini 安装", "请选择本机已有的 Houdini 安装。"),
            }
            title, message = modes[view.mode]
            self.setup_title.setText(title)
            self.setup_message.setText(message)
            self.install_guide.setVisible(view.mode in {"codex_missing", "codex_incompatible", "codex_unconfirmed"})
            self.setup_codex.setVisible(view.mode != "houdini")
            self.setup_codex.setText("选择兼容安装" if view.mode == "codex_incompatible" else
                                    "选择其他安装" if view.mode == "codex_error" else "选择已有安装")
            self.setup_retry.setVisible(view.mode in {"codex_error", "houdini"})
            self.setup_houdini.setVisible(view.mode == "houdini")
            self.set_action_role(self.install_guide, view.mode == "codex_missing")
            self.set_action_role(self.setup_codex, view.mode in {"codex_incompatible", "codex_unconfirmed"})
            self.set_action_role(self.setup_retry, view.mode == "codex_error")
            self.set_action_role(self.setup_houdini, True)
            if self._setup_mode != view.mode:
                ordered = {
                    "codex_missing": (self.install_guide, self.setup_codex, self.setup_retry, self.setup_houdini),
                    "codex_incompatible": (self.setup_codex, self.install_guide, self.setup_retry, self.setup_houdini),
                    "codex_unconfirmed": (self.setup_codex, self.install_guide, self.setup_retry, self.setup_houdini),
                    "codex_error": (self.setup_retry, self.setup_codex, self.install_guide, self.setup_houdini),
                    "houdini": (self.setup_houdini, self.setup_retry, self.setup_codex, self.install_guide),
                }[view.mode] + (self.setup_details,)
                for widget in ordered:
                    self.setup_actions.removeWidget(widget)
                for widget in ordered:
                    self.setup_actions.addWidget(widget)
                self._setup_mode = view.mode
        pending_login = bool(account.get("login_pending", status == "waiting"))
        uncertain = bool(account.get("action_unknown"))
        self.auth_title.setText("登录以继续" if view.mode == "signed_out" else
                                "请在浏览器中完成登录" if view.mode == "waiting" else "暂时无法确认账号")
        self.auth_message.setText("使用你的 ChatGPT 账号连接 Codex。" if view.mode == "signed_out" else
                                  "完成后会自动继续。" if view.mode == "waiting" else
                                  "先查询原账号状态，再决定下一步。")
        self.login.setVisible(view.mode == "signed_out")
        self.login.setEnabled(not busy and not uncertain and not pending_login)
        self.auth_query.setVisible(view.mode == "attention")
        self.auth_query.setEnabled(not busy)
        self.reopen_login.setVisible(pending_login)
        self.cancel_login.setVisible(pending_login)
        self.reopen_login.setEnabled(not busy and not uncertain)
        self.cancel_login.setEnabled(not busy and not uncertain)
        self.auth_hint.setVisible(view.mode == "signed_out")
        self.recents.setVisible(bool(self._recent_records))
        self.empty_hint.setVisible(not self._recent_records)
        self.deferred_row.setVisible(self._deferred_target is not None)
        if self._deferred_target is not None:
            self.deferred_label.setText("待打开 · " + Path(self._deferred_target.path).name + "\n准备完成，请主动打开。")
        self.home_error.setText(self.failure_message())
        self.home_error.setVisible(bool(self._failure))
        self.open_button.setEnabled(view.name == "home" and not active)
        self.empty_button.setEnabled(view.name == "home" and not active)
        mode = view.mode
        self.launch_title.setText("已在 Houdini 中打开" if mode == "opened" else
                                  "尚未确认场景是否打开" if mode == "unknown" else
                                  "未能打开场景" if mode == "failed" else "正在打开 " + self._launch_label)
        messages = {"validate": "确认启动条件", "prepare": "确认启动条件", "submit": "启动 Houdini",
                    "connecting": "连接 Studio", "scene": "正在确认场景",
                    "unknown": "Houdini 可能已经启动。先查询原请求，避免重复打开。",
                    "opened": self._launch_label + "\n关闭此窗口不会关闭 Houdini。",
                    "failed": self.failure_message() or "已确认没有可能存活的启动进程，可以返回后重新打开。"}
        self.launch_message.setText(messages.get(mode, "正在确认启动状态"))
        self.launch_query.setVisible(mode == "unknown")
        self.launch_query.setEnabled("status" not in self._pending)
        self.launch_back.setVisible(mode == "failed")
        if self.launch_loader:
            self.launch_loader.set_busy(view.name == "launching" and mode in {"validate", "prepare", "submit", "connecting", "scene"})
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
        details = {"environment": self._snapshot, "launch": self._launch_record,
                   "request_id": self._request_id, "icons": icon_diagnostics()}
        rendered = json.dumps(details, ensure_ascii=False, indent=2, default=str)
        if self.diagnostics_text.toPlainText() != rendered:
            self.diagnostics_text.setPlainText(rendered)
        page = self.pages[self.current_page]
        if self.stack.currentWidget() is not page:
            self.page_transition.stop()
            self.stack.setCurrentWidget(page)
            if self.isVisible() and not self.isMinimized():
                self.page_transition.start()
            else:
                self.page_opacity.setOpacity(1.0)
        for widget in self.findChildren(QtWidgets.QPushButton):
            if widget.property("studioRole") == "primary" and widget.isVisibleTo(self):
                widget.setFixedHeight(40)

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
                self._snapshot.get("account", {}).get("status") == "signed_in" and
                not self._snapshot.get("account", {}).get("action_unknown"))

    def probe(self):
        if self._closed or self._launch_active():
            return
        self.probe_delay.stop()
        self._checking_visible = False
        self.checking_delay.start()
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
        if self._minimize_attempted_id == self._request_id:
            return
        self._minimize_attempted_id = self._request_id
        if self._minimize_after_open and self._secondary is None and not self.isMinimized():
            self._minimize_scheduled_id = self._request_id
            self.minimize_timer.start()

    def minimize_opened_request(self):
        if (not self._closed and self._minimize_scheduled_id == self._request_id and
                self.projection().mode == "opened" and self._secondary is None and
                self._minimize_after_open and self.isVisible() and not self.isMinimized()):
            self.showMinimized()

    def reload_recents(self):
        self._submit("recent", lambda: self.catalog.recent(limit=20), self.recents_loaded)

    def recents_loaded(self, records):
        self._recent_records = list(records or [])
        self.recents.clear()
        self._recent_rows = []
        for record in self._recent_records:
            item = QtWidgets.QListWidgetItem()
            item.setSizeHint(QtCore.QSize(0, 64))
            item.setData(QtCore.Qt.UserRole, record)
            item.setToolTip(record["path"])
            self.recents.addItem(item)
            row = RecentRow(record)
            row.selected.connect(self.select_recent_record)
            row.activated.connect(self.activate_recent_record)
            row.menu_requested.connect(self.show_recent_menu)
            set_button_icon(row.more_button, "ellipsis", text="更多", icon_only=True)
            row.more_button.setAccessibleName(record["name"] + " 的操作")
            self.recents.setItemWidget(item, row)
            self._recent_rows.append(row)
            if record["path"] == self._recent_path:
                self.recents.setCurrentItem(item)
        if self.recents.currentRow() < 0 and self.recents.count():
            self.recents.setCurrentRow(0)
        self.render()

    def select_recent_record(self, record):
        for index in range(self.recents.count()):
            item = self.recents.item(index)
            if item.data(QtCore.Qt.UserRole)["path"] == record["path"]:
                self.recents.setCurrentItem(item)
                return

    def recent_selection_changed(self, item, _previous=None):
        self._recent_path = item.data(QtCore.Qt.UserRole)["path"] if item is not None else None
        for row in self._recent_rows:
            row.set_selected(row.record["path"] == self._recent_path)

    def activate_recent(self, item):
        if item is not None:
            self.activate_recent_record(item.data(QtCore.Qt.UserRole))

    def activate_recent_record(self, record):
        if record.get("missing"):
            self.show_failure(ApiFailure("找不到此文件。请在该条目的更多菜单中重新定位。", code="HIP_MISSING"))
            self.render()
            return
        self.activate_target(path=record["path"])

    def recent_context_menu(self, position):
        item = self.recents.itemAt(position) if position is not None else self.recents.currentItem()
        if item is not None:
            location = (self.recents.viewport().mapToGlobal(position) if position is not None else
                        self.recents.viewport().mapToGlobal(self.recents.visualItemRect(item).center()))
            self.show_recent_menu(item.data(QtCore.Qt.UserRole), location)

    def show_recent_menu(self, record, location):
        menu = QtWidgets.QMenu(self)
        menu.setObjectName("studioRecentMenu")
        apply_theme(menu, popup=True)
        if record.get("missing"):
            menu.addAction("重新定位", lambda: self.relocate_recent(record))
            menu.addAction("复制原路径", lambda: QtWidgets.QApplication.clipboard().setText(record["path"]))
        else:
            menu.addAction("打开", lambda: self.activate_recent_record(record))
            menu.addAction("在资源管理器中显示", lambda: self._reveal_path(record["path"]))
            menu.addAction("复制路径", lambda: QtWidgets.QApplication.clipboard().setText(record["path"]))
        menu.addAction("从最近列表移除", lambda: self.forget_recent(record))
        menu.popup(location)
        self._menu = menu

    def relocate_recent(self, record):
        if self._request_id is not None:
            return
        old_path = record["path"]
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "重新定位 HIP", "", "Houdini scenes (*.hip *.hiplc *.hipnc)")
        if path:
            def done(_value):
                self._recent_path = path
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
        if self.current_page != "home" or self._request_id is not None:
            return
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "打开 HIP", "", "Houdini scenes (*.hip *.hiplc *.hipnc)")
        if path:
            self.activate_target(path=path)

    def select_path(self, path):
        """Pure selection used for drops outside Home; never admits or starts."""
        def selected(target):
            self._target = self._deferred_target = target
            self._failure = None
        self._submit("selection", lambda: self.target_factory.hip(path), selected)

    def activate_deferred(self):
        if self._deferred_target is not None:
            self.activate_target(self._deferred_target)

    def activate_target(self, target=None, *, path=None):
        if self._closed or self.current_page != "home" or not self._ready() or self._request_id is not None:
            return
        if target is None and path is None:
            return
        self._pending.pop("selection", None)
        self._request_id = new_id()
        self._launch_paths = self.paths
        self._launch_target = target
        self._launch_label = Path(path).name if path else ("空场景" if target.kind == "empty" else Path(target.path).name)
        self._launch_record = self._launch_error = self._prepared = None
        self._launch_version += 1
        self._launch_phase = "validate" if path else "prepare"
        self._remembered = False
        self._deferred_target = None
        self._failure = None
        self.account_poll.stop()
        if path:
            self._submit("target", lambda: self.target_factory.hip(path), self.target_activated, self.activation_failed)
        else:
            self.target_activated(target)
        self.render()

    def target_activated(self, target):
        self._target = self._launch_target = target
        self._launch_phase = "prepare"
        owner = self._onboarding
        self._submit("prepare", lambda: owner.call("prepare_launch"), self.prepared, self.prepare_failed)

    def activation_failed(self, failure):
        # No launch submission has run. This is local preflight evidence.
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
        self._submit("launch", lambda: self._launch(paths, target, choices["houdini_path"],
                     choices["codex_path"], request_id=request_id), self.launched, self.launch_failed)

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
        if value.get("error"):
            self._launch_error = value["error"]
            self.show_failure(value["error"])
        elif self._launch_error is not None:
            if self._failure is self._launch_error:
                self._failure = None
            self._launch_error = None
        if self.projection().mode == "opened":
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
        self.open_url("https://developers.openai.com/codex/cli/")

    @staticmethod
    def dropped_path(mime):
        urls = mime.urls()
        if len(urls) != 1 or not urls[0].isLocalFile() or urls[0].hasQuery() or urls[0].hasFragment():
            return None
        path = urls[0].toLocalFile()
        return path if Path(path).suffix.lower() in {".hip", ".hiplc", ".hipnc"} else None

    def dragEnterEvent(self, event):
        if self.dropped_path(event.mimeData()):
            self.drop_hint.setVisible(self.current_page == "home")
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self.drop_hint.hide()
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        self.drop_hint.hide()
        path = self.dropped_path(event.mimeData())
        if not path:
            event.ignore()
            return
        if self.current_page == "home":
            self.activate_target(path=path)
        else:
            self.select_path(path)
        event.acceptProposedAction()

    def closeEvent(self, event):
        self._closed = True
        self._generation += 1
        self.page_transition.stop()
        for timer in (self.poll, self.account_poll, self.probe_delay, self.checking_delay, self.minimize_timer):
            timer.stop()
        owner = self._onboarding
        if owner is not None:
            owner.cancelled.set()
            QtCore.QThreadPool.globalInstance().start(Task(owner.close))
        super().closeEvent(event)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QtCore.QEvent.WindowStateChange and self.isMinimized():
            self.page_transition.stop()
            self.page_opacity.setOpacity(1.0)
