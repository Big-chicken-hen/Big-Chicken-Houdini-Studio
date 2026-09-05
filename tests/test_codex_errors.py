"""Exceptions must retain their identity across native Python error handling."""
from contextlib import contextmanager
import unittest

from studio.codex.errors import BridgeError, CodexRPCError, ProtocolRejected


@contextmanager
def boundary():
    yield


class CodexErrorTests(unittest.TestCase):
    def test_traceback_is_mutable_and_contextmanager_preserves_original_error(self):
        for error in (BridgeError("CODEX_REQUEST_TIMEOUT", "timeout", 504),
                      CodexRPCError("turn/start", {"message": "rejected"}),
                      ProtocolRejected("unknown", "request")):
            with self.subTest(type=type(error).__name__):
                try:
                    with boundary():
                        raise error
                except BridgeError as caught:
                    self.assertIs(caught, error)
                    self.assertIsNotNone(caught.__traceback__)
                    caught.__traceback__ = None
                    self.assertEqual(caught.to_dict()["structured_error"]["code"], caught.code)
                else:
                    self.fail("The original exception was swallowed")
