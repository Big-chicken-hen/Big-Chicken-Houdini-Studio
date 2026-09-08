"""Evidence counts native calls once and keeps quality judgments unverified."""
import unittest

from scripts.tc1_evidence import summarize


class EvidenceTests(unittest.TestCase):
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
