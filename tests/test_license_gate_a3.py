# tests/test_license_gate_a3.py
import sqlite3
import pytest
import dental_clinic
from datetime import datetime, timedelta, timezone


@pytest.fixture()
def local(tmp_path, monkeypatch):
    db = str(tmp_path / 'clinic.db')
    monkeypatch.setattr(dental_clinic, 'CLOUD_MODE', False)
    monkeypatch.setattr(dental_clinic, 'DB_NAME', db)
    dental_clinic.init_database()
    with dental_clinic.app.test_client() as c:
        yield c


def _seed_license(serial, status='active', days=365, grace_extra=14):
    today = datetime.now(timezone.utc).date()
    expires = (today + timedelta(days=days)).strftime('%Y-%m-%d')
    grace = (today + timedelta(days=days + grace_extra)).strftime('%Y-%m-%d')
    conn = sqlite3.connect(dental_clinic.DB_NAME)
    conn.execute('''INSERT INTO licenses (serial_number, clinic_name, plan_name, status,
                    max_devices, expires_at, grace_until) VALUES (?,?,?,?,?,?,?)''',
                 (serial, 'C', 'standard', status, 3, expires, grace))
    conn.execute("INSERT INTO app_settings (key, value) VALUES ('active_serial_number', ?) "
                 "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (serial,))
    conn.commit(); conn.close()


def _state(local):
    conn = sqlite3.connect(dental_clinic.DB_NAME)
    cur = conn.cursor()
    s = dental_clinic._license_gate_state(cur)
    conn.close()
    return s


def test_state_unlicensed_when_no_license(local):
    assert _state(local)['state'] == 'unlicensed'


def test_state_active_for_future_window(local):
    _seed_license('DENTAL-A3-ACT', days=365)
    assert _state(local)['state'] == 'active'


def test_state_grace_when_in_grace(local):
    _seed_license('DENTAL-A3-GRC', days=-5, grace_extra=14)   # expired 5d ago, 14d grace
    assert _state(local)['state'] == 'grace'


def test_state_view_only_past_grace(local):
    _seed_license('DENTAL-A3-EXP', days=-60, grace_extra=14)  # well past grace
    assert _state(local)['state'] == 'view_only'


def test_state_view_only_when_revoked(local):
    _seed_license('DENTAL-A3-REV', status='revoked', days=365)
    assert _state(local)['state'] == 'view_only'
