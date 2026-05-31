#!/usr/bin/env python3
"""
Dental Clinic Management System
Single-file executable with auto-installation
Run: py dental_clinic.py (Windows) or python dental_clinic.py (Linux/Mac)
"""

import sys
import subprocess
import os
import platform
import sqlite3
import base64
import binascii
import collections
import contextlib
import hashlib
import hmac
import threading
import time
import webbrowser
import json
import re
import secrets
import uuid
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path


# Auto-install dependencies
def check_and_install_dependencies():
    """Check and install required packages"""
    required_packages = {
        'flask': 'Flask',
        'flask_cors': 'Flask-CORS',
        'waitress': 'waitress'
    }

    print("Checking dependencies...")

    for module_name, package_name in required_packages.items():
        try:
            __import__(module_name)
            print(f"  {package_name} is already installed")
        except ImportError:
            print(f"  Installing {package_name}...")
            try:
                subprocess.check_call([sys.executable, '-m', 'pip', 'install', package_name])
            except Exception as exc:
                # Non-fatal: a missing optional package (waitress) is handled at
                # runtime; a missing required one will surface a clear ImportError below.
                print(f"  Could not install {package_name}: {exc}")


# Check and install dependencies before importing
check_and_install_dependencies()

# Now import the packages
from flask import Flask, render_template_string, request, jsonify, send_file, session, redirect, url_for, g
from flask_cors import CORS
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from markupsafe import escape


app = Flask(__name__)
# CORS is only needed where a browser on a different origin would call the
# JSON API — that's only the local clinic server (mobile uses the HTTP API
# without a browser, so CORS doesn't apply to it). The staff web portal is
# same-origin (Flask serves both the HTML and the API), so CORS isn't needed
# there either. On the cloud node there is no browser entry point at all, so
# CORS is disabled — `/api/*` is reached only by other servers / the mobile,
# never by a third-party page.
#
# On the local server: scope CORS to /api/* with no credentials (no cookies),
# so a malicious site can't ride a session by accident. Without `supports_credentials`
# the only thing reachable is a public token-authenticated API surface.
if not os.environ.get('CLINIC_CLOUD_MODE', '0').strip().lower() in ('1', 'true', 'yes', 'on'):
    CORS(app, resources={r'/api/*': {'origins': '*'}}, supports_credentials=False)

# Helpful development defaults so UI changes are visible immediately when testing locally.
# - Enable template auto-reload so Jinja templates refresh without restarting the server.
# - Set send-file cache age to 0 to avoid stale static assets.
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0


def _load_or_create_secret_key():
    """Load (or create) the persistent Flask session secret from app_settings.

    Kept self-contained so it works before init_database() runs and when the
    module is imported by tests. Falls back to an ephemeral key on any error.
    """
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        cursor.execute('SELECT value FROM app_settings WHERE key = ?', ('flask_secret_key',))
        row = cursor.fetchone()
        if row and row[0]:
            key = row[0]
        else:
            key = secrets.token_hex(32)
            cursor.execute('INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)',
                           ('flask_secret_key', key))
            conn.commit()
        conn.close()
        return key
    except Exception:
        return secrets.token_hex(32)


@app.after_request
def _add_no_cache_headers(response):
    # When running in debug/development mode we prevent aggressive caching of
    # HTML/CSS/JS so frontend changes appear immediately in the browser.
    _frozen = getattr(sys, 'frozen', False)
    disable_cache = os.environ.get('CLINIC_DISABLE_CACHE', '0' if _frozen else '1') == '1'
    debug_mode = os.environ.get('CLINIC_DEBUG', '0' if _frozen else '1') == '1'
    if disable_cache or debug_mode:
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    return response

# Where the database / uploads / backups live. See window/data_dir.py for the
# resolution rules (env var > frozen-exe ProgramData > source script dir).
from window.data_dir import resolve_data_dir
_DATA_DIR = resolve_data_dir()
_BUNDLE_DIR = Path(sys._MEIPASS) if getattr(sys, 'frozen', False) else Path(__file__).parent
_DATA_DIR.mkdir(parents=True, exist_ok=True)

# ── Multi-tenant cloud mode ─────────────────────────────────────────────────
# With CLINIC_CLOUD_MODE on, one process serves many clinics: a master registry
# DB (cloud_master.db) tracks clinics, and each clinic gets its own SQLite file
# (clinic_<id>.db). Requests carry a clinic token; a before_request hook resolves
# it and points DB_NAME at that clinic's file for the duration of the request, so
# every existing `sqlite3.connect(DB_NAME)` handler works unchanged. Off (the
# default — i.e. the clinic's own local server), none of this is active.
CLOUD_MODE = os.environ.get('CLINIC_CLOUD_MODE', '0').strip().lower() in ('1', 'true', 'yes', 'on')
MASTER_DB_PATH = str(_DATA_DIR / 'cloud_master.db')
_request_state = threading.local()


class _DbPathProxy(os.PathLike):
    """Path-like whose value is per-thread, so concurrent requests for different
    clinics each see their own DB. sqlite3.connect()/send_file() call os.fspath()
    on it, so call sites keep using DB_NAME verbatim."""

    def __init__(self, default):
        self._default = str(default)

    def _resolve(self):
        return getattr(_request_state, 'db_path', None) or self._default

    def __fspath__(self):
        return self._resolve()

    def __str__(self):
        return self._resolve()

    def __repr__(self):
        return f'<DbPathProxy {self._resolve()!r}>'


def _set_request_db_path(path):
    _request_state.db_path = str(path) if path else None


def _clinic_db_path(clinic_id):
    return str(_DATA_DIR / f'clinic_{int(clinic_id)}.db')


DB_NAME = _DbPathProxy(MASTER_DB_PATH) if CLOUD_MODE else str(_DATA_DIR / 'dental_clinic.db')
UPLOAD_FOLDER = _DATA_DIR / 'uploads'
UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
PAIRING_CODE_TTL_MINUTES = 5
DEFAULT_LICENSE_DAYS = 30
DEFAULT_LICENSE_GRACE_DAYS = 7

# Endpoints reachable on the cloud node without a clinic token.
_CLOUD_OPEN_EXACT = {'/api/clinics/register', '/api/system/readiness', '/api/license/offline-verify', '/healthz', '/logo', '/favicon.ico'}
_CLOUD_OPEN_PREFIXES = ('/static/',)
# Not available on the cloud node: uploads aren't part of cloud sync and the
# folder isn't tenant-scoped; the /api/cloud/* endpoints are for a clinic's own
# local server only.
_CLOUD_BLOCKED_PREFIXES = ('/api/medical-images', '/api/cloud/')

# Tiny in-memory per-IP rate limiter for the cloud's only unauthenticated POST
# (/api/clinics/register). Default 10 attempts per hour per IP; tunable via
# CLINIC_REGISTER_RATE_LIMIT (count) and CLINIC_REGISTER_RATE_WINDOW (seconds).
# Resets on every process restart — good enough to deter spam without pulling
# in Redis. Behind Caddy we read X-Forwarded-For; otherwise request.remote_addr.
try:
    _REGISTER_RATE_LIMIT = int(os.environ.get('CLINIC_REGISTER_RATE_LIMIT', '10'))
except (TypeError, ValueError):
    _REGISTER_RATE_LIMIT = 10
try:
    _REGISTER_RATE_WINDOW = int(os.environ.get('CLINIC_REGISTER_RATE_WINDOW', '3600'))
except (TypeError, ValueError):
    _REGISTER_RATE_WINDOW = 3600
_register_attempts = {}  # ip -> list[timestamps]; sliding window
_register_attempts_lock = threading.Lock()

# Optional HMAC-signed-serial gating for /api/clinics/register. When the env
# CLINIC_SERIAL_SIGNING_KEY is set (base64-encoded HMAC key matching the one
# used by serial_generator.py), the register handler will accept an
# `offline_token` field in the body and verify it. With CLINIC_REQUIRE_SIGNED_SERIAL=1,
# unsigned / invalid registrations are rejected outright; otherwise (default)
# the signature is verified when present but not required, so legacy demo
# serials still register. Off entirely when the key isn't configured.
_SERIAL_SIGNING_KEY_B64 = os.environ.get('CLINIC_SERIAL_SIGNING_KEY', '').strip()
_REQUIRE_SIGNED_SERIAL = os.environ.get('CLINIC_REQUIRE_SIGNED_SERIAL', '0').strip().lower() in ('1', 'true', 'yes', 'on')


def _serial_signing_key():
    """Decoded HMAC key, or None if not configured."""
    if not _SERIAL_SIGNING_KEY_B64:
        return None
    try:
        return base64.b64decode(_SERIAL_SIGNING_KEY_B64)
    except (ValueError, binascii.Error):
        return None


def _verify_serial_token(serial, token, key):
    """Return (ok, reason). Verifies that ``token`` is a valid offline-license
    token (payload.signature, both base64-url or base64) issued by a holder of
    ``key`` and that its payload's ``serial`` field equals ``serial`` and the
    license isn't expired past its grace period."""
    if not token:
        return False, 'offline_token required'
    try:
        payload_part, signature_part = str(token).split('.', 1)
    except ValueError:
        return False, 'malformed offline_token'
    # serial_generator.py uses plain base64; tolerate urlsafe too.
    def _decode(s):
        try:
            return base64.b64decode(s + '=' * (-len(s) % 4))
        except (ValueError, binascii.Error):
            try:
                return base64.urlsafe_b64decode(s + '=' * (-len(s) % 4))
            except (ValueError, binascii.Error):
                return None
    payload_bytes = _decode(payload_part)
    sig_bytes = _decode(signature_part)
    if payload_bytes is None or sig_bytes is None:
        return False, 'malformed offline_token'
    expected = hmac.new(key, payload_bytes, hashlib.sha256).digest()
    if not hmac.compare_digest(expected, sig_bytes):
        return False, 'invalid offline_token signature'
    try:
        payload = json.loads(payload_bytes.decode('utf-8'))
    except (ValueError, UnicodeDecodeError):
        return False, 'malformed offline_token payload'
    token_serial = str(payload.get('serial') or '').strip().upper()
    if token_serial != serial.strip().upper():
        return False, 'offline_token does not match this serial'
    # Honour grace_until > today if present (datetime.utcnow()-equivalent).
    grace = str(payload.get('grace_until') or '').strip()
    if grace:
        try:
            grace_dt = datetime.fromisoformat(grace.rstrip('Z'))
            if _naive_utc_now() > grace_dt:
                return False, 'offline_token has expired'
        except ValueError:
            pass  # malformed grace value — don't block on it
    return True, ''


def _client_ip():
    fwd = request.headers.get('X-Forwarded-For', '')
    if fwd:
        return fwd.split(',')[0].strip()
    return request.remote_addr or 'unknown'


def _check_register_rate_limit():
    """Return None if allowed, else a (response, status) tuple to send back.
    Sliding window — drops timestamps older than the window before counting."""
    if _REGISTER_RATE_LIMIT <= 0:
        return None
    ip = _client_ip()
    now = time.monotonic()
    cutoff = now - _REGISTER_RATE_WINDOW
    with _register_attempts_lock:
        bucket = [t for t in _register_attempts.get(ip, []) if t > cutoff]
        if len(bucket) >= _REGISTER_RATE_LIMIT:
            _register_attempts[ip] = bucket
            return jsonify({
                'error': f'Too many registration attempts — try again later '
                         f'(limit {_REGISTER_RATE_LIMIT} per {_REGISTER_RATE_WINDOW}s).'
            }), 429
        bucket.append(now)
        _register_attempts[ip] = bucket
    return None


def _resolve_clinic_token():
    return (request.headers.get('X-Clinic-Token') or request.args.get('clinic_token') or '').strip()


@app.before_request
def _cloud_tenant_routing():
    """In cloud mode: route each /api/* request to its clinic's DB by token."""
    if not CLOUD_MODE:
        return None
    _set_request_db_path(None)  # default to the master DB; reset per request (threads are reused)
    if request.method == 'OPTIONS':
        return None
    path = request.path or '/'
    if path in _CLOUD_OPEN_EXACT or path.startswith(_CLOUD_OPEN_PREFIXES):
        return None
    if path.startswith(_CLOUD_BLOCKED_PREFIXES):
        return jsonify({'error': 'Not available on the cloud node'}), 501
    if not path.startswith('/api/'):
        # The staff web portal is served by each clinic's *local* server.
        return ('DentaCare cloud sync node — staff use your local server.\n', 200, {'Content-Type': 'text/plain; charset=utf-8'})
    token = _resolve_clinic_token()
    if not token:
        return jsonify({'error': 'Clinic token required'}), 401
    row = None
    try:
        conn = sqlite3.connect(MASTER_DB_PATH)
        conn.row_factory = sqlite3.Row
        row = conn.execute('SELECT id, active FROM clinics WHERE clinic_token = ?', (token,)).fetchone()
        if row and int(row['active']) == 1:
            try:  # last-seen bookkeeping is best-effort — never fail a request over it
                conn.execute('UPDATE clinics SET last_seen_at = CURRENT_TIMESTAMP WHERE id = ?', (row['id'],))
                conn.commit()
            except sqlite3.Error:
                pass
        conn.close()
    except sqlite3.Error:
        row = None
    if not row or int(row['active']) != 1:
        return jsonify({'error': 'Invalid clinic token'}), 401
    _set_request_db_path(_clinic_db_path(row['id']))
    return None


@app.teardown_request
def _cloud_tenant_routing_teardown(exc):
    if CLOUD_MODE:
        _set_request_db_path(None)


# Persistent session secret (needs DB_NAME, so set here rather than at app creation).
app.secret_key = _load_or_create_secret_key()

_APP_STARTED_AT = time.time()

SYNC_TABLES = [
    'patients',
    'appointments',
    'visits',
    'treatments',
    'treatment_plans',
    'treatment_procedures',
    'patient_followups',
    'expenses',
    'billing',
    'holidays'
]
MOBILE_ANDROID_PACKAGE_PATH = Path('deployment') / 'mobile' / 'android' / 'clinic-mobile.apk'
MOBILE_IOS_PACKAGE_PATH = Path('deployment') / 'mobile' / 'ios' / 'clinic-mobile.ipa'


def ensure_table_column(cursor, table_name, column_name, column_type):
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [row[1] for row in cursor.fetchall()]
    if column_name not in columns:
        if column_name == 'payment_status':
            cursor.execute(f'ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type} DEFAULT "pending"')
        elif column_name == 'source_type':
            cursor.execute(f'ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type} DEFAULT "manual"')
        else:
            # SQLite does not allow non-constant defaults like CURRENT_TIMESTAMP when
            # adding a column. If the requested column_type contains such a default,
            # add the column without the DEFAULT clause to remain compatible.
            ct = column_type
            if 'CURRENT_TIMESTAMP' in column_type or 'strftime' in column_type:
                ct = column_type.split('DEFAULT')[0].strip()
            cursor.execute(f'ALTER TABLE {table_name} ADD COLUMN {column_name} {ct}')


def ensure_updated_at_trigger(cursor, table_name):
    cursor.execute(f'''
        CREATE TRIGGER IF NOT EXISTS trg_{table_name}_updated_at
        AFTER UPDATE ON {table_name}
        FOR EACH ROW
        BEGIN
            UPDATE {table_name}
            SET updated_at = CURRENT_TIMESTAMP
            WHERE id = NEW.id;
        END
    ''')


def get_db_connection(with_row_factory=False):
    conn = sqlite3.connect(DB_NAME)
    if with_row_factory:
        conn.row_factory = sqlite3.Row
    return conn


def _naive_utc_now():
    # datetime.utcnow() is deprecated as of Python 3.12. Keep the same naive-UTC
    # semantics we've always had (no tzinfo) by stripping it after going aware.
    return datetime.now(timezone.utc).replace(tzinfo=None)


def utc_now_iso():
    return _naive_utc_now().replace(microsecond=0).isoformat() + 'Z'


def generate_pair_code():
    return ''.join(secrets.choice('0123456789') for _ in range(6))


def read_app_setting(cursor, key, default_value=None):
    cursor.execute('SELECT value FROM app_settings WHERE key = ?', (key,))
    row = cursor.fetchone()
    if not row:
        return default_value
    return row[0]


def write_app_setting(cursor, key, value):
    cursor.execute('''
        INSERT INTO app_settings (key, value, updated_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP
    ''', (key, str(value)))


def get_or_create_license_signing_key(cursor):
    key = read_app_setting(cursor, 'license_signing_key', '')
    if key:
        return key
    key = secrets.token_urlsafe(48)
    write_app_setting(cursor, 'license_signing_key', key)
    return key


def build_offline_license_payload(record, validity, device_id=''):
    return {
        'serial_number': record['serial_number'],
        'clinic_name': record['clinic_name'],
        'plan_name': record['plan_name'],
        'status': record['status'],
        'max_devices': record['max_devices'],
        'expires_at': record['expires_at'],
        'grace_until': record['grace_until'],
        'licensed': bool(validity['licensed']),
        'in_grace': bool(validity['in_grace']),
        'device_id': device_id,
        'issued_at': utc_now_iso(),
    }


def encode_offline_license_token(payload, signing_key):
    payload_json = json.dumps(payload, sort_keys=True, separators=(',', ':')).encode('utf-8')
    payload_part = base64.urlsafe_b64encode(payload_json).decode('ascii').rstrip('=')
    signature = hmac.new(signing_key.encode('utf-8'), payload_json, hashlib.sha256).digest()
    signature_part = base64.urlsafe_b64encode(signature).decode('ascii').rstrip('=')
    return f'{payload_part}.{signature_part}'


def decode_offline_license_token(token, signing_key):
    try:
        payload_part, signature_part = token.split('.', 1)
        payload_bytes = base64.urlsafe_b64decode(payload_part + '=' * (-len(payload_part) % 4))
        expected_signature = hmac.new(signing_key.encode('utf-8'), payload_bytes, hashlib.sha256).digest()
        actual_signature = base64.urlsafe_b64decode(signature_part + '=' * (-len(signature_part) % 4))
        if not hmac.compare_digest(expected_signature, actual_signature):
            return None
        return json.loads(payload_bytes.decode('utf-8'))
    except Exception:
        return None


def serialize_offline_license(record, validity, signing_key, device_id=''):
    payload = build_offline_license_payload(record, validity, device_id=device_id)
    token = encode_offline_license_token(payload, signing_key)
    return payload, token


def verify_offline_license_token(token, signing_key):
    payload = decode_offline_license_token(token, signing_key)
    if not payload:
        return None
    expires_at = payload.get('expires_at') or ''
    grace_until = payload.get('grace_until') or ''
    status = payload.get('status') or 'active'
    validity = evaluate_license_window(status, expires_at, grace_until)
    if not validity['licensed']:
        return None
    return payload


def get_table_columns(cursor, table_name):
    cursor.execute(f'PRAGMA table_info({table_name})')
    return [row[1] for row in cursor.fetchall()]


def init_database():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Enable WAL: readers no longer block on the single writer, which avoids
    # "database is locked" errors when staff browsers and mobile sync overlap.
    # WAL is a persistent property of the database file, so setting it once here
    # applies to every future connection.
    try:
        cursor.execute('PRAGMA journal_mode=WAL')
    except sqlite3.Error:
        pass

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS patients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            date_of_birth TEXT,
            phone TEXT,
            email TEXT,
            address TEXT,
            medical_history TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            appointment_date TEXT NOT NULL,
            duration INTEGER DEFAULT 30,
            treatment_type TEXT,
            status TEXT DEFAULT 'scheduled',
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (patient_id) REFERENCES patients (id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS visits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            appointment_id INTEGER,
            patient_id INTEGER NOT NULL,
            visit_date TEXT NOT NULL,
            dentist_name TEXT,
            chief_complaint TEXT,
            diagnosis TEXT,
            procedure_summary TEXT,
            follow_up_date TEXT,
            status TEXT DEFAULT 'open',
            notes TEXT,
            outcome TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (patient_id) REFERENCES patients (id),
            FOREIGN KEY (appointment_id) REFERENCES appointments (id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS treatments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            appointment_id INTEGER,
            treatment_name TEXT NOT NULL,
            description TEXT,
            cost REAL DEFAULT 0,
            treatment_date TEXT,
            dentist_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (patient_id) REFERENCES patients (id),
            FOREIGN KEY (appointment_id) REFERENCES appointments (id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS treatment_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            plan_name TEXT NOT NULL,
            goals TEXT,
            estimated_cost REAL,
            status TEXT DEFAULT 'draft',
            start_date TEXT,
            end_date TEXT,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (patient_id) REFERENCES patients (id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS treatment_procedures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            requires_lab INTEGER DEFAULT 0,
            default_price REAL DEFAULT 0,
            default_lab_expense REAL DEFAULT 0,
            active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS patient_followups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            followup_date TEXT,
            tooth_no TEXT,
            diagnosis TEXT,
            treatment_procedure TEXT,
            procedure_id INTEGER,
            price REAL DEFAULT 0,
            discount REAL DEFAULT 0,
            lab_expense REAL DEFAULT 0,
            clinic_profit REAL DEFAULT 0,
            payment REAL DEFAULT 0,
            remaining_amount REAL DEFAULT 0,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (patient_id) REFERENCES patients (id),
            FOREIGN KEY (procedure_id) REFERENCES treatment_procedures (id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            amount REAL NOT NULL,
            expense_date TEXT,
            vendor TEXT,
            notes TEXT,
            payment_status TEXT DEFAULT 'pending',
            patient_id INTEGER,
            treatment_id INTEGER,
            source_type TEXT DEFAULT 'manual',
            reference_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (patient_id) REFERENCES patients (id),
            FOREIGN KEY (treatment_id) REFERENCES treatments (id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS billing (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            treatment_id INTEGER,
            invoice_number TEXT,
            amount REAL NOT NULL,
            subtotal REAL,
            discount REAL DEFAULT 0,
            paid_amount REAL DEFAULT 0,
            balance_due REAL DEFAULT 0,
            payment_method TEXT,
            payment_status TEXT DEFAULT 'pending',
            payment_date TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (patient_id) REFERENCES patients (id),
            FOREIGN KEY (treatment_id) REFERENCES treatments (id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS holidays (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            holiday_date TEXT NOT NULL,
            name TEXT,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS medical_images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            file_name TEXT NOT NULL,
            file_path TEXT NOT NULL,
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            notes TEXT,
            FOREIGN KEY (patient_id) REFERENCES patients (id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS support_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action_type TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id INTEGER,
            details TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            display_name TEXT DEFAULT '',
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login_at TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pairing_requests (
            pair_code TEXT PRIMARY KEY,
            device_name TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TEXT NOT NULL,
            consumed INTEGER DEFAULT 0
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS paired_devices (
            device_id TEXT PRIMARY KEY,
            device_name TEXT NOT NULL,
            device_token TEXT NOT NULL UNIQUE,
            paired_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active INTEGER DEFAULT 1
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sync_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            device_id TEXT,
            table_count INTEGER DEFAULT 0,
            record_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sync_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            entity_type TEXT,
            entity_id INTEGER,
            source_device_id TEXT,
            details TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Records deletions of synced rows so the deletion propagates on the next sync
    # instead of being undone when another device pushes the (now stale) row back.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sync_tombstones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            table_name TEXT NOT NULL,
            row_id INTEGER NOT NULL,
            deleted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(table_name, row_id)
        )
    ''')

    # Multi-tenant registry — only populated in the cloud master DB; harmless
    # (and empty) in a clinic's own single-tenant database.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS clinics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            clinic_name TEXT NOT NULL,
            clinic_token TEXT NOT NULL UNIQUE,
            serial_number TEXT UNIQUE,
            active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_seen_at TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS licenses (
            serial_number TEXT PRIMARY KEY,
            clinic_name TEXT,
            plan_name TEXT DEFAULT 'starter',
            status TEXT DEFAULT 'active',
            max_devices INTEGER DEFAULT 2,
            expires_at TEXT,
            grace_until TEXT,
            activated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS license_devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            serial_number TEXT NOT NULL,
            device_id TEXT NOT NULL,
            device_name TEXT,
            first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active INTEGER DEFAULT 1,
            UNIQUE(serial_number, device_id),
            FOREIGN KEY (serial_number) REFERENCES licenses(serial_number)
        )
    ''')

    # Migration shims: safely add columns that were added after the initial schema
    # (existing databases won't have them; new ones already have them in CREATE TABLE).
    ensure_table_column(cursor, 'expenses', 'payment_status', 'TEXT')
    ensure_table_column(cursor, 'expenses', 'patient_id', 'INTEGER')
    ensure_table_column(cursor, 'expenses', 'treatment_id', 'INTEGER')
    ensure_table_column(cursor, 'expenses', 'source_type', 'TEXT')
    ensure_table_column(cursor, 'expenses', 'reference_id', 'INTEGER')
    ensure_table_column(cursor, 'patient_followups', 'procedure_id', 'INTEGER')
    ensure_table_column(cursor, 'patient_followups', 'lab_expense', 'REAL')
    ensure_table_column(cursor, 'patient_followups', 'clinic_profit', 'REAL')
    ensure_table_column(cursor, 'patient_followups', 'discount', 'REAL DEFAULT 0')
    ensure_table_column(cursor, 'patient_followups', 'remaining_amount', 'REAL')
    ensure_table_column(cursor, 'billing', 'invoice_number', 'TEXT')
    ensure_table_column(cursor, 'billing', 'subtotal', 'REAL')
    ensure_table_column(cursor, 'billing', 'discount', 'REAL')
    ensure_table_column(cursor, 'billing', 'paid_amount', 'REAL')
    ensure_table_column(cursor, 'billing', 'balance_due', 'REAL')
    ensure_table_column(cursor, 'billing', 'payment_status', 'TEXT')
    ensure_table_column(cursor, 'patients', 'updated_at', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP')
    ensure_table_column(cursor, 'appointments', 'updated_at', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP')
    ensure_table_column(cursor, 'visits', 'updated_at', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP')
    ensure_table_column(cursor, 'treatments', 'updated_at', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP')
    ensure_table_column(cursor, 'treatment_plans', 'updated_at', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP')
    ensure_table_column(cursor, 'treatment_procedures', 'updated_at', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP')
    ensure_table_column(cursor, 'patient_followups', 'updated_at', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP')
    ensure_table_column(cursor, 'expenses', 'updated_at', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP')
    ensure_table_column(cursor, 'billing', 'updated_at', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP')
    ensure_table_column(cursor, 'holidays', 'updated_at', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP')

    # New tables for features
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS patient_credit_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            type TEXT NOT NULL,
            note TEXT DEFAULT '',
            invoice_id INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Add missing columns to existing tables
    ensure_table_column(cursor, 'patient_followups', 'is_deleted', 'INTEGER DEFAULT 0')
    ensure_table_column(cursor, 'patient_followups', 'entry_type', "TEXT DEFAULT 'new'")
    ensure_table_column(cursor, 'patient_followups', 'tooth_number', 'TEXT DEFAULT ""')
    ensure_table_column(cursor, 'patients', 'birth_date', 'TEXT DEFAULT ""')
    ensure_table_column(cursor, 'patients', 'gender', 'TEXT DEFAULT ""')
    ensure_table_column(cursor, 'patients', 'notes', 'TEXT DEFAULT ""')
    ensure_table_column(cursor, 'billing', 'credit_used', 'REAL DEFAULT 0')
    ensure_table_column(cursor, 'billing', 'discount_amount', 'REAL DEFAULT 0')
    ensure_table_column(cursor, 'billing', 'remaining_amount', 'REAL DEFAULT 0')
    # Optional raw expression text shown verbatim on the sheet / invoice (e.g. "20+20").
    for _col in ('price_expr', 'discount_expr', 'lab_expense_expr', 'payment_expr'):
        ensure_table_column(cursor, 'patient_followups', _col, 'TEXT')
    for _col in ('subtotal_expr', 'discount_expr', 'paid_amount_expr'):
        ensure_table_column(cursor, 'billing', _col, 'TEXT')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_patient_credit_patient_id ON patient_credit_transactions(patient_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_patient_followups_is_deleted ON patient_followups(is_deleted)')

    cursor.execute('CREATE INDEX IF NOT EXISTS idx_treatment_plans_patient_id ON treatment_plans(patient_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_expenses_date ON expenses(expense_date)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_expenses_status ON expenses(payment_status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_expenses_patient_id ON expenses(patient_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_expenses_treatment_id ON expenses(treatment_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_expenses_source_type ON expenses(source_type)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_expenses_reference_id ON expenses(reference_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_medical_images_patient_id ON medical_images(patient_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_holidays_date ON holidays(holiday_date)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs(created_at)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_audit_logs_entity ON audit_logs(entity_type, entity_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_treatment_procedures_active ON treatment_procedures(active)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_patient_followups_procedure_id ON patient_followups(procedure_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_visits_patient_id ON visits(patient_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_visits_visit_date ON visits(visit_date)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_patient_followups_patient_id ON patient_followups(patient_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_patient_followups_date ON patient_followups(followup_date)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_pairing_requests_expires_at ON pairing_requests(expires_at)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_paired_devices_last_seen_at ON paired_devices(last_seen_at)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_sync_events_created_at ON sync_events(created_at)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_sync_tombstones_deleted_at ON sync_tombstones(deleted_at)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_license_devices_serial_number ON license_devices(serial_number)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_licenses_status ON licenses(status)')

    for table_name in SYNC_TABLES:
        ensure_updated_at_trigger(cursor, table_name)

    default_procedures = [
        ('Checkup', 0, 0, 0),
        ('Cleaning', 0, 200, 0),
        ('Filling', 0, 250, 0),
        ('Root Canal', 0, 600, 0),
        ('Extraction', 0, 300, 0),
        ('Whitening', 0, 800, 0),
        ('Zircon Crown', 1, 700, 300),
        ('Porcelain Crown', 1, 900, 450),
        ('Braces', 1, 3500, 1000),
    ]
    cursor.executemany('''
        INSERT OR IGNORE INTO treatment_procedures (name, requires_lab, default_price, default_lab_expense)
        VALUES (?, ?, ?, ?)
    ''', default_procedures)

    # One-time migration: the legacy "treatment_catalog" was merged into the procedure catalog.
    # If an old database still has that table, copy any custom rows into treatment_procedures
    # (matched by name; duplicates are ignored), then mark the migration done.
    cursor.execute("SELECT value FROM app_settings WHERE key = 'treatment_catalog_migrated'")
    already_migrated = cursor.fetchone()
    if not already_migrated:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='treatment_catalog'")
        if cursor.fetchone():
            cursor.execute('SELECT name_ar, name_en, default_price, is_active FROM treatment_catalog')
            for name_ar, name_en, default_price, is_active in cursor.fetchall():
                name = (name_en or name_ar or '').strip()
                if not name:
                    continue
                cursor.execute('''
                    INSERT OR IGNORE INTO treatment_procedures (name, requires_lab, default_price, default_lab_expense, active)
                    VALUES (?, 0, ?, 0, ?)
                ''', (name, default_price or 0, 1 if is_active else 0))
            cursor.execute('DROP TABLE treatment_catalog')
        cursor.execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES ('treatment_catalog_migrated', '1')")

    cursor.execute('''
        INSERT OR IGNORE INTO app_settings (key, value)
        VALUES ('app_instance_id', ?)
    ''', (str(uuid.uuid4()),))

    cursor.execute('''
        INSERT OR IGNORE INTO app_settings (key, value)
        VALUES ('active_serial_number', '')
    ''')

    cursor.execute('''
        INSERT OR IGNORE INTO app_settings (key, value)
        VALUES ('mobile_android_download_url', '')
    ''')

    cursor.execute('''
        INSERT OR IGNORE INTO app_settings (key, value)
        VALUES ('mobile_ios_download_url', '')
    ''')

    cursor.execute('''
        INSERT OR IGNORE INTO app_settings (key, value)
        VALUES ('license_signing_key', '')
    ''')

    cursor.execute('''
        INSERT OR IGNORE INTO app_settings (key, value)
        VALUES ('doctor_name', ?)
    ''', (CLINIC_CONFIG['DOCTOR_NAME'],))

    cursor.execute('''
        INSERT OR IGNORE INTO app_settings (key, value)
        VALUES ('doctor_name_ar', ?)
    ''', (CLINIC_CONFIG['DOCTOR_NAME_AR'],))

    cursor.execute('''
        INSERT OR IGNORE INTO treatment_procedures (id, name, requires_lab, active)
        VALUES (0, 'مراجعة', 0, 1)
    ''')

    # Seed a default admin account on first run (no users yet). The password can be
    # overridden with the CLINIC_ADMIN_PASSWORD env var; otherwise it defaults to
    # 'admin' and the console prints a reminder to change it from Settings.
    # In CLOUD_MODE the staff portal isn't reachable (every non-/api/* path is
    # redirected to "use your local server"), so seeding a login row would just
    # be a stale credential sitting in the registry — skip it.
    if not CLOUD_MODE:
        cursor.execute('SELECT COUNT(*) FROM users')
        if cursor.fetchone()[0] == 0:
            default_pw = os.environ.get('CLINIC_ADMIN_PASSWORD') or 'admin'
            cursor.execute(
                'INSERT INTO users (username, password_hash, display_name) VALUES (?, ?, ?)',
                ('admin', generate_password_hash(default_pw), 'Administrator')
            )

    conn.commit()
    conn.close()
    print("Database initialized successfully")


def generate_invoice_number():
    return f"INV-{datetime.now().strftime('%Y%m%d%H%M%S')}"


def append_audit_log(cursor, action_type, entity_type, entity_id=None, details=None):
    details_text = ''
    if details is not None:
        if isinstance(details, str):
            details_text = details
        else:
            details_text = json.dumps(details, ensure_ascii=False)
    cursor.execute('''
        INSERT INTO audit_logs (action_type, entity_type, entity_id, details)
        VALUES (?, ?, ?, ?)
    ''', (str(action_type or ''), str(entity_type or ''), entity_id, details_text))


def normalize_datetime_input(value):
    """Deprecated: use normalize_appointment_datetime_input() instead."""
    if not value:
        raise ValueError('Appointment date is required')

    normalized = str(value).strip().replace('T', ' ')
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError('Invalid appointment date format') from exc

    return parsed.strftime('%Y-%m-%d %H:%M:%S')


def normalize_appointment_datetime_input(value):
    if value is None:
        raise ValueError('Appointment date is required')

    raw = str(value).strip()
    if not raw:
        raise ValueError('Appointment date is required')

    separator = 'T' if 'T' in raw else (' ' if ' ' in raw else None)
    if separator is None:
        raise ValueError('Appointment time is required')

    date_part, time_part = raw.split(separator, 1)
    normalized_date = parse_date_input(date_part)
    if not normalized_date:
        raise ValueError('Invalid appointment date format')

    normalized_time_part = str(time_part).strip().replace('T', ' ')
    if not normalized_time_part:
        raise ValueError('Appointment time is required')

    time_token = normalized_time_part.split()[0]
    if ':' not in time_token:
        raise ValueError('Invalid appointment time format')

    candidate = f'{normalized_date} {normalized_time_part}'
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise ValueError('Invalid appointment date format') from exc

    return parsed.strftime('%Y-%m-%d %H:%M:%S')


def is_friday_datetime(value):
    if not value:
        return False

    normalized = str(value).strip().replace('T', ' ')
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return False
    return parsed.weekday() == 4


def normalize_date_input(value):
    if not value:
        return datetime.now().strftime('%Y-%m-%d')

    cleaned = str(value).strip()
    try:
        return datetime.fromisoformat(cleaned.replace('T', ' ')).strftime('%Y-%m-%d')
    except ValueError:
        try:
            return datetime.strptime(cleaned[:10], '%Y-%m-%d').strftime('%Y-%m-%d')
        except ValueError:
            return datetime.now().strftime('%Y-%m-%d')


def parse_date_input(value):
    """Accept YYYY-MM-DD, DD/MM/YYYY, DD-MM-YYYY and return YYYY-MM-DD or None."""
    if not value:
        return None
    cleaned = str(value).strip()
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y'):
        try:
            return datetime.strptime(cleaned[:10], fmt).strftime('%Y-%m-%d')
        except ValueError:
            continue
    return None


def format_date_display(value):
    """Convert YYYY-MM-DD to DD/MM/YYYY for display."""
    if not value:
        return ''
    cleaned = str(value).strip()[:10]
    try:
        return datetime.strptime(cleaned, '%Y-%m-%d').strftime('%d/%m/%Y')
    except ValueError:
        return cleaned


def format_date_input_placeholder():
    """Return DD/MM/YYYY placeholder for date inputs."""
    return 'DD/MM/YYYY'


def normalize_api_date(value):
    """Normalize API date filters to YYYY-MM-DD when possible."""
    if not value:
        return None
    parsed = parse_date_input(value)
    if parsed:
        return parsed
    cleaned = str(value).strip()
    try:
        return datetime.fromisoformat(cleaned[:10].replace('T', ' ')).strftime('%Y-%m-%d')
    except ValueError:
        return None


def appointment_row_to_dict(row):
    if hasattr(row, 'keys'):
        appointment_id = row['id']
        patient_id = row['patient_id']
        appointment_date = row['appointment_date'] or ''
        duration_raw = row['duration']
        treatment_type = row['treatment_type']
        status = row['status']
        notes = row['notes']
        created_at = row['created_at']
        patient_name_raw = row['patient_name'] if 'patient_name' in row.keys() else ''
    else:
        appointment_id = row[0]
        patient_id = row[1]
        appointment_date = row[2] or ''
        duration_raw = row[3]
        treatment_type = row[4]
        status = row[5]
        notes = row[6]
        created_at = row[7] if len(row) > 7 else None
        patient_name_raw = row[-1] if len(row) > 8 else ''

    patient_name = str(patient_name_raw or '').strip() or f'Patient #{patient_id}'
    try:
        duration = int(duration_raw) if duration_raw is not None else 30
    except (TypeError, ValueError):
        duration = 30

    return {
        'id': appointment_id,
        'patient_id': patient_id,
        'appointment_date': appointment_date,
        'appointment_datetime': appointment_date,
        'duration': duration,
        'duration_minutes': duration,
        'treatment_type': treatment_type or '',
        'status': status or 'scheduled',
        'notes': notes or '',
        'created_at': created_at,
        'patient_name': patient_name,
    }


def build_date_clause(column_name, start_date, end_date):
    if start_date and end_date:
        return f' AND date({column_name}) BETWEEN ? AND ?', [start_date, end_date]
    if start_date:
        return f' AND date({column_name}) >= ?', [start_date]
    if end_date:
        return f' AND date({column_name}) <= ?', [end_date]
    return '', []


def calculate_age(birth_date_str):
    """Return integer age from YYYY-MM-DD birth date, or None."""
    if not birth_date_str:
        return None
    parsed = parse_date_input(birth_date_str)
    if not parsed:
        return None
    try:
        dob = datetime.strptime(parsed, '%Y-%m-%d').date()
        today = datetime.now().date()
        return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    except ValueError:
        return None


def get_patient_credit_balance(cursor, patient_id):
    """Return the patient's credit balance — money the clinic is currently holding
    *for* the patient (positive means the clinic owes the patient).

    It's overpayment on the follow-up ledger — ``Σ payment − Σ (price − discount)``
    when that is positive — plus any manual credit adjustments recorded in
    ``patient_credit_transactions`` (signed: positive = added credit, negative = used)."""
    cursor.execute('''
        SELECT COALESCE(SUM(price), 0), COALESCE(SUM(COALESCE(discount, 0)), 0), COALESCE(SUM(payment), 0)
        FROM patient_followups
        WHERE patient_id = ? AND COALESCE(is_deleted, 0) = 0
    ''', (patient_id,))
    total_price, total_discount, total_paid = cursor.fetchone() or (0, 0, 0)
    overpaid = float(total_paid) - (float(total_price) - float(total_discount))
    cursor.execute('SELECT COALESCE(SUM(amount), 0) FROM patient_credit_transactions WHERE patient_id = ?', (patient_id,))
    manual = float(cursor.fetchone()[0] or 0)
    return round(max(0.0, overpaid + manual), 2)


_AMOUNT_EXPR_RE = re.compile(r'^[0-9.+\-*/() ]+$')


def sanitize_amount_expr(raw, numeric_value):
    """If the user typed a real arithmetic expression for an amount (e.g. ``"20+20"``)
    we keep it verbatim so it can be shown on the sheet / invoice. Returns the cleaned
    string only when it (a) is just digits / operators / parens, (b) actually contains
    an operator, and (c) evaluates to the numeric value we stored. Otherwise ``None``."""
    s = str(raw or '').strip()
    if not s or len(s) > 40 or not _AMOUNT_EXPR_RE.match(s):
        return None
    if not re.search(r'[+*/]', s) and not re.search(r'\d\s*-\s*\d', s):
        return None  # a bare number (or just a leading minus) — nothing to preserve
    try:
        val = eval(s, {'__builtins__': {}}, {})  # safe: only digits/operators, no names
    except Exception:
        return None
    if not isinstance(val, (int, float)) or abs(float(val) - float(numeric_value or 0)) > 0.01:
        return None
    return s


def get_authenticated_device(cursor):
    token = request.headers.get('X-Device-Token') or request.args.get('device_token')
    if not token:
        # On the cloud node, the clinic token already validated by
        # _cloud_tenant_routing (which scoped us to this clinic's DB) is itself
        # sufficient authorisation for sync — no separate device pairing needed.
        if CLOUD_MODE and getattr(_request_state, 'db_path', None):
            return {'device_id': 'cloud-clinic-sync', 'device_name': 'cloud sync'}
        return None
    cursor.execute('''
        SELECT device_id, device_name, is_active
        FROM paired_devices
        WHERE device_token = ?
    ''', (token,))
    device = cursor.fetchone()
    if not device or int(device[2]) != 1:
        return None
    cursor.execute('''
        UPDATE paired_devices
        SET last_seen_at = CURRENT_TIMESTAMP
        WHERE device_id = ?
    ''', (device[0],))
    return {'device_id': device[0], 'device_name': device[1]}


def upsert_row(cursor, table_name, row_data):
    table_columns = get_table_columns(cursor, table_name)
    payload = {}
    for key, value in row_data.items():
        if key in table_columns:
            payload[key] = value

    if 'id' not in payload:
        return False

    columns = list(payload.keys())
    placeholders = ', '.join('?' for _ in columns)
    cursor.execute(
        f"INSERT OR REPLACE INTO {table_name} ({', '.join(columns)}) VALUES ({placeholders})",
        tuple(payload[col] for col in columns)
    )
    return True


def record_tombstone(cursor, table_name, row_id, deleted_at=None):
    """Remember that a synced row was deleted.

    Without this, a delete on one device is silently undone the next time another
    device pushes the same row back during sync. Tombstones are kept separately so
    the live tables stay clean (rows are still hard-deleted).
    """
    if table_name not in SYNC_TABLES or row_id is None:
        return
    try:
        row_id = int(row_id)
    except (TypeError, ValueError):
        return
    if deleted_at:
        cursor.execute('''
            INSERT INTO sync_tombstones (table_name, row_id, deleted_at)
            VALUES (?, ?, ?)
            ON CONFLICT(table_name, row_id) DO UPDATE SET deleted_at = excluded.deleted_at
            WHERE excluded.deleted_at > sync_tombstones.deleted_at
        ''', (table_name, row_id, str(deleted_at)))
    else:
        cursor.execute('''
            INSERT INTO sync_tombstones (table_name, row_id, deleted_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(table_name, row_id) DO UPDATE SET deleted_at = CURRENT_TIMESTAMP
        ''', (table_name, row_id))


def parse_timestamp_for_sync(value):
    if not value:
        return datetime.min
    text = str(value).strip().replace('Z', '')
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return datetime.min


def _collect_sync_export(cursor, since_dt=None):
    """Build a sync snapshot from the DB this cursor is connected to.

    Returns (tables, tombstones, total_records). With since_dt, only rows /
    tombstones changed strictly after it are included (an incremental delta).
    Shared by the /api/sync/export route and the cloud-sync worker.
    """
    tables = {}
    total = 0
    for table_name in SYNC_TABLES:
        cursor.execute(f'SELECT * FROM {table_name} ORDER BY id ASC')
        rows = [dict(r) for r in cursor.fetchall()]
        if since_dt is not None:
            rows = [r for r in rows
                    if parse_timestamp_for_sync(r.get('updated_at') or r.get('created_at')) > since_dt]
        tables[table_name] = rows
        total += len(rows)
    cursor.execute('SELECT table_name, row_id, deleted_at FROM sync_tombstones ORDER BY id ASC')
    tombstones = []
    for r in cursor.fetchall():
        t = dict(r)
        if since_dt is not None and parse_timestamp_for_sync(t.get('deleted_at')) <= since_dt:
            continue
        tombstones.append(t)
    return tables, tombstones, total


def _apply_sync_import(cursor, payload):
    """Merge an incoming sync payload ({tables, tombstones}) into the DB this
    cursor is connected to — last-write-wins by updated_at. Caller commits.

    Returns (applied_total, skipped_total, tombstones_applied, by_table). Shared
    by the /api/sync/import route and the cloud-sync worker.
    """
    incoming_tables = payload.get('tables')
    if not isinstance(incoming_tables, dict):
        incoming_tables = {}
    applied_total = skipped_total = 0
    by_table = {}
    for table_name in SYNC_TABLES:
        incoming_rows = incoming_tables.get(table_name, [])
        if not isinstance(incoming_rows, list):
            continue
        applied = skipped = 0
        for row_data in incoming_rows:
            if not isinstance(row_data, dict):
                skipped += 1
                continue
            entity_id = row_data.get('id')
            if entity_id is None:
                skipped += 1
                continue
            cursor.execute(f'SELECT updated_at, created_at FROM {table_name} WHERE id = ?', (entity_id,))
            existing = cursor.fetchone()
            incoming_updated = parse_timestamp_for_sync(row_data.get('updated_at') or row_data.get('created_at'))
            if existing:
                local_updated = parse_timestamp_for_sync(existing['updated_at'] or existing['created_at'])
                if incoming_updated <= local_updated:
                    skipped += 1
                    continue
            else:
                cursor.execute(
                    'SELECT deleted_at FROM sync_tombstones WHERE table_name = ? AND row_id = ?',
                    (table_name, entity_id),
                )
                tomb = cursor.fetchone()
                if tomb:
                    if incoming_updated <= parse_timestamp_for_sync(tomb['deleted_at']):
                        skipped += 1
                        continue
                    cursor.execute(
                        'DELETE FROM sync_tombstones WHERE table_name = ? AND row_id = ?',
                        (table_name, entity_id),
                    )
            try:
                ok = upsert_row(cursor, table_name, row_data)
            except sqlite3.Error:
                # A single malformed row (e.g. NOT NULL violation from an outdated
                # client schema) must not kill the whole batch. Count it and keep going.
                ok = False
            if ok:
                applied += 1
            else:
                skipped += 1
        by_table[table_name] = {'applied': applied, 'skipped': skipped}
        applied_total += applied
        skipped_total += skipped

    incoming_tombstones = payload.get('tombstones')
    if not isinstance(incoming_tombstones, list):
        incoming_tombstones = []
    tombstones_applied = 0
    for tomb in incoming_tombstones:
        if not isinstance(tomb, dict):
            continue
        t_table = tomb.get('table_name')
        t_row_id = tomb.get('row_id')
        t_deleted_at = tomb.get('deleted_at')
        if t_table not in SYNC_TABLES or t_row_id is None:
            continue
        cursor.execute(f'SELECT updated_at, created_at FROM {t_table} WHERE id = ?', (t_row_id,))
        existing = cursor.fetchone()
        if existing:
            local_updated = parse_timestamp_for_sync(existing['updated_at'] or existing['created_at'])
            if local_updated >= parse_timestamp_for_sync(t_deleted_at):
                continue
            cursor.execute(f'DELETE FROM {t_table} WHERE id = ?', (t_row_id,))
            tombstones_applied += 1
        record_tombstone(cursor, t_table, t_row_id, t_deleted_at)
    return applied_total, skipped_total, tombstones_applied, by_table


def _safe_json(text):
    try:
        return json.loads(text or '{}')
    except (ValueError, TypeError):
        return {}


def evaluate_license_window(status, expires_at, grace_until):
    today = _naive_utc_now().date()
    try:
        expires_date = datetime.strptime(str(expires_at), '%Y-%m-%d').date() if expires_at else today
    except ValueError:
        expires_date = today
    try:
        grace_date = datetime.strptime(str(grace_until), '%Y-%m-%d').date() if grace_until else expires_date
    except ValueError:
        grace_date = expires_date

    in_grace = today > expires_date and today <= grace_date
    licensed = str(status or '') == 'active' and (today <= expires_date or in_grace)
    return {
        'licensed': licensed,
        'in_grace': in_grace,
        'expires_date': expires_date.isoformat(),
        'grace_date': grace_date.isoformat()
    }


def fetch_license_record(cursor, serial_number):
    cursor.execute('''
        SELECT serial_number, clinic_name, plan_name, status, max_devices, expires_at, grace_until
        FROM licenses
        WHERE serial_number = ?
    ''', (serial_number,))
    row = cursor.fetchone()
    if not row:
        return None
    return {
        'serial_number': row[0],
        'clinic_name': row[1],
        'plan_name': row[2],
        'status': row[3],
        'max_devices': row[4],
        'expires_at': row[5],
        'grace_until': row[6]
    }


def get_mobile_download_options(cursor):
    android_setting = str(read_app_setting(cursor, 'mobile_android_download_url', '') or '').strip()
    ios_setting = str(read_app_setting(cursor, 'mobile_ios_download_url', '') or '').strip()

    android_url = android_setting or '/downloads/android'
    ios_url = ios_setting or '/downloads/ios'

    android_available = bool(android_setting) or MOBILE_ANDROID_PACKAGE_PATH.exists()
    ios_available = bool(ios_setting) or MOBILE_IOS_PACKAGE_PATH.exists()

    return {
        'android': {
            'platform': 'android',
            'label': 'Android',
            'url': android_url,
            'available': android_available
        },
        'ios': {
            'platform': 'ios',
            'label': 'iOS',
            'url': ios_url,
            'available': ios_available
        }
    }


# ── Clinic Branding Config ──────────────────────────────────────────────────
# Edit these values to customise the system name, clinic name, and doctor name.
# These are injected into the HTML template and the JS translation tables.
CLINIC_CONFIG = {
    'SYSTEM_NAME':   'DentaCare',
    'CLINIC_NAME':   'Dental Management System',
    'DOCTOR_NAME':   'Dr. Wasfy Barzaq',
    'DOCTOR_NAME_AR': 'د. وصفي برزق',
    'CLINIC_TAGLINE': 'Patient Care & Practice Management',
}
# ─────────────────────────────────────────────────────────────────────────────

# HTML templates extracted to templates.py (see that module).
from templates import HTML_TEMPLATE, MOBILE_PORTAL_TEMPLATE, LOGIN_TEMPLATE


def _safe_next_url(target):
    """Return target only if it is a safe same-site path, else empty string."""
    if not target or not target.startswith('/'):
        return ''
    if target.startswith('//') or target.startswith('/\\'):
        return ''
    return target


# Browser-facing endpoints that require a logged-in staff session. The data/sync
# REST API and mobile/license/pairing endpoints are intentionally left open so the
# offline-first mobile app keeps working unchanged.
_AUTH_REQUIRED_EXACT = {'/', '/api/backup', '/api/bt/status', '/api/bt/configure'}
_AUTH_REQUIRED_PREFIXES = ('/invoice/',)


@app.before_request
def _require_login_for_portal():
    if request.method == 'OPTIONS':
        return None
    path = request.path or '/'
    if path not in _AUTH_REQUIRED_EXACT and not path.startswith(_AUTH_REQUIRED_PREFIXES):
        return None
    if session.get('uid'):
        return None
    if path.startswith('/api/'):
        return jsonify({'error': 'Authentication required'}), 401
    return redirect(url_for('login_page', next=path))


@app.route('/login', methods=['GET', 'POST'])
def login_page():
    next_url = _safe_next_url(request.values.get('next', ''))
    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        password = request.form.get('password') or ''
        conn = sqlite3.connect(DB_NAME)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE username = ? AND is_active = 1', (username,))
        user = cursor.fetchone()
        if user and check_password_hash(user['password_hash'], password):
            cursor.execute('UPDATE users SET last_login_at = CURRENT_TIMESTAMP WHERE id = ?', (user['id'],))
            conn.commit()
            conn.close()
            session.clear()
            session['uid'] = user['id']
            session['uname'] = user['username']
            return redirect(next_url or url_for('index'))
        conn.close()
        return render_template_string(LOGIN_TEMPLATE, error='Invalid username or password.', next_url=next_url), 401
    if session.get('uid'):
        return redirect(next_url or url_for('index'))
    return render_template_string(LOGIN_TEMPLATE, error=None, next_url=next_url)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login_page'))


@app.route('/api/auth/me')
def auth_me():
    return jsonify({'authenticated': bool(session.get('uid')), 'username': session.get('uname', '')})


@app.route('/api/auth/change-password', methods=['POST'])
def auth_change_password():
    if not session.get('uid'):
        return jsonify({'error': 'Authentication required'}), 401
    data = request.json or {}
    current = data.get('current_password') or ''
    new = data.get('new_password') or ''
    if len(new) < 4:
        return jsonify({'error': 'New password must be at least 4 characters.'}), 400
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE id = ?', (session['uid'],))
    user = cursor.fetchone()
    if not user or not check_password_hash(user['password_hash'], current):
        conn.close()
        return jsonify({'error': 'Current password is incorrect.'}), 400
    cursor.execute('UPDATE users SET password_hash = ? WHERE id = ?', (generate_password_hash(new), user['id']))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE, **CLINIC_CONFIG)


@app.route('/logo')
def serve_logo():
    logo_path = _BUNDLE_DIR / 'DentaCare.PNG'
    if logo_path.exists():
        return send_file(str(logo_path), mimetype='image/png')
    return ('', 204)


@app.route('/mobile-download')
def mobile_download():
    return render_template_string(MOBILE_PORTAL_TEMPLATE)


@app.route('/downloads/android')
def download_android_package():
    if not MOBILE_ANDROID_PACKAGE_PATH.exists():
        return jsonify({'error': 'Android package is not uploaded yet'}), 404
    return send_file(
        MOBILE_ANDROID_PACKAGE_PATH,
        as_attachment=True,
        download_name='clinic-mobile-android.apk'
    )


@app.route('/downloads/ios')
def download_ios_package():
    if not MOBILE_IOS_PACKAGE_PATH.exists():
        return jsonify({'error': 'iOS package is not uploaded yet'}), 404
    return send_file(
        MOBILE_IOS_PACKAGE_PATH,
        as_attachment=True,
        download_name='clinic-mobile-ios.ipa'
    )

# API Routes
@app.route('/api/stats')
def get_stats():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Total patients
    cursor.execute('SELECT COUNT(*) FROM patients')
    total_patients = cursor.fetchone()[0]
    
    # Total appointments
    cursor.execute('SELECT COUNT(*) FROM appointments')
    total_appointments = cursor.fetchone()[0]
    
    # Today's appointments
    today = datetime.now().date()
    cursor.execute('SELECT COUNT(*) FROM appointments WHERE DATE(appointment_date) = ?', (today,))
    today_appointments = cursor.fetchone()[0]

    # Today's visits = follow-up sheet entries dated today (the `visits` table is unused;
    # the follow-up sheet is where visits are actually recorded).
    cursor.execute(
        'SELECT COUNT(*) FROM patient_followups WHERE date(followup_date) = ? AND COALESCE(is_deleted, 0) = 0',
        (today,))
    total_visits = cursor.fetchone()[0]

    # Today's revenue = follow-up payments collected today.
    cursor.execute(
        'SELECT COALESCE(SUM(payment), 0) FROM patient_followups WHERE date(followup_date) = ? AND COALESCE(is_deleted, 0) = 0',
        (today,))
    total_revenue = cursor.fetchone()[0]
    
    conn.close()
    
    return jsonify({
        'total_patients': total_patients,
        'total_appointments': total_appointments,
        'today_appointments': today_appointments,
        'total_visits': total_visits,
        'total_revenue': float(total_revenue or 0)
    })

@app.route('/api/patients', methods=['GET', 'POST'])
def patients():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    if request.method == 'GET':
        cursor.execute('SELECT * FROM patients ORDER BY id DESC')
        patients_list = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return jsonify(patients_list)
    
    else:  # POST
        data = request.json or {}
        if not data.get('first_name') or not data.get('last_name'):
            conn.close()
            return jsonify({'error': 'First name and last name are required'}), 400
        birth_date = data.get('date_of_birth')
        if birth_date:
            parsed_date = parse_date_input(birth_date)
            if not parsed_date:
                conn.close()
                return jsonify({'error': 'Invalid date of birth format. Use DD/MM/YYYY.'}), 400
            birth_date = parsed_date
        cursor.execute('''
            INSERT INTO patients (first_name, last_name, date_of_birth, phone, email, address, medical_history)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (data['first_name'], data['last_name'], birth_date,
              data.get('phone'), data.get('email'), data.get('address'), data.get('medical_history')))
        conn.commit()
        conn.close()
        return jsonify({'success': True})

@app.route('/api/patients/check-duplicate', methods=['GET'])
def check_patient_duplicate():
    first_name = (request.args.get('first_name') or '').strip()
    last_name  = (request.args.get('last_name')  or '').strip()
    phone      = (request.args.get('phone')      or '').strip()
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    name_matches, phone_matches = [], []
    if first_name and last_name:
        cursor.execute('''
            SELECT id, first_name, last_name, phone
            FROM patients
            WHERE LOWER(first_name) = LOWER(?) AND LOWER(last_name) = LOWER(?)
        ''', (first_name, last_name))
        name_matches = [dict(r) for r in cursor.fetchall()]
    if phone:
        cursor.execute('''
            SELECT id, first_name, last_name, phone
            FROM patients
            WHERE phone = ? AND phone != ''
        ''', (phone,))
        phone_matches = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return jsonify({'name_matches': name_matches, 'phone_matches': phone_matches})

@app.route('/api/patients/<int:patient_id>', methods=['DELETE'])
def delete_patient(patient_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # Soft-delete dependent records first to avoid orphans
    cursor.execute('UPDATE patient_followups SET is_deleted = 1 WHERE patient_id = ?', (patient_id,))
    cursor.execute('DELETE FROM patients WHERE id = ?', (patient_id,))
    record_tombstone(cursor, 'patients', patient_id)
    append_audit_log(cursor, 'delete', 'patient', patient_id, {'patient_id': patient_id})
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/patients/<int:patient_id>/full-profile')
def patient_full_profile(patient_id):
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute('SELECT * FROM patients WHERE id = ?', (patient_id,))
    patient = cursor.fetchone()
    if not patient:
        conn.close()
        return jsonify({'error': 'Patient not found'}), 404

    def fetch_all(query, params=()):
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

    profile = {
        'patient': dict(patient),
        'appointments': fetch_all('''
            SELECT * FROM appointments WHERE patient_id = ? ORDER BY appointment_date DESC
        ''', (patient_id,)),
        'visits': fetch_all('''
            SELECT * FROM visits WHERE patient_id = ? ORDER BY visit_date DESC
        ''', (patient_id,)),
        'treatments': fetch_all('''
            SELECT * FROM treatments WHERE patient_id = ? ORDER BY id DESC
        ''', (patient_id,)),
        'billing': fetch_all('''
            SELECT * FROM billing WHERE patient_id = ? ORDER BY id DESC
        ''', (patient_id,)),
        'treatment_plans': fetch_all('''
            SELECT * FROM treatment_plans WHERE patient_id = ? ORDER BY id DESC
        ''', (patient_id,)),
        'followups': fetch_all('''
            SELECT pf.*, tp.requires_lab as procedure_requires_lab
            FROM patient_followups pf
            LEFT JOIN treatment_procedures tp ON tp.id = pf.procedure_id
            WHERE pf.patient_id = ? AND COALESCE(pf.is_deleted, 0) = 0
            ORDER BY pf.followup_date DESC, pf.id DESC
        ''', (patient_id,)),
        'medical_images': fetch_all('''
            SELECT * FROM medical_images WHERE patient_id = ? ORDER BY uploaded_at DESC
        ''', (patient_id,))
    }
    profile['age'] = calculate_age(dict(patient).get('date_of_birth'))
    profile['birth_date_display'] = format_date_display(dict(patient).get('date_of_birth'))
    profile['credit_balance'] = get_patient_credit_balance(cursor, patient_id)
    conn.close()
    return jsonify(profile)

@app.route('/api/treatment-procedures', methods=['GET', 'POST'])
def treatment_procedures_collection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    if request.method == 'GET':
        include_inactive = str(request.args.get('include_inactive', '0')).strip() in ('1', 'true', 'True')
        if include_inactive:
            cursor.execute('''
                SELECT id, name, requires_lab, default_price, default_lab_expense, active, created_at
                FROM treatment_procedures
                ORDER BY name COLLATE NOCASE ASC
            ''')
        else:
            cursor.execute('''
                SELECT id, name, requires_lab, default_price, default_lab_expense, active, created_at
                FROM treatment_procedures
                WHERE active = 1
                ORDER BY name COLLATE NOCASE ASC
            ''')
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return jsonify(rows)

    data = request.json or {}
    name = str(data.get('name') or '').strip()
    if not name:
        conn.close()
        return jsonify({'error': 'Procedure name is required'}), 400

    requires_lab = 1 if str(data.get('requires_lab', '0')).strip() in ('1', 'true', 'True', 'on') else 0

    def as_float(value, default=0):
        try:
            if value in (None, ''):
                return float(default)
            return float(value)
        except (TypeError, ValueError):
            return float(default)

    default_price = as_float(data.get('default_price'))
    default_lab_expense = as_float(data.get('default_lab_expense'))

    try:
        cursor.execute('''
            INSERT INTO treatment_procedures (name, requires_lab, default_price, default_lab_expense, active)
            VALUES (?, ?, ?, ?, 1)
        ''', (name, requires_lab, default_price, default_lab_expense))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'error': 'Procedure already exists'}), 409

    conn.close()
    return jsonify({'success': True})

@app.route('/api/treatment-procedures/<int:procedure_id>', methods=['PUT'])
def treatment_procedure_update(procedure_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    data = request.json or {}

    def as_float(value, default=0):
        try:
            if value in (None, ''):
                return float(default)
            return float(value)
        except (TypeError, ValueError):
            return float(default)

    name = str(data.get('name') or '').strip()
    if not name:
        conn.close()
        return jsonify({'error': 'Procedure name is required'}), 400

    requires_lab = 1 if str(data.get('requires_lab', '0')).strip() in ('1', 'true', 'True', 'on') else 0
    active = 1 if str(data.get('active', '1')).strip() in ('1', 'true', 'True', 'on') else 0

    try:
        cursor.execute('''
            UPDATE treatment_procedures
            SET name = ?, requires_lab = ?, default_price = ?, default_lab_expense = ?, active = ?
            WHERE id = ?
        ''', (name, requires_lab, as_float(data.get('default_price')), as_float(data.get('default_lab_expense')), active, procedure_id))
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'error': 'Procedure already exists'}), 409

    if cursor.rowcount == 0:
        conn.close()
        return jsonify({'error': 'Procedure not found'}), 404

    conn.commit()
    conn.close()
    return jsonify({'success': True})

def _recompute_followup_balances(cursor, patient_id):
    """Rewrite every follow-up row's ``remaining_amount`` as the true running ledger
    balance — the cumulative ``Σ (price − discount − payment)`` walked in chronological
    order. This keeps the "amount to pay" column correct after entries are edited,
    deleted, or added out of date order (the value can't be a per-row snapshot)."""
    cursor.execute('''
        SELECT id, COALESCE(price, 0), COALESCE(discount, 0), COALESCE(payment, 0), COALESCE(remaining_amount, 0)
        FROM patient_followups
        WHERE patient_id = ? AND COALESCE(is_deleted, 0) = 0
        ORDER BY date(followup_date) ASC, id ASC
    ''', (patient_id,))
    running = 0.0
    stale = []
    for fid, price, discount, payment, stored in cursor.fetchall():
        running += float(price) - float(discount) - float(payment)
        new_amount = round(running, 2)
        if abs(new_amount - float(stored)) > 0.005:
            stale.append((new_amount, fid))
    for amount, fid in stale:
        cursor.execute('UPDATE patient_followups SET remaining_amount = ? WHERE id = ?', (amount, fid))


@app.route('/api/patients/<int:patient_id>/followups', methods=['GET', 'POST'])
def patient_followups(patient_id):
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute('SELECT id, first_name, last_name FROM patients WHERE id = ?', (patient_id,))
    patient_row = cursor.fetchone()
    if not patient_row:
        conn.close()
        return jsonify({'error': 'Patient not found'}), 404

    patient_full_name = f"{patient_row['first_name']} {patient_row['last_name']}".strip()

    if request.method == 'GET':
        # Self-heal stored running balances, then return rows in chronological order.
        _recompute_followup_balances(cursor, patient_id)
        conn.commit()
        cursor.execute('''
            SELECT pf.*, tp.requires_lab as procedure_requires_lab
            FROM patient_followups pf
            LEFT JOIN treatment_procedures tp ON tp.id = pf.procedure_id
            WHERE pf.patient_id = ? AND COALESCE(pf.is_deleted, 0) = 0
            ORDER BY pf.followup_date ASC, pf.id ASC
        ''', (patient_id,))
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return jsonify(rows)

    data = request.json or {}

    def as_float(value, default=0):
        try:
            if value in (None, ''):
                return float(default)
            return float(value)
        except (TypeError, ValueError):
            return float(default)

    cursor.execute('''
        SELECT COALESCE(SUM(price), 0), COALESCE(SUM(COALESCE(discount,0)), 0), COALESCE(SUM(payment), 0)
        FROM patient_followups
        WHERE patient_id = ? AND COALESCE(is_deleted, 0) = 0
    ''', (patient_id,))
    previous_totals = cursor.fetchone() or (0, 0, 0)
    previous_balance = max(as_float(previous_totals[0]) - as_float(previous_totals[1]) - as_float(previous_totals[2]), 0)

    price = as_float(data.get('price'))
    discount = as_float(data.get('discount'))
    payment = as_float(data.get('payment'))
    lab_expense = as_float(data.get('lab_expense'))
    # Clinic profit is the net the clinic actually earns: price minus the discount
    # given to the patient, minus the lab cost. (Payment only moves the balance.)
    clinic_profit = price - discount - lab_expense
    remaining_amount = max(previous_balance + price - discount - payment, 0)

    procedure_id = data.get('procedure_id')
    try:
        procedure_id = int(procedure_id) if procedure_id not in (None, '') else None
    except (TypeError, ValueError):
        procedure_id = None

    treatment_procedure = str(data.get('treatment_procedure') or '').strip()
    requires_lab = False

    if procedure_id:
        cursor.execute('''
            SELECT id, name, requires_lab
            FROM treatment_procedures
            WHERE id = ? AND active = 1
        ''', (procedure_id,))
        procedure_row = cursor.fetchone()
        if procedure_row:
            treatment_procedure = procedure_row['name']
            requires_lab = bool(procedure_row['requires_lab'])
        else:
            procedure_id = None

    if not treatment_procedure:
        conn.close()
        return jsonify({'error': 'Treatment procedure is required'}), 400

    price_expr = sanitize_amount_expr(data.get('price_expr'), price)
    discount_expr = sanitize_amount_expr(data.get('discount_expr'), discount)
    payment_expr = sanitize_amount_expr(data.get('payment_expr'), payment)
    lab_expense_expr = sanitize_amount_expr(data.get('lab_expense_expr'), lab_expense) if requires_lab else None

    if not requires_lab:
        lab_expense = 0
        clinic_profit = price - discount

    # Parse followup date to ensure YYYY-MM-DD format
    followup_date = data.get('followup_date')
    if not followup_date:
        conn.close()
        return jsonify({'error': 'Followup date is required'}), 400

    parsed_followup_date = parse_date_input(followup_date)
    if not parsed_followup_date:
        conn.close()
        return jsonify({'error': 'Invalid followup date format. Use DD/MM/YYYY.'}), 400

    cursor.execute('''
        INSERT INTO patient_followups (
            patient_id, followup_date, tooth_no, diagnosis, treatment_procedure, procedure_id,
            price, discount, lab_expense, clinic_profit, payment, remaining_amount, notes,
            price_expr, discount_expr, lab_expense_expr, payment_expr
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        patient_id,
        parsed_followup_date,
        data.get('tooth_no'),
        data.get('diagnosis'),
        treatment_procedure,
        procedure_id,
        price,
        discount,
        lab_expense,
        clinic_profit,
        payment,
        remaining_amount,
        data.get('notes'),
        price_expr,
        discount_expr,
        lab_expense_expr,
        payment_expr
    ))

    followup_id = cursor.lastrowid

    append_audit_log(cursor, 'create', 'patient_followup', followup_id, {
        'patient_id': patient_id,
        'treatment_procedure': treatment_procedure,
        'price': price,
        'payment': payment,
        'lab_expense': lab_expense,
        'clinic_profit': clinic_profit,
        'followup_date': followup_date
    })

    if requires_lab and lab_expense > 0:
        cursor.execute('''
            INSERT INTO expenses (
                category, amount, expense_date, vendor, notes,
                payment_status, patient_id, source_type, reference_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            treatment_procedure,
            lab_expense,
            parsed_followup_date,
            patient_full_name,
            f"Auto from follow-up: {patient_full_name} - {treatment_procedure}",
            'postponed',
            patient_id,
            'followup',
            followup_id
        ))
        append_audit_log(cursor, 'create', 'expense', cursor.lastrowid, {
            'source_type': 'followup',
            'reference_id': followup_id,
            'patient_id': patient_id,
            'category': treatment_procedure,
            'amount': lab_expense
        })

    _recompute_followup_balances(cursor, patient_id)
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/patients/<int:patient_id>/followups/<int:followup_id>', methods=['DELETE', 'PUT'])
def followup_detail(patient_id, followup_id):
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    if request.method == 'DELETE':
        cursor.execute(
            'UPDATE patient_followups SET is_deleted = 1 WHERE id = ? AND patient_id = ?',
            (followup_id, patient_id)
        )
        if cursor.rowcount == 0:
            conn.close()
            return jsonify({'error': 'Follow-up not found'}), 404
        # Auto-created lab expense (if any) for this entry should go too.
        cursor.execute(
            "SELECT id FROM expenses WHERE source_type = 'followup' AND reference_id = ?",
            (followup_id,)
        )
        for (exp_id,) in cursor.fetchall():
            cursor.execute('DELETE FROM expenses WHERE id = ?', (exp_id,))
            record_tombstone(cursor, 'expenses', exp_id)
        append_audit_log(cursor, 'delete', 'patient_followup', followup_id, {'patient_id': patient_id})
        _recompute_followup_balances(cursor, patient_id)
        conn.commit()
        conn.close()
        return jsonify({'success': True})

    # PUT — update existing followup
    data = request.json or {}

    def as_float(value, default=0):
        try:
            if value in (None, ''):
                return float(default)
            return float(value)
        except (TypeError, ValueError):
            return float(default)

    followup_date = data.get('followup_date')
    if not followup_date:
        conn.close()
        return jsonify({'error': 'Followup date is required'}), 400
    parsed_date = parse_date_input(followup_date)
    if not parsed_date:
        conn.close()
        return jsonify({'error': 'Invalid followup date format. Use DD/MM/YYYY.'}), 400

    price = as_float(data.get('price'))
    discount = as_float(data.get('discount'))
    payment = as_float(data.get('payment'))
    lab_expense = as_float(data.get('lab_expense'))
    # Recompute clinic profit server-side: price − discount − lab cost.
    clinic_profit = price - discount - lab_expense

    price_expr = sanitize_amount_expr(data.get('price_expr'), price)
    discount_expr = sanitize_amount_expr(data.get('discount_expr'), discount)
    payment_expr = sanitize_amount_expr(data.get('payment_expr'), payment)
    lab_expense_expr = sanitize_amount_expr(data.get('lab_expense_expr'), lab_expense)

    treatment_procedure = data.get('treatment_procedure')
    # remaining_amount is rewritten by _recompute_followup_balances below; store a placeholder.
    cursor.execute('''
        UPDATE patient_followups
        SET followup_date = ?, treatment_procedure = ?, price = ?, discount = ?, lab_expense = ?,
            clinic_profit = ?, payment = ?, notes = ?,
            price_expr = ?, discount_expr = ?, lab_expense_expr = ?, payment_expr = ?
        WHERE id = ? AND patient_id = ?
    ''', (
        parsed_date, treatment_procedure, price, discount, lab_expense,
        clinic_profit, payment, data.get('notes'),
        price_expr, discount_expr, lab_expense_expr, payment_expr,
        followup_id, patient_id
    ))
    if cursor.rowcount == 0:
        conn.close()
        return jsonify({'error': 'Follow-up not found'}), 404

    # Keep the auto-created lab expense in sync with the edited entry.
    cursor.execute("SELECT id FROM expenses WHERE source_type = 'followup' AND reference_id = ?", (followup_id,))
    for (exp_id,) in cursor.fetchall():
        cursor.execute('DELETE FROM expenses WHERE id = ?', (exp_id,))
        record_tombstone(cursor, 'expenses', exp_id)
    if lab_expense > 0:
        cursor.execute('SELECT first_name, last_name FROM patients WHERE id = ?', (patient_id,))
        prow = cursor.fetchone()
        pname = f"{prow['first_name']} {prow['last_name']}".strip() if prow else ''
        cursor.execute('''
            INSERT INTO expenses (
                category, amount, expense_date, vendor, notes,
                payment_status, patient_id, source_type, reference_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            treatment_procedure or 'Lab', lab_expense, parsed_date, pname,
            f"Auto from follow-up: {pname} - {treatment_procedure or ''}",
            'postponed', patient_id, 'followup', followup_id
        ))

    append_audit_log(cursor, 'update', 'patient_followup', followup_id, {
        'patient_id': patient_id,
        'treatment_procedure': treatment_procedure,
        'price': price,
        'payment': payment,
    })
    _recompute_followup_balances(cursor, patient_id)
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/appointments', methods=['GET', 'POST'])
def appointments():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    if request.method == 'GET':
        cursor.execute('''
            SELECT a.*, p.first_name || ' ' || p.last_name as patient_name
            FROM appointments a
            JOIN patients p ON a.patient_id = p.id
            ORDER BY datetime(a.appointment_date) DESC, a.id DESC
        ''')
        appointments = [appointment_row_to_dict(row) for row in cursor.fetchall()]
        conn.close()
        return jsonify(appointments)
    
    else:  # POST
        data = request.get_json(silent=True) or {}
        try:
            patient_id = int(data.get('patient_id'))
        except (TypeError, ValueError):
            conn.close()
            return jsonify({'error': 'Valid patient is required'}), 400

        try:
            duration = int(data.get('duration', 30))
        except (TypeError, ValueError):
            conn.close()
            return jsonify({'error': 'Duration must be a number'}), 400

        if duration <= 0 or duration > 480:
            conn.close()
            return jsonify({'error': 'Duration must be between 1 and 480 minutes'}), 400

        appointment_date_raw = data.get('appointment_date')
        if appointment_date_raw is None:
            appointment_date_raw = data.get('appointment_datetime')

        try:
            appointment_date = normalize_appointment_datetime_input(appointment_date_raw)
        except ValueError as exc:
            conn.close()
            return jsonify({'error': str(exc)}), 400

        if is_friday_datetime(appointment_date):
            conn.close()
            return jsonify({'error': 'Friday is a permanent holiday'}), 400

        cursor.execute('SELECT id FROM patients WHERE id = ?', (patient_id,))
        if not cursor.fetchone():
            conn.close()
            return jsonify({'error': 'Patient not found'}), 404

        cursor.execute('''
            SELECT a.id, a.appointment_date, a.duration,
                   p.first_name || ' ' || p.last_name as patient_name
            FROM appointments a
            JOIN patients p ON a.patient_id = p.id
            WHERE a.status = 'scheduled'
              AND datetime(?) < datetime(a.appointment_date, '+' || a.duration || ' minutes')
              AND datetime(?, '+' || ? || ' minutes') > datetime(a.appointment_date)
            ORDER BY a.appointment_date ASC
            LIMIT 1
        ''', (appointment_date, appointment_date, duration))
        conflict = cursor.fetchone()
        if conflict:
            conn.close()
            return jsonify({
                'error': f"Conflict with appointment #{conflict[0]} ({conflict[3]}) at {conflict[1]}",
                'conflict': {
                    'appointment_id': conflict[0],
                    'patient_name': conflict[3],
                    'appointment_date': conflict[1],
                    'duration': conflict[2]
                }
            }), 409

        status_raw = str(data.get('status') or 'scheduled').strip().lower()
        status = status_raw if status_raw in ('scheduled', 'confirmed', 'cancelled', 'completed') else 'scheduled'

        cursor.execute('''
            INSERT INTO appointments (patient_id, appointment_date, duration, treatment_type, status, notes)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (patient_id, appointment_date, duration,
              data.get('treatment_type'), status, data.get('notes')))
        appointment_id = cursor.lastrowid

        cursor.execute('''
            SELECT a.*, p.first_name || ' ' || p.last_name as patient_name
            FROM appointments a
            JOIN patients p ON a.patient_id = p.id
            WHERE a.id = ?
        ''', (appointment_id,))
        created = cursor.fetchone()
        conn.commit()
        conn.close()
        return jsonify(appointment_row_to_dict(created))

@app.route('/api/appointments/recent')
def recent_appointments():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT a.*, p.first_name || ' ' || p.last_name as patient_name
        FROM appointments a
        JOIN patients p ON a.patient_id = p.id
        ORDER BY datetime(a.appointment_date) DESC, a.id DESC
        LIMIT 10
    ''')
    appointments = [appointment_row_to_dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify(appointments)

@app.route('/api/appointments/<int:appointment_id>/status', methods=['PUT'])
def update_appointment_status(appointment_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    data = request.get_json(silent=True) or {}
    status = str(data.get('status') or '').strip().lower()
    if status not in {'scheduled', 'confirmed', 'completed', 'cancelled'}:
        conn.close()
        return jsonify({'error': 'Invalid appointment status'}), 400
    cursor.execute('UPDATE appointments SET status = ? WHERE id = ?', (status, appointment_id))
    if cursor.rowcount == 0:
        conn.close()
        return jsonify({'error': 'Appointment not found'}), 404
    conn.commit()
    conn.close()
    return jsonify({'success': True})


@app.route('/api/appointments/<int:appointment_id>', methods=['DELETE'])
def delete_appointment(appointment_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM appointments WHERE id = ?', (appointment_id,))
    if cursor.rowcount == 0:
        conn.close()
        return jsonify({'error': 'Appointment not found'}), 404
    record_tombstone(cursor, 'appointments', appointment_id)
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/treatment-plans', methods=['GET', 'POST'])
def treatment_plans():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    if request.method == 'GET':
        cursor.execute('''
            SELECT tp.*, p.first_name || ' ' || p.last_name as patient_name
            FROM treatment_plans tp
            JOIN patients p ON tp.patient_id = p.id
            ORDER BY tp.id DESC
        ''')
        plans = []
        for row in cursor.fetchall():
            plans.append({
                'id': row[0],
                'patient_id': row[1],
                'plan_name': row[2],
                'goals': row[3],
                'estimated_cost': row[4],
                'status': row[5],
                'start_date': row[6],
                'end_date': row[7],
                'notes': row[8],
                'created_at': row[9],
                'patient_name': row[10]
            })
        conn.close()
        return jsonify(plans)

    data = request.json or {}
    if not data.get('patient_id') or not data.get('plan_name'):
        conn.close()
        return jsonify({'error': 'patient_id and plan_name are required'}), 400
    cursor.execute('''
        INSERT INTO treatment_plans (patient_id, plan_name, goals, estimated_cost, status, start_date, end_date, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        data['patient_id'], data['plan_name'], data.get('goals'), data.get('estimated_cost'),
        data.get('status', 'draft'), data.get('start_date'), data.get('end_date'), data.get('notes')
    ))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/treatment-plans/<int:plan_id>', methods=['PUT', 'DELETE'])
def treatment_plan_detail(plan_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    if request.method == 'DELETE':
        cursor.execute('DELETE FROM treatment_plans WHERE id = ?', (plan_id,))
        record_tombstone(cursor, 'treatment_plans', plan_id)
        conn.commit()
        conn.close()
        return jsonify({'success': True})

    data = request.json or {}
    if not data.get('plan_name'):
        conn.close()
        return jsonify({'error': 'plan_name is required'}), 400
    cursor.execute('''
        UPDATE treatment_plans
        SET plan_name = ?, goals = ?, estimated_cost = ?, status = ?, start_date = ?, end_date = ?, notes = ?
        WHERE id = ?
    ''', (
        data['plan_name'], data.get('goals'), data.get('estimated_cost'), data.get('status', 'draft'),
        data.get('start_date'), data.get('end_date'), data.get('notes'), plan_id
    ))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/expenses', methods=['GET', 'POST'])
def expenses():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    if request.method == 'GET':
        cursor.execute('SELECT id, category, amount, expense_date, vendor, notes, payment_status, created_at FROM expenses ORDER BY expense_date DESC, id DESC')
        rows = []
        for row in cursor.fetchall():
            rows.append({
                'id': row[0],
                'category': row[1],
                'amount': row[2],
                'expense_date': row[3],
                'vendor': row[4],
                'notes': row[5],
                'payment_status': row[6] or 'pending',
                'created_at': row[7]
            })
        conn.close()
        return jsonify(rows)

    data = request.get_json(silent=True) or {}
    if not data.get('category'):
        conn.close()
        return jsonify({'error': 'category is required'}), 400
    try:
        amount = float(data.get('amount', 0))
    except (TypeError, ValueError):
        conn.close()
        return jsonify({'error': 'amount must be a number'}), 400
    if amount <= 0:
        conn.close()
        return jsonify({'error': 'amount must be greater than zero'}), 400

    # Parse expense date to ensure YYYY-MM-DD format
    expense_date = data.get('expense_date')
    if expense_date:
        parsed_date = parse_date_input(expense_date)
        if not parsed_date:
            conn.close()
            return jsonify({'error': 'Invalid expense date format. Use DD/MM/YYYY.'}), 400
        expense_date = parsed_date
    
    cursor.execute('''
        INSERT INTO expenses (category, amount, expense_date, vendor, notes, payment_status)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (data['category'], data['amount'], expense_date, data.get('vendor'), data.get('notes'), data.get('payment_status', 'pending')))
    append_audit_log(cursor, 'create', 'expense', cursor.lastrowid, {
        'source_type': 'manual',
        'category': data.get('category'),
        'amount': data.get('amount'),
        'payment_status': data.get('payment_status', 'pending')
    })
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/expenses/<int:expense_id>', methods=['DELETE', 'PUT'])
def delete_or_update_expense(expense_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    if request.method == 'DELETE':
        cursor.execute('DELETE FROM expenses WHERE id = ?', (expense_id,))
        record_tombstone(cursor, 'expenses', expense_id)
        append_audit_log(cursor, 'delete', 'expense', expense_id, {'id': expense_id})
    else:  # PUT
        data = request.json
        if 'payment_status' in data:
            cursor.execute('UPDATE expenses SET payment_status = ? WHERE id = ?', (data['payment_status'], expense_id))
            append_audit_log(cursor, 'update_status', 'expense', expense_id, {
                'payment_status': data['payment_status']
            })
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/reports/summary')
def reports_summary():
    start_date = normalize_api_date(request.args.get('start_date'))
    end_date = normalize_api_date(request.args.get('end_date'))
    if request.args.get('start_date') and not start_date:
        return jsonify({'error': 'Invalid start_date'}), 400
    if request.args.get('end_date') and not end_date:
        return jsonify({'error': 'Invalid end_date'}), 400
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    clause, params = build_date_clause('appointment_date', start_date, end_date)
    cursor.execute(f'SELECT COUNT(*) FROM appointments WHERE 1=1{clause}', params)
    appointments_count = cursor.fetchone()[0]

    clause, params = build_date_clause('visit_date', start_date, end_date)
    cursor.execute(f'SELECT COUNT(*) FROM visits WHERE 1=1{clause}', params)
    visits_count = cursor.fetchone()[0]

    # Reports revenue source matches dashboard: patient follow-up payments only.
    clause, params = build_date_clause('followup_date', start_date, end_date)
    cursor.execute(f'SELECT COALESCE(SUM(payment), 0) FROM patient_followups WHERE COALESCE(is_deleted, 0) = 0{clause}', params)
    revenue = cursor.fetchone()[0]

    clause, params = build_date_clause('followup_date', start_date, end_date)
    cursor.execute(f'SELECT COALESCE(SUM(COALESCE(lab_expense, 0)), 0) FROM patient_followups WHERE COALESCE(is_deleted, 0) = 0{clause}', params)
    lab_expenses = cursor.fetchone()[0]

    clause, params = build_date_clause('followup_date', start_date, end_date)
    cursor.execute(f'SELECT COALESCE(SUM(COALESCE(clinic_profit, COALESCE(price, 0) - COALESCE(discount, 0) - COALESCE(lab_expense, 0))), 0) FROM patient_followups WHERE COALESCE(is_deleted, 0) = 0{clause}', params)
    clinic_gross_profit = cursor.fetchone()[0]

    clause, params = build_date_clause('expense_date', start_date, end_date)
    cursor.execute(f'SELECT COALESCE(SUM(amount), 0) FROM expenses WHERE payment_status = "paid" AND 1=1{clause}', params)
    expenses_paid = cursor.fetchone()[0]
    
    clause, params = build_date_clause('expense_date', start_date, end_date)
    cursor.execute(f'SELECT COALESCE(SUM(amount), 0) FROM expenses WHERE payment_status = "postponed" AND 1=1{clause}', params)
    expenses_postponed = cursor.fetchone()[0]
    
    expenses_total = float(expenses_paid or 0) + float(expenses_postponed or 0)

    clause, params = build_date_clause('start_date', start_date, end_date)
    cursor.execute(f'SELECT COUNT(*) FROM treatment_plans WHERE 1=1{clause}', params)
    plans_count = cursor.fetchone()[0]

    conn.close()
    return jsonify({
        'appointments': appointments_count,
        'visits': visits_count,
        'revenue': float(revenue or 0),
        'lab_expenses': float(lab_expenses or 0),
        'clinic_gross_profit': float(clinic_gross_profit or 0),
        'expenses': expenses_total,
        'expenses_paid': float(expenses_paid or 0),
        'expenses_postponed': float(expenses_postponed or 0),
        'profit': float(revenue or 0) - expenses_total,
        'treatment_plans': plans_count
    })

@app.route('/api/reports/weekly')
def reports_weekly():
    week_start_param = request.args.get('week_start')
    try:
        if week_start_param:
            week_start = datetime.strptime(week_start_param, '%Y-%m-%d').date()
        else:
            today = datetime.now().date()
            week_start = today - timedelta(days=today.weekday())
    except ValueError:
        return jsonify({'error': 'Invalid week_start format. Use YYYY-MM-DD'}), 400

    week_end = week_start + timedelta(days=6)
    start_str = week_start.isoformat()
    end_str = week_end.isoformat()

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute('SELECT COUNT(*) FROM appointments WHERE date(appointment_date) BETWEEN ? AND ?', (start_str, end_str))
    appointments_count = cursor.fetchone()[0]

    cursor.execute('SELECT COUNT(*) FROM visits WHERE date(visit_date) BETWEEN ? AND ?', (start_str, end_str))
    visits_count = cursor.fetchone()[0]

    # Count distinct teeth (excluding follow-ups marked as 'مراجعة')
    cursor.execute('''
        SELECT COUNT(DISTINCT tooth_no) FROM patient_followups 
        WHERE date(followup_date) BETWEEN ? AND ? 
        AND COALESCE(is_deleted, 0) = 0 
        AND treatment_procedure != 'مراجعة'
    ''', (start_str, end_str))
    distinct_teeth = cursor.fetchone()[0] or 0

    # Count follow-ups (مراجعة entries)
    cursor.execute('''
        SELECT COUNT(*) FROM patient_followups 
        WHERE date(followup_date) BETWEEN ? AND ? 
        AND COALESCE(is_deleted, 0) = 0 
        AND treatment_procedure = 'مراجعة'
    ''', (start_str, end_str))
    follow_ups_count = cursor.fetchone()[0] or 0

    cursor.execute('SELECT COALESCE(SUM(payment), 0) FROM patient_followups WHERE COALESCE(is_deleted, 0) = 0 AND date(followup_date) BETWEEN ? AND ?', (start_str, end_str))
    revenue = cursor.fetchone()[0]

    cursor.execute('SELECT COALESCE(SUM(COALESCE(lab_expense, 0)), 0) FROM patient_followups WHERE COALESCE(is_deleted, 0) = 0 AND date(followup_date) BETWEEN ? AND ?', (start_str, end_str))
    lab_expenses = cursor.fetchone()[0]

    cursor.execute('SELECT COALESCE(SUM(COALESCE(clinic_profit, COALESCE(price, 0) - COALESCE(discount, 0) - COALESCE(lab_expense, 0))), 0) FROM patient_followups WHERE COALESCE(is_deleted, 0) = 0 AND date(followup_date) BETWEEN ? AND ?', (start_str, end_str))
    clinic_gross_profit = cursor.fetchone()[0]

    cursor.execute('SELECT COALESCE(SUM(amount), 0) FROM expenses WHERE payment_status = "paid" AND date(expense_date) BETWEEN ? AND ?', (start_str, end_str))
    expenses_paid = cursor.fetchone()[0]
    
    cursor.execute('SELECT COALESCE(SUM(amount), 0) FROM expenses WHERE payment_status = "postponed" AND date(expense_date) BETWEEN ? AND ?', (start_str, end_str))
    expenses_postponed = cursor.fetchone()[0]
    
    expenses_total = float(expenses_paid or 0) + float(expenses_postponed or 0)

    cursor.execute('SELECT COUNT(*) FROM treatment_plans WHERE date(start_date) BETWEEN ? AND ?', (start_str, end_str))
    plans_count = cursor.fetchone()[0]

    cursor.execute('SELECT COUNT(*) FROM billing WHERE date(COALESCE(payment_date, created_at)) BETWEEN ? AND ?', (start_str, end_str))
    invoice_count = cursor.fetchone()[0]

    cursor.execute('SELECT COUNT(*) FROM patient_followups WHERE COALESCE(is_deleted, 0) = 0 AND date(followup_date) BETWEEN ? AND ?', (start_str, end_str))
    session_count = cursor.fetchone()[0]

    cursor.execute('SELECT COUNT(DISTINCT patient_id) FROM patient_followups WHERE COALESCE(is_deleted, 0) = 0 AND date(followup_date) BETWEEN ? AND ?', (start_str, end_str))
    patient_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM patient_followups WHERE COALESCE(is_deleted, 0) = 0 AND entry_type = 'followup' AND date(followup_date) BETWEEN ? AND ?", (start_str, end_str))
    followups_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM patient_followups WHERE COALESCE(is_deleted, 0) = 0 AND (entry_type = 'new' OR entry_type IS NULL OR entry_type = '') AND date(followup_date) BETWEEN ? AND ?", (start_str, end_str))
    new_entries_count = cursor.fetchone()[0]

    conn.close()
    return jsonify({
        'week_start': start_str,
        'week_end': end_str,
        'week_start_display': format_date_display(start_str),
        'week_end_display': format_date_display(end_str),
        'appointments': appointments_count,
        'visits': visits_count,
        'distinct_teeth': distinct_teeth,
        'revenue': float(revenue or 0),
        'lab_expenses': float(lab_expenses or 0),
        'clinic_gross_profit': float(clinic_gross_profit or 0),
        'expenses': expenses_total,
        'expenses_paid': float(expenses_paid or 0),
        'expenses_postponed': float(expenses_postponed or 0),
        'profit': float(revenue or 0) - expenses_total,
        'treatment_plans': plans_count,
        'invoice_count': invoice_count,
        'session_count': session_count,
        'patient_count': patient_count,
        'followups': followups_count,
        'new_entries': new_entries_count
    })

@app.route('/api/reports/receivables')
def reports_receivables():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute('''
        SELECT
            p.id AS patient_id,
            p.first_name || ' ' || p.last_name AS patient_name,
            COALESCE(SUM(pf.price), 0) AS total_to_pay,
            COALESCE(SUM(COALESCE(pf.discount, 0)), 0) AS total_discount,
            COALESCE(SUM(pf.payment), 0) AS total_paid,
            MAX(pf.followup_date) AS last_followup_date
        FROM patients p
        LEFT JOIN patient_followups pf ON pf.patient_id = p.id AND COALESCE(pf.is_deleted, 0) = 0
        GROUP BY p.id, p.first_name, p.last_name
        HAVING (COALESCE(SUM(pf.price), 0) - COALESCE(SUM(COALESCE(pf.discount, 0)), 0) - COALESCE(SUM(pf.payment), 0)) > 0
        ORDER BY (COALESCE(SUM(pf.price), 0) - COALESCE(SUM(COALESCE(pf.discount, 0)), 0) - COALESCE(SUM(pf.payment), 0)) DESC, patient_name ASC
    ''')

    rows = []
    total_receivables = 0.0
    today = datetime.now().date()

    for row in cursor.fetchall():
        total_to_pay = float(row['total_to_pay'] or 0)
        total_discount = float(row['total_discount'] or 0)
        total_paid = float(row['total_paid'] or 0)
        outstanding = max(total_to_pay - total_discount - total_paid, 0.0)
        total_receivables += outstanding

        overdue_days = 0
        last_followup_date = row['last_followup_date']
        if last_followup_date:
            try:
                overdue_days = max((today - datetime.strptime(last_followup_date[:10], '%Y-%m-%d').date()).days, 0)
            except ValueError:
                overdue_days = 0

        rows.append({
            'patient_id': row['patient_id'],
            'patient_name': row['patient_name'],
            'total_to_pay': total_to_pay,
            'total_discount': total_discount,
            'total_paid': total_paid,
            'outstanding': outstanding,
            'last_followup_date': last_followup_date,
            'overdue_days': overdue_days
        })

    conn.close()
    return jsonify({
        'total_receivables': total_receivables,
        'count': len(rows),
        'rows': rows
    })

@app.route('/api/patients/<int:patient_id>/invoice-summary')
def patient_invoice_summary(patient_id):
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute('SELECT id, first_name, last_name, phone FROM patients WHERE id = ?', (patient_id,))
    patient = cursor.fetchone()
    if not patient:
        conn.close()
        return jsonify({'error': 'Patient not found'}), 404

    # Make sure stored running balances are current before the statement is built.
    _recompute_followup_balances(cursor, patient_id)
    conn.commit()

    conditions = ['patient_id = ?', 'COALESCE(is_deleted, 0) = 0']
    params = [patient_id]
    if start_date:
        conditions.append('date(followup_date) >= ?')
        params.append(start_date)
    if end_date:
        conditions.append('date(followup_date) <= ?')
        params.append(end_date)
    where_clause = ' AND '.join(conditions)

    cursor.execute(f'''
        SELECT id, followup_date, treatment_procedure, tooth_no,
               price, discount, lab_expense, clinic_profit, payment, remaining_amount, notes,
               price_expr, discount_expr, lab_expense_expr, payment_expr
        FROM patient_followups
        WHERE {where_clause}
        ORDER BY followup_date ASC, id ASC
    ''', params)
    items = []
    for row in cursor.fetchall():
        it = dict(row)
        it['price'] = float(it.get('price') or 0)
        it['discount'] = float(it.get('discount') or 0)
        it['lab_expense'] = float(it.get('lab_expense') or 0)
        it['payment'] = float(it.get('payment') or 0)
        it['remaining_amount'] = float(it.get('remaining_amount') or 0)
        # Net amount the patient owes for this line (price minus the discount given).
        it['net_due'] = round(it['price'] - it['discount'], 2)
        items.append(it)

    cursor.execute(f'''
        SELECT
            COALESCE(SUM(price), 0) AS total_price,
            COALESCE(SUM(COALESCE(discount, 0)), 0) AS total_discount,
            COALESCE(SUM(payment), 0) AS total_paid
        FROM patient_followups
        WHERE {where_clause}
    ''', params)
    totals = cursor.fetchone()

    total_price = float((totals['total_price'] if totals else 0) or 0)
    total_discount = float((totals['total_discount'] if totals else 0) or 0)
    total_paid = float((totals['total_paid'] if totals else 0) or 0)
    # What the patient actually owes = price − discount; what's left = that − payments.
    total_to_pay = round(max(total_price - total_discount, 0.0), 2)
    total_left = round(max(total_to_pay - total_paid, 0.0), 2)

    conn.close()
    return jsonify({
        'patient': {
            'id': patient['id'],
            'name': f"{patient['first_name']} {patient['last_name']}".strip(),
            'phone': patient['phone']
        },
        'items': items,
        'totals': {
            'total_price': round(total_price, 2),
            'total_discount': round(total_discount, 2),
            'total_to_pay': total_to_pay,
            'total_paid': round(total_paid, 2),
            'total_left': total_left
        },
        'range': {
            'start_date': start_date,
            'end_date': end_date
        }
    })

@app.route('/api/patients/<int:patient_id>/payment-history')
def patient_payment_history(patient_id):
    """Every payment recorded for one patient, from both sources:
    the per-entry `payment` column on the follow-up sheet, and the
    `billing` payment records. Sorted oldest-first so the staff member
    sees the full collection history when they pick a patient in the
    Billing → Payment Record tab."""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute('SELECT id, first_name, last_name, phone FROM patients WHERE id = ?', (patient_id,))
    patient = cursor.fetchone()
    if not patient:
        conn.close()
        return jsonify({'error': 'Patient not found'}), 404

    events = []

    # Follow-up sheet — one event per entry that carried a payment.
    cursor.execute('''
        SELECT id, followup_date, treatment_procedure, tooth_no, payment, payment_expr
        FROM patient_followups
        WHERE patient_id = ? AND COALESCE(is_deleted, 0) = 0 AND COALESCE(payment, 0) > 0
        ORDER BY followup_date ASC, id ASC
    ''', (patient_id,))
    for row in cursor.fetchall():
        events.append({
            'source': 'followup',
            'ref_id': row['id'],
            'date': row['followup_date'],
            'description': row['treatment_procedure'] or '',
            'tooth_no': row['tooth_no'],
            'amount': float(row['payment'] or 0),
            'amount_expr': row['payment_expr'],
            'credit_used': 0.0,
            'method': None,
            'payment_status': None,
        })

    # Billing payment records — only those that actually moved money
    # (a cash payment or applied credit). Mirrors `/api/billing` (no
    # is_deleted filter — billing rows are hard-deleted).
    cursor.execute('''
        SELECT id, invoice_number, payment_date, created_at, paid_amount,
               paid_amount_expr, credit_used, payment_method, payment_status
        FROM billing
        WHERE patient_id = ?
        ORDER BY id ASC
    ''', (patient_id,))
    for row in cursor.fetchall():
        paid = float(row['paid_amount'] or 0)
        credit = float(row['credit_used'] or 0)
        if paid <= 0 and credit <= 0:
            continue
        created = row['created_at'] or ''
        events.append({
            'source': 'billing',
            'ref_id': row['id'],
            'date': row['payment_date'] or (created[:10] if created else None),
            'description': row['invoice_number'] or '',
            'tooth_no': None,
            'amount': paid,
            'amount_expr': row['paid_amount_expr'],
            'credit_used': credit,
            'method': row['payment_method'],
            'payment_status': row['payment_status'],
        })

    # Oldest first; rows without a date sort to the front.
    events.sort(key=lambda e: (e['date'] or ''))

    total_paid = round(sum(e['amount'] for e in events), 2)
    total_credit = round(sum(e['credit_used'] for e in events), 2)

    conn.close()
    return jsonify({
        'patient': {
            'id': patient['id'],
            'name': f"{patient['first_name']} {patient['last_name']}".strip(),
            'phone': patient['phone']
        },
        'events': events,
        'totals': {
            'total_paid': total_paid,
            'total_credit_used': total_credit,
            'count': len(events)
        }
    })

@app.route('/api/audit-logs')
def audit_logs():
    limit_param = request.args.get('limit', '200')
    try:
        limit = max(1, min(int(limit_param), 1000))
    except ValueError:
        limit = 200

    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, action_type, entity_type, entity_id, details, created_at
        FROM audit_logs
        ORDER BY id DESC
        LIMIT ?
    ''', (limit,))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify(rows)

@app.route('/api/holidays', methods=['GET', 'POST'])
def holidays():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    if request.method == 'GET':
        cursor.execute('SELECT id, holiday_date, name, notes, created_at FROM holidays ORDER BY holiday_date DESC')
        rows = []
        for row in cursor.fetchall():
            rows.append({
                'id': row[0],
                'holiday_date': row[1],
                'name': row[2],
                'notes': row[3],
                'created_at': row[4]
            })
        conn.close()
        return jsonify(rows)

    data = request.json
    holiday_date = data.get('holiday_date')
    if not holiday_date:
        conn.close()
        return jsonify({'error': 'Holiday date is required'}), 400
    
    # Parse holiday date to ensure YYYY-MM-DD format
    parsed_date = parse_date_input(holiday_date)
    if not parsed_date:
        conn.close()
        return jsonify({'error': 'Invalid holiday date format. Use DD/MM/YYYY.'}), 400
    
    cursor.execute('''
        INSERT INTO holidays (holiday_date, name, notes)
        VALUES (?, ?, ?)
    ''', (parsed_date, data.get('name'), data.get('notes')))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/holidays/<int:holiday_id>', methods=['DELETE'])
def delete_holiday(holiday_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM holidays WHERE id = ?', (holiday_id,))
    record_tombstone(cursor, 'holidays', holiday_id)
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/backup')
def backup_database():
    backup_name = f"dental_clinic_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    return send_file(DB_NAME, as_attachment=True, download_name=backup_name)

@app.route('/api/medical-images', methods=['GET', 'POST'])
def medical_images():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    if request.method == 'GET':
        patient_id = request.args.get('patient_id')
        if patient_id:
            cursor.execute('SELECT * FROM medical_images WHERE patient_id = ? ORDER BY uploaded_at DESC', (patient_id,))
        else:
            cursor.execute('SELECT * FROM medical_images ORDER BY uploaded_at DESC')
        rows = []
        for row in cursor.fetchall():
            rows.append({
                'id': row[0],
                'patient_id': row[1],
                'file_name': row[2],
                'file_path': row[3],
                'uploaded_at': row[4],
                'notes': row[5]
            })
        conn.close()
        return jsonify(rows)

    patient_id = request.form.get('patient_id')
    notes = request.form.get('notes')
    file = request.files.get('image')
    if not file:
        conn.close()
        return jsonify({'error': 'No image uploaded'}), 400

    if not patient_id:
        conn.close()
        return jsonify({'error': 'Patient is required'}), 400

    safe_name = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{secure_filename(file.filename)}"
    file_path = UPLOAD_FOLDER / safe_name
    file.save(file_path)
    cursor.execute('''
        INSERT INTO medical_images (patient_id, file_name, file_path, notes)
        VALUES (?, ?, ?, ?)
    ''', (patient_id, file.filename, str(file_path), notes))
    new_id = cursor.lastrowid
    conn.commit()
    conn.close()
    # Return the new id so clients (e.g. the mobile app) can reconcile the
    # uploaded row against the catalog they fetch back via GET.
    return jsonify({'success': True, 'id': new_id})


@app.route('/api/medical-images/<int:image_id>/file')
def medical_image_file(image_id):
    """Stream the stored bytes for one medical image so non-browser clients
    (the mobile app) can download and cache it. The desktop UI embeds images
    inline, but the mobile app needs the raw file to view/sync. file_path is
    written by our own upload handler, so it is not request-controlled."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT file_path, file_name FROM medical_images WHERE id = ?', (image_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return jsonify({'error': 'Image not found'}), 404
    file_path = row[0]
    if not file_path or not Path(file_path).exists():
        return jsonify({'error': 'File missing'}), 404
    return send_file(file_path, download_name=row[1] or Path(file_path).name)

@app.route('/api/support', methods=['GET', 'POST'])
def support_messages():
    if request.method == 'GET':
        return jsonify([
            {
                'title': 'Backup your database daily',
                'detail': 'Use the Backup button before updates or heavy work.'
            },
            {
                'title': 'Use the calendar for reservations',
                'detail': 'Open Appointments to see all bookings at a glance.'
            },
            {
                'title': 'Open a patient profile for full history',
                'detail': 'Click View in Patients to inspect visits, treatments, billing, and images.'
            }
        ])

    data = request.json
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('INSERT INTO support_messages (subject, message) VALUES (?, ?)', (data['subject'], data['message']))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/visits', methods=['GET', 'POST'])
def visits():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    if request.method == 'GET':
        cursor.execute('''
            SELECT v.*, p.first_name || ' ' || p.last_name as patient_name
            FROM visits v
            JOIN patients p ON v.patient_id = p.id
            ORDER BY v.visit_date DESC
        ''')
        visits = []
        for row in cursor.fetchall():
            visits.append({
                'id': row[0],
                'appointment_id': row[1],
                'patient_id': row[2],
                'visit_date': row[3],
                'dentist_name': row[4],
                'chief_complaint': row[5],
                'diagnosis': row[6],
                'procedure_summary': row[7],
                'follow_up_date': row[8],
                'status': row[9],
                'notes': row[10],
                'outcome': row[11],
                'created_at': row[12],
                'patient_name': row[13]
            })
        conn.close()
        return jsonify(visits)

    data = request.json
    cursor.execute('''
        INSERT INTO visits (
            appointment_id, patient_id, visit_date, dentist_name, chief_complaint,
            diagnosis, procedure_summary, follow_up_date, status, notes, outcome
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        data.get('appointment_id'),
        data['patient_id'],
        data['visit_date'],
        data.get('dentist_name'),
        data.get('chief_complaint'),
        data.get('diagnosis'),
        data.get('procedure_summary'),
        data.get('follow_up_date'),
        data.get('status', 'open'),
        data.get('notes'),
        data.get('outcome')
    ))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/visits/<int:visit_id>/status', methods=['PUT'])
def update_visit_status(visit_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    data = request.json
    cursor.execute('UPDATE visits SET status = ? WHERE id = ?', (data['status'], visit_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/visits/from-appointment/<int:appointment_id>', methods=['POST'])
def create_visit_from_appointment(appointment_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute('''
        SELECT patient_id, appointment_date, treatment_type, notes
        FROM appointments
        WHERE id = ?
    ''', (appointment_id,))
    appointment = cursor.fetchone()

    if not appointment:
        conn.close()
        return jsonify({'success': False, 'message': 'Appointment not found'}), 404

    cursor.execute('''
        INSERT INTO visits (appointment_id, patient_id, visit_date, chief_complaint, notes, status)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (
        appointment_id,
        appointment[0],
        appointment[1],
        appointment[2],
        appointment[3],
        'open'
    ))

    cursor.execute('UPDATE appointments SET status = ? WHERE id = ?', ('completed', appointment_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/treatments', methods=['GET', 'POST'])
def treatments():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    if request.method == 'GET':
        cursor.execute('''
            SELECT t.*, p.first_name || ' ' || p.last_name as patient_name
            FROM treatments t
            JOIN patients p ON t.patient_id = p.id
            ORDER BY t.id DESC
        ''')
        treatments = []
        for row in cursor.fetchall():
            treatments.append({
                'id': row[0],
                'patient_id': row[1],
                'appointment_id': row[2],
                'treatment_name': row[3],
                'description': row[4],
                'cost': row[5],
                'treatment_date': row[6],
                'dentist_name': row[7],
                'created_at': row[8],
                'patient_name': row[9]
            })
        conn.close()
        return jsonify(treatments)
    
    else:  # POST
        data = request.json
        cursor.execute('''
            INSERT INTO treatments (patient_id, treatment_name, description, cost, treatment_date, dentist_name)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (data['patient_id'], data['treatment_name'], data.get('description'),
              data['cost'], data.get('treatment_date'), data.get('dentist_name')))
        conn.commit()
        conn.close()
        return jsonify({'success': True})

@app.route('/api/treatments/<int:treatment_id>', methods=['DELETE'])
def delete_treatment(treatment_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM treatments WHERE id = ?', (treatment_id,))
    record_tombstone(cursor, 'treatments', treatment_id)
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/billing', methods=['GET', 'POST'])
def billing():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    if request.method == 'GET':
        cursor.execute('''
            SELECT b.*, p.first_name || ' ' || p.last_name as patient_name
            FROM billing b
            JOIN patients p ON b.patient_id = p.id
            ORDER BY b.id DESC
        ''')
        billing_records = []
        for row in cursor.fetchall():
            row_data = dict(row)
            billing_records.append({
                'id': row_data.get('id'),
                'patient_id': row_data.get('patient_id'),
                'treatment_id': row_data.get('treatment_id'),
                'invoice_number': row_data.get('invoice_number'),
                'amount': row_data.get('amount'),
                'subtotal': row_data.get('subtotal'),
                'subtotal_expr': row_data.get('subtotal_expr'),
                'discount': row_data.get('discount'),
                'discount_expr': row_data.get('discount_expr'),
                'paid_amount': row_data.get('paid_amount'),
                'paid_amount_expr': row_data.get('paid_amount_expr'),
                'credit_used': row_data.get('credit_used') or 0,
                'balance_due': row_data.get('balance_due'),
                'payment_method': row_data.get('payment_method'),
                'payment_status': row_data.get('payment_status'),
                'payment_date': row_data.get('payment_date'),
                'created_at': row_data.get('created_at'),
                'patient_name': row_data.get('patient_name')
            })
        conn.close()
        return jsonify(billing_records)
    
    else:  # POST
        data = request.json or {}
        if not data.get('patient_id'):
            conn.close()
            return jsonify({'error': 'patient_id is required'}), 400
        try:
            subtotal = float(data.get('subtotal', data.get('amount', 0)))
            discount = float(data.get('discount', 0))
            paid_amount = float(data.get('paid_amount', 0))
            credit_used = float(data.get('credit_used', 0) or 0)
        except (TypeError, ValueError):
            conn.close()
            return jsonify({'error': 'Invalid billing equation values'}), 400

        if subtotal <= 0:
            conn.close()
            return jsonify({'error': 'Subtotal must be greater than zero'}), 400
        if discount < 0:
            conn.close()
            return jsonify({'error': 'Discount cannot be negative'}), 400
        if paid_amount < 0:
            conn.close()
            return jsonify({'error': 'Paid amount cannot be negative'}), 400
        if credit_used < 0:
            conn.close()
            return jsonify({'error': 'Credit used cannot be negative'}), 400

        # Don't let a payment draw more credit than the patient actually has.
        if credit_used > 0:
            available_credit = get_patient_credit_balance(cursor, int(data['patient_id']))
            if credit_used > available_credit + 0.005:
                conn.close()
                return jsonify({'error': f'Patient only has ₪{available_credit:.2f} of credit available'}), 400

        total_amount = round(max(0.0, subtotal - discount), 2)
        settled = paid_amount + credit_used   # cash + credit applied to this invoice
        balance_due = round(max(0.0, total_amount - settled), 2)

        if total_amount > 0 and settled >= total_amount:
            payment_status = 'paid'
        elif settled > 0:
            payment_status = 'partial'
        else:
            payment_status = 'pending'

        invoice_number = data.get('invoice_number') or generate_invoice_number()
        subtotal_expr = sanitize_amount_expr(data.get('subtotal_expr'), subtotal)
        discount_expr = sanitize_amount_expr(data.get('discount_expr'), discount)
        paid_amount_expr = sanitize_amount_expr(data.get('paid_amount_expr'), paid_amount)

        # Parse payment date to ensure YYYY-MM-DD format
        payment_date = data.get('payment_date')
        if payment_date:
            parsed_date = parse_date_input(payment_date)
            if not parsed_date:
                conn.close()
                return jsonify({'error': 'Invalid payment date format. Use DD/MM/YYYY.'}), 400
            payment_date = parsed_date

        cursor.execute('''
            INSERT INTO billing (
                patient_id, treatment_id, invoice_number, amount,
                subtotal, discount, paid_amount, credit_used, balance_due,
                payment_method, payment_status, payment_date,
                subtotal_expr, discount_expr, paid_amount_expr
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            data['patient_id'],
            data.get('treatment_id'),
            invoice_number,
            total_amount,
            subtotal,
            discount,
            paid_amount,
            round(credit_used, 2),
            balance_due,
            data.get('payment_method'),
            payment_status,
            payment_date,
            subtotal_expr,
            discount_expr,
            paid_amount_expr
        ))
        billing_id = cursor.lastrowid
        if credit_used > 0:
            cursor.execute(
                'INSERT INTO patient_credit_transactions (patient_id, amount, type, note, invoice_id) VALUES (?, ?, ?, ?, ?)',
                (int(data['patient_id']), -round(credit_used, 2), 'debit', f'Applied to invoice {invoice_number}', billing_id)
            )
        append_audit_log(cursor, 'create', 'billing', billing_id, {
            'patient_id': data.get('patient_id'),
            'invoice_number': invoice_number,
            'subtotal': subtotal,
            'discount': discount,
            'paid_amount': paid_amount,
            'credit_used': round(credit_used, 2),
            'amount': total_amount,
            'balance_due': balance_due,
            'payment_status': payment_status
        })
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'payment_status': payment_status, 'amount': total_amount, 'balance_due': balance_due})

@app.route('/api/billing/<int:billing_id>', methods=['DELETE'])
def delete_billing(billing_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # Reverse any credit that this invoice consumed before removing it.
    cursor.execute('DELETE FROM patient_credit_transactions WHERE invoice_id = ?', (billing_id,))
    cursor.execute('DELETE FROM billing WHERE id = ?', (billing_id,))
    record_tombstone(cursor, 'billing', billing_id)
    append_audit_log(cursor, 'delete', 'billing', billing_id, {'id': billing_id})
    conn.commit()
    conn.close()
    return jsonify({'success': True})


@app.route('/invoice/<int:billing_id>')
def billing_invoice(billing_id):
    # Normalise to a known value so the reflected `lang` can't carry markup.
    lang = 'ar' if request.args.get('lang') == 'ar' else 'en'
    is_ar = lang == 'ar'
    direction = 'rtl' if is_ar else 'ltr'
    align = 'right' if is_ar else 'left'

    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('''
        SELECT b.*, p.first_name || ' ' || p.last_name AS patient_name
        FROM billing b
        LEFT JOIN patients p ON b.patient_id = p.id
        WHERE b.id = ?
    ''', (billing_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return 'Invoice not found', 404

    b = dict(row)
    labels = {
        'en': {
            'title': 'Invoice', 'patient': 'Patient', 'invoice_no': 'Invoice #',
            'date': 'Date', 'subtotal': 'Subtotal', 'discount': 'Discount',
            'total': 'Total', 'paid': 'Paid', 'balance': 'Amount to Pay',
            'method': 'Payment Method', 'status': 'Status', 'clinic': 'Dr. Wasfy Barzaq Dental Clinic'
        },
        'ar': {
            'title': 'فاتورة', 'patient': 'المريض', 'invoice_no': 'رقم الفاتورة',
            'date': 'التاريخ', 'subtotal': 'الإجمالي قبل الخصم', 'discount': 'الخصم',
            'total': 'الإجمالي', 'paid': 'المدفوع', 'balance': 'المبلغ المطلوب',
            'method': 'طريقة الدفع', 'status': 'الحالة', 'clinic': 'عيادة د. وصفي برزق للأسنان'
        }
    }
    lbl = labels.get(lang, labels['en'])
    currency = '₪'

    logo_path = _BUNDLE_DIR / 'DentaCare.PNG'
    logo_src = '/logo'
    if logo_path.exists():
        with open(str(logo_path), 'rb') as _lf:
            logo_src = 'data:image/png;base64,' + base64.b64encode(_lf.read()).decode()

    # All DB-derived strings are HTML-escaped before interpolation.
    inv_no = escape(b.get("invoice_number") or "—")
    patient_name = escape(b.get("patient_name") or "—")
    inv_date = escape(b.get("payment_date") or b.get("created_at") or "—")
    pay_method = escape(b.get("payment_method") or "—")
    pay_status = escape(b.get("payment_status") or "—")

    def amt_cell(value, expr=None):
        # Show the verbatim expression the user typed (e.g. "20+20") when there is one.
        expr = sanitize_amount_expr(expr, value)
        if expr:
            return f'{escape(expr)} = {currency} {float(value or 0):.2f}'
        return f'{currency} {float(value or 0):.2f}'

    html = f'''<!DOCTYPE html>
<html lang="{lang}" dir="{direction}">
<head>
<meta charset="UTF-8">
<title>{lbl["title"]} {inv_no}</title>
<style>
  body {{ font-family: Arial, sans-serif; margin: 32px; color: #222; direction: {direction}; }}
  .inv-header {{ display: flex; align-items: center; gap: 16px; margin-bottom: 6px; flex-direction: {"row-reverse" if is_ar else "row"}; }}
  .inv-header img {{ height: 64px; width: auto; }}
  .inv-header-text {{ flex: 1; }}
  h1 {{ margin: 0 0 2px 0; font-size: 22px; }}
  .clinic {{ color: #555; margin: 0 0 20px 0; font-size: 14px; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 16px; }}
  th, td {{ border: 1px solid #ddd; padding: 10px 12px; text-align: {align}; }}
  th {{ background: #f5f5f5; font-weight: 600; }}
  .total-row td {{ font-weight: 700; background: #f9f9f9; }}
  @media print {{ body {{ margin: 16px; }} }}
</style>
</head>
<body>
<div class="inv-header">
  <img src="{logo_src}" alt="DentaCare">
  <div class="inv-header-text">
    <h1>{lbl["title"]}</h1>
    <div class="clinic">{lbl["clinic"]}</div>
  </div>
</div>
<table>
  <tr><th>{lbl["invoice_no"]}</th><td>{inv_no}</td></tr>
  <tr><th>{lbl["patient"]}</th><td>{patient_name}</td></tr>
  <tr><th>{lbl["date"]}</th><td>{inv_date}</td></tr>
  <tr><th>{lbl["method"]}</th><td>{pay_method}</td></tr>
  <tr><th>{lbl["status"]}</th><td>{pay_status}</td></tr>
  <tr><th>{lbl["subtotal"]}</th><td>{amt_cell(b.get("subtotal"), b.get("subtotal_expr"))}</td></tr>
  <tr><th>{lbl["discount"]}</th><td>{amt_cell(b.get("discount"), b.get("discount_expr"))}</td></tr>
  <tr class="total-row"><th>{lbl["total"]}</th><td>{currency} {float(b.get("amount") or 0):.2f}</td></tr>
  <tr><th>{lbl["paid"]}</th><td>{amt_cell(b.get("paid_amount"), b.get("paid_amount_expr"))}</td></tr>
  <tr class="total-row"><th>{lbl["balance"]}</th><td>{currency} {float(b.get("balance_due") or 0):.2f}</td></tr>
</table>
<script>window.onload = function() {{ window.print(); }}</script>
</body>
</html>'''
    return html


@app.route('/api/pairing/start', methods=['POST'])
def start_pairing():
    data = request.json or {}
    device_name = str(data.get('device_name') or 'Mobile Device').strip()
    if not device_name:
        return jsonify({'error': 'Device name is required'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM pairing_requests WHERE consumed = 1 OR datetime(expires_at) < datetime("now")')

    expires_at = (_naive_utc_now() + timedelta(minutes=PAIRING_CODE_TTL_MINUTES)).strftime('%Y-%m-%d %H:%M:%S')
    pair_code = generate_pair_code()
    for _ in range(5):
        cursor.execute('SELECT pair_code FROM pairing_requests WHERE pair_code = ?', (pair_code,))
        if not cursor.fetchone():
            break
        pair_code = generate_pair_code()

    cursor.execute('''
        INSERT INTO pairing_requests (pair_code, device_name, expires_at)
        VALUES (?, ?, ?)
    ''', (pair_code, device_name, expires_at))
    append_audit_log(cursor, 'create', 'pairing_request', None, {'device_name': device_name, 'pair_code': pair_code})
    conn.commit()
    conn.close()

    return jsonify({
        'success': True,
        'pair_code': pair_code,
        'expires_at': expires_at,
        'ttl_minutes': PAIRING_CODE_TTL_MINUTES
    })


@app.route('/api/pairing/complete', methods=['POST'])
def complete_pairing():
    data = request.json or {}
    pair_code = str(data.get('pair_code') or '').strip()
    if not pair_code:
        return jsonify({'error': 'Pair code is required'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT pair_code, device_name, expires_at, consumed
        FROM pairing_requests
        WHERE pair_code = ?
    ''', (pair_code,))
    request_row = cursor.fetchone()
    if not request_row:
        conn.close()
        return jsonify({'error': 'Invalid pair code'}), 404

    expires_at = datetime.strptime(request_row[2], '%Y-%m-%d %H:%M:%S')
    if int(request_row[3]) == 1 or _naive_utc_now() > expires_at:
        conn.close()
        return jsonify({'error': 'Pair code expired'}), 410

    device_id = str(data.get('device_id') or uuid.uuid4()).strip()
    device_name = str(data.get('device_name') or request_row[1] or 'Mobile Device').strip()
    device_token = secrets.token_urlsafe(32)

    cursor.execute('''
        INSERT INTO paired_devices (device_id, device_name, device_token, paired_at, last_seen_at, is_active)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1)
        ON CONFLICT(device_id) DO UPDATE SET
            device_name = excluded.device_name,
            device_token = excluded.device_token,
            last_seen_at = CURRENT_TIMESTAMP,
            is_active = 1
    ''', (device_id, device_name, device_token))

    cursor.execute('UPDATE pairing_requests SET consumed = 1 WHERE pair_code = ?', (pair_code,))
    append_audit_log(cursor, 'create', 'paired_device', None, {'device_id': device_id, 'device_name': device_name})
    conn.commit()
    conn.close()

    return jsonify({
        'success': True,
        'device_id': device_id,
        'device_name': device_name,
        'device_token': device_token
    })


@app.route('/api/sync/export')
def sync_export():
    conn = get_db_connection(with_row_factory=True)
    cursor = conn.cursor()
    device = get_authenticated_device(cursor)
    if not device:
        conn.close()
        return jsonify({'error': 'Unauthorized device token'}), 401

    # Optional incremental sync: only rows changed/deleted strictly after ?since=<iso-ts>.
    since_raw = request.args.get('since')
    since_dt = parse_timestamp_for_sync(since_raw) if since_raw else None

    snapshot_tables, tombstones, total_records = _collect_sync_export(cursor, since_dt)

    app_instance_id = read_app_setting(cursor, 'app_instance_id', '')
    cursor.execute('''
        INSERT INTO sync_snapshots (source, device_id, table_count, record_count)
        VALUES (?, ?, ?, ?)
    ''', ('export', device['device_id'], len(SYNC_TABLES), total_records))
    cursor.execute('''
        INSERT INTO sync_events (event_type, source_device_id, details)
        VALUES (?, ?, ?)
    ''', ('snapshot_export', device['device_id'], json.dumps({
        'record_count': total_records,
        'tombstone_count': len(tombstones),
        'incremental': since_dt is not None,
    })))
    conn.commit()
    conn.close()

    return jsonify({
        'success': True,
        'generated_at': utc_now_iso(),
        'source_instance_id': app_instance_id,
        'incremental': since_dt is not None,
        'table_count': len(SYNC_TABLES),
        'record_count': total_records,
        'tables': snapshot_tables,
        'tombstones': tombstones
    })


@app.route('/api/sync/import', methods=['POST'])
def sync_import():
    payload = request.json or {}
    incoming_tables = payload.get('tables')
    if not isinstance(incoming_tables, dict):
        return jsonify({'error': 'Invalid payload: tables is required'}), 400

    conn = get_db_connection(with_row_factory=True)
    cursor = conn.cursor()
    device = get_authenticated_device(cursor)
    if not device:
        conn.close()
        return jsonify({'error': 'Unauthorized device token'}), 401

    applied_total, skipped_total, tombstones_applied, by_table = _apply_sync_import(cursor, payload)

    cursor.execute('''
        INSERT INTO sync_snapshots (source, device_id, table_count, record_count)
        VALUES (?, ?, ?, ?)
    ''', ('import', device['device_id'], len(by_table), applied_total))
    cursor.execute('''
        INSERT INTO sync_events (event_type, source_device_id, details)
        VALUES (?, ?, ?)
    ''', ('snapshot_import', device['device_id'], json.dumps({
        'applied_total': applied_total,
        'skipped_total': skipped_total,
        'tombstones_applied': tombstones_applied,
    })))
    conn.commit()
    conn.close()

    return jsonify({
        'success': True,
        'applied_total': applied_total,
        'skipped_total': skipped_total,
        'tombstones_applied': tombstones_applied,
        'by_table': by_table
    })


@app.route('/api/clinics/register', methods=['POST'])
def register_clinic():
    """Cloud node only: provision a new clinic tenant — its own DB + a token.

    Called once per clinic by its local server. Each serial registers exactly
    one clinic; calling again with the same serial returns the existing token
    (idempotent), so a re-run after a crash is safe.
    """
    if not CLOUD_MODE:
        return jsonify({'error': 'Clinic registration is only available on the cloud node'}), 404

    limited = _check_register_rate_limit()
    if limited is not None:
        return limited

    data = request.json or {}
    serial_number = str(data.get('serial_number') or '').strip().upper()
    clinic_name = str(data.get('clinic_name') or '').strip()
    offline_token = str(data.get('offline_token') or '').strip()
    if len(serial_number) < 8:
        return jsonify({'error': 'serial_number must be at least 8 characters'}), 400
    if not clinic_name:
        return jsonify({'error': 'clinic_name is required'}), 400

    # HMAC-signed-serial gate (opt-in). When CLINIC_SERIAL_SIGNING_KEY is set,
    # we verify an offline_token if present; with CLINIC_REQUIRE_SIGNED_SERIAL=1,
    # registration without a valid signed token is rejected. This lets the cloud
    # roll out signing without breaking already-issued demo serials.
    signing_key = _serial_signing_key()
    if signing_key is not None and (offline_token or _REQUIRE_SIGNED_SERIAL):
        ok, reason = _verify_serial_token(serial_number, offline_token, signing_key)
        if not ok:
            return jsonify({'error': reason}), 403
    elif _REQUIRE_SIGNED_SERIAL and signing_key is None:
        # Misconfiguration: enforcement requested but no key set.
        return jsonify({'error': 'Server signing key not configured'}), 500

    master = sqlite3.connect(MASTER_DB_PATH)
    master.row_factory = sqlite3.Row
    existing = master.execute(
        'SELECT id, clinic_name, clinic_token, active FROM clinics WHERE serial_number = ?',
        (serial_number,),
    ).fetchone()
    if existing:
        active = int(existing['active']) == 1
        master.close()
        if not active:
            return jsonify({'error': 'This serial is registered to a deactivated clinic'}), 403
        return jsonify({
            'success': True, 'already_registered': True,
            'clinic_id': existing['id'], 'clinic_name': existing['clinic_name'],
            'clinic_token': existing['clinic_token'],
        })

    clinic_token = secrets.token_urlsafe(32)
    try:
        cur = master.execute(
            'INSERT INTO clinics (clinic_name, clinic_token, serial_number, active) VALUES (?, ?, ?, 1)',
            (clinic_name, clinic_token, serial_number),
        )
        clinic_id = cur.lastrowid
        master.commit()
    except sqlite3.IntegrityError:
        master.close()
        return jsonify({'error': 'That serial is already in use'}), 409

    db_path = _clinic_db_path(clinic_id)
    try:
        _set_request_db_path(db_path)
        init_database()
    except Exception as exc:  # noqa: BLE001 - report and roll back any partial state
        _set_request_db_path(None)
        try:
            master.execute('DELETE FROM clinics WHERE id = ?', (clinic_id,))
            master.commit()
        except sqlite3.Error:
            pass
        master.close()
        try:
            if os.path.exists(db_path):
                os.remove(db_path)
        except OSError:
            pass
        return jsonify({'error': f'Failed to initialise clinic database: {exc}'}), 500
    finally:
        _set_request_db_path(None)
    master.close()

    return jsonify({
        'success': True, 'already_registered': False,
        'clinic_id': clinic_id, 'clinic_name': clinic_name, 'clinic_token': clinic_token,
    })


@app.route('/api/cloud/pair', methods=['POST'])
def cloud_pair():
    """Local server only: register this clinic with the cloud node and remember
    the returned token, then do an immediate first sync. Body: {cloud_url, serial_number}.
    (cloud_url may be omitted if CLINIC_CLOUD_URL is set in the environment.)"""
    if CLOUD_MODE:
        return jsonify({'error': 'Not applicable on the cloud node'}), 400
    data = request.json or {}
    cloud_url = str(data.get('cloud_url') or os.environ.get('CLINIC_CLOUD_URL') or '').strip().rstrip('/')
    serial = str(data.get('serial_number') or '').strip().upper()
    if not cloud_url:
        return jsonify({'error': 'cloud_url is required'}), 400
    if len(serial) < 8:
        return jsonify({'error': 'serial_number must be at least 8 characters'}), 400
    clinic_name = str(CLINIC_CONFIG.get('CLINIC_NAME') or 'Clinic')
    try:
        status, resp = _cloud_http_request('POST', f'{cloud_url}/api/clinics/register',
                                           body={'serial_number': serial, 'clinic_name': clinic_name})
    except Exception as exc:  # noqa: BLE001 - connection error → can't reach
        return jsonify({'error': f'Could not reach the cloud node: {exc}'}), 502
    if status != 200 or not (isinstance(resp, dict) and resp.get('clinic_token')):
        return jsonify({'error': f'Cloud registration failed (HTTP {status})', 'detail': resp}), 502

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    write_app_setting(cur, 'cloud_url', cloud_url)
    write_app_setting(cur, 'cloud_clinic_token', resp['clinic_token'])
    write_app_setting(cur, 'cloud_clinic_id', str(resp.get('clinic_id') or ''))
    conn.commit()
    conn.close()

    first_sync = _run_cloud_sync_once(cloud_url, resp['clinic_token'])
    return jsonify({
        'success': True,
        'cloud_url': cloud_url,
        'clinic_id': resp.get('clinic_id'),
        'already_registered': resp.get('already_registered'),
        'first_sync': first_sync,
    })


@app.route('/api/cloud/status')
def cloud_status():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    url, token, interval = _cloud_sync_config()
    info = {
        'cloud_mode': CLOUD_MODE,
        'configured': bool(url and token),
        'cloud_url': url,
        'clinic_id': (read_app_setting(cur, 'cloud_clinic_id', '') or None),
        'sync_interval_minutes': interval,
        'last_sync_at': (read_app_setting(cur, 'cloud_last_sync_at', '') or None),
        'last_sync_result': (read_app_setting(cur, 'cloud_last_sync_result', '') or None),
        'last_pull_at': (read_app_setting(cur, 'cloud_last_pull_at', '') or None),
        'last_push_at': (read_app_setting(cur, 'cloud_last_push_at', '') or None),
    }
    conn.close()
    return jsonify(info)


@app.route('/api/cloud/sync-now', methods=['POST'])
def cloud_sync_now():
    if CLOUD_MODE:
        return jsonify({'error': 'Not applicable on the cloud node'}), 400
    url, token, _ = _cloud_sync_config()
    if not (url and token):
        return jsonify({'error': 'Cloud sync is not configured — pair with the cloud node first'}), 400
    return jsonify(_run_cloud_sync_once(url, token))


@app.route('/api/cloud/unpair', methods=['POST'])
def cloud_unpair():
    if CLOUD_MODE:
        return jsonify({'error': 'Not applicable on the cloud node'}), 400
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    for k in ('cloud_url', 'cloud_clinic_token', 'cloud_clinic_id',
              'cloud_last_sync_at', 'cloud_last_sync_result', 'cloud_last_pull_at', 'cloud_last_push_at'):
        cur.execute('DELETE FROM app_settings WHERE key = ?', (k,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


def _bt_list_serial_ports():
    """Return COM port entries that look like Bluetooth SPP ports.

    On Windows, the **incoming** BT-SPP port (the one we want to listen on)
    typically has a hwid containing ``LOCALMFG``; outgoing per-device ports
    have the remote device's address in the hwid instead. We surface both —
    the user can override — but rank the incoming-looking ones first so the
    auto-pick lands on the right port without the user needing to know.
    """
    try:
        from serial.tools import list_ports
    except ImportError:
        return []
    ports = []
    for p in list_ports.comports():
        desc = (p.description or '').lower()
        hwid = (p.hwid or '').lower()
        is_bt = (
            'bluetooth' in desc
            or 'standard serial over bluetooth' in desc
            or 'bthenum' in hwid
        )
        if not is_bt:
            continue
        looks_incoming = 'localmfg' in hwid
        ports.append({
            'device': p.device,
            'description': p.description or '',
            'hwid': p.hwid or '',
            'looks_incoming': looks_incoming,
        })
    # Sort: incoming-looking first, then alphabetical for stability.
    ports.sort(key=lambda x: (not x['looks_incoming'], x['device']))
    return ports


def _bt_pick_default_port():
    """Best guess at the COM port the desktop should listen on. Empty string
    if no Bluetooth port is registered with Windows yet (user needs to enable
    'Allow other devices to send files' or pair a phone first)."""
    ports = _bt_list_serial_ports()
    return ports[0]['device'] if ports else ''


@app.route('/api/bt/status', methods=['GET'])
def bt_status():
    if CLOUD_MODE:
        return jsonify({'error': 'Bluetooth sync is local-server only'}), 400
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    enabled = read_app_setting(cur, 'bt_sync_enabled', '0') == '1'
    com_port = read_app_setting(cur, 'bt_sync_com_port', '') or ''
    last_sync_at = read_app_setting(cur, 'bt_last_sync_at', '') or ''
    last_error = read_app_setting(cur, 'bt_last_error', '') or ''
    # Paired phones — the Settings UI lists these so the user can see which
    # phones have a stored device_token. Newest-first, capped at 20 to keep
    # the response tiny even in a clinic with many self-pairs.
    try:
        cur.execute(
            'SELECT device_id, device_name, paired_at, last_seen_at, is_active '
            'FROM paired_devices ORDER BY last_seen_at DESC LIMIT 20'
        )
        paired_rows = cur.fetchall()
    except sqlite3.Error:
        paired_rows = []
    conn.close()
    paired = [
        {
            'device_id': row['device_id'],
            'device_name': row['device_name'],
            'paired_at': row['paired_at'] or '',
            'last_seen_at': row['last_seen_at'] or '',
            'is_active': bool(int(row['is_active'] or 0)),
        }
        for row in paired_rows
    ]
    available = _bt_list_serial_ports()
    # Snapshot the deque under a list() to avoid emitting half-mutated entries
    # if the worker thread appends mid-serialization. Last 10 only.
    recent = list(_bt_recent_attempts)[-10:]
    recent.reverse()  # Newest-first for the UI.
    return jsonify({
        'enabled': enabled,
        'com_port': com_port,
        'last_sync_at': last_sync_at,
        'last_error': last_error,
        'available_ports': available,
        # The port the server *would* listen on if the user just toggled
        # Enable without picking anything. The JS UI uses this for the
        # "Smart pick" UX so the user doesn't need to know about COM ports.
        'recommended_port': available[0]['device'] if available else '',
        'paired_devices': paired,
        'recent_attempts': recent,
        # True while the daemon thread currently holds the COM port open.
        # Single-bool read of a module-level flag (atomic in CPython under
        # the GIL); good enough for a diagnostic indicator.
        'server_listening': bool(_bt_server_listening),
    })


@app.route('/api/bt/configure', methods=['POST'])
def bt_configure():
    if CLOUD_MODE:
        return jsonify({'error': 'Bluetooth sync is local-server only'}), 400
    data = request.get_json(silent=True) or {}
    enabled = data.get('enabled')
    if not isinstance(enabled, bool):
        return jsonify({'error': 'enabled (bool) required'}), 400
    com_port = data.get('com_port')
    if com_port is None:
        com_port = ''
    elif not isinstance(com_port, str):
        return jsonify({'error': 'com_port must be a string'}), 400
    com_port = com_port.strip()
    # Smart pick: if enabling without a port, fall back to whatever Windows
    # has registered as a Bluetooth port. The user can override later.
    auto_picked = False
    if enabled and not com_port:
        com_port = _bt_pick_default_port()
        auto_picked = bool(com_port)
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    write_app_setting(cur, 'bt_sync_enabled', '1' if enabled else '0')
    write_app_setting(cur, 'bt_sync_com_port', com_port)
    # Saving fresh settings clears the previous error — the next loop
    # iteration on the worker thread will either re-error or recover.
    write_app_setting(cur, 'bt_last_error', '')
    conn.commit()
    conn.close()
    return jsonify({
        'ok': True,
        'com_port': com_port,
        'auto_picked': auto_picked,
    })


@app.route('/api/license/activate', methods=['POST'])
def activate_license():
    data = request.json or {}
    serial_number = str(data.get('serial_number') or '').strip().upper()
    clinic_name = str(data.get('clinic_name') or '').strip()
    device_id = str(data.get('device_id') or '').strip()
    device_name = str(data.get('device_name') or '').strip()

    if len(serial_number) < 8:
        return jsonify({'error': 'Serial number must be at least 8 characters'}), 400

    try:
        max_devices = int(data.get('max_devices', 2))
    except (TypeError, ValueError):
        return jsonify({'error': 'max_devices must be a number'}), 400

    if max_devices < 1:
        return jsonify({'error': 'max_devices must be at least 1'}), 400

    plan_name = str(data.get('plan_name') or 'starter').strip() or 'starter'
    now_dt = _naive_utc_now()
    expires_at = (now_dt + timedelta(days=DEFAULT_LICENSE_DAYS)).strftime('%Y-%m-%d')
    grace_until = (datetime.strptime(expires_at, '%Y-%m-%d') + timedelta(days=DEFAULT_LICENSE_GRACE_DAYS)).strftime('%Y-%m-%d')

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT serial_number, status, max_devices, expires_at, grace_until FROM licenses WHERE serial_number = ?', (serial_number,))
    existing = cursor.fetchone()

    if existing:
        existing_status = str(existing[1] or 'active')
        if existing_status in ('revoked', 'suspended'):
            conn.close()
            return jsonify({'error': f'License is {existing_status}'}), 403

        cursor.execute('''
            UPDATE licenses
            SET clinic_name = ?, plan_name = ?, status = 'active',
                max_devices = ?, updated_at = CURRENT_TIMESTAMP
            WHERE serial_number = ?
        ''', (clinic_name, plan_name, max_devices, serial_number))
        expires_at = existing[3] or expires_at
        grace_until = existing[4] or grace_until
    else:
        cursor.execute('''
            INSERT INTO licenses (
                serial_number, clinic_name, plan_name, status,
                max_devices, expires_at, grace_until, activated_at, updated_at
            )
            VALUES (?, ?, ?, 'active', ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ''', (serial_number, clinic_name, plan_name, max_devices, expires_at, grace_until))

    if device_id:
        cursor.execute('SELECT max_devices FROM licenses WHERE serial_number = ?', (serial_number,))
        license_row = cursor.fetchone()
        limit_count = int(license_row[0] or 1)

        cursor.execute('''
            SELECT 1 FROM license_devices
            WHERE serial_number = ? AND device_id = ?
        ''', (serial_number, device_id))
        existing_binding = cursor.fetchone()

        if not existing_binding:
            cursor.execute('''
                SELECT COUNT(*) FROM license_devices
                WHERE serial_number = ? AND is_active = 1
            ''', (serial_number,))
            active_device_count = int(cursor.fetchone()[0] or 0)
            if active_device_count >= limit_count:
                conn.close()
                return jsonify({'error': f'Max active devices reached ({limit_count})'}), 403

        cursor.execute('''
            INSERT INTO license_devices (serial_number, device_id, device_name, first_seen_at, last_seen_at, is_active)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1)
            ON CONFLICT(serial_number, device_id) DO UPDATE SET
                device_name = excluded.device_name,
                last_seen_at = CURRENT_TIMESTAMP,
                is_active = 1
        ''', (serial_number, device_id, device_name))

    write_app_setting(cursor, 'active_serial_number', serial_number)
    append_audit_log(cursor, 'activate', 'license', None, {
        'serial_number': serial_number,
        'clinic_name': clinic_name,
        'plan_name': plan_name,
        'device_id': device_id
    })
    # Create a device-bound offline license token (if possible)
    signing_key = get_or_create_license_signing_key(cursor)
    record = fetch_license_record(cursor, serial_number)
    offline_license_token = ''
    offline_license_payload = {}
    if record:
        validity = evaluate_license_window(record['status'], record['expires_at'], record['grace_until'])
        offline_license_payload, offline_license_token = serialize_offline_license(record, validity, signing_key, device_id=device_id)

    conn.commit()
    conn.close()

    resp = {
        'success': True,
        'serial_number': serial_number,
        'plan_name': plan_name,
        'expires_at': expires_at,
        'grace_until': grace_until
    }
    if offline_license_token:
        resp['offline_license_token'] = offline_license_token
        resp['offline_license'] = offline_license_payload

    return jsonify(resp)


@app.route('/api/license/login', methods=['POST'])
def license_login():
    data = request.json or {}
    serial_number = str(data.get('serial_number') or '').strip().upper()
    if len(serial_number) < 8:
        return jsonify({'error': 'Serial number must be at least 8 characters'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    record = fetch_license_record(cursor, serial_number)
    if not record:
        conn.close()
        return jsonify({'error': 'Serial not found'}), 404

    validity = evaluate_license_window(record['status'], record['expires_at'], record['grace_until'])
    if not validity['licensed']:
        conn.close()
        return jsonify({
            'error': 'Serial is not active for login',
            'status': record['status'],
            'expires_at': record['expires_at'],
            'grace_until': record['grace_until']
        }), 403

    downloads = get_mobile_download_options(cursor)
    write_app_setting(cursor, 'active_serial_number', serial_number)
    append_audit_log(cursor, 'login', 'license', None, {'serial_number': serial_number, 'portal': 'mobile-download'})

    signing_key = get_or_create_license_signing_key(cursor)
    payload = build_offline_license_payload(record, validity)
    offline_license_token = encode_offline_license_token(payload, signing_key)

    conn.commit()
    conn.close()

    return jsonify({
        'success': True,
        'serial_number': serial_number,
        'clinic_name': record['clinic_name'],
        'plan_name': record['plan_name'],
        'status': record['status'],
        'expires_at': record['expires_at'],
        'grace_until': record['grace_until'],
        'in_grace': validity['in_grace'],
        'offline_license_token': offline_license_token,
        'offline_license': payload,
        'downloads': downloads
    })


@app.route('/api/license/offline-verify', methods=['POST'])
def license_offline_verify():
    data = request.json or {}
    token = str(data.get('offline_license_token') or '').strip()
    device_id = str(data.get('device_id') or '').strip()
    if not token:
        return jsonify({'error': 'Offline license token is required'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    signing_key = get_or_create_license_signing_key(cursor)
    payload = verify_offline_license_token(token, signing_key)
    if not payload:
        conn.close()
        return jsonify({'error': 'Offline license is invalid or expired'}), 403

    # If the token was issued bound to a device, and the requester supplied a device_id,
    # ensure they match. If token has no device_id, it's considered unbound.
    token_device = str(payload.get('device_id') or '').strip()
    if token_device and device_id and token_device != device_id:
        conn.close()
        return jsonify({'error': 'License token locked to different device', 'detail': 'Device mismatch'}), 403

    downloads = get_mobile_download_options(cursor)
    conn.close()
    return jsonify({'success': True, 'offline_license': payload, 'downloads': downloads})


@app.route('/api/mobile/download-links', methods=['GET', 'POST'])
def mobile_download_links():
    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == 'GET':
        serial_number = str(request.args.get('serial_number') or '').strip().upper()
        if serial_number:
            record = fetch_license_record(cursor, serial_number)
            if not record:
                conn.close()
                return jsonify({'error': 'Serial not found'}), 404
            validity = evaluate_license_window(record['status'], record['expires_at'], record['grace_until'])
            if not validity['licensed']:
                conn.close()
                return jsonify({'error': 'Serial is not active'}), 403

        links = get_mobile_download_options(cursor)
        conn.close()
        return jsonify({'success': True, 'downloads': links})

    data = request.json or {}
    android_url = str(data.get('android_url') or '').strip()
    ios_url = str(data.get('ios_url') or '').strip()

    if not android_url and not ios_url:
        return jsonify({'error': 'At least one URL is required'}), 400

    if android_url:
        write_app_setting(cursor, 'mobile_android_download_url', android_url)
    if ios_url:
        write_app_setting(cursor, 'mobile_ios_download_url', ios_url)

    append_audit_log(cursor, 'update', 'mobile_download_links', None, {
        'android_url': android_url,
        'ios_url': ios_url
    })
    conn.commit()
    links = get_mobile_download_options(cursor)
    conn.close()
    return jsonify({'success': True, 'downloads': links})


@app.route('/api/license/status')
def license_status():
    conn = get_db_connection()
    cursor = conn.cursor()
    active_serial = read_app_setting(cursor, 'active_serial_number', '')

    if not active_serial:
        cursor.execute('''
            SELECT serial_number
            FROM licenses
            WHERE status = 'active'
            ORDER BY updated_at DESC, activated_at DESC
            LIMIT 1
        ''')
        row = cursor.fetchone()
        if row:
            active_serial = row[0]

    if not active_serial:
        conn.close()
        return jsonify({'licensed': False, 'message': 'No active license'})

    record = fetch_license_record(cursor, active_serial)
    if not record:
        conn.close()
        return jsonify({'licensed': False, 'message': 'Active serial not found'})

    cursor.execute('''
        SELECT COUNT(*)
        FROM license_devices
        WHERE serial_number = ? AND is_active = 1
    ''', (record['serial_number'],))
    active_devices = int(cursor.fetchone()[0] or 0)
    conn.close()

    validity = evaluate_license_window(record['status'], record['expires_at'], record['grace_until'])

    return jsonify({
        'licensed': validity['licensed'],
        'serial_number': record['serial_number'],
        'clinic_name': record['clinic_name'],
        'plan_name': record['plan_name'],
        'status': record['status'],
        'max_devices': record['max_devices'],
        'active_devices': active_devices,
        'expires_at': record['expires_at'],
        'grace_until': record['grace_until'],
        'in_grace': validity['in_grace']
    })


@app.route('/api/clinic-settings', methods=['GET', 'POST'])
def clinic_settings():
    conn = get_db_connection(with_row_factory=True)
    cursor = conn.cursor()
    if request.method == 'GET':
        doctor_name    = read_app_setting(cursor, 'doctor_name',    CLINIC_CONFIG['DOCTOR_NAME'])
        doctor_name_ar = read_app_setting(cursor, 'doctor_name_ar', CLINIC_CONFIG['DOCTOR_NAME_AR'])
        conn.close()
        return jsonify({'doctor_name': doctor_name, 'doctor_name_ar': doctor_name_ar})
    data = request.json or {}
    name_en = (data.get('doctor_name') or '').strip()
    name_ar = (data.get('doctor_name_ar') or '').strip()
    if not name_en and not name_ar:
        conn.close()
        return jsonify({'error': 'At least one name is required'}), 400
    if name_en:
        write_app_setting(cursor, 'doctor_name', name_en)
    if name_ar:
        write_app_setting(cursor, 'doctor_name_ar', name_ar)
    effective_en = name_en or read_app_setting(cursor, 'doctor_name', CLINIC_CONFIG['DOCTOR_NAME'])
    effective_ar = name_ar or read_app_setting(cursor, 'doctor_name_ar', CLINIC_CONFIG['DOCTOR_NAME_AR'])
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'doctor_name': effective_en, 'doctor_name_ar': effective_ar})

import logging as _logging

# One-line JSON access log per request when CLINIC_LOG_FORMAT=json. Default
# text leaves Flask's stdout logging alone — set the env var on the cloud node
# to make logs parseable by log shippers (Better Stack, Datadog, CloudWatch, etc.).
_REQUEST_LOG = _logging.getLogger('clinic.access')


def _configure_access_logging():
    if os.environ.get('CLINIC_LOG_FORMAT', 'text').lower() != 'json':
        return
    _REQUEST_LOG.setLevel(_logging.INFO)
    if not _REQUEST_LOG.handlers:
        handler = _logging.StreamHandler(sys.stdout)
        # The message IS the JSON payload — no extra formatting.
        handler.setFormatter(_logging.Formatter('%(message)s'))
        _REQUEST_LOG.addHandler(handler)
    _REQUEST_LOG.propagate = False  # avoid double-emit via root logger


_configure_access_logging()


@app.before_request
def _access_log_start():
    g._req_started_at = time.time()


@app.after_request
def _access_log_end(response):
    if os.environ.get('CLINIC_LOG_FORMAT', 'text').lower() != 'json':
        return response
    try:
        started = getattr(g, '_req_started_at', None)
        latency_ms = int((time.time() - started) * 1000) if started else 0
        payload = {
            'ts': datetime.now(timezone.utc).isoformat(),
            'method': request.method,
            'path': request.path,
            'status': response.status_code,
            'latency_ms': latency_ms,
        }
        clinic_id = getattr(g, 'clinic_id', None) if CLOUD_MODE else None
        if clinic_id is not None:
            payload['clinic_id'] = clinic_id
        _REQUEST_LOG.info(json.dumps(payload))
    except Exception:  # noqa: BLE001 — access log MUST NEVER tank a response
        pass
    return response


def _newest_backup_timestamp():
    """Walk the backups directory and return an ISO timestamp for the newest
    backup file, or None if none exist. Handles both the single-tenant flat
    layout (`backups/*.db`) and the per-tenant cloud layout (`backups/<label>/*.db`)."""
    try:
        if not BACKUP_DIR.exists():
            return None
        newest_mtime = 0.0
        for path in BACKUP_DIR.rglob('*.db'):
            try:
                mtime = path.stat().st_mtime
                if mtime > newest_mtime:
                    newest_mtime = mtime
            except OSError:
                continue
        if newest_mtime == 0.0:
            return None
        return datetime.fromtimestamp(newest_mtime, tz=timezone.utc).isoformat()
    except Exception:  # noqa: BLE001 — health checks must never raise
        return None


@app.route('/healthz')
def healthz():
    """Unauthenticated liveness/readiness probe.

    Designed for external monitoring (uptime checks, k8s probes). Returns 200
    if the database opens and a trivial query succeeds; 503 otherwise. Exposed
    on the cloud node without a clinic token (added to `_CLOUD_OPEN_EXACT`).

    The response is intentionally small — no per-tenant counts, no auth state —
    so it can be polled aggressively without hitting hot paths.
    """
    db_ok = True
    db_error = None
    try:
        # On the cloud node, _cloud_tenant_routing skips this path, so the
        # global DB_NAME default is whatever was last set — try opening the
        # master/single DB directly to keep this independent of routing state.
        target_db = MASTER_DB_PATH if CLOUD_MODE else str(DB_NAME)
        conn = sqlite3.connect(target_db, timeout=2.0)
        try:
            conn.execute('SELECT 1')
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001
        db_ok = False
        db_error = type(exc).__name__
    body = {
        'status': 'ok' if db_ok else 'degraded',
        'mode': 'cloud' if CLOUD_MODE else 'local',
        'db_writable': db_ok,
        'last_backup_at': _newest_backup_timestamp(),
        'uptime_seconds': int(time.time() - _APP_STARTED_AT),
    }
    if db_error:
        body['db_error'] = db_error
    return jsonify(body), (200 if db_ok else 503)


@app.route('/api/system/readiness')
def system_readiness():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM paired_devices WHERE is_active = 1')
    paired_devices = int(cursor.fetchone()[0] or 0)
    cursor.execute("SELECT COUNT(*) FROM licenses WHERE status = 'active'")
    active_licenses = int(cursor.fetchone()[0] or 0)
    cursor.execute('SELECT COUNT(*) FROM sync_snapshots')
    snapshot_count = int(cursor.fetchone()[0] or 0)
    conn.close()

    return jsonify({
        'ready': True,
        'paired_devices': paired_devices,
        'active_licenses': active_licenses,
        'sync_snapshots': snapshot_count
    })

@app.route('/api/patients/<int:patient_id>', methods=['PUT'])
def update_patient(patient_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    data = request.json or {}
    fields = []
    values = []
    allowed = ['first_name', 'last_name', 'phone', 'date_of_birth', 'birth_date', 'gender', 'address', 'notes', 'medical_history', 'email']
    for field in allowed:
        if field in data:
            col = 'date_of_birth' if field == 'birth_date' else field
            val = data[field]
            if col in ('date_of_birth',) and val:
                val = parse_date_input(val) or val
            fields.append(f'{col} = ?')
            values.append(val)
    if not fields:
        conn.close()
        return jsonify({'error': 'No fields to update'}), 400
    values.append(patient_id)
    cursor.execute(f'UPDATE patients SET {", ".join(fields)} WHERE id = ?', values)
    conn.commit()
    conn.close()
    return jsonify({'success': True})


@app.route('/api/patients/<int:patient_id>/credit', methods=['GET'])
def patient_credit(patient_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    balance = get_patient_credit_balance(cursor, patient_id)
    cursor.execute('SELECT * FROM patient_credit_transactions WHERE patient_id = ? ORDER BY id DESC', (patient_id,))
    rows = [list(r) for r in cursor.fetchall()]
    conn.close()
    return jsonify({'balance': balance, 'transactions': rows})


@app.route('/api/patients/<int:patient_id>/credit-adjustment', methods=['POST'])
def patient_credit_adjustment(patient_id):
    data = request.json or {}
    amount = float(data.get('amount', 0))
    note = str(data.get('note') or 'Manual adjustment')
    conn = get_db_connection()
    cursor = conn.cursor()
    # Store the signed amount so SUM(amount) is the running balance directly.
    cursor.execute('INSERT INTO patient_credit_transactions (patient_id, amount, type, note) VALUES (?, ?, ?, ?)',
                 (patient_id, amount, 'credit' if amount >= 0 else 'debit', note))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


def open_browser(port=5000):
    """Open browser after a short delay"""
    import time
    time.sleep(1.5)
    webbrowser.open(f'http://127.0.0.1:{port}')


# --- Automated database backups ------------------------------------------------
BACKUP_DIR = _DATA_DIR / 'backups'
try:
    BACKUP_RETENTION = max(1, int(os.environ.get('CLINIC_BACKUP_RETENTION', '20')))
except (TypeError, ValueError):
    BACKUP_RETENTION = 20
try:
    BACKUP_INTERVAL_HOURS = float(os.environ.get('CLINIC_BACKUP_INTERVAL_HOURS', '6'))
except (TypeError, ValueError):
    BACKUP_INTERVAL_HOURS = 6.0


def _list_databases_to_back_up():
    """Return [(label, src_path, dest_subdir)] for the backup loop.

    Single-tenant: one entry; snapshots land directly in BACKUP_DIR with the
    historic ``dental_clinic_<stamp>.db`` name (no subfolder — preserves the
    existing on-disk layout for installed clinics).
    Cloud node (``CLINIC_CLOUD_MODE=1``): the master registry + one entry per
    discovered ``clinic_<id>.db``, each in its own ``BACKUP_DIR/<label>/``
    subfolder so retention is tracked per tenant."""
    if CLOUD_MODE:
        entries = [('master', MASTER_DB_PATH, BACKUP_DIR / 'master')]
        for path in sorted(_DATA_DIR.glob('clinic_*.db')):
            label = path.stem  # e.g. 'clinic_1'
            entries.append((label, str(path), BACKUP_DIR / label))
        return entries
    return [('dental_clinic', str(DB_NAME), BACKUP_DIR)]


def run_database_backup():
    """Snapshot every active database with SQLite's online backup API (consistent
    and safe while the server is running, including in WAL mode), then prune each
    target folder to the most recent BACKUP_RETENTION files. Returns the list of
    snapshot paths written (empty on full failure). One failing DB doesn't abort
    the others."""
    written = []
    try:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(f'⚠️  Could not create backup dir {BACKUP_DIR}: {exc}')
        return written
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    for label, src_path, subdir in _list_databases_to_back_up():
        if not os.path.exists(src_path):
            continue
        try:
            subdir.mkdir(parents=True, exist_ok=True)
            dest_path = subdir / f'{label}_{stamp}.db'
        except OSError as exc:
            print(f'⚠️  Database backup failed for {label}: {exc}')
            continue
        try:
            src = sqlite3.connect(src_path)
            try:
                dst = sqlite3.connect(str(dest_path))
                try:
                    with dst:
                        src.backup(dst)
                finally:
                    dst.close()
            finally:
                src.close()
        except Exception as exc:  # noqa: BLE001 — one tenant's failure mustn't kill the rest
            print(f'⚠️  Database backup failed for {label}: {exc}')
            # sqlite3.connect(dst) creates the file before the backup runs, so a
            # failed src.backup() leaves a stub behind — clean it up so retention
            # pruning doesn't keep it around as a "valid" snapshot.
            try:
                dest_path.unlink()
            except OSError:
                pass
            continue
        written.append(str(dest_path))
        existing = sorted(subdir.glob(f'{label}_*.db'))
        for old in existing[:-BACKUP_RETENTION]:
            try:
                old.unlink()
            except OSError:
                pass
    return written


def _backup_loop():
    """Background worker: one backup shortly after startup, then every
    BACKUP_INTERVAL_HOURS hours."""
    import time
    time.sleep(8)
    while True:
        paths = run_database_backup()
        for path in paths:
            print(f'💾 Database backup written: {path}')
        time.sleep(max(0.1, BACKUP_INTERVAL_HOURS) * 3600)


# ── Cloud sync (the clinic's local server ⇄ the cloud node) ─────────────────
try:
    CLOUD_SYNC_INTERVAL_MINUTES = max(1.0, float(os.environ.get('CLINIC_CLOUD_SYNC_INTERVAL_MINUTES', '15')))
except ValueError:
    CLOUD_SYNC_INTERVAL_MINUTES = 15.0


# ── Bluetooth-SPP wire protocol ─────────────────────────────────────────────
# Frames are 4-byte big-endian unsigned length + UTF-8 JSON payload. The cap
# guards against a peer claiming a 4 GB frame; real deltas are a few KB.
BT_MAX_FRAME_BYTES = 4 * 1024 * 1024  # 4 MB


def encode_bt_frame(payload):
    """Encode a JSON-serialisable dict into a length-prefixed BT frame."""
    body = json.dumps(payload).encode('utf-8')
    if len(body) > BT_MAX_FRAME_BYTES:
        raise ValueError(f'frame too large: {len(body)} > {BT_MAX_FRAME_BYTES}')
    return len(body).to_bytes(4, 'big') + body


def _read_exactly(stream, n):
    """Read exactly n bytes from a stream, or raise EOFError."""
    chunks = []
    remaining = n
    while remaining > 0:
        chunk = stream.read(remaining)
        if not chunk:
            raise EOFError(f'stream closed after {n - remaining} of {n} bytes')
        chunks.append(chunk)
        remaining -= len(chunk)
    return b''.join(chunks)


def decode_bt_frame(stream):
    """Read one length-prefixed BT frame from a binary stream and return the
    decoded JSON dict. Raises EOFError on truncation, ValueError on malformed
    JSON or an oversized frame."""
    header = _read_exactly(stream, 4)
    length = int.from_bytes(header, 'big')
    if length > BT_MAX_FRAME_BYTES:
        raise ValueError(f'frame too large: {length} > {BT_MAX_FRAME_BYTES}')
    body = _read_exactly(stream, length)
    try:
        return json.loads(body.decode('utf-8'))
    except (UnicodeDecodeError, ValueError) as exc:
        raise ValueError(f'malformed JSON: {exc}') from exc


BT_PROTOCOL_VERSION = '1.0.0'


def _bt_lookup_device_by_token(cursor, token):
    """Return the device row for a token, or None. Mirrors the auth lookup
    in get_authenticated_device but without using request context."""
    if not token:
        return None
    cursor.execute(
        'SELECT device_id, device_name, is_active FROM paired_devices WHERE device_token = ?',
        (token,),
    )
    row = cursor.fetchone()
    if not row or int(row['is_active']) != 1:
        return None
    cursor.execute(
        'UPDATE paired_devices SET last_seen_at = CURRENT_TIMESTAMP WHERE device_id = ?',
        (row['device_id'],),
    )
    return {'device_id': row['device_id'], 'device_name': row['device_name']}


def _bt_pair_new_device(cursor, device_id, device_name):
    """Issue a fresh device_token over the BT-SPP channel. Used by op:bt_pair
    so a freshly-OS-Bluetooth-bonded peer can self-pair without the user
    juggling 6-digit codes — the OS bond + the configured BT-SPP COM port
    are the trust gates.

    Rotates the token on the existing row when device_id is already known,
    so a mobile that lost its stored token (reinstall, factory reset) can
    re-pair without leaking dead paired_devices rows."""
    token = secrets.token_urlsafe(32)
    cursor.execute('''
        INSERT INTO paired_devices (device_id, device_name, device_token, paired_at, last_seen_at, is_active)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1)
        ON CONFLICT(device_id) DO UPDATE SET
            device_name = excluded.device_name,
            device_token = excluded.device_token,
            last_seen_at = CURRENT_TIMESTAMP,
            is_active = 1
    ''', (device_id, device_name, token))
    append_audit_log(cursor, 'create', 'paired_device', None,
                     {'device_id': device_id, 'device_name': device_name, 'via': 'bt_pair'})
    return token


def _bt_handle_request(cursor, req, authed):
    """Dispatch one BT request. Returns (response_dict, new_authed_flag).
    Pure function — no I/O, no threading.

    Also drops a diagnostic breadcrumb into _bt_recent_attempts so the
    Settings UI can show recent connection attempts even when nothing
    persisted to bt_last_sync_at (e.g. auth failures)."""
    op = req.get('op')
    if op == 'hello':
        device = _bt_lookup_device_by_token(cursor, req.get('device_token'))
        if device is None:
            _bt_record_attempt('hello', outcome='unauthorized',
                               detail='invalid or missing device_token')
            return {'error': 'unauthorized'}, False
        _bt_record_attempt('hello', device_id=device.get('device_id'),
                           device_name=device.get('device_name'), outcome='ok')
        return {'ok': True, 'server_version': BT_PROTOCOL_VERSION}, True

    if op == 'bt_pair':
        device_id = str(req.get('device_id') or '').strip()
        if not device_id:
            _bt_record_attempt('bt_pair', outcome='rejected',
                               detail='device_id required')
            return {'error': 'device_id required'}, False
        device_name = str(req.get('device_name') or '').strip() or device_id
        try:
            token = _bt_pair_new_device(cursor, device_id, device_name)
        except Exception as exc:  # noqa: BLE001 — log & re-raise for the session loop
            _bt_record_attempt('bt_pair', device_id=device_id,
                               device_name=device_name, outcome='error',
                               detail=repr(exc))
            raise
        _bt_record_attempt('bt_pair', device_id=device_id,
                           device_name=device_name, outcome='ok')
        return {'ok': True, 'device_token': token,
                'server_version': BT_PROTOCOL_VERSION}, True

    if not authed:
        _bt_record_attempt(op or 'unknown', outcome='unauthorized',
                           detail='request before hello succeeded')
        return {'error': 'unauthorized'}, authed

    if op == 'sync_export':
        try:
            since_raw = req.get('since')
            since_dt = parse_timestamp_for_sync(since_raw) if since_raw else None
            tables, tombstones, _total = _collect_sync_export(cursor, since_dt)
        except Exception as exc:  # noqa: BLE001
            _bt_record_attempt('sync_export', outcome='error', detail=repr(exc))
            raise
        _bt_record_attempt('sync_export', outcome='ok')
        return {
            'ok': True,
            'tables': tables,
            'tombstones': tombstones,
            'generated_at': _naive_utc_now().isoformat(),
        }, authed

    if op == 'sync_import':
        try:
            applied, skipped, _tombs_applied, _by_table = _apply_sync_import(cursor, req)
        except Exception as exc:  # noqa: BLE001
            _bt_record_attempt('sync_import', outcome='error', detail=repr(exc))
            raise
        _bt_record_attempt('sync_import', outcome='ok',
                           detail=f'applied={applied} skipped={skipped}')
        return {'ok': True, 'applied': applied, 'skipped': skipped}, authed

    _bt_record_attempt(op or 'unknown', outcome='rejected', detail='unknown op')
    return {'error': 'unknown op'}, authed


def _bt_serve_session(stream_in, stream_out, db_path=None):
    """Drive one BT session: read frames, dispatch, write responses, exit
    when the peer disconnects or sends a malformed frame. Closes on the
    first unauthorized response (auth failure) or fatal protocol error.

    Returns True if at least one frame was dispatched (real peer
    interaction), False if the session ended at EOF before any frame was
    read. The daemon uses this to suppress a misleading "Last sync"
    timestamp on an idle read-timeout cycle that nothing actually used.

    Opens its own short-lived SQLite connection so the caller (the BT
    server thread) doesn't have to manage one. `db_path` defaults to
    DB_NAME — exposed for tests."""
    conn = sqlite3.connect(db_path or DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    authed = False
    processed_any = False
    try:
        while True:
            try:
                req = decode_bt_frame(stream_in)
            except EOFError:
                return processed_any
            except ValueError:
                try:
                    stream_out.write(encode_bt_frame({'error': 'malformed frame'}))
                    stream_out.flush()
                except Exception:
                    pass
                return processed_any
            resp, authed = _bt_handle_request(cursor, req, authed)
            try:
                stream_out.write(encode_bt_frame(resp))
                stream_out.flush()
            except Exception:
                return processed_any
            processed_any = True
            conn.commit()
            if 'error' in resp and resp['error'] == 'unauthorized':
                return processed_any
            # Terminal ops: the mobile client closes its BT connection right
            # after these (sync_import ends a sync round-trip; bt_pair is a
            # one-shot handshake on its own connection). Return now instead of
            # looping back into a blocking read — a Windows BT-SPP COM port
            # doesn't surface the peer's disconnect as a prompt EOF, so the
            # daemon would otherwise sit on the dead session for the full read
            # budget (~30s), during which the still-open port won't accept the
            # phone's next incoming connection (it fails with a connect error
            # every cycle after the first). Returning lets the daemon close +
            # reopen the port (~1s) and be listening again before the phone's
            # next 30s tick.
            if req.get('op') in ('sync_import', 'bt_pair'):
                return processed_any
    finally:
        try:
            conn.close()
        except Exception:
            pass


# How long the BT worker idles when disabled or after an error.
_BT_LOOP_SLEEP = 30.0
_BT_LOOP_ERROR_SLEEP = 15.0
_BT_LOOP_RECONNECT_SLEEP = 1.0  # Brief pause after a session ends before reopening the port.

# In-memory ring buffer of recent BT connection attempts. Deliberately not
# persisted — these are diagnostic breadcrumbs for the Settings UI; restart
# drops them. maxlen=20 caps the memory footprint and exposes the last 10 to
# the UI via /api/bt/status. Single-bool/append operations on a deque are
# thread-safe in CPython under the GIL, so we don't need an explicit lock.
_bt_recent_attempts = collections.deque(maxlen=20)

# Module-level flag: True while the daemon thread holds the COM port open in
# its current loop iteration. Read by /api/bt/status to drive the "Listening"
# indicator in the Settings card. A single bool write/read is atomic in
# CPython under the GIL — no lock needed.
_bt_server_listening = False


def _bt_record_attempt(op, device_id=None, device_name=None, outcome='ok', detail=''):
    """Append one diagnostic breadcrumb to _bt_recent_attempts. O(1).
    Called from the request dispatcher after each op completes (success or
    failure). Intentionally does NOT touch SQLite — these are throw-away
    breadcrumbs, not audit log entries."""
    try:
        ts = _naive_utc_now().isoformat()
    except Exception:
        ts = ''
    entry = {
        'ts': ts,
        'op': op or '',
        'device_id': device_id or '',
        'device_name': device_name or '',
        'outcome': outcome or '',
        'detail': (detail or '')[:160],
    }
    _bt_recent_attempts.append(entry)


# ── Native Windows RFCOMM listener (AF_BTH) ────────────────────────────────
#
# Replaces the Windows "Incoming COM port" requirement. The pyserial COM-port
# path remains as fallback in bt_sync_server() when this native path can't
# bind (older Windows / no BT radio / API error). See:
#   docs/superpowers/specs/2026-05-29-bluetooth-zero-setup-ux-design.md
#
# The radio cannot be unit-tested; the only testable seam is the accept→serve
# loop in _bt_accept_and_serve, which Task 3 exercises with injected fakes.

import ctypes as _ct
from ctypes import wintypes as _wt
import socket as _stdsocket  # importing initializes Winsock for the process

_AF_BTH = 32
_SOCK_STREAM = 1
_BTHPROTO_RFCOMM = 3
_BT_PORT_ANY = 0xFFFFFFFF  # (ULONG)-1; tells the stack to assign a channel
_NS_BTH = 16
_RNRSERVICE_REGISTER = 0
_RNRSERVICE_DELETE = 1
_INVALID_SOCKET = _ct.c_void_p(-1).value


class _GUID(_ct.Structure):
    _fields_ = [
        ('Data1', _wt.DWORD),
        ('Data2', _wt.WORD),
        ('Data3', _wt.WORD),
        ('Data4', _ct.c_ubyte * 8),
    ]


# Serial Port Profile service class UUID: 00001101-0000-1000-8000-00805F9B34FB
# Android's BluetoothConnection.toAddress() looks up this exact UUID via SDP.
_SPP_UUID = _GUID(
    0x00001101, 0x0000, 0x1000,
    (_ct.c_ubyte * 8)(0x80, 0x00, 0x00, 0x80, 0x5F, 0x9B, 0x34, 0xFB),
)


class _SOCKADDR_BTH(_ct.Structure):
    _fields_ = [
        ('addressFamily', _wt.USHORT),
        ('btAddr', _ct.c_ulonglong),
        ('serviceClassId', _GUID),
        ('port', _wt.ULONG),
    ]


class _SOCKET_ADDRESS(_ct.Structure):
    _fields_ = [
        ('lpSockaddr', _ct.POINTER(_SOCKADDR_BTH)),
        ('iSockaddrLength', _ct.c_int),
    ]


class _CSADDR_INFO(_ct.Structure):
    _fields_ = [
        ('LocalAddr', _SOCKET_ADDRESS),
        ('RemoteAddr', _SOCKET_ADDRESS),
        ('iSocketType', _ct.c_int),
        ('iProtocol', _ct.c_int),
    ]


class _WSAQUERYSET(_ct.Structure):
    _fields_ = [
        ('dwSize', _wt.DWORD),
        ('lpszServiceInstanceName', _wt.LPWSTR),
        ('lpServiceClassId', _ct.POINTER(_GUID)),
        ('lpVersion', _ct.c_void_p),
        ('lpszComment', _wt.LPWSTR),
        ('dwNameSpace', _wt.DWORD),
        ('lpNSProviderId', _ct.POINTER(_GUID)),
        ('lpszContext', _wt.LPWSTR),
        ('dwNumberOfProtocols', _wt.DWORD),
        ('lpafpProtocols', _ct.c_void_p),
        ('lpszQueryString', _wt.LPWSTR),
        ('dwNumberOfCsAddrs', _wt.DWORD),
        ('lpcsaBuffer', _ct.POINTER(_CSADDR_INFO)),
        ('dwOutputFlags', _wt.DWORD),
        ('lpBlob', _ct.c_void_p),
    ]


try:
    _ws2 = _ct.WinDLL('ws2_32', use_last_error=True)
    _ws2.socket.restype = _ct.c_void_p
    _ws2.socket.argtypes = [_ct.c_int, _ct.c_int, _ct.c_int]
    _ws2.bind.restype = _ct.c_int
    _ws2.bind.argtypes = [_ct.c_void_p, _ct.c_void_p, _ct.c_int]
    _ws2.listen.restype = _ct.c_int
    _ws2.listen.argtypes = [_ct.c_void_p, _ct.c_int]
    _ws2.accept.restype = _ct.c_void_p
    _ws2.accept.argtypes = [_ct.c_void_p, _ct.c_void_p, _ct.POINTER(_ct.c_int)]
    _ws2.recv.restype = _ct.c_int
    _ws2.recv.argtypes = [_ct.c_void_p, _ct.c_char_p, _ct.c_int, _ct.c_int]
    _ws2.send.restype = _ct.c_int
    _ws2.send.argtypes = [_ct.c_void_p, _ct.c_char_p, _ct.c_int, _ct.c_int]
    _ws2.closesocket.restype = _ct.c_int
    _ws2.closesocket.argtypes = [_ct.c_void_p]
    _ws2.getsockname.restype = _ct.c_int
    _ws2.getsockname.argtypes = [_ct.c_void_p, _ct.c_void_p, _ct.POINTER(_ct.c_int)]
    _ws2.WSASetServiceW.restype = _ct.c_int
    _ws2.WSASetServiceW.argtypes = [_ct.POINTER(_WSAQUERYSET), _ct.c_int, _wt.DWORD]
    _BT_NATIVE_AVAILABLE = True
except (AttributeError, OSError):
    # Not Windows, or ws2_32 missing the symbols we need (very old SKUs).
    _ws2 = None
    _BT_NATIVE_AVAILABLE = False


class _NativeBtSocket:
    """Duck-types recv/sendall/close around a raw Winsock SOCKET handle so
    _BtSocketStream doesn't care it's not a Python socket."""

    def __init__(self, handle):
        self._h = handle

    def recv(self, n):
        buf = _ct.create_string_buffer(n)
        ret = _ws2.recv(self._h, buf, n, 0)
        if ret <= 0:
            return b''  # EOF or error — caller treats as EOF
        return bytes(buf.raw[:ret])

    def sendall(self, data):
        view = memoryview(data)
        offset = 0
        while offset < len(view):
            chunk = bytes(view[offset:])
            ret = _ws2.send(self._h, chunk, len(chunk), 0)
            if ret <= 0:
                raise OSError(
                    f'BT send failed: WSAError={_ct.get_last_error()}')
            offset += ret

    def close(self):
        try:
            _ws2.closesocket(self._h)
        except Exception:
            pass


def _bt_open_native_listener():
    """Open + advertise + listen on an AF_BTH RFCOMM socket. Returns the
    listening socket handle, or raises OSError if the native path is
    unavailable on this machine. Caller (bt_sync_server) treats OSError as
    "fall back to COM port".

    Side effect: publishes an SDP record under the SPP UUID so Android's
    BluetoothConnection.toAddress() finds us without a fixed channel."""
    if not _BT_NATIVE_AVAILABLE:
        raise OSError('AF_BTH not available on this build')
    _stdsocket  # ensure Winsock is started (importing is sufficient)
    sock = _ws2.socket(_AF_BTH, _SOCK_STREAM, _BTHPROTO_RFCOMM)
    if sock in (None, 0) or sock == _INVALID_SOCKET:
        raise OSError(
            f'AF_BTH socket() failed: WSAError={_ct.get_last_error()}')
    addr = _SOCKADDR_BTH()
    addr.addressFamily = _AF_BTH
    addr.btAddr = 0
    addr.serviceClassId = _SPP_UUID
    addr.port = _BT_PORT_ANY
    if _ws2.bind(sock, _ct.byref(addr), _ct.sizeof(addr)) != 0:
        err = _ct.get_last_error()
        _ws2.closesocket(sock)
        raise OSError(f'AF_BTH bind() failed: WSAError={err}')
    addr_len = _ct.c_int(_ct.sizeof(addr))
    if _ws2.getsockname(sock, _ct.byref(addr), _ct.byref(addr_len)) != 0:
        err = _ct.get_last_error()
        _ws2.closesocket(sock)
        raise OSError(f'AF_BTH getsockname() failed: WSAError={err}')
    if _ws2.listen(sock, 1) != 0:
        err = _ct.get_last_error()
        _ws2.closesocket(sock)
        raise OSError(f'AF_BTH listen() failed: WSAError={err}')
    # Publish SDP record so the phone finds us by SPP UUID.
    csa = _CSADDR_INFO()
    csa.LocalAddr.lpSockaddr = _ct.pointer(addr)
    csa.LocalAddr.iSockaddrLength = _ct.sizeof(addr)
    csa.iSocketType = _SOCK_STREAM
    csa.iProtocol = _BTHPROTO_RFCOMM
    wqs = _WSAQUERYSET()
    wqs.dwSize = _ct.sizeof(wqs)
    wqs.lpszServiceInstanceName = 'DentaCare Sync'
    wqs.lpServiceClassId = _ct.pointer(_SPP_UUID)
    wqs.dwNameSpace = _NS_BTH
    wqs.dwNumberOfCsAddrs = 1
    wqs.lpcsaBuffer = _ct.pointer(csa)
    if _ws2.WSASetServiceW(_ct.byref(wqs), _RNRSERVICE_REGISTER, 0) != 0:
        err = _ct.get_last_error()
        _ws2.closesocket(sock)
        raise OSError(f'WSASetService(REGISTER) failed: WSAError={err}')
    return sock


def _bt_close_native_listener(handle):
    """Best-effort teardown. Windows drops the SDP record when the registering
    process exits, so we just close the socket — sufficient for daemon=True."""
    try:
        if handle:
            _ws2.closesocket(handle)
    except Exception:
        pass


@contextlib.contextmanager
def _bt_native_listener_session():
    """Open the native AF_BTH RFCOMM listener and guarantee its close runs
    regardless of how the body exits — including BaseException
    (KeyboardInterrupt, SystemExit). Yields the listener handle.

    Raises OSError if the native path is unavailable on this machine;
    callers treat that as 'fall back to COM port'."""
    handle = _bt_open_native_listener()
    try:
        yield handle
    finally:
        _bt_close_native_listener(handle)


def _bt_native_accept(listener_handle, stop_event):
    """Block on accept() for one connection. stop_event is honored at the
    session boundary by the outer worker loop (same model the COM-port path
    uses); daemon=True kills any in-flight accept on process exit."""
    addr = _SOCKADDR_BTH()
    addr_len = _ct.c_int(_ct.sizeof(addr))
    handle = _ws2.accept(
        listener_handle, _ct.byref(addr), _ct.byref(addr_len))
    if handle is None or handle == _INVALID_SOCKET:
        return None
    return handle


def _bt_accept_and_serve(listener_handle, stop_event, db_path=None,
                         _accept_fn=None, _wrap_sock=None):
    """Accept one peer, wrap, dispatch via _bt_serve_session. Returns the
    processed flag from _bt_serve_session (False = EOF before any frame).

    _accept_fn / _wrap_sock are injectable seams for tests; defaults are the
    real Winsock accept + _NativeBtSocket."""
    accept_fn = _accept_fn or _bt_native_accept
    wrap_fn = _wrap_sock or (lambda h: _NativeBtSocket(h))
    conn_handle = accept_fn(listener_handle, stop_event)
    if conn_handle is None:
        return False
    sock = wrap_fn(conn_handle)
    stream = _BtSocketStream(sock)
    try:
        return _bt_serve_session(stream, stream, db_path=db_path)
    finally:
        try:
            sock.close()
        except Exception:
            pass


class _BtSocketStream:
    """Adapts a connected socket-like object (anything with recv/sendall/close)
    onto the .read(n)/.write/.flush surface that _bt_serve_session +
    encode_bt_frame/decode_bt_frame already use for the COM-port path. Lets the
    new native RFCOMM listener reuse _bt_serve_session verbatim."""

    def __init__(self, sock):
        self._sock = sock

    def read(self, n):
        """Up to n bytes. Short reads (incl. zero on EOF) are allowed —
        decode_bt_frame's _read_exactly turns a short read into EOFError."""
        chunks = []
        remaining = n
        while remaining > 0:
            chunk = self._sock.recv(remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        return b''.join(chunks)

    def write(self, data):
        self._sock.sendall(data)

    def flush(self):
        pass

    def close(self):
        try:
            self._sock.close()
        except Exception:
            pass


def _bt_open_port(port, baudrate=115200, timeout=30.0):
    """Open a pyserial port. Indirection so tests can swap this.

    `timeout` is the per-read budget. It must be long enough that an idle
    listener doesn't EOF before a phone has a chance to connect and write its
    first frame — a 1s budget produces a ~1s open window per loop iteration on
    Windows, which a roaming phone almost never lands in. 30s is comfortably
    long for SPP handshake latency while still letting the loop check
    stop_event between iterations."""
    import serial as _pyserial
    return _pyserial.Serial(port, baudrate=baudrate, timeout=timeout)


def bt_sync_server(stop_event=None):
    """Daemon loop: each cycle, re-read settings, prefer the native AF_BTH
    listener (no Windows COM port), fall back to the existing pyserial
    COM-port path if the native one can't bind. Skipped on cloud / debug
    parent.

    Module-level _bt_server_listening reflects whichever path currently holds
    the listener open, so /api/bt/status's diagnostic stays accurate."""
    import serial as _pyserial
    global _bt_server_listening
    while stop_event is None or not stop_event.is_set():
        try:
            conn = get_db_connection()
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            enabled = read_app_setting(cur, 'bt_sync_enabled', '0') == '1'
            com_port_setting = (read_app_setting(cur, 'bt_sync_com_port', '') or '').strip()
            conn.close()
        except sqlite3.Error:
            enabled, com_port_setting = False, ''
        if not enabled:
            _bt_server_listening = False
            _bt_sleep(_BT_LOOP_SLEEP, stop_event)
            continue
        # Strategy: try the native RFCOMM listener first. Any OSError on open
        # → fall back to the COM-port path (today's behaviour) so legacy
        # machines don't regress. The context manager guarantees the listener
        # is closed even if _bt_accept_and_serve raises BaseException, so
        # Ctrl+C / SystemExit don't leak the Winsock handle.
        try:
            with _bt_native_listener_session() as native_handle:
                _bt_server_listening = True
                try:
                    processed = _bt_accept_and_serve(native_handle, stop_event)
                except Exception as exc:  # noqa: BLE001
                    _bt_record_error(f'{type(exc).__name__}: {exc}')
                    processed = False
                finally:
                    _bt_server_listening = False
            if processed:
                _bt_record_success()
            _bt_sleep(_BT_LOOP_RECONNECT_SLEEP, stop_event)
            continue
        except OSError as exc:
            _bt_record_attempt(
                op='listen', outcome='rejected',
                detail=f'native unavailable: {exc} — using COM fallback')
        # ── COM-port fallback (legacy path) ──
        port = com_port_setting or _bt_pick_default_port()
        if not port:
            _bt_server_listening = False
            _bt_record_error('no bluetooth port available')
            _bt_sleep(_BT_LOOP_ERROR_SLEEP, stop_event)
            continue
        try:
            ser = _bt_open_port(port)
            _bt_server_listening = True
            try:
                with ser:
                    processed = _bt_serve_session(ser, ser)
            finally:
                _bt_server_listening = False
            if processed:
                _bt_record_success()
            _bt_sleep(_BT_LOOP_RECONNECT_SLEEP, stop_event)
        except _pyserial.SerialException as exc:
            _bt_server_listening = False
            _bt_record_error(f'serial: {exc}')
            _bt_sleep(_BT_LOOP_ERROR_SLEEP, stop_event)
        except Exception as exc:  # noqa: BLE001
            _bt_server_listening = False
            _bt_record_error(f'{type(exc).__name__}: {exc}')
            _bt_sleep(_BT_LOOP_ERROR_SLEEP, stop_event)


def _bt_sleep(seconds, stop_event):
    """Sleep up to `seconds`, waking early if stop_event fires."""
    if stop_event is None:
        time.sleep(seconds)
        return
    stop_event.wait(timeout=seconds)


def _bt_record_success():
    try:
        conn = get_db_connection()
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        write_app_setting(cur, 'bt_last_sync_at', _naive_utc_now().isoformat())
        write_app_setting(cur, 'bt_last_error', '')
        conn.commit()
        conn.close()
    except sqlite3.Error:
        pass


def _bt_record_error(message):
    try:
        conn = get_db_connection()
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        write_app_setting(cur, 'bt_last_error', message[:300])
        conn.commit()
        conn.close()
    except sqlite3.Error:
        pass


def _cloud_http_request(method, url, headers=None, body=None, timeout=15):
    """Tiny JSON HTTP helper (stdlib only). Returns (status_code, parsed_body).
    HTTP error responses (4xx/5xx with a body) are returned, not raised; a real
    connection failure (URLError) propagates."""
    data = json.dumps(body).encode('utf-8') if body is not None else None
    hdrs = dict(headers or {})
    if data is not None:
        hdrs.setdefault('Content-Type', 'application/json')
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, _safe_json(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, _safe_json(exc.read().decode('utf-8'))
        except Exception:
            return exc.code, {}


def _cloud_sync_config():
    """Return (cloud_url, clinic_token, interval_minutes). url/token are None if
    not configured. Env vars (CLINIC_CLOUD_URL / CLINIC_CLOUD_TOKEN) win over the
    values saved by /api/cloud/pair in app_settings."""
    url = os.environ.get('CLINIC_CLOUD_URL', '').strip()
    token = os.environ.get('CLINIC_CLOUD_TOKEN', '').strip()
    if not (url and token):
        try:
            conn = sqlite3.connect(DB_NAME)
            cur = conn.cursor()
            url = url or (read_app_setting(cur, 'cloud_url', '') or '')
            token = token or (read_app_setting(cur, 'cloud_clinic_token', '') or '')
            conn.close()
        except sqlite3.Error:
            pass
    return (url.rstrip('/') or None), (token or None), CLOUD_SYNC_INTERVAL_MINUTES


def _run_cloud_sync_once(cloud_url, clinic_token, http=None):
    """One pull-then-push cycle against the cloud node. Records the outcome in
    app_settings (cloud_last_sync_at / cloud_last_sync_result / cloud_last_*_at)
    and returns a result dict. Never raises."""
    http = http or _cloud_http_request
    cloud_url = (cloud_url or '').rstrip('/')
    headers = {'X-Clinic-Token': clinic_token}
    result = {'ok': False, 'pulled': 0, 'pushed': 0, 'tombstones_applied': 0, 'at': utc_now_iso()}
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    try:
        # --- pull ---
        last_pull = read_app_setting(cur, 'cloud_last_pull_at', '') or ''
        pull_url = f'{cloud_url}/api/sync/export'
        if last_pull:
            pull_url += '?since=' + urllib.parse.quote(last_pull)
        status, payload = http('GET', pull_url, headers)
        if status != 200:
            raise RuntimeError(f'pull HTTP {status}: {payload}')
        applied, _skipped, tombs, _bt = _apply_sync_import(cur, payload)
        result['pulled'], result['tombstones_applied'] = applied, tombs
        write_app_setting(cur, 'cloud_last_pull_at', str(payload.get('generated_at') or utc_now_iso()))
        conn.commit()
        # --- push ---
        last_push = read_app_setting(cur, 'cloud_last_push_at', '') or ''
        since_dt = parse_timestamp_for_sync(last_push) if last_push else None
        tables, tombstones, total = _collect_sync_export(cur, since_dt)
        status, resp = http('POST', f'{cloud_url}/api/sync/import', headers,
                            {'tables': tables, 'tombstones': tombstones})
        if status != 200:
            raise RuntimeError(f'push HTTP {status}: {resp}')
        result['pushed'] = resp.get('applied_total', total) if isinstance(resp, dict) else total
        write_app_setting(cur, 'cloud_last_push_at', utc_now_iso())
        write_app_setting(cur, 'cloud_last_sync_at', result['at'])
        write_app_setting(cur, 'cloud_last_sync_result', 'ok')
        conn.commit()
        result['ok'] = True
    except Exception as exc:  # noqa: BLE001 - network/HTTP/parse errors all become a recorded result
        result['error'] = str(exc)
        try:
            write_app_setting(cur, 'cloud_last_sync_at', result['at'])
            write_app_setting(cur, 'cloud_last_sync_result', f'error: {exc}'[:300])
            conn.commit()
        except sqlite3.Error:
            pass
    finally:
        conn.close()
    return result


def cloud_sync_worker():
    """Background loop on the clinic's LOCAL server: mirror to/from the cloud node
    every CLINIC_CLOUD_SYNC_INTERVAL_MINUTES, whenever a cloud URL + clinic token
    are configured. Skips quietly when offline (the failed round is just recorded)."""
    time.sleep(20)  # let startup finish
    while True:
        url, token, interval = _cloud_sync_config()
        if url and token:
            try:
                _run_cloud_sync_once(url, token)
            except Exception:
                pass  # _run_cloud_sync_once records its own errors; never crash the loop
        time.sleep(max(60.0, interval * 60.0))


if __name__ == '__main__':
    # Windows defaults stdout/stderr to the locale code page (cp1252 on
    # most English installs), which crashes the moment we print an emoji.
    # Force UTF-8 with replacement so the banner and access log never bring
    # the server down on a Unicode-unfriendly terminal.
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding='utf-8', errors='replace')
        except (AttributeError, OSError):
            pass

    host = os.environ.get('CLINIC_HOST', '127.0.0.1')
    port_raw = os.environ.get('CLINIC_PORT', '5000')
    try:
        port = int(port_raw)
    except ValueError:
        port = 5000

    # Default to production mode when frozen (exe); debug mode in dev.
    _default_debug = '0' if getattr(sys, 'frozen', False) else '1'
    debug_mode = os.environ.get('CLINIC_DEBUG', _default_debug) == '1'

    print("\n" + "="*60)
    print("🦷 DENTAL CLINIC MANAGEMENT SYSTEM")
    print("="*60)

    print('\n📊 Initializing database...')
    init_database()

    # Warn if the default admin password is still in use.
    try:
        _c = sqlite3.connect(DB_NAME)
        _c.row_factory = sqlite3.Row
        _u = _c.execute("SELECT password_hash FROM users WHERE username = 'admin'").fetchone()
        _c.close()
        if _u and check_password_hash(_u['password_hash'], 'admin'):
            print("\n⚠️  SECURITY: the portal login is still  admin / admin")
            print("    Change it in the app: Settings → Account → Change Password.")
    except Exception:
        pass

    # Skip browser auto-open for the headless service. The pywebview window
    # launcher (DentaCare.exe) is the customer-facing UI in packaged mode;
    # opening a browser tab too would be redundant. CLINIC_HEADLESS=1 is set
    # by NSSM in the service registration; CLOUD_MODE always implies headless.
    headless = (
        os.environ.get('CLINIC_HEADLESS', '0').strip().lower() in ('1', 'true', 'yes', 'on')
        or CLOUD_MODE
    )
    if not headless:
        threading.Thread(target=open_browser, kwargs={'port': port}, daemon=True).start()

    # Automatic database backups (production runs only — in debug the reloader
    # would spawn the worker twice, and source checkouts have git anyway).
    backups_on = (not debug_mode) and BACKUP_INTERVAL_HOURS > 0
    if backups_on:
        threading.Thread(target=_backup_loop, daemon=True).start()

    # Background mirror to/from the cloud node (a clinic's local server only).
    _cloud_url, _cloud_token, _cloud_interval = _cloud_sync_config()
    cloud_sync_on = (not CLOUD_MODE) and (not debug_mode)
    if cloud_sync_on:
        threading.Thread(target=cloud_sync_worker, daemon=True).start()

    # Background Bluetooth-SPP listener. Local clinic server only. Runs in
    # *both* production and debug — but in debug, only inside the Werkzeug
    # reloader's child process (WERKZEUG_RUN_MAIN=true), so the parent
    # watchdog doesn't try to open the same COM port and lose to the child.
    bt_sync_on = (not CLOUD_MODE) and (
        not debug_mode or os.environ.get('WERKZEUG_RUN_MAIN') == 'true'
    )
    if bt_sync_on:
        threading.Thread(target=bt_sync_server, daemon=True).start()

    print("\n✅ System ready!")
    print(f'🌐 Opening browser at http://127.0.0.1:{port}')
    print('🔐 Portal login required (default: admin / admin)')
    if backups_on:
        print(f'🗄️  Automatic backups every {BACKUP_INTERVAL_HOURS:g}h → {BACKUP_DIR}')
    if cloud_sync_on:
        if _cloud_url and _cloud_token:
            print(f'☁️  Cloud sync every {_cloud_interval:g} min → {_cloud_url}')
        else:
            print('☁️  Cloud sync ready (not yet paired — POST /api/cloud/pair or set CLINIC_CLOUD_URL + CLINIC_CLOUD_TOKEN)')
    if bt_sync_on:
        print('📡 Bluetooth sync ready (configure in Settings → Bluetooth Sync)')
    if host != '127.0.0.1':
        print(f'📶 LAN mode enabled on {host}:{port}')
    print("\n📝 Press CTRL+C to stop the server\n")
    print("="*60 + "\n")

    if debug_mode:
        # Dev: Flask's reloader/debugger so code & template changes are picked up.
        # Set CLINIC_DEBUG=0 to run in production mode (default when frozen as .exe).
        app.run(host=host, port=port, debug=True)
    else:
        # Production: serve with waitress (a proper multi-threaded WSGI server)
        # instead of the Werkzeug dev server. Fall back to app.run() if waitress
        # is unavailable so the app still starts.
        try:
            from waitress import serve
            print(f'🚀 Serving with waitress on {host}:{port}')
            serve(app, host=host, port=port, threads=8)
        except ImportError:
            print('⚠️  waitress not available — falling back to the built-in server.')
            print('    Install it for production use:  pip install waitress')
            app.run(host=host, port=port, debug=False)


