"""Native conversation projection. No persisted or synthesized chat history."""
from __future__ import annotations

import base64
import json
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from .icons import set_button_icon
from .shared import Task, button, label
from .theme import COLORS, apply_theme


class SafeBrowser(QtWidgets.QTextBrowser):
    """Markdown may contain links; it may never fetch files or remote resources."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setOpenLinks(False)
        self.setOpenExternalLinks(False)
        self.anchorClicked.connect(self.open_link)
        self.document().setDefaultStyleSheet(
            "p { margin: 6px 0; } pre { background: " + COLORS["surface_elevated"] + "; padding: 10px; } "
            "a { color: " + COLORS["primary_pink"] + "; } code { font-family: Consolas; }")

    def loadResource(self, kind, url):
        return QtCore.QByteArray()

    @staticmethod
    def open_link(url):
        if url.scheme() in {"https", "http"}:
            QtGui.QDesktopServices.openUrl(url)


class ImageView(QtWidgets.QLabel):
    activated = QtCore.Signal()

    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton and self.rect().contains(event.position().toPoint()):
            self.activated.emit()
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.key() in {QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter, QtCore.Qt.Key_Space}:
            self.activated.emit()
            event.accept()
        else:
            super().keyPressEvent(event)


class ImagePreview(QtWidgets.QDialog):
    """Enlarge only the already-decoded image; never perform another source read."""
    def __init__(self, decoded, parent=None):
        super().__init__(parent)
        self.decoded = decoded
        self.setObjectName("studioImagePreview")
        self.setWindowTitle("图片预览")
        apply_theme(self)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        self.picture = label("")
        self.picture.setAlignment(QtCore.Qt.AlignCenter)
        self.picture.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Ignored)
        layout.addWidget(self.picture)
        available = self.screen().availableGeometry()
        self.resize(min(960, available.width() - 24), min(720, available.height() - 24))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        dpr = self.devicePixelRatioF()
        pixmap = QtGui.QPixmap.fromImage(self.decoded).scaled(
            max(1, int((self.width() - 24) * dpr)), max(1, int((self.height() - 24) * dpr)),
            QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
        pixmap.setDevicePixelRatio(dpr)
        self.picture.setPixmap(pixmap)


class ImageTile(QtWidgets.QFrame):
    """Decode selected/native image bytes in a worker, create pixmaps on the UI thread."""
    removed = QtCore.Signal()
    geometry_will_change = QtCore.Signal()
    geometry_changed = QtCore.Signal()

    def __init__(self, source, caption="图片", removable=False, compact=False, parent=None):
        super().__init__(parent)
        self.setObjectName("imageTile")
        self.compact = compact
        self.decoded = QtGui.QImage()
        self.failure = None
        self.viewer = None
        self._display_key = None
        self._box = (56, 56) if compact else (560, 300)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.picture = ImageView("读取图片…")
        self.picture.setTextFormat(QtCore.Qt.PlainText)
        self.picture.setAlignment(QtCore.Qt.AlignCenter)
        self.picture.setWordWrap(True)
        self.picture.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.picture.setCursor(QtCore.Qt.PointingHandCursor)
        self.picture.activated.connect(self.enlarge)
        layout.addWidget(self.picture)
        self.caption = label(caption)
        self.caption.setToolTip(caption)
        self.caption.setMinimumWidth(0)
        self.caption.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Preferred)
        self.caption.setVisible(compact or caption != "图片")
        self.caption.setMaximumHeight(16)
        layout.addWidget(self.caption)
        if removable:
            self.remove_button = button("移除图片", self.removed.emit, "quiet")
            self.remove_button.setParent(self)
            self.remove_button.setStyleSheet("padding: 0; background: " + COLORS["surface_elevated"] + ";")
            self.remove_button.setFixedSize(32, 32)
            set_button_icon(self.remove_button, "x", text="移除图片 " + caption, fallback_text="移除", icon_only=True)
        else:
            self.remove_button = None
        self.set_display_size(*self._box)
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
            raise ValueError(reader.errorString() or "无法读取图片")
        return result

    def loaded(self, result):
        self.geometry_will_change.emit()
        self.decoded = result
        self.failure = None
        self.set_display_size(*self._box)
        self.picture.setToolTip("点击放大此图片")
        self.geometry_changed.emit()

    def unavailable(self, message):
        self.failure = message
        self.picture.setText("图片无法读取\n" + str(message))
        self.picture.setToolTip(str(message))

    def set_display_size(self, width, height):
        self._box = (max(1, width), max(1, height))
        size = QtCore.QSize(*self._box)
        if not self.decoded.isNull():
            size = self.decoded.size().scaled(size, QtCore.Qt.KeepAspectRatio)
        if self.compact:
            size = QtCore.QSize(56, 56)
        self.picture.setFixedSize(size)
        self.setFixedWidth(80 if self.compact else size.width())
        if self.remove_button:
            self.remove_button.move(self.width() - 32, 0)
            self.remove_button.raise_()
        key = (self.decoded.cacheKey(), size.width(), size.height(), self.devicePixelRatioF())
        if not self.decoded.isNull() and key != self._display_key:
            self._display_key = key
            dpr = self.devicePixelRatioF()
            pixmap = QtGui.QPixmap.fromImage(self.decoded).scaled(
                int(size.width() * dpr), int(size.height() * dpr),
                QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
            pixmap.setDevicePixelRatio(dpr)
            self.picture.setPixmap(pixmap)

    def enlarge(self):
        if self.decoded.isNull() or self.compact:
            return
        if self.viewer is None:
            self.viewer = ImagePreview(self.decoded, self)
        self.viewer.show()
        self.viewer.raise_()

    def event(self, event):
        result = super().event(event)
        if event.type() == QtCore.QEvent.DevicePixelRatioChange and hasattr(self, "_box"):
            self.set_display_size(*self._box)
        return result


def image_sources(item, app_root):
    roots = (Path(app_root).resolve(),) if isinstance(app_root, (str, Path)) else tuple(Path(path).resolve() for path in app_root)
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
                if any(root == path or root in path.parents for root in roots):
                    sources.append({"path": str(path)})
    return sources[:8]


class MessageCard(QtWidgets.QFrame):
    layout_will_change = QtCore.Signal()
    layout_changed = QtCore.Signal()
    def __init__(self, item, app_root, parent=None):
        super().__init__(parent)
        self.setObjectName("messageCard")
        self.app_root = app_root
        self.item = {}
        self.rendered_text = None
        self.image_tiles = []
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        self.title = label("", "messageAuthor")
        layout.addWidget(self.title)
        self.sync_note = label("恢复中的消息：完整内容到达时更新，也可手动刷新连接。", "muted", True)
        self.sync_note.hide()
        layout.addWidget(self.sync_note)
        self.text = SafeBrowser()
        self.text.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.text.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        layout.addWidget(self.text)
        self.images = QtWidgets.QHBoxLayout()
        self.images.setContentsMargins(0, 0, 0, 0)
        self.images.setSpacing(8)
        self.images.setAlignment(QtCore.Qt.AlignLeft)
        self.image_area = QtWidgets.QWidget()
        self.image_area.setObjectName("imageBody")
        self.image_area.setLayout(self.images)
        self.image_scroll = QtWidgets.QScrollArea()
        self.image_scroll.setWidget(self.image_area)
        self.image_area.setAutoFillBackground(False)
        self.image_scroll.viewport().setAutoFillBackground(False)
        self.image_scroll.setWidgetResizable(True)
        layout.addWidget(self.image_scroll)
        self.details_button = button("查看工具内容", self.toggle_details, "quiet")
        layout.addWidget(self.details_button, 0, QtCore.Qt.AlignLeft)
        self.details = QtWidgets.QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setMaximumHeight(190)
        self.details.hide()
        layout.addWidget(self.details)
        self.update_item(item)

    def update_item(self, item, *, force=False):
        if self.item == item and not force:
            return False
        self.item = item
        kind = item.get("type", "item")
        role = "user" if kind == "userMessage" else "assistant"
        if self.property("studioRole") != role:
            self.setProperty("studioRole", role)
            self.style().unpolish(self)
            self.style().polish(self)
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
            text = ""  # The native tool payload stays behind the explicit details control.
        elif kind == "imageView":
            text = ""
        elif kind == "contextCompaction":
            text = "此会话由 Codex 自动压缩，可继续当前对话。"
        elif not text:
            text = status or "等待原生事件…"
        text_changed = self.rendered_text != str(text)
        if text_changed:
            self.rendered_text = str(text)
            self.text.setMarkdown(self.rendered_text)
        self.text.setVisible(bool(text))
        is_tool = kind not in {"userMessage", "agentMessage", "reasoning", "plan", "contextCompaction", "imageView"}
        self.details_button.setVisible(is_tool)
        if self.details.isVisible():
            self.show_details()
        sources = image_sources(item, self.app_root)
        if sources != [source for source, _tile in self.image_tiles]:
            unused = list(self.image_tiles)
            self.image_tiles = []
            for index, source in enumerate(sources):
                match = next((pair for pair in unused if pair[0] == source), None)
                if match is None:
                    tile = ImageTile(source)
                    tile.geometry_will_change.connect(self.layout_will_change.emit)
                    tile.geometry_changed.connect(self.image_loaded)
                else:
                    unused.remove(match)
                    tile = match[1]
                self.image_tiles.append((source, tile))
                self.images.insertWidget(index, tile)
            for _source, tile in unused:
                self.images.removeWidget(tile)
                tile.deleteLater()
        self.image_scroll.setVisible(bool(sources))
        self.fit_images()
        if text_changed:
            QtCore.QTimer.singleShot(0, self, self.fit_text)
        return True

    def set_recovering(self, recovering):
        self.sync_note.setVisible(recovering)

    def fit_text(self):
        self.text.document().setTextWidth(max(100, self.text.viewport().width()))
        height = min(1600, int(self.text.document().size().height()) + 8)
        self.text.setFixedHeight(max(28, height))
        self.text.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded if height == 1600 else QtCore.Qt.ScrollBarAlwaysOff)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.fit_text()
        self.fit_images()

    def fit_images(self):
        if not self.image_tiles:
            return
        available = max(56, self.width() - self.layout().contentsMargins().left() - self.layout().contentsMargins().right())
        single = len(self.image_tiles) == 1
        for _source, tile in self.image_tiles:
            tile.set_display_size(min(560, available) if single else min(240, available), 300 if single else 160)
        height = max(tile.sizeHint().height() for _source, tile in self.image_tiles)
        self.image_area.setMinimumWidth(0 if single else sum(tile.width() for _source, tile in self.image_tiles)
                                       + (len(self.image_tiles) - 1) * 8)
        self.image_scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff if single else QtCore.Qt.ScrollBarAsNeeded)
        self.image_scroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.image_scroll.setFixedHeight(height + (0 if single else self.image_scroll.horizontalScrollBar().sizeHint().height()))

    def image_loaded(self):
        self.fit_images()
        self.layout_changed.emit()

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
    def __init__(self, app_root, parent=None, *, image_roots=None):
        super().__init__(parent)
        self.app_root = (app_root,) if image_roots is None else tuple(image_roots)
        self.setWidgetResizable(True)
        self.body = QtWidgets.QWidget()
        self.body.setObjectName("transcript")
        self.layout = QtWidgets.QVBoxLayout(self.body)
        self.layout.setContentsMargins(0, 8, 0, 12)
        self.layout.setSpacing(10)
        self.setWidget(self.body)
        self.body.setAutoFillBackground(False)
        self.viewport().setAutoFillBackground(False)
        self.cards = {}
        self.thread_id = None
        self.history_known = False
        self.last_turn_id = None
        self.item_turns = {}
        self.tool_groups = {}
        self.suppressed_deltas = set()
        self.completed_items = set()
        self._scroll_target = None
        self._scroll_restore = QtCore.QTimer(self)
        self._scroll_restore.setSingleShot(True)
        self._scroll_restore.timeout.connect(self.restore_scroll)
        self.verticalScrollBar().actionTriggered.connect(self.cancel_scroll_restore)
        self.verticalScrollBar().sliderPressed.connect(self.cancel_scroll_restore)
        self.empty = label("从一个想法开始。\n登录后新建对话，描述你想完成的 Houdini 工作。", "welcome", True)
        self.empty.setAlignment(QtCore.Qt.AlignCenter)
        self.empty.setMinimumHeight(170)
        self.layout.addWidget(self.empty)
        self.turn_notice = label("", "warning", True)
        self.turn_notice.hide()
        self.layout.addWidget(self.turn_notice)
        self._notice_turn = None
        self._image_anchor = None
        self.layout.addStretch()

    def set_image_roots(self, roots):
        roots = tuple(Path(root).resolve() for root in roots)
        if roots == self.app_root:
            return
        self.app_root = roots
        for card in self.cards.values():
            card.app_root = roots
            card.update_item(card.item, force=True)

    def reset(self, thread_id=None):
        self.cancel_scroll_restore()
        for card in self.cards.values():
            self.layout.removeWidget(card)
            card.deleteLater()
        self.cards.clear()
        for control in self.tool_groups.values():
            self.layout.removeWidget(control)
            control.deleteLater()
        self.tool_groups.clear()
        self.item_turns.clear()
        self.thread_id = thread_id
        self.history_known = False
        self.last_turn_id = None
        self.suppressed_deltas.clear()
        self.completed_items.clear()
        self.turn_notice.hide()
        self._notice_turn = None
        self.empty.show()

    def hydrate(self, thread):
        if not thread:
            return
        if thread.get("id") != self.thread_id:
            self.reset(thread.get("id"))
        if "turns" in thread:
            self.history_known = True
            self.last_turn_id = (thread["turns"][-1].get("id") if thread["turns"] else None)
        target = self.scroll_target()
        position = 1  # The welcome widget stays at layout index zero.
        for turn in thread.get("turns", []):
            group_placed = False
            complete = turn.get("status") in {"completed", "interrupted", "failed"}
            for item in turn.get("items", []):
                item_id = item.get("id")
                if not item_id:
                    continue
                item_complete = complete or item.get("status") in {"completed", "failed", "declined"}
                if item_id not in self.completed_items or item_complete:
                    self.put(item, preserve_scroll=False, turn_id=turn.get("id"))
                card = self.cards[item_id]
                group = self.tool_groups.get(self.item_turns.get(item_id)) if self.is_tool(item) else None
                if group and not group_placed:
                    self.layout.insertWidget(position, group)
                    position += 1
                    group_placed = True
                if self.layout.indexOf(card) != position:
                    self.layout.insertWidget(position, card)
                position += 1
                # No atomic cursor accompanies thread/read. Never duplicate text by
                # appending pre-snapshot deltas. item/completed replaces the snapshot.
                self.suppressed_deltas.add(item_id)
                if item_complete:
                    self.completed_items.add(item_id)
                card.set_recovering(item_id not in self.completed_items)
        # Same-thread items newer than the read are retained until their native
        # completion. A non-atomic snapshot is not evidence that they were removed.
        if self._notice_turn:
            self.set_turn_notice(self._notice_turn, self.turn_notice.text())
        self.queue_scroll_restore(target)

    @staticmethod
    def is_tool(item):
        return item.get("type") not in {"userMessage", "agentMessage", "reasoning", "plan", "contextCompaction", "imageView"}

    def put(self, item, *, preserve_scroll=True, turn_id=None):
        item_id = item.get("id")
        if not item_id:
            return
        target = self.scroll_target() if preserve_scroll else None
        if item_id in self.cards:
            changed = self.cards[item_id].update_item(item)
        else:
            card = MessageCard(item, self.app_root)
            card.layout_will_change.connect(self.image_will_change)
            card.layout_changed.connect(self.image_changed)
            self.cards[item_id] = card
            self.layout.insertWidget(self.layout.count() - 1, card)
            self.empty.hide()
            changed = True
        if turn_id:
            self.cards[item_id].setProperty("nativeTurnId", turn_id)
        if self.is_tool(item):
            group_id = turn_id or self.item_turns.get(item_id) or self.last_turn_id or "current"
            self.item_turns[item_id] = group_id
            if group_id not in self.tool_groups:
                control = QtWidgets.QToolButton()
                control.setCheckable(True)
                control.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
                control.toggled.connect(lambda _checked, group_id=group_id: self.update_tool_group(group_id))
                self.tool_groups[group_id] = control
                self.layout.insertWidget(self.layout.indexOf(self.cards[item_id]), control)
            self.update_tool_group(group_id)
        if changed and preserve_scroll:
            self.queue_scroll_restore(target)

    def update_tool_group(self, group_id):
        control = self.tool_groups[group_id]
        cards = [self.cards[key] for key, turn_id in self.item_turns.items() if turn_id == group_id]
        set_button_icon(control, "chevron-down" if control.isChecked() else "chevron-right",
                        text="本轮执行详情 · " + str(len(cards)) + " 项", size=16)
        for card in cards:
            # Native images remain in the conversation even when tool internals fold away.
            card.setVisible(control.isChecked() or bool(card.image_tiles))

    def image_will_change(self):
        self._image_anchor = self.scroll_target()

    def image_changed(self):
        if self._image_anchor is not None:
            self.queue_scroll_restore(self._image_anchor)
        self._image_anchor = None

    def set_turn_notice(self, turn_id, text):
        cards = [card for card in self.cards.values() if card.property("nativeTurnId") == turn_id] if turn_id else []
        self._notice_turn = turn_id if text else None
        self.turn_notice.setText(text)
        visible = bool(text and cards)
        if visible:
            position = max(self.layout.indexOf(card) for card in cards) + 1
            if self.layout.indexOf(self.turn_notice) != position:
                target = self.scroll_target()
                self.layout.insertWidget(position, self.turn_notice)
                self.queue_scroll_restore(target)
        self.turn_notice.setVisible(visible)
        return visible

    def apply_event(self, event):
        method, params = event.get("method", ""), event.get("params", {})
        if method == "turn/started":
            self.last_turn_id = (params.get("turn") or {}).get("id") or params.get("turnId") or self.last_turn_id
        if method in {"item/started", "item/completed"}:
            item = params.get("item", {})
            if method == "item/started" and item.get("id") in self.cards:
                return
            self.put(item, turn_id=params.get("turnId"))
            if method == "item/completed" and item.get("id") in self.cards:
                target = self.scroll_target()
                self.completed_items.add(item["id"])
                self.suppressed_deltas.add(item["id"])
                self.cards[item["id"]].set_recovering(False)
                self.queue_scroll_restore(target)
        elif method in {"item/agentMessage/delta", "item/plan/delta"}:
            item_id = params.get("itemId")
            if item_id in self.completed_items:
                return
            if item_id in self.suppressed_deltas:
                return True  # At most one automatic repair, then the native final item.
            card = self.cards.get(item_id)
            item = dict(card.item) if card else {"id": item_id,
                "type": "plan" if method == "item/plan/delta" else "agentMessage", "text": ""}
            item["text"] = item.get("text", "") + params.get("delta", "")
            self.put(item)
        elif method == "item/reasoning/summaryTextDelta":
            item_id = params.get("itemId")
            if item_id in self.completed_items:
                return
            if item_id in self.suppressed_deltas:
                return True
            card = self.cards.get(item_id)
            item = dict(card.item) if card else {"id": item_id, "type": "reasoning"}
            summary = list(item.get("summary", []))
            index = min(100, max(0, params.get("summaryIndex", 0)))
            while len(summary) <= index:
                summary.append("")
            summary[index] += params.get("delta", "")
            item["summary"] = summary
            self.put(item)

    def scroll_target(self):
        if self._scroll_target is not None:
            return self._scroll_target
        bar = self.verticalScrollBar()
        value = bar.value()
        if bar.maximum() - value < 45:
            return (True, None, 0, value)
        anchor = min((card for card in self.cards.values() if not card.isHidden() and card.y() + card.height() > value),
                     key=lambda card: card.y(), default=None)
        return (False, anchor.item["id"] if anchor else None,
                value - anchor.y() if anchor else 0, value)

    def queue_scroll_restore(self, target):
        self._scroll_target = target
        self._scroll_restore.start(0)

    def cancel_scroll_restore(self, *_args):
        self._scroll_restore.stop()
        self._scroll_target = None

    def restore_scroll(self):
        target = self._scroll_target
        if target is None:
            return
        self.layout.activate()

        def after_layout():
            if self._scroll_target is not target:
                return
            self._scroll_target = None
            bottom, item_id, offset, value = target
            anchor = self.cards.get(item_id)
            bar = self.verticalScrollBar()
            bar.setValue(bar.maximum() if bottom else anchor.y() + offset if anchor else value)
        # QTextDocument height changes post another Qt LayoutRequest. Preserve
        # the anchor through that pass, while allowing user scrolling to cancel.
        QtCore.QTimer.singleShot(0, self, after_layout)

    def to_bottom(self):
        self.cancel_scroll_restore()
        self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())
