"""Local server's client for the cloud email relay (POST /api/relay/email,
added in Task 4 — see tests/test_email_relay_cloud.py for the cloud-side
contract). `send_system_email` wraps `_cloud_http_request` +
`_cloud_sync_config` (both already used by the cloud-sync worker; see
tests/test_cloud_sync_worker.py for the same monkeypatch pattern) and maps
the relay's HTTP outcomes onto a small (ok, reason) contract so callers
(invites, OTP, recovery-code alerts) never have to touch urllib directly.
`send_system_email_async` is the fire-and-forget wrapper used for alerts that
must never block the request that triggered them.
"""
import logging
import threading
import urllib.error

import pytest

import dental_clinic


def _paired(monkeypatch, url='https://cloud.example.test', token='tok-123'):
    monkeypatch.setattr(dental_clinic, '_cloud_sync_config', lambda: (url, token, 60))


def _unpaired(monkeypatch):
    monkeypatch.setattr(dental_clinic, '_cloud_sync_config', lambda: (None, None, 60))


def _fake_http(status, resp_body=None):
    """Build a fake `_cloud_http_request` returning (status, resp_body) for
    every call, and a `calls` list recording each call's actual arguments —
    kept as separate names so the configured response body is never
    shadowed by the request body the caller sends."""
    calls = []

    def fake(method, url, headers=None, body=None, timeout=None, **_kw):
        calls.append({'method': method, 'url': url, 'headers': headers,
                      'body': body, 'timeout': timeout})
        return status, (resp_body if resp_body is not None else {})
    return fake, calls


def test_send_system_email_success_returns_true_empty_reason(monkeypatch):
    _paired(monkeypatch)
    fake, calls = _fake_http(200, {'sent': True})
    monkeypatch.setattr(dental_clinic, '_cloud_http_request', fake)

    ok, reason = dental_clinic.send_system_email(
        'a@b.c', 'password_reset', {'clinic_name': 'X', 'code': '123456'}, lang='ar')

    assert (ok, reason) == (True, '')
    assert len(calls) == 1
    call = calls[0]
    assert call['method'] == 'POST'
    assert call['url'] == 'https://cloud.example.test/api/relay/email'
    assert call['headers']['X-Clinic-Token'] == 'tok-123'


def test_send_system_email_not_paired_when_no_cloud_config(monkeypatch):
    _unpaired(monkeypatch)
    calls = []
    monkeypatch.setattr(dental_clinic, '_cloud_http_request',
                        lambda *a, **k: calls.append((a, k)) or (200, {'sent': True}))

    ok, reason = dental_clinic.send_system_email('a@b.c', 'password_reset', {})

    assert (ok, reason) == (False, 'not_paired')
    assert not calls, 'must not attempt an HTTP call when unpaired'


def test_send_system_email_unreachable_on_network_exception(monkeypatch):
    _paired(monkeypatch)

    def raising(*a, **k):
        raise urllib.error.URLError('no route to host')
    monkeypatch.setattr(dental_clinic, '_cloud_http_request', raising)

    ok, reason = dental_clinic.send_system_email('a@b.c', 'password_reset', {})

    assert (ok, reason) == (False, 'unreachable')


def test_send_system_email_rate_limited_on_429(monkeypatch):
    _paired(monkeypatch)
    fake, _calls = _fake_http(429, {'error': 'Too many requests'})
    monkeypatch.setattr(dental_clinic, '_cloud_http_request', fake)

    ok, reason = dental_clinic.send_system_email('a@b.c', 'password_reset', {})

    assert (ok, reason) == (False, 'rate_limited')


def test_send_system_email_rejected_on_400(monkeypatch):
    _paired(monkeypatch)
    fake, _calls = _fake_http(400, {'error': 'Unknown template'})
    monkeypatch.setattr(dental_clinic, '_cloud_http_request', fake)

    ok, reason = dental_clinic.send_system_email('a@b.c', 'not_a_real_template', {})

    assert (ok, reason) == (False, 'rejected')


def test_send_system_email_rejected_on_401(monkeypatch):
    _paired(monkeypatch)
    fake, _calls = _fake_http(401, {'error': 'Unauthorized'})
    monkeypatch.setattr(dental_clinic, '_cloud_http_request', fake)

    ok, reason = dental_clinic.send_system_email('a@b.c', 'password_reset', {})

    assert (ok, reason) == (False, 'rejected')


def test_send_system_email_provider_on_502(monkeypatch):
    _paired(monkeypatch)
    fake, _calls = _fake_http(502, {'error': 'Email provider failure'})
    monkeypatch.setattr(dental_clinic, '_cloud_http_request', fake)

    ok, reason = dental_clinic.send_system_email('a@b.c', 'password_reset', {})

    assert (ok, reason) == (False, 'provider')


def test_send_system_email_async_invokes_sync_function_on_a_thread(monkeypatch):
    calls = []
    done = threading.Event()
    main_thread = threading.current_thread()
    seen_thread = []

    def fake_send(to, template, params, lang='en'):
        seen_thread.append(threading.current_thread())
        calls.append((to, template, params, lang))
        done.set()
        return True, ''

    monkeypatch.setattr(dental_clinic, 'send_system_email', fake_send)

    dental_clinic.send_system_email_async('a@b.c', 'otp_login', {'code': '1'}, lang='ar')

    assert done.wait(timeout=5), 'send_system_email_async never invoked send_system_email'
    assert calls == [('a@b.c', 'otp_login', {'code': '1'}, 'ar')]
    assert seen_thread and seen_thread[0] is not main_thread, \
        'must run off the calling thread (fire-and-forget)'


def test_send_system_email_async_never_raises_and_logs_on_crash(monkeypatch):
    # Attach a real logging.Handler to the actual 'dental_clinic' logger
    # instead of monkeypatching logging.getLogger globally — patching that
    # function process-wide corrupts pytest's own logging plugin (it also
    # calls logging.getLogger() for its internal root-logger handlers).
    finished = threading.Event()
    logged = []

    class _CatchHandler(logging.Handler):
        def emit(self, record):
            logged.append(record.getMessage())
            finished.set()

    def fake_send_raises(to, template, params, lang='en'):
        raise RuntimeError('boom')

    monkeypatch.setattr(dental_clinic, 'send_system_email', fake_send_raises)

    target_logger = logging.getLogger('dental_clinic')
    handler = _CatchHandler()
    target_logger.addHandler(handler)
    try:
        # Must return immediately without propagating the crash from the thread.
        dental_clinic.send_system_email_async('a@b.c', 'otp_login', {'code': '1'})
        assert finished.wait(timeout=5), 'exception inside the async thread was never logged/handled'
    finally:
        target_logger.removeHandler(handler)

    assert logged and 'crash' in logged[0].lower()
