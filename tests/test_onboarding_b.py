# tests/test_onboarding_b.py
import sqlite3
import pytest
import dental_clinic


@pytest.fixture()
def local(tmp_path, monkeypatch):
    db = str(tmp_path / 'clinic.db')
    monkeypatch.setattr(dental_clinic, 'CLOUD_MODE', False)
    monkeypatch.setattr(dental_clinic, 'DB_NAME', db)
    monkeypatch.delenv('CLINIC_LICENSE_CLOUD_URL', raising=False)
    monkeypatch.delenv('CLINIC_CLOUD_URL', raising=False)
    dental_clinic.init_database()
    with dental_clinic.app.test_client() as c:
        yield c


def test_license_cloud_url_falls_back_to_baked(local):
    assert dental_clinic._license_cloud_url() == dental_clinic._BAKED_CLOUD_BASE_URL.rstrip('/')


def test_env_overrides_baked(local, monkeypatch):
    monkeypatch.setenv('CLINIC_LICENSE_CLOUD_URL', 'https://staging.example.test/')
    assert dental_clinic._license_cloud_url() == 'https://staging.example.test'
