"""Summarize exported native thread items and existing receipts; never run tools.

Input: the JSON returned by Bridge.read_thread, plus that workspace's receipt DB.
Use only dedicated TC-1/TC-2 review data. Keep raw exports local. Counts are external
model calls, not HTTP polls; error classification and visual quality need review.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import sqlite3


def summarize(native, receipts):
    thread = native.get("thread", native)
    result = {"thread_id": thread.get("id"), "turns": [],
              "api_guess_failures": None, "visual_quality": "awaiting_review",
              "first_useful_authoring_latency": "requires_turn_start_time_and_action_review"}
    for turn in thread.get("turns", []):
        calls, inspect_views, sources, metadata_kinds = Counter(), Counter(), Counter(), Counter()
        seen, problems, operation_ids = set(), [], set()
        for item in turn.get("items", []):
            if item.get("type") != "mcpToolCall" or item.get("id") in seen:
                continue
            seen.add(item["id"])
            tool = item.get("tool", "unknown")
            calls[tool] += 1
            args = item.get("arguments") or {}
            if tool == "hia_inspect":
                inspect_views.update(view.get("view", "node") for view in args.get("views", []))
            if tool == "hia_lookup":
                source = args.get("source", "metadata")
                sources[source] += 1
                if source == "metadata":
                    metadata_kinds.update(request.get("kind", "unknown") for request in args.get("requests", [
                        {"kind": "type" if "type_name" in args else "search"}]))
            payload = item.get("result") or {}
            item_errors = []
            if item.get("error") or item.get("status") == "failed" or payload.get("isError"):
                item_errors.append("native_tool_failure")
            for content in payload.get("content", []):
                if content.get("type") != "text":
                    continue
                try:
                    value = json.loads(content.get("text", ""))
                except (ValueError, TypeError):
                    continue
                if not isinstance(value, dict):
                    continue
                if value.get("operation_id"):
                    operation_ids.add(value["operation_id"])
                detail = value.get("result", value)
                if value.get("error"):
                    item_errors.append(value["error"].get("code", "unknown_error"))
                if isinstance(detail, dict) and detail.get("status") == "partial":
                    item_errors.append("partial_result")
            if item_errors:
                problems.append({"item_id": item["id"], "tool": tool, "signals": sorted(set(item_errors)),
                                 "classification": "awaiting_review"})
        related = [r for r in receipts if r["operation_id"] in operation_ids]
        feedback, captures = [], []
        for receipt in related:
            detail = receipt.get("result") or {}
            if receipt.get("kind") == "execute" and "observe_after" in detail:
                after = detail["observe_after"]
                feedback.append({"operation_id": receipt["operation_id"], "mode": after.get("mode"),
                                 "status": after.get("status"), "counts": after.get("counts", {})})
            if receipt.get("kind") == "capture":
                captures.append({"operation_id": receipt["operation_id"], "state": receipt.get("state"),
                    **{key: detail.get(key) for key in ("requested_target", "requested_view", "target",
                        "actual_frame", "restored_frame", "capture_error", "restore_errors")},
                    "restored_view": detail.get("view", {}).get("restored")})
        result["turns"].append({"turn_id": turn.get("id"), "status": turn.get("status"),
            "tool_calls": dict(calls), "total_tool_calls": sum(calls.values()),
            "inspect_views": dict(inspect_views), "lookup_calls_by_source": dict(sources),
            "metadata_requests": dict(metadata_kinds), "failures_for_manual_review": problems,
            "execution_feedback": feedback, "captures": captures,
            "manual_classifications": {"post_create_inspect_calls": None, "viewport_only_execute_calls": None,
                "api_guesses_and_repeated_calls": None, "partial_repair_method": None,
                "node_continuity_and_artist_edits": "awaiting_review"},
            "receipt_timings": [{key: r.get(key) for key in (
                "operation_id", "kind", "state", "mutation_outcome", "checks_outcome", "created_at", "timings")}
                for r in related]})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("thread_json", type=Path)
    parser.add_argument("receipt_db", type=Path)
    parser.add_argument("--stage", choices=("tc1", "tc2"), default="tc1")
    args = parser.parse_args()
    review = Path(__file__).resolve().parents[1] / ".runtime" / "reviews" / args.stage
    for path in (args.thread_json, args.receipt_db):
        if review not in path.resolve().parents:
            parser.error("Use this checkout's dedicated review inputs for the selected stage")
    native = json.loads(args.thread_json.read_text(encoding="utf-8"))
    with sqlite3.connect(args.receipt_db.resolve().as_uri() + "?mode=ro", uri=True) as db:
        receipts = [json.loads(row[0]) for row in db.execute("SELECT receipt FROM operations ORDER BY rowid")]
    print(json.dumps(summarize(native, receipts), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
