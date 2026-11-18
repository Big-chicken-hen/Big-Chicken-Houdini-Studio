"""Real loopback HTTP lifecycle faults; Qt carries only completed Python data."""
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import time
import unittest
from unittest.mock import patch

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from PySide6 import QtCore, QtNetwork, QtWidgets  # noqa: E402
from shiboken6 import delete, isValid  # noqa: E402
from studio.ui.shared import Api  # noqa: E402
from scripts.preview_ui import process_until  # noqa: E402


class ApiLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.calls = []
        self.slow_reply_release = threading.Event()
        self.body_read_started = threading.Event()
        owner = self
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                self.rfile.read(int(self.headers.get('Content-Length', '0')))
                self.do_GET()

            def do_GET(self):
                owner.calls.append(self.path)
                if self.path == '/delay':
                    time.sleep(.35)
                elif self.path.startswith('/same'):
                    time.sleep(.07 if self.path.endswith('one') else .35)
                elif self.path == '/alias?first':
                    owner.slow_reply_release.wait(2)
                elif self.path == '/drop':
                    self.connection.close()
                    return
                value = {'marker': self.path.split('?')[1]} if self.path.startswith('/alias?') else {'ready': True}
                data = {'/empty': b'', '/malformed': b'{', '/array': b'[]'}.get(self.path, json.dumps(value).encode())
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data) + (10 if self.path == '/truncated' else 0)))
                self.end_headers()
                try:
                    if self.path == '/blocked-body':
                        self.wfile.write(data[:1])
                        self.wfile.flush()
                        owner.body_read_started.set()
                        owner.slow_reply_release.wait(2)
                        data = data[1:]
                    self.wfile.write(data)
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    pass
            def log_message(self, *_args):
                pass
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()
        self.api = Api('http://127.0.0.1:' + str(self.server.server_port), 'local-test-token')

    def tearDown(self):
        self.slow_reply_release.set()
        self.api.close()
        if isValid(self.api):
            delete(self.api)
        self.app.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
        self.server.shutdown()
        self.server.server_close()
        self.worker.join(2)

    def test_empty_http_body_cannot_be_a_successful_empty_object(self):
        for route in ('/empty', '/malformed', '/array'):
            with self.subTest(route=route):
                done, failed = [], []
                self.api.call('GET', route, done=done.append, failed=failed.append)
                process_until(lambda: bool(done or failed))
                self.assertEqual(done, [])
                self.assertEqual(len(failed), 1)
                self.assertEqual(failed[0].submission_state, 'unknown')

    def test_duplicate_completion_is_delivered_once_after_io_cleanup(self):
        done, failed, cleaned = [], [], []
        self.api.call('GET', '/delay', done=lambda value: (cleaned.append(job.socket is None and job.finished.is_set()), done.append(value)),
                      failed=failed.append)
        request_id = next(iter(self.api._pending))
        job = self.api._pending[request_id][0]
        process_until(lambda: bool(done or failed))
        self.api._complete((request_id, {'ready': True}))
        self.assertEqual(done, [{'ready': True}])
        self.assertEqual(failed, [])
        self.assertEqual(cleaned, [True])
        self.assertEqual(self.api._pending, {})

    def test_close_interrupts_an_active_read_without_reconnect_or_callback(self):
        done, failed = [], []
        self.api.call('GET', '/blocked-body', done=done.append, failed=failed.append, unique=True)
        job = next(iter(self.api._pending.values()))[0]
        self.assertTrue(self.body_read_started.wait(1))
        self.api.close()
        self.assertTrue(job.finished.wait(1), 'Close did not interrupt the pending socket read')
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(50, loop.quit)
        loop.exec()
        self.assertEqual(done, [])
        self.assertEqual(failed, [])
        self.assertEqual(self.api.inflight, set())
        self.assertEqual(self.api._pending, {})
        self.assertEqual(self.calls, ['/blocked-body'])

    def test_overlapping_nonunique_reads_keep_unique_key_until_both_finish(self):
        done = []
        self.api.call('GET', '/same?one', done=done.append)
        self.api.call('GET', '/same?two', done=done.append)
        process_until(lambda: len(done) == 1)
        self.assertFalse(self.api.call('GET', '/same?third', done=done.append, unique=True))
        process_until(lambda: len(done) == 2)
        self.assertEqual(self.api.inflight, set())

    def test_aliased_get_result_cannot_consume_or_destroy_another_active_reply(self):
        first_done, second_done, failures = [], [], []
        first_reply = [None]
        qt_get_calls = []
        native_get = QtNetwork.QNetworkAccessManager.get

        def aliased_get(manager, request):
            qt_get_calls.append(request.url().path())
            actual = native_get(manager, request)
            if first_reply[0] is None:
                first_reply[0] = actual
            return first_reply[0]

        # Preserve the old binding-fault injection globally. The replacement
        # transport must never enter Qt Network, including on concurrent reads.
        with patch.object(QtNetwork.QNetworkAccessManager, 'get', aliased_get):
            self.api.call('GET', '/alias?first', done=first_done.append,
                          failed=lambda value: failures.append(('first', str(value))))
            first_job = next(iter(self.api._pending.values()))[0]
            self.api.call('GET', '/alias?second', done=second_done.append,
                          failed=lambda value: failures.append(('second', str(value))))
            process_until(lambda: bool(second_done or failures))
            self.assertEqual(failures, [])
            self.assertEqual(second_done, [{'marker': 'second'}])
            self.assertEqual(first_done, [])
            self.assertFalse(first_job.finished.is_set())
            self.assertIsNotNone(first_job.socket)
            self.slow_reply_release.set()
            process_until(lambda: bool(first_done or failures))
        self.assertEqual(first_done, [{'marker': 'first'}])
        self.assertEqual(second_done, [{'marker': 'second'}])
        self.assertEqual(failures, [])
        self.assertEqual(self.calls.count('/alias?first'), 1)
        self.assertEqual(self.calls.count('/alias?second'), 1)
        self.assertEqual(qt_get_calls, [])
        self.assertEqual(self.api.inflight, set())
        self.assertEqual(self.api._pending, {})

    def test_disconnect_is_unknown_without_replay_and_invalid_routes_never_send(self):
        for route in ('/drop', '/truncated'):
            with self.subTest(route=route):
                done, failed = [], []
                self.api.call('POST', route, {'message': 'send once'}, done=done.append, failed=failed.append)
                process_until(lambda: bool(done or failed))
                self.assertEqual(done, [])
                self.assertEqual(len(failed), 1)
                self.assertEqual(failed[0].submission_state, 'unknown')
                self.assertEqual(self.calls.count(route), 1)
        before = list(self.calls)
        for route in ('http://127.0.0.1:1/', '//127.0.0.1:1/', '/ok#fragment'):
            rejected = []
            self.api.call('GET', route, failed=rejected.append)
            process_until(lambda: bool(rejected))
            self.assertEqual(rejected[0].submission_state, 'not_submitted')
        self.assertEqual(self.calls, before)

    def test_stop_does_not_wait_for_the_ordinary_http_worker(self):
        pool = QtCore.QThreadPool.globalInstance()
        previous_limit = pool.maxThreadCount()
        pending_done, stop_done, failed = [], [], []
        pool.setMaxThreadCount(1)
        try:
            self.api.call('POST', '/blocked-body', {'message': 'pending input'},
                          done=pending_done.append, failed=failed.append)
            self.assertTrue(self.body_read_started.wait(1))
            self.api.call('POST', '/stop', {}, done=stop_done.append, failed=failed.append)
            process_until(lambda: bool(stop_done or failed), timeout=1000)
            self.assertEqual(stop_done, [{'ready': True}])
            self.assertEqual(pending_done, [])
            self.assertEqual(failed, [])
            self.assertEqual(self.calls.count('/blocked-body'), 1)
            self.assertEqual(self.calls.count('/stop'), 1)
        finally:
            self.slow_reply_release.set()
            pool.setMaxThreadCount(previous_limit)
        process_until(lambda: bool(pending_done or failed))
        self.assertEqual(pending_done, [{'ready': True}])
        self.assertEqual(failed, [])
