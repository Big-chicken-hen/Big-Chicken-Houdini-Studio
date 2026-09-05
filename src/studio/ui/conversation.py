"""Native conversation projection. No persisted or synthesized chat history."""
from __future__ import annotations

import base64
import json
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from .shared import Task, button, clear_layout, label


class SafeBrowser(QtWidgets.QTextBrowser):
    """Markdown may contain links; it may never fetch files or remote resources."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setOpenLinks(False)
        self.setOpenExternalLinks(False)
        self.anchorClicked.connect(self.open_link)
        self.document().setDefaultStyleSheet(
            "p { margin: 6px 0; } pre { background: #191c18; padding: 10px; } "
            "a { color: #c8e889; } code { font-family: Consolas; }")

    def loadResource(self, kind, url):
        return QtCore.QByteArray()

    @staticmethod
    def open_link(url):
        if url.scheme() in {"https", "http"}:
            QtGui.QDesktopServices.openUrl(url)


class ImageTile(QtWidgets.QFrame):
    """Decode selected/native image bytes in a worker, create pixmaps on the UI thread."""
    removed = QtCore.Signal()

    def __init__(self, source, caption="图片", removable=False, compact=False, parent=None):
        super().__init__(parent)
        self.setObjectName("imageTile")
        self.setFixedWidth(132 if compact else 260)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(7, 7, 7, 7)
        self.picture = label("读取图片…")
        self.picture.setAlignment(QtCore.Qt.AlignCenter)
        self.picture.setFixedSize(116, 68) if compact else self.picture.setFixedSize(244, 148)
        layout.addWidget(self.picture)
        row = QtWidgets.QHBoxLayout()
        name = label(caption)
        name.setToolTip(caption)
        name.setMinimumWidth(0)
        name.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Preferred)
        row.addWidget(name, 1)
        if removable:
            remove = button("×", self.removed.emit, "quiet")
            remove.setAccessibleName("移除图片 " + caption)
            remove.setFixedSize(24, 24)
            row.addWidget(remove)
        layout.addLayout(row)
        self.task = Task(lambda: self.decode(source))
        self.task.signals.result.connect(self.loaded)
        self.task.signals.error.connect(self.unavailable)
        QtCore.QThreadPool.globalInstance().start(self.task)

    @staticmethod
    def decode(source):
        buffer = None
        if source.get("data"):
            data = source["data"]
            if len(data) > 24 * 1024 * 1024:
                raise ValueError("图片过大")
            raw = base64.b64decode(data, validate=True)
            buffer = QtCore.QBuffer()
            buffer.setData(raw)
            buffer.open(QtCore.QIODevice.ReadOnly)
            reader = QtGui.QImageReader(buffer)
        else:
            reader = QtGui.QImageReader(str(source.get("path", "")))
        reader.setAutoTransform(True)
        size = reader.size()
        if size.isValid():
            reader.setScaledSize(size.scaled(900, 600, QtCore.Qt.KeepAspectRatio))
        result = reader.read()
        if result.isNull():
            raise ValueError("图片不可用")
        return result

    def loaded(self, result):
        self.picture.setPixmap(QtGui.QPixmap.fromImage(result).scaled(
            self.picture.size(), QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation))
        self.picture.setToolTip("原生图片预览")

    def unavailable(self, _message):
        self.picture.setText("图片不可用")


def image_sources(item, app_root):
    content = list(item.get("content") or [])
    if item.get("type") == "imageView":
        content.append({"type": "localImage", "path": item.get("path")})
    result = item.get("result") or {}
    if isinstance(result, dict):
        content.extend(result.get("content") or [])
    sources = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "image" and block.get("data"):
            sources.append({"data": block["data"]})
        elif block.get("type") in {"image", "localImage"}:
            url = block.get("url", "")
            if url.startswith("data:image/") and ";base64," in url:
                sources.append({"data": url.split(";base64,", 1)[1]})
            elif block.get("path"):
                path = Path(block["path"]).resolve()
                # Native history cannot ask Qt to read outside application storage.
                if app_root == path or app_root in path.parents:
                    sources.append({"path": str(path)})
    return sources[:8]


class MessageCard(QtWidgets.QFrame):
    def __init__(self, item, app_root, parent=None):
        super().__init__(parent)
        self.setObjectName("messageCard")
        self.app_root = app_root
        self.item = {}
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(18, 13, 18, 14)
        self.title = label("", "messageAuthor")
        layout.addWidget(self.title)
        self.text = SafeBrowser()
        self.text.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.text.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        layout.addWidget(self.text)
        self.images = QtWidgets.QHBoxLayout()
        self.images.setAlignment(QtCore.Qt.AlignLeft)
        self.image_area = QtWidgets.QWidget()
        self.image_area.setObjectName("imageBody")
        self.image_area.setLayout(self.images)
        self.image_scroll = QtWidgets.QScrollArea()
        self.image_scroll.setWidget(self.image_area)
        self.image_scroll.setWidgetResizable(True)
        self.image_scroll.setFixedHeight(208)
        layout.addWidget(self.image_scroll)
        self.details_button = button("查看工具内容", self.toggle_details, "quiet")
        layout.addWidget(self.details_button, 0, QtCore.Qt.AlignLeft)
        self.details = QtWidgets.QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setMaximumHeight(190)
        self.details.hide()
        layout.addWidget(self.details)
        self.update_item(item)

    def update_item(self, item):
        previous = self.item
        self.item = item
        kind = item.get("type", "item")
        status = item.get("status", "")
        titles = {"userMessage": "你", "agentMessage": "CODEX", "reasoning": "CODEX · 思考摘要",
                  "plan": "CODEX · 计划", "contextCompaction": "CODEX · 原生上下文压缩",
                  "mcpToolCall": "工具 · " + str(item.get("tool", "")), "commandExecution": "命令执行",
                  "fileChange": "文件变更", "webSearch": "网页检索", "imageView": "图片"}
        self.title.setText(titles.get(kind, kind) + ("  /  " + status if status else ""))
        text = item.get("text", "")
        if kind == "userMessage":
            text = "\n\n".join(c.get("text", "") for c in item.get("content", []) if c.get("type") == "text")
        elif kind == "reasoning":
            text = "\n".join(str(s) for s in item.get("summary", []))
        elif kind == "commandExecution":
            text = item.get("command", "")
        elif kind == "webSearch":
            text = item.get("query", "")
        elif kind == "fileChange":
            text = "\n".join(c.get("path", "") for c in item.get("changes", []))
        elif kind == "mcpToolCall":
            text = "原生工具事件；场景结果请查看「执行记录」。"
        elif kind == "contextCompaction":
            text = "此会话由 Codex 自动压缩，可继续当前对话。"
        elif not text:
            text = status or "等待原生事件…"
        self.text.setMarkdown(str(text))
        self.text.setVisible(bool(text))
        is_tool = kind not in {"userMessage", "agentMessage", "reasoning", "plan", "contextCompaction"}
        self.details_button.setVisible(is_tool)
        if self.details.isVisible():
            self.show_details()
        # Text deltas don't decode the same image again.
        if previous.get("content") != item.get("content") or previous.get("result") != item.get("result") or not previous:
            clear_layout(self.images)
            sources = image_sources(item, self.app_root)
            for source in sources:
                self.images.addWidget(ImageTile(source))
            self.image_scroll.setVisible(bool(sources))
        QtCore.QTimer.singleShot(0, self.fit_text)

    def fit_text(self):
        self.text.document().setTextWidth(max(100, self.text.viewport().width()))
        height = min(1600, int(self.text.document().size().height()) + 8)
        self.text.setFixedHeight(max(28, height))
        self.text.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded if height == 1600 else QtCore.Qt.ScrollBarAlwaysOff)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.fit_text()

    def show_details(self):
        value = {k: v for k, v in self.item.items() if k != "result"}
        result = self.item.get("result")
        if isinstance(result, dict):
            value["result"] = {**result, "content": [
                {k: v for k, v in c.items() if k != "data"} for c in result.get("content", [])]}
        self.details.setPlainText(json.dumps(value, ensure_ascii=False, indent=2)[:48000])

    def toggle_details(self):
        self.details.setVisible(not self.details.isVisible())
        if self.details.isVisible():
            self.show_details()


class Transcript(QtWidgets.QScrollArea):
    def __init__(self, app_root, parent=None):
        super().__init__(parent)
        self.app_root = app_root
        self.setWidgetResizable(True)
        self.body = QtWidgets.QWidget()
        self.body.setObjectName("transcript")
        self.layout = QtWidgets.QVBoxLayout(self.body)
        self.layout.setContentsMargins(0, 8, 0, 12)
        self.layout.setSpacing(10)
        self.setWidget(self.body)
        self.cards = {}
        self.suppressed_deltas = set()
        self.empty = label("从一个想法开始。\n登录后新建对话，描述你想完成的 Houdini 工作。", "welcome", True)
        self.empty.setAlignment(QtCore.Qt.AlignCenter)
        self.empty.setMinimumHeight(170)
        self.layout.addWidget(self.empty)
        self.layout.addStretch()

    def reset(self):
        for card in self.cards.values():
            self.layout.removeWidget(card)
            card.deleteLater()
        self.cards.clear()
        self.suppressed_deltas.clear()
        self.empty.show()

    def hydrate(self, thread):
        self.reset()
        for turn in (thread or {}).get("turns", []):
            for item in turn.get("items", []):
                self.put(item)
                # No atomic cursor accompanies thread/read. Never duplicate text by
                # appending pre-snapshot deltas. item/completed replaces the snapshot.
                self.suppressed_deltas.add(item.get("id"))
        self.to_bottom()

    def put(self, item):
        item_id = item.get("id")
        if not item_id:
            return
        bar = self.verticalScrollBar()
        bottom = bar.maximum() - bar.value() < 45
        if item_id in self.cards:
            self.cards[item_id].update_item(item)
        else:
            card = MessageCard(item, self.app_root)
            self.cards[item_id] = card
            self.layout.insertWidget(self.layout.count() - 1, card)
            self.empty.hide()
        if bottom:
            QtCore.QTimer.singleShot(0, self.to_bottom)

    def apply_event(self, event):
        method, params = event.get("method", ""), event.get("params", {})
        if method in {"item/started", "item/completed"}:
            item = params.get("item", {})
            if method == "item/started" and item.get("id") in self.cards:
                return
            self.put(item)
        elif method in {"item/agentMessage/delta", "item/plan/delta"}:
            item_id = params.get("itemId")
            if item_id in self.suppressed_deltas:
                return
            card = self.cards.get(item_id)
            item = dict(card.item) if card else {"id": item_id, "type": "agentMessage", "text": ""}
            item["text"] = item.get("text", "") + params.get("delta", "")
            self.put(item)
        elif method == "item/reasoning/summaryTextDelta":
            item_id = params.get("itemId")
            if item_id in self.suppressed_deltas:
                return
            card = self.cards.get(item_id)
            item = dict(card.item) if card else {"id": item_id, "type": "reasoning"}
            summary = list(item.get("summary", []))
            index = min(100, max(0, params.get("summaryIndex", 0)))
            while len(summary) <= index:
                summary.append("")
            summary[index] += params.get("delta", "")
            item["summary"] = summary
            self.put(item)

    def to_bottom(self):
        self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())
