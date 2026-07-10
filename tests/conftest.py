"""Shared test fixtures. The CSRF middleware (feat/csrf-protection) rejects
unsafe-method requests without a valid token. The whole existing suite POSTs
without one, so this test-client subclass mirrors the real frontend fetch
interceptor: it seeds a session CSRF token and attaches a matching X-CSRFToken
header (and a csrf_token form field) on unsafe methods. Pass csrf=False to opt
out and exercise the rejection path."""
import os
import secrets
import sys

# encryption_key.py wraps Windows DPAPI (win32crypt), which has no Linux/macOS
# build at all -- pywin32 isn't even installed there (see requirements.txt's
# platform marker). CLINIC_TEST_FAKE_DPAPI swaps in a reversible XOR stand-in
# (read by encryption_key.py at its own import time, so this must be set
# BEFORE `import dental_clinic` below pulls it in transitively). Also
# propagates to any subprocess a test spawns via env={**os.environ, ...} (see
# tests/test_service_mode.py, which runs dental_clinic.py as a real child
# process -- a same-process monkeypatch wouldn't reach it). Real DPAPI itself
# is validated separately by Task 1's frozen-build spike; this only lets the
# rest of the suite exercise real SQLCipher (genuine manylinux wheels, no
# stub needed) through get_db_connection() on non-Windows CI.
if sys.platform != 'win32':
    os.environ['CLINIC_TEST_FAKE_DPAPI'] = '1'

from flask.testing import FlaskClient

import dental_clinic

_UNSAFE = {'POST', 'PUT', 'PATCH', 'DELETE'}


class _CsrfTestClient(FlaskClient):
    def open(self, *args, **kwargs):
        attach = kwargs.pop('csrf', True)
        method = (kwargs.get('method') or 'GET').upper()
        if attach and method in _UNSAFE:
            with self.session_transaction() as sess:
                token = sess.get('csrf_token')
                if not token:
                    token = secrets.token_urlsafe(32)
                    sess['csrf_token'] = token
            headers = dict(kwargs.get('headers') or {})
            headers.setdefault('X-CSRFToken', token)
            kwargs['headers'] = headers
            data = kwargs.get('data')
            if isinstance(data, dict) and 'csrf_token' not in data:
                data = dict(data)
                data['csrf_token'] = token
                kwargs['data'] = data
        return super().open(*args, **kwargs)


# Applied at collection time, before any test builds a client.
dental_clinic.app.test_client_class = _CsrfTestClient
