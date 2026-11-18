"""Pinned schema and precise error classification; not a real model acceptance."""
import json
from pathlib import Path
import unittest

from studio.codex.errors import CodexRPCError
from studio.codex.protocol import ProtocolPolicy, steer_rejection_reason


class NativeSteerContractTests(unittest.TestCase):
    def test_consumed_pinned_contract_exposes_identity_without_turn_overrides(self):
        root = Path(__file__).resolve().parents[1]
        contract = json.loads((root/'contracts/codex/0.153.4/integration.json').read_text(encoding='utf-8'))
        self.assertEqual(contract['codex_version'], ProtocolPolicy().version)
        ProtocolPolicy().require_client_request('turn/steer')
        steer = contract['requests']['TurnSteerParams']
        self.assertEqual(set(steer['properties']), {'threadId', 'expectedTurnId', 'clientUserMessageId', 'input'})
        self.assertEqual(set(steer['required']), {'threadId', 'expectedTurnId', 'input'})
        self.assertIn('clientUserMessageId', contract['requests']['TurnStartParams']['properties'])
        self.assertIn('clientId', contract['response_definitions']['UserMessage']['properties'])
        self.assertEqual(contract['response_definitions']['TurnSteerResponse']['required'], ['turnId'])

    def rejection(self, message, code=-32600, data=None, method='turn/steer'):
        return CodexRPCError(method, {'code': code, 'message': message, 'data': data})

    def test_no_active_and_exact_expected_target_are_not_submitted(self):
        self.assertEqual(steer_rejection_reason(self.rejection('no active turn to steer'), 'T'), 'turn_ended')
        mismatch = self.rejection('expected active turn id `T` but found `U`')
        self.assertEqual(steer_rejection_reason(mismatch, 'T'), 'turn_changed')
        self.assertIsNone(steer_rejection_reason(mismatch, 'another-turn'))
        self.assertIsNone(steer_rejection_reason(mismatch, 'T', version='0.154.0'))

    def test_special_turn_data_is_versioned_and_cannot_contradict_message(self):
        for kind in ('review', 'compact'):
            data = {'message': f'cannot steer a {kind} turn', 'additionalDetails': None,
                    'codexErrorInfo': {'activeTurnNotSteerable': {'turnKind': kind}}}
            error = self.rejection(f'cannot steer a {kind} turn', data=data)
            self.assertEqual(steer_rejection_reason(error, 'T'), 'unsupported_turn')
            # Native serialization fallback is documented in the pinned source.
            self.assertEqual(steer_rejection_reason(self.rejection(error.message), 'T'), 'unsupported_turn')
            data['codexErrorInfo']['activeTurnNotSteerable']['turnKind'] = 'unknown-kind'
            self.assertIsNone(steer_rejection_reason(error, 'T'))

    def test_generic_rpc_transport_errors_never_become_definite_rejection(self):
        for error in (self.rejection('no active turn to steer', code=-32603),
                      self.rejection('failed to steer turn: controlled'),
                      self.rejection('no active turn to steer', method='turn/start'),
                      self.rejection('expected active turn id `T` but found `U` trailing text')):
            self.assertIsNone(steer_rejection_reason(error, 'T'))

    def test_only_proven_input_refusals_are_classified(self):
        self.assertEqual(steer_rejection_reason(self.rejection('input must not be empty'), 'T'), 'invalid_input')
        error = self.rejection('Input exceeds the maximum length of 100 characters.', -32602,
                               {'input_error_code': 'input_too_large', 'max_chars': 100, 'actual_chars': 101})
        self.assertEqual(steer_rejection_reason(error, 'T'), 'invalid_input')
        self.assertIsNone(steer_rejection_reason(self.rejection(error.message, -32602), 'T'))


if __name__ == '__main__':
    unittest.main()
