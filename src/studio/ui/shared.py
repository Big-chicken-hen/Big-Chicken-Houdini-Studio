from __future__ import annotations

import http.client
import json
import select
import socket
import threading
import time
from urllib.parse import urlsplit

from PySide6 import QtCore, QtWidgets
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

class _CancellableSocket(socket.socket):
    """Keep HTTPResponse's ordinary SocketIO reads cancellable on Windows."""
    def __init__(self, cancelled, idle_timeout):
        super().__init__(socket.AF_INET, socket.SOCK_STREAM)
        self.cancelled, self.idle_timeout = cancelled, idle_timeout

    def recv_into(self, buffer, nbytes=0, flags=0):
        deadline = time.monotonic() + self.idle_timeout
        while not self.cancelled.is_set():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Local service response was inactive for 45 seconds")
            readable, _, _ = select.select([self], [], [], min(.1, remaining))
            if readable and not self.cancelled.is_set():
                # One reader, no MSG_WAITALL: consume only the bytes now ready.
                return super().recv_into(buffer, nbytes, flags)
        raise OSError("Request was closed")


class _HttpJob(QtCore.QRunnable):
    """One direct loopback exchange. The worker never reads or modifies widgets."""
    timeout = 45  # Socket inactivity timeout, not an overall request deadline.
    response_limit = 18 * 1024 * 1024

    def __init__(self, request_id, key, url, token, method, path, payload, failure, parent):
        super().__init__()
        self.request_id, self.key = request_id, key
        self.url, self.token, self.method, self.path = url, token, method, path
        self.payload, self.failure = payload, failure
        self.signals = TaskSignals(parent)
        self.cancelled = threading.Event()
        self.finished = threading.Event()
        self.socket_lock = threading.Lock()
        self.socket = None

    def cancel(self):
        self.cancelled.set()
        with self.socket_lock:
            active, self.socket = self.socket, None
        if active is not None:
            try:
                active.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            active.close()

    def exchange(self):
        if self.failure is not None:
            return self.failure
        endpoint = urlsplit(self.url)
        connection = http.client.HTTPConnection(endpoint.hostname, endpoint.port, timeout=self.timeout)
        connection.auto_open = False  # Cancellation cannot cause send() to reconnect.
        response, active, status = None, None, None
        try:
            active = _CancellableSocket(self.cancelled, self.timeout)
            active.settimeout(self.timeout)
            with self.socket_lock:
                if self.cancelled.is_set():
                    raise OSError("Request was closed before sending")
                self.socket = active
                connection.sock = active
            # The only supported host is the validated IPv4 loopback literal;
            # there is no DNS, proxy, redirect or automatic retry path.
            active.connect((endpoint.hostname, endpoint.port))
            if self.cancelled.is_set():
                raise OSError("Request was closed before sending")
            connection.request(self.method, endpoint.path + self.path, body=self.payload,
                               headers={"Authorization": "Bearer " + self.token,
                                        "Content-Type": "application/json", "Connection": "close"})
            response = connection.getresponse()
            status = response.status
            raw = response.read(self.response_limit + 1)
            if len(raw) > self.response_limit:
                return ApiFailure("Bridge response exceeds the 18 MB transport limit", code="RESPONSE_LIMIT",
                                  status=status, submission_state="unknown")
            if response.length is not None and response.length > 0:
                raise http.client.IncompleteRead(raw, response.length)
            if not raw:
                raise ValueError("Bridge returned an empty response")
            value = json.loads(raw)
            if not isinstance(value, dict):
                raise ValueError("Bridge returned an invalid response")
            if not 200 <= status < 300:
                error = value.get("error")
                return ApiFailure(error.get("message", "Request failed") if isinstance(error, dict)
                                  else "Local service rejected the request",
                                  code=error.get("code") if isinstance(error, dict) else None,
                                  status=status, submission_state=error.get("submission_state")
                                  if isinstance(error, dict) else None,
                                  details=error if isinstance(error, dict) else value)
            return value  # A successful receipt query can contain an execution error.
        except (ValueError, TypeError) as error:
            return ApiFailure(str(error).replace(self.token, "[REDACTED]"), code="INVALID_RESPONSE",
                              status=status, submission_state="unknown")
        except (OSError, http.client.HTTPException) as error:
            return ApiFailure(str(error).replace(self.token, "[REDACTED]"), code="CONNECTION_LOST",
                              status=status, submission_state="unknown")
        finally:
            try:
                if response is not None:
                    response.close()
            finally:
                try:
                    connection.close()
                finally:
                    with self.socket_lock:
                        if self.socket is active:
                            self.socket = None
                    if active is not None:
                        active.close()

    def run(self):
        try:
            value = self.exchange()
        except Exception:
            value = ApiFailure("Local service did not confirm the request", code="CONNECTION_LOST",
                               submission_state="unknown")
        self.finished.set()
        try:
            self.signals.result.emit((self.request_id, value))
        except RuntimeError:
            if isValid(self.signals):
                raise


def _cancel_http_jobs(pending, counts, inflight):
    """Pure Python teardown, also safe during the owning QObject's destruction."""
    requests = tuple(pending.values())
    pending.clear()
    counts.clear()
    inflight.clear()
    for job, _done, _failed in requests:
        job.cancel()


class Api(QtCore.QObject):
    def __init__(self, url, token, parent=None):
        super().__init__(parent)
        from ..http import loopback_url
        self.url, self.token = loopback_url(url), token
        self.inflight = set()
        self._inflight_counts = {}
        self._pending = {}
        self._next_request = 0
        self.closed = False
        self.destroyed.connect(lambda *_args, pending=self._pending, counts=self._inflight_counts,
                               inflight=self.inflight: _cancel_http_jobs(pending, counts, inflight))

    @QtCore.Slot(object)
    def _complete(self, result):
        request_id, value = result
        pending = self._pending.pop(request_id, None)
        if pending is None:
            return
        job, done, failed = pending
        remaining = self._inflight_counts[job.key] - 1
        if remaining:
            self._inflight_counts[job.key] = remaining
        else:
            self._inflight_counts.pop(job.key)
            self.inflight.discard(job.key)
        if isValid(job.signals):
            job.signals.deleteLater()
        callback = failed if isinstance(value, ApiFailure) else done
        if callback and not self.closed:
            callback(value)  # Business errors remain outside transport exception handling.

    def call(self, method, path, body=None, done=None, failed=None, unique=False):
        key = (method, path.split("?", 1)[0] if isinstance(path, str) else "")
        if self.closed or not isValid(self) or unique and key in self.inflight:
            return False
        payload, failure = None, None
        try:
            if (method not in {"GET", "POST"} or not isinstance(path, str) or not path.startswith("/")
                    or path.startswith("//") or urlsplit(path).scheme or urlsplit(path).netloc
                    or urlsplit(path).fragment):
                raise ValueError("Routes must be relative to the current loopback service")
            if method == "POST":
                payload = json.dumps(body or {}).encode()
        except (ValueError, TypeError) as error:
            failure = ApiFailure(str(error), code="INVALID_REQUEST", submission_state="not_submitted")
        self._next_request += 1
        request_id = self._next_request
        job = _HttpJob(request_id, key, self.url, self.token, method, path, payload, failure, self)
        self._pending[request_id] = (job, done, failed)
        self.inflight.add(key)
        self._inflight_counts[key] = self._inflight_counts.get(key, 0) + 1
        job.signals.result.connect(self._complete, QtCore.Qt.QueuedConnection)
        if method == "POST" and path == "/stop":
            # Stop must not wait behind occupied history/submission HTTP workers.
            # This thread performs one exchange and exits; it is not a send queue.
            threading.Thread(target=job.run, name="studio-stop-http", daemon=True).start()
        else:
            QtCore.QThreadPool.globalInstance().start(job)
        return True

    def close(self):
        self.closed = True
        _cancel_http_jobs(self._pending, self._inflight_counts, self.inflight)


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
