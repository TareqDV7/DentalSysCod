"""Cloud relay endpoint: POST /api/relay/email. Auth by clinic token,
per-clinic rate limits, template render (email_templates.render), send via
Resend (monkeypatched in tests through dental_clinic._send_via_resend).

Follows the CLOUD_MODE test-setup conventions in tests/test_cloud_mode.py
(env flag + fresh master DB + registered clinic w/ clinic_token) — the
`cloud_client` fixture below mirrors its `cloud` fixture.
"""
import pytest

import dental_clinic


@pytest.fixture()
def local_client(tmp_path, monkeypatch):
    """A normal (non-cloud) server — the relay route must 404 here."""
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(tmp_path / 'clinic.db'))
    monkeypatch.setattr(dental_clinic, 'CLOUD_MODE', False)
    dental_clinic.init_database()
    with dental_clinic.app.test_client() as c:
        yield c


@pytest.fixture()
def cloud_client(tmp_path, monkeypatch):
    """A cloud-mode node with a fresh master DB — mirrors test_cloud_mode.py's
    `cloud` fixture, plus clearing the relay rate-limit state so it can't
    leak between tests."""
    data_dir = tmp_path / 'clouddata'
    data_dir.mkdir()
    master = str(data_dir / 'cloud_master.db')
    monkeypatch.setattr(dental_clinic, 'CLOUD_MODE', True)
    monkeypatch.setattr(dental_clinic, '_DATA_DIR', data_dir)
    monkeypatch.setattr(dental_clinic, 'MASTER_DB_PATH', master)
    monkeypatch.setattr(dental_clinic, 'DB_NAME', dental_clinic._DbPathProxy(master))
    monkeypatch.setattr(dental_clinic, 'UPLOAD_FOLDER', data_dir / 'uploads')
    (data_dir / 'uploads').mkdir(exist_ok=True)
    monkeypatch.setattr(dental_clinic, '_REQUIRE_SIGNED_SERIAL', False)
    dental_clinic._set_request_db_path(None)
    dental_clinic._register_attempts.clear()  # rate-limit state must not leak between tests
    dental_clinic._relay_attempts_hour.clear()
    dental_clinic._relay_attempts_day.clear()
    dental_clinic.init_database()  # builds the master DB
    with dental_clinic.app.test_client() as c:
        yield c
    dental_clinic._set_request_db_path(None)
    dental_clinic._register_attempts.clear()
    dental_clinic._relay_attempts_hour.clear()
    dental_clinic._relay_attempts_day.clear()


def _register_clinic(client, serial, name='Test Clinic'):
    """Mirror test_cloud_mode.py's `_register` helper: provision a clinic row
    via the real registration endpoint and return the full response body."""
    r = client.post('/api/clinics/register', json={'serial_number': serial, 'clinic_name': name})
    assert r.status_code == 200, r.get_data(as_text=True)
    return r.get_json()


def _h(token):
    return {'X-Clinic-Token': token}


@pytest.fixture()
def clinic_token(cloud_client):
    return _register_clinic(cloud_client, 'RELAY-SERIAL-0001')['clinic_token']


def test_relay_requires_cloud_mode(local_client):
    # CLINIC_CLOUD_MODE off -> route 404s
    r = local_client.post('/api/relay/email', json={})
    assert r.status_code == 404


def test_relay_rejects_bad_token(cloud_client):
    r = cloud_client.post('/api/relay/email',
                          json={'to': 'a@b.c', 'template': 'password_reset',
                                'params': {}, 'lang': 'en'},
                          headers=_h('nope'))
    assert r.status_code == 401


def test_relay_sends(cloud_client, monkeypatch, clinic_token):
    calls = []
    monkeypatch.setattr(dental_clinic, '_send_via_resend',
                        lambda to, subject, body: calls.append((to, subject, body)))
    r = cloud_client.post('/api/relay/email',
                          json={'to': 'a@b.c', 'template': 'password_reset',
                                'params': {'clinic_name': 'X', 'code': '123456'}, 'lang': 'en'},
                          headers=_h(clinic_token))
    assert r.status_code == 200 and r.get_json()['sent'] is True
    assert calls and '123456' in calls[0][2]


def test_relay_unknown_template_400(cloud_client, clinic_token):
    r = cloud_client.post('/api/relay/email',
                          json={'to': 'a@b.c', 'template': 'not_a_real_template',
                                'params': {}, 'lang': 'en'},
                          headers=_h(clinic_token))
    assert r.status_code == 400
    assert 'error' in r.get_json()


def test_relay_non_dict_params_400(cloud_client, monkeypatch, clinic_token):
    # non-dict params must be a clean 400, not a TypeError-driven 500
    monkeypatch.setattr(dental_clinic, '_send_via_resend', lambda to, subject, body: None)
    for bad in (['x'], 'x', 5, True):
        r = cloud_client.post('/api/relay/email',
                              json={'to': 'a@b.c', 'template': 'password_reset',
                                    'params': bad, 'lang': 'en'},
                              headers=_h(clinic_token))
        assert r.status_code == 400, bad
        assert 'error' in r.get_json()


def test_relay_rate_limit_429(cloud_client, monkeypatch, clinic_token):
    # monkeypatch dental_clinic._RELAY_HOURLY_LIMIT to 2, send 3, expect 429
    monkeypatch.setattr(dental_clinic, '_RELAY_HOURLY_LIMIT', 2)
    monkeypatch.setattr(dental_clinic, '_send_via_resend', lambda to, subject, body: None)
    body = {'to': 'a@b.c', 'template': 'password_reset',
            'params': {'clinic_name': 'X', 'code': '111111'}, 'lang': 'en'}
    for _ in range(2):
        r = cloud_client.post('/api/relay/email', json=body, headers=_h(clinic_token))
        assert r.status_code == 200, r.get_data(as_text=True)
    r = cloud_client.post('/api/relay/email', json=body, headers=_h(clinic_token))
    assert r.status_code == 429


def test_relay_provider_failure_502(cloud_client, monkeypatch, clinic_token):
    # _send_via_resend raises -> 502, body {'error': ...}
    def _boom(to, subject, body):
        raise RuntimeError('resend is down')
    monkeypatch.setattr(dental_clinic, '_send_via_resend', _boom)
    r = cloud_client.post('/api/relay/email',
                          json={'to': 'a@b.c', 'template': 'password_reset',
                                'params': {'clinic_name': 'X', 'code': '999999'}, 'lang': 'en'},
                          headers=_h(clinic_token))
    assert r.status_code == 502
    assert 'error' in r.get_json()
