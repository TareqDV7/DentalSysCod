"""Editable tooth-condition catalog (mirrors the treatment_procedures catalog)."""

import sqlite3

import pytest

import dental_clinic


@pytest.fixture()
def client(tmp_path, monkeypatch):
    test_db = tmp_path / 'clinic_test.db'
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(test_db))
    dental_clinic.init_database()
    with dental_clinic.app.test_client() as test_client:
        yield test_client


def test_core_eight_seeded(client):
    rows = client.get('/api/tooth-conditions').get_json()
    names = {r['name'] for r in rows}
    assert {'Healthy', 'Decay', 'Filled', 'Crown', 'Root canal',
            'Missing', 'Implant', 'Needs extraction'} <= names
    # Catalog carries display metadata.
    decay = next(r for r in rows if r['name'] == 'Decay')
    assert decay['color'].startswith('#')
    assert decay['name_ar']
    assert 'sort_order' in decay
