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
        panel = StudioPanel(paths=AppPaths(root), api=api, auto_poll=False)
        self.addCleanup(panel.deleteLater)
        self.addCleanup(panel.close)
        panel.show()
        process_until(lambda: len(panel.transcript.cards) == len(history) and not panel.hydrating)
        image_card = panel.transcript.cards["image_item"]
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
            return sum(method == "GET" and path == "/thread" for method, path, _body in api.calls)

        deliver([event("item/started", item={"id": "live", "type": "agentMessage", "text": ""}),
                 event("item/agentMessage/delta", itemId="live", delta="即时前缀")])
        self.assertEqual(panel.transcript.cards["live"].item["text"], "即时前缀")
        native = copy.deepcopy(api.thread)
        native["turns"][-1]["items"] = [{"id": "live", "type": "agentMessage", "text": "即时前缀·快照重叠"}]
        QtTest.QTest.qWait(30)
        transcript = panel.transcript
        anchor = transcript.cards["history_30"]
        transcript.verticalScrollBar().setValue(anchor.y() + 9)
        anchor_y = anchor.mapTo(transcript.viewport(), QtCore.QPoint()).y()
        original_cards = dict(transcript.cards)
        image_key = tile.picture.pixmap().cacheKey()
        document = transcript.cards["history_10"].text.document()
        image_card.toggle_details()
        QtTest.QTest.qWait(20)
        # Opening details above the anchor is outside history synchronization;
        # record the user's current reading position after that layout settles.
        transcript.verticalScrollBar().setValue(anchor.y() + 9)
        anchor_y = anchor.mapTo(transcript.viewport(), QtCore.QPoint()).y()
        before = read_count()
        api.hold["/thread"] = []
        events_path = "/events?after=" + str(panel.cursor)
        api.hold[events_path] = []
        panel.refresh()
        in_flight = api.hold[events_path].pop()[0]
        panel.load_history()
        loaded = api.hold["/thread"].pop()[0]
        buffered = [event("item/agentMessage/delta", itemId="live", delta="·快照重叠"),
                    event("item/started", item={"id": "late", "type": "agentMessage", "text": ""}),
                    event("item/agentMessage/delta", itemId="late", delta="在途事件保留")]
        in_flight({"cursor": sequence, "events": buffered})
        self.assertEqual(len(panel.history_events), 3)
        native["turns"][0]["items"][4]["text"] += "\n\n" + "回填修正的上方内容。" * 80
        loaded({"thread": native})
        QtTest.QTest.qWait(30)
        self.assertEqual(transcript.cards["live"].item["text"], "即时前缀·快照重叠")
        self.assertEqual(transcript.cards["late"].item["text"], "在途事件保留")
        self.assertEqual(anchor.mapTo(transcript.viewport(), QtCore.QPoint()).y(), anchor_y)
        for item_id, card in original_cards.items():
            self.assertIs(transcript.cards[item_id], card)
        self.assertIs(image_card.images.itemAt(0).widget(), tile)
        self.assertEqual(tile.picture.pixmap().cacheKey(), image_key)
        self.assertIs(transcript.cards["history_10"].text.document(), document)
        self.assertTrue(image_card.details.isVisible())
        self.assertTrue(transcript.cards["live"].sync_note.isVisible())
        self.assertTrue(panel.history_refresh.isActive())

        # Advance the one scheduled repair without waiting a wall-clock interval.
        panel.history_refresh.stop()
        panel.history_refresh.timeout.emit()
        repaired = api.hold["/thread"].pop()[0]
        native["turns"][-1]["items"] = [
            {"id": "live", "type": "agentMessage", "text": "即时前缀·快照重叠·补读"},
            {"id": "late", "type": "agentMessage", "text": "在途事件保留"}]
        # A tool item larger than the transient buffer must still be recovered at
        # the turn boundary, even after the one automatic repair is spent.
        oversized = {"id": "oversized_tool", "type": "mcpToolCall", "tool": "inspect", "status": "completed",
                     "result": {"content": [{"type": "text", "text": "bounded evidence\n" * 34000}]}}
        deliver([event("item/completed", item=oversized)])
        self.assertLessEqual(panel.history_event_bytes, 512 * 1024)
        repaired({"thread": native})
        self.assertFalse(panel.history_refresh.isActive())
        for _ in range(8):
            deliver([event("item/agentMessage/delta", itemId="live", delta="·流式后续") for _ in range(35)])
            app.processEvents()
        self.assertEqual(read_count() - before, 2)
        self.assertFalse(panel.history_refresh.isActive())
        self.assertEqual(transcript.cards["live"].item["text"], "即时前缀·快照重叠·补读")
        deliver([event("item/started", item={"id": "normal", "type": "agentMessage", "text": ""}),
                 event("item/agentMessage/delta", itemId="normal", delta="新消息仍即时显示")])
        self.assertEqual(transcript.cards["normal"].item["text"], "新消息仍即时显示")

        final = {"id": "live", "type": "agentMessage", "text": "完整最终内容，原生确认一次。"}
        deliver([event("item/completed", item=final),
                 event("item/agentMessage/delta", itemId="live", delta="迟到增量不能重复追加")])
        self.assertEqual(transcript.cards["live"].item["text"], final["text"])
        self.assertTrue(transcript.cards["live"].sync_note.isHidden())
        # A stale active snapshot must not downgrade an item already completed.
        transcript.hydrate(native)
        self.assertEqual(transcript.cards["live"].item["text"], final["text"])
        native["turns"][-1]["status"] = "completed"
        native["turns"][-1]["items"] = [final, native["turns"][-1]["items"][1], oversized,
                                         {"id": "normal", "type": "agentMessage", "text": "新消息仍即时显示"}]
        deliver([event("turn/completed", turn={"id": "live_turn", "status": "completed"})])
        self.assertTrue(panel.history_refresh.isActive())
        panel.history_refresh.stop()
        panel.history_refresh.timeout.emit()
        api.hold["/thread"].pop()[0]({"thread": native})
        QtTest.QTest.qWait(30)
        self.assertEqual(read_count() - before, 3)  # Explicit read + one repair + terminal read.
        self.assertFalse(panel.history_refresh.isActive())
        self.assertEqual(transcript.cards["oversized_tool"].item, oversized)
        self.assertIs(image_card.images.itemAt(0).widget(), tile)
        self.assertEqual(tile.picture.pixmap().cacheKey(), image_key)
        self.assertEqual(anchor.mapTo(transcript.viewport(), QtCore.QPoint()).y(), anchor_y)
        self.assertFalse(transcript.cards["live"].sync_note.isVisible())


if __name__ == "__main__":
    unittest.main()
