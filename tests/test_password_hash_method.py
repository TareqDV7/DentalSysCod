"""Password hashes must use a PyInstaller-frozen-safe method.

Werkzeug 3's *default* ``generate_password_hash`` method is ``scrypt``
(``scrypt:32768:8:1$...``). ``scrypt`` relies on OpenSSL scrypt support plus a
~32 MB memory budget that frozen (PyInstaller) binaries frequently can't
satisfy — so seeding / verifying the ``admin`` account can silently fail in the
packaged ``.exe`` even though dev and pytest (full OpenSSL) pass. The symptom is
"``admin`` / ``admin`` rejected on a brand-new install", which never reproduces
in CI.

Pin every password hash to ``pbkdf2:sha256``: pure-``hashlib``, always available,
and identical in dev and frozen builds. ``check_password_hash`` still
auto-detects the method from the stored prefix, so any legacy scrypt hashes keep
verifying.
"""
import sqlite3

import dental_clinic

# A method that does NOT depend on OpenSSL scrypt support or a large maxmem.
FROZEN_SAFE_PREFIX = 'pbkdf2:'


def _init_db(tmp_path, monkeypatch, admin_password=None):
    db = tmp_path / 'pwhash.db'
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(db))
    monkeypatch.setattr(dental_clinic, 'CLOUD_MODE', False)
    if admin_password is None:
        monkeypatch.delenv('CLINIC_ADMIN_PASSWORD', raising=False)
    else:
        monkeypatch.setenv('CLINIC_ADMIN_PASSWORD', admin_password)
    dental_clinic.init_database()
    dental_clinic.app.config['TESTING'] = True
    return db


def _admin_hash(db):
    return sqlite3.connect(str(db)).execute(
        "SELECT password_hash FROM users WHERE username='admin'").fetchone()[0]


def _login(client, uid=1):
    with client.session_transaction() as sess:
        sess['uid'] = uid
        sess['uname'] = 'admin'


def test_seeded_default_admin_hash_is_frozen_safe(tmp_path, monkeypatch):
    db = _init_db(tmp_path, monkeypatch, admin_password=None)
    assert _admin_hash(db).startswith(FROZEN_SAFE_PREFIX)


def test_seeded_env_admin_hash_is_frozen_safe(tmp_path, monkeypatch):
    db = _init_db(tmp_path, monkeypatch, admin_password='s3cret-pw')
    assert _admin_hash(db).startswith(FROZEN_SAFE_PREFIX)


def test_seeded_default_admin_can_log_in(tmp_path, monkeypatch):
    # The end-to-end guarantee: the well-known default verifies against the
    # stored hash. (Passes in dev today; the value is locking it in so a future
    # method change that breaks the frozen binary can't slip through green CI.)
    _init_db(tmp_path, monkeypatch, admin_password=None)
    h = _admin_hash(tmp_path / 'pwhash.db')
    from werkzeug.security import check_password_hash
    assert check_password_hash(h, 'admin')


def test_form_password_change_writes_frozen_safe_hash(tmp_path, monkeypatch):
    db = _init_db(tmp_path, monkeypatch, admin_password=None)
    with dental_clinic.app.test_client() as c:
        _login(c)
        r = c.post('/change-password', data={
            'current_password': 'admin',
            'new_password': 'newpass1',
            'confirm_password': 'newpass1',
        })
        assert r.status_code == 302
    assert _admin_hash(db).startswith(FROZEN_SAFE_PREFIX)


def test_api_password_change_writes_frozen_safe_hash(tmp_path, monkeypatch):
    db = _init_db(tmp_path, monkeypatch, admin_password=None)
    with dental_clinic.app.test_client() as c:
        _login(c)
        r = c.post('/api/auth/change-password', json={
            'current_password': 'admin',
            'new_password': 'newpass1',
        })
        assert r.status_code == 200
    assert _admin_hash(db).startswith(FROZEN_SAFE_PREFIX)
