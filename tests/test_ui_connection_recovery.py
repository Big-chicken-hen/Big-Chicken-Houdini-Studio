"""Injected connection failures through the real transport and Composer callbacks."""
import copy
import http.client
import json
import threading
import tempfile
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

import test_ui_steer as fixtures
from scripts.preview_ui import process_until
from studio.ui import shared
from studio.http_diagnostics import HttpDiagnostics


class ConnectionRecoveryTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.ComposerSteerTest.setUpClass.__func__)
    active = fixtures.ComposerSteerTest.active
    requests = fixtures.ComposerSteerTest.requests

    def setUp(self):
        fixtures.ComposerSteerTest.setUp(self)
        self.received = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                owner.received.append((self.path, body))
                data = json.dumps(fixtures.ComposerSteerTest.response(body)).encode()
                self.send_response(200)
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *_args):
                pass

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()
        self.transport = shared.Api(f'http://127.0.0.1:{self.server.server_port}', 'test-token')
        preview_call = self.api.call

        def dispatch(method, path, body=None, **callbacks):
            if method == 'POST' and path in {'/turn', '/turn/steer'}:
                self.api.calls.append((method, path, copy.deepcopy(body)))
                return self.transport.call(method, path, body, **callbacks)
            return preview_call(method, path, body, **callbacks)

        self.api.call = dispatch

    def tearDown(self):
        self.transport.close()
        self.transport.deleteLater()
        self.server.shutdown()
        self.server.server_close()
        self.worker.join(2)
        fixtures.ComposerSteerTest.tearDown(self)

    def connect_failure(self, *, steer=False, poll_first=False, new_draft=False):
        if steer:
            self.active()
        state = copy.deepcopy(self.panel.state)
        original = '请保留这条原文\n和附件'
        attachments = [{'attachment_id': 'original.png', 'name': 'original.png',
                        'path': str(self.evidence / 'original.png'), 'status': 'ready',
                        'local_key': 'original.png'}]
        self.panel.attachments = copy.deepcopy(attachments)
        self.panel.input.setPlainText(original)
        self.panel.update_controls()
        self.assertTrue(self.panel.send_button.isEnabled())
        entered, release = threading.Event(), threading.Event()

        def fail_connect(*_args):
            entered.set()
            release.wait(2)
            error = OSError(10048, 'injected address in use')
            error.winerror = 10048
            raise error

        with patch.object(shared._CancellableSocket, 'connect', fail_connect), \
                patch.object(http.client.HTTPConnection, 'request') as write:
            self.panel.send()
            snapshot = self.panel.pending_submission
            self.assertTrue(entered.wait(1))
            if new_draft:
                self.panel.input.setPlainText('后来输入的新草稿')
            if poll_first:
                self.panel.connection_failed(shared.ApiFailure('background state read failed',
                                                               code='CONNECTION_LOST'))
            release.set()
            process_until(lambda: not self.transport._pending)
            write.assert_not_called()
        self.assertEqual(self.received, [])
        self.assertEqual(snapshot['state'], 'not_submitted')
        self.assertFalse(snapshot['forward_attempted'])
        self.assertIsNone(self.panel.pending_submission)
        self.assertFalse(self.panel.uncertain_send)
        self.assertFalse(self.panel.submitting)
        self.assertEqual(self.api.hold['/reconcile'], [])
        if new_draft:
            self.assertEqual(self.panel.input.toPlainText(), '后来输入的新草稿')
            self.assertIs(self.panel.retained_submissions[snapshot['client_user_message_id']], snapshot)
            self.assertEqual(snapshot['text'], original)
            self.assertEqual(snapshot['attachments'], attachments)
        else:
            self.assertEqual(self.panel.input.toPlainText(), original)
            self.assertEqual(self.panel.attachments, attachments)
        self.panel.apply_state(state)
        self.assertTrue(self.panel.send_button.isEnabled())
        self.assertEqual(len(self.requests()), 1)  # Recovery never resubmits.
        self.panel.send()  # Only another explicit user action may send.
        process_until(lambda: not self.transport._pending)
        self.assertEqual(len(self.received), 1)
        self.assertEqual(self.received[0][0], '/turn/steer' if steer else '/turn')

    def test_start_connect_failure_restores_draft_without_query_or_replay(self):
        self.connect_failure()

    def test_steer_connect_failure_keeps_later_draft_and_original_attachment(self):
        self.connect_failure(steer=True, new_draft=True)

    def test_poll_generation_change_does_not_swallow_original_unsent_terminal(self):
        self.connect_failure(steer=True, poll_first=True)

    def test_request_entry_failure_is_unknown_without_headers_and_never_replayed(self):
        self.active()
        self.panel.input.setPlainText('possibly written request')
        with patch.object(http.client.HTTPConnection, 'request', side_effect=OSError('write interrupted')):
            self.panel.send()
            snapshot = self.panel.pending_submission
            process_until(lambda: not self.transport._pending)
        self.assertEqual(snapshot['state'], 'unknown')
        self.assertTrue(self.panel.uncertain_send)
        self.assertIs(self.panel.pending_submission, snapshot)
        self.assertEqual(len(self.api.hold['/reconcile']), 1)
        self.assertEqual(self.api.hold['/reconcile'][0][2],
                         {'client_user_message_id': snapshot['client_user_message_id']})
        self.assertEqual(len(self.requests()), 1)
        self.assertEqual(self.received, [])

    def test_accepted_reply_after_background_failure_settles_only_original_input(self):
        self.active()
        self.panel.input.setPlainText('one actual HTTP post')
        entered, release = threading.Event(), threading.Event()
        getresponse = http.client.HTTPConnection.getresponse

        def delayed_response(connection):
            entered.set()
            release.wait(2)
            return getresponse(connection)

        with patch.object(http.client.HTTPConnection, 'getresponse', delayed_response):
            self.panel.send()
            snapshot = self.panel.pending_submission
            self.assertTrue(entered.wait(1))
            self.panel.input.setPlainText('new draft')
            self.panel.connection_failed(shared.ApiFailure('state read failed', code='CONNECTION_LOST'))
            self.panel.state['codex'].update(state='completed', stop_requested=True)
            release.set()
            process_until(lambda: not self.transport._pending)
        self.assertEqual(snapshot['state'], 'accepted')
        self.assertIsNone(self.panel.pending_submission)
        self.assertFalse(self.panel.uncertain_send)
        self.assertEqual(self.panel.state['codex']['state'], 'completed')
        self.assertEqual(self.panel.input.toPlainText(), 'new draft')
        self.assertEqual(len(self.received), 1)
        self.assertEqual(len(self.requests()), 1)

    def test_old_send_terminal_cannot_restore_into_a_changed_account(self):
        self.active()
        self.panel.input.setPlainText('original owner input')
        entered, release = threading.Event(), threading.Event()

        def delayed_failure(*_args):
            entered.set()
            release.wait(2)
            raise OSError('connect failed')

        with patch.object(shared._CancellableSocket, 'connect', delayed_failure):
            self.panel.send()
            snapshot = self.panel.pending_submission
            self.assertTrue(entered.wait(1))
            self.panel.accept_account_revision(self.panel.account_revision + 1)
            self.panel.input.setPlainText('different owner draft')
            release.set()
            process_until(lambda: not self.transport._pending)
        self.assertEqual(self.panel.input.toPlainText(), 'different owner draft')
        self.assertEqual(snapshot['state'], 'pending')
        self.assertIs(self.panel.pending_submission, snapshot)
        self.assertEqual(self.received, [])

    def test_outage_backs_off_to_one_state_probe_and_coalesces_recovery(self):
        self.api.hold['/account'] = []
        state = copy.deepcopy(self.panel.state)
        before = len(self.api.calls)
        for index in range(7):
            self.panel.connection_failed(shared.ApiFailure('offline', code='CONNECTION_LOST'))
            self.assertEqual(self.panel.poll.interval(), min(850 * 2 ** (index + 1), 20000))
            self.panel.refresh()
            self.panel.refresh_account()
        self.assertEqual(len(self.api.calls), before)
        self.panel.poll_retry_at = 0
        self.panel.refresh()
        self.assertEqual([path for _, path, _ in self.api.calls[before:]], ['/state'])
        done = self.api.hold['/state'][-1][0]
        after_probe = len(self.api.calls)
        done(state)
        self.assertEqual(self.panel.poll.interval(), 850)
        paths = [path.split('?', 1)[0] for _, path, _ in self.api.calls[after_probe:]]
        self.assertEqual(paths.count('/events'), 1)
        self.assertEqual(paths.count('/account'), 1)
        self.assertEqual(paths.count('/thread/history'), 1)
        self.assertEqual(self.requests(), [])

    def test_opt_in_diagnostic_correlates_fault_without_message_or_credentials(self):
        with tempfile.TemporaryDirectory(dir=self.evidence) as directory:
            trace = HttpDiagnostics(fixtures.Path(directory), max_bytes=8192)
            self.transport.diagnostics = trace
            trace.window_seconds = 0
            error = OSError(10048, 'test-token private-body private-attachment')
            error.winerror = 10048
            body = {'client_user_message_id': '1' * 32 + '.' + '2' * 32,
                    'text': 'private-body', 'attachments': ['private-attachment']}
            failed = []
            with patch.object(shared._CancellableSocket, 'connect', side_effect=error):
                self.transport.call('POST', '/turn/steer', body, failed=failed.append)
                process_until(lambda: bool(failed))
            trace.handler.close()
            files = list(fixtures.Path(directory).glob('panel-http-*.jsonl'))
            raw = files[0].read_text(encoding='utf-8')
            for secret in ('test-token', 'private-body', 'private-attachment', body['client_user_message_id']):
                self.assertNotIn(secret, raw)
            records = [json.loads(line) for line in raw.splitlines()]
            fault = next(row for row in records if row['kind'] == 'failure')
            self.assertEqual(fault['phase'], 'connect')
            self.assertEqual(fault['route'], '/turn/steer')
            self.assertEqual(fault['winerror'], 10048)
            self.assertEqual(fault['submission_state'], 'not_submitted')
            self.assertEqual(fault['message_hash'], shared.message_fingerprint(body))
            self.assertTrue(fault['stack'])
            self.assertEqual(failed[0].details['request_id'], fault['request_id'])
            self.assertTrue(fault['endpoint'].startswith('127.0.0.1:'))
            row = next(row for row in records if row['kind'] == 'window')['routes']['/turn/steer']
            self.assertEqual(row['inflight'], 0)
            self.assertEqual(row['started'], row['completed'])


if __name__ == '__main__':
    unittest.main()
