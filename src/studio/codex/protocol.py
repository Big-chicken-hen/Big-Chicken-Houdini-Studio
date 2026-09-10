"""Versioned integration surface, independent of the historical HIA contracts."""
from dataclasses import dataclass
import re

from .errors import ProtocolRejected

SUPPORTED_CODEX_VERSION = "0.153.4"


@dataclass(frozen=True)
class ProtocolPolicy:
    version: str = SUPPORTED_CODEX_VERSION
    client_requests: frozenset = frozenset({
        "initialize", "thread/start", "thread/resume", "thread/list", "thread/read",
        "thread/turns/list", "thread/items/list",
        "thread/name/set", "thread/archive", "thread/unarchive", "thread/delete",
        "turn/start", "turn/steer", "turn/interrupt", "model/list", "account/read", "account/login/start",
        "account/login/cancel", "account/logout", "account/rateLimits/read"})
    client_notifications: frozenset = frozenset({"initialized"})
    server_requests: frozenset = frozenset({
        "item/commandExecution/requestApproval", "item/fileChange/requestApproval",
        "item/permissions/requestApproval", "item/tool/requestUserInput", "mcpServer/elicitation/request"})

    def require_client_request(self, method):
        if method not in self.client_requests:
            raise ProtocolRejected(method, "client request")

    def require_client_notification(self, method):
        if method not in self.client_notifications:
            raise ProtocolRejected(method, "client notification")

    def allows_server_request(self, method):
        return method in self.server_requests

    def allows_server_notification(self, method):
        # Unknown notifications are harmless projections, never commands or recovery triggers.
        return isinstance(method, str)


def steer_rejection_reason(error, expected_turn_id, version=SUPPORTED_CODEX_VERSION):
    """Classify only proven 0.153.4 steer admission refusals, preserving the RPC.

    No-active/mismatch lack stable structured reason fields in this version.
    These are Studio categories, not invented native error codes. Everything
    else, including an internal error after possible acceptance, stays unknown.
    """
    if version != "0.153.4" or not isinstance(expected_turn_id, str) or not expected_turn_id:
        return None
    details = getattr(error, "details", None)
    if (getattr(error, "code", None) != "CODEX_RPC_ERROR" or not isinstance(details, dict)
            or details.get("method") != "turn/steer"):
        return None
    rpc = details.get("rpc_error")
    if not isinstance(rpc, dict):
        return None
    message, code, data = rpc.get("message"), rpc.get("code"), rpc.get("data")
    if code == -32600:
        if message == "no active turn to steer" and data is None:
            return "turn_ended"
        if (isinstance(message, str) and data is None and re.fullmatch(
                r"expected active turn id `" + re.escape(expected_turn_id) + r"` but found `[^`]+`", message)):
            return "turn_changed"
        for kind in ("review", "compact"):
            if message == f"cannot steer a {kind} turn":
                if data is None or (isinstance(data, dict) and isinstance(data.get("codexErrorInfo"), dict)
                    and data["codexErrorInfo"].get("activeTurnNotSteerable") == {"turnKind": kind}):
                    return "unsupported_turn"
        if data is None and message in {"expectedTurnId must not be empty", "input must not be empty"}:
            return "invalid_input"
    if code == -32602 and isinstance(data, dict) and data.get("input_error_code") == "input_too_large":
        limit = data.get("max_chars")
        if type(limit) is int and message == f"Input exceeds the maximum length of {limit} characters.":
            return "invalid_input"
    return None
