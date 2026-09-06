"""Revocable, in-memory consent for single native Studio tool approvals.

0.153.4 emits item/started before its privileged mcp_tool_call elicitation.
That elicitation has no call ID: require one matching in-flight item, the
native fallback question, and exact arguments. Ambiguity stays user-driven.
This does not classify or sandbox Python/HOM side effects.
"""
from __future__ import annotations

import json


STUDIO_SERVER = "big_chicken"
STUDIO_TOOLS = (
    "hia_context", "hia_inspect", "hia_lookup", "hia_execute_hom", "hia_capture",
    "hia_operation", "hia_project_memory",
)
_MAX_INFLIGHT_CALLS = 32
_APPROVAL_META = frozenset({
    "codex_approval_kind", "tool_name", "tool_title", "tool_description",
    "tool_params", "tool_params_display",
})


def _arguments(value):
    if not isinstance(value, dict):
        return None
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    # Redaction loses payload identity. Never infer equivalence from masked data.
    return None if "[REDACTED]" in encoded else encoded


class SessionTrust:
    def __init__(self):
        self.enabled = False
        self.revision = 0
        self.calls = {}

    def reset(self):
        self.enabled = False
        self.revision += 1
        self.calls = {}

    def change(self, enabled):
        self.enabled = enabled
        self.revision += 1

    def observe(self, method, params, turn_id):
        if method in {"turn/started", "turn/completed"}:
            self.calls = {}
        if params.get("turnId") != turn_id or not turn_id:
            return
        item = params.get("item", {})
        if item.get("type") != "mcpToolCall" or not isinstance(item.get("id"), str):
            return
        if self.calls is None:
            return  # Overflow disables correlation until the next turn boundary.
        if method == "item/completed":
            self.calls.pop(item["id"], None)
        elif method == "item/started" and item["id"] not in self.calls:
            if len(self.calls) >= _MAX_INFLIGHT_CALLS:
                self.calls = None
            else:
                self.calls[item["id"]] = {"item": item, "answered": False}

    def match(self, request, thread_id, turn_id):
        if (not thread_id or not turn_id or not self.calls or len(self.calls) != 1 or
                request.get("method") != "mcpServer/elicitation/request"):
            return None
        params = request.get("params", {})
        meta = params.get("_meta")
        if (params.get("threadId") != thread_id or params.get("turnId") != turn_id or
                params.get("serverName") != STUDIO_SERVER or params.get("mode") != "form" or
                params.get("requestedSchema") != {"type": "object", "properties": {}} or
                "url" in params or not isinstance(meta, dict) or
                meta.get("codex_approval_kind") != "mcp_tool_call" or set(meta) - _APPROVAL_META):
            return None
        call_id, call = next(iter(self.calls.items()))
        item = call["item"]
        tool = item.get("tool")
        if (call["answered"] or item.get("server") != STUDIO_SERVER or tool not in STUDIO_TOOLS or
                item.get("status") != "inProgress" or
                meta.get("tool_name", tool) != tool or
                params.get("message") != f'Allow the {STUDIO_SERVER} MCP server to run tool "{tool}"?'):
            return None
        arguments = _arguments(item.get("arguments"))
        if arguments is None or arguments != _arguments(meta.get("tool_params")):
            return None
        return call_id

    def consume(self, call_id):
        if self.calls and call_id in self.calls:
            self.calls[call_id]["answered"] = True
