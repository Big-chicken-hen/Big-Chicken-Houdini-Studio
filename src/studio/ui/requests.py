"""User-driven responses to native Codex server requests."""
from __future__ import annotations

import json

from PySide6 import QtCore, QtGui, QtWidgets

from .shared import button, label


class RequestCard(QtWidgets.QFrame):
    respond = QtCore.Signal(object, object)

    def __init__(self, request, parent=None):
        super().__init__(parent)
        self.request = request
        self.request_id = request["request_id"]
        self.setObjectName("requestCard")
        self.layout = QtWidgets.QVBoxLayout(self)
        self.layout.setContentsMargins(16, 13, 16, 13)
        self.layout.setSpacing(10)
        self.inputs = {}
        self.actions = []
        self.error = label("", "warning", True)
        method, params = request.get("method"), request.get("params", {})
        self.layout.addWidget(label("需要你的回应", "messageAuthor"))
        self.layout.addWidget(label(str(params.get("reason") or params.get("message") or method), wrap=True))
        details = QtWidgets.QPlainTextEdit()
        details.setReadOnly(True)
        details.setPlainText(json.dumps(params, ensure_ascii=False, indent=2))
        details.setMaximumHeight(140)
        details.hide()
        toggle = button("查看完整请求", lambda: details.setVisible(not details.isVisible()), "quiet")
        self.layout.addWidget(toggle, 0, QtCore.Qt.AlignLeft)
        self.layout.addWidget(details)
        self.layout.addWidget(self.error)
        self.error.hide()
        self.row = QtWidgets.QHBoxLayout()
        if method in {"item/commandExecution/requestApproval", "item/fileChange/requestApproval"}:
            if params.get("command"):
                self.layout.addWidget(label(str(params["command"]), wrap=True))
            if params.get("cwd"):
                self.layout.addWidget(label("工作目录  " + str(params["cwd"]), "muted", True))
            if params.get("networkApprovalContext"):
                self.layout.addWidget(label("网络访问  " + json.dumps(params["networkApprovalContext"], ensure_ascii=False), wrap=True))
            if params.get("additionalPermissions"):
                self.layout.addWidget(label("附加权限  " + json.dumps(params["additionalPermissions"], ensure_ascii=False), wrap=True))
            allowed = params.get("availableDecisions") or ["accept", "decline", "cancel"]
            names = {"accept": "允许本次", "acceptForSession": "允许本会话", "decline": "拒绝", "cancel": "取消请求"}
            for decision in allowed:
                if isinstance(decision, str) and decision in names:
                    self.action(names[decision], lambda d=decision: self.submit({"decision": d}))
            if not self.actions:
                self.layout.addWidget(label("当前原生审批选项暂不受支持。", "warning", True))
        elif method == "item/permissions/requestApproval":
            self.layout.addWidget(label(json.dumps(params.get("permissions", {}), ensure_ascii=False, indent=2), wrap=True))
            self.action("允许列出的权限 · 本轮", lambda: self.submit({"permissions": params.get("permissions", {}), "scope": "turn"}))
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

    def action(self, title, callback):
        control = button(title, lambda: callback())
        self.row.addWidget(control)
        self.actions.append(control)

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
        self.error.hide()
        for control in self.actions:
            control.setEnabled(False)
        self.respond.emit(self.request_id, result)

    def failed(self, message):
        self.error.setText(message)
        self.error.show()
        for control in self.actions:
            control.setEnabled(True)
