"""Explicit offscreen preview fixtures; never loaded by the production Panel."""
from __future__ import annotations

import copy
import argparse
import json
import os
import shutil
import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT / "src"))
sys.path.insert(0, str(APP_ROOT))

from PySide6 import QtCore, QtGui, QtWidgets  # noqa: E402

from studio.ui.panel import StudioPanel  # noqa: E402


class PreviewApi:
    def __init__(self, root):
        self.root = Path(root)
        self.calls = []
        self.hold = {}
        self.errors = {}
        self.closed = False
        self.state = {
            "workspace": {"workspace_id": "preview_workspace", "name": "折光实验室  /  离屏预览"},
            "thread_id": "preview_thread", "turn_id": "preview_turn",
            "account_revision": 1,
            "thread_settings": {"thread_id": "preview_thread", "revision": 1,
                                "model": "preview-model", "effort": "high", "source": "native"},
            "turn_settings": {"thread_id": "preview_thread", "turn_id": "preview_turn",
                              "requested_model": "preview-model", "requested_effort": "high",
                              "model": "preview-model", "effort": "high", "confirmation": "requested",
                              "from_model": None, "reason": None},
            "scene_trust": {"thread_id": "preview_thread", "revision": 1, "enabled": False,
                            "available": True, "can_change": True, "pending": False,
                            "scene_epoch": "preview_epoch", "runtime_id": "preview_runtime"},
            "scene_context": {"thread_id": "preview_thread", "scene_epoch": "preview_epoch",
                              "current_scene_epoch": "preview_epoch", "changed": False},
            "codex": {"state": "interrupted", "alive": True, "stop_requested": True},
            "runtime": {"connection": "connected", "main_thread_busy": True, "queue_depth": 1,
                        "active_operation_id": "preview_operation", "scene": {
                            "scene_epoch": "preview_epoch", "hip_path": str(self.root / "refraction.hip"),
                            "display_name": "refraction.hip", "is_new_file": False,
                            "saved_hip_path": str(self.root / "refraction.hip"),
                            "frame": 48, "dirty": True, "observed_at": 1}},
            "pending_requests": []}
        self.account = {"account_revision": 1, "status": "signed_in", "account": {
            "type": "chatgpt", "email": "preview@example.invalid", "planType": "Preview"}}
        self.models = {"account_revision": 1, "catalog_revision": 1, "nextCursor": None,
                       "data": [{"id": "preview_model", "model": "preview-model", "displayName": "预览模型",
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
        if self.closed:
            return False
        self.calls.append((method, path, copy.deepcopy(body)))
        if path in self.hold:
            self.hold[path].append((done, failed, copy.deepcopy(body)))
            return True
        if path in self.errors:
            if failed:
                QtCore.QTimer.singleShot(0, lambda: failed(self.errors[path]) if not self.closed else None)
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
            result = {"thread": self.thread, "model": self.state["thread_settings"]["model"],
                      "reasoningEffort": self.state["thread_settings"]["effort"],
                      "thread_settings": {**self.state["thread_settings"], "thread_id": self.thread["id"]}}
        elif path == "/thread":
            result = {"thread": self.thread}
        elif path == "/reconcile":
            result = {"reconciled": True, "thread": self.thread, "codex_state": self.state["codex"]["state"]}
        elif path == "/turn":
            self.state["codex"]["state"] = "running"
            self.state["turn_settings"] = {"thread_id": self.state["thread_id"], "turn_id": "preview_turn_2",
                                           "requested_model": body.get("model"), "requested_effort": body.get("effort"),
                                           "model": body.get("model"), "effort": body.get("effort"), "confirmation": "requested",
                                           "from_model": None, "reason": None}
            result = {"turn": {"id": "preview_turn_2", "status": "inProgress", "items": []},
                      "turn_settings": self.state["turn_settings"]}
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
            QtCore.QTimer.singleShot(0, lambda: done(snapshot) if not self.closed else None)
        return True

    def close(self):
        self.closed = True


def process_until(predicate, timeout=3000):
    timer = QtCore.QElapsedTimer()
    timer.start()
    while not predicate():
        QtWidgets.QApplication.processEvents(QtCore.QEventLoop.AllEvents, 20)
        if timer.elapsed() >= timeout:
            raise AssertionError("Timed out waiting for Qt preview callback")


def fixture_image(path):
    # Existing local test image: used only as image data, never a product background or icon.
    shutil.copyfile(APP_ROOT / "src" / "studio" / "ui" / "assets" / "rain-night-studio.png", path)


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


def capture_panel_previews(root, *, widths=(360, 440, 720), states=None):
    """Capture layout fixtures only; all service results are explicit local data."""
    app = QtWidgets.QApplication.instance()
    if app is None or app.platformName() != "offscreen":
        raise RuntimeError("Panel previews require an isolated offscreen application")
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    api = PreviewApi(root)
    api.state["runtime"]["scene"].update(display_name="bookcase.hip", hip_path=str(root / "bookcase.hip"))
    api.thread["turns"][0]["items"][0]["content"][0]["text"] = "创建一个开放式书架，分成四个等高格，保留背板。"
    api.thread["turns"][0]["items"][1]["text"] = "这是明确的离屏界面夹具。下方使用仓库已有 PNG 测试图片解码、结果图尺寸与放大预览。"
    picture = root / "layout-fixture.png"
    fixture_image(picture)
    api.thread["turns"][0]["items"].append({"id": "native_picture", "type": "imageView", "path": str(picture)})
    panel = StudioPanel(api=api, auto_poll=False, image_roots=(root,))
    records = []
    scale = os.environ.get("QT_SCALE_FACTOR", "1")
    try:
        panel.show()
        process_until(lambda: len(panel.transcript.cards) == 4 and panel.models_loaded)
        tile = panel.transcript.cards["native_picture"].images.itemAt(0).widget()
        process_until(lambda: not tile.picture.pixmap().isNull())
        panel.input.insertPlainText("把宽度改为 1.6 米，其他尺寸保留。\n参考图片中的分格比例。")
        baseline = copy.deepcopy(api.state)
        cases = {360: ("working", "approval", "unknown", "model-popup", "short-pane"),
                 440: ("idle", "attachments", "invalid-model"), 720: ("result-image",)}
        for width in widths:
            for state in states or cases.get(width, ("idle",)):
                api.state = copy.deepcopy(baseline)
                api.state["thread_settings"]["revision"] = len(records) + 1
                api.state["codex"].update(state="completed", stop_requested=False)
                api.state["runtime"].update(main_thread_busy=False, active_operation_id=None, queue_depth=0)
                api.operation.update(state="finished", mutation_outcome="completed", checks_outcome="passed")
                panel.attachments.clear()
                panel.selection_reference = None
                panel.model_controls.popup.hide()
                panel.render_attachments()
                panel.show_notice("")
                panel.model_controls.apply_native(api.state["thread_settings"], restore=True)
                if state in {"working", "short-pane"}:
                    api.state["codex"].update(state="running")
                    api.state["runtime"].update(main_thread_busy=True, active_operation_id="preview_operation", queue_depth=1)
                    api.operation.update(state="running", mutation_outcome="unknown", checks_outcome="not_run")
                    panel.set_selection({"nodes": ["/obj/bookcase/frame", "/obj/bookcase/shelves", "/obj/bookcase/back"],
                                         "scene_epoch": "preview_epoch"})
                    panel.add_images([picture])
                    process_until(lambda: panel.attachments[0]["status"] == "ready")
                    attached = next(iter(panel.attachment_tiles.values()))
                    process_until(lambda: not attached.picture.pixmap().isNull())
                elif state == "attachments":
                    panel.add_images([picture, picture])
                    process_until(lambda: all(item["status"] == "ready" for item in panel.attachments))
                    process_until(lambda: all(not tile.picture.pixmap().isNull() for tile in panel.attachment_tiles.values()))
                elif state == "approval":
                    api.state["codex"]["state"] = "running"
                    api.state["pending_requests"] = [{"request_id": 1, "method": "item/permissions/requestApproval",
                        "params": {"threadId": "preview_thread", "reason": "允许将此次导出写入所选目录？",
                                   "permissions": {"fileSystem": {"write": ["C:/chosen-output"]}}}}]
                elif state == "unknown":
                    api.state["codex"]["state"] = "unknown"
                    api.state["runtime"]["storage_fault"] = "receipt storage fixture"
                    api.operation.update(state="unknown", mutation_outcome="unknown", checks_outcome="not_run")
                    panel.show_notice("上次提交是否执行尚未确认。请查询上次提交，再决定下一步。")
                elif state == "invalid-model":
                    api.state["thread_settings"].update(model="unavailable-native-model")
                    panel.model_controls.apply_native(api.state["thread_settings"], restore=True)
                panel.resize(width, 520 if state == "short-pane" else 800)
                panel.apply_state(copy.deepcopy(api.state))
                app.processEvents()
                panel.transcript.to_bottom()
                app.processEvents()
                if state == "model-popup":
                    panel.model_controls.button.click()
                    app.processEvents()
                capture = panel.grab()
                name = f"panel-{width}-{state}-scale-{scale}.png"
                if not capture.save(str(root / name)):
                    raise AssertionError("Could not save Panel preview")
                record = {"file": name, "state": state, "requested_width": width,
                          "logical_size": [panel.width(), panel.height()],
                          "image_size": [capture.width(), capture.height()], "dpr": capture.devicePixelRatio()}
                if state == "model-popup":
                    popup = panel.model_controls.popup
                    available = popup.screen().availableGeometry()
                    if not popup.isVisible() or not available.contains(popup.geometry()):
                        raise AssertionError(f"Model popup: visible={popup.isVisible()}, geometry={popup.geometry().getRect()}, "
                                             f"available={available.getRect()}, entry_enabled={panel.model_controls.button.isEnabled()}")
                    popup_name = f"model-popup-{width}-scale-{scale}.png"
                    popup.grab().save(str(root / popup_name))
                    record.update(popup_file=popup_name, popup_geometry=list(popup.geometry().getRect()),
                                  screen_available=list(available.getRect()), popup_contained=True)
                if state == "result-image":
                    tile.enlarge()
                    app.processEvents()
                    enlarged = f"result-image-expanded-scale-{scale}.png"
                    tile.viewer.grab().save(str(root / enlarged))
                    record["expanded_file"] = enlarged
                    tile.viewer.hide()
                records.append(record)
        (root / f"report-scale-{scale}.json").write_text(json.dumps({
            "mode": "Qt offscreen with explicit API and image fixtures", "qt": QtCore.qVersion(), "captures": records,
            "houdini_gui_verified": False, "codex_inference_verified": False,
            "microsoft_pinyin_verified": False, "windows_clipboard_verified": False,
            "cross_monitor_dpi_verified": False}, ensure_ascii=False, indent=2), encoding="utf-8")
        return records
    finally:
        api.close()
        panel.close()
        panel.deleteLater()
        app.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
        app.processEvents()
        app.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scale", default="1")
    parser.add_argument("--case", choices=("all", "high-dpi"), default="all")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.environ["QT_SCALE_FACTOR"] = args.scale
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    configure_preview_fonts(app)
    root = (args.out or APP_ROOT / ".runtime" / "previews" / "panel-productization").resolve()
    if APP_ROOT / ".runtime" not in root.parents:
        raise ValueError("Panel previews must remain beneath this checkout's .runtime")
    root.mkdir(parents=True, exist_ok=True)
    options = {"widths": (360,), "states": ("working", "model-popup")} if args.case == "high-dpi" else {}
    product_captures = capture_panel_previews(root, **options)
    (root / "preview-report.json").write_text(json.dumps({
        "mode": "Qt offscreen; explicit Panel API and image fixtures",
        "panel_layout_captures": product_captures,
        "houdini_gui_verified": False, "codex_inference_verified": False,
        "qt_version": QtCore.qVersion()}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(root))


if __name__ == "__main__":
    main()
