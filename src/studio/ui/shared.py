from __future__ import annotations

import json

from PySide6 import QtCore, QtNetwork, QtWidgets
from shiboken6 import isValid

from .icons import icon_diagnostics, set_button_icon
from .theme import studio_stylesheet

FONT = "Microsoft YaHei UI"
DARK = studio_stylesheet("studioPanel")
LIGHT = studio_stylesheet("studioLauncher")


def label(text, name=None, wrap=False):
    item = QtWidgets.QLabel(text)
    item.setTextFormat(QtCore.Qt.PlainText)
    if name:
        item.setObjectName(name)
    item.setWordWrap(wrap)
    return item


def button(text, callback=None, name=None):
    item = QtWidgets.QPushButton(text)
    item.setCursor(QtCore.Qt.PointingHandCursor)
    item.setMinimumHeight(32)
    item.setAccessibleName(text)
    if name:
        item.setObjectName(name)
    if callback:
        item.clicked.connect(callback)
    return item


def clear_layout(layout):
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().deleteLater()


class ApiFailure(str):
    """A displayable error that preserves the server's submission classification."""
    def __new__(cls, message, *, code=None, status=None, submission_state=None, details=None):
        value = super().__new__(cls, message)
        value.code, value.status, value.submission_state = code, status, submission_state
        value.details = details
        return value


class ErrorDetails(QtWidgets.QFrame):
    """A short plain-text reason and optional diagnostics, without a retry action."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("studioError")
        self.failure = None
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        self.summary = label("", wrap=True)
        self.summary.setProperty("tone", "error")
        layout.addWidget(self.summary)
        self.toggle = QtWidgets.QToolButton()
        self.toggle.setObjectName("quiet")
        self.toggle.setText("查看详情")
        self.toggle.setCheckable(True)
        self.toggle.setMinimumSize(32, 32)
        self.toggle.setAccessibleName("展开错误详情")
        set_button_icon(self.toggle, "chevron-right", text="查看详情", size=16)
        layout.addWidget(self.toggle, 0, QtCore.Qt.AlignLeft)
        self.body = QtWidgets.QWidget()
        body = QtWidgets.QVBoxLayout(self.body)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(4)
        self.details = QtWidgets.QPlainTextEdit()
        self.details.setObjectName("statusDetails")
        self.details.setReadOnly(True)
        self.details.setTabChangesFocus(True)
        self.details.setMinimumHeight(64)
        self.details.setMaximumHeight(144)
        self.details.setAccessibleName("错误详情")
        body.addWidget(self.details)
        layout.addWidget(self.body)
        self.toggle.toggled.connect(self.set_expanded)
        self.set_failure(None)

    def set_failure(self, failure, details=None):
        self.failure = failure
        if failure is None:
            self.summary.clear()
            self.details.clear()
            self.toggle.setChecked(False)
            self.body.hide()
            self.hide()
            return
        if isinstance(failure, dict):
            message = str(failure.get("message", "需要处理一个问题"))
            record = dict(failure)
        else:
            message = str(failure)
            record = {key: getattr(failure, key, None) for key in ("code", "status", "submission_state", "details")}
            record = {key: value for key, value in record.items() if value is not None}
        self.summary.setText(message.splitlines()[0] if message else "需要处理一个问题")
        if details is not None:
            record["details"] = details
        resources = icon_diagnostics()
        if resources:
            record["ui_resources"] = resources
        rendered = message + ("\n\n" + json.dumps(record, ensure_ascii=False, indent=2, default=str) if record else "")
        if self.details.toPlainText() != rendered:
            self.details.setPlainText(rendered)
        self.show()
        self.body.setVisible(self.toggle.isChecked())

    def set_expanded(self, expanded):
        self.body.setVisible(expanded and self.failure is not None)
        set_button_icon(self.toggle, "chevron-down" if expanded else "chevron-right",
                        text="收起详情" if expanded else "查看详情", size=16)
        self.toggle.setAccessibleName("收起错误详情" if expanded else "展开错误详情")

class Api(QtCore.QObject):
    def __init__(self, url, token, parent=None):
        super().__init__(parent)
        from ..http import loopback_url
        self.url, self.token = loopback_url(url), token
        self.manager = QtNetwork.QNetworkAccessManager(self)
        self.inflight = set()
        self.replies = set()
        self.closed = False

    def call(self, method, path, body=None, done=None, failed=None, unique=False):
        key = (method, path.split("?", 1)[0])
        if self.closed or unique and key in self.inflight:
            return False
        self.inflight.add(key)
        request = QtNetwork.QNetworkRequest(QtCore.QUrl(self.url + path))
        request.setRawHeader(b"Authorization", ("Bearer " + self.token).encode())
        request.setHeader(QtNetwork.QNetworkRequest.ContentTypeHeader, "application/json")
        request.setAttribute(QtNetwork.QNetworkRequest.RedirectPolicyAttribute,
                             QtNetwork.QNetworkRequest.ManualRedirectPolicy)
        request.setTransferTimeout(45000)
        reply = (self.manager.get(request) if method == "GET" else
                 self.manager.post(request, json.dumps(body or {}).encode()))
        self.replies.add(reply)

        def finished():
            self.inflight.discard(key)
            self.replies.discard(reply)
            raw = bytes(reply.readAll())
            try:
                if self.closed:
                    return
                value = json.loads(raw) if raw else {}
                if not isinstance(value, dict):
                    raise ValueError("Bridge returned an invalid response")
                status = reply.attribute(QtNetwork.QNetworkRequest.HttpStatusCodeAttribute)
                # A receipt can contain an execution error while its HTTP query succeeds.
                if reply.error() != QtNetwork.QNetworkReply.NoError or not (isinstance(status, int) and 200 <= status < 300):
                    error = value.get("error")
                    message = error.get("message", "Request failed") if isinstance(error, dict) else reply.errorString()
                    if failed:
                        failed(ApiFailure(message, code=error.get("code") if isinstance(error, dict) else None,
                                          status=status, submission_state=error.get("submission_state")
                                          if isinstance(error, dict) else None,
                                          details=error if isinstance(error, dict) else value))
                elif done:
                    done(value)
            except (ValueError, TypeError) as exc:
                if failed:
                    failed(ApiFailure(str(exc)))
            finally:
                reply.deleteLater()
        reply.finished.connect(finished)
        return True

    def close(self):
        self.closed = True
        for reply in tuple(self.replies):
            reply.abort()


class TaskSignals(QtCore.QObject):
    result = QtCore.Signal(object)
    error = QtCore.Signal(object)


class Task(QtCore.QRunnable):
    def __init__(self, function):
        super().__init__()
        self.function = function
        self.signals = TaskSignals()

    def run(self):
        try:
            value = self.function()
        except Exception as exc:
            details = getattr(exc, "details", None)
            self._emit("error", ApiFailure(str(exc), code=getattr(exc, "code", None),
                status=getattr(exc, "status", None), details=details,
                submission_state=details.get("submission_state") if isinstance(details, dict) else None))
        else:
            self._emit("result", value)

    def _emit(self, channel, value):
        try:
            getattr(self.signals, channel).emit(value)
        except RuntimeError:
            # Application teardown may delete the QObject while a worker finishes
            # its cleanup. Delivery failure is not failure of the completed work.
            if isValid(self.signals):
                raise

