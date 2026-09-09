"""Bounded pages from the pinned native store, with connection-local fallback."""
import json

from .codex.errors import BridgeError
from .common import StudioError, new_id


class NativeHistory:
    def __init__(self, bridge):
        self.bridge = bridge
        self.reset()

    def reset(self):
        self.generation = new_id()
        self.unsupported = set()

    @staticmethod
    def unsupported_error(error):
        rpc = (error.details or {}).get("rpc_error", {})
        return (error.code == "CODEX_RPC_ERROR" and
                (rpc.get("code") == -32601 or any(text in error.message.lower() for text in
                 ("list_turns is not supported", "list_items is not supported", "unsupported method"))))

    def page(self, thread_id, *, cursor=None, turn_id=None):
        bridge = self.bridge
        generation = self.generation
        if thread_id != bridge.thread_id or thread_id in bridge.conversations.deleted:
            raise StudioError("HISTORY_SCOPE_CHANGED", "当前对话已变化，请读取所选对话。", 409)
        method = "thread/items/list" if turn_id else "thread/turns/list"
        terminal_at_start = turn_id in getattr(bridge, "completed_turns", ()) if turn_id else False
        limit = 50 if turn_id else 8
        params = {"threadId": thread_id, "limit": limit, "sortDirection": "desc"}
        if turn_id:
            params["turnId"] = turn_id
        else:
            params["itemsView"] = "full"
        if cursor:
            params["cursor"] = cursor
        try:
            if method in self.unsupported:
                value = self.fallback(thread_id, turn_id, cursor, limit)
            else:
                page = bridge.client.request(method, params)
                if turn_id:
                    entries = page.get("data", [])
                    if any(entry.get("turnId") != turn_id for entry in entries):
                        raise StudioError("HISTORY_SCOPE_CHANGED", "Native item page returned another turn", 409)
                    turns = [{"id": turn_id, "itemsView": "full", "history_turn_terminal": terminal_at_start,
                              "items": [entry["item"] for entry in reversed(entries)]}]
                else:
                    turns = list(reversed(page.get("data", [])))
                value = {"thread": {"id": thread_id, "turns": turns},
                         "next_cursor": page.get("nextCursor"), "history_available": True,
                         "history_source": method, "turn_id": turn_id}
        except BridgeError as error:
            if not self.unsupported_error(error):
                raise
            if generation == self.generation:
                self.unsupported.add(method)
            value = self.fallback(thread_id, turn_id, cursor, limit)
        if (generation != self.generation or thread_id != bridge.thread_id
                or thread_id in bridge.conversations.deleted):
            raise StudioError("HISTORY_SCOPE_CHANGED", "连接或对话已变化，忽略旧历史读取。", 409)
        return {**value, "connection_generation": generation}

    def fallback(self, thread_id, turn_id, cursor, limit):
        anchor = None
        if cursor:
            try:
                parsed = json.loads(cursor)
                if parsed["fallback_thread"] != thread_id or parsed["turn"] != turn_id:
                    raise ValueError
                anchor = parsed["before"]
                if not isinstance(anchor, str):
                    raise ValueError
            except (ValueError, TypeError, KeyError):
                raise StudioError("HISTORY_CURSOR_CHANGED", "历史分页来源已变化，请刷新连接。", 409) from None
        value = self.bridge.read_thread(thread_id)
        thread = value.get("thread") or {}
        if thread.get("id") != thread_id:
            raise StudioError("HISTORY_SCOPE_CHANGED", "Native history returned another thread", 409)
        if value.get("history_available") is False:
            return {**value, "next_cursor": None, "history_source": "metadata", "turn_id": turn_id}
        if turn_id:
            turn = next((turn for turn in thread.get("turns", []) if turn.get("id") == turn_id), None)
            entries = list(reversed((turn or {}).get("items", [])))
        else:
            entries = list(reversed(thread.get("turns", [])))
        offset = 0
        if anchor:
            offset = next((i + 1 for i, entry in enumerate(entries) if entry.get("id") == anchor), None)
            if offset is None:
                raise StudioError("HISTORY_CURSOR_CHANGED", "历史分页边界已变化，请刷新连接。", 409)
        if turn_id:
            turns = [{**turn, "items": list(reversed(entries[offset:offset + limit]))}] if turn else []
        else:
            turns = list(reversed(entries[offset:offset + limit]))
        next_cursor = (json.dumps({"fallback_thread": thread_id, "turn": turn_id, "before": entries[offset + limit - 1]["id"]})
                       if offset + limit < len(entries) else None)
        return {"thread": {"id": thread_id, "turns": turns}, "history_available": True,
                "next_cursor": next_cursor, "history_source": "thread/read fallback", "turn_id": turn_id}
