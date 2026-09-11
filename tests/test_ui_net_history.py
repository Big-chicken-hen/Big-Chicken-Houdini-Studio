"""Bounded history transport recovery and stale-delivery checks; no native model."""
import copy
import os
import unittest
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6 import QtCore, QtTest, QtWidgets  # noqa: E402

from scripts.preview_ui import PreviewApi, configure_preview_fonts, process_until  # noqa: E402
from studio.common import AppPaths  # noqa: E402
from studio.ui.panel import StudioPanel  # noqa: E402


class PanelNetworkHistoryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        configure_preview_fonts(cls.app)
        cls.root = Path(__file__).resolve().parents[1]
        cls.evidence = cls.root / ".runtime" / "ui-net-history-tests"
        cls.evidence.mkdir(parents=True, exist_ok=True)

    def setUp(self):
        self.api = PreviewApi(self.evidence)
        self.panel = StudioPanel(api=self.api, auto_poll=False, image_roots=(self.evidence,),
                                 paths=AppPaths(self.root, data_root=self.evidence / "state",
                                                cache_root=self.evidence / "cache"))
        self.panel.show()
        process_until(lambda: len(self.panel.transcript.cards) == 3 and not self.panel.hydrating)
        self.api.hold["/thread/history"] = []

    def tearDown(self):
        self.panel.close()
        self.api.close()
        self.panel.deleteLater()
        self.app.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
        self.app.processEvents()

    def history_calls(self):
        return [call for call in self.api.calls if call[1].startswith("/thread/history?")]

    def history_reply(self):
        return self.api.hold["/thread/history"].pop(0)

    def canonical(self):
        return {key: copy.deepcopy(card.item) for key, card in self.panel.transcript.cards.items()}

    def test_failed_refresh_keeps_canonical_and_draft_with_only_one_automatic_read(self):
        original = self.canonical()
        self.panel.input.setPlainText("保留正在编辑的草稿")
        before = len(self.history_calls())
        writes = [call for call in self.api.calls if call[0] != "GET"]
        self.panel.load_history()
        loaded, failed, _ = self.history_reply()
        loaded({})  # HTTP success alone does not prove an empty native Thread.
        self.assertEqual(self.canonical(), original)
        self.assertTrue(self.panel.transcript.history_known)
        self.assertIn("历史读取失败", self.panel.notice.text())
        process_until(lambda: len(self.api.hold["/thread/history"]) == 1)
        _retry_loaded, retry_failed, _ = self.history_reply()
        retry_failed("reply unavailable")
        failed("duplicate completion")
        loaded({"thread": {"id": self.panel.thread_id, "turns": []}})
        for number in range(5):
            self.panel.schedule_history(turn_id="gap_" + str(number), terminal=True)
        QtTest.QTest.qWait(300)
        self.assertEqual(len(self.history_calls()) - before, 2)
        self.assertEqual(self.canonical(), original)
        self.assertEqual(self.panel.input.toPlainText(), "保留正在编辑的草稿")
        self.assertIn("刷新连接重试", self.panel.notice.text())
        self.assertFalse(self.panel.hydrating)
        self.assertFalse(self.panel.history_retry.isActive())
        self.assertEqual([call for call in self.api.calls if call[0] != "GET"], writes)

        # The existing explicit refresh action can initiate another read.
        self.panel.refresh_button.click()
        process_until(lambda: len(self.api.hold["/thread/history"]) == 1)
        self.history_reply()[0]({"thread": copy.deepcopy(self.api.thread)})
        self.assertFalse(self.panel.hydrating)
        self.assertFalse(self.panel.history_retry_exhausted)
        self.assertEqual(self.panel.input.toPlainText(), "保留正在编辑的草稿")

    def test_first_failure_is_not_empty_history_and_recovery_accepts_valid_empty_thread(self):
        for malformed in (
                {"thread": {"id": self.panel.thread_id, "turns": None}},
                {"thread": {"id": self.panel.thread_id, "turns": []}, "history_available": True,
                 "error": {"code": "HISTORY_UNAVAILABLE", "message": "not a successful empty Thread"}}):
            with self.subTest(payload=malformed):
                self.panel.transcript.reset(self.panel.thread_id, generation=self.panel.connection_generation)
                self.panel.load_history()
                self.history_reply()[0](malformed)
                self.assertEqual(self.panel.transcript.cards, {})
                self.assertFalse(self.panel.transcript.history_known)
                self.assertIn("历史读取失败", self.panel.notice.text())
                process_until(lambda: len(self.api.hold["/thread/history"]) == 1)
                self.history_reply()[0]({"thread": {"id": self.panel.thread_id, "turns": []},
                                         "history_available": True, "error": None})
                self.assertEqual(self.panel.transcript.cards, {})
                self.assertTrue(self.panel.transcript.history_known)
                self.assertFalse(self.panel.hydrating)
                self.assertEqual(self.panel.notice.text(), "")

    def test_unmaterialized_thread_is_metadata_and_bad_pages_do_not_change_cursor(self):
        original = self.canonical()
        self.panel.load_history()
        self.history_reply()[0]({"thread": {"id": self.panel.thread_id}, "history_available": False,
                                 "history_message": "尚未物化"})
        self.assertEqual(self.canonical(), original)
        self.assertFalse(self.panel.history_retry.isActive())
        self.panel.history_cursor = "native-before-item"
        self.panel.load_history(older=True)
        loaded, _failed, _ = self.history_reply()
        loaded({"thread": {"id": self.panel.thread_id, "turns": [{"id": "bad", "items": None}]},
                "next_cursor": "do-not-adopt"})
        self.assertEqual(self.panel.history_cursor, "native-before-item")
        self.assertEqual(self.canonical(), original)
        process_until(lambda: len(self.api.hold["/thread/history"]) == 1)
        self.assertIn("cursor=native-before-item", self.history_calls()[-1][1])
        self.history_reply()[0]({"thread": {"id": self.panel.thread_id, "turns": []},
                                 "next_cursor": None})
        self.assertIsNone(self.panel.history_cursor)
        self.assertEqual(self.canonical(), original)

    def test_old_generation_and_a_b_a_callbacks_cannot_change_current_notice_or_history(self):
        self.api.hold["/events"] = []
        accepted = []
        self.panel.call("GET", "/events?after=0", done=accepted.append)
        old_events_done, old_events_failed, _ = self.api.hold["/events"].pop()
        self.panel.advance_connection()
        self.panel.show_notice("当前连接提示")
        old_events_done({"events": [], "cursor": 0})
        old_events_failed("old connection failed")
        self.assertEqual(accepted, [])
        self.assertEqual(self.panel.notice.text(), "当前连接提示")

        thread_a = self.panel.thread_id
        self.panel.load_history()
        a_loaded, a_failed, _ = self.history_reply()
        self.panel.thread_id = "thread_b"
        self.panel.load_history()
        b_loaded, b_failed, _ = self.history_reply()
        self.panel.thread_id = thread_a
        self.panel.load_history()
        current_loaded, _current_failed, _ = self.history_reply()
        for loaded, failed, thread in ((a_loaded, a_failed, thread_a), (b_loaded, b_failed, "thread_b")):
            loaded({"thread": {"id": thread, "turns": []}})
            failed("retired history")
        self.assertTrue(self.panel.hydrating)
        self.assertFalse(self.panel.history_retry.isActive())
        self.assertEqual(self.panel.notice.text(), "当前连接提示")
        current_loaded({"thread": copy.deepcopy(self.api.thread)})
        self.assertFalse(self.panel.hydrating)
        self.assertEqual(len(self.panel.transcript.cards), 3)

    def test_retirement_cancels_scheduled_recovery_without_draft_or_message_changes(self):
        original = self.canonical()
        self.panel.input.setPlainText("不会因历史恢复而丢失")
        for retired in ("archived", "deleted", "closed"):
            with self.subTest(retired=retired):
                self.panel.invalidate_history()
                self.panel.load_history()
                loaded, failed, _ = self.history_reply()
                failed("network failure")
                calls = len(self.history_calls())
                if retired == "closed":
                    self.panel.close()
                else:
                    getattr(self.panel, retired + "_threads").add(self.panel.thread_id)
                QtTest.QTest.qWait(300)
                loaded({"thread": {"id": self.panel.thread_id, "turns": []}})
                failed("late network failure")
                self.assertEqual(len(self.history_calls()), calls)
                self.assertEqual(self.canonical(), original)
                self.assertEqual(self.panel.input.toPlainText(), "不会因历史恢复而丢失")
                if retired != "closed":
                    getattr(self.panel, retired + "_threads").discard(self.panel.thread_id)


if __name__ == "__main__":
    unittest.main()
