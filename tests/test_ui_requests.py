"""Explicit permission choices and late scene-trust responses, using offscreen Qt."""
import copy
import os
from pathlib import Path
import secrets
import tempfile
import unittest
from unittest.mock import Mock

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6 import QtWidgets  # noqa: E402

from studio.ui.requests import RequestCard, SessionTrustControl  # noqa: E402


class DeferredApi:
    def __init__(self):
        self.calls = []

    def call(self, method, path, body=None, done=None, failed=None):
        self.calls.append((method, path, copy.deepcopy(body), done, failed))
        return True


def trust_state(thread_id="thread_a", enabled=False, **extra):
    return {"thread_id": thread_id, "scene_trust": {
        "thread_id": thread_id, "enabled": enabled, "available": True, "can_change": True,
        "revision": 1, **extra}}


class RequestControlsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.api = DeferredApi()
        self.control = SessionTrustControl(self.api)
        self.control.apply_state(trust_state())

    def tearDown(self):
        self.control.close()
        self.control.deleteLater()
        self.app.processEvents()

    def test_grant_is_explicit_and_not_optimistic(self):
        self.assertEqual(self.api.calls, [])
        self.control.toggle.click()
        self.assertEqual(self.api.calls, [])
        self.control.grant.click()
        self.control.request_change(True)
        self.assertEqual(len(self.api.calls), 1)
        method, path, body, done, _ = self.api.calls[0]
        self.assertEqual((method, path, body),
                         ("POST", "/scene-trust", {"enabled": True, "thread_id": "thread_a", "revision": 1}))
        self.assertNotIn("已授权", self.control.status.text())
        self.assertFalse(self.control.grant.isEnabled())
        done({"scene_trust": trust_state(enabled=True, revision=2)["scene_trust"]})
        self.assertIn("已授权", self.control.status.text())
        self.assertTrue(self.control.revoke.isEnabled())
        # A pre-change /state response arriving late cannot revert the display.
        self.control.apply_state(trust_state(enabled=False, revision=1))
        self.assertIn("已授权", self.control.status.text())

    def test_lost_revoke_response_requires_query_not_replay(self):
        self.control.apply_state(trust_state(enabled=True))
        changed = []
        self.control.changed.connect(lambda: changed.append(True))
        self.control.revoke.click()
        self.api.calls[0][4]("response lost")
        self.assertTrue(self.control.uncertain)
        self.assertIn("尚未确认", self.control.status.text())
        self.control.request_change(False)
        self.control.query.click()
        self.assertEqual([call[:2] for call in self.api.calls], [("POST", "/scene-trust"), ("GET", "/state")])
        # An old Panel poll cannot settle a write that lost its response.
        self.control.apply_state(trust_state(enabled=True))
        self.assertTrue(self.control.uncertain)
        # A read initiated after the failure can confirm the grant is still active.
        self.api.calls[1][3](trust_state(enabled=True))
        self.assertFalse(self.control.uncertain)
        self.assertIn("已授权", self.control.status.text())
        self.assertTrue(self.control.feedback.isHidden())
        self.assertEqual(len(changed), 1)

    def test_late_grant_cannot_apply_to_another_conversation(self):
        self.control.request_change(True)
        _, _, _, done, failed = self.api.calls[0]
        self.control.apply_state(trust_state("thread_b"))
        done({"scene_trust": trust_state(enabled=True)["scene_trust"]})
        failed("old timeout")
        self.assertEqual(self.control.thread_id, "thread_b")
        self.assertFalse(self.control.uncertain)
        self.assertNotIn("已授权", self.control.status.text())
        self.assertTrue(self.control.feedback.isHidden())

    def test_unavailable_or_busy_native_policy_cannot_be_changed(self):
        self.control.apply_state(trust_state(can_change=False, reason="Wait for the current operation"))
        self.control.request_change(True)
        self.assertFalse(self.control.grant.isEnabled())
        self.assertIn("current operation", self.control.grant.toolTip())
        self.assertEqual(self.api.calls, [])
        self.control.apply_state({"thread_id": "thread_b"})
        self.control.request_change(True)
        self.assertEqual(self.api.calls, [])
        self.control.set_api(None)
        self.control.apply_state(trust_state())
        self.assertFalse(self.control.toggle.isEnabled())

    def test_existing_trust_can_be_revoked_while_houdini_is_disconnected(self):
        self.control.apply_state(trust_state(enabled=True, available=False, can_change=True,
                                            reason="Houdini is disconnected"))
        self.assertIn("已授权", self.control.status.text())
        self.assertTrue(self.control.revoke.isEnabled())
        self.control.revoke.click()
        self.assertEqual(self.api.calls[0][2]["enabled"], False)

    def test_control_and_bridge_share_binding_revision_and_revocation_contract(self):
        from studio.bridge import Bridge
        from studio.common import AppPaths, StudioError
        from studio.workspace import Workspaces

        root = Path(__file__).resolve().parents[1] / ".runtime" / "request-ui-tests"
        root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as directory:
            path = Path(directory)
            (path / "pyproject.toml").write_text("# fixture", encoding="utf-8")
            paths = AppPaths(path)
            workspace = Workspaces(paths).create("Local approval UI fixture")
            bridge = Bridge(paths, workspace["workspace_id"], "fixture", secrets.token_hex(24), "codex",
                            Mock(is_running=True))
            bridge.thread_id = "thread_a"
            bridge._runtime = Mock()
            bridge._runtime.call.return_value = {"alive": True}

            class DirectApi:
                def call(self, method, route, body=None, done=None, failed=None):
                    try:
                        value = bridge.route(method, route, {}, body or {})
                    except StudioError as exc:
                        if failed:
                            failed(str(exc))
                    else:
                        if done:
                            done(value)
                    return True

            self.control.set_api(DirectApi())
            self.control.apply_state(bridge.state())
            self.control.grant.click()
            self.assertTrue(bridge.scene_trust.enabled)
            self.assertEqual(self.control.trust["revision"], bridge.scene_trust.revision)
            bridge._runtime.call.side_effect = StudioError("CONNECTION_LOST", "offline")
            self.control.apply_state(bridge.state())
            self.control.revoke.click()
            self.assertFalse(bridge.scene_trust.enabled)
            self.assertIn("逐次确认", self.control.status.text())

    def test_native_permission_session_choice_is_separate_and_explicit(self):
        permissions = {"fileSystem": {"write": ["C:/explicit-output"]}}
        card = RequestCard({"request_id": 71, "method": "item/permissions/requestApproval",
                            "params": {"permissions": permissions}})
        responses = []
        card.respond.connect(lambda request_id, value: responses.append((request_id, value)))
        self.assertEqual(responses, [])
        next(button for button in card.actions if "本会话" in button.text()).click()
        self.assertEqual(responses, [(71, {"permissions": permissions, "scope": "session"})])
        self.assertEqual(self.api.calls, [])
        self.assertTrue(all(not button.isEnabled() for button in card.actions))
        card.deleteLater()

    def test_ambiguous_native_response_cannot_be_sent_twice(self):
        request = {"request_id": 72, "method": "mcpServer/elicitation/request", "params": {
            "mode": "form", "_meta": {"codex_approval_kind": "mcp_tool_call"},
            "requestedSchema": {"type": "object", "properties": {}}}}
        card = RequestCard(request)
        responses = []
        card.respond.connect(lambda request_id, value: responses.append((request_id, value)))
        card.actions[0].click()
        card.failed("Response lost")
        card.update_request(request)  # An old pending snapshot is not proof of non-delivery.
        card.submit({"action": "accept", "content": {}})
        self.assertEqual(len(responses), 1)
        self.assertTrue(card.response_unknown)
        self.assertTrue(all(not button.isEnabled() for button in card.actions))
        card.deleteLater()
        unknown_card = RequestCard({**request, "response_state": "unknown"})
        self.assertTrue(unknown_card.response_unknown)
        self.assertTrue(all(not button.isEnabled() for button in unknown_card.actions))
        unknown_card.deleteLater()


if __name__ == "__main__":
    unittest.main()
