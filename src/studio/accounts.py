"""Small projections of one native client's account and owned login attempt."""
from __future__ import annotations

import copy
import threading
from collections import deque
from urllib.parse import urlsplit

from .common import StudioError


def account_status(value):
    account = value.get("account")
    if account is None:
        return "signed_out"
    return "signed_in" if account.get("type") == "chatgpt" else "other"


class NativeAccount:
    def __init__(self, client):
        self.client = client
        self.lock = threading.RLock()
        self.action = threading.Lock()
        self.revision = 0
        self.value = {"account": None, "requiresOpenaiAuth": True,
                      "status": "unknown", "message": "正在确认账号。"}
        self.login_id = None
        self._auth_url = None  # Only used by an explicit browser action; never in snapshots.
        self.uncertain = None
        self.completions = deque(maxlen=8)

    def snapshot(self):
        with self.lock:
            return {**copy.deepcopy(self.value), "account_revision": self.revision,
                    "login_pending": bool(self.login_id), "action_unknown": bool(self.uncertain)}

    def invalidate(self, message="账号状态已变化，请重新确认。"):
        with self.lock:
            self.revision += 1
            self.value.update(status="unknown", message=message)

    def observe(self, event):
        method, params = event.get("method"), event.get("params", {})
        with self.lock:
            if method == "account/updated":
                self.invalidate()
                # A native change is authoritative; a stale read is not.
                if params.get("authMode") is None:
                    self.value.update(account=None, status="signed_out", message="请使用 ChatGPT 登录。")
                    if self.uncertain == "logout":
                        self.uncertain = None
            elif method == "account/login/completed":
                login_id = params.get("loginId")
                if login_id:
                    self.completions.append(login_id)
                if login_id and login_id == self.login_id:
                    self.login_id = self._auth_url = self.uncertain = None
                    self.invalidate("登录流程已结束，正在确认账号。")
            elif event.get("type") in {"process_exit", "process_stopped"}:
                self.login_id = self._auth_url = self.uncertain = None
                self.invalidate("Codex 连接已结束，账号状态尚未确认。")

    def read(self):
        with self.lock:
            revision = self.revision
        try:
            result = self.client.request("account/read", {"refreshToken": False})
        except Exception:
            self.invalidate("暂时无法确认账号，请重新检查。")
            raise
        if not isinstance(result, dict) or "account" not in result:
            raise StudioError("ACCOUNT_RESPONSE_INVALID", "原生账号响应不完整，请重新检查。", 502)
        account = result["account"]
        if account is not None:
            if not isinstance(account, dict) or not isinstance(account.get("type"), str):
                raise StudioError("ACCOUNT_RESPONSE_INVALID", "原生账号类型尚未确认。", 502)
            # Keep identity labels only; credentials never belong to this projection.
            account = {key: account[key] for key in ("type", "email", "planType")
                       if isinstance(account.get(key), str)}
        value = {"account": account, "requiresOpenaiAuth": result.get("requiresOpenaiAuth", True)}
        with self.lock:
            if revision != self.revision:
                return self.snapshot()
            if account != self.value.get("account"):
                self.revision += 1
            status = account_status(value)
            if self.uncertain == "logout" and status != "signed_out":
                status = "unknown"
            elif self.uncertain == "logout" or status == "signed_in":
                self.uncertain = None
                self.login_id = self._auth_url = None
            if self.login_id and status != "signed_in":
                status = "waiting"
            elif self.uncertain:
                status = "unknown"
            messages = {"signed_in": "已登录 ChatGPT。", "signed_out": "请使用 ChatGPT 登录。",
                        "other": "当前使用其他认证方式，请切换到 ChatGPT 登录。",
                        "waiting": "等待浏览器完成登录。", "unknown": "账号操作结果尚未确认，请查询账号。"}
            self.value = {**value, "status": status, "message": messages[status]}
            return self.snapshot()

    def start_login(self):
        with self.action:
            with self.lock:
                if self.uncertain:
                    raise StudioError("ACCOUNT_ACTION_UNKNOWN", "上次登录操作尚未确认，请先查询或结束此登录连接。", 409)
                if self.login_id:
                    return {"type": "chatgpt", "loginId": self.login_id, "authUrl": self._auth_url}
            try:
                result = self.client.request("account/login/start", {"type": "chatgpt"})
            except Exception:
                with self.lock:
                    self.uncertain = "login"
                    self.invalidate("登录是否已开始尚未确认，请先查询账号。")
                raise
            url = result.get("authUrl", "") if isinstance(result, dict) else ""
            try:
                parsed = urlsplit(url if isinstance(url, str) else "")
                valid_url = parsed.scheme == "https" and parsed.hostname and not parsed.username and not parsed.password
            except ValueError:
                valid_url = False
            if (not isinstance(result, dict) or result.get("type") != "chatgpt" or
                    not isinstance(result.get("loginId"), str) or
                    not valid_url):
                with self.lock:
                    self.uncertain = "login"
                raise StudioError("LOGIN_RESPONSE_INVALID", "原生登录响应不完整，请重新检查 Codex。", 502)
            with self.lock:
                if result["loginId"] not in self.completions:
                    self.login_id, self._auth_url = result["loginId"], url
                    self.value.update(status="waiting", message="等待浏览器完成登录。")
                else:
                    self.invalidate("登录流程已结束，请查询账号。")
            return {"type": "chatgpt", "loginId": result["loginId"], "authUrl": url}

    def reopen_login(self):
        with self.lock:
            if not self.login_id or not self._auth_url or self.uncertain:
                raise StudioError("LOGIN_NOT_PENDING", "当前没有可重新打开的登录流程。", 409)
            return self._auth_url

    def cancel_login(self):
        with self.action:
            with self.lock:
                login_id = self.login_id
                if self.uncertain:
                    raise StudioError("ACCOUNT_ACTION_UNKNOWN", "登录结果尚未确认，请结束此登录连接后重新检查。", 409)
            if not login_id:
                return self.snapshot()
            try:
                self.client.request("account/login/cancel", {"loginId": login_id})
            except Exception:
                with self.lock:
                    self.uncertain = "cancel"
                    self.invalidate("取消登录尚未确认，请先查询账号。")
                raise
            with self.lock:
                if self.login_id == login_id:
                    self.login_id = self._auth_url = None
                self.invalidate("登录已取消，请查询当前账号。")
            return self.read()

    def logout(self):
        with self.action:
            with self.lock:
                if self.uncertain:
                    raise StudioError("ACCOUNT_ACTION_UNKNOWN", "上次账号操作尚未确认，请先查询。", 409)
                login_id = self.login_id
            if login_id:
                try:
                    self.client.request("account/login/cancel", {"loginId": login_id})
                except Exception:
                    with self.lock:
                        self.uncertain = "cancel"
                        self.invalidate("取消登录尚未确认，请先查询账号。")
                    raise
            with self.lock:
                self.login_id = self._auth_url = None
                self.invalidate("正在退出账号。")
            try:
                self.client.request("account/logout", {})
            except Exception:
                with self.lock:
                    self.uncertain = "logout"
                    self.invalidate("退出账号尚未确认，请先查询账号。")
                raise
            return self.read()
