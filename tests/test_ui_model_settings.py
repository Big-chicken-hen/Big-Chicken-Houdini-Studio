"""Focused native Qt projections; no model, account action, or Houdini execution."""
import copy
import json
import os
import unittest
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6 import QtCore, QtGui, QtWidgets  # noqa: E402

from scripts.preview_ui import PreviewApi, configure_preview_fonts, fixture_image, process_until  # noqa: E402
from studio.ui.conversation import image_sources  # noqa: E402
from studio.ui.panel import StudioPanel  # noqa: E402


class PanelProductTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        if cls.app.platformName() != "offscreen":
            raise RuntimeError("These fixtures require an isolated offscreen application")
        configure_preview_fonts(cls.app)
        cls.root = Path(__file__).resolve().parents[1] / ".runtime" / "panel-product-tests"
        cls.root.mkdir(parents=True, exist_ok=True)

    def setUp(self):
        self.api = PreviewApi(self.root)
        self.api.state["codex"].update(state="idle", stop_requested=False)
        self.api.state["runtime"].update(main_thread_busy=False, active_operation_id=None, queue_depth=0)
        self.api.models["data"].append({"id": "catalog-not-the-slug", "model": "second-model", "displayName": "Second",
            "hidden": False, "isDefault": False, "defaultReasoningEffort": "balanced",
            "supportedReasoningEfforts": [{"reasoningEffort": "balanced"}, {"reasoningEffort": "adaptive-max"}],
            "inputModalities": ["text", "image"]})
        self.panel = StudioPanel(api=self.api, auto_poll=False, image_roots=(self.root,))
        self.panel.show()
        process_until(lambda: self.panel.models_loaded and not self.panel.hydrating)

    def tearDown(self):
        self.api.close()
        self.panel.close()
        self.panel.deleteLater()
        self.app.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
        self.app.processEvents()
        self.app.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)

    def choose_model(self, slug):
        index = next(i for i in range(self.panel.models.count()) if self.panel.models.itemData(i)["model"] == slug)
        self.panel.models.setCurrentIndex(index)

    def select_thread(self, thread_id, model="preview-model", effort="high", revision=2):
        self.api.thread = {"id": thread_id, "turns": []}
        self.api.state.update(thread_id=thread_id, turn_id=None)
        self.api.state["thread_settings"] = {"thread_id": thread_id, "revision": revision, "model": model,
                                            "effort": effort, "source": "native"}
        self.panel.thread_selected({"thread": self.api.thread, "model": model, "reasoningEffort": effort,
                                    "thread_settings": self.api.state["thread_settings"]})
        process_until(lambda: not self.panel.hydrating)

    def test_restore_uses_native_settings_and_catalog_refresh_keeps_user_intent(self):
        self.api.state["turn_settings"].update(requested_model="second-model", requested_effort="adaptive-max",
                                                model="rerouted-model", confirmation="rerouted")
        self.panel.model_controls.reset_connection()
        self.panel.apply_state(copy.deepcopy(self.api.state))
        self.assertEqual(self.panel.model_controls.next_model, "preview-model")
        self.assertEqual(self.panel.model_controls.next_effort, "high")
        self.select_thread("other_thread", "second-model", "adaptive-max")
        self.assertEqual(self.panel.model_controls.request_settings(), {
            "expected_thread_id": "other_thread", "settings_revision": 2,
            "model": "second-model", "effort": "adaptive-max"})
        self.api.hold["/models"] = []
        self.panel.load_models()
        loaded, _, _ = self.api.hold["/models"].pop()
        self.choose_model("preview-model")
        self.panel.efforts.setCurrentIndex(self.panel.efforts.findData("ultra"))
        selection = self.panel.model_controls.selection_revision
        loaded({**self.api.models, "catalog_revision": 2})
        self.assertEqual(self.panel.model_controls.next_model, "preview-model")
        self.assertEqual(self.panel.model_controls.next_effort, "ultra")
        self.assertEqual(self.panel.model_controls.selection_revision, selection)
        # Ordinary polling must not rebuild a selector or replace a local override.
        self.panel.apply_state(copy.deepcopy(self.api.state))
        self.assertEqual(self.panel.model_controls.next_effort, "ultra")

    def test_old_account_catalog_cannot_repopulate_or_enable_send(self):
        self.panel.input.insertPlainText("local draft")
        self.api.hold["/models"] = []
        self.panel.load_models()
        stale, _, _ = self.api.hold["/models"].pop()
        self.api.state["account_revision"] = 2
        self.api.account["account_revision"] = 2
        self.panel.apply_state(copy.deepcopy(self.api.state))
        stale({**self.api.models, "catalog_revision": 99})
        self.assertFalse(self.panel.models_loaded)
        self.assertFalse(self.panel.send_button.isEnabled())
        process_until(lambda: bool(self.api.hold["/models"]))
        fresh, _, _ = self.api.hold["/models"].pop()
        fresh({**self.api.models, "account_revision": 2, "catalog_revision": 1})
        self.assertTrue(self.panel.models_loaded)
        self.assertTrue(self.panel.send_button.isEnabled())
        self.panel.apply_models({**self.api.models, "catalog_revision": 100})
        self.assertEqual(self.panel.model_controls.account_revision, 2)
        self.assertEqual(self.panel.model_controls.catalog_revision, 1)

    def test_missing_model_requires_choice_and_incompatible_effort_uses_native_default(self):
        self.panel.input.insertPlainText("edit")
        self.select_thread("missing", "retired-model", "ultra")
        self.assertEqual(self.panel.model_controls.next_model, "retired-model")
        self.assertIn("不可用", self.panel.models.currentText())
        self.assertFalse(self.panel.send_button.isEnabled())
        self.choose_model("second-model")
        self.assertEqual(self.panel.model_controls.next_effort, "balanced")
        self.assertIn("原生默认", self.panel.model_controls.note.text())
        self.panel.input.insertPlainText("edit")
        self.assertTrue(self.panel.send_button.isEnabled())

    def test_submitted_settings_are_bound_and_reroute_does_not_change_next_choice(self):
        self.choose_model("second-model")
        self.panel.efforts.setCurrentIndex(self.panel.efforts.findData("adaptive-max"))
        self.panel.input.insertPlainText("create an asset")
        self.api.hold["/turn"] = []
        self.panel.send()
        done, _, body = self.api.hold["/turn"].pop()
        self.assertEqual(body["model"], "second-model")
        self.assertEqual(body["expected_thread_id"], "preview_thread")
        self.assertEqual(body["settings_revision"], 1)
        self.assertFalse(self.panel.models.isEnabled())
        self.assertTrue(self.panel.input.isEnabled())
        self.panel.input.insertPlainText("\nnext draft")
        requested = {"thread_id": "preview_thread", "turn_id": "sent_turn", "requested_model": "second-model",
                     "requested_effort": "adaptive-max", "model": "second-model", "effort": "adaptive-max",
                     "confirmation": "requested", "from_model": None, "reason": None}
        done({"turn": {"id": "sent_turn", "status": "inProgress", "items": []}, "turn_settings": requested})
        self.assertIn("本轮已请求", self.panel.model_controls.current.text())
        self.api.state.update(turn_id="sent_turn", turn_settings={**requested, "model": "routed-model",
                             "from_model": "second-model", "confirmation": "rerouted", "reason": "test_reason"})
        self.api.state["codex"]["state"] = "running"
        self.panel.apply_state(copy.deepcopy(self.api.state))
        self.assertIn("routed-model", self.panel.model_controls.current.text())
        self.assertEqual(self.panel.model_controls.next_model, "second-model")
        self.assertEqual(self.panel.model_controls.next_effort, "adaptive-max")
        self.panel.model_controls.apply_turn({**requested, "turn_id": "old_turn", "model": "wrong"},
                                             active=True, turn_id="sent_turn")
        self.assertIn("routed-model", self.panel.model_controls.current.text())
        self.assertIn("next draft", self.panel.input.toPlainText())
        self.panel.model_controls.apply_turn(None, active=True, turn_id="unconfirmed_new_turn")
        self.assertTrue(self.panel.model_controls.current.isHidden())

    def test_thread_drafts_keep_document_cursor_selection_and_late_attachment_owner(self):
        self.panel.input.insertPlainText("draft A")
        document = self.panel.input.document()
        self.panel.set_selection({"nodes": ["/obj/asset"], "scene_epoch": "preview_epoch"})
        picture = self.root / "draft-reference.png"
        fixture_image(picture)
        self.api.hold["/attachments"] = []
        self.panel.add_images([picture])
        tile = next(iter(self.panel.attachment_tiles.values()))
        process_until(lambda: not tile.picture.pixmap().isNull())
        attached, _, _ = self.api.hold["/attachments"].pop()
        self.select_thread("thread_B")
        self.panel.input.insertPlainText("draft B")
        attached({"attachment_id": "saved.png", "name": picture.name, "path": str(picture)})
        self.assertEqual(self.panel.attachments, [])
        self.assertIsNone(self.panel.selection_reference)
        self.select_thread("preview_thread", revision=3)
        self.assertIs(self.panel.input.document(), document)
        self.assertEqual(self.panel.input.toPlainText(), "draft A")
        self.assertEqual(self.panel.input.textCursor().position(), len("draft A"))
        self.assertEqual(self.panel.attachments[0]["attachment_id"], "saved.png")
        self.assertEqual(self.panel.selection_reference["nodes"], ["/obj/asset"])
        self.panel.input.undo()
        self.assertEqual(self.panel.input.toPlainText(), "")
        self.select_thread("thread_B", revision=4)
        self.assertEqual(self.panel.input.toPlainText(), "draft B")
        compact_height = self.panel.input.maximumHeight()
        self.panel.input.insertPlainText("\n".join(["next paragraph"] * 12))
        self.app.processEvents()
        self.assertGreater(self.panel.input.maximumHeight(), compact_height)

    def test_save_as_keeps_reference_but_new_scene_marks_context_and_selection_stale(self):
        self.panel.input.insertPlainText("keep the local draft")
        self.panel.set_selection({"nodes": ["/obj/asset"], "scene_epoch": "preview_epoch"})
        self.api.state["scene_context"].update(scene_epoch=None, changed=True)
        self.panel.apply_state(copy.deepcopy(self.api.state))
        self.assertTrue(self.panel.scene_context_note.isHidden())
        diagnostics = json.loads(self.panel.scene_label.toolTip())
        self.assertIsNone(diagnostics["scene_context"]["scene_epoch"])
        self.api.state["scene_context"]["scene_epoch"] = "preview_epoch"
        scene = self.api.state["runtime"]["scene"]
        scene.update(display_name="B.hip", hip_path=str(self.root / "B.hip"), saved_hip_path=str(self.root / "B.hip"))
        self.panel.apply_state(copy.deepcopy(self.api.state))
        self.assertIn("B.hip", self.panel.workspace_name.text())
        self.assertTrue(self.panel.scene_context_note.isHidden())
        self.assertIn("已引用：1 个节点", self.panel.reference_label.text())
        self.assertTrue(self.panel.send_button.isEnabled())
        scene.update(scene_epoch="replacement_epoch", display_name="未保存场景", is_new_file=True, saved_hip_path=None)
        self.api.state["scene_context"] = {"thread_id": "preview_thread", "scene_epoch": "preview_epoch",
                                           "current_scene_epoch": "replacement_epoch", "changed": True}
        self.panel.apply_state(copy.deepcopy(self.api.state))
        self.assertIn("来自之前", self.panel.reference_label.text())
        self.assertTrue(self.panel.scene_context_note.isVisible())
        self.assertFalse(self.panel.send_button.isEnabled())
        self.assertEqual(self.panel.input.toPlainText(), "keep the local draft")

    def test_image_roots_are_workspace_scoped_and_narrow_model_bar_stays_visible(self):
        workspace = self.panel.paths.workspace("preview_workspace")
        roots = (workspace / "attachments", workspace / "artifacts")
        allowed = {"type": "userMessage", "content": [{"type": "localImage", "path": str(roots[0] / "reference.png")}]}
        outside = {"type": "imageView", "path": str(self.panel.paths.root / "private.png")}
        self.assertEqual(len(image_sources(allowed, roots)), 1)
        self.assertEqual(image_sources(outside, roots), [])
        for width in (360, 440, 720):
            self.panel.resize(width, 900)
            self.app.processEvents()
            self.assertEqual(self.panel.width(), width)
            self.assertTrue(self.panel.model_controls.isVisible())
            self.assertTrue(self.panel.models.isVisible())
            self.assertTrue(self.panel.efforts.isVisible())
            self.assertLessEqual(self.panel.models.mapTo(self.panel, QtCore.QPoint()).x() + self.panel.models.width(), width)

    def test_file_mime_uses_attachments_and_old_selection_read_cannot_bind_new_scene(self):
        picture = self.root / "dropped-reference.png"
        fixture_image(picture)
        mime = QtCore.QMimeData()
        mime.setUrls([QtCore.QUrl.fromLocalFile(str(picture))])
        mime.setText("file MIME fallback")
        self.panel.input.insertPlainText("draft")
        self.assertTrue(self.panel.input.canInsertFromMimeData(mime))
        self.panel.input.insertFromMimeData(mime)
        process_until(lambda: self.panel.attachments and self.panel.attachments[0]["status"] == "ready")
        tile = next(iter(self.panel.attachment_tiles.values()))
        process_until(lambda: not tile.picture.pixmap().isNull())
        self.assertEqual(self.panel.input.toPlainText(), "draft")
        self.assertEqual(sum(path == "/attachments" for _, path, _ in self.api.calls), 1)
        self.api.hold["/selection"] = []
        self.panel.request_selection()
        selected, _, _ = self.api.hold["/selection"].pop()
        self.api.state["runtime"]["scene"]["scene_epoch"] = "replacement"
        self.panel.apply_state(copy.deepcopy(self.api.state))
        selected({"nodes": ["/obj/new_scene_node"], "scene_epoch": "replacement"})
        self.assertIsNone(self.panel.selection_reference)

    def test_previous_connection_and_closed_panel_ignore_late_callbacks(self):
        old = self.api
        self.choose_model("second-model")
        self.panel.efforts.setCurrentIndex(self.panel.efforts.findData("adaptive-max"))
        old.hold["/account"] = []
        old.hold["/threads"] = []
        self.panel.refresh_account()
        self.panel.load_threads()
        account_done, account_failed, _ = old.hold["/account"].pop()
        threads_done, _, _ = old.hold["/threads"].pop()
        self.api = PreviewApi(self.root)
        self.api.models = copy.deepcopy(old.models)
        self.api.state["codex"].update(state="idle", stop_requested=False)
        self.panel.api = self.api
        self.panel.connect_bridge()
        process_until(lambda: self.panel.models_loaded and not self.panel.hydrating)
        account_done({"account_revision": 999, "status": "signed_out", "account": None})
        account_failed("old account failure")
        threads_done({"data": [{"id": "obsolete", "preview": "obsolete"}]})
        self.assertEqual(self.panel.account_revision, 1)
        self.assertTrue(self.panel.logged_in)
        self.assertEqual(self.panel.model_controls.next_model, "second-model")
        self.assertEqual(self.panel.model_controls.next_effort, "adaptive-max")
        self.assertEqual(self.panel.threads.findData("obsolete"), -1)
        self.panel.close()
        account_done({"account_revision": 1000, "status": "signed_out", "account": None})
        self.assertEqual(self.panel.account_revision, 1)
        old.close()

if __name__ == "__main__":
    unittest.main()
