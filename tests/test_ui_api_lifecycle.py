"""Real Qt HTTP lifecycle faults; no Houdini, account or model access."""
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import time
import unittest

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from PySide6 import QtCore, QtWidgets  # noqa: E402
from shiboken6 import delete, isValid  # noqa: E402
from studio.ui.shared import Api  # noqa: E402
from scripts.preview_ui import process_until  # noqa: E402


class ApiLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.calls = []
        owner = self
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                owner.calls.append(self.path)
                if self.path == '/delay':
                    time.sleep(.35)
                elif self.path.startswith('/same'):
                    time.sleep(.07 if self.path.endswith('one') else .35)
                data = b'' if self.path == '/empty' else json.dumps({'ready': True}).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                try:
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
        self.api.close()
        if isValid(self.api):
            delete(self.api)
        self.app.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
        self.server.shutdown()
        self.server.server_close()
        self.worker.join(2)

    def test_empty_http_body_cannot_be_a_successful_empty_object(self):
        done, failed = [], []
        self.api.call('GET', '/empty', done=done.append, failed=failed.append)
        process_until(lambda: bool(done or failed))
        self.assertEqual(done, [])
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0].submission_state, 'unknown')

    def test_duplicate_finished_is_delivered_once_after_native_signal(self):
        done, failed, markers = [], [], []
        self.api.call('GET', '/ok', done=lambda value: (markers.append('delivery'), done.append(value)),
                      failed=failed.append)
        reply = next(iter(self.api.replies))
        def native_finished():
            markers.append('native-finished')
            if markers.count('native-finished') == 1:
                reply.finished.emit()
        reply.finished.connect(native_finished)
        process_until(lambda: bool(done or failed))
        self.assertEqual(done, [{'ready': True}])
        self.assertEqual(failed, [])
        self.assertEqual(markers[-1], 'delivery')
        self.assertEqual(markers.count('delivery'), 1)

    def test_unexpected_destroy_without_finished_releases_request_once(self):
        done, failed = [], []
        self.api.call('GET', '/delay', done=done.append, failed=failed.append, unique=True)
        reply = next(iter(self.api.replies))
        delete(reply)
        # A bounded Qt loop admits the destroyed notification without waiting
        # for the server's delayed response or synthesizing another request.
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(50, loop.quit)
        loop.exec()
        self.assertEqual(done, [])
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0].code, 'REPLY_UNAVAILABLE')
        self.assertEqual(self.api.inflight, set())
        self.assertEqual(self.api.replies, set())

    def test_overlapping_nonunique_reads_keep_unique_key_until_both_finish(self):
        done = []
        self.api.call('GET', '/same?one', done=done.append)
        self.api.call('GET', '/same?two', done=done.append)
        process_until(lambda: len(done) == 1)
        self.assertFalse(self.api.call('GET', '/same?third', done=done.append, unique=True))
        process_until(lambda: len(done) == 2)
        self.assertEqual(self.api.inflight, set())
