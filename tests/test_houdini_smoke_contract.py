"""Offline checks of the smoke harness; deliberately not a real-Houdini result."""
import json
import unittest
from studio.common import StudioError
from studio.houdini_smoke import DiscardAdmissionResponse, example_batch, tool_value, wire_call


class SmokeContractTests(unittest.TestCase):
    def test_owned_script_compiles_and_never_replaces_a_hip(self):
        source = example_batch('/obj/bcs_smoke_abc123')
        compile(source, '<smoke fixture>', 'exec')
        for forbidden in ('hipFile.clear', 'hipFile.load', 'hipFile.save'):
            self.assertNotIn(forbidden, source)
        with self.assertRaises(ValueError):
            example_batch('/obj/user_asset')

    def test_mcp_envelope_and_receipt_decoding(self):
        message = wire_call(3, 'hia_context', {})
        self.assertEqual(message['params']['name'], 'hia_context')
        value = {'operation_id': 'one', 'state': 'finished'}
        self.assertEqual(tool_value({'result': {'content': [{'type': 'text', 'text': json.dumps(value)}]}}), value)

    def test_fault_discards_response_after_exactly_one_real_client_submission(self):
        class Client:
            def __init__(self):
                self.calls = []
            def call(self, method, path, payload=None):
                self.calls.append((method, path, payload))
                return {'operation_id': 'one', 'state': 'queued'}
        client = Client()
        fault = DiscardAdmissionResponse(client)
        with self.assertRaises(StudioError):
            fault.call('POST', '/operations', {'kind': 'execute'})
        receipt = fault.call('GET', '/operations/one')
        self.assertEqual(receipt['operation_id'], 'one')
        self.assertEqual([v[0] for v in client.calls], ['POST', 'GET'])
