"""Internal clients stay direct; fixtures never change Clash or global settings."""
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import socket
import threading
import unittest
from unittest.mock import patch

from studio.http import Client, serve


class ProxyFixture(unittest.TestCase):
    def setUp(self):
        self.proxy_calls, self.direct_calls = [], []
        owner = self
        class Proxy(BaseHTTPRequestHandler):
            def do_GET(self):
                owner.proxy_calls.append(True)  # Never retain headers/token.
                self.send_error(502)
            do_POST = do_GET
            def log_message(self, *_args):
                pass
        self.proxy = ThreadingHTTPServer(('127.0.0.1', 0), Proxy)
        self.proxy_thread = threading.Thread(target=self.proxy.serve_forever, daemon=True)
        self.proxy_thread.start()
        self.token = 'isolated-proxy-fixture-token-' * 2
        def route(method, path, _query, body):
            self.direct_calls.append((method, path))
            return {'received': body.get('marker')}
        self.server = serve(route, self.token)
        self.url = 'http://127.0.0.1:' + str(self.server.server_port)
        self.closed_proxy = socket.socket()
        self.closed_proxy.bind(('127.0.0.1', 0))  # Reserved, deliberately not listening.

    def tearDown(self):
        self.closed_proxy.close()
        for server in (self.proxy, self.server):
            server.shutdown()
            server.server_close()
        self.proxy_thread.join(2)

    def environments(self):
        base = {key: value for key, value in os.environ.items()
                if key.lower() not in {'http_proxy', 'https_proxy', 'all_proxy', 'no_proxy'}}
        yield 'absent_in_test_worker', base
        for name, port in (('configured_test_proxy', self.proxy.server_port),
                           ('unavailable_test_proxy', self.closed_proxy.getsockname()[1])):
            values = {'HTTP_PROXY': f'http://127.0.0.1:{port}', 'HTTPS_PROXY': f'http://127.0.0.1:{port}',
                      'ALL_PROXY': f'http://127.0.0.1:{port}', 'NO_PROXY': ''}
            yield name, {**base, **values, **{key.lower(): value for key, value in values.items()}}


class LoopbackProxyTests(ProxyFixture):
    def test_runtime_client_ignores_case_varied_proxy_environment_without_exceptions(self):
        for name, environment in self.environments():
            with self.subTest(name=name), patch.dict(os.environ, environment, clear=True):
                result = Client(self.url, self.token, timeout=1).call('POST', '/fixture', {'marker': name})
                self.assertEqual(result, {'received': name})
        self.assertEqual(self.proxy_calls, [])
        self.assertEqual(self.direct_calls, [('POST', '/fixture')] * 3)
