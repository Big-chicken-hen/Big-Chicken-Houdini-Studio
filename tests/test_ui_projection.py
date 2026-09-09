"""Canonical native content under reordered delivery; no model or Houdini claims."""
import os
from pathlib import Path
import unittest

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6 import QtCore, QtGui, QtTest, QtWidgets  # noqa: E402

from scripts.preview_ui import configure_preview_fonts  # noqa: E402
from studio.ui.conversation import Transcript  # noqa: E402


class ProjectionRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        configure_preview_fonts(cls.app)

    def setUp(self):
        self.view = Transcript(Path(__file__).resolve().parents[1] / ".runtime")
        self.view.resize(430, 600)
        self.view.reset("a")
        self.view.show()
        self.sequence = 0

    def tearDown(self):
        self.view.close()
        self.view.deleteLater()
        self.app.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)

    def event(self, method, *, turn="one", thread="a", item=None, **params):
        self.sequence += 1
        self.view.apply_event({"sequence": self.sequence, "method": method,
            "params": {"threadId": thread, "turnId": turn, **({"item": item} if item else {}), **params}})

    def card(self, item_id="reply", turn="one"):
        return next(c for c in self.view.cards.values()
                    if c.item["id"] == item_id and c.property("nativeTurnId") == turn)

    @staticmethod
    def message(text, item_id="reply"):
        return {"id": item_id, "type": "agentMessage", "text": text}

    def history(self, text, *, status="inProgress", view="full"):
        return {"id": "a", "turns": [{"id": "one", "status": status,
            "itemsView": view, "items": [self.message(text)]}]}

    def test_late_summary_and_full_history_cannot_replace_native_terminal(self):
        final = "完整终态，保留末尾标记 END。"
        self.event("item/completed", item=self.message(final))
        self.view.hydrate(self.history("历史摘要", status="completed", view="summary"))
        self.assertEqual(self.card().item["text"], final)
        self.view.hydrate(self.history("较早的完整读取", status="completed"))
        self.assertEqual(self.card().item["text"], final)

    def test_contiguous_stream_survives_non_atomic_snapshot(self):
        self.event("item/started", item=self.message(""))
        self.event("item/agentMessage/delta", itemId="reply", delta="甲")
        self.view.hydrate(self.history("甲乙"))
        self.event("item/agentMessage/delta", itemId="reply", delta="乙")
        self.event("item/agentMessage/delta", itemId="reply", delta="丙")
        self.assertEqual(self.card().item["text"], "甲乙丙")

    def test_item_identity_includes_turn_and_rejects_other_thread(self):
        self.event("item/completed", item=self.message("第一轮"))
        self.event("item/started", turn="two", item=self.message(""))
        self.event("item/agentMessage/delta", turn="two", itemId="reply", delta="第二轮")
        self.assertEqual(len(self.view.cards), 2)
        self.assertEqual(self.card(turn="one").item["text"], "第一轮")
        self.assertEqual(self.card(turn="two").item["text"], "第二轮")
        self.event("item/completed", thread="b", item=self.message("其他对话"))
        self.assertEqual(self.card().item["text"], "第一轮")

    def test_long_message_uses_outer_scroll_and_keeps_selected_text(self):
        text = "# 长回复\n\n" + "中文内容与代码 `value = 1`。\n\n" * 180 + "末尾 END-180"
        self.event("item/started", item=self.message(text))
        QtTest.QTest.qWait(80)
        card = self.card()
        self.assertIn("END-180", card.text.toPlainText())
        self.assertGreater(card.text.height(), 1600)
        self.assertEqual(card.text.verticalScrollBarPolicy(), QtCore.Qt.ScrollBarAlwaysOff)
        cursor = card.text.textCursor()
        cursor.setPosition(5)
        cursor.setPosition(14, QtGui.QTextCursor.KeepAnchor)
        card.text.setTextCursor(cursor)
        selected = cursor.selectedText()
        self.event("item/agentMessage/delta", itemId="reply", delta="\n尾部继续")
        QtTest.QTest.qWait(80)
        self.assertEqual(card.text.textCursor().selectedText(), selected)
        self.assertTrue(card.item["text"].endswith("尾部继续"))

    def test_drawing_is_coalesced_but_source_and_terminal_are_immediate(self):
        self.event("item/started", item=self.message(""))
        card = self.card()
        initial = card.markdown_updates
        for _ in range(100):
            self.event("item/agentMessage/delta", itemId="reply", delta="中文")
        self.assertEqual(card.source_text(), "中文" * 100)
        self.assertEqual(card.markdown_updates, initial)
        QtTest.QTest.qWait(70)
        self.assertEqual(card.markdown_updates, initial + 1)
        self.event("item/agentMessage/delta", itemId="reply", delta="unfinished")
        self.event("item/completed", item=self.message("# 完整\n\n```python\nvalue = 1\n```\n\nEND"))
        self.assertFalse(card.render_timer.isActive())
        self.assertTrue(card.source_text().endswith("END"))
        self.assertTrue(card.text.toPlainText().endswith("END"))

    def test_old_connection_render_and_event_cannot_change_new_projection(self):
        self.event("item/started", item=self.message("可信前缀"))
        old = self.card()
        self.event("item/agentMessage/delta", itemId="reply", delta="，在途更新")
        generation = self.view.projection.generation
        self.view.bind("a", generation + 1)
        self.assertTrue(old.retired)
        self.assertFalse(old.render_timer.isActive())
        self.view.apply_event({"method": "item/completed", "params": {"threadId": "a", "turnId": "one",
            "item": self.message("旧连接终态")}}, generation=generation)
        old.render_item()
        self.assertEqual(self.card().source_text(), "可信前缀，在途更新")
        QtTest.QTest.qWait(10)
        self.assertTrue(self.card().sync_note.isVisible())


if __name__ == "__main__":
    unittest.main()
