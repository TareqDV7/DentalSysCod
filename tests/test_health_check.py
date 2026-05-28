"""Tests for window.health_check.wait_for_service.

The helper polls a healthz URL with retry-with-backoff until either it
gets a 200 response or the budget runs out. Returns True/False — never
raises."""

import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from window.health_check import wait_for_service


def _start_server(handler_cls):
    """Spin up an HTTP server on a random port. Returns (port, stop_fn)."""
    srv = HTTPServer(('127.0.0.1', 0), handler_cls)
    port = srv.server_port
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()

    def stop():
        srv.shutdown()
        srv.server_close()
    return port, stop


def test_returns_true_when_endpoint_is_healthy_immediately():
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')
        def log_message(self, *a, **kw):
            pass
    port, stop = _start_server(H)
    try:
        assert wait_for_service(f'http://127.0.0.1:{port}/healthz', timeout=2.0) is True
    finally:
        stop()


def test_returns_false_when_endpoint_never_responds():
    # Port that nothing is listening on. We pick a random high port and don't
    # bind it; the connection will be refused immediately on every attempt.
    import socket
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()
    start = time.monotonic()
    result = wait_for_service(f'http://127.0.0.1:{port}/healthz', timeout=1.0)
    elapsed = time.monotonic() - start
    assert result is False
    assert 0.9 <= elapsed <= 1.5, f'should respect the timeout, took {elapsed}s'


def test_returns_true_when_endpoint_becomes_healthy_mid_poll():
    """First N requests return 503, subsequent ones return 200. Helper should
    keep polling and return True once 200 lands."""
    state = {'ok_after': time.monotonic() + 0.5}

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            if time.monotonic() < state['ok_after']:
                self.send_response(503)
            else:
                self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{}')
        def log_message(self, *a, **kw):
            pass

    port, stop = _start_server(H)
    try:
        assert wait_for_service(f'http://127.0.0.1:{port}/healthz', timeout=2.0) is True
    finally:
        stop()


def test_does_not_raise_on_invalid_url():
    assert wait_for_service('http://nonexistent-host-12345.invalid/x', timeout=0.5) is False
