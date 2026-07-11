"""GET/PUT /api/reminders/settings — mirrors the existing /api/branding
endpoint's shape and auth posture. SMTP password / SMS API key are
encrypted before being written and never echoed back in plaintext on GET."""
import os

import pytest
from cryptography.fernet import Fernet

import dental_clinic


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('CLINIC_CLOUD_REMINDER_KEY', Fernet.generate_key().decode())
    test_db = tmp_path / 'reminder_settings_test.db'
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(test_db))
    dental_clinic.init_database()
    dental_clinic.app.config['TESTING'] = True
    with dental_clinic.app.test_client() as c:
        with c.session_transaction() as sess:
            sess['uid'] = 1
            sess['username'] = 'admin'
        yield c


def test_get_returns_defaults_on_fresh_db(client):
    resp = client.get('/api/reminders/settings')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['enabled'] is False
    assert data['lead_hours'] == 24
    assert data['smtp_password_set'] is False
    assert data['sms_api_key_set'] is False
    assert 'smtp_password' not in data
    assert 'sms_api_key' not in data


def test_put_then_get_roundtrips_non_secret_fields(client):
    resp = client.put('/api/reminders/settings', json={
        'enabled': True,
        'lead_hours': 12,
        'message_template': 'Hi {patient_name}, see you {date} {time}.',
        'clinic_timezone': 'Asia/Dubai',
        'smtp_host': 'smtp.example.com',
        'smtp_port': 587,
        'smtp_user': 'clinic@example.com',
        'smtp_password': 'hunter2',
        'sms_provider': 'twilio',
        'sms_api_key': 'ACxxxx',
        'sms_api_secret': 'authtoken',
        'sms_from_number': '+15551234567',
    })
    assert resp.status_code == 200

    data = client.get('/api/reminders/settings').get_json()
    assert data['enabled'] is True
    assert data['lead_hours'] == 12
    assert data['smtp_host'] == 'smtp.example.com'
    assert data['smtp_password_set'] is True
    assert data['sms_api_key_set'] is True
    assert data['sms_api_secret_set'] is True
    assert 'smtp_password' not in data
    assert 'sms_api_key' not in data
    assert 'sms_api_secret' not in data


def test_put_requires_login(tmp_path, monkeypatch):
    monkeypatch.setenv('CLINIC_CLOUD_REMINDER_KEY', Fernet.generate_key().decode())
    test_db = tmp_path / 'reminder_settings_nologin.db'
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(test_db))
    dental_clinic.init_database()
    with dental_clinic.app.test_client() as c:
        resp = c.put('/api/reminders/settings', json={'enabled': True})
    assert resp.status_code == 401
