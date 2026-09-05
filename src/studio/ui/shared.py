from __future__ import annotations

import json

from PySide6 import QtCore, QtGui, QtNetwork, QtWidgets

FONT = "Microsoft YaHei UI"
DARK = """
QWidget { font-family: 'Microsoft YaHei UI'; font-size: 12px; color: #E7E8E2; }
QWidget#studioPanel { background: #20231F; }
QLabel#muted { color: #90998D; }
QLabel#brand { color: #C8E889; font-weight: 800; font-size: 17px; }
QLabel#heading { font-size: 22px; font-weight: 700; }
QLabel#eyebrow { color: #A3AE99; font-size: 10px; letter-spacing: 2px; }
QFrame#card { background: #2A2E27; border: 1px solid #3B4137; border-radius: 9px; }
QFrame#status { background: #171A16; border-radius: 7px; }
QPushButton { background: #30362C; border: 1px solid #46503E; padding: 7px 12px; border-radius: 6px; }
QPushButton:hover { background: #414A39; }
QPushButton:disabled { color: #777E70; border-color: #343B2E; background: #272D23; }
QPushButton#primary { background: #C8E889; border-color: #C8E889; color: #20271A; font-weight: 700; }
QPushButton#primary:hover { background: #D7F0AE; }
QPushButton#primary:disabled { background: #475339; border-color: #475339; color: #8C9C7C; }
QPushButton#quiet { background: transparent; border: none; color: #AEB9A4; padding: 4px; }
QPushButton#stop { color: #E7B08B; background: #3A2C22; border-color: #604B38; }
QComboBox, QLineEdit, QTextEdit, QPlainTextEdit { background: #191D17; border: 1px solid #3B4433; border-radius: 6px; padding: 8px; selection-background-color: #52643B; }
QComboBox::drop-down { border: none; width: 18px; }
QComboBox QAbstractItemView { background: #252B20; color: #E7E8E2; selection-background-color: #455438; }
QTextBrowser { background: transparent; border: none; padding: 0; }
QScrollArea { background: transparent; border: none; }
QScrollBar:vertical { background: transparent; width: 7px; }
QScrollBar::handle:vertical { background: #56614C; border-radius: 3px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QTabWidget::pane { border: none; }
QTabBar::tab { background: transparent; color: #97A18E; padding: 11px 12px; border-bottom: 2px solid transparent; }
QTabBar::tab:selected { color: #D9EDB7; border-bottom: 2px solid #C8E889; }
QListWidget { background: #22271E; border: none; border-radius: 8px; padding: 5px; }
QListWidget::item { padding: 12px; border-bottom: 1px solid #363F2E; }
QListWidget::item:selected { background: #3F4C33; }
QToolTip { background: #D8E7C1; color: #22271E; border: 0; padding: 6px; }
"""

LIGHT = """
QWidget { font-family: 'Microsoft YaHei UI'; font-size: 13px; color: #30382D; }
QWidget#studioLauncher { background: #F2F1EB; }
QFrame#rail { background: #252B23; }
QFrame#rail QLabel { color: #B7C0AE; }
QFrame#rail QLabel#brand { color: #D2EA9F; font-size: 20px; font-weight: 800; }
QLabel#title { color: #283421; font-size: 34px; font-weight: 800; }
QLabel#muted { color: #7D8775; }
QLabel#eyebrow { color: #76826B; font-size: 11px; letter-spacing: 2px; }
QFrame#sheet { background: #FCFCF8; border: 1px solid #DCDFD3; border-radius: 12px; }
QFrame#well { background: #E8EDDC; border-radius: 10px; }
QPushButton { background: #F9FAF4; border: 1px solid #C9D0BB; padding: 9px 15px; border-radius: 7px; }
QPushButton:hover { background: #E9EEDC; }
QPushButton#primary { background: #2E3B25; border: 0; color: #EBF3DC; padding: 14px 24px; font-weight: 700; }
QPushButton#primary:hover { background: #465A36; }
QPushButton:disabled { color: #959D8A; background: #E1E4D9; border-color: #E1E4D9; }
QPushButton#primary:disabled { color: #8B957D; background: #DFE4D5; }
QPushButton#railButton { color: #E6EBDF; background: #394331; border: 0; text-align: left; padding: 13px 16px; }
QLineEdit, QComboBox { background: #FFFFFF; border: 1px solid #D6DBCD; border-radius: 6px; padding: 10px; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView { background: #FFFFFF; selection-background-color: #DBE5C8; color: #283421; }
QListWidget { background: transparent; border: none; outline: none; }
QListWidget::item { background: #F9FAF5; padding: 16px; border: 1px solid #DCE0D3; margin-bottom: 8px; border-radius: 8px; }
QListWidget::item:selected { background: #E4EDCF; border-color: #A5B987; color: #24301E; }
"""


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
    def __new__(cls, message, *, code=None, status=None, submission_state=None):
        value = super().__new__(cls, message)
        value.code, value.status, value.submission_state = code, status, submission_state
        return value


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
                                          if isinstance(error, dict) else None))
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
    error = QtCore.Signal(str)


class Task(QtCore.QRunnable):
    def __init__(self, function):
        super().__init__()
        self.function = function
        self.signals = TaskSignals()

    def run(self):
        try:
            self.signals.result.emit(self.function())
        except Exception as exc:
            self.signals.error.emit(str(exc))


class StudioGlyph(QtWidgets.QWidget):
    """Code-drawn brand illustration, unrelated to the user's Houdini scene."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(160, 150)

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.translate(self.width() / 2, self.height() / 2)
        scale = min(self.width(), self.height()) / 170
        painter.scale(scale, scale)
        painter.setPen(QtGui.QPen(QtGui.QColor("#9CAB83"), 1))
        painter.setBrush(QtGui.QColor("#E1EBCF"))
        painter.drawEllipse(QtCore.QRectF(-60, -60, 120, 120))
        painter.setBrush(QtCore.Qt.NoBrush)
        for angle in (-55, -25, 5, 35, 65):
            painter.save()
            painter.rotate(angle)
            painter.drawEllipse(QtCore.QRectF(-22, -60, 44, 120))
            painter.restore()
        painter.setPen(QtGui.QPen(QtGui.QColor("#34472A"), 2))
        painter.drawLine(-74, 37, 68, -40)
        for x, y in ((-74, 37), (68, -40), (-5, 0)):
            painter.setBrush(QtGui.QColor("#34472A"))
            painter.drawEllipse(QtCore.QPointF(x, y), 4, 4)
