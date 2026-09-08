"""Evidence counts native calls once and keeps quality judgments unverified."""
import unittest
import json

from scripts.tc1_evidence import summarize


class EvidenceTests(unittest.TestCase):
    def test_feedback_is_counted_from_original_receipts_not_repeated_gets(self):
        items = [{"id": str(i), "type": "mcpToolCall", "tool": tool,
                  "result": {"content": [{"type": "text", "text": json.dumps({"operation_id": op})}]}}
                 for i, (tool, op) in enumerate((("hia_execute_hom", "edit"),
                     ("hia_operation", "edit"), ("hia_capture", "image"), ("hia_operation", "image")))]
        receipts = [{"operation_id": "edit", "kind": "execute", "result": {"observe_after": {
            "mode": "passive_after_failure", "status": "partial", "counts": {"ok": 2, "skipped": 2}}}},
            {"operation_id": "image", "kind": "capture", "state": "failed", "result": {
                "actual_frame": 72, "restored_frame": 1, "capture_error": None,
                "restore_errors": [{"phase": "default_view"}]}}]
        turn = summarize({"turns": [{"items": items}]}, receipts)["turns"][0]
        self.assertEqual(len(turn["execution_feedback"]), 1)
        self.assertEqual(turn["execution_feedback"][0]["counts"], {"ok": 2, "skipped": 2})
        self.assertEqual(len(turn["captures"]), 1)
        self.assertEqual(turn["captures"][0]["actual_frame"], 72)
        self.assertEqual(turn["captures"][0]["state"], "failed")
        self.assertIsNone(turn["manual_classifications"]["viewport_only_execute_calls"])

    def test_internal_polls_do_not_count_and_empty_search_is_not_a_guess_error(self):
        search = {"id": "search", "type": "mcpToolCall", "tool": "hia_lookup", "status": "completed",
                  "arguments": {"source": "metadata", "requests": [
                      {"kind": "search", "category": "Sop", "query": "none"}, {"kind": "categories"}]},
                  "result": {"content": [{"type": "text", "text": '{"operation_id":"read","result":{"types":[]}}'}]}}
        native = {"thread": {"id": "thread", "turns": [{"id": "turn", "items": [search, search,
            {"id": "inspect", "type": "mcpToolCall", "tool": "hia_inspect", "status": "completed",
             "arguments": {"views": [{"view": "node"}, {"view": "parameters"}]}}]}]}}
        result = summarize(native, [{"operation_id": "read", "timings": {"queue_seconds": 0.05}},
                                    {"operation_id": "tester_owned", "kind": "execute"}])
        turn = result["turns"][0]
        self.assertEqual(turn["total_tool_calls"], 2)
        self.assertEqual(turn["metadata_requests"], {"search": 1, "categories": 1})
        self.assertEqual(turn["inspect_views"], {"node": 1, "parameters": 1})
        self.assertEqual(len(turn["receipt_timings"]), 1)
        self.assertEqual(turn["failures_for_manual_review"], [])
        self.assertIsNone(result["api_guess_failures"])


if __name__ == "__main__":
    unittest.main()
