"""Versioned integration surface, independent of the historical HIA contracts."""
from dataclasses import dataclass

from .errors import ProtocolRejected

SUPPORTED_CODEX_VERSION = "0.153.4"


@dataclass(frozen=True)
class ProtocolPolicy:
    version: str = SUPPORTED_CODEX_VERSION
    client_requests: frozenset = frozenset({
        "initialize", "thread/start", "thread/resume", "thread/list", "thread/read",
        "turn/start", "turn/interrupt", "model/list", "account/read", "account/login/start",
        "account/login/cancel", "account/rateLimits/read"})
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
