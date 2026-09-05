"""Explicit offscreen preview fixtures; never loaded by the production Panel."""
from __future__ import annotations

import copy
import json
import os
import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT / "src"))

from PySide6 import QtCore, QtGui, QtWidgets  # noqa: E402

from studio.common import AppPaths  # noqa: E402
from studio.ui.launcher import StudioLauncher  # noqa: E402
from studio.ui.panel import StudioPanel  # noqa: E402


class PreviewApi:
    def __init__(self, root):
        self.root = Path(root)
        self.calls = []
        self.hold = {}
        self.errors = {}
        self.state = {
            "workspace": {"workspace_id": "preview_workspace", "name": "折光实验室  /  离屏预览"},
            "thread_id": "preview_thread", "turn_id": "preview_turn",
            "codex": {"state": "interrupted", "alive": True, "stop_requested": True},
            "runtime": {"connection": "connected", "main_thread_busy": True, "queue_depth": 1,
                        "active_operation_id": "preview_operation", "scene": {
                            "scene_epoch": "preview_epoch", "hip_path": str(self.root / "refraction.hip"),
                            "frame": 48, "dirty": True, "observed_at": 1}},
            "pending_requests": []}
        self.account = {"account": {"type": "chatgpt", "email": "preview@example.invalid", "planType": "Preview"}}
        self.models = {"data": [{"id": "preview_model", "model": "preview-model", "displayName": "模型列表 · 预览夹具",
                                "isDefault": True, "defaultReasoningEffort": "high",
                                "supportedReasoningEfforts": [{"reasoningEffort": "high", "description": "预览档位"},
                                                              {"reasoningEffort": "ultra", "description": "预览档位"}]}]}
        self.thread = {"id": "preview_thread", "turns": [{"id": "preview_turn", "status": "interrupted", "items": [
            {"id": "user_1", "type": "userMessage", "content": [{"type": "text", "text": "把选中的几何体做成磨砂玻璃，保留轮廓，先调整材质再看一帧效果。"}]},
            {"id": "agent_1", "type": "agentMessage", "text": "材质参数已提交给 Houdini。你刚刚停止了本轮对话，当前 cook 仍在运行。\n\n请在 **执行记录** 查看原操作的持久化结果。"},
            {"id": "tool_1", "type": "mcpToolCall", "tool": "execute", "status": "inProgress", "arguments": {"label": "调整玻璃材质"}}
        ]}]}
        self.operation = {"operation_id": "preview_operation", "state": "running", "kind": "execute", "label": "调整玻璃材质 · 定向 cook",
                          "scene_epoch": "preview_epoch", "mutation_outcome": "unknown", "checks_outcome": "not_run",
                          "external_side_effects": "unknown", "automatic_retry_safe": False, "result_ref": None}
        self.records = [{"id": "decision_1", "body": "保留原始几何体；材质变化在独立节点中完成。", "created_at": 1}]
        self.events = []

    def call(self, method, path, body=None, done=None, failed=None, unique=False):
        self.calls.append((method, path, copy.deepcopy(body)))
        if path in self.hold:
            self.hold[path].append((done, failed, copy.deepcopy(body)))
            return True
        if path in self.errors:
            if failed:
                QtCore.QTimer.singleShot(0, lambda: failed(self.errors[path]))
            return True
        if path == "/state":
            result = self.state
        elif path.startswith("/events"):
            result = {"events": self.events, "cursor": len(self.events), "resync_required": False}
        elif path == "/account":
            result = self.account
        elif path == "/account/login":
            result = {"authUrl": "https://example.invalid/explicit-preview-login", "loginId": "preview_login"}
        elif path == "/models":
            result = self.models
        elif path == "/threads":
            result = {"data": [{"id": self.thread["id"], "preview": "玻璃材质探索 · 原生历史"}]}
        elif path == "/threads/select":
            result = {"thread": self.thread}
        elif path == "/thread":
            result = {"thread": self.thread}
        elif path == "/reconcile":
            result = {"reconciled": True, "thread": self.thread, "codex_state": self.state["codex"]["state"]}
        elif path == "/turn":
            self.state["codex"]["state"] = "running"
            result = {"turn": {"id": "preview_turn_2", "status": "inProgress", "items": []}}
        elif path == "/stop":
            result = {"codex_interrupt_requested": True, "scene": {"future_operations_stopped": True}}
        elif path == "/operations":
            result = {"operations": [self.operation]}
        elif path.endswith("/cancel"):
            result = self.operation
        elif "/detail?" in path:
            result = {"operation_id": self.operation["operation_id"], "available": True, "text": '{"evidence":"page"}',
                      "offset": 0, "next_offset": None, "total_characters": 19}
        elif path.startswith("/operations/"):
            result = self.operation
        elif path == "/selection":
            result = {"nodes": ["/obj/glass"], "scene_epoch": "preview_epoch"}
        elif path == "/attachments":
            result = {"attachment_id": "preview_attachment.png", "name": Path(body["path"]).name, "path": body["path"]}
        elif path == "/requests/respond":
            self.state["pending_requests"] = [r for r in self.state["pending_requests"] if r["request_id"] != body["request_id"]]
            result = {"responded": True}
        elif path == "/memory":
            if body.get("action") == "list":
                result = {"records": self.records}
            else:
                result = {"id": "new_decision", "committed": True}
        else:
            raise AssertionError("Unexpected preview route: " + path)
        snapshot = copy.deepcopy(result)
        if done:
            QtCore.QTimer.singleShot(0, lambda: done(snapshot))
        return True


def process_until(predicate, timeout=3000):
    timer = QtCore.QElapsedTimer()
    timer.start()
    while not predicate():
        QtWidgets.QApplication.processEvents(QtCore.QEventLoop.AllEvents, 20)
        if timer.elapsed() >= timeout:
            raise AssertionError("Timed out waiting for Qt preview callback")


def fixture_image(path):
    image = QtGui.QImage(440, 260, QtGui.QImage.Format_RGB32)
    image.fill(QtGui.QColor("#DDE7CA"))
    painter = QtGui.QPainter(image)
    painter.setRenderHint(QtGui.QPainter.Antialiasing)
    painter.setPen(QtGui.QPen(QtGui.QColor("#5C7550"), 3))
    painter.setBrush(QtGui.QColor("#B4C69B"))
    painter.drawRoundedRect(QtCore.QRectF(125, 45, 185, 160), 45, 45)
    painter.setPen(QtGui.QColor("#384A2C"))
    painter.drawText(QtCore.QRectF(0, 215, 440, 35), QtCore.Qt.AlignCenter, "IMAGE DECODING FIXTURE")
    painter.end()
    image.save(str(path))


def configure_preview_fonts(app):
    # Windows' offscreen Qt plugin does not enumerate installed fonts. Register
    # existing font files only in this process; never install or change fonts.
    if not QtGui.QFontDatabase.families():
        font_dir = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
        for name in ("msyh.ttc", "msyhbd.ttc", "segoeui.ttf", "consola.ttf"):
            path = font_dir / name
            if path.is_file():
                QtGui.QFontDatabase.addApplicationFont(str(path))
    app.setFont(QtGui.QFont("Microsoft YaHei UI", 10))


def main():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    configure_preview_fonts(app)
    root = APP_ROOT / ".runtime" / "previews"
    root.mkdir(parents=True, exist_ok=True)
    api = PreviewApi(root)
    panel = StudioPanel(api=api, auto_poll=False)
    panel.resize(850, 1040)
    panel.show()
    process_until(lambda: len(panel.transcript.cards) == 3)
    picture = root / "image-fixture.png"
    fixture_image(picture)
    panel.add_images([str(picture)])
    process_until(lambda: panel.attachment_layout.count() == 1)
    tile = panel.attachment_layout.itemAt(0).widget()
    process_until(lambda: not tile.picture.pixmap().isNull())
    panel.input.setPlainText("等当前操作结束后，继续检查粗糙度。")
    app.processEvents()
    panel.grab().save(str(root / "panel-conversation.png"))
    panel.tabs.setCurrentIndex(1)
    process_until(lambda: panel.operation_list.count() > 0)
    panel.operation_list.setCurrentRow(0)
    process_until(lambda: "mutation_outcome" in panel.operation_detail.toPlainText())
    app.processEvents()
    panel.grab().save(str(root / "panel-operations.png"))
    panel.tabs.setCurrentIndex(2)
    process_until(lambda: panel.decisions.count() > 0)
    app.processEvents()
    panel.grab().save(str(root / "panel-decisions.png"))
    # Launcher uses the actual empty workspace list; no sample workspace is written.
    launcher = StudioLauncher(paths=AppPaths())
    launcher.show()
    app.processEvents()
    launcher.grab().save(str(root / "launcher.png"))
    (root / "preview-report.json").write_text(json.dumps({
        "mode": "Qt offscreen; explicit API fixture", "screenshots": ["panel-conversation.png", "panel-operations.png", "panel-decisions.png", "launcher.png"],
        "houdini_gui_verified": False, "codex_inference_verified": False,
        "qt_version": QtCore.qVersion()}, ensure_ascii=False, indent=2), encoding="utf-8")
    panel.close()
    launcher.close()
    print(str(root))


if __name__ == "__main__":
    main()
