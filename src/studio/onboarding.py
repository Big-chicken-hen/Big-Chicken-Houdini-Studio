"""Bounded native environment/account checks, called only by UI workers."""
from __future__ import annotations

import copy
import os
import shutil
import threading
import time
from pathlib import Path

from .accounts import NativeAccount
from .codex.client import CodexStdioClient
from .codex.protocol import ProtocolPolicy, SUPPORTED_CODEX_VERSION
from .common import StudioError, atomic_json, read_json
from .launcher import check_codex, codex_app_server_command, discover_houdini, helper_environment
from .houdini_compatibility import inspect_houdini, require_houdini_launch, VALIDATED_VERSION


ONBOARDING_POLICY = ProtocolPolicy(client_requests=frozenset({
    "initialize", "account/read", "account/login/start", "account/login/cancel", "account/logout"}),
    server_requests=frozenset())


def codex_candidates(paths, preferred=None):
    """Enumerate known native installations without executing shell wrappers."""
    name = "codex.exe" if os.name == "nt" else "codex"
    values = [preferred, paths.install("tools", "codex", "bin", name),
              paths.local("toolchains", "codex", name), shutil.which(name)]
    if os.name == "nt":
        local = os.environ.get("LOCALAPPDATA")
        if local:
            binary_root = Path(local) / "OpenAI" / "Codex" / "bin"
            if binary_root.is_dir():
                values.extend(sorted(binary_root.glob("*/codex.exe"))[:24])
            values.append(Path(local) / "Programs" / "Codex" / "resources" / name)
        wrapper = shutil.which("codex.cmd")
        if wrapper:
            modules = Path(wrapper).parent / "node_modules" / "@openai"
            for package in (modules / "codex", modules / "codex-win32-x64",
                            modules / "codex" / "node_modules" / "@openai" / "codex-win32-x64"):
                values.append(package / "vendor" / "x86_64-pc-windows-msvc" / "codex" / name)
    seen, result = set(), []
    for value in values:
        if not value:
            continue
        path = Path(value).expanduser().resolve()
        key = os.path.normcase(str(path))
        if key not in seen and path.is_file():
            seen.add(key)
            result.append(str(path))
    return result[:12]


class Onboarding:
    """One owned App Server; never creates threads, tools or Houdini processes."""
    def __init__(self, paths, *, client_factory=CodexStdioClient, version_checker=check_codex,
                 candidate_provider=codex_candidates, houdini_provider=discover_houdini, houdini_inspector=inspect_houdini):
        self.paths = paths
        self.client_factory, self.version_checker = client_factory, version_checker
        self.candidate_provider, self.houdini_provider = candidate_provider, houdini_provider
        self.houdini_inspector = houdini_inspector
        self.lock, self.action = threading.RLock(), threading.RLock()
        self.client = self.account = None
        self.generation = self.revision = 0
        self.closed = False
        self.preferences_path = paths.data("environment-preferences.json")
        try:
            value = read_json(self.preferences_path)
            self.preferences = value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            self.preferences = {}
        self.codex = {"state": "checking", "path": "", "version": None, "message": "正在检查 Codex。"}
        self.houdini = {"state": "missing", "path": "", "version": None, "installations": [],
                        "message": "尚未检查 Houdini 安装。"}
        self.last_account = {"status": "unknown", "message": "尚未确认账号。"}
        self.error = None

    def snapshot(self):
        with self.lock:
            account = self.last_account
            if self.account:
                native = self.account.snapshot()
                identity = native.get("account") or {}
                account = {"status": native["status"], "message": native["message"],
                           "type": identity.get("type"), "email": identity.get("email"),
                           "plan_type": identity.get("planType"),
                           "account_revision": native["account_revision"],
                           "login_pending": native["login_pending"], "action_unknown": native["action_unknown"]}
            return copy.deepcopy({"revision": self.revision, "codex": self.codex,
                                  "houdini": self.houdini, "account": account, "error": self.error})

    def _failed(self, code, message):
        with self.lock:
            self.error = {"code": code, "message": message}
            if code == "ONBOARDING_CLOSE_UNKNOWN":
                self.codex.update(state="error", message=message)
            self.revision += 1
        return self.snapshot()

    def _require_open(self):
        if self.closed:
            raise StudioError("ONBOARDING_CLOSED", "启动器已关闭。", 409)

    def _require_client(self):
        self._require_open()
        if not self.client or not self.client.is_running:
            raise StudioError("CODEX_RECHECK_REQUIRED", "请重新检查 Codex 连接。", 409)

    def _event(self, generation, event):
        with self.lock:
            if generation != self.generation or self.closed:
                return
            if self.account:
                self.account.observe(event)
            if event.get("type") == "process_exit":
                self.codex.update(state="error", message="Codex 已退出，请重新检查。")
            if event.get("method", "").startswith("account/") or event.get("type") == "process_exit":
                self.revision += 1

    def _stop_client(self):
        with self.lock:
            self.generation += 1  # Discard notifications from the client being closed.
            client, account = self.client, self.account
        if client:
            try:
                if account and account.login_id and not account.uncertain and client.is_running:
                    account.cancel_login()
            except Exception:
                pass  # Closing this owned connection also ends its browser callback.
            client.close(grace_seconds=0.5, deadline=time.monotonic() + 4)
            if client.is_running:
                raise StudioError("ONBOARDING_CLOSE_UNKNOWN", "登录连接尚未结束，请查询后再启动。", 409)
        with self.lock:
            self.client = self.account = None

    def _save_preferences(self, **values):
        self.preferences.update(values)
        atomic_json(self.preferences_path, self.preferences)

    def _houdini(self, override):
        installations = [{**item, **self.houdini_inspector(item["path"], self.paths)} for item in self.houdini_provider()]
        selected_path = override or self.preferences.get("last_houdini")
        if selected_path:
            selected = self.houdini_inspector(selected_path, self.paths)
            if not any(item["path"] == selected["path"] for item in installations):
                installations.insert(0, {"label": Path(selected_path).parent.parent.name, **selected})
        else:
            automatic = [item for item in installations if item["compatibility"]["auto_selectable"]]
            # Preserve explicit choices above; an untested newer build must not
            # displace the observed baseline when selecting an installation.
            automatic.sort(key=lambda item: (item["compatibility"]["status"] != "validated",
                                             item["version"] != VALIDATED_VERSION))
            selected = automatic[0] if automatic else None
        if not selected or not selected["path"]:
            self.houdini = {"state": "missing", "path": "", "version": None, "installations": installations,
                            "message": "请选择已有 Houdini GUI 安装；后续 22.x minor 版本须手动选择。"}
            return
        self.houdini = {**{key: selected[key] for key in ("path", "version", "compatibility")},
                        "state": "incompatible" if selected["compatibility"]["status"] == "unsupported" else "found",
                        "installations": installations, "message": selected["compatibility"]["message"]}

    def _codex_selection(self, override):
        bundled = self.paths.install("tools", "codex", "bin", "codex.exe" if os.name == "nt" else "codex")
        installed = (self.paths.root / "release-manifest.json").is_file()
        # An explicit empty preference is the user's Restore bundled choice.
        # Do not silently let an inherited external path undo that choice.
        explicit = (str(override).strip() if override is not None else
                    self.preferences["codex_override"] if "codex_override" in self.preferences else
                    os.environ.get("BCS_CODEX_PATH"))
        if explicit:
            source = "bundled" if os.path.normcase(str(Path(explicit).resolve())) == os.path.normcase(str(bundled.resolve())) else "explicit_external"
            return [explicit], source
        if installed:
            return [str(bundled)], "bundled"
        return self.candidate_provider(self.paths, self.preferences.get("codex_verified")), "discovered"

    def probe(self, codex_override=None, houdini_override=None):
        with self.action:
            self._require_open()
            try:
                self._stop_client()
            except Exception:
                return self._failed("ONBOARDING_CLOSE_UNKNOWN", "上次 Codex 连接尚未结束，请重新检查。")
            with self.lock:
                self.error = None
                self.last_account = {"status": "unknown", "message": "正在确认账号。"}
                self.codex = {"state": "checking", "path": "", "version": None, "message": "正在检查 Codex。"}
                self.revision += 1
                if codex_override is not None:
                    self._save_preferences(codex_override=str(codex_override).strip())
                self._houdini(houdini_override)
                candidates, source = self._codex_selection(codex_override)
            failures = []
            for candidate in candidates:
                try:
                    checked = self.version_checker(candidate, self.paths)
                    env = helper_environment(self.paths)
                    env["CODEX_HOME"] = str(self.paths.codex_home)
                    cwd = self.paths.data("onboarding")
                    cwd.mkdir(parents=True, exist_ok=True)
                    self.paths.codex_home.mkdir(parents=True, exist_ok=True)
                    with self.lock:
                        self.generation += 1
                        generation = self.generation
                        client = self.client_factory(codex_app_server_command(checked), cwd=cwd, environment=env,
                            policy=ONBOARDING_POLICY, request_timeout=6,
                            event_sink=lambda event, generation=generation: self._event(generation, event))
                        self.client, self.account = client, NativeAccount(client)
                    client.start()
                    client.initialize()
                    with self.lock:
                        self.codex = {"state": "ready", "path": checked, "version": SUPPORTED_CODEX_VERSION, "source": source,
                                      "message": "原生连接已确认。"}
                        self._save_preferences(codex_verified=checked)
                        self.revision += 1
                    # Network/account errors do not turn a working binary into missing Codex.
                    try:
                        self.account.read()
                    except Exception:
                        self.error = {"code": "ACCOUNT_UNAVAILABLE", "message": "暂时无法确认账号，请重新检查。"}
                    return self.snapshot()
                except Exception as exc:
                    failures.append({"path": str(candidate), "code": getattr(exc, "code", "CODEX_UNAVAILABLE")})
                    try:
                        self._stop_client()
                    except Exception:
                        return self._failed("ONBOARDING_CLOSE_UNKNOWN", "Codex 连接退出尚未确认，不能再启动另一个。")
            with self.lock:
                state = "missing" if not candidates else "incompatible"
                self.codex.update(state=state, source=source,
                                  message="随包 Codex 缺失或不可用，请修复安装。" if source == "bundled" else
                                  "未找到可用 Codex。请安装或选择兼容的 " + SUPPORTED_CODEX_VERSION + "。",
                                  path=str(candidates[0]) if len(candidates) == 1 else "", attempts=failures)
            code = "CODEX_OVERRIDE_INVALID" if source == "explicit_external" else "CODEX_BUNDLED_INVALID" if source == "bundled" else "CODEX_REQUIRED"
            return self._failed(code, self.codex["message"])

    def account_read(self):
        with self.action:
            self._require_client()
            try:
                self.account.read()
                self.error = None
            except Exception:
                self.error = {"code": "ACCOUNT_UNAVAILABLE", "message": "暂时无法确认账号，请重新检查。"}
            return self.snapshot()

    def login_start(self):
        with self.action:
            self._require_client()
            value = self.account.start_login()
            return {**self.snapshot(), "auth_url": value["authUrl"]}

    def reopen_login(self):
        with self.action:
            self._require_client()
            return self.account.reopen_login()

    def cancel_login(self):
        with self.action:
            self._require_client()
            self.account.cancel_login()
            return self.snapshot()

    def logout(self):
        with self.action:
            self._require_client()
            self.account.logout()
            return self.snapshot()

    def prepare_launch(self, houdini_confirmation=None):
        with self.action:
            self._require_client()
            account = self.account.read()
            if self.codex["state"] != "ready" or account["status"] != "signed_in":
                raise StudioError("CHATGPT_LOGIN_REQUIRED", "请先确认 ChatGPT 登录。", 409)
            if self.houdini["state"] != "found":
                raise StudioError("HOUDINI_REQUIRED", "请选择 Houdini 安装。")
            selected = self.houdini_inspector(self.houdini["path"], self.paths)
            require_houdini_launch(selected, houdini_confirmation)
            result = {"codex_path": self.codex["path"], "houdini_path": self.houdini["path"],
                      "codex_home": str(self.paths.codex_home)}
            if houdini_confirmation is not None:
                result["houdini_confirmation"] = copy.deepcopy(houdini_confirmation)
            self.last_account = self.snapshot()["account"]
            self._stop_client()
            return result

    def remember_houdini(self, path):
        with self.action:
            if Path(path).is_file():
                self._save_preferences(last_houdini=str(Path(path).resolve()))

    def close(self):
        with self.action:
            with self.lock:
                self.closed = True
            self._stop_client()
