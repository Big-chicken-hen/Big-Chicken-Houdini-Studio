"""One long native-history recovery case; no Houdini or model inference."""
import base64
import copy
import os
import unittest
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6 import QtCore, QtTest, QtWidgets  # noqa: E402

from scripts.preview_ui import PreviewApi, configure_preview_fonts, fixture_image, process_until  # noqa: E402
from studio.common import AppPaths  # noqa: E402
from studio.ui.panel import StudioPanel  # noqa: E402


class HistoryRecoveryTest(unittest.TestCase):
    def test_long_image_history_has_bounded_reads_reuses_widgets_and_keeps_viewport(self):
        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        configure_preview_fonts(app)
        root = Path(__file__).resolve().parents[1]
        evidence = root / ".runtime" / "ui-history-tests"
        evidence.mkdir(parents=True, exist_ok=True)
        picture = evidence / "reference.png"
        fixture_image(picture)
        image = {"id": "image_item", "type": "mcpToolCall", "tool": "capture", "status": "completed",
                 "result": {"content": [{"type": "image", "mimeType": "image/png",
                                          "data": base64.b64encode(picture.read_bytes()).decode()}]}}
        history = [{"id": "history_" + str(index), "type": "agentMessage",
                    "text": "历史步骤 " + str(index) + "\n\n" + "保留既有网络与明确的参数。" * 16}
                   for index in range(55)]
        history.insert(12, image)
        api = PreviewApi(evidence)
        api.state["codex"]["state"] = "running"
        api.thread = {"id": "preview_thread", "turns": [
            {"id": "old_turn", "status": "completed", "items": history},
            {"id": "live_turn", "status": "inProgress", "items": []}]}
        panel = StudioPanel(paths=AppPaths(root, data_root=evidence / "state", cache_root=evidence / "cache"), api=api, auto_poll=False, image_roots=(evidence,))
        self.addCleanup(panel.deleteLater)
        self.addCleanup(panel.close)
        panel.show()
        process_until(lambda: len(panel.transcript.cards) == len(history) and not panel.hydrating)
        image_card = panel.transcript.card("image_item")
        tile = image_card.images.itemAt(0).widget()
        process_until(lambda: not tile.picture.pixmap().isNull())
        QtTest.QTest.qWait(30)
        sequence = 0

        def event(method, **params):
            nonlocal sequence
            sequence += 1
            return {"sequence": sequence, "method": method,
                    "params": {"threadId": "preview_thread", "turnId": "live_turn", **params}}

        def deliver(events):
            panel.apply_events({"cursor": sequence, "events": events})

        def read_count():
            return sum(method == "GET" and path.startswith("/thread/history?") for method, path, _body in api.calls)

        deliver([event("item/started", item={"id": "live", "type": "agentMessage", "text": ""}),
                 event("item/agentMessage/delta", itemId="live", delta="即时前缀")])
        self.assertEqual(panel.transcript.card("live").item["text"], "即时前缀")
        native = copy.deepcopy(api.thread)
        native["turns"][-1]["items"] = [{"id": "live", "type": "agentMessage", "text": "即时前缀·快照重叠"}]
        QtTest.QTest.qWait(30)
        transcript = panel.transcript
        anchor = transcript.card("history_30")
        transcript.verticalScrollBar().setValue(anchor.y() + 9)
        anchor_y = anchor.mapTo(transcript.viewport(), QtCore.QPoint()).y()
        original_cards = dict(transcript.cards)
        image_key = tile.picture.pixmap().cacheKey()
        document = transcript.card("history_10").text.document()
        image_card.toggle_details()
        QtTest.QTest.qWait(20)
        # Opening details above the anchor is outside history synchronization;
        # record the user's current reading position after that layout settles.
        transcript.verticalScrollBar().setValue(anchor.y() + 9)
        anchor_y = anchor.mapTo(transcript.viewport(), QtCore.QPoint()).y()
        before = read_count()
        api.hold["/thread/history"] = []
        panel.load_history()
        loaded = api.hold["/thread/history"].pop()[0]
        deliver([event("item/agentMessage/delta", itemId="live", delta="·快照重叠"),
                 event("item/started", item={"id": "late", "type": "agentMessage", "text": ""}),
                 event("item/agentMessage/delta", itemId="late", delta="在途事件保留")])
        self.assertEqual(transcript.card("late").item["text"], "在途事件保留")
        loaded({"thread": native})
        QtTest.QTest.qWait(80)
        self.assertEqual(transcript.card("live").item["text"], "即时前缀·快照重叠")
        self.assertEqual(anchor.mapTo(transcript.viewport(), QtCore.QPoint()).y(), anchor_y)
        for key, card in original_cards.items():
            self.assertIs(transcript.cards[key], card)
        self.assertIs(image_card.images.itemAt(0).widget(), tile)
        self.assertEqual(tile.picture.pixmap().cacheKey(), image_key)
        self.assertIs(transcript.card("history_10").text.document(), document)
        self.assertTrue(image_card.details.isVisible())
        self.assertTrue(transcript.card("live").sync_note.isHidden())
        self.assertFalse(panel.history_refresh.isActive())

        # A large terminal item is consumed immediately; history loading no longer
        # buffers/drops it. Ordinary streaming performs no history repair requests.
        oversized = {"id": "oversized_tool", "type": "mcpToolCall", "tool": "inspect", "status": "completed",
                     "result": {"content": [{"type": "text", "text": "bounded evidence\n" * 34000}]}}
        deliver([event("item/completed", item=oversized)])
        self.assertEqual(transcript.card("oversized_tool").item, oversized)
        for _ in range(8):
            deliver([event("item/agentMessage/delta", itemId="live", delta="·流式后续") for _ in range(35)])
            app.processEvents()
        self.assertEqual(read_count() - before, 1)
        self.assertEqual(transcript.card("live").item["text"], "即时前缀·快照重叠" + "·流式后续" * 280)
        final = {"id": "live", "type": "agentMessage", "text": "完整最终内容，原生确认一次。"}
        deliver([event("item/completed", item=final),
                 event("item/completed", item={"id": "late", "type": "agentMessage", "text": "在途事件保留"}),
                 event("item/agentMessage/delta", itemId="live", delta="迟到增量不能重复追加"),
                 event("turn/completed", turn={"id": "live_turn", "status": "completed"})])
        self.assertEqual(transcript.card("live").item["text"], final["text"])
        self.assertFalse(panel.history_refresh.isActive())
        self.assertEqual(read_count() - before, 1)
        QtTest.QTest.qWait(80)
        self.assertEqual(anchor.mapTo(transcript.viewport(), QtCore.QPoint()).y(), anchor_y)


if __name__ == "__main__":
    unittest.main()
