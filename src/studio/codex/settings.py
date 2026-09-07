"""Native model catalog and small thread/turn settings projections."""
from __future__ import annotations

import copy
import threading
import time

from ..common import StudioError


class ModelCatalog:
    def __init__(self, client, account_revision):
        self.client, self.account_revision = client, account_revision
        self.lock, self.fetch_lock = threading.Lock(), threading.Lock()
        self.revision = self.generation = 0
        self.cached = None
        self.cached_at = 0.0

    def invalidate(self):
        with self.lock:
            self.generation += 1
            self.cached = None

    def read(self):
        with self.fetch_lock:
            account_revision = self.account_revision()
            with self.lock:
                generation = self.generation
                if (self.cached and self.cached["account_revision"] == account_revision and
                        time.monotonic() - self.cached_at < 60):
                    return copy.deepcopy(self.cached)
            models, seen, cursors, cursor = [], set(), set(), None
            for _ in range(8):
                params = {"limit": 64, "includeHidden": False}
                if cursor:
                    params["cursor"] = cursor
                page = self.client.request("model/list", params)
                if not isinstance(page, dict) or not isinstance(page.get("data"), list):
                    raise StudioError("MODEL_CATALOG_INVALID", "原生模型列表不完整，请重新查询。", 502)
                for item in page["data"]:
                    if not isinstance(item, dict) or not isinstance(item.get("model"), str):
                        raise StudioError("MODEL_CATALOG_INVALID", "原生模型标识不完整，请重新查询。", 502)
                    if not item.get("hidden", False) and item["model"] not in seen:
                        seen.add(item["model"])
                        models.append(copy.deepcopy(item))
                    if len(models) > 512:
                        raise StudioError("MODEL_CATALOG_INCOMPLETE", "模型列表超出本次读取范围，请重新查询。", 502)
                cursor = page.get("nextCursor")
                if cursor is None:
                    break
                if not isinstance(cursor, str) or not cursor or cursor in cursors:
                    raise StudioError("MODEL_CATALOG_INCOMPLETE", "原生模型分页尚未完整，保留当前选择并重新查询。", 502)
                cursors.add(cursor)
            else:
                raise StudioError("MODEL_CATALOG_INCOMPLETE", "原生模型列表超出本次读取范围，请重新查询。", 502)
            with self.lock:
                if generation != self.generation or account_revision != self.account_revision():
                    raise StudioError("MODEL_CATALOG_CHANGED", "账号已变化，请重新查询可用模型。", 409)
                self.revision += 1
                self.cached = {"data": models, "nextCursor": None, "account_revision": account_revision,
                               "catalog_revision": self.revision}
                self.cached_at = time.monotonic()
                return copy.deepcopy(self.cached)

    def validate(self, model, effort, attachments=False):
        item = next((value for value in self.read()["data"] if value["model"] == model), None)
        if item is None:
            raise StudioError("MODEL_UNAVAILABLE", "所选模型已不可用，请重新选择模型。", 409)
        efforts = [value.get("reasoningEffort") for value in item.get("supportedReasoningEfforts", [])
                   if isinstance(value, dict)]
        if effort is not None and effort not in efforts:
            raise StudioError("EFFORT_UNAVAILABLE", "所选推理强度不适用于此模型，请使用其原生默认值或重新选择。", 409)
        if attachments and "image" not in item.get("inputModalities", ["text", "image"]):
            raise StudioError("MODEL_IMAGE_UNSUPPORTED", "此模型不接受图片，请保留草稿并选择支持图片的模型。", 409)


class NativeSettings:
    """Called under the Bridge lock; never treats a requested model as routing proof."""
    def __init__(self):
        self.revision = 0
        self.thread = {"thread_id": None, "revision": 0, "model": None, "effort": None, "source": "unknown"}
        self.turn = None
        self.pending_reroutes = {}

    def bind(self, thread_id, response):
        self.revision += 1
        model, effort = response.get("model"), response.get("reasoningEffort")
        self.thread = {"thread_id": thread_id, "revision": self.revision,
                       "model": model if isinstance(model, str) else None,
                       "effort": effort if isinstance(effort, str) else None,
                       "source": "native" if isinstance(model, str) else "unknown"}
        self.turn, self.pending_reroutes = None, {}

    def check_binding(self, body, thread_id):
        if "expected_thread_id" in body and body["expected_thread_id"] != thread_id:
            raise StudioError("THREAD_SELECTION_STALE", "当前对话已变化，草稿已保留，请确认后再发送。", 409)
        if "settings_revision" in body and (type(body["settings_revision"]) is not int or
                                            body["settings_revision"] != self.revision):
            raise StudioError("MODEL_SETTINGS_STALE", "当前对话的模型设置已变化，请确认后再发送。", 409)

    def requested(self, thread_id, body):
        model = body.get("model") or self.thread["model"]
        effort = body.get("effort") or (self.thread["effort"] if model == self.thread["model"] else None)
        self.turn = {"thread_id": thread_id, "turn_id": None, "requested_model": model,
                     "requested_effort": effort, "model": model, "effort": effort,
                     "confirmation": "requested", "from_model": None, "reason": None}
        self.pending_reroutes = {}

    def admitted(self, turn_id):
        if not self.turn or self.turn["turn_id"] not in {None, turn_id}:
            return
        self.turn["turn_id"] = turn_id
        pending = self.pending_reroutes.pop(turn_id, None)
        self.pending_reroutes.clear()
        if pending:
            self.rerouted(pending)

    def rerouted(self, params):
        if not self.turn or params.get("threadId") != self.turn["thread_id"]:
            return
        turn_id = params.get("turnId")
        if not turn_id or not isinstance(params.get("toModel"), str):
            return
        if self.turn["turn_id"] is None:
            if len(self.pending_reroutes) < 8:
                self.pending_reroutes[turn_id] = copy.deepcopy(params)
        elif turn_id == self.turn["turn_id"]:
            self.turn.update(model=params["toModel"], confirmation="rerouted",
                             from_model=params.get("fromModel"), reason=params.get("reason"))

    def snapshot(self):
        return {"thread_settings": copy.deepcopy(self.thread), "turn_settings": copy.deepcopy(self.turn)}
