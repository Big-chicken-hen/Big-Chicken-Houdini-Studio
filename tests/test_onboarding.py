"""Account ownership and candidate selection without login, inference or Houdini."""
import copy
import tempfile
import unittest
from pathlib import Path

from studio.accounts import NativeAccount
from studio.codex.client import CodexStdioClient, _PendingResponse
from studio.codex.errors import BridgeError, ProtocolRejected
from studio.codex.protocol import ProtocolPolicy
from studio.common import AppPaths, StudioError, encoded
from studio.onboarding import Onboarding


AUTH_URL = "https://auth.openai.com/oauth/authorize?state=fixture-state&code_challenge=fixture-challenge"


class AccountClient:
    def __init__(self, command=(), *, event_sink=None, **kwargs):
        self.command, self.options, self.sink = command, kwargs, event_sink
        self.calls = []
        self.is_running = False
        self.identity = {"account": {"type": "chatgpt", "email": "fixture@example.invalid", "planType": "plus"},
                         "requiresOpenaiAuth": True}
        self.fail = None
        self.read_hook = None
        self.login_number = 0

    def start(self):
        self.is_running = True

    def initialize(self):
        self.calls.append(("initialize", {}))
        if self.command and "handshake-fails" in self.command[0]:
            raise BridgeError("CODEX_REQUEST_TIMEOUT", "fixture initialize failure")

    def notify(self, method, **params):
        if self.sink:
            self.sink({"type": "codex_notification", "method": method, "params": params})

    def request(self, method, params):
        self.calls.append((method, params))
        if method == self.fail:
            raise BridgeError("CODEX_REQUEST_TIMEOUT", "fixture response loss")
        if method == "account/read":
            value = copy.deepcopy(self.identity)
            if self.read_hook:
                self.read_hook()
            return value
        if method == "account/login/start":
            self.login_number += 1
            return {"type": "chatgpt", "loginId": str(self.login_number), "authUrl": AUTH_URL}
        if method == "account/login/cancel":
            self.notify("account/login/completed", loginId=params["loginId"], success=False)
            return {"status": "canceled"}
        if method == "account/logout":
            self.identity["account"] = None
            self.notify("account/updated", authMode=None)
            return {}
        raise AssertionError(method)

    def close(self, **_kwargs):
        self.calls.append(("close", {}))
        self.is_running = False
        if self.sink:
            self.sink({"type": "process_stopped"})


class OnboardingTests(unittest.TestCase):
    def setUp(self):
        folder = Path(__file__).resolve().parents[1] / ".runtime" / "tests"
        folder.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=folder)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "pyproject.toml").write_text("# fixture", encoding="utf-8")
        self.paths = AppPaths(self.root, data_root=self.root / "state", cache_root=self.root / "cache")
        self.houdini = self.root / "Houdini 22.0.368" / "bin" / "houdini.exe"
        self.houdini.parent.mkdir(parents=True)
        self.houdini.touch()
        self.clients = []

    def make(self, candidates, signed_in=True):
        def factory(*args, **kwargs):
            client = AccountClient(*args, **kwargs)
            if not signed_in:
                client.identity["account"] = None
            self.clients.append(client)
            return client

        def version(path, _paths):
            if "incompatible" in str(path):
                raise StudioError("CODEX_VERSION_UNTESTED", "fixture mismatch")
            return str(path)

        value = Onboarding(self.paths, client_factory=factory, version_checker=version,
                           candidate_provider=lambda *_: candidates,
                           houdini_provider=lambda: [{"path": str(self.houdini), "label": "Houdini 22.0.368"}])
        self.addCleanup(value.close)
        return value

    def test_automatic_selection_checks_candidates_and_hands_off_same_profile(self):
        value = self.make(["incompatible", "handshake-fails", "compatible"])
        result = value.probe()
        self.assertEqual(result["codex"]["path"], "compatible")
        self.assertEqual(result["account"]["status"], "signed_in")
        self.assertFalse(self.clients[0].is_running)
        client = self.clients[-1]
        policy = client.options["policy"]
        for method in ("thread/start", "turn/start", "model/list"):
            with self.assertRaises(ProtocolRejected):
                policy.require_client_request(method)
        self.assertFalse(policy.server_requests)
        self.assertEqual(client.options["environment"]["CODEX_HOME"], str(self.paths.codex_home))
        handoff = value.prepare_launch()
        self.assertEqual(handoff, {"codex_path": "compatible", "houdini_path": str(self.houdini),
                                   "codex_home": str(self.paths.codex_home)})
        self.assertFalse(client.is_running)
        self.assertNotIn("workspace", encoded(result).lower())

    def test_invalid_explicit_override_never_falls_back_and_is_remembered(self):
        value = self.make(["compatible"])
        result = value.probe(codex_override="incompatible")
        self.assertEqual(result["error"]["code"], "CODEX_OVERRIDE_INVALID")
        self.assertEqual(self.clients, [])
        later = self.make(["compatible"])
        self.assertEqual(later.probe()["codex"]["state"], "incompatible")
        self.assertEqual(self.clients, [])
        self.assertEqual(later.probe(codex_override="")["codex"]["state"], "ready")

    def test_owned_login_requires_account_confirmation_and_stale_completion_is_ignored(self):
        value = self.make(["compatible"], signed_in=False)
        value.probe()
        first = value.login_start()
        self.assertEqual(first["auth_url"], AUTH_URL)
        self.assertNotIn("fixture-state", encoded(value.snapshot()))
        self.assertEqual(value.login_start()["auth_url"], AUTH_URL)
        client = self.clients[-1]
        self.assertEqual(client.login_number, 1)
        client.notify("account/login/completed", loginId="old", success=True)
        self.assertEqual(value.snapshot()["account"]["status"], "waiting")
        client.notify("account/login/completed", loginId="1", success=True)
        self.assertEqual(value.snapshot()["account"]["status"], "unknown")
        client.identity["account"] = {"type": "chatgpt", "email": "confirmed@example.invalid"}
        self.assertEqual(value.account_read()["account"]["status"], "signed_in")

    def test_close_cancels_only_owned_login_and_late_old_client_cannot_change_state(self):
        value = self.make(["compatible"], signed_in=False)
        value.probe()
        value.login_start()
        old = self.clients[-1]
        value.probe()
        self.assertIn(("account/login/cancel", {"loginId": "1"}), old.calls)
        before = value.snapshot()
        old.notify("account/updated", authMode=None)
        self.assertEqual(value.snapshot(), before)
        value.close()
        with self.assertRaises(StudioError):
            value.probe()

    def test_network_unknown_and_api_key_account_never_become_chatgpt_ready(self):
        value = self.make(["compatible"])
        value.probe()
        client = self.clients[-1]
        client.fail = "account/read"
        self.assertEqual(value.account_read()["account"]["status"], "unknown")
        client.fail = None
        client.identity["account"] = {"type": "apiKey"}
        self.assertEqual(value.account_read()["account"]["status"], "other")
        with self.assertRaises(StudioError):
            value.prepare_launch()

    def test_native_account_fences_old_reads_and_does_not_replay_unknown_login(self):
        client = AccountClient()
        account = NativeAccount(client)
        client.sink = account.observe
        client.read_hook = lambda: client.notify("account/updated", authMode="chatgpt")
        self.assertEqual(account.read()["status"], "unknown")
        client.read_hook = None
        client.fail = "account/login/start"
        with self.assertRaises(BridgeError):
            account.start_login()
        with self.assertRaises(StudioError):
            account.start_login()
        self.assertEqual(sum(method == "account/login/start" for method, _ in client.calls), 1)

    def test_logout_uses_official_cancel_and_logout_without_file_credential_access(self):
        value = self.make(["compatible"], signed_in=False)
        value.probe()
        value.login_start()
        result = value.logout()
        self.assertEqual(result["account"]["status"], "signed_out")
        methods = [method for method, _ in self.clients[-1].calls]
        self.assertLess(methods.index("account/login/cancel"), methods.index("account/logout"))
        self.assertFalse((self.paths.codex_home / "auth.json").exists())

    def test_auth_url_only_survives_the_owned_login_response(self):
        client = CodexStdioClient(["unused"], cwd=self.root, environment={}, policy=ProtocolPolicy())
        pending = _PendingResponse("account/login/start")
        client._pending[1] = pending
        client._handle_response({"id": 1, "result": {"type": "chatgpt", "loginId": "fixture", "authUrl": AUTH_URL}})
        self.assertEqual(pending.result["authUrl"], AUTH_URL)
        self.assertNotIn("fixture-state", encoded(client._redact_value({"authUrl": AUTH_URL})))
        self.assertNotIn("fixture-challenge", client._redact_text("Login: " + AUTH_URL))
        self.assertNotIn("secret-code", client._redact_text("http://localhost:1455/auth/callback?code=secret-code"))


if __name__ == "__main__":
    unittest.main()
