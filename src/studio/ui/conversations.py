"""Compact native conversation manager; drafts and transcript stay in the Panel."""
from urllib.parse import urlencode

from PySide6 import QtCore, QtWidgets

from .shared import button, label
from .theme import apply_theme


class ConversationManager(QtWidgets.QDialog):
    def __init__(self, panel):
        super().__init__(panel)
        self.panel = panel
        self.generation = 0
        self.next_cursor = None
        self.busy = False
        self.closed = False
        self.pending = {}
        self.setObjectName("studioConversationManager")
        self.setWindowTitle("管理对话")
        self.setMinimumSize(330, 390)
        self.resize(460, 520)
        apply_theme(self, popup=True)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText("搜索对话标题")
        self.search.setAccessibleName("搜索对话标题")
        self.search.setMaxLength(160)
        layout.addWidget(self.search)
        self.archived = QtWidgets.QCheckBox("已归档")
        layout.addWidget(self.archived)
        self.rows = QtWidgets.QListWidget()
        layout.addWidget(self.rows, 1)
        self.notice = label("", wrap=True)
        layout.addWidget(self.notice)
        self.more = button("加载更多", lambda: self.load(append=True))
        layout.addWidget(self.more)
        row = QtWidgets.QHBoxLayout()
        self.open_button = button("打开", self.open_selected, "primary")
        self.new_button = button("新对话", self.new_conversation)
        self.rename_button = button("重命名", self.rename)
        for control in (self.open_button, self.new_button, self.rename_button):
            row.addWidget(control)
        layout.addLayout(row)
        row = QtWidgets.QHBoxLayout()
        self.archive_button = button("归档", self.archive)
        self.delete_button = button("删除", self.delete)
        self.reconcile_button = button("核对原生结果", self.reconcile)
        for control in (self.archive_button, self.delete_button, self.reconcile_button):
            row.addWidget(control)
        layout.addLayout(row)
        self.timer = QtCore.QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(300)
        self.timer.timeout.connect(self.load)
        self.search.textChanged.connect(self.search_changed)
        self.archived.toggled.connect(self.load)
        self.rows.currentItemChanged.connect(self.controls)
        self.rows.itemDoubleClicked.connect(self.open_selected)
        self.finished.connect(self.finished_dialog)
        self.controls()
        self.load()

    def finished_dialog(self, _result):
        self.closed = True
        self.generation += 1
        self.timer.stop()

    def selected(self):
        item = self.rows.currentItem()
        return item.data(QtCore.Qt.UserRole) if item else None

    def controls(self, *_):
        selected = self.selected()
        pending = bool(selected and selected["id"] in self.pending)
        available = not self.busy and not pending and bool(selected)
        current_busy = bool(selected and selected["id"] == self.panel.thread_id and not self.panel.new_thread.isEnabled())
        self.open_button.setEnabled(available and not self.archived.isChecked() and self.panel.new_thread.isEnabled())
        self.new_button.setEnabled(not self.busy and self.panel.new_thread.isEnabled())
        self.rename_button.setEnabled(available)
        self.archive_button.setEnabled(available and not current_busy)
        self.archive_button.setText("恢复" if self.archived.isChecked() else "归档")
        self.delete_button.setEnabled(available and not current_busy)
        self.reconcile_button.setVisible(pending)
        self.reconcile_button.setEnabled(pending and not self.busy)
        self.more.setVisible(bool(self.next_cursor))
        self.more.setEnabled(not self.busy)
        if not self.rows.count() and not self.busy:
            self.notice.setText("没有匹配的对话。" if self.search.text() else "暂无已归档对话。" if self.archived.isChecked() else "暂无对话。")

    def search_changed(self):
        self.generation += 1
        self.timer.start()

    def invalidate(self):
        if not self.closed:
            self.generation += 1
            self.load()

    def load(self, *_args, append=False):
        if self.closed:
            return
        self.generation += 1
        generation, account, api = self.generation, self.panel.account_revision, self.panel.api
        selected = self.selected()
        query = {"search": self.search.text(), "archived": str(self.archived.isChecked()).lower()}
        if append and self.next_cursor:
            query["cursor"] = self.next_cursor
        self.busy = True
        self.notice.setText("正在读取对话…")
        self.controls()

        def current():
            return (not self.closed and generation == self.generation and api is self.panel.api
                    and account == self.panel.account_revision)

        def loaded(value):
            if not current():
                return
            if value.get("lifecycle_revision", 0) < (self.panel.lifecycle_revision or 0):
                self.load()
                return
            self.busy = False
            self.pending = {row["thread_id"]: row for row in self.panel.state.get("conversations", {}).get("pending", [])}
            if not append:
                self.rows.clear()
            existing = {self.rows.item(i).data(QtCore.Qt.UserRole)["id"] for i in range(self.rows.count())}
            rows = list(value.get("data", []))
            present = existing | {row["id"] for row in rows}
            rows.extend({"id": key, "name": "待核对 · " + (row.get("title") or "对话")}
                        for key, row in self.pending.items() if key not in present)
            if (not rows and not append and not self.archived.isChecked() and not self.search.text()
                    and self.panel.thread_id and self.panel.thread_id not in self.panel.deleted_threads):
                # Native empty threads may not yet have a persisted list row.
                rows.append({"id": self.panel.thread_id, "name": "当前对话"})
            for thread in rows:
                if thread["id"] in existing or thread["id"] in self.panel.deleted_threads:
                    continue
                item = QtWidgets.QListWidgetItem(thread.get("name") or thread.get("preview") or "未命名对话")
                item.setData(QtCore.Qt.UserRole, thread)
                item.setToolTip(item.text())
                self.rows.addItem(item)
                if selected and selected["id"] == thread["id"]:
                    self.rows.setCurrentItem(item)
            self.next_cursor = value.get("nextCursor")
            self.notice.clear()
            self.controls()

        def failed(message):
            if current():
                self.busy = False
                self.controls()
                self.notice.setText(str(message))
        self.panel.call("GET", "/threads?" + urlencode(query), done=loaded, failed=failed)

    def open_selected(self, *_):
        selected = self.selected()
        if selected and self.open_button.isEnabled():
            self.accept()
            self.panel.select_thread(selected["id"])

    def new_conversation(self):
        self.accept()
        self.panel.select_thread(None)

    def rename(self):
        selected = self.selected()
        if not selected:
            return
        name, accepted = QtWidgets.QInputDialog.getText(self, "重命名对话", "对话标题", text=selected.get("name") or "")
        if accepted and name.strip():
            self.mutate("rename", name=name.strip())

    def archive(self):
        self.mutate("unarchive" if self.archived.isChecked() else "archive")

    def delete(self):
        selected = self.selected()
        if not selected:
            return
        answer = QtWidgets.QMessageBox.question(self, "删除对话", "确定删除此对话？此操作不可恢复。\n"
            "原生删除也可能删除它的派生子对话。\n场景文件、操作收据和生成的资产会保留。",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No, QtWidgets.QMessageBox.No)
        if answer == QtWidgets.QMessageBox.Yes:
            self.mutate("delete", confirm_delete_with_descendants=True)

    def mutate(self, action, **fields):
        selected = self.selected()
        if not selected or self.busy:
            return
        self.request("/threads/manage", {"thread_id": selected["id"], "action": action, **fields})

    def reconcile(self):
        selected = self.selected()
        if selected:
            self.request("/threads/reconcile", {"thread_id": selected["id"]})

    def request(self, path, body):
        self.generation += 1
        self.busy = True
        self.panel.threads_generation += 1
        self.panel.revision += 1  # Discard state/list/selection responses captured before the mutation.
        self.controls()

        def done(value):
            if self.closed:
                self.panel.apply_conversations(value.get("conversations", {}), refresh_manager=False)
                self.panel.refresh()
                return
            self.busy = False
            self.panel.apply_conversations(value.get("conversations", {}), refresh_manager=False)
            self.pending = {row["thread_id"]: row for row in value.get("conversations", {}).get("pending", [])}
            self.notice.setText("已确认。" if value.get("confirmed") else "原生结果尚未确认，草稿已保留。请先核对结果。")
            self.controls()
            self.panel.load_threads()
            self.panel.refresh()
            if value.get("confirmed"):
                self.load()

        def failed(message):
            if not self.closed:
                self.busy = False
                self.controls()
                self.notice.setText(str(message))
            self.panel.refresh()
        self.panel.call("POST", path, body, done=done, failed=failed)
