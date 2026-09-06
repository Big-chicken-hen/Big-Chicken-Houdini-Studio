"""Scene-first Launcher. Backends own readiness, admission and process facts."""
from __future__ import annotations

from pathlib import Path
import threading

from PySide6 import QtCore, QtGui, QtWidgets

from ..common import AppPaths, StudioError, new_id
from .launcher_visuals import LAUNCHER_STYLE, ReadinessRow
from .shared import ApiFailure, ErrorDetails, StudioGlyph, Task, button, label


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
    def __init__(self, paths=None, *, onboarding_factory=None, onboarding_for_paths=None, catalog=None, target_factory=None,
                 launch_function=None, status_function=None, browser_open=None, auto_probe=True):
        super().__init__()
        self.paths = paths if paths is not None else AppPaths.for_user()
        if onboarding_factory is None:
            if onboarding_for_paths is None:
                from ..onboarding import Onboarding
                onboarding_for_paths = Onboarding
            onboarding_factory = lambda bound_paths=self.paths: onboarding_for_paths(bound_paths)
        if catalog is None or target_factory is None:
            from ..targets import SceneCatalog, SceneTarget
            catalog = catalog if catalog is not None else SceneCatalog(self.paths)
            target_factory = target_factory or SceneTarget
        if launch_function is None or status_function is None:
            from ..launcher import launch_target, launch_status
            launch_function = launch_function or launch_target
            status_function = status_function or launch_status
        self.catalog, self.target_factory = catalog, target_factory
        self._factory, self._launch, self._query = onboarding_factory, launch_function, status_function
        self._normal_paths, self._normal_factory = self.paths, onboarding_factory
        self._onboarding_for_paths = onboarding_for_paths
        self._legacy_context = None
        self._browser_open = browser_open or QtGui.QDesktopServices.openUrl
        self._guard = threading.Lock()
        self._onboarding = None
        self._generation, self._serial = 0, 0
        self._pending, self._tasks = {}, {}
        self._closed = False
        self._snapshot = {}
        self._overrides_dirty = set()
        self._needs_probe = False
        self._target = self.target_factory.empty()
        self._user_chose_target = False
        self._recent_records = []
        self._recent_path = None
        self._request_id = None
        self._launch_target = None
        self._launch_paths = None
        self._launch_legacy_workspace_id = None
        self._launch_record = None
        self._launch_error = None
        self._launch_version = 0
        self._launch_phase = None
        self._prepared = None
        self._remembered = False
        self.setObjectName("studioLauncher")
        self.setWindowTitle("Big-Chicken Studio")
        self.setMinimumSize(560, 600)
        self.resize(780, 740)
        self.setAcceptDrops(True)
        self.build_ui()
        self.setStyleSheet(LAUNCHER_STYLE)
        self.probe_delay = QtCore.QTimer(self)
        self.probe_delay.setSingleShot(True)
        self.probe_delay.setInterval(250)
        self.probe_delay.timeout.connect(self.probe)
        self.details_timer = QtCore.QTimer(self)
        self.details_timer.setSingleShot(True)
        self.details_timer.timeout.connect(self.reveal_details)
        self.poll = QtCore.QTimer(self)
        self.poll.setInterval(1500)
        self.poll.timeout.connect(self.query_launch)
        self.account_poll = QtCore.QTimer(self)
        self.account_poll.setInterval(2000)
        self.account_poll.timeout.connect(self.refresh_account)
        self._account_polls = 0
        self.reload_recents()
        self.render()
        if auto_probe:
            self.probe()

    def build_ui(self):
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)
        header = QtWidgets.QHBoxLayout()
        header.setSpacing(12)
        header.addWidget(StudioGlyph())
        header.addWidget(label("Big-Chicken Studio", "heading"), 1)
        self.advanced_toggle = button("高级", self.toggle_advanced, "quiet")
        self.advanced_toggle.setCheckable(True)
        self.advanced_toggle.setAccessibleName("高级启动设置")
        header.addWidget(self.advanced_toggle)
        self.details_button = button("详情", self.show_details, "quiet")
        self.details_button.setAccessibleName("启动诊断详情")
        header.addWidget(self.details_button)
        root.addLayout(header)

        self.scroll = QtWidgets.QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        body = QtWidgets.QWidget()
        body.setObjectName("launcherBody")
        content = QtWidgets.QVBoxLayout(body)
        content.setContentsMargins(0, 0, 4, 0)
        content.setSpacing(16)
        readiness = QtWidgets.QFrame()
        readiness.setObjectName("surface")
        rows = QtWidgets.QVBoxLayout(readiness)
        rows.setContentsMargins(12, 12, 12, 12)
        rows.setSpacing(8)
        self.account_row = ReadinessRow("ChatGPT")
        self.codex_row = ReadinessRow("Codex")
        self.houdini_row = ReadinessRow("Houdini")
        for widget in (self.account_row, self.codex_row, self.houdini_row):
            rows.addWidget(widget)
        actions = QtWidgets.QHBoxLayout()
        actions.addStretch()
        self.reopen_login = button("重新打开登录页", lambda: self.account_action("reopen_login"), "quiet")
        self.cancel_login = button("取消登录", lambda: self.account_action("cancel_login"), "quiet")
        self.logout = button("退出登录", lambda: self.account_action("logout"), "quiet")
        for widget in (self.reopen_login, self.cancel_login, self.logout):
            actions.addWidget(widget)
        rows.addLayout(actions)
        content.addWidget(readiness)

        self.context_notice = QtWidgets.QFrame()
        self.context_notice.setObjectName("surface")
        context = QtWidgets.QVBoxLayout(self.context_notice)
        self.context_summary = label("", wrap=True)
        self.context_summary.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Preferred)
        context.addWidget(self.context_summary)
        self.return_normal = button("返回常规启动", self.leave_legacy, "quiet")
        context.addWidget(self.return_normal, 0, QtCore.Qt.AlignLeft)
        content.addWidget(self.context_notice)

        row = QtWidgets.QHBoxLayout()
        self.scene_title = label("最近场景", "sectionTitle")
        row.addWidget(self.scene_title, 1)
        self.open_button = button("打开 HIP…", self.choose_hip)
        self.empty_button = button("空场景", self.select_empty)
        self.empty_button.setCheckable(True)
        self.empty_button.setAccessibleName("Start Empty · 选择空场景")
        row.addWidget(self.open_button)
        row.addWidget(self.empty_button)
        content.addLayout(row)
        self.recents = QtWidgets.QListWidget()
        self.recents.setAccessibleName("Recent HIP · 最近场景")
        self.recents.setTextElideMode(QtCore.Qt.ElideMiddle)
        self.recents.setMinimumHeight(144)
        self.recents.setMaximumHeight(228)
        self.recents.setAcceptDrops(False)
        self.recents.itemClicked.connect(self.select_recent)
        self.recents.itemDoubleClicked.connect(self.launch_recent)
        self.recents.itemActivated.connect(self.launch_recent)
        content.addWidget(self.recents)
        self.empty_hint = label("打开一个 HIP，或选择空场景开始。也可以将一个 HIP 文件拖到这里。", "muted", True)
        content.addWidget(self.empty_hint)
        row = QtWidgets.QHBoxLayout()
        self.relocate = button("重新定位…", self.relocate_recent, "quiet")
        self.remove_recent = button("从最近列表移除", self.forget_recent, "quiet")
        row.addWidget(self.relocate)
        row.addWidget(self.remove_recent)
        row.addStretch()
        content.addLayout(row)

        self.advanced = QtWidgets.QFrame()
        self.advanced.setObjectName("surface")
        advanced = QtWidgets.QVBoxLayout(self.advanced)
        advanced.setContentsMargins(12, 12, 12, 12)
        advanced.setSpacing(8)
        advanced.addWidget(label("程序选择", "sectionTitle"))
        advanced.addWidget(label("Codex 路径覆盖 · 留空自动发现", "muted", True))
        row = QtWidgets.QHBoxLayout()
        self.codex = QtWidgets.QLineEdit()
        self.codex.setAccessibleName("Codex 高级路径覆盖")
        self.codex.setPlaceholderText("自动选择兼容安装")
        self.codex.textEdited.connect(lambda _text: self.overrides_changed("codex"))
        self.codex_browse = button("选择…", self.choose_codex)
        row.addWidget(self.codex, 1)
        row.addWidget(self.codex_browse)
        advanced.addLayout(row)
        advanced.addWidget(label("Houdini 安装", "muted"))
        row = QtWidgets.QHBoxLayout()
        self.houdini = QtWidgets.QComboBox()
        self.houdini.setAccessibleName("Houdini 安装")
        self.houdini.setMinimumContentsLength(12)
        self.houdini.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.houdini.addItem("自动选择", "")
        self.houdini.currentIndexChanged.connect(lambda _index: self.overrides_changed("houdini"))
        self.houdini_browse = button("选择…", self.choose_houdini)
        row.addWidget(self.houdini, 1)
        row.addWidget(self.houdini_browse)
        advanced.addLayout(row)
        row = QtWidgets.QHBoxLayout()
        self.recheck = button("重新检查环境", self.probe)
        self.install_guide = button("Codex 安装指引", self.open_install_guide, "quiet")
        row.addWidget(self.recheck)
        row.addWidget(self.install_guide)
        row.addStretch()
        advanced.addLayout(row)
        self.environment_details = label("", "muted", True)
        self.environment_details.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        self.environment_details.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Preferred)
        advanced.addWidget(self.environment_details)
        advanced.addWidget(label("旧上下文", "sectionTitle"))
        advanced.addWidget(label("显式访问本安装的旧数据。历史记录不能确认本次应打开的 HIP。", "muted", True))
        self.load_legacy = button("查看本安装的旧上下文", self.reload_legacy, "quiet")
        advanced.addWidget(self.load_legacy, 0, QtCore.Qt.AlignLeft)
        self.legacy_list = QtWidgets.QListWidget()
        self.legacy_list.setAccessibleName("本安装旧上下文 · 原身份与原位置")
        self.legacy_list.setTextElideMode(QtCore.Qt.ElideMiddle)
        self.legacy_list.setMinimumHeight(100)
        self.legacy_list.setMaximumHeight(180)
        self.legacy_list.currentItemChanged.connect(self.legacy_selected)
        self.legacy_list.hide()
        advanced.addWidget(self.legacy_list)
        self.legacy_details = label("尚未读取旧数据。", "muted", True)
        self.legacy_details.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        self.legacy_details.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Preferred)
        advanced.addWidget(self.legacy_details)
        self.enter_legacy = button("选择 HIP 并进入原上下文…", self.choose_legacy_hip)
        self.enter_legacy.hide()
        advanced.addWidget(self.enter_legacy, 0, QtCore.Qt.AlignLeft)
        self.advanced.hide()
        content.addWidget(self.advanced)
        self.error_details = ErrorDetails()
        content.addWidget(self.error_details)
        content.addStretch()
        self.scroll.setWidget(body)
        root.addWidget(self.scroll, 1)

        status = QtWidgets.QHBoxLayout()
        self.status = label("", wrap=True)
        self.status.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Preferred)
        status.addWidget(self.status, 1)
        root.addLayout(status)
        self.footer = QtWidgets.QBoxLayout(QtWidgets.QBoxLayout.LeftToRight)
        self.footer.setSpacing(12)
        self.target_summary = label("", wrap=True)
        self.target_summary.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Preferred)
        self.footer.addWidget(self.target_summary, 1)
        self.launch_button = button("正在检查…", self.primary_action, "primary")
        self.launch_button.setMinimumHeight(40)
        self.footer.addWidget(self.launch_button)
        root.addLayout(self.footer)
        self.setTabOrder(self.open_button, self.empty_button)
        self.setTabOrder(self.empty_button, self.recents)
        self.setTabOrder(self.recents, self.launch_button)
        self.setTabOrder(self.launch_button, self.advanced_toggle)

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
                self._snapshot.get("account", {}).get("status") == "signed_in")

    def render(self):
        if self._closed:
            return
        snapshot = self._snapshot
        account, codex, houdini = (snapshot.get(key, {}) for key in ("account", "codex", "houdini"))
        status = account.get("status", "unknown")
        account_text = {"signed_in": "已登录 ChatGPT", "signed_out": "需要使用 ChatGPT 登录",
                        "waiting": "等待浏览器登录", "unknown": "账号状态暂未确认",
                        "other": "当前为其他认证方式"}.get(status, "账号状态暂未确认")
        if status == "signed_in" and account.get("email"):
            account_text += " · " + str(account["email"])
        self.account_row.set_status(account_text, "success" if status == "signed_in" else "warning")
        cs = codex.get("state", "checking")
        self.codex_row.set_status("已通过检查 · " + str(codex.get("version") or "") if cs == "ready" else
                                 {"checking": "正在检查", "missing": "未找到可用安装",
                                  "incompatible": "所选版本不兼容", "error": "暂时无法完成检查"}.get(cs, "尚未确认"),
                                 "success" if cs == "ready" else "neutral" if cs == "checking" else "warning")
        self.houdini_row.set_status("已找到 " + str(houdini.get("version") or "安装") + " · 许可证在启动时确认"
                                   if houdini.get("state") == "found" else "未找到 Houdini 安装",
                                   "neutral" if houdini.get("state") == "found" else "warning")
        active = self._launch_active()
        busy = "probe" in self._pending or "account" in self._pending
        for control in (self.open_button, self.empty_button, self.recents, self.relocate, self.remove_recent,
                        self.codex, self.codex_browse, self.houdini, self.houdini_browse, self.recheck,
                        self.load_legacy, self.legacy_list, self.return_normal):
            control.setEnabled(not active)
        self.load_legacy.setEnabled(not active and "legacy" not in self._pending)
        self.enter_legacy.setEnabled(not active and self.legacy_list.currentItem() is not None)
        self.recheck.setEnabled(not active and not busy)
        self.reopen_login.setVisible(status == "waiting" and not active)
        self.cancel_login.setVisible(status == "waiting" and not active)
        self.reopen_login.setEnabled(not busy)
        self.cancel_login.setEnabled(not busy)
        self.logout.setVisible(status == "signed_in" and not active)
        self.logout.setEnabled(not busy)
        self.empty_button.setChecked(self._target is not None and self._target.kind == "empty")
        legacy = self._legacy_context
        self.scene_title.setText("本次目标" if legacy is not None else "最近场景")
        self.context_notice.setVisible(legacy is not None)
        if legacy is not None:
            self.context_summary.setText("原上下文 · " + str(legacy.get("name") or legacy["workspace_id"]) +
                                         "\n本次将打开下方所选 HIP；历史记录不代表当前场景事实。")
        self.empty_hint.setVisible(not self._recent_records and legacy is None)
        self.recents.setVisible(bool(self._recent_records) and legacy is None)
        self.relocate.setVisible(bool(self._recent_path) and legacy is None)
        self.remove_recent.setVisible(bool(self._recent_path) and legacy is None)
        self.empty_button.setText("返回并选择空场景" if legacy is not None else "空场景")
        target = self._launch_target if active else self._target
        if target is None:
            self.target_summary.setText("请选择可用的 HIP 或空场景")
        elif target.kind == "empty":
            self.target_summary.setText("空场景\n未保存的新场景")
        else:
            self.target_summary.setText(Path(target.path).name + "\n" + str(Path(target.path).parent))
        self.target_summary.setToolTip(str(target.path) if target and target.path else "每次启动空场景使用独立的内部上下文")
        self.launch_button.setEnabled(True)
        record = self._launch_record or {}
        state = record.get("state")
        if self._launch_phase:
            title = "正在检查启动条件…" if self._launch_phase == "prepare" else "正在启动 Houdini…"
            self.launch_button.setEnabled(False)
            message = title
        elif active:
            if state == "target_opened" and record.get("target_opened"):
                title, message = "Studio 已打开", "已确认打开目标场景。关闭此窗口不会关闭 Houdini。"
                self.launch_button.setEnabled(False)
            elif state == "runtime_connected":
                title, message = "查询场景状态", "Studio 已连接，目标场景是否打开尚未确认。"
            elif state in {"accepted", "starting"}:
                title, message = "正在连接 Studio…", "Houdini 已接纳启动，正在等待连接和目标场景确认。"
                self.launch_button.setEnabled(False)
            else:
                title, message = "查询启动状态", "上次启动结果尚未确认，请查询原请求。"
            if "status" in self._pending:
                self.launch_button.setEnabled(False)
        elif busy:
            title, message = "正在检查…", "正在确认环境和账号；仍可选择场景。"
            self.launch_button.setEnabled(False)
        elif self._needs_probe:
            title, message = "重新检查环境", "启动条件已变化，请重新确认后继续。"
        elif cs in {"missing", "incompatible"}:
            title, message = "选择 Codex 安装", "选择兼容安装，或在高级设置中查看安装指引。"
        elif cs != "ready":
            title, message = "重新检查环境", "尚未确认可用的 Codex。"
        elif houdini.get("state") != "found":
            title, message = "选择 Houdini 安装", "选择本机 Houdini 后继续。"
        elif status in {"signed_out", "other"}:
            title, message = "使用 ChatGPT 登录", "登录通过官方浏览器流程完成。"
        elif status == "waiting":
            title, message = "等待浏览器登录…", "完成后会重新确认账号，也可以取消本次登录。"
            self.launch_button.setEnabled(False)
        elif status != "signed_in":
            title, message = "重新检查账号", "暂时无法确认账号；这不表示已经登出。"
        elif self._target is None or "target" in self._pending:
            title, message = "选择启动目标", "请选择可用的 HIP 或空场景。"
            self.launch_button.setEnabled(False)
        else:
            title, message = "Launch Studio", "启动目标已选定。" if state != "closed" else "上次会话已关闭，可启动所选场景。"
        self.launch_button.setText(title)
        self.launch_button.setAccessibleName(title)
        self.status.setText(message)
        self._sync_environment_controls()

    def _sync_environment_controls(self):
        houdini = self._snapshot.get("houdini", {})
        selected = (self.houdini.currentData() if "houdini" in self._overrides_dirty else
                    houdini.get("path") or self.houdini.currentData())
        self.houdini.blockSignals(True)
        for item in houdini.get("installations", []):
            if self.houdini.findData(item["path"]) < 0:
                self.houdini.addItem(item["label"], item["path"])
                self.houdini.setItemData(self.houdini.count() - 1, item["path"], QtCore.Qt.ToolTipRole)
        index = self.houdini.findData(selected)
        if index >= 0:
            self.houdini.setCurrentIndex(index)
        self.houdini.blockSignals(False)
        codex = self._snapshot.get("codex", {})
        if "codex" not in self._overrides_dirty and codex.get("path"):
            self.codex.setText(codex["path"])
        self.environment_details.setText("Codex：" + str(codex.get("path") or "尚未选定") +
                                         "\nHoudini：" + str(houdini.get("path") or "尚未选定") +
                                         "\n账号类型：" + str(self._snapshot.get("account", {}).get("type") or "尚未确认") +
                                         "\n数据位置：" + str(self.paths.data_root) +
                                         ("\n启动请求：" + self._request_id if self._request_id else ""))

    def show_failure(self, failure):
        self.error_details.set_failure(failure)

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
            self.error_details.set_failure(None)
        if value.get("account", {}).get("status") == "waiting":
            self.account_poll.start()
        else:
            self.account_poll.stop()

    def account_action(self, method):
        if self._launch_active() or self._closed or self._onboarding is None:
            return
        if method == "login_start" and "account" in self._pending:
            return
        self._account_polls = 0
        owner = self._onboarding
        def complete(value):
            if isinstance(value, dict):
                self.apply_snapshot(value)
            if method in {"login_start", "reopen_login"}:
                url = value.get("auth_url") if isinstance(value, dict) else value
                if url:
                    self.open_url(url)
        self._submit("account", lambda: owner.call(method), complete, self.account_failed)
        self.render()

    def account_failed(self, failure):
        self.account_poll.stop()
        self._snapshot["account"] = {"status": "unknown"}
        self.show_failure(failure)

    def refresh_account(self):
        if self._closed or self._launch_active() or "account" in self._pending or self._onboarding is None:
            return
        if self.account_poll.isActive():
            self._account_polls += 1
            if self._account_polls >= 150:
                self.account_poll.stop()
                self._snapshot["account"] = {"status": "unknown", "message": "请主动重新检查登录状态"}
                self.render()
                return
        owner = self._onboarding
        self._submit("account", lambda: owner.call("account_read"), self.apply_snapshot, self.account_failed)
        self.render()

    def primary_action(self):
        if self._launch_active():
            self.query_launch()
        elif "probe" in self._pending or "account" in self._pending:
            return
        elif self._needs_probe:
            self.probe()
        elif self._snapshot.get("codex", {}).get("state") in {"missing", "incompatible"}:
            self.choose_codex()
        elif self._snapshot.get("codex", {}).get("state") != "ready":
            self.probe()
        elif self._snapshot.get("houdini", {}).get("state") != "found":
            self.choose_houdini()
        elif self._snapshot.get("account", {}).get("status") in {"signed_out", "other"}:
            self.account_action("login_start")
        elif self._snapshot.get("account", {}).get("status") != "signed_in":
            self.refresh_account()
        else:
            self.start_session()

    def reload_recents(self):
        self._submit("recent", lambda: self.catalog.recent(limit=20), self.recents_loaded)

    def reload_legacy(self):
        if self._launch_active() or "legacy" in self._pending:
            return
        self.legacy_details.setText("正在读取本安装原位置的上下文记录…")
        self._submit("legacy", self.catalog.legacy_workspaces, self.legacy_loaded)
        self.render()

    def legacy_loaded(self, records):
        self.legacy_list.clear()
        for record in records or []:
            item = QtWidgets.QListWidgetItem(str(record.get("name") or "旧上下文") +
                                            "\nID · " + record["workspace_id"])
            item.setData(QtCore.Qt.UserRole, record)
            self.legacy_list.addItem(item)
        found = self.legacy_list.count() > 0
        self.legacy_list.setVisible(found)
        self.enter_legacy.setVisible(found)
        self.legacy_details.setText("请选择原记录；关联 HIP 尚未确认。" if found else
                                   "本安装的 .runtime 中没有可列出的旧上下文。")

    def legacy_selected(self, item, _previous=None):
        if item is not None:
            record = item.data(QtCore.Qt.UserRole)
            paths = AppPaths.for_legacy(self._normal_paths.root)
            work = paths.workspace(record["workspace_id"]) / "work"
            self.legacy_details.setText("原工作目录：" + str(work) + "\n原账号目录：" + str(paths.codex_home) +
                                       "\n关联 HIP：未确认。进入前须明确选择现存 HIP；原记录留在原位置。")
        self.render()

    def choose_legacy_hip(self):
        item = self.legacy_list.currentItem()
        if self._launch_active() or item is None:
            return
        if self._onboarding_for_paths is None:
            self.show_failure(ApiFailure("当前启动服务不支持切换数据位置", code="PROFILE_SWITCH_UNAVAILABLE"))
            return
        record = dict(item.data(QtCore.Qt.UserRole))
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "为原上下文明确选择 HIP", "", "Houdini scenes (*.hip *.hiplc *.hipnc)")
        if not path:
            return
        self._target = None
        self._user_chose_target = True
        def selected(target):
            self.switch_context(AppPaths.for_legacy(self._normal_paths.root), record, target)
        self._submit("target", lambda: self.target_factory.hip(path), selected)
        self.render()

    def switch_context(self, paths, record, target):
        if self._closed or self._launch_active():
            return
        if record is not None and target.kind != "hip":
            self.show_failure(ApiFailure("进入原上下文须明确选择现存 HIP", code="LEGACY_HIP_REQUIRED"))
            return
        # All old account I/O completes and closes under the guard before the new
        # owner's factory runs. The factory binds these paths, never mutable UI state.
        self.paths, self._legacy_context, self._target = paths, record, target
        self._factory = ((lambda bound_paths=paths: self._onboarding_for_paths(bound_paths))
                         if record is not None else self._normal_factory)
        self._pending.pop("target", None)
        self._pending.pop("recent-edit", None)
        self._recent_path = None
        self._user_chose_target = True
        self._request_id, self._launch_record, self._prepared = None, None, None
        self._launch_version += 1
        self._snapshot = {}
        self._overrides_dirty.clear()
        self.codex.clear()
        self.houdini.blockSignals(True)
        self.houdini.clear()
        self.houdini.addItem("自动选择", "")
        self.houdini.blockSignals(False)
        self.error_details.set_failure(None)
        self.probe()

    def leave_legacy(self):
        if self._legacy_context is not None:
            self.switch_context(self._normal_paths, None, self.target_factory.empty())

    def recents_loaded(self, records):
        self._recent_records = list(records or [])
        self.recents.clear()
        for record in self._recent_records:
            text = record["name"] + ("  ·  找不到文件" if record.get("missing") else "")
            stamp = record.get("last_used_at")
            date = QtCore.QDateTime.fromSecsSinceEpoch(int(stamp)).toString("yyyy-MM-dd HH:mm") if stamp else ""
            item = QtWidgets.QListWidgetItem(text + "\n" + record["directory"] + ("\n" + date if date else ""))
            item.setData(QtCore.Qt.UserRole, record)
            item.setToolTip(record["path"])
            self.recents.addItem(item)
            if record["path"] == self._recent_path:
                self.recents.setCurrentItem(item)
        if self._recent_records and not self._user_chose_target:
            self.recents.setCurrentRow(0)
            self.select_recent(self.recents.item(0))
        self.render()

    def select_recent(self, item):
        if self._launch_active():
            return
        record = item.data(QtCore.Qt.UserRole)
        self._recent_path = record["path"]
        self._user_chose_target = True
        self.select_path(record["path"])

    def launch_recent(self, item):
        ready = self._ready() and not self._launch_active()
        record = item.data(QtCore.Qt.UserRole)
        self._recent_path = record["path"]
        self._user_chose_target = True
        self.select_path(record["path"], launch_after=ready)

    def select_path(self, path, *, launch_after=False):
        if self._launch_active():
            return
        self._target = None
        self._user_chose_target = True
        def selected(target):
            self._target = target
            self.error_details.set_failure(None)
            self.render()
            if launch_after and self._ready():
                self.start_session()
        self._submit("target", lambda: self.target_factory.hip(path), selected)
        self.render()

    def select_empty(self):
        if self._launch_active():
            return
        if self._legacy_context is not None:
            self.leave_legacy()
            return
        self._pending.pop("target", None)
        self._target = self.target_factory.empty()
        self._user_chose_target = True
        self._recent_path = None
        self.recents.clearSelection()
        self.error_details.set_failure(None)
        self.render()

    def choose_hip(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "打开 HIP", "", "Houdini scenes (*.hip *.hiplc *.hipnc)")
        if path:
            self._recent_path = None
            self.select_path(path)

    def relocate_recent(self):
        old_path = self._recent_path
        if not old_path or self._launch_active():
            return
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "重新定位 HIP", "", "Houdini scenes (*.hip *.hiplc *.hipnc)")
        if path:
            def done(_value):
                if self._recent_path == old_path:
                    self._recent_path = path
                    self.select_path(path)
                self.reload_recents()
            self._submit("recent-edit", lambda: self.catalog.relocate_recent(old_path, path), done)

    def forget_recent(self):
        path = self._recent_path
        if not path or self._launch_active():
            return
        def done(_value):
            if self._recent_path == path:
                self.select_empty()
            self.reload_recents()
        self._submit("recent-edit", lambda: self.catalog.remove_recent(path), done)

    def choose_codex(self):
        self.advanced_toggle.setChecked(True)
        self.toggle_advanced()
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "选择 Codex", "", "Codex (codex.exe codex)")
        if path:
            self.codex.setText(path)
            self.overrides_changed("codex")

    def choose_houdini(self):
        self.advanced_toggle.setChecked(True)
        self.toggle_advanced()
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "选择 Houdini", "", "Houdini (houdini.exe houdinifx.exe houdini)")
        if path:
            index = self.houdini.findData(path)
            if index < 0:
                self.houdini.addItem(Path(path).parent.parent.name, path)
                index = self.houdini.count() - 1
            self.houdini.setCurrentIndex(index)

    def toggle_advanced(self):
        self.advanced.setVisible(self.advanced_toggle.isChecked())

    def show_details(self):
        if self.error_details.failure is not None:
            self.error_details.toggle.setChecked(True)
        else:
            self.advanced_toggle.setChecked(True)
            self.toggle_advanced()
        self.details_timer.start(0)

    def reveal_details(self):
        if not self._closed:
            target = self.error_details if self.error_details.failure is not None else self.advanced
            self.scroll.ensureWidgetVisible(target)

    def open_url(self, value):
        url = QtCore.QUrl(str(value))
        if url.scheme() not in {"https", "http"} or not url.host() or url.userInfo():
            self.show_failure(ApiFailure("登录地址无效，请重新检查账号", code="LOGIN_URL_INVALID"))
            return
        if not self._browser_open(url):
            self.show_failure(ApiFailure("未能打开浏览器，可重新打开登录页", code="BROWSER_UNAVAILABLE"))

    def open_install_guide(self):
        self.open_url("https://developers.openai.com/codex/cli/")

    def start_session(self):
        if self._closed or self._launch_active() or not self._ready() or self._target is None or self._onboarding is None:
            return
        self._request_id = new_id()
        self._launch_target = self._target
        self._launch_paths = self.paths
        self._launch_legacy_workspace_id = (self._legacy_context or {}).get("workspace_id")
        self._launch_record = None
        self._launch_error = None
        self._launch_version += 1
        self._launch_phase = "prepare"
        self._remembered = False
        self.account_poll.stop()
        self.error_details.set_failure(None)
        owner = self._onboarding
        self._submit("prepare", lambda: owner.call("prepare_launch"), self.prepared, self.prepare_failed)
        self.render()

    def prepared(self, choices):
        if not isinstance(choices, dict):
            self.prepare_failed(ApiFailure("启动条件尚未确认，请重新检查", code="PREPARE_UNCONFIRMED"))
            return
        if Path(choices.get("codex_home") or "").resolve() != self._launch_paths.codex_home:
            self.prepare_failed(ApiFailure("账号与启动的数据位置不一致，请重新检查环境", code="PROFILE_MISMATCH"))
            return
        self._prepared = choices
        request_id, target = self._request_id, self._launch_target
        paths = self._launch_paths
        arguments = {"request_id": request_id}
        if self._launch_legacy_workspace_id is not None:
            arguments["legacy_workspace_id"] = self._launch_legacy_workspace_id
        self._launch_phase = "submit"
        self._submit("launch", lambda: self._launch(paths, target, choices["houdini_path"],
                     choices["codex_path"], **arguments), self.launched, self.launch_failed)

    def prepare_failed(self, failure):
        # launch_target has not been called, so no admission could have happened.
        self._request_id = None
        self._launch_phase = None
        self.show_failure(failure)
        self._snapshot["account"] = {"status": "unknown"}
        self._needs_probe = True

    def launched(self, value):
        self._launch_phase = None
        self._launch_version += 1
        self.apply_launch_status(value)
        if self._launch_active():
            self.poll.start()

    def launch_failed(self, failure):
        # The exception alone cannot prove that Popen or admission did not occur.
        self._launch_phase = None
        self._launch_record = {"request_id": self._request_id, "state": "unknown", "process_may_exist": True,
                               "target": self._launch_target.to_dict()}
        self._launch_error = failure
        self.show_failure(failure)
        self.poll.start()

    def query_launch(self):
        if self._closed or not self._request_id or "status" in self._pending:
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
            if self.error_details.failure is self._launch_error:
                self.error_details.set_failure(None)
            self._launch_error = None
        state = value.get("state")
        if state == "target_opened" and value.get("target_opened") and not self._remembered:
            self._remembered = True
            owner, path = self._onboarding, (self._prepared or {}).get("houdini_path")
            if owner is not None and path:
                self._submit("remember", lambda: owner.call("remember_houdini", path), lambda _value: None)
            self.reload_recents()
        if state in {"closed", "rejected"} and not value.get("process_may_exist"):
            self.poll.stop()
            self.probe()

    @staticmethod
    def dropped_path(mime):
        urls = mime.urls()
        if len(urls) != 1 or not urls[0].isLocalFile() or urls[0].hasQuery() or urls[0].hasFragment():
            return None
        path = urls[0].toLocalFile()
        return path if Path(path).suffix.lower() in {".hip", ".hiplc", ".hipnc"} else None

    def dragEnterEvent(self, event):
        if not self._launch_active() and self.dropped_path(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        path = self.dropped_path(event.mimeData())
        if self._launch_active() or not path:
            event.ignore()
            self.show_failure(ApiFailure("请拖入一个本地 HIP 文件", code="HIP_DROP_INVALID"))
            return
        self._recent_path = None
        self.select_path(path)
        event.acceptProposedAction()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.footer.setDirection(QtWidgets.QBoxLayout.TopToBottom if self.width() < 660 else QtWidgets.QBoxLayout.LeftToRight)

    def closeEvent(self, event):
        self._closed = True
        self._generation += 1
        self.poll.stop()
        self.account_poll.stop()
        self.probe_delay.stop()
        self.details_timer.stop()
        owner = self._onboarding
        if owner is not None:
            owner.cancelled.set()
            # A worker waits for outstanding account I/O; the Qt thread never does.
            QtCore.QThreadPool.globalInstance().start(Task(owner.close))
        super().closeEvent(event)
