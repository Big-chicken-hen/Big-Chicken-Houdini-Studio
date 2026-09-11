"""Unresolved user inputs and compact connection-local identities, not chat history."""
from __future__ import annotations

import copy
import re

from .common import StudioError, atomic_json, payload_hash, read_json, encoded


class UserSubmissions:
    """All methods run under Bridge.lock. Only unresolved payloads reach disk."""
    def __init__(self, path):
        self.path = path
        self.records = {}
        self.last = {}
        self.fault = None
        if path.exists():
            try:
                if path.stat().st_size > 2 * 1024 * 1024:
                    raise ValueError("Pending input exceeds its storage bound")
                saved = read_json(path)
                if saved.get("format") != 1 or not isinstance(saved.get("pending"), list) or len(saved["pending"]) > 1:
                    raise ValueError("Pending input storage is invalid")
                for record in saved["pending"]:
                    if (not isinstance(record, dict) or not self.valid_id(record.get("client_user_message_id"))
                            or record.get("state") not in {"pending", "unknown"} or not record.get("thread_id")
                            or record.get("connection_generation") != record["client_user_message_id"].split(".")[0]
                            or record.get("intent") not in {"start", "steer"}
                            or not isinstance(record.get("snapshot"), dict)):
                        raise ValueError("Pending input identity is invalid")
                    record["state"] = "unknown"
                    if record.get("forward_attempted") is not True:
                        # A crash between preserving the snapshot and writing
                        # the frame cannot establish that no write took place.
                        record["forward_attempted"] = None
                    self.records[record["client_user_message_id"]] = record
                    self.last[record["thread_id"]] = record["client_user_message_id"]
            except (OSError, ValueError, TypeError, AttributeError, KeyError):
                self.fault = "未确认输入的保留记录无法读取；先保留原文件并核对状态。"

    @staticmethod
    def valid_id(value):
        return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{32}\.[0-9a-f]{32}", value) is not None

    def unresolved(self, thread_id=None):
        return [record for record in self.records.values() if record["state"] in {"pending", "unknown"}
                and (thread_id is None or record["thread_id"] == thread_id)]

    def reset_generation(self, generation):
        # Never discard unknown payloads on reconnect. Old IDs remain unusable
        # for sends because their generation is part of the immutable ID.
        self.records = {key: record for key, record in self.records.items()
                        if record["connection_generation"] == generation or record["state"] in {"pending", "unknown"}}
        self.last = {record["thread_id"]: key for key, record in self.records.items()}

    def remember(self, body, intent, account_identity):
        message_id, generation = body.get("client_user_message_id"), body.get("connection_generation")
        if not self.valid_id(message_id) or message_id.split(".")[0] != generation:
            raise StudioError("INPUT_ID_INVALID", "消息身份不完整；内容已保留，请重新确认连接。", 409,
                              submission_state="not_submitted")
        fingerprint = payload_hash({"intent": intent, "body": body})
        previous = self.records.get(message_id)
        if previous:
            if previous.get("fingerprint") != fingerprint:
                raise StudioError("INPUT_ID_CONFLICT", "此消息身份属于原发送；请查询原记录，不会再次发送。", 409,
                                  submission_state="not_submitted")
            return previous, False
        record = {"client_user_message_id": message_id, "intent": intent,
                  "connection_generation": generation, "account_revision": body.get("account_revision"),
                  "account_identity": account_identity, "thread_id": body.get("expected_thread_id"),
                  "expected_turn_id": body.get("expected_turn_id"), "turn_id": None,
                  "state": "not_submitted", "forward_attempted": False, "native_item_id": None,
                  "fingerprint": fingerprint}
        self.records[message_id] = record
        # A rejected competing click must not hide the active pending record.
        if not self.unresolved(record["thread_id"]):
            self.last[record["thread_id"]] = message_id
        return record, True

    def persist(self):
        if self.fault:
            # Never replace an unreadable or unconfirmed original snapshot with
            # an empty record merely because a later admission was rejected.
            raise StudioError("INPUT_STORAGE_UNCONFIRMED", self.fault, 503, submission_state="unknown")
        try:
            pending = [record for record in self.unresolved() if "snapshot" in record]
            if len(pending) > 1:
                raise ValueError("Only one owned input can be unresolved before changing Thread")
            value = {"format": 1, "pending": pending}
            if len(encoded(value).encode("utf-8")) > 2 * 1024 * 1024:
                raise ValueError("Pending input exceeds its storage bound")
            atomic_json(self.path, value)
        except (OSError, ValueError, TypeError):
            self.fault = "未确认输入无法保存；原发送结果待确认，暂不能继续发送。"
            raise StudioError("INPUT_STORAGE_UNCONFIRMED", self.fault, 503, submission_state="unknown") from None

    def reserve(self, record, snapshot):
        if self.fault:
            raise StudioError("INPUT_STORAGE_UNCONFIRMED", self.fault, 503, submission_state="not_submitted")
        record.update(state="pending", snapshot=copy.deepcopy(snapshot))
        self.last[record["thread_id"]] = record["client_user_message_id"]
        self.persist()

    def settle(self, record, state, *, turn_id=None, native_item_id=None, error=None):
        if record["state"] == "accepted":
            if native_item_id:
                record["native_item_id"] = native_item_id
                record["confirmation_source"] = "native_item"
            return
        record["state"] = state
        if turn_id:
            record["turn_id"] = turn_id
        if native_item_id:
            record["native_item_id"] = native_item_id
        if state == "accepted":
            record["confirmation_source"] = "native_item" if native_item_id else "native_ack"
        if error:
            record["error"] = error
        else:
            record.pop("error", None)
        if state in {"accepted", "not_submitted"}:
            record.pop("snapshot", None)
        self.persist()

    @staticmethod
    def public(record):
        return copy.deepcopy({key: value for key, value in record.items()
                              if key not in {"fingerprint", "account_identity"}}) if record else None

    def snapshot(self, thread_id):
        unresolved = self.unresolved(thread_id)
        record = unresolved[0] if unresolved else self.records.get(self.last.get(thread_id))
        return {"user_submission": self.public(record),
                "unresolved_submissions": [self.public(item) for item in self.unresolved()],
                "submission_storage_fault": self.fault}
