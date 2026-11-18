"""Controlled stdio faults only; no Codex model or Houdini calls."""
import json
from pathlib import Path
import threading
import unittest
from unittest.mock import patch

from studio.codex.client import CodexStdioClient, _MAX_TRACKED_REQUESTS
from studio.codex.errors import BridgeError, CodexRPCError
from studio.codex.protocol import ProtocolPolicy


class InputPipe:
    def __init__(self):
        self.frames = []
        self.on_write = None
        self.fail_flush = False

    def write(self, text):
        self.frames.append(text)
        if self.on_write:
            self.on_write(json.loads(text))
        return len(text)

    def flush(self):
        if self.fail_flush:
            raise BrokenPipeError('controlled response loss')


class Process:
    def __init__(self):
        self.stdin = InputPipe()

    def poll(self):
        return None


class TrackedRequestsTests(unittest.TestCase):
    def setUp(self):
        self.client = CodexStdioClient(['unused'], cwd=Path.cwd(), environment={},
                                       policy=ProtocolPolicy(), request_timeout=0.005)
        self.process = self.client._process = Process()
        self.results = []

    def callback(self, ticket, result, error):
        # Also covers a reply delivered synchronously inside the fake write().
        for lock in (self.client._pending_lock, self.client._write_lock):
            self.assertTrue(lock.acquire(blocking=False), 'callback held a client transport lock')
            lock.release()
        self.results.append((ticket.request_id, result, error))

    def ticket(self, text='same words', method='turn/steer'):
        return self.client.prepare_tracked_request(method, {
            'threadId': 'thread-A', 'expectedTurnId': 'turn-T',
            'clientUserMessageId': 'message-' + str(len(self.process.stdin.frames)),
            'input': [{'type': 'text', 'text': text}],
        }, self.callback)

    def test_lost_ack_is_retained_and_late_exact_rpc_settles_once(self):
        ticket = self.ticket()
        self.client.send_prepared(ticket)
        with self.assertRaisesRegex(BridgeError, 'CODEX_REQUEST_TIMEOUT'):
            self.client.wait_prepared(ticket)
        self.assertFalse(ticket.settled)
        self.assertIn(ticket.request_id, self.client._tracked)
        reply = {'id': ticket.request_id, 'result': {'turnId': 'turn-T'}}
        self.client._handle_response(reply)
        self.client._handle_response({'id': ticket.request_id, 'error': {'code': -32603, 'message': 'late'}})
        self.assertEqual(self.client.wait_prepared(ticket), {'turnId': 'turn-T'})
        self.assertEqual(len(self.results), 1)
        self.assertEqual(ticket._frame, '')
        with self.assertRaisesRegex(BridgeError, 'CODEX_SEND_ALREADY_ATTEMPTED'):
            self.client.send_prepared(ticket)
        self.assertEqual(len(self.process.stdin.frames), 1)

    def test_success_during_write_delivers_outside_locks_and_freezes_input(self):
        params = {'threadId': 'thread-A', 'input': [{'type': 'text', 'text': 'original'}]}
        ticket = self.client.prepare_tracked_request('turn/start', params, self.callback)
        params['input'][0]['text'] = 'later draft'
        self.process.stdin.on_write = lambda frame: self.client._handle_response(
            {'id': frame['id'], 'result': {'turn': {'id': 'T'}}})
        self.client.send_prepared(ticket)
        self.assertEqual(self.client.wait_prepared(ticket), {'turn': {'id': 'T'}})
        self.assertEqual(len(self.results), 1)
        self.assertEqual(json.loads(self.process.stdin.frames[0])['params']['input'][0]['text'], 'original')

    def test_write_failure_is_attempted_and_cannot_be_replayed(self):
        self.process.stdin.fail_flush = True
        ticket = self.ticket()
        with self.assertRaisesRegex(BridgeError, 'CODEX_STDIN_FAILED'):
            self.client.send_prepared(ticket)
        self.assertTrue(ticket.forward_attempted)
        self.assertFalse(ticket.settled)
        self.assertEqual(len(self.results), 1)
        with self.assertRaisesRegex(BridgeError, 'CODEX_STDIN_FAILED'):
            self.client.wait_prepared(ticket)
        with self.assertRaisesRegex(BridgeError, 'CODEX_SEND_ALREADY_ATTEMPTED'):
            self.client.send_prepared(ticket)
        self.assertEqual(len(self.process.stdin.frames), 1)
        self.client._handle_response({'id': ticket.request_id, 'result': {'turnId': 'turn-T'}})
        self.assertEqual(self.client.wait_prepared(ticket), {'turnId': 'turn-T'})
        self.assertEqual(len(self.results), 2)  # Unknown transport notice, then original native ACK.

    def test_native_ack_observed_before_flush_error_keeps_acceptance(self):
        self.process.stdin.fail_flush = True
        self.process.stdin.on_write = lambda frame: self.client._handle_response(
            {'id': frame['id'], 'result': {'turnId': 'turn-T'}})
        ticket = self.ticket()
        self.client.send_prepared(ticket)
        self.assertEqual(self.client.wait_prepared(ticket), {'turnId': 'turn-T'})
        self.assertEqual(len(self.results), 1)
        self.assertIsNone(ticket.error)

    def test_replacement_process_and_discard_do_not_forward(self):
        ticket = self.ticket()
        replacement = self.client._process = Process()
        with self.assertRaisesRegex(BridgeError, 'CODEX_NOT_RUNNING'):
            self.client.send_prepared(ticket)
        self.assertFalse(ticket.forward_attempted)
        self.assertFalse(replacement.stdin.frames)
        self.assertFalse(self.process.stdin.frames)
        discarded = self.ticket()
        self.client.discard_prepared(discarded)
        self.assertFalse(discarded.forward_attempted)
        self.assertTrue(discarded.settled)
        self.assertEqual(discarded.error.code, 'CODEX_SEND_DISCARDED')

    def test_capacity_refuses_new_frame_and_expiry_reports_original_unknown(self):
        tickets = [self.ticket() for _ in range(_MAX_TRACKED_REQUESTS)]
        with self.assertRaisesRegex(BridgeError, 'CODEX_SEND_CAPACITY'):
            self.ticket()
        self.assertEqual(len(self.client._tracked), _MAX_TRACKED_REQUESTS)
        ticket = tickets[0]
        self.client.send_prepared(ticket)
        self.client.discard_prepared(tickets[1])
        replacement = self.ticket()
        self.assertGreater(replacement.request_id, tickets[-1].request_id)
        with patch('studio.codex.client.time.monotonic', return_value=ticket._expires_at + 1):
            self.client._expire_tracked()
        self.assertTrue(ticket.forward_attempted)
        self.assertEqual(ticket.error.code, 'CODEX_RESPONSE_TRACKING_EXPIRED')
        self.assertEqual(len(self.process.stdin.frames), 1)
        self.assertFalse(self.client._tracked)

    def test_same_text_different_ids_produces_three_ordered_original_sends(self):
        for _ in range(3):
            ticket = self.ticket()
            self.client.send_prepared(ticket)
            self.client._handle_response({'id': ticket.request_id, 'result': {'turnId': 'turn-T'}})
            self.client.wait_prepared(ticket)
        frames = [json.loads(frame) for frame in self.process.stdin.frames]
        self.assertEqual([frame['params']['clientUserMessageId'] for frame in frames],
                         ['message-0', 'message-1', 'message-2'])
        self.assertEqual([frame['params']['expectedTurnId'] for frame in frames], ['turn-T'] * 3)
        self.assertEqual(len(self.results), 3)

    def test_exact_item_confirmation_releases_capacity_and_waiter_without_fabricating_ack(self):
        tickets = []
        for _ in range(_MAX_TRACKED_REQUESTS + 2):
            ticket = self.ticket()
            tickets.append(ticket)
            self.client.send_prepared(ticket)
            self.assertTrue(self.client.retire_confirmed(ticket))
            self.assertTrue(ticket.event.is_set())
            self.assertFalse(self.client._tracked)
            with self.assertRaisesRegex(BridgeError, 'CODEX_REQUEST_EXTERNALLY_CONFIRMED'):
                self.client.wait_prepared(ticket)
            self.assertIsNone(ticket.result)
            self.assertEqual(self.results, [])  # Native item is the caller's fact, not an RPC result.
        for ticket in tickets:
            self.client._handle_response({'id': ticket.request_id, 'result': {'turnId': 'turn-T'}})
            self.assertEqual(ticket.error.code, 'CODEX_REQUEST_EXTERNALLY_CONFIRMED')
        self.assertEqual(self.results, [])
        self.assertEqual(len(self.process.stdin.frames), _MAX_TRACKED_REQUESTS + 2)
        with self.assertRaisesRegex(BridgeError, 'CODEX_SEND_ALREADY_ATTEMPTED'):
            self.client.send_prepared(tickets[0])

    def test_confirmation_cannot_retire_unforwarded_or_overwrite_actual_rpc_result(self):
        ticket = self.ticket()
        with self.assertRaisesRegex(BridgeError, 'CODEX_SEND_NOT_ATTEMPTED'):
            self.client.retire_confirmed(ticket)
        self.assertIn(ticket.request_id, self.client._tracked)
        self.client.send_prepared(ticket)
        self.client._handle_response({'id': ticket.request_id, 'result': {'turnId': 'turn-T'}})
        self.assertFalse(self.client.retire_confirmed(ticket))
        self.assertEqual(self.client.wait_prepared(ticket), {'turnId': 'turn-T'})
        self.assertEqual(len(self.results), 1)

    def test_concurrent_responses_and_process_failure_cannot_overwrite_terminal(self):
        ticket = self.ticket()
        self.client.send_prepared(ticket)
        barrier = threading.Barrier(3)

        def respond(value):
            barrier.wait()
            self.client._handle_response({'id': ticket.request_id, 'result': {'turnId': value}})

        workers = [threading.Thread(target=respond, args=(value,)) for value in ('T', 'duplicate')]
        for worker in workers:
            worker.start()
        barrier.wait()
        for worker in workers:
            worker.join(timeout=2)
            self.assertFalse(worker.is_alive())
        first = ticket.result
        self.client._fail_pending(BridgeError('CODEX_PROCESS_EXITED', 'controlled exit'))
        self.assertIs(ticket.result, first)
        self.assertEqual(len(self.results), 1)

    def test_rpc_rejection_and_process_exit_remain_distinct(self):
        rejected = self.ticket()
        self.client.send_prepared(rejected)
        self.client._handle_response({'id': rejected.request_id, 'error': {
            'code': -32600, 'message': 'no active turn to steer', 'data': None}})
        with self.assertRaises(CodexRPCError):
            self.client.wait_prepared(rejected)
        unknown = self.ticket()
        self.client.send_prepared(unknown)
        self.client._fail_pending(BridgeError('CODEX_PROCESS_EXITED', 'controlled exit'))
        self.assertTrue(unknown.forward_attempted)
        self.assertFalse(unknown.settled)
        self.assertEqual(unknown.error.code, 'CODEX_PROCESS_EXITED')
        self.client._handle_response({'id': unknown.request_id, 'result': {'turnId': 'turn-T'}})
        self.assertIsNone(unknown.error)
        self.assertEqual(len(self.results), 3)


if __name__ == '__main__':
    unittest.main()
