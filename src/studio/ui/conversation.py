"""Native conversation projection. No persisted or synthesized chat history."""
from __future__ import annotations

import base64
import json
import math
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from ..message_projection import MessageProjection, ProjectedItem
from .activity import activity_segments, is_tool, tool_facts
from .icons import set_button_icon
from .shared import Task, button, label
from .theme import COLORS, apply_theme


class SafeBrowser(QtWidgets.QTextBrowser):
    """Markdown may contain links; it may never fetch files or remote resources."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.source_text = None
        self.setOpenLinks(False)
        self.setOpenExternalLinks(False)
        self.anchorClicked.connect(self.open_link)
        self.document().setDefaultStyleSheet(
            "p { margin: 6px 0; } pre { background: " + COLORS["surface_elevated"] + "; padding: 10px; } "
            "a { color: " + COLORS["primary_pink"] + "; } code { font-family: Consolas; }")

    def loadResource(self, kind, url):
        return QtCore.QByteArray()

    def contextMenuEvent(self, event):
        menu = self.createStandardContextMenu()
        if self.source_text:
            menu.addSeparator()
            menu.addAction("复制完整正文", lambda: QtWidgets.QApplication.clipboard().setText(self.source_text()))
        menu.exec(event.globalPos())
        menu.deleteLater()

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
        self.retired = False
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
        if self.retired:
            return
        self.geometry_will_change.emit()
        self.decoded = result
        self.failure = None
        self.set_display_size(*self._box)
        self.picture.setToolTip("点击放大此图片")
        self.geometry_changed.emit()

    def unavailable(self, message):
        if self.retired:
            return
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
        self.retired = False
        self.rendered_text = None
        self.markdown_updates = 0
        self.render_timer = QtCore.QTimer(self)
        self.render_timer.setSingleShot(True)
        self.render_timer.setInterval(50)
        self.render_timer.timeout.connect(self.render_item)
        self.fit_timer = QtCore.QTimer(self)
        self.fit_timer.setSingleShot(True)
        self.fit_timer.timeout.connect(self.fit_text)
        self.image_tiles = []
        self.activity_expanded = True
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        self.title = label("", "messageAuthor", True)
        layout.addWidget(self.title)
        self.sync_note = label("恢复中的消息：完整内容到达时更新，也可手动刷新连接。", "muted", True)
        self.sync_note.hide()
        layout.addWidget(self.sync_note)
        self.activity_warning = label("", "warning", True)
        self.activity_warning.setProperty("tone", "warning")
        self.activity_warning.hide()
        layout.addWidget(self.activity_warning)
        self.text = SafeBrowser()
        self.text.document().documentLayout().documentSizeChanged.connect(lambda _size: self.schedule_fit())
        self.text.source_text = self.source_text
        self.text.setToolTip("右键可复制完整正文")
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
        self.image_caption = label("", "muted", True)
        self.image_caption.hide()
        layout.addWidget(self.image_caption)
        self.details_button = button("查看工具内容", self.toggle_details, "quiet")
        layout.addWidget(self.details_button, 0, QtCore.Qt.AlignLeft)
        self.details = QtWidgets.QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setMaximumHeight(190)
        self.details.hide()
        layout.addWidget(self.details)
        self.update_item(item)

    def retire(self):
        self.retired = True
        self.render_timer.stop()
        self.fit_timer.stop()
        self.hide()
        for _source, tile in self.image_tiles:
            tile.retired = True

    def source_text(self):
        if self.item.get("type") == "userMessage":
            return "\n\n".join(c.get("text", "") for c in self.item.get("content", []) if c.get("type") == "text")
        if self.item.get("type") == "reasoning":
            return "\n".join(self.item.get("summary", []))
        return self.item.get("text", "")

    def update_item(self, item, *, force=False, defer=False):
        if self.retired or (self.item == item and not force and not self.render_timer.isActive()):
            return False
        self.item = dict(item)  # Canonical data is current even while painting is coalesced.
        if defer:
            if not self.render_timer.isActive():
                self.render_timer.start()
        else:
            self.render_item()
        return True

    def render_item(self):
        self.render_timer.stop()
        if self.retired:
            return
        self.layout_will_change.emit()
        item = self.item
        kind = item.get("type", "item")
        role = "user" if kind == "userMessage" else "assistant"
        if self.property("studioRole") != role:
            self.setProperty("studioRole", role)
            self.style().unpolish(self)
            self.style().polish(self)
        status = item.get("status", "")
        titles = {"userMessage": "你", "agentMessage": "Codex", "reasoning": "Codex · 思考摘要",
                  "plan": "Codex · 计划", "contextCompaction": "Codex · 原生上下文压缩",
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
            cursor = self.text.textCursor()
            anchor, position = cursor.anchor(), cursor.position()
            self.text.setMarkdown(self.rendered_text)
            self.markdown_updates += 1
            cursor = QtGui.QTextCursor(self.text.document())
            last = self.text.document().characterCount() - 1
            cursor.setPosition(min(anchor, last))
            cursor.setPosition(min(position, last), QtGui.QTextCursor.KeepAnchor)
            self.text.setTextCursor(cursor)
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
                tile.hide()
                tile.retired = True
                tile.deleteLater()
        self.image_scroll.setVisible(bool(sources))
        facts = tool_facts(item) if is_tool else {"warning": "", "caption": ""}
        if is_tool:
            title = {"hia_context": "场景观察", "hia_inspect": "目标查询", "hia_lookup": "节点与帮助查询",
                     "hia_execute_hom": "场景操作", "hia_capture": "获取视图", "hia_operation": "执行记录",
                     "hia_project_memory": "项目约定"}.get(item.get("tool"), titles.get(kind, "工具活动"))
            self.title.setText(title)  # Native item completion is not HOM completion.
        self.activity_warning.setText(facts["warning"])
        self.activity_warning.setVisible(bool(facts["warning"]))
        self.image_caption.setText(facts["caption"])
        self.image_caption.setVisible(bool(sources and facts["caption"]))
        self.set_activity_expanded(self.activity_expanded)
        self.fit_images()
        if text_changed:
            QtCore.QTimer.singleShot(0, self, self.fit_text)
        self.layout_changed.emit()

    def set_activity_expanded(self, expanded):
        collapse = self.activity_expanded and not expanded
        self.activity_expanded = expanded
        if not is_tool(self.item):
            return
        critical = bool(self.activity_warning.text()) or not self.sync_note.isHidden()
        if collapse:
            self.details.hide()
        explicit_detail = not self.details.isHidden()
        self.title.setVisible(expanded or critical or explicit_detail)
        self.details_button.setVisible(expanded or critical or explicit_detail)
        self.text.setVisible(expanded and bool(self.rendered_text))
        self.setVisible(expanded or critical or bool(self.image_tiles) or explicit_detail)

    def set_recovering(self, recovering):
        self.sync_note.setVisible(recovering)
        self.set_activity_expanded(self.activity_expanded)

    def schedule_fit(self):
        if not self.retired:
            self.fit_timer.start()

    def fit_text(self):
        if self.retired:
            return
        self.text.document().setTextWidth(max(100, self.text.viewport().width()))
        chrome = max(8, self.text.height() - self.text.viewport().height())
        height = math.ceil(self.text.document().size().height()) + chrome
        self.text.setFixedHeight(max(28, height))
        self.text.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.schedule_fit()
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
        self.set_activity_expanded(self.activity_expanded)


class Transcript(QtWidgets.QScrollArea):
    older_requested = QtCore.Signal()
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
        self.segment_items = {}
        self.turn_gaps = {}
        self.projection = MessageProjection()
        self.history_revision = 0
        self._scroll_target = None
        self._scroll_restore = QtCore.QTimer(self)
        self._scroll_restore.setSingleShot(True)
        self._scroll_restore.timeout.connect(self.restore_scroll)
        self.verticalScrollBar().actionTriggered.connect(self.cancel_scroll_restore)
        self.verticalScrollBar().sliderPressed.connect(self.cancel_scroll_restore)
        self.older = button("加载更早消息", self.older_requested.emit, "quiet")
        self.older.hide()
        self.layout.addWidget(self.older, 0, QtCore.Qt.AlignLeft)
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

    def clear_widgets(self):
        self.cancel_scroll_restore()
        self._image_anchor = None
        for card in self.cards.values():
            card.retire()
            self.layout.removeWidget(card)
            card.deleteLater()
        self.cards.clear()
        for control in self.tool_groups.values():
            self.layout.removeWidget(control)
            control.hide()
            control.deleteLater()
        self.tool_groups.clear()
        self.segment_items.clear()
        for gap in self.turn_gaps.values():
            self.layout.removeWidget(gap)
            gap.hide()
            gap.deleteLater()
        self.turn_gaps.clear()
        self.item_turns.clear()
        self.turn_notice.hide()
        self._notice_turn = None
        self.empty.show()
        self.older.hide()

    def reset(self, thread_id=None, *, generation=None):
        generation = self.projection.generation if generation is None else generation
        self.clear_widgets()
        self.projection = MessageProjection()
        self.projection.bind(thread_id, generation)
        self.thread_id = thread_id
        self.history_known = False
        self.last_turn_id = None
        self.history_revision = 0

    def bind(self, thread_id, generation):
        if thread_id == self.thread_id and generation == self.projection.generation:
            return
        if thread_id != self.thread_id:
            self.reset(thread_id, generation=generation)
            return
        target = self.scroll_target()
        self.projection.bind(thread_id, generation)
        if target[1] is not None:
            key = target[1]
            target = (target[0], self.projection.key(key.turn, key.item), target[2], target[3])
        self.clear_widgets()
        for key in self.projection.ordered_keys():
            self.display(key, preserve_scroll=False)
        self.arrange()
        self.queue_scroll_restore(target)

    def card(self, item_id, turn_id=None):
        matches = [card for key, card in self.cards.items()
                   if key.item == item_id and (turn_id is None or key.turn == turn_id)]
        if len(matches) != 1:
            raise KeyError((turn_id, item_id))
        return matches[0]

    def hydrate(self, thread, *, generation=None, revision=None, older=False):
        if not thread:
            return
        generation = self.projection.generation if generation is None else generation
        if self.thread_id is None and generation == self.projection.generation:
            self.bind(thread.get('id'), generation)
        if thread.get('id') != self.thread_id or generation != self.projection.generation:
            return
        self.history_revision = max(self.history_revision + 1, revision or 0) if revision is None else revision
        target = self.scroll_target()
        changed = self.projection.history(thread, generation, self.history_revision, older=older)
        if 'turns' in thread:
            self.history_known = True
        self.last_turn_id = self.projection.turns[-1] if self.projection.turns else None
        for key in changed:
            self.display(key, preserve_scroll=False)
        self.arrange()
        self.queue_scroll_restore(target)

    def arrange(self):
        position = 2
        expanded_items = {key for group_id, keys in self.segment_items.items()
                          if group_id in self.tool_groups and self.tool_groups[group_id].isChecked() for key in keys}
        ordered = [(key, self.cards[key].item) for key in self.projection.ordered_keys() if key in self.cards]
        self.segment_items = activity_segments(ordered)
        for group_id in tuple(self.tool_groups):
            if group_id not in self.segment_items:
                control = self.tool_groups.pop(group_id)
                self.layout.removeWidget(control)
                control.hide()
                control.deleteLater()
        self.item_turns.clear()
        for group_id, keys in self.segment_items.items():
            for key in keys:
                self.item_turns[key] = group_id
            if group_id not in self.tool_groups:
                control = QtWidgets.QToolButton()
                control.setObjectName("quiet")
                control.setCheckable(True)
                control.setChecked(any(key in expanded_items for key in keys))
                control.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
                control.setMinimumHeight(40)
                control.toggled.connect(lambda _checked, group_id=group_id: self.update_tool_group(group_id)
                    if group_id in self.tool_groups else None)
                self.tool_groups[group_id] = control
            self.update_tool_group(group_id)
        previous_turn = None
        for key, _item in ordered:
            card = self.cards.get(key)
            if previous_turn is not None and key.turn != previous_turn:
                if key.turn not in self.turn_gaps:
                    gap = QtWidgets.QWidget()
                    gap.setFixedHeight(16)
                    self.turn_gaps[key.turn] = gap
                self.layout.insertWidget(position, self.turn_gaps[key.turn])
                position += 1
            previous_turn = key.turn
            group = self.tool_groups.get(key)
            if group:
                self.layout.insertWidget(position, group)
                self.layout.setAlignment(group, QtCore.Qt.AlignLeft)
                position += 1
            if self.layout.indexOf(card) != position:
                self.layout.insertWidget(position, card)
            self.layout.setAlignment(card, QtCore.Qt.AlignRight if card.item.get("type") == "userMessage" else QtCore.Qt.AlignmentFlag(0))
            position += 1
        self.fit_cards()
        if self._notice_turn:
            self.set_turn_notice(self._notice_turn, self.turn_notice.text())

    @staticmethod
    def is_tool(item):
        return is_tool(item)

    def put(self, item, *, preserve_scroll=True, turn_id=None):
        turn_id = turn_id or self.last_turn_id
        if not turn_id or not self.thread_id or not item.get('id'):
            return
        key = self.projection.key(turn_id, item['id'])
        if key in self.projection.records:
            return
        self.projection.remember(key)
        self.projection.records[key] = ProjectedItem(dict(item), terminal=item.get('type') == 'userMessage')
        self.display(key, preserve_scroll=preserve_scroll)

    def display(self, key, *, preserve_scroll=True, defer=False):
        record = self.projection.records[key]
        item = record.item
        target = self.scroll_target() if preserve_scroll else None
        if key in self.cards:
            changed = self.cards[key].update_item(item, defer=defer)
        else:
            card = MessageCard(item, self.app_root)
            card.setProperty('nativeTurnId', key.turn)
            card.layout_will_change.connect(lambda key=key, card=card: self.image_will_change()
                if self.cards.get(key) is card and not card.retired else None)
            card.layout_changed.connect(lambda key=key, card=card: self.image_changed()
                if self.cards.get(key) is card and not card.retired else None)
            self.cards[key] = card
            self.layout.insertWidget(self.layout.count() - 1, card)
            self.empty.hide()
            changed = True
        self.cards[key].set_recovering(record.recovering)
        if changed and not defer and preserve_scroll:
            self.arrange()
        if changed and preserve_scroll and not defer:
            self.queue_scroll_restore(target)

    def update_tool_group(self, group_id):
        control = self.tool_groups[group_id]
        cards = [self.cards[key] for key in self.segment_items[group_id]]
        counts = {"查询": 0, "执行": 0, "取图": 0, "其他操作": 0}
        images = 0
        for card in cards:
            tool = card.item.get("tool", "")
            action = (card.item.get("arguments") or {}).get("action")
            query = tool in {"hia_context", "hia_inspect", "hia_lookup"} or (
                tool == "hia_operation" and action in {"get", "detail", "list"}) or (
                tool == "hia_project_memory" and action == "list")
            key = "执行" if tool == "hia_execute_hom" else "取图" if tool == "hia_capture" else "查询" if query else "其他操作"
            counts[key] += 1
            images += len(card.image_tiles)
        parts = [f"{count} 次{kind}" for kind, count in counts.items() if count and kind != "取图"]
        if images:
            parts.append(f"{images} 张视图")
        elif counts["取图"]:
            parts.append(f"{counts['取图']} 次取图")
        title = "在 Houdini 中工作" if all(str(card.item.get("tool", "")).startswith("hia_") for card in cards) else "工具活动"
        set_button_icon(control, "chevron-down" if control.isChecked() else "chevron-right",
                        text=title + "\n" + " · ".join(parts), size=16)
        control.setAccessibleName("工具活动：" + "，".join(parts))
        for card in cards:
            card.set_activity_expanded(control.isChecked())

    def fit_cards(self):
        width = max(120, self.viewport().width())
        for card in self.cards.values():
            if card.item.get("type") == "userMessage":
                card.setFixedWidth(int(width * .86))

    def viewportEvent(self, event):
        result = super().viewportEvent(event)
        if event.type() == QtCore.QEvent.Resize and hasattr(self, "cards"):
            QtCore.QTimer.singleShot(0, self, self.fit_cards)
        return result

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "cards"):
            self.fit_cards()

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

    def mark_gap(self, turn_id=None):
        self.projection.mark_gap(turn_id)
        for key, record in self.projection.records.items():
            if key in self.cards:
                self.cards[key].set_recovering(record.recovering)

    def apply_event(self, event, *, generation=None):
        generation = self.projection.generation if generation is None else generation
        changed = self.projection.event(event, generation)
        defer = event.get('method', '').endswith(('delta', 'summaryTextDelta'))
        for key in changed:
            self.display(key, defer=defer)
        self.last_turn_id = self.projection.turns[-1] if self.projection.turns else None
        return bool(self.projection.recovering_turns())

    def scroll_target(self):
        if self._scroll_target is not None:
            return self._scroll_target
        bar = self.verticalScrollBar()
        value = bar.value()
        if bar.maximum() - value < 45:
            return (True, None, 0, value)
        anchor = min((card for card in self.cards.values() if not card.isHidden() and card.y() + card.height() > value),
                     key=lambda card: card.y(), default=None)
        return (False, next((key for key, card in self.cards.items() if card is anchor), None),
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
