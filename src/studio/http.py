"""Authenticated loopback JSON; no credentials in URLs or request logs."""
from __future__ import annotations

import hmac
import http.client
import json
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .common import StudioError, encoded

MAX_BODY = 2 * 1024 * 1024


def redact(value, token):
    if isinstance(value, str):
        return value.replace(token, "[REDACTED]") if token else value
    if isinstance(value, dict):
        return {redact(str(k), token): redact(v, token) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v, token) for v in value]
    return value


class BoundedHTTPServer(ThreadingHTTPServer):
    request_queue_size = 16
    daemon_threads = True

    def __init__(self, *args, **kwargs):
        self.slots = threading.BoundedSemaphore(32)
        super().__init__(*args, **kwargs)

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()

    def handle_error(self, request, client_address):
        pass  # Never emit raw request/exception data into service logs.


def loopback_url(url):
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "http" or parts.hostname != "127.0.0.1" or not parts.port or parts.username or parts.password:
        raise StudioError("INVALID_ENDPOINT", "Only an authenticated 127.0.0.1 HTTP endpoint is supported")
    return url.rstrip("/")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise StudioError("REDIRECT_REJECTED", "Authenticated requests cannot follow redirects")


class Client:
    def __init__(self, url, token, timeout=3):
        self.url, self.token, self.timeout = loopback_url(url), token, timeout
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def call(self, method, path, payload=None, timeout=None):
        if not path.startswith("/") or path.startswith("//"):
            raise StudioError("INVALID_ROUTE", "Routes must be relative to the local service")
        request = urllib.request.Request(self.url + path,
                                         data=encoded(payload).encode() if payload is not None else None,
                                         headers={"Authorization": "Bearer " + self.token,
                                                  "Content-Type": "application/json"}, method=method)
        try:
            with self.opener.open(request, timeout=timeout or self.timeout) as response:
                raw = response.read(18 * 1024 * 1024 + 1)
                if len(raw) > 18 * 1024 * 1024:
                    raise StudioError("RESPONSE_LIMIT", "Response exceeds transport limit", 502)
                return json.loads(raw)
        except urllib.error.HTTPError as exc:
            try:
                try:
                    error = json.loads(exc.read(MAX_BODY)).get("error", {})
                except (ValueError, AttributeError, http.client.HTTPException):
                    error = {}
            finally:
                exc.close()
            raise StudioError(error.get("code", "HTTP_ERROR"), redact(error.get("message", "Local service rejected the request"), self.token), exc.code) from exc
        except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException, ValueError) as exc:
            raise StudioError("CONNECTION_LOST", "Local service did not confirm the request", 503) from exc


def serve(router, token, port=0):
    if not isinstance(token, str) or len(token) < 32:
        raise ValueError("A fresh session token of at least 32 characters is required")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            self.handle_request("GET")

        def do_POST(self):
            self.handle_request("POST")

        def handle_request(self, method):
            status = 200
            try:
                self.connection.settimeout(8)
                if not hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + token):
                    raise StudioError("UNAUTHORIZED", "Session authentication is required", 401)
                # Cross-origin browser requests must not be able to drive local scene writes.
                if self.headers.get("Origin") or self.headers.get("Transfer-Encoding"):
                    raise StudioError("REQUEST_REJECTED", "Cross-origin and chunked requests are not supported", 403)
                host = self.headers.get("Host", "")
                if host != "127.0.0.1:" + str(self.server.server_port):
                    raise StudioError("INVALID_HOST", "Unexpected Host header", 403)
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 <= length <= MAX_BODY:
                    raise StudioError("REQUEST_LIMIT", "Request body exceeds 2 MB", 413)
                if method == "POST" and "application/json" not in self.headers.get("Content-Type", ""):
                    raise StudioError("CONTENT_TYPE", "POST requires application/json", 415)
                raw = self.rfile.read(length) if length else b"{}"
                body = json.loads(raw, parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON")))
                if not isinstance(body, dict):
                    raise StudioError("INVALID_BODY", "A JSON object is required")
                parts = urllib.parse.urlsplit(self.path)
                value = router(method, parts.path, urllib.parse.parse_qs(parts.query), body)
            except StudioError as exc:
                status, value = exc.status, exc.payload()
            except (ValueError, TypeError, KeyError):
                status, value = 400, {"error": {"code": "INVALID_REQUEST", "message": "Invalid request arguments"}}
            except Exception:
                status, value = 500, {"error": {"code": "SERVICE_ERROR", "message": "Local service could not complete this request"}}
            try:
                raw = encoded(redact(value, token)).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
            except (BrokenPipeError, ConnectionError, OSError):
                pass  # Receipts were already persisted. The caller can query them by ID.

    server = BoundedHTTPServer(("127.0.0.1", port), Handler)
    thread = threading.Thread(target=server.serve_forever, name="studio-loopback", daemon=True)
    thread.start()
    return server
