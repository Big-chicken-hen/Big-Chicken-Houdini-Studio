"""Native exception handling must preserve Codex errors and their HTTP fields."""
from contextlib import contextmanager
import unittest

from studio.codex.errors import BridgeError, CodexRPCError, ProtocolRejected


@contextmanager
def boundary():
    yield


class CodexErrorTests(unittest.TestCase):
    def test_contextmanager_preserves_original_error_and_traceback(self):
        for error in (BridgeError("CODEX_REQUEST_TIMEOUT", "timeout", 504, {"method": "turn/start"}),
                      CodexRPCError("turn/start", {"message": "rejected"}),
                      ProtocolRejected("unknown", "request")):
            with self.subTest(error=type(error).__name__):
                expected = error.to_dict()
                try:
                    with boundary():
                        raise error
                except BridgeError as caught:
                    self.assertIs(caught, error)
                    self.assertIsNotNone(caught.__traceback__)
                    caught.__traceback__ = None
                    self.assertEqual(caught.to_dict(), expected)
                else:
                    self.fail("The original exception was swallowed")

    def test_unittest_and_chained_error_keep_structured_fields(self):
        original = TimeoutError("transport timeout")
        error = BridgeError("CODEX_REQUEST_TIMEOUT", "Request timed out", 504, {"method": "turn/start"})
        with self.assertRaises(BridgeError) as caught:
            with boundary():
                raise error from original
        self.assertIs(caught.exception, error)
        self.assertIs(error.__cause__, original)
        self.assertEqual(error.http_status, 504)
        self.assertEqual(error.to_dict(), {"ok": False, "structured_error": {
            "code": "CODEX_REQUEST_TIMEOUT", "message": "Request timed out", "details": {"method": "turn/start"}}})
