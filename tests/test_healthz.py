"""Tests for the unauthenticated /healthz probe."""

import json
import pytest

import dental_clinic


@pytest.fixture
def local_client(tmp_path, monkeypatch):
    db = tmp_path / 'healthz_local.db'
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(db))
    monkeypatch.setattr(dental_clinic, 'CLOUD_MODE', False)
    dental_clinic.init_database()
    app = dental_clinic.app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def test_healthz_ok_on_local_without_auth(local_client):
    r = local_client.get('/healthz')
    assert r.status_code == 200
    body = r.get_json()
    assert body['status'] == 'ok'
    assert body['mode'] == 'local'
    assert body['db_writable'] is True
    assert 'last_backup_at' in body
    assert isinstance(body['uptime_seconds'], int)


def test_healthz_returns_503_when_db_unreachable(local_client, monkeypatch, tmp_path):
    # Point at a path inside a non-existent directory so sqlite3.connect fails.
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(tmp_path / 'nope' / 'x.db'))
    r = local_client.get('/healthz')
    assert r.status_code == 503
    body = r.get_json()
    assert body['status'] == 'degraded'
    assert body['db_writable'] is False
    assert 'db_error' in body


def test_healthz_open_on_cloud_node_without_clinic_token(tmp_path, monkeypatch):
    # On cloud mode, /api/* without a token returns 400 — /healthz must be
    # exempt so monitoring probes work.
    master = tmp_path / 'cloud_master.db'
    monkeypatch.setattr(dental_clinic, 'MASTER_DB_PATH', str(master))
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(master))
    monkeypatch.setattr(dental_clinic, 'CLOUD_MODE', True)
    dental_clinic.init_database()
    with dental_clinic.app.test_client() as c:
        r = c.get('/healthz')
        assert r.status_code == 200
        body = r.get_json()
        assert body['mode'] == 'cloud'
        assert body['status'] == 'ok'


def test_healthz_response_is_small(local_client):
    # External monitors poll aggressively — keep the payload tight.
    r = local_client.get('/healthz')
    assert len(r.data) < 500, 'healthz response should stay under 500 bytes'


def test_json_access_log_emits_well_formed_line(local_client, monkeypatch, capsys):
    monkeypatch.setenv('CLINIC_LOG_FORMAT', 'json')
    # Re-run the configurator so the StreamHandler attaches to (the now-real)
    # stdout that pytest's capsys is monitoring.
    log = dental_clinic._REQUEST_LOG
    # Clear any handler attached by an earlier test or import.
    for h in list(log.handlers):
        log.removeHandler(h)
    dental_clinic._configure_access_logging()
    # The configurator picks one of {pytest-captured stdout, real stdout} at
    # call time; capsys.readouterr() drains whichever we landed on. Hitting
    # /healthz fires before_request + after_request — the after hook does the
    # logging.
    local_client.get('/healthz')
    out = capsys.readouterr().out
    # Strip ANSI / non-JSON noise; find a line that parses as JSON with our keys.
    parsed = None
    for line in out.splitlines():
        line = line.strip()
        if not line.startswith('{'):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if 'method' in obj and 'path' in obj:
            parsed = obj
            break
    assert parsed is not None, f'no JSON access log line found in: {out!r}'
    assert parsed['method'] == 'GET'
    assert parsed['path'] == '/healthz'
    assert parsed['status'] == 200
    assert isinstance(parsed['latency_ms'], int)
