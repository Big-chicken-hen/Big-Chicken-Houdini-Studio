"""User-driven responses to native Codex server requests."""
from __future__ import annotations

import json

from PySide6 import QtCore, QtGui, QtWidgets

from .icons import set_button_icon
from .shared import button, label
from .theme import apply_theme


def permission_lines(value, prefix=""):
    """Present every permission field; this is display-only, never a policy filter."""
    names = {"fileSystem": "文件访问", "filesystem": "文件访问", "read": "读取", "write": "写入",
             "network": "网络访问", "enabled": "启用", "host": "主机", "port": "端口", "protocol": "协议",
             "allowedDomains": "允许的域名", "deniedDomains": "拒绝的域名"}
    if isinstance(value, dict):
        return [line for key, item in value.items()
                for line in permission_lines(item, (prefix + " · " if prefix else "") + names.get(key, str(key)))]
    if isinstance(value, list):
        return [line for item in value for line in permission_lines(item, prefix)] or [prefix + "：未列出条目"]
    text = "是" if value is True else "否" if value is False else "未指定" if value is None else str(value)
    if prefix.endswith(("读取", "写入")) and isinstance(value, str):
        text = QtCore.QDir.cleanPath(value)
    return [(prefix + "：" if prefix else "") + text]


class RequestCard(QtWidgets.QFrame):
    respond = QtCore.Signal(object, object)

    def __init__(self, request, parent=None):
        super().__init__(parent)
        self.request = request
        self.request_id = request["request_id"]
        self.setObjectName("requestCard")
        self.layout = QtWidgets.QVBoxLayout(self)
        self.layout.setContentsMargins(12, 12, 12, 12)
        self.layout.setSpacing(8)
        self.inputs = {}
        self.actions = []
        self.waiting_response = False
        self.response_unknown = False
        self.error = label("", "warning", True)
        method, params = request.get("method"), request.get("params", {})
        self.layout.addWidget(label("需要你的回应", "messageAuthor"))
        descriptions = {"item/commandExecution/requestApproval": "请求执行命令", "item/fileChange/requestApproval": "请求修改文件",
                        "item/permissions/requestApproval": "请求额外权限", "item/tool/requestUserInput": "请回答以下问题"}
        self.layout.addWidget(label(str(params.get("reason") or params.get("message") or descriptions.get(method, "原生请求")), wrap=True))
        details = QtWidgets.QPlainTextEdit()
        details.setReadOnly(True)
        details.setPlainText(json.dumps(params, ensure_ascii=False, indent=2))
        details.setMaximumHeight(140)
        details.hide()
        toggle = button("完整请求", lambda: details.setVisible(not details.isVisible()), "quiet")
        set_button_icon(toggle, "chevron-right", text="完整请求", size=16)
        self.full_request = details
        self.layout.addWidget(self.error)
        self.error.hide()
        self.row = QtWidgets.QBoxLayout(QtWidgets.QBoxLayout.LeftToRight)
        self.row.setSpacing(6)
        if method in {"item/commandExecution/requestApproval", "item/fileChange/requestApproval"}:
            if params.get("command"):
                self.layout.addWidget(label(str(params["command"]), wrap=True))
            if params.get("cwd"):
                self.layout.addWidget(label("工作目录  " + str(params["cwd"]), "muted", True))
            if params.get("grantRoot"):
                self.layout.addWidget(label("授权根目录  " + QtCore.QDir.cleanPath(str(params["grantRoot"])), wrap=True))
            if params.get("networkApprovalContext"):
                self.add_permissions(params["networkApprovalContext"], "网络访问")
            if params.get("additionalPermissions"):
                self.add_permissions(params["additionalPermissions"], "附加权限")
            allowed = params.get("availableDecisions") or ["accept", "decline", "cancel"]
            names = {"accept": "允许本次", "acceptForSession": "允许本会话", "decline": "拒绝", "cancel": "取消请求"}
            for decision in allowed:
                if isinstance(decision, str) and decision in names:
                    self.action(names[decision], lambda d=decision: self.submit({"decision": d}))
            if not self.actions:
                self.layout.addWidget(label("当前原生审批选项暂不受支持。", "warning", True))
        elif method == "item/permissions/requestApproval":
            self.add_permissions(params.get("permissions", {}))
            self.layout.addWidget(label("请在下方选择仅本轮允许，或允许本会话。", "muted", True))
            self.action("允许本轮", lambda: self.submit({"permissions": params.get("permissions", {}), "scope": "turn"}))
            self.action("允许本会话", lambda: self.submit({"permissions": params.get("permissions", {}), "scope": "session"}))
            self.action("拒绝", lambda: self.submit({"permissions": {}, "scope": "turn"}))
        elif method == "item/tool/requestUserInput":
            for question in params.get("questions", []):
                self.add_question(question)
            self.action("提交回答", self.answer_questions)
        elif method == "mcpServer/elicitation/request":
            if params.get("mode") == "url":
                url = QtCore.QUrl(params.get("url", ""))
                self.layout.addWidget(label(url.toDisplayString(), "muted", True))
                open_button = button("打开网页", lambda: QtGui.QDesktopServices.openUrl(url))
                open_button.setEnabled(url.scheme() in {"https", "http"})
                self.layout.addWidget(open_button)
                self.action("已完成，继续", lambda: self.submit({"action": "accept", "content": None}))
            elif (params.get("_meta", {}).get("codex_approval_kind") == "mcp_tool_call" and
                  params.get("requestedSchema") == {"type": "object", "properties": {}}):
                self.action("允许本次", lambda: self.submit({"action": "accept", "content": {}}))
            else:
                schema = params.get("requestedSchema", {})
                self.layout.addWidget(label("按下列原生字段要求填写 JSON。提交前可检查完整内容。", "muted", True))
                schema_view = QtWidgets.QPlainTextEdit(json.dumps(schema, ensure_ascii=False, indent=2))
                schema_view.setReadOnly(True)
                schema_view.setMaximumHeight(150)
                self.layout.addWidget(schema_view)
                self.form = QtWidgets.QPlainTextEdit()
                self.form.setPlaceholderText('{"字段名": "填写值"}')
                self.form.setMaximumHeight(130)
                self.layout.addWidget(self.form)
                self.action("提交表单", self.answer_form)
            self.action("拒绝", lambda: self.submit({"action": "decline", "content": None}))
            self.action("取消", lambda: self.submit({"action": "cancel", "content": None}))
        else:
            self.layout.addWidget(label("此原生请求尚未支持。请求保持待处理，可停止当前 Codex 轮次。", "warning", True))
        self.row.addStretch()
        self.layout.addLayout(self.row)
        self.layout.addWidget(toggle, 0, QtCore.Qt.AlignLeft)
        self.layout.addWidget(details)
        self.update_request(request)

    def add_permissions(self, value, prefix=""):
        for text in permission_lines(value, prefix):
            detail = label(text, wrap=True)
            detail.setToolTip(text)
            detail.setMinimumWidth(0)
            self.layout.addWidget(detail)

    def action(self, title, callback):
        control = button(title, lambda: callback())
        self.row.addWidget(control)
        self.actions.append(control)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        margins = self.layout.contentsMargins()
        action_width = sum(control.minimumSizeHint().width() for control in self.actions) + max(0, len(self.actions) - 1) * 6
        self.row.setDirection(QtWidgets.QBoxLayout.TopToBottom if action_width > self.width() - margins.left() - margins.right()
                              else QtWidgets.QBoxLayout.LeftToRight)

    def add_question(self, question):
        self.layout.addWidget(label(question.get("header", ""), "eyebrow"))
        self.layout.addWidget(label(question.get("question", ""), wrap=True))
        combo = QtWidgets.QComboBox()
        combo.setPlaceholderText("请选择…")
        options = question.get("options") or []
        for option in options:
            combo.addItem(option.get("label", ""), option.get("label", ""))
            combo.setItemData(combo.count() - 1, option.get("description", ""), QtCore.Qt.ToolTipRole)
        combo.setCurrentIndex(-1)
        combo.setVisible(bool(options))
        self.layout.addWidget(combo)
        free = QtWidgets.QLineEdit()
        free.setPlaceholderText("填写你的回答" if not options else "或填写自己的回答")
        free.setVisible(not options or bool(question.get("isOther")))
        if question.get("isSecret"):
            free.setEchoMode(QtWidgets.QLineEdit.Password)
        self.layout.addWidget(free)
        self.inputs[question["id"]] = (combo, free)

    def answer_questions(self):
        answers = {}
        for key, (combo, free) in self.inputs.items():
            answer = free.text().strip() if not free.isHidden() else ""
            answer = answer or combo.currentData()
            if not answer:
                self.failed("请回答每个问题后提交。")
                return
            answers[key] = {"answers": [answer]}
        self.submit({"answers": answers})

    def answer_form(self):
        try:
            content = json.loads(self.form.toPlainText())
            if not isinstance(content, dict):
                raise ValueError("表单必须是 JSON 对象。")
            schema = self.request.get("params", {}).get("requestedSchema", {})
            for name in schema.get("required", []):
                if name not in content:
                    raise ValueError("缺少必填字段：" + name)
        except ValueError as exc:
            self.failed(str(exc))
            return
        self.submit({"action": "accept", "content": content})

    def submit(self, result):
        if self.waiting_response or self.response_unknown:
            return
        self.waiting_response = True
        self.error.hide()
        for control in self.actions:
            control.setEnabled(False)
        self.respond.emit(self.request_id, result)

    def failed(self, message):
        if self.waiting_response or getattr(message, "code", None) == "APPROVAL_RESPONSE_UNKNOWN":
            self.mark_response_unknown()
            return
        self.error.setText(message)
        self.error.show()
        for control in self.actions:
            control.setEnabled(True)

    def update_request(self, request):
        self.request = request
        if request.get("response_state") == "unknown":
            self.mark_response_unknown()

    def mark_response_unknown(self):
        self.response_unknown = True
        self.error.setText("本次回应是否送达尚未确认。请查询对话状态，确认前不能再次提交回应。")
        self.error.show()
        for control in self.actions:
            control.setEnabled(False)


class SessionTrustControl(QtWidgets.QFrame):
    """Explicit scene trust, projected from the Bridge's current conversation."""

    changed = QtCore.Signal()

    def __init__(self, api=None, parent=None):
        super().__init__(parent)
        self.api = api
        self.thread_id = None
        self.trust = {}
        self.busy = False
        self.uncertain = False
        self.querying = False
        self.request_revision = 0
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        row = QtWidgets.QHBoxLayout()
        self.status = label("当前对话：逐次确认", "muted", True)
        self.status.setParent(self)
        self.status.hide()
        self.toggle = button("授权…", self.show_details, "quiet")
        self.toggle.setAccessibleName("当前对话的场景操作授权")
        self.revoke = button("撤销", lambda: self.request_change(False), "quiet")
        self.revoke.setAccessibleName("撤销当前对话的场景操作授权")
        self.query = button("查询授权状态", self.query_state, "quiet")
        row.addWidget(self.toggle)
        layout.addLayout(row)
        self.details = QtWidgets.QFrame(self, QtCore.Qt.Popup)
        self.details.setObjectName("studioConsentPopup")
        apply_theme(self.details, popup=True)
        details_layout = QtWidgets.QVBoxLayout(self.details)
        details_layout.setContentsMargins(12, 12, 12, 12)
        details_layout.addWidget(label(
            "允许当前会话通过 Studio 读取、截图和修改 Houdini，对后续工具调用生效；"
            "当前已出现的审批仍需处理。授权包含本机 Python/HOM 执行，"
            "脚本可能产生场景外的影响；这项授权不会逐批审查全部副作用。"
            "清空场景、覆盖文件或大范围删除应先明确确认。其他工具和外部权限仍分别确认。"
            "撤销后恢复后续请求的逐次确认；已允许的请求和正在执行的修改不会被撤回。"
            "切换会话或重新启动后需要重新选择。", "muted", True))
        self.grant = button("允许此会话操作 Houdini", lambda: self.request_change(True), "primary")
        details_layout.addWidget(self.grant, 0, QtCore.Qt.AlignLeft)
        details_layout.addWidget(self.revoke, 0, QtCore.Qt.AlignLeft)
        details_layout.addWidget(self.query, 0, QtCore.Qt.AlignLeft)
        self.details.hide()
        self.feedback = label("", "warning", True)
        details_layout.addWidget(self.feedback)
        self.feedback.hide()
        self.render()

    def set_api(self, api):
        if api is not self.api:
            # A new authenticated endpoint has its own consent revision space,
            # even when it resumes a conversation with the same native ID.
            self.request_revision += 1
            self.thread_id, self.trust = None, {}
            self.busy = self.uncertain = self.querying = False
            self.details.hide()
            self.feedback.hide()
        self.api = api
        self.render()

    def closeEvent(self, event):
        self.set_api(None)
        super().closeEvent(event)

    def apply_state(self, value):
        thread_id = value.get("thread_id")
        trust = value.get("scene_trust") or {}
        revision, previous = trust.get("revision"), self.trust.get("revision")
        if (thread_id == self.thread_id and isinstance(revision, int) and isinstance(previous, int) and
                revision < previous):
            return
        if thread_id != self.thread_id:
            self.request_revision += 1
            self.busy = self.uncertain = self.querying = False
            self.details.hide()
            self.feedback.hide()
        self.thread_id = thread_id
        self.trust = trust
        self.render()

    def render(self):
        bound = bool(self.thread_id and self.trust.get("thread_id") == self.thread_id)
        known = bound and type(self.trust.get("enabled")) is bool and not self.uncertain
        pending = self.busy or self.trust.get("pending", False)
        enabled = known and self.trust.get("enabled") is True
        can_change = bool(self.api and known and type(self.trust.get("revision")) is int and
                          self.trust.get("can_change", False) and not pending)
        text = "当前对话：已授权" if enabled else "当前对话：逐次确认"
        if not known:
            text = "场景授权状态不可用"
        if pending:
            text = "正在更新场景授权…"
        elif self.uncertain or bound and self.trust.get("enabled") is None:
            text = "场景授权状态尚未确认"
        self.status.setText(text)
        self.toggle.setText("本对话已授权" if enabled else "逐次确认" if known and not pending else text)
        self.toggle.setVisible(True)
        self.toggle.setEnabled(bool(self.api and self.thread_id))
        self.grant.setEnabled(can_change and bool(self.trust.get("available")) and not enabled)
        self.revoke.setVisible(bool(enabled))
        self.revoke.setEnabled(can_change)
        self.query.setVisible(self.uncertain)
        self.query.setEnabled(bool(self.api) and not self.busy and not self.querying)
        reason = self.trust.get("reason") or ("请先建立会话连接。" if not known else "")
        for control in (self.toggle, self.grant, self.revoke):
            control.setToolTip(reason)

    def show_details(self):
        if self.details.isVisible():
            self.details.hide()
            return
        bounds = self.screen().availableGeometry()
        width = min(360, max(1, bounds.width() - 16))
        self.details.setFixedWidth(width)
        self.details.adjustSize()
        height = min(self.details.height(), bounds.height() - 16)
        self.details.resize(width, height)
        anchor = self.toggle.mapToGlobal(QtCore.QPoint(self.toggle.width(), 0))
        x = max(bounds.left() + 8, min(anchor.x() - width, bounds.right() - width - 7))
        y = max(bounds.top() + 8, min(anchor.y() - height - 4, bounds.bottom() - height - 7))
        self.details.move(x, y)
        self.details.show()

    def request_change(self, enabled):
        if (self.busy or self.uncertain or self.api is None or not self.thread_id or
                self.trust.get("thread_id") != self.thread_id or enabled and not self.trust.get("available") or
                type(self.trust.get("revision")) is not int or not self.trust.get("can_change") or
                self.trust.get("pending")):
            return
        thread_id = self.thread_id
        self.request_revision += 1
        revision = self.request_revision
        self.busy = True
        self.feedback.hide()
        self.render()

        def current():
            return thread_id == self.thread_id and revision == self.request_revision

        def done(value):
            if not current():
                return
            self.busy = False
            trust = value.get("scene_trust")
            if isinstance(trust, dict) and trust.get("thread_id") == thread_id:
                self.uncertain = False
                self.apply_state({"thread_id": thread_id, "scene_trust": trust})
                if trust.get("enabled") is enabled and not trust.get("pending"):
                    self.details.hide()
            else:
                self.uncertain = True
                self.render()
            self.changed.emit()

        def failed(message):
            if not current():
                return
            self.busy = False
            self.uncertain = True
            self.feedback.setText(str(message))
            self.feedback.show()
            self.render()
            self.query_state()

        accepted = self.api.call("POST", "/scene-trust", {"enabled": enabled, "thread_id": thread_id,
                                                         "revision": self.trust["revision"]},
                                 done=done, failed=failed)
        if accepted is False and current():
            self.busy = False
            self.render()

    def query_state(self):
        if self.api is None or self.busy or self.querying:
            return
        thread_id, revision = self.thread_id, self.request_revision
        self.querying = True
        self.render()

        def current():
            return thread_id == self.thread_id and revision == self.request_revision

        def done(value):
            if not current():
                return
            self.querying = False
            trust = value.get("scene_trust") or {}
            if value.get("thread_id") == thread_id and trust.get("thread_id") == thread_id:
                self.apply_state(value)
                if type(trust.get("enabled")) is bool and not trust.get("pending"):
                    self.uncertain = False
                    self.feedback.hide()
            self.render()
            self.changed.emit()

        def failed(message):
            if not current():
                return
            self.querying = False
            self.feedback.setText(str(message))
            self.feedback.show()
            self.render()

        # This read begins after the failed write response. An unrelated older
        # Panel poll must not resolve uncertainty about that write.
        accepted = self.api.call("GET", "/state", done=done, failed=failed)
        if accepted is False and current():
            self.querying = False
            self.render()
