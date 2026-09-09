"""Ephemeral native item projection; no chat persistence or inferred completion."""
from dataclasses import dataclass


@dataclass(frozen=True)
class ItemKey:
    generation: int
    thread: str
    turn: str
    item: str


@dataclass
class ProjectedItem:
    item: dict
    terminal: bool = False
    native_terminal: bool = False
    continuous: bool = False
    recovering: bool = False


class MessageProjection:
    def __init__(self):
        self.generation = 0
        self.thread_id = None
        self.records = {}
        self.turns = []
        self.item_order = {}
        self.closed_turns = set()
        self.gaps = set()
        self.sequence = 0
        self.history_revision = -1

    def bind(self, thread_id, generation):
        previous = self.records if thread_id == self.thread_id else {}
        if thread_id != self.thread_id:
            self.turns, self.item_order = [], {}
            self.closed_turns, self.gaps = set(), set()
        self.thread_id, self.generation = thread_id, generation
        self.records = {}
        for key, record in previous.items():
            record.continuous = False
            record.recovering = not record.terminal
            self.records[ItemKey(generation, thread_id, key.turn, key.item)] = record
        self.sequence, self.history_revision = 0, -1

    def key(self, turn_id, item_id):
        return ItemKey(self.generation, self.thread_id, turn_id, item_id)

    def ordered_keys(self):
        return [self.key(turn, item) for turn in self.turns for item in self.item_order.get(turn, [])]

    def remember(self, key):
        if key.turn not in self.turns:
            self.turns.append(key.turn)
        order = self.item_order.setdefault(key.turn, [])
        if key.item not in order:
            order.append(key.item)

    def recovering_turns(self):
        return self.gaps | {key.turn for key, record in self.records.items() if record.recovering}

    def mark_gap(self, turn_id=None):
        if turn_id:
            self.gaps.add(turn_id)
        for key, record in self.records.items():
            if not record.terminal and (turn_id is None or key.turn == turn_id):
                record.continuous = False
                record.recovering = True

    def event(self, event, generation):
        if generation != self.generation:
            return set()
        params, method = event.get("params", {}), event.get("method", "")
        if params.get("threadId") != self.thread_id:
            return set()
        sequence = event.get("sequence")
        if isinstance(sequence, int):
            if sequence <= self.sequence:
                return set()
            self.sequence = sequence
        turn = params.get("turnId") or (params.get("turn") or {}).get("id")
        if not turn:
            return set()
        if turn not in self.turns:
            self.turns.append(turn)
        if method == "turn/completed":
            self.closed_turns.add(turn)
            changed = set()
            for key, record in self.records.items():
                if key.turn == turn and not record.terminal:
                    record.recovering = True
                    record.continuous = False
                    changed.add(key)
            return changed
        item = params.get("item") or {}
        item_id = item.get("id") or params.get("itemId")
        if not item_id:
            return set()
        key = self.key(turn, item_id)
        record = self.records.get(key)
        if method == "item/completed":
            self.records[key] = ProjectedItem(dict(item), terminal=True, native_terminal=True)
        elif method == "item/started":
            if record is not None:
                return set()  # A repeated start cannot reset or align an existing stream.
            continuous = turn not in self.closed_turns and turn not in self.gaps
            self.records[key] = ProjectedItem(dict(item), terminal=item.get("type") == "userMessage",
                                               continuous=continuous, recovering=not continuous)
        elif method in {"item/agentMessage/delta", "item/plan/delta", "item/reasoning/summaryTextDelta"}:
            if record is None:
                kind = "reasoning" if "reasoning" in method else "plan" if "/plan/" in method else "agentMessage"
                record = self.records[key] = ProjectedItem({"id": item_id, "type": kind, "text": ""}, recovering=True)
            if record.terminal:
                return set()
            if record.continuous:
                value = dict(record.item)
                if method == "item/reasoning/summaryTextDelta":
                    summary = list(value.get("summary", []))
                    index = min(100, max(0, params.get("summaryIndex", 0)))
                    while len(summary) <= index:
                        summary.append("")
                    summary[index] += params.get("delta", "")
                    value["summary"] = summary
                else:
                    value["text"] = value.get("text", "") + params.get("delta", "")
                record.item = value
            else:
                record.recovering = True  # Unknown prefix/boundary: never guess an append.
        else:
            return set()
        self.remember(key)
        return {key}

    @staticmethod
    def merge_order(existing, incoming, default_index=0):
        """Insert loaded history before its known anchor; absence never deletes."""
        pending = []
        for value in incoming:
            if value in existing:
                index = existing.index(value)
                existing[index:index] = pending
                pending = []
            elif value not in pending:
                pending.append(value)
        if pending:
            known = [value for value in incoming if value in existing]
            index = existing.index(known[-1]) + 1 if known else default_index
            existing[index:index] = pending

    def history(self, thread, generation, revision, *, older=False):
        if (generation != self.generation or thread.get("id") != self.thread_id
                or revision < self.history_revision):
            return set()
        self.history_revision = revision
        turns = thread.get("turns", [])
        position = 0 if older else next((i for i, turn in enumerate(self.turns) if turn not in self.closed_turns), len(self.turns))
        self.merge_order(self.turns, [turn["id"] for turn in turns if turn.get("id")], position)
        changed = set()
        for turn in turns:
            turn_id = turn.get("id")
            if not turn_id:
                continue
            # Pinned thread/read with includeTurns returns full items. Paginated
            # responses carry itemsView explicitly; summary/notLoaded are not bodies.
            view = turn.get("itemsView", "full")
            if view != "full":
                continue
            complete = (turn.get("status") in {"completed", "interrupted", "failed"}
                        or turn.get("history_turn_terminal") is True)
            if complete:
                self.closed_turns.add(turn_id)
            self.gaps.discard(turn_id)
            items = [item for item in turn.get("items", []) if item.get("id")]
            self.merge_order(self.item_order.setdefault(turn_id, []), [item["id"] for item in items])
            for item in items:
                key = self.key(turn_id, item["id"])
                record = self.records.get(key)
                terminal = complete or item.get("status") in {"completed", "failed", "declined"}
                if record and (record.native_terminal or record.terminal or record.continuous and not terminal):
                    continue
                self.records[key] = ProjectedItem(dict(item), terminal=terminal, recovering=not terminal)
                changed.add(key)
        return changed
