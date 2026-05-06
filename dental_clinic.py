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
import hashlib
import hmac
import threading
import webbrowser
import json
import secrets
import uuid
from datetime import datetime, timedelta
from pathlib import Path


# Auto-install dependencies
def check_and_install_dependencies():
    """Check and install required packages"""
    required_packages = {
        'flask': 'Flask',
        'flask_cors': 'Flask-CORS'
    }

    print("Checking dependencies...")

    for module_name, package_name in required_packages.items():
        try:
            __import__(module_name)
            print(f"  {package_name} is already installed")
        except ImportError:
            print(f"  Installing {package_name}...")
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', package_name])


# Check and install dependencies before importing
check_and_install_dependencies()

# Now import the packages
from flask import Flask, render_template_string, request, jsonify, send_file
from flask_cors import CORS
from werkzeug.utils import secure_filename


app = Flask(__name__)
CORS(app)

DB_NAME = 'dental_clinic.db'
UPLOAD_FOLDER = Path('uploads')
UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
PAIRING_CODE_TTL_MINUTES = 5
DEFAULT_LICENSE_DAYS = 30
DEFAULT_LICENSE_GRACE_DAYS = 7

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


def utc_now_iso():
    return datetime.utcnow().replace(microsecond=0).isoformat() + 'Z'


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

    ensure_table_column(cursor, 'expenses', 'payment_status', 'TEXT')
    ensure_table_column(cursor, 'expenses', 'patient_id', 'INTEGER')
    ensure_table_column(cursor, 'expenses', 'treatment_id', 'INTEGER')
    ensure_table_column(cursor, 'expenses', 'source_type', 'TEXT')
    ensure_table_column(cursor, 'expenses', 'reference_id', 'INTEGER')
    ensure_table_column(cursor, 'patient_followups', 'procedure_id', 'INTEGER')
    ensure_table_column(cursor, 'patient_followups', 'lab_expense', 'REAL')
    ensure_table_column(cursor, 'patient_followups', 'clinic_profit', 'REAL')
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
        CREATE TABLE IF NOT EXISTS treatment_catalog (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name_ar TEXT NOT NULL,
            name_en TEXT DEFAULT '',
            default_price REAL DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')

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

    # Seed treatment_catalog only if empty
    cursor.execute('SELECT COUNT(*) FROM treatment_catalog')
    if cursor.fetchone()[0] == 0:
        default_catalog = [
            ('كشف', 'Consultation', 50),
            ('تنظيف', 'Cleaning', 100),
            ('حشوة', 'Filling', 150),
            ('خلع', 'Extraction', 100),
            ('سحب عصب', 'Root Canal', 400),
            ('تركيبة', 'Crown/Prosthesis', 500),
            ('مراجعة', 'Follow-up', 0),
        ]
        cursor.executemany('INSERT INTO treatment_catalog (name_ar, name_en, default_price) VALUES (?, ?, ?)', default_catalog)

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
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_treatment_catalog_active ON treatment_catalog(is_active)')
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
        INSERT OR IGNORE INTO treatment_procedures (id, name, requires_lab, active)
        VALUES (0, 'مراجعة', 0, 1)
    ''')

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
    if not value:
        raise ValueError('Appointment date is required')

    normalized = str(value).strip().replace('T', ' ')
    try:
        parsed = datetime.fromisoformat(normalized)
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
    return {
        'id': row[0],
        'patient_id': row[1],
        'appointment_date': row[2],
        'duration': row[3],
        'treatment_type': row[4],
        'status': row[5],
        'notes': row[6],
        'created_at': row[7],
        'patient_name': row[8],
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
    """Return credit balance (positive means clinic owes patient)."""
    cursor.execute('SELECT COALESCE(SUM(amount), 0) FROM patient_credit_transactions WHERE patient_id = ?', (patient_id,))
    return float(cursor.fetchone()[0] or 0)


def get_authenticated_device(cursor):
    token = request.headers.get('X-Device-Token') or request.args.get('device_token')
    if not token:
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


def parse_timestamp_for_sync(value):
    if not value:
        return datetime.min
    text = str(value).strip().replace('Z', '')
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return datetime.min


def evaluate_license_window(status, expires_at, grace_until):
    today = datetime.utcnow().date()
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


# HTML Template
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dental Clinic Management System</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;600;700;800&family=Space+Grotesk:wght@600;700&display=swap');

        :root {
            --bg-1: #f1f7f8;
            --bg-2: #e7f0ff;
            --panel: #ffffff;
            --line: #dbe4ef;
            --text: #11243a;
            --muted: #627386;
            --brand: #0f6d7b;
            --brand-2: #1d7fb7;
            --accent: #13b5a7;
            --danger: #d9434e;
            --warning: #d89e1f;
            --ok: #1f9a5f;
            --shadow: 0 14px 36px rgba(19, 39, 66, 0.12);
        }

        * { margin: 0; padding: 0; box-sizing: border-box; }

        body {
            font-family: 'Manrope', 'Inter', 'Segoe UI', Tahoma, sans-serif;
            color: var(--text);
            background:
                radial-gradient(1200px 500px at 100% -30%, #cfe7ff 0%, transparent 60%),
                radial-gradient(1000px 500px at -10% 0%, #cff3ec 0%, transparent 58%),
                linear-gradient(160deg, var(--bg-1), var(--bg-2));
            min-height: 100vh;
            padding: 22px;
        }

        body[data-theme="dark"] {
            --bg-1: #0b1220;
            --bg-2: #111a2d;
            --panel: #0f1728;
            --line: #263449;
            --text: #e7eef8;
            --muted: #9bb0c8;
            --shadow: 0 18px 40px rgba(0, 0, 0, 0.35);
            background:
                radial-gradient(1200px 500px at 100% -30%, rgba(29, 127, 183, 0.18) 0%, transparent 60%),
                radial-gradient(1000px 500px at -10% 0%, rgba(19, 181, 167, 0.12) 0%, transparent 58%),
                linear-gradient(160deg, var(--bg-1), var(--bg-2));
        }

        .container {
            max-width: 1460px;
            margin: 0 auto;
            display: flex;
            flex-direction: column;
            background: rgba(255, 255, 255, 0.88);
            border: 1px solid rgba(255, 255, 255, 0.85);
            backdrop-filter: blur(8px);
            border-radius: 24px;
            box-shadow: var(--shadow);
            overflow: hidden;
        }

        body[data-theme="dark"] .container {
            background: rgba(12, 19, 33, 0.92);
            border-color: rgba(255, 255, 255, 0.06);
        }

        .header {
            padding: 34px 32px 26px;
            color: #fff;
            background: linear-gradient(140deg, var(--brand) 0%, var(--brand-2) 52%, #3565b8 100%);
            position: relative;
            overflow: hidden;
        }

        .header::after {
            content: '';
            position: absolute;
            width: 260px;
            height: 260px;
            right: -80px;
            top: -100px;
            border-radius: 50%;
            background: rgba(255, 255, 255, 0.15);
        }

        .header h1 {
            font-family: 'Space Grotesk', 'Manrope', sans-serif;
            font-size: clamp(1.6rem, 4vw, 2.6rem);
            letter-spacing: -0.02em;
            margin-bottom: 8px;
            position: relative;
            z-index: 1;
        }

        .header p { opacity: 0.9; position: relative; z-index: 1; }

        body[data-theme="dark"] .header {
            background: linear-gradient(140deg, #0e2b4d 0%, #124c71 52%, #1d5f87 100%);
        }

        .header-top {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 12px;
            width: 100%;
            position: relative;
            z-index: 1;
        }

        .header-meta {
            display: flex;
            align-items: center;
            gap: 10px;
            flex-wrap: wrap;
            justify-content: flex-end;
        }

        .doctor-badge {
            padding: 8px 12px;
            border-radius: 12px;
            font-weight: 700;
            color: #0d3f67;
            border: 1px solid rgba(255, 255, 255, 0.45);
            background: rgba(255, 255, 255, 0.86);
            backdrop-filter: blur(4px);
            white-space: nowrap;
        }

        body[data-theme="dark"] .doctor-badge {
            color: #eaf2ff;
            border-color: rgba(255, 255, 255, 0.14);
            background: rgba(15, 23, 40, 0.84);
        }

        .theme-toggle {
            margin: 0;
            width: 38px;
            height: 38px;
            min-width: 38px;
            min-height: 38px;
            padding: 0;
            border-radius: 999px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            font-size: 1.05rem;
            line-height: 1;
        }

        .language-toggle {
            margin: 0;
            padding: 0 12px;
            min-height: 38px;
            border-radius: 999px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            font-size: 0.9rem;
            font-weight: 700;
            white-space: nowrap;
        }

        .sub-tabs {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(118px, max-content));
            justify-content: flex-start;
            gap: 10px;
            margin-bottom: 16px;
        }

        .sub-tab {
            border: 1px solid #c9d8e8;
            border-radius: 10px;
            background: #f7fbff;
            color: #2d4c67;
            padding: 9px 13px;
            font-weight: 700;
            cursor: pointer;
            box-shadow: 0 2px 6px rgba(15, 40, 66, 0.04);
            transition: 0.2s ease;
        }

        .sub-tab:hover {
            background: #edf6ff;
        }

        .sub-tab.active {
            background: linear-gradient(135deg, #e2f7f4 0%, #e5efff 100%);
            border-color: #aec9e2;
            color: #113f64;
            box-shadow: 0 7px 18px rgba(35, 108, 161, 0.12);
        }

        .sub-tab-content {
            display: none;
            margin-bottom: 14px;
        }

        .sub-tab-content.active {
            display: block;
            border: 1px solid rgba(163, 192, 219, 0.38);
            border-radius: 12px;
            background: rgba(248, 252, 255, 0.72);
            padding: 14px 14px 10px;
        }

        .collapsible-box {
            border: 1px solid var(--line);
            border-radius: 12px;
            background: #fff;
            padding: 10px 12px;
        }

        .collapsible-box > summary {
            cursor: pointer;
            font-weight: 800;
            color: #214a68;
            list-style: none;
        }

        .collapsible-box > summary::-webkit-details-marker {
            display: none;
        }

        .collapsible-box > summary::before {
            content: '▸';
            margin-right: 6px;
        }

        .collapsible-box[open] > summary::before {
            content: '▾';
        }

        body[data-theme="dark"] .sub-tab {
            background: #111c30;
            border-color: #31425c;
            color: #bdd0e6;
        }

        body[data-theme="dark"] .sub-tab.active {
            background: linear-gradient(135deg, rgba(19, 181, 167, 0.18) 0%, rgba(29, 127, 183, 0.2) 100%);
            border-color: rgba(96, 135, 179, 0.5);
            color: #f3f8ff;
        }

        body[data-theme="dark"] .sub-tab-content.active {
            background: rgba(13, 25, 43, 0.62);
            border-color: rgba(87, 117, 151, 0.45);
        }

        body[data-theme="dark"] .collapsible-box {
            background: #10192a;
            border-color: #253347;
        }

        body[data-theme="dark"] .collapsible-box > summary {
            color: #dce8f6;
        }

        .app-body {
            display: flex;
            flex-direction: row;
            flex: 1;
            min-height: 0;
        }

        .nav-tabs {
            display: flex;
            flex-direction: column;
            gap: 4px;
            padding: 16px 10px;
            background: #f3f7fb;
            border-right: 1px solid var(--line);
            overflow-y: auto;
            width: 196px;
            min-width: 196px;
            flex-shrink: 0;
        }

        .nav-tabs-label {
            font-size: 0.7rem;
            font-weight: 800;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            color: var(--muted);
            padding: 4px 6px 10px;
        }

        body[data-theme="dark"] .nav-tabs {
            background: #10192a;
            border-right-color: #1e2e42;
        }

        .nav-tab {
            flex: none;
            width: 100%;
            text-align: left;
            border: 1px solid transparent;
            background: transparent;
            border-radius: 10px;
            color: #35516d;
            padding: 11px 13px;
            font-weight: 700;
            font-size: 0.92rem;
            cursor: pointer;
            transition: 0.2s ease;
            display: flex;
            align-items: center;
            gap: 9px;
        }

        .nav-tab:hover { background: #e8f1fa; }

        body[data-theme="dark"] .nav-tab {
            color: #bfd0e4;
        }

        body[data-theme="dark"] .nav-tab:hover {
            background: rgba(255, 255, 255, 0.05);
        }

        .nav-tab.active {
            background: linear-gradient(135deg, #e6f7f5 0%, #dfefff 100%);
            border-color: #bed4e8;
            color: #113f64;
            box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.8);
        }

        body[data-theme="dark"] .nav-tab.active {
            background: linear-gradient(135deg, rgba(19, 181, 167, 0.18) 0%, rgba(29, 127, 183, 0.2) 100%);
            border-color: rgba(96, 135, 179, 0.5);
            color: #f3f8ff;
        }

        /* Collapsible sidebar quick-win: compact width and icon-only mode */
        body.sidebar-collapsed .nav-tabs {
            width: 72px;
            min-width: 72px;
            padding: 10px 6px;
        }
        body.sidebar-collapsed .nav-tab {
            justify-content: center;
            padding: 8px 6px;
            gap: 0;
        }
        body.sidebar-collapsed .nav-tab span:not(.tab-icon) { display: none; }
        body.sidebar-collapsed .nav-tabs-label { display: none; }

        @media (max-width: 980px) {
            .nav-tabs { width: 72px; min-width: 72px; }
            .nav-tabs-label { display: none; }
            .content { padding: 18px; }
        }

        .content { flex: 1; min-width: 0; padding: 28px; }
        .tab-content { display: none; }
        .tab-content.active { display: block; animation: fadeIn 0.25s ease; }

        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(8px); }
            to { opacity: 1; transform: translateY(0); }
        }

        h2 {
            font-family: 'Space Grotesk', 'Manrope', sans-serif;
            margin-bottom: 14px;
            letter-spacing: -0.02em;
        }

        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 14px;
            margin-bottom: 22px;
        }

        .stat-card {
            padding: 18px;
            border-radius: 16px;
            color: #fff;
            background: linear-gradient(135deg, #1a8ca2 0%, #2672c5 100%);
            box-shadow: 0 12px 24px rgba(23, 76, 129, 0.2);
        }

        body[data-theme="dark"] .stat-card {
            background: linear-gradient(135deg, #164457 0%, #224f8a 100%);
            box-shadow: 0 12px 24px rgba(0, 0, 0, 0.24);
        }

        .stat-card h3 {
            font-size: clamp(1.5rem, 3vw, 2.3rem);
            margin-bottom: 6px;
            line-height: 1.1;
        }

        .stat-card p { opacity: 0.92; font-size: 0.9rem; }

        .form-group { margin-bottom: 16px; }
        .form-group label {
            display: block;
            margin-bottom: 7px;
            color: #2c425c;
            font-weight: 700;
            font-size: 0.92rem;
        }

        .form-group input,
        .form-group select,
        .form-group textarea {
            width: 100%;
            border: 1px solid #cdd9e6;
            border-radius: 12px;
            padding: 11px 12px;
            background: #fff;
            color: var(--text);
            transition: 0.2s ease;
        }

        body[data-theme="dark"] .form-group input,
        body[data-theme="dark"] .form-group select,
        body[data-theme="dark"] .form-group textarea {
            background: #0e1727;
            border-color: #2a3951;
            color: var(--text);
        }

        /* Design tokens (quick-win) */
        :root {
            --space-1: 6px;
            --space-2: 10px;
            --space-3: 14px;
            --space-4: 18px;
            --space-5: 24px;
            --space-6: 32px;
            --gap: var(--space-3);
            --input-padding: 12px 14px;
        }

        .form-group textarea { resize: vertical; min-height: 96px; }

        .form-group input:focus,
        .form-group select:focus,
        .form-group textarea:focus {
            outline: none;
            border-color: #7bb6e2;
            box-shadow: 0 0 0 4px rgba(61, 149, 211, 0.14);
        }

        .form-row { display: grid; grid-template-columns: 1fr 1fr; gap: var(--gap); }

        .btn {
            border: none;
            border-radius: 12px;
            padding: 10px 16px;
            cursor: pointer;
            font-weight: 800;
            font-size: 0.9rem;
            transition: 0.18s ease;
            letter-spacing: 0.01em;
        }

        .btn:hover { transform: translateY(-1px); }
        .btn-primary { background: linear-gradient(135deg, var(--brand) 0%, var(--brand-2) 100%); color: #fff; }
        .btn-success { background: linear-gradient(135deg, #2c9e62 0%, #22b7a1 100%); color: #fff; }
        .btn-danger { background: linear-gradient(135deg, #da4c58 0%, #be3955 100%); color: #fff; }
        .btn-warning { background: linear-gradient(135deg, #f2ca53 0%, #e8a733 100%); color: #342300; }

        /* Small / icon buttons */
        .btn-sm { padding: 6px 10px; font-size: 0.85rem; border-radius: 10px; }
        .btn-icon { padding: 6px 8px; font-size: 0.88rem; border-radius: 10px; }

        .table-container {
            margin-top: 16px;
            overflow-x: auto;
            border: 1px solid var(--line);
            border-radius: 16px;
            background: #fff;
        }

        body[data-theme="dark"] .table-container {
            background: #0f1728;
            border-color: #253347;
        }

        table { width: 100%; border-collapse: collapse; }
        table th {
            padding: 14px 16px;
            text-align: left;
            font-size: 0.95rem;
            letter-spacing: 0.02em;
            color: #49617b;
            background: #f5f9fd;
            border-bottom: 1px solid var(--line);
        }

        body[data-theme="dark"] table th {
            background: #121d31;
            color: #b9cbe0;
            border-bottom-color: #27364a;
        }

        table td {
            padding: 14px 16px;
            border-bottom: 1px solid #edf2f7;
            vertical-align: top;
            font-size: 0.95rem;
        }

        body[data-theme="dark"] table td {
            border-bottom-color: #223043;
        }

        body[data-theme="dark"] table tr:hover {
            background: rgba(255, 255, 255, 0.03);
        }

        table tr:hover { background: #f7fbff; }

        .badge {
            display: inline-flex;
            align-items: center;
            border-radius: 999px;
            padding: 4px 10px;
            font-size: 0.76rem;
            font-weight: 800;
            text-transform: uppercase;
            letter-spacing: 0.04em;
        }

        .badge-success { background: #e0f4e8; color: #166942; }
        .badge-warning { background: #fff1d4; color: #8b5e00; }
        .badge-danger { background: #ffe2e5; color: #8d1f33; }
        .badge-info { background: #e3f1ff; color: #1f5d9e; }

        .expense-status-select { padding: 4px 6px; font-size: 0.85rem; border-radius: 6px; border: 1px solid #cdd9e6; }
        .expense-status-select[data-status="paid"] { background: #e0f4e8; color: #166942; }
        .expense-status-select[data-status="postponed"] { background: #fff1d4; color: #8b5e00; }
        body[data-theme="dark"] .expense-status-select[data-status="paid"] { background: #1a3a22; color: #6ee699; border-color: #2a5a32; }
        body[data-theme="dark"] .expense-status-select[data-status="postponed"] { background: #2a2210; color: #d4a843; border-color: #4a3a10; }

        .action-buttons { display: flex; gap: 8px; flex-wrap: wrap; }
        .action-buttons button { padding: 7px 12px; font-size: 0.8rem; }

        .toolbar-row {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
            margin-top: 12px;
            align-items: center;
        }

        .toolbar-row .btn { padding: 10px 14px; }

        .search-status { margin-top: 8px; color: var(--muted); font-size: 0.9rem; }

        .calendar-controls {
            margin-top: 12px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 12px;
            flex-wrap: wrap;
            padding: 12px;
            border: 1px solid var(--line);
            border-radius: 14px;
            background: linear-gradient(135deg, #f8fcff 0%, #f2fbf8 100%);
        }

        .calendar-month-title {
            font-family: 'Space Grotesk', 'Manrope', sans-serif;
            font-size: 1.12rem;
            font-weight: 700;
            color: #214766;
        }

        .appointments-calendar { margin-top: 14px; display: grid; grid-template-columns: repeat(7, 1fr); gap: 8px; }
        .calendar-day-header {
            font-weight: 700;
            padding: 8px;
            background: #f2f7fc;
            border: 1px solid var(--line);
            border-radius: 10px;
            text-align: center;
            color: #345670;
            font-size: 0.85rem;
        }

        .calendar-day-cell {
            min-height: 116px;
            border: 1px solid var(--line);
            border-radius: 12px;
            padding: 8px;
            background: #fff;
            transition: all 0.2s ease;
        }

        .calendar-day-cell.cursor-pointer {
            cursor: pointer;
        }

        .calendar-day-cell.cursor-pointer:hover {
            background: #f0f8ff;
            border-color: #7bb6e2;
            box-shadow: 0 2px 8px rgba(61, 149, 211, 0.15);
            transform: translateY(-1px);
        }

        .calendar-day-cell.cursor-not-allowed {
            cursor: not-allowed;
            opacity: 0.7;
        }

        .calendar-day-number { font-weight: 800; color: #27415b; }
        .calendar-empty { font-size: 11px; color: #8ba0b5; margin-top: 6px; }
        /* Date picker modal */
        .date-picker-modal { display: none; position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.4); z-index: 10000; align-items: center; justify-content: center; }
        .date-picker-modal.active { display: flex; }
        .date-picker-modal-content { background: #fff; border-radius: 16px; padding: 20px; box-shadow: 0 8px 32px rgba(0,0,0,0.15); max-width: 320px; width: 90%; }
        body[data-theme="dark"] .date-picker-modal-content { background: #0e1727; color: #f1f5f9; }
        .date-picker-modal-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
        .date-picker-modal-header button { background: none; border: none; font-size: 24px; cursor: pointer; color: #627386; }
        .date-picker-modal-month { font-weight: 700; font-size: 1.1rem; text-align: center; }
        .date-picker-grid { display: grid; grid-template-columns: repeat(7, 1fr); gap: 8px; margin-top: 14px; }
        .date-picker-day { text-align: center; padding: 6px; border-radius: 8px; cursor: pointer; font-size: 0.9rem; border: 1px solid transparent; }
        .date-picker-day:hover { background: #e8f1fa; }
        .date-picker-day-name { font-weight: 700; font-size: 0.75rem; color: #627386; padding: 8px 0; }
        body[data-theme="dark"] .date-picker-day:hover { background: rgba(255,255,255,0.08); }
        .date-picker-day.empty { cursor: default; }
        .date-picker-day.today { background: #e6f7f5; border-color: #13b5a7; color: #0f6d7b; font-weight: 700; }


        .calendar-event {
            font-size: 11px;
            padding: 5px 7px;
            margin-top: 5px;
            background: linear-gradient(135deg, #e5f2ff 0%, #def5ef 100%);
            border: 1px solid #cee1f5;
            border-radius: 8px;
            line-height: 1.35;
        }

        .alert { padding: 12px; border-radius: 10px; margin-bottom: 14px; }
        .alert-success { background: #e2f6ea; color: #0f643f; border: 1px solid #bee7ce; }
        .alert-error { background: #ffe6e8; color: #892336; border: 1px solid #fac8ce; }

        body[data-theme="dark"] .alert-success {
            background: rgba(31, 154, 95, 0.14);
            color: #7be0b0;
            border-color: rgba(31, 154, 95, 0.28);
        }

        body[data-theme="dark"] .alert-error {
            background: rgba(217, 67, 78, 0.14);
            color: #ff9da8;
            border-color: rgba(217, 67, 78, 0.28);
        }

        .modal {
            display: none;
            position: fixed;
            inset: 0;
            background: rgba(10, 23, 38, 0.58);
            z-index: 1000;
            justify-content: center;
            align-items: center;
            padding: 16px;
        }

        .modal.active { display: flex; }

        .modal-content {
            background: #fff;
            padding: 22px;
            border-radius: 16px;
            max-width: 640px;
            width: 100%;
            max-height: 90vh;
            overflow-y: auto;
            border: 1px solid var(--line);
            box-shadow: var(--shadow);
        }

        body[data-theme="dark"] .modal-content {
            background: #111a2b;
            border-color: #253347;
        }

        .modal-header { margin-bottom: 16px; }
        .modal-header h2 {
            font-family: 'Space Grotesk', 'Manrope', sans-serif;
            color: #19344f;
            letter-spacing: -0.01em;
        }

        body[data-theme="dark"] .modal-header h2,
        body[data-theme="dark"] .billing-equation-box h4 {
            color: #e6effb;
        }

        .close-modal {
            float: right;
            font-size: 1.3rem;
            line-height: 1;
            cursor: pointer;
            color: #59758f;
        }

        body[data-theme="dark"] .close-modal {
            color: #b0c3da;
        }

        .billing-equation-box {
            border: 1px solid #cfe1f0;
            border-radius: 12px;
            background: linear-gradient(135deg, #f5fbff 0%, #f3fff8 100%);
            padding: 12px;
            margin-bottom: 16px;
        }

        body[data-theme="dark"] .billing-equation-box {
            background: linear-gradient(135deg, rgba(17, 28, 46, 0.98) 0%, rgba(16, 42, 52, 0.98) 100%);
            border-color: #27364a;
        }

        .billing-equation-box h4 {
            margin-bottom: 8px;
            color: #214a68;
            font-size: 0.92rem;
        }

        .billing-equation-box p {
            font-size: 0.87rem;
            color: #4d6379;
            margin-bottom: 3px;
        }

        body[data-theme="dark"] .billing-equation-box p,
        body[data-theme="dark"] .search-status {
            color: #a9bed7;
        }

        body[data-theme="dark"] .calendar-controls {
            background: linear-gradient(135deg, #10192a 0%, #0f1f20 100%);
            border-color: #253347;
        }

        body[data-theme="dark"] .calendar-month-title,
        body[data-theme="dark"] .calendar-day-number {
            color: #eaf2ff;
        }

        body[data-theme="dark"] .calendar-day-header,
        body[data-theme="dark"] .calendar-day-cell {
            background: #10192a;
            border-color: #253347;
            color: #dce7f4;
        }

        body[data-theme="dark"] .calendar-day-cell.cursor-pointer:hover {
            background: #132238;
        }

        body[data-theme="dark"] .calendar-event {
            background: linear-gradient(135deg, rgba(29, 127, 183, 0.2) 0%, rgba(19, 181, 167, 0.16) 100%);
            border-color: rgba(124, 156, 196, 0.24);
            color: #eff6ff;
        }

        @media (max-width: 1024px) {
            .nav-tabs { width: 168px; min-width: 168px; padding: 12px 8px; }
            .content { padding: 20px; }
            .appointments-calendar { grid-template-columns: repeat(4, 1fr); }
        }

        @media (max-width: 760px) {
            .app-body { flex-direction: column; }
            .nav-tabs {
                flex-direction: row;
                width: auto; min-width: 0;
                border-right: none; border-bottom: 1px solid var(--line);
                padding: 8px 10px;
                overflow-x: auto; overflow-y: hidden;
                gap: 6px;
            }
            html[dir="rtl"] .nav-tabs { flex-direction: row-reverse; border-left: none; order: 0; }
            .nav-tab { flex: 0 0 auto; width: auto; padding: 9px 12px; }
            .nav-tabs-label { display: none; }
            body { padding: 10px; }
            .header { padding: 20px; }
            .content { padding: 14px; }
            .form-row { grid-template-columns: 1fr; gap: 10px; }
            .stats-grid { grid-template-columns: 1fr 1fr; }
            .appointments-calendar { grid-template-columns: repeat(2, 1fr); }
            .action-buttons { flex-direction: column; }
            .action-buttons .btn { width: 100%; }
            .theme-toggle { width: 34px; height: 34px; min-width: 34px; min-height: 34px; }
            .language-toggle { min-height: 34px; font-size: 0.84rem; padding: 0 9px; }
            .sub-tabs { grid-template-columns: 1fr 1fr; gap: 8px; }
            .sub-tab { text-align: center; }
            .sub-tab-content.active { padding: 12px 10px 8px; }
        }

        /* RTL Support */
        html[dir="rtl"] body {
            direction: rtl;
            text-align: right;
            font-family: 'Cairo', 'Tajawal', 'Noto Sans Arabic', 'Segoe UI', Tahoma, sans-serif;
        }
        html[dir="rtl"] .header { text-align: right; }
        html[dir="rtl"] .header-top { flex-direction: row-reverse; }
        html[dir="rtl"] .header-meta { justify-content: flex-start; }
        html[dir="rtl"] .nav-tabs { border-right: none; border-left: 1px solid var(--line); order: 1; }
        html[dir="rtl"] .nav-tab { text-align: right; }
        html[dir="rtl"] .form-row { direction: rtl; }
        html[dir="rtl"] .toolbar-row { flex-direction: row-reverse; }
        html[dir="rtl"] .action-buttons { flex-direction: row-reverse; }
        html[dir="rtl"] table { text-align: right; }
        html[dir="rtl"] table th,
        html[dir="rtl"] table td { text-align: right; }
        html[dir="rtl"] .form-group label { text-align: right; display: block; }
        html[dir="rtl"] .modal-content { direction: rtl; text-align: right; }
        html[dir="rtl"] .close-modal { float: left; }

        /* ── UI Polish ── */
        .page-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
            flex-wrap: wrap;
            margin-bottom: 20px;
            padding-bottom: 16px;
            border-bottom: 2px solid var(--line);
        }
        .page-header h2 { margin-bottom: 0; }
        .page-header .header-actions { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
        .section-divider {
            display: flex;
            align-items: center;
            gap: 10px;
            margin: 24px 0 14px;
        }
        .section-divider span {
            font-family: 'Space Grotesk', 'Manrope', sans-serif;
            font-weight: 700;
            font-size: 0.9rem;
            color: var(--text);
            white-space: nowrap;
        }
        .section-divider::after { content: ''; flex: 1; height: 1px; background: var(--line); }
        .stat-card { position: relative; overflow: hidden; }
        .stat-card .stat-icon {
            position: absolute;
            right: 14px;
            top: 50%;
            transform: translateY(-50%);
            font-size: 2.4rem;
            opacity: 0.18;
            pointer-events: none;
        }
        html[dir="rtl"] .stat-card .stat-icon { right: auto; left: 14px; }
        .stat-card h3, .stat-card p { position: relative; z-index: 1; }
        .stat-card-teal { background: linear-gradient(135deg, #0f6d7b 0%, #13b5a7 100%) !important; }
        .stat-card-blue { background: linear-gradient(135deg, #1d7fb7 0%, #3565b8 100%) !important; }
        .stat-card-green { background: linear-gradient(135deg, #1f9a5f 0%, #22b7a1 100%) !important; }
        .stat-card-amber { background: linear-gradient(135deg, #c47f10 0%, #d89e1f 100%) !important; color: #fff !important; }
        body[data-theme="dark"] .stat-card-teal { background: linear-gradient(135deg, #0a4a53 0%, #0d7870 100%) !important; }
        body[data-theme="dark"] .stat-card-blue { background: linear-gradient(135deg, #133a60 0%, #1d4a82 100%) !important; }
        body[data-theme="dark"] .stat-card-green { background: linear-gradient(135deg, #0c4d30 0%, #0f6050 100%) !important; }
        body[data-theme="dark"] .stat-card-amber { background: linear-gradient(135deg, #5a3a00 0%, #704800 100%) !important; }
        .nav-tab .tab-icon { font-size: 1.05rem; flex-shrink: 0; }
        table td { padding: 13px 12px; }
        .holiday-panel { margin-top: 22px; border-radius: 12px; border: 1px solid var(--line); overflow: hidden; }
        .holiday-panel > summary {
            cursor: pointer;
            padding: 13px 16px;
            background: var(--bg-1);
            font-weight: 700;
            color: var(--text);
            list-style: none;
            user-select: none;
            display: flex;
            align-items: center;
            gap: 8px;
            transition: background 0.15s ease;
        }
        .holiday-panel > summary:hover { background: var(--bg-2); }
        .holiday-panel > summary::-webkit-details-marker { display: none; }
        .holiday-panel > summary::before { content: '▸'; color: var(--muted); font-size: 0.78rem; }
        .holiday-panel[open] > summary::before { content: '▾'; }
        body[data-theme="dark"] .holiday-panel > summary { background: #111c30; }
        body[data-theme="dark"] .holiday-panel[open] > summary { background: #0f1728; }
        .holiday-panel-body { padding: 16px; border-top: 1px solid var(--line); background: var(--panel); }
        .dashboard-toolbar { display: flex; justify-content: flex-end; margin-bottom: 20px; }

        /* ── Profile Tabs ── */
        .profile-tabs {
            display: flex;
            gap: 6px;
            padding: 12px 0 0;
            border-bottom: 2px solid var(--line);
            margin-bottom: 18px;
            flex-wrap: wrap;
        }
        .profile-tab {
            border: none;
            background: transparent;
            padding: 9px 18px;
            font-weight: 700;
            font-size: 0.9rem;
            color: var(--muted);
            cursor: pointer;
            border-bottom: 3px solid transparent;
            margin-bottom: -2px;
            border-radius: 0;
            transition: 0.18s ease;
        }
        .profile-tab:hover { color: var(--brand); }
        .profile-tab.active { color: var(--brand); border-bottom-color: var(--brand); }
        body[data-theme="dark"] .profile-tab.active { color: var(--accent); border-bottom-color: var(--accent); }
        .profile-tab-content { display: none; }
        .profile-tab-content.active { display: block; animation: fadeIn 0.2s ease; }

        /* ── Profile stat compact ── */
        .profile-stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
            gap: 12px;
            margin-bottom: 16px;
        }

        /* ── Collapsible form panel ── */
        .form-panel {
            border: 1px solid var(--line);
            border-radius: 14px;
            margin-bottom: 16px;
            overflow: hidden;
        }
        .form-panel > summary {
            cursor: pointer;
            list-style: none;
            padding: 13px 16px;
            background: var(--bg-1);
            font-weight: 800;
            color: var(--text);
            display: flex;
            align-items: center;
            gap: 8px;
            user-select: none;
            transition: background 0.15s;
        }
        .form-panel > summary:hover { background: var(--bg-2); }
        .form-panel > summary::-webkit-details-marker { display: none; }
        .form-panel > summary::before { content: '▸'; color: var(--muted); font-size: 0.8rem; transition: transform 0.2s; }
        .form-panel[open] > summary::before { content: '▾'; }
        .form-panel-body { padding: 16px; border-top: 1px solid var(--line); background: var(--panel); }
        body[data-theme="dark"] .form-panel > summary { background: #111c30; }
        body[data-theme="dark"] .form-panel-body { background: #0f1728; }

        /* ── 3-col form row ── */
        .form-row-3 {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
            gap: var(--gap);
        }
        @media (max-width: 980px) { .form-row-3 { grid-template-columns: 1fr 1fr; } }
        @media (max-width: 560px) { .form-row-3 { grid-template-columns: 1fr; } }

        /* ── Section card ── */
        .section-card {
            border: 1px solid var(--line);
            border-radius: 14px;
            padding: 18px;
            background: var(--panel);
            margin-bottom: 18px;
        }
        .section-card-title {
            font-family: 'Space Grotesk', 'Manrope', sans-serif;
            font-size: 0.9rem;
            font-weight: 800;
            letter-spacing: 0.04em;
            text-transform: uppercase;
            color: var(--muted);
            margin-bottom: 14px;
        }
        body[data-theme="dark"] .section-card { background: #0f1728; border-color: #253347; }

        /* ── Readonly info grid ── */
        .info-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
            gap: 10px 16px;
        }
        .info-field label {
            font-size: 0.76rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            color: var(--muted);
            display: block;
            margin-bottom: 3px;
        }
        .info-field span {
            font-size: 0.95rem;
            font-weight: 600;
            color: var(--text);
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="header-top">
                <div>
                    <h1 data-i18n="title">🦷 Dental Clinic Management System</h1>
                    <p data-i18n="subtitle">Complete Patient Care & Appointment Management</p>
                </div>
                <div class="header-meta">
                    <div class="doctor-badge" data-i18n="doctor_name">Dr. Wasfy Barzaq</div>
                    <button id="theme-toggle" class="btn btn-warning theme-toggle" title="Night Mode" aria-label="Night Mode">🌙</button>
                    <button id="language-toggle" class="btn btn-warning language-toggle" data-i18n="language_toggle">English/العربية</button>
                </div>
            </div>
        </div>
        
        <div class="app-body">
        <div class="nav-tabs">
            <div class="nav-tabs-label" data-i18n="navigation">Navigation</div>
            <button class="nav-tab active" onclick="switchTab('dashboard', this)"><span class="tab-icon">🏠</span><span data-en="Dashboard" data-ar="لوحة المعلومات">Dashboard</span></button>
            <button class="nav-tab" onclick="switchTab('patients', this)"><span class="tab-icon">👥</span><span data-en="Patients" data-ar="المرضى">Patients</span></button>
            <button class="nav-tab" onclick="switchTab('appointments', this)"><span class="tab-icon">📅</span><span data-en="Appointments" data-ar="المواعيد">Appointments</span></button>
            <button class="nav-tab" onclick="switchTab('reports', this)"><span class="tab-icon">📊</span><span data-en="Reports" data-ar="التقارير">Reports</span></button>
            <button class="nav-tab" onclick="switchTab('financial', this)"><span class="tab-icon">💰</span><span data-en="Financial" data-ar="المالي">Financial</span></button>
            <button class="nav-tab" onclick="switchTab('support', this)"><span class="tab-icon">🔧</span><span data-en="Support" data-ar="الدعم">Support</span></button>
        </div>

        <div class="content">
            <!-- Dashboard Tab -->
            <div id="dashboard" class="tab-content active">
                <div class="page-header">
                    <h2 data-i18n="dashboard_overview">Dashboard Overview</h2>
                    <div class="header-actions">
                        <button class="btn btn-primary" onclick="downloadBackup()" data-i18n="download_backup">💾 Download Backup</button>
                    </div>
                </div>
                <div class="stats-grid" id="stats-grid">
                    <div class="stat-card stat-card-teal">
                        <span class="stat-icon">👥</span>
                        <h3 id="total-patients">0</h3>
                        <p data-i18n="total_patients">Total Patients</p>
                    </div>
                    <div class="stat-card stat-card-blue">
                        <span class="stat-icon">📅</span>
                        <h3 id="today-appointments">0</h3>
                        <p data-i18n="todays_appointments">Today's Appointments</p>
                    </div>
                    <div class="stat-card stat-card-green">
                        <span class="stat-icon">🩺</span>
                        <h3 id="total-visits">0</h3>
                        <p data-i18n="total_visits">Total Visits</p>
                    </div>
                    <div class="stat-card stat-card-amber">
                        <span class="stat-icon">💰</span>
                        <h3 id="total-revenue">₪ 0</h3>
                        <p data-i18n="total_revenue">Total Revenue</p>
                    </div>
                </div>

                <div class="section-divider"><span data-i18n="recent_appointments">Recent Appointments</span></div>
                <div class="table-container">
                    <table id="recent-appointments-table">
                        <thead>
                            <tr>
                                <th data-i18n="patient">Patient</th>
                                <th data-i18n="date_time">Date & Time</th>
                                <th data-i18n="treatment_type">Treatment Type</th>
                                <th data-i18n="status">Status</th>
                            </tr>
                        </thead>
                        <tbody id="recent-appointments-body"></tbody>
                    </table>
                </div>
            </div>
            
            <!-- Patients Tab -->
            <div id="patients" class="tab-content">
                <div class="page-header">
                    <h2 data-i18n="patient_management">Patient Management</h2>
                    <div class="header-actions">
                        <button class="btn btn-primary" onclick="showAddPatientModal()" data-i18n="add_new_patient">+ Add New Patient</button>
                    </div>
                </div>

                <div class="form-row" style="margin-top:0; margin-bottom:0;">
                    <div class="form-group" style="margin-bottom:0;">
                        <label data-i18n="search_by_name_phone_email">Search by name, phone, or email</label>
                        <input type="text" id="patient-search-input" data-i18n-placeholder="search_placeholder" placeholder="Type patient name, phone, or email" oninput="filterPatientsTable()">
                    </div>
                    <div class="form-group" style="margin-bottom:0; display:flex; align-items:flex-end; gap:10px;">
                        <button class="btn btn-primary" type="button" onclick="openFirstPatientMatch()" data-i18n="open_patient_by_name">Open Patient by Name</button>
                        <button class="btn btn-warning" type="button" onclick="clearPatientSearch()" data-i18n="clear">Clear</button>
                    </div>
                </div>
                <div id="patient-search-status" class="search-status" data-i18n="showing_all_patients">Showing all patients.</div>
                
                <div class="table-container">
                    <table id="patients-table">
                        <thead>
                            <tr>
                                <th>ID</th>
                                <th data-i18n="name">Name</th>
                                <th data-i18n="date_of_birth">Date of Birth</th>
                                <th data-i18n="phone">Phone</th>
                                <th data-i18n="email">Email</th>
                                <th data-i18n="actions">Actions</th>
                            </tr>
                        </thead>
                        <tbody id="patients-body"></tbody>
                    </table>
                </div>
            </div>
            
            <!-- Appointments Tab -->
            <div id="appointments" class="tab-content">
                <div class="page-header">
                    <h2 data-i18n="appointments">Appointments</h2>
                    <div class="header-actions">
                        <button class="btn btn-primary" onclick="showAddAppointmentModal()" data-i18n="schedule_appointment">+ Schedule Appointment</button>
                    </div>
                </div>

                <div class="calendar-controls">
                    <div class="toolbar-row" style="margin-top:0;">
                        <button class="btn btn-warning" type="button" onclick="changeCalendarMonth(-1)" data-i18n="previous_month">Previous Month</button>
                        <button class="btn btn-warning" type="button" onclick="goToCurrentCalendarMonth()" data-i18n="current_month">Current Month</button>
                        <button class="btn btn-warning" type="button" onclick="changeCalendarMonth(1)" data-i18n="next_month">Next Month</button>
                    </div>
                    <div id="calendar-month-label" class="calendar-month-title"></div>
                    <button class="btn btn-warning" type="button" onclick="loadAppointments()" data-i18n="refresh">Refresh</button>
                </div>

                <div id="appointments-calendar" class="appointments-calendar"></div>

                <details class="holiday-panel">
                    <summary>📆 <span data-i18n="holiday_management">Holiday Management</span></summary>
                    <div class="holiday-panel-body">
                        <form id="holiday-form">
                            <div class="form-row">
                                <div class="form-group">
                                    <label data-i18n="holiday_date">Holiday Date *</label>
                                    <input type="text" name="holiday_date" id="holiday-date" placeholder="DD/MM/YYYY" title="Enter date in DD/MM/YYYY format" required>
                                </div>
                                <div class="form-group">
                                    <label data-i18n="holiday_name">Holiday Name *</label>
                                    <input type="text" name="name" required>
                                </div>
                            </div>
                            <div class="form-group">
                                <label data-i18n="notes">Notes</label>
                                <textarea name="notes" data-i18n-placeholder="optional_note" placeholder="Optional note"></textarea>
                            </div>
                            <button class="btn btn-primary" type="submit" data-i18n="add_holiday">Add Holiday</button>
                        </form>
                        <div class="table-container" style="margin-top:16px;">
                            <table>
                                <thead>
                                    <tr>
                                        <th data-i18n="date">Date</th>
                                        <th data-i18n="holiday">Holiday</th>
                                        <th data-i18n="notes">Notes</th>
                                        <th data-i18n="actions">Actions</th>
                                    </tr>
                                </thead>
                                <tbody id="holidays-body"><tr><td colspan="4" data-i18n="no_holidays_yet">No holidays yet</td></tr></tbody>
                            </table>
                        </div>
                    </div>
                </details>
                
                <div class="table-container">
                    <table id="appointments-table">
                        <thead>
                            <tr>
                                <th>ID</th>
                                <th data-i18n="patient">Patient</th>
                                <th data-i18n="date_time">Date & Time</th>
                                <th data-i18n="duration">Duration</th>
                                <th data-i18n="treatment_type">Treatment Type</th>
                                <th data-i18n="status">Status</th>
                            </tr>
                        </thead>
                        <tbody id="appointments-body"></tbody>
                    </table>
                </div>
            </div>

            <div id="reports" class="tab-content">
                <div class="page-header">
                    <h2 data-i18n="reporting_system">Reporting System</h2>
                </div>
                <div class="sub-tabs" id="reports-sub-tabs">
                    <button class="sub-tab active" onclick="switchReportsSubTab('weekly', this)" data-i18n="weekly_tab">Weekly</button>
                    <button class="sub-tab" onclick="switchReportsSubTab('monthly', this)" data-i18n="monthly_tab">Monthly</button>
                    <button class="sub-tab" onclick="switchReportsSubTab('lab', this)" data-i18n="lab_tab">Lab</button>
                </div>

                <div id="reports-subtab-weekly" class="sub-tab-content active">
                    <div class="toolbar-row" style="margin-top:0;">
                        <div class="form-group" style="margin:0;">
                            <label data-i18n="start_date">Start Date</label>
                            <input type="date" id="weekly-start-picker">
                        </div>
                        <button class="btn btn-success" onclick="loadWeeklyReport()" data-i18n="this_week">This Week</button>
                        <button class="btn btn-primary" onclick="loadWeeklyReportFromPicker()" data-i18n="run_report">Run Report</button>
                    </div>
                    <div id="weekly-report-range" class="search-status" data-i18n="weekly_range_not_selected">Weekly range not selected.</div>
                </div>

                <div id="reports-subtab-monthly" class="sub-tab-content">
                    <div class="form-row">
                        <div class="form-group">
                            <label data-i18n="month">Month</label>
                            <input type="month" id="report-month-picker">
                        </div>
                    </div>
                    <div class="toolbar-row" style="margin-top:0;">
                        <button class="btn btn-primary" onclick="loadMonthlyReport()" data-i18n="run_monthly_report">Run Monthly Report</button>
                    </div>
                </div>

                <div id="reports-subtab-lab" class="sub-tab-content">
                    <div class="form-row">
                        <div class="form-group">
                            <label data-i18n="start_date">Start Date</label>
                            <input type="date" id="report-start-date">
                        </div>
                        <div class="form-group">
                            <label data-i18n="end_date">End Date</label>
                            <input type="date" id="report-end-date">
                        </div>
                    </div>
                    <div class="toolbar-row" style="margin-top:0;">
                        <button class="btn btn-primary" onclick="loadLabReport()" data-i18n="run_lab_report">Run Lab Report</button>
                    </div>

                    <details id="procedure-catalog-panel" class="collapsible-box" ontoggle="handleProcedureCatalogToggle(this)" style="margin-top:12px;">
                        <summary data-i18n="procedure_catalog">Procedure Catalog</summary>
                        <div style="margin-top:12px;">
                            <form id="procedure-form">
                                <input type="hidden" id="procedure-id" value="">
                                <div class="form-row">
                                    <div class="form-group">
                                        <label data-i18n="procedure_name_required">Procedure Name *</label>
                                        <input type="text" id="procedure-name" required>
                                    </div>
                                    <div class="form-group">
                                        <label data-i18n="default_price">Default Price</label>
                                        <input type="number" step="0.01" min="0" id="procedure-default-price" value="0">
                                    </div>
                                    <div class="form-group">
                                        <label data-i18n="default_lab_expense">Default Lab Expense</label>
                                        <input type="number" step="0.01" min="0" id="procedure-default-lab-expense" value="0">
                                    </div>
                                </div>
                                <div class="toolbar-row" style="margin-top:0; margin-bottom:10px;">
                                    <label style="display:flex; gap:8px; align-items:center; font-weight:600;">
                                        <input type="checkbox" id="procedure-requires-lab">
                                        <span data-i18n="requires_lab">Requires Lab</span>
                                    </label>
                                    <label style="display:flex; gap:8px; align-items:center; font-weight:600;">
                                        <input type="checkbox" id="procedure-active" checked>
                                        <span data-i18n="active">Active</span>
                                    </label>
                                </div>
                                <div class="toolbar-row" style="margin-top:0; margin-bottom:10px;">
                                    <button class="btn btn-primary" type="submit" id="procedure-save-btn" data-i18n="save_procedure">Save Procedure</button>
                                    <button class="btn btn-warning" type="button" id="procedure-cancel-btn" onclick="resetProcedureForm()" data-i18n="cancel">Cancel</button>
                                </div>
                            </form>
                            <div class="table-container" style="margin-top:12px;">
                                <table>
                                    <thead>
                                        <tr>
                                            <th data-i18n="procedure_name">Procedure</th>
                                            <th data-i18n="requires_lab">Requires Lab</th>
                                            <th data-i18n="default_price">Default Price</th>
                                            <th data-i18n="default_lab_expense">Default Lab Expense</th>
                                            <th data-i18n="active">Active</th>
                                            <th data-i18n="actions">Actions</th>
                                        </tr>
                                    </thead>
                                    <tbody id="procedures-body"><tr><td colspan="6" data-i18n="no_data">No data</td></tr></tbody>
                                </table>
                            </div>
                        </div>
                    </details>

                    <details id="treatment-catalog-panel" class="collapsible-box" ontoggle="if(this.open)loadTreatmentCatalogUI()" style="margin-top:12px;">
                        <summary>إدارة العلاجات / Treatment Catalog</summary>
                        <div style="margin-top:12px;">
                            <form id="treatment-catalog-form">
                                <input type="hidden" id="tc-id" value="">
                                <div class="form-row">
                                    <div class="form-group">
                                        <label>الاسم بالعربية *</label>
                                        <input type="text" id="tc-name-ar" required>
                                    </div>
                                    <div class="form-group">
                                        <label>English Name</label>
                                        <input type="text" id="tc-name-en">
                                    </div>
                                    <div class="form-group">
                                        <label>السعر الافتراضي</label>
                                        <input type="number" step="0.01" min="0" id="tc-price" value="0">
                                    </div>
                                </div>
                                <div class="toolbar-row" style="margin-top:0; margin-bottom:10px;">
                                    <button class="btn btn-primary" type="submit">حفظ</button>
                                    <button class="btn btn-warning" type="button" onclick="resetTreatmentCatalogForm()">إلغاء</button>
                                </div>
                            </form>
                            <div class="table-container" style="margin-top:12px;">
                                <table>
                                    <thead><tr><th>الاسم بالعربية</th><th>English</th><th>السعر</th><th>الحالة</th><th>إجراءات</th></tr></thead>
                                    <tbody id="treatment-catalog-body"><tr><td colspan="5">Loading...</td></tr></tbody>
                                </table>
                            </div>
                        </div>
                    </details>
                </div>

                <div class="stats-grid" style="margin-top:20px;">
                    <div class="stat-card"><h3 id="report-visits">0</h3><p data-i18n="visits">Visits</p></div>
                    <div class="stat-card"><h3 id="report-revenue">₪ 0</h3><p data-i18n="revenue">Revenue</p></div>
                    <div class="stat-card"><h3 id="report-expenses">₪ 0</h3><p data-i18n="expenses">Expenses</p></div>
                    <div class="stat-card"><h3 id="report-lab-expenses">₪ 0</h3><p data-i18n="lab_expenses">Lab Expenses</p></div>
                    <div class="stat-card"><h3 id="report-clinic-gross-profit">₪ 0</h3><p data-i18n="clinic_gross_profit">Clinic Gross Profit</p></div>
                    <div class="stat-card"><h3 id="report-profit">₪ 0</h3><p data-i18n="profit">Profit</p></div>
                </div>
            </div>

            <div id="financial" class="tab-content">
                <div class="page-header">
                    <h2 data-i18n="financial_management">Financial Management</h2>
                </div>
                <div class="sub-tabs" id="financial-sub-tabs">
                    <button class="sub-tab active" onclick="switchFinancialSubTab('management', this)" data-i18n="management_tab">Management</button>
                    <button class="sub-tab" onclick="switchFinancialSubTab('billing', this)" data-i18n="billing_tab">Billing</button>
                    <button class="sub-tab" onclick="switchFinancialSubTab('invoices', this)" data-i18n="invoices_tab">Invoices</button>
                </div>

                <div id="financial-subtab-management" class="sub-tab-content active">

                <h3 style="margin-top:20px;" data-i18n="receivables_tracking">Receivables Tracking</h3>
                <div class="stats-grid" style="margin-top:10px; margin-bottom:10px;">
                    <div class="stat-card"><h3 id="receivables-total">₪ 0</h3><p data-i18n="total_receivables">Total Receivables</p></div>
                    <div class="stat-card"><h3 id="receivables-count">0</h3><p data-i18n="patients_with_balance">Patients with Balance</p></div>
                </div>
                <div class="table-container" style="margin-top:12px;">
                    <table>
                        <thead>
                            <tr>
                                <th data-i18n="patient_name">Patient Name</th>
                                <th data-i18n="total_to_pay">Total to Pay</th>
                                <th data-i18n="paid">Paid</th>
                                <th data-i18n="left">Left</th>
                                <th data-i18n="last_date">Last Date</th>
                                <th data-i18n="overdue_days">Overdue Days</th>
                            </tr>
                        </thead>
                        <tbody id="receivables-body"><tr><td colspan="6" data-i18n="no_data">No data</td></tr></tbody>
                    </table>
                </div>

                <details class="form-panel" open>
                <summary>➕ <span data-i18n="expense_tracking">Expense Tracking</span></summary>
                <div class="form-panel-body">
                <div class="toolbar-row" style="margin-top:0; margin-bottom:10px;">
                    <label for="expense-filter-period" style="font-weight:600;" data-i18n="period">Period:</label>
                    <select id="expense-filter-period" onchange="loadExpenses()" style="max-width:190px;">
                        <option value="all" data-i18n="all">All</option>
                        <option value="today" data-i18n="today">Today</option>
                        <option value="week" data-i18n="this_week">This Week</option>
                        <option value="month" data-i18n="this_month">This Month</option>
                    </select>
                    <label for="expense-filter-status-select" style="font-weight:600;" data-i18n="status">Status:</label>
                    <select id="expense-filter-status-select" onchange="loadExpenses()" style="max-width:190px;">
                        <option value="all" data-i18n="all_status">All Status</option>
                        <option value="paid" data-i18n="paid">Paid</option>
                        <option value="postponed" data-i18n="postponed">Postponed</option>
                    </select>
                </div>
                <div id="expense-filter-status" class="search-status" style="margin-bottom:12px;" data-i18n="showing_all_expenses">Showing all expenses.</div>
                <form id="expense-form">
                    <div class="form-row-3">
                        <div class="form-group">
                            <label data-i18n="category_required">Category *</label>
                            <input type="text" name="category" required>
                        </div>
                        <div class="form-group">
                            <label data-i18n="amount_required">Amount (₪) *</label>
                            <input type="number" step="0.01" min="0" name="amount" required>
                        </div>
                        <div class="form-group">
                            <label data-i18n="vendor">Vendor</label>
                            <input type="text" name="vendor">
                        </div>
                    </div>
                    <div class="form-row">
                        <div class="form-group">
                            <label data-i18n="date_required">Date *</label>
                            <input type="text" name="expense_date" id="expense-date" placeholder="DD/MM/YYYY" title="Enter date in DD/MM/YYYY format" required>
                        </div>
                        <div class="form-group">
                            <label data-i18n="status_required">Status *</label>
                            <select name="payment_status" required>
                                <option value="paid" data-i18n="paid">Paid</option>
                                <option value="postponed" data-i18n="postponed">Postponed</option>
                            </select>
                        </div>
                    </div>
                    <div class="form-group">
                        <label data-i18n="notes">Notes</label>
                        <textarea name="notes" data-i18n-placeholder="optional_note" placeholder="Optional note" style="min-height: 48px;"></textarea>
                    </div>
                    <button class="btn btn-primary" type="submit" data-i18n="add_expense">Add Expense</button>
                </form>
                </div>
                </details>
                <div class="table-container" style="margin-top:16px;">
                    <table>
                        <thead>
                            <tr>
                                <th data-i18n="date">Date</th>
                                <th data-i18n="category">Category</th>
                                <th data-i18n="amount">Amount</th>
                                <th data-i18n="status">Status</th>
                                <th data-i18n="vendor">Vendor</th>
                                <th data-i18n="notes">Notes</th>
                                <th data-i18n="actions">Actions</th>
                            </tr>
                        </thead>
                        <tbody id="expenses-body"><tr><td colspan="7" data-i18n="no_expenses_yet">No expenses yet</td></tr></tbody>
                    </table>
                </div>
                </div>

                <div id="financial-subtab-billing" class="sub-tab-content">

                <details class="form-panel" open>
                <summary>➕ <span data-i18n="billing_management">Billing Management</span></summary>
                <div class="form-panel-body">
                <form id="billing-form">
                    <div class="form-row">
                        <div class="form-group">
                            <label data-i18n="patient_required">Patient *</label>
                            <select name="patient_id" id="billing-patient-select" required>
                                <option value="" data-i18n="select_patient">Select Patient</option>
                            </select>
                        </div>
                        <div class="form-group">
                            <label data-i18n="date">Date</label>
                            <input type="text" name="payment_date" id="billing-date" placeholder="DD/MM/YYYY" title="Enter date in DD/MM/YYYY format">
                        </div>
                    </div>
                    <div class="form-row-3">
                        <div class="form-group">
                            <label data-i18n="subtotal_required">Subtotal *</label>
                            <input type="number" step="0.01" min="0" name="subtotal" required>
                        </div>
                        <div class="form-group">
                            <label data-i18n="discount">Discount</label>
                            <input type="number" step="0.01" min="0" name="discount" value="0">
                        </div>
                        <div class="form-group">
                            <label>Credit Used</label>
                            <input type="number" step="0.01" min="0" name="credit_used" value="0" id="billing-credit-used">
                        </div>
                    </div>
                    <div class="form-row">
                        <div class="form-group">
                            <label data-i18n="paid_amount">Paid Amount</label>
                            <input type="number" step="0.01" min="0" name="paid_amount" value="0">
                        </div>
                        <div class="form-group">
                            <label data-i18n="payment_method">Payment Method</label>
                            <input type="text" name="payment_method" placeholder="Cash / Card / Transfer">
                        </div>
                    </div>
                    <button class="btn btn-primary" type="submit" data-i18n="create_invoice">Create Invoice</button>
                </form>
                </div>
                </details>
                <div class="table-container" style="margin-top:12px;">
                    <table>
                        <thead>
                            <tr>
                                <th data-i18n="invoice_no">Invoice #</th>
                                <th data-i18n="patient">Patient</th>
                                <th data-i18n="amount">Amount</th>
                                <th data-i18n="paid_amount">Paid Amount</th>
                                <th data-i18n="balance_due">Balance Due</th>
                                <th data-i18n="status">Status</th>
                                <th data-i18n="date">Date</th>
                                <th data-i18n="actions">Actions</th>
                            </tr>
                        </thead>
                        <tbody id="billing-body"><tr><td colspan="8" data-i18n="no_data">No data</td></tr></tbody>
                    </table>
                </div>
                </div>

                <div id="financial-subtab-invoices" class="sub-tab-content">

                <h3 style="margin-top:20px;" data-i18n="patient_total_invoice">Patient Total Invoice</h3>
                <div class="form-row">
                    <div class="form-group">
                        <label data-i18n="patient_required">Patient *</label>
                        <select id="invoice-patient-select">
                            <option value="" data-i18n="select_patient">Select Patient</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label data-i18n="start_date">Start Date</label>
                        <input type="date" id="invoice-start-date">
                    </div>
                    <div class="form-group">
                        <label data-i18n="end_date">End Date</label>
                        <input type="date" id="invoice-end-date">
                    </div>
                </div>
                <div class="toolbar-row" style="margin-top:0; margin-bottom:10px;">
                    <div class="form-group" style="margin:0; min-width:220px;">
                        <label for="invoice-print-language" data-i18n="print_language">Print Language</label>
                        <select id="invoice-print-language">
                            <option value="current" data-i18n="print_language_current">Current App Language</option>
                            <option value="ar" data-i18n="print_language_arabic">Arabic</option>
                            <option value="en" data-i18n="print_language_english">English</option>
                        </select>
                    </div>
                    <button class="btn btn-success" type="button" onclick="loadPatientInvoiceSummary()" data-i18n="generate_total_invoice">Generate Total Invoice</button>
                    <button class="btn btn-primary" type="button" onclick="printCurrentPatientInvoice()" data-i18n="print_invoice">Print Invoice</button>
                </div>
                <div class="stats-grid" style="margin-top:10px; margin-bottom:10px;">
                    <div class="stat-card"><h3 id="invoice-total-to-pay">₪ 0</h3><p data-i18n="total_to_pay">Total to Pay</p></div>
                    <div class="stat-card"><h3 id="invoice-total-paid">₪ 0</h3><p data-i18n="paid">Paid</p></div>
                    <div class="stat-card"><h3 id="invoice-total-left">₪ 0</h3><p data-i18n="left">Left</p></div>
                </div>
                <div class="table-container" style="margin-top:12px;">
                    <table>
                        <thead>
                            <tr>
                                <th data-i18n="date">Date</th>
                                <th data-i18n="treatment_procedure">Treatment Procedure</th>
                                <th data-i18n="price">Price</th>
                                <th data-i18n="payment">Payment</th>
                                <th data-i18n="balance">Balance</th>
                            </tr>
                        </thead>
                        <tbody id="patient-invoice-body"><tr><td colspan="5" data-i18n="no_data">No data</td></tr></tbody>
                    </table>
                </div>
                </div>
            </div>

            <div id="support" class="tab-content">
                <div class="page-header">
                    <h2 data-i18n="technical_support">Technical Support</h2>
                </div>
                <h3 style="margin-top:4px;" data-i18n="audit_log">Audit Log</h3>
                <div class="table-container" style="margin-top:12px;">
                    <table>
                        <thead>
                            <tr>
                                <th>ID</th>
                                <th data-i18n="date_time">Date and Time</th>
                                <th data-i18n="action">Action</th>
                                <th data-i18n="entity">Entity</th>
                                <th data-i18n="details">Details</th>
                            </tr>
                        </thead>
                        <tbody id="audit-logs-body"><tr><td colspan="5" data-i18n="no_data">No data</td></tr></tbody>
                    </table>
                </div>
                <div id="support-content"></div>
                <div style="margin-top:20px;">
                    <button class="btn btn-primary" onclick="loadSupportSection()" data-i18n="refresh_help">Refresh Help</button>
                </div>
            </div>
        </div>
        </div><!-- end app-body -->
    </div>
    
    <!-- Add Patient Modal -->
    <div id="add-patient-modal" class="modal" onclick="if(event.target===this)closeModal('add-patient-modal')">
        <div class="modal-content">
            <div class="modal-header">
                <span class="close-modal" onclick="closeModal('add-patient-modal')">&times;</span>
                <h2 data-i18n="add_new_patient">Add New Patient</h2>
            </div>
            <form id="add-patient-form">
                <div class="form-row">
                    <div class="form-group">
                        <label data-i18n="first_name_required">First Name *</label>
                        <input type="text" name="first_name" required>
                    </div>
                    <div class="form-group">
                        <label data-i18n="last_name_required">Last Name *</label>
                        <input type="text" name="last_name" required>
                    </div>
                </div>
                <div class="form-row">
                    <div class="form-group">
                        <label data-i18n="date_of_birth">Date of Birth</label>
                        <div style="display:flex;gap:8px;align-items:flex-end;"><input type="text" name="date_of_birth" placeholder="DD/MM/YYYY" style="flex:1;"><button type="button" class="btn btn-warning" onclick="showDatePickerForPatient()" style="padding:11px 14px;min-width:48px;">📅</button></div>
                    </div>
                    <div class="form-group">
                        <label data-i18n="phone">Phone</label>
                        <input type="tel" name="phone">
                    </div>
                </div>
                <div class="form-group">
                    <label data-i18n="email">Email</label>
                    <input type="email" name="email">
                </div>
                <div class="form-group">
                    <label data-i18n="address">Address</label>
                    <input type="text" name="address">
                </div>
                <div class="form-group">
                    <label data-i18n="medical_history">Medical History</label>
                    <textarea name="medical_history"></textarea>
                </div>
                <button type="submit" class="btn btn-primary" data-i18n="add_patient">Add Patient</button>
            </form>
        </div>
    </div>
    
    <!-- Add Appointment Modal -->
    <div id="add-appointment-modal" class="modal" onclick="if(event.target===this)closeModal('add-appointment-modal')">
        <div class="modal-content">
            <div class="modal-header">
                <span class="close-modal" onclick="closeModal('add-appointment-modal')">&times;</span>
                <h2 data-i18n="schedule_appointment">Schedule Appointment</h2>
            </div>
            <form id="add-appointment-form">
                <div class="form-group">
                    <label data-i18n="patient_required">Patient *</label>
                    <select name="patient_id" id="appointment-patient-select" required>
                        <option value="" data-i18n="select_patient">Select Patient</option>
                    </select>
                </div>
                <div class="form-row">
                    <div class="form-group">
                        <label data-i18n="date_time_required">Date & Time *</label>
                        <input type="datetime-local" name="appointment_date" title="Enter date and time (DD/MM/YYYY HH:MM)" required>
                    </div>
                    <div class="form-group">
                        <label data-i18n="duration_minutes">Duration (minutes)</label>
                        <input type="number" name="duration" value="30">
                    </div>
                </div>
                <div class="form-group">
                    <label data-i18n="treatment_type">Treatment Type</label>
                    <select name="treatment_type">
                        <option value="Checkup" data-i18n="treatment_checkup">Checkup</option>
                        <option value="Cleaning" data-i18n="treatment_cleaning">Cleaning</option>
                        <option value="Filling" data-i18n="treatment_filling">Filling</option>
                        <option value="Root Canal" data-i18n="treatment_root_canal">Root Canal</option>
                        <option value="Extraction" data-i18n="treatment_extraction">Extraction</option>
                        <option value="Whitening" data-i18n="treatment_whitening">Whitening</option>
                        <option value="Crown" data-i18n="treatment_crown">Crown</option>
                        <option value="Braces" data-i18n="treatment_braces">Braces</option>
                        <option value="Other" data-i18n="other">Other</option>
                    </select>
                </div>
                <div class="form-group">
                    <label data-i18n="notes">Notes</label>
                    <textarea name="notes"></textarea>
                </div>
                <button type="submit" class="btn btn-primary" data-i18n="schedule_appointment">Schedule Appointment</button>
            </form>
        </div>
    </div>
    
    <!-- Edit Patient Modal -->
    <div id="edit-patient-modal" class="modal" onclick="if(event.target===this)closeModal('edit-patient-modal')">
        <div class="modal-content">
            <div class="modal-header">
                <span class="close-modal" onclick="closeModal('edit-patient-modal')">&times;</span>
                <h2 data-i18n="edit_personal_data">Edit Personal Data</h2>
            </div>
            <form id="edit-patient-form">
                <input type="hidden" name="patient_id" id="edit-patient-id">
                <div class="form-row">
                    <div class="form-group"><label data-i18n="first_name">First Name</label><input type="text" name="first_name" id="edit-first-name"></div>
                    <div class="form-group"><label data-i18n="last_name">Last Name</label><input type="text" name="last_name" id="edit-last-name"></div>
                </div>
                <div class="form-row">
                    <div class="form-group"><label data-i18n="phone">Phone</label><input type="tel" name="phone" id="edit-phone"></div>
                    <div class="form-group"><label><span data-i18n="date_of_birth">Date of Birth</span> (DD/MM/YYYY)</label><input type="text" name="date_of_birth" id="edit-dob" placeholder="DD/MM/YYYY" title="Enter date in DD/MM/YYYY format"></div>
                </div>
                <div class="form-row">
                    <div class="form-group"><label data-i18n="gender">Gender</label><select name="gender" id="edit-gender"><option value="">--</option><option value="male" data-i18n="male">Male</option><option value="female" data-i18n="female">Female</option></select></div>
                    <div class="form-group"><label data-i18n="address">Address</label><input type="text" name="address" id="edit-address"></div>
                </div>
                <div class="form-group"><label data-i18n="notes">Notes</label><textarea name="notes" id="edit-notes"></textarea></div>
                <button type="submit" class="btn btn-primary" data-i18n="save">Save</button>
            </form>
        </div>
    </div>

    <!-- Edit Followup Modal -->
    <div id="edit-followup-modal" class="modal" onclick="if(event.target===this)closeModal('edit-followup-modal')">
        <div class="modal-content">
            <div class="modal-header">
                <span class="close-modal" onclick="closeModal('edit-followup-modal')">&times;</span>
                <h2 data-i18n="edit_entry">Edit Entry</h2>
            </div>
            <form id="edit-followup-form">
                <input type="hidden" id="ef-patient-id">
                <input type="hidden" id="ef-followup-id">
                <div class="form-row">
                    <div class="form-group">
                        <label data-i18n="date">Date</label>
                        <input type="text" id="ef-date" placeholder="DD/MM/YYYY" title="Enter date in DD/MM/YYYY format">
                    </div>
                    <div class="form-group">
                        <label data-i18n="procedure">Procedure</label>
                        <input type="text" id="ef-procedure">
                    </div>
                </div>
                <div class="form-row">
                    <div class="form-group">
                        <label data-i18n="price">Price</label>
                        <input type="number" step="0.01" min="0" id="ef-price" value="0">
                    </div>
                    <div class="form-group">
                        <label data-i18n="payment">Payment</label>
                        <input type="number" step="0.01" min="0" id="ef-payment" value="0">
                    </div>
                </div>
                <div class="form-group">
                    <label data-i18n="notes">Notes</label>
                    <textarea id="ef-notes"></textarea>
                </div>
                <button type="submit" class="btn btn-primary" data-i18n="save">Save</button>
                <button type="button" class="btn btn-warning" onclick="closeModal('edit-followup-modal')" data-i18n="cancel">Cancel</button>
            </form>
        </div>
    </div>

    <!-- Full Patient Profile Modal -->
    <div id="patient-profile-modal" class="modal" onclick="if(event.target===this)closeModal('patient-profile-modal')">
        <div class="modal-content" style="max-width: 1100px;">
            <div class="modal-header">
                <span class="close-modal" onclick="closeModal('patient-profile-modal')">&times;</span>
                <h2 data-i18n="patient_profile">Patient Profile</h2>
            </div>
            <div id="patient-profile-content"></div>
        </div>
    </div>

    <script>
        let patientsCache = [];
        let appointmentsCache = [];
        let holidaysCache = [];
        let treatmentProceduresCache = [];
        let billingCache = [];
        let currentPatientInvoicePayload = null;
        let currentProfilePatient = null;
        let currentFollowupBalance = 0;
        let patientProfileCache = {};
        let followupsCache = {};
        let currentCalendarDate = new Date();
        let currentLanguage = localStorage.getItem('clinic-language') || 'en';
        let currentTheme = localStorage.getItem('clinic-theme') || 'light';
        let currentReportsSubTab = localStorage.getItem('reports-subtab') || 'weekly';
        let currentFinancialSubTab = localStorage.getItem('financial-subtab') || 'management';

        // Language translations map
        const translations = {
            en: {
                title: 'Dental Clinic Management System',
                subtitle: 'Complete Patient Care and Appointment Management',
                doctor_name: 'Dr. Wasfy Barzaq',
                language_toggle: 'English/العربية',
                dashboard_overview: 'Dashboard Overview',
                total_patients: 'Total Patients',
                todays_appointments: "Today's Appointments",
                appointments: 'Appointments',
                recent_appointments: 'Recent Appointments',
                patient: 'Patient',
                patient_required: 'Patient *',
                date_time: 'Date and Time',
                date_time_required: 'Date and Time *',
                duration: 'Duration',
                duration_minutes: 'Duration (minutes)',
                treatment_type: 'Treatment Type',
                treatment_checkup: 'Checkup',
                treatment_cleaning: 'Cleaning',
                treatment_filling: 'Filling',
                treatment_root_canal: 'Root Canal',
                treatment_extraction: 'Extraction',
                treatment_whitening: 'Whitening',
                treatment_crown: 'Crown',
                treatment_braces: 'Braces',
                status: 'Status',
                patient_management: 'Patient Management',
                add_new_patient: 'Add New Patient',
                add_patient: 'Add Patient',
                first_name: 'First Name',
                first_name_required: 'First Name *',
                last_name: 'Last Name',
                last_name_required: 'Last Name *',
                date_of_birth: 'Date of Birth',
                phone: 'Phone',
                phone_required: 'Phone *',
                email: 'Email',
                address: 'Address',
                gender: 'Gender',
                male: 'Male',
                female: 'Female',
                medical_history: 'Medical History',
                search_by_name_phone_email: 'Search by name, phone, or email',
                search_placeholder: 'Type patient name, phone, or email',
                open_patient_by_name: 'Open Patient by Name',
                clear: 'Clear',
                showing_all_patients: 'Showing all patients.',
                showing_n_patients: 'Showing {count} patient(s).',
                name: 'Name',
                actions: 'Actions',
                download_backup: 'Download Backup',
                schedule_appointment: 'Schedule Appointment',
                schedule: 'Schedule',
                select_patient: 'Select Patient',
                appointment_date_required: 'Appointment Date *',
                appointment_time_required: 'Appointment Time *',
                previous_month: 'Previous Month',
                current_month: 'Current Month',
                next_month: 'Next Month',
                refresh: 'Refresh',
                holiday_management: 'Holiday Management',
                holiday_date: 'Holiday Date *',
                holiday_name: 'Holiday Name *',
                add_holiday: 'Add Holiday',
                date: 'Date',
                holiday: 'Holiday',
                no_holidays_yet: 'No holidays yet',
                optional_note: 'Optional note',
                reporting_system: 'Reporting System',
                financial_management: 'Financial Management',
                weekly_tab: 'Weekly',
                monthly_tab: 'Monthly',
                lab_tab: 'Lab',
                weekly_reports: 'Weekly',
                monthly_reports: 'Monthly',
                lab_reports: 'Lab',
                management_tab: 'Management',
                billing_tab: 'Billing',
                invoices_tab: 'Invoices',
                month: 'Month',
                run_monthly_report: 'Run Monthly Report',
                run_lab_report: 'Run Lab Report',
                print_invoice: 'Print Invoice',
                print_language: 'Print Language',
                print_language_current: 'Current App Language',
                print_language_arabic: 'Arabic',
                print_language_english: 'English',
                invoice_preview_unavailable: 'No invoice data to print yet.',
                description: 'Description',
                start_date: 'Start Date',
                end_date: 'End Date',
                run_report: 'Run Report',
                this_week: 'This Week',
                weekly_range_not_selected: 'Weekly range not selected.',
                night_mode: 'Night Mode',
                day_mode: 'Day Mode',
                visits: 'Visits',
                revenue: 'Revenue',
                expenses: 'Expenses',
                lab_expenses: 'Lab Expenses',
                clinic_gross_profit: 'Clinic Gross Profit',
                profit: 'Profit',
                procedure_catalog: 'Procedure Catalog',
                procedure_name: 'Procedure',
                procedure_name_required: 'Procedure Name *',
                default_price: 'Default Price',
                default_lab_expense: 'Default Lab Expense',
                active: 'Active',
                save_procedure: 'Save Procedure',
                edit_procedure: 'Edit',
                procedure_saved: 'Procedure saved successfully.',
                unable_save_procedure: 'Unable to save procedure.',
                receivables_tracking: 'Receivables Tracking',
                total_receivables: 'Total Receivables',
                patients_with_balance: 'Patients with Balance',
                last_date: 'Last Date',
                overdue_days: 'Overdue Days',
                billing_management: 'Billing Management',
                subtotal_required: 'Subtotal *',
                discount: 'Discount',
                paid_amount: 'Paid Amount',
                payment_method: 'Payment Method',
                create_invoice: 'Create Invoice',
                invoice_no: 'Invoice #',
                balance_due: 'Balance Due',
                patient_total_invoice: 'Patient Total Invoice',
                generate_total_invoice: 'Generate Total Invoice',
                audit_log: 'Audit Log',
                action: 'Action',
                entity: 'Entity',
                details: 'Details',
                unable_add_billing: 'Unable to create invoice.',
                no_receivables: 'No receivables found.',
                expense_tracking: 'Expense Tracking',
                period: 'Period:',
                all: 'All',
                today: 'Today',
                this_month: 'This Month',
                all_status: 'All Status',
                paid: 'Paid',
                postponed: 'Postponed',
                showing_all_expenses: 'Showing all expenses.',
                category_required: 'Category *',
                amount_required: 'Amount (ILS) *',
                date_required: 'Date *',
                status_required: 'Status *',
                category: 'Category',
                amount: 'Amount',
                vendor: 'Vendor',
                add_expense: 'Add Expense',
                no_expenses_yet: 'No expenses yet',
                technical_support: 'Technical Support',
                refresh_help: 'Refresh Help',
                patient_profile: 'Patient Profile',
                cancel: 'Cancel',
                other: 'Other',
                no_data: 'No data',
                yes: 'Yes',
                no: 'No',
                range: 'Range',
                full_period: 'full period',
                weekly_range_text: 'Weekly range: {start} to {end}',
                showing_expenses_count: 'Showing {count} expense(s).',
                no_expenses_found: 'No expenses found',
                no_appointments: 'No appointments',
                holiday_label: 'Holiday',
                no_holidays_for_day: 'No holidays',
                no_appointments_for_day: 'No appointments',
                visit_label: 'Visit',
                delete: 'Delete',
                edit: 'Edit',
                delete_expense_confirm: 'Delete this expense?',
                delete_holiday_confirm: 'Delete this holiday?',
                confirm_delete_patient: 'Are you sure you want to delete this patient?',
                select_patient_first: 'Please type a patient name first.',
                no_patient_match: 'No patient matched your search.',
                patient_not_found: 'Patient not found',
                saved_successfully: 'Saved successfully.',
                no_phone: 'No phone',
                view: 'View',
                book: 'Book',
                min: 'min',
                followups: 'Follow-ups',
                current_balance: 'Current balance',
                total_to_pay: 'Total to pay',
                left: 'Left',
                book_for_patient: 'Book Appointment for This Patient',
                open_calendar: 'Open Calendar',
                patient_name: 'Patient Name',
                followup_sheet: 'Patient Follow-up Sheet',
                treatment_procedure: 'Treatment Procedure',
                select_procedure: 'Select Procedure',
                custom_procedure_name: 'Custom Procedure Name',
                custom_procedure_placeholder: 'Type procedure name',
                requires_lab: 'Requires Lab',
                price: 'Price',
                lab_expense: 'Lab Expense',
                clinic_profit: 'Clinic Profit',
                payment: 'Payment',
                balance: 'Balance',
                add_entry: 'Add Entry',
                procedure_required: 'Please select a procedure or enter a custom procedure name.',
                medical_images: 'Medical Images',
                image_notes: 'Image notes',
                upload_image: 'Upload Image',
                file: 'File',
                uploaded: 'Uploaded',
                no_entries_yet: 'No entries yet',
                unable_save_followup: 'Unable to save follow-up.',
                unable_schedule_appointment: 'Unable to schedule appointment.',
                unable_add_expense: 'Unable to add expense.',
                unable_add_holiday: 'Unable to add holiday.',
                unable_start_visit: 'Unable to start visit.',
                visit_started: 'Visit started from appointment successfully.',
                unknown: 'Unknown',
                confirm_delete: 'Are you sure you want to delete?',
                no_entry_found: 'Entry not found',
                save_failed: 'Save failed',
                age: 'Age',
                age_unknown: 'Age not recorded',
                edit_personal_data: 'Edit Personal Data',
                edit_entry: 'Edit Entry',
                save: 'Save',
                credit_balance: 'Patient Credit Balance',
                edit_notes: 'Edit Notes',
                this_week: 'This Week',
                session_count: 'Sessions',
                patient_count: 'Patients',
                new_entries: 'New Entries',
                followups_count: 'Follow-ups',
                overview: 'Overview',
                patient_info: 'Patient Information',
                total_visits: 'Total Visits',
                total_revenue: 'Total Revenue',
                navigation: 'Navigation',
                notes: 'Notes'
            },
            ar: {
                title: 'نظام إدارة عيادة الأسنان',
                subtitle: 'إدارة شاملة للمرضى والمواعيد',
                doctor_name: 'د. وصفي برزق',
                language_toggle: 'العربية/English',
                dashboard_overview: 'نظرة عامة على لوحة التحكم',
                total_patients: 'إجمالي المرضى',
                todays_appointments: 'مواعيد اليوم',
                appointments: 'المواعيد',
                recent_appointments: 'أحدث المواعيد',
                patient: 'المريض',
                patient_required: 'المريض *',
                date_time: 'التاريخ والوقت',
                date_time_required: 'التاريخ والوقت *',
                duration: 'المدة',
                duration_minutes: 'المدة (بالدقائق)',
                treatment_type: 'نوع العلاج',
                treatment_checkup: 'فحص',
                treatment_cleaning: 'تنظيف',
                treatment_filling: 'حشو',
                treatment_root_canal: 'علاج عصب',
                treatment_extraction: 'خلع',
                treatment_whitening: 'تبييض',
                treatment_crown: 'تلبيسة',
                treatment_braces: 'تقويم',
                status: 'الحالة',
                patient_management: 'إدارة المرضى',
                add_new_patient: 'إضافة مريض جديد',
                add_patient: 'إضافة المريض',
                first_name: 'الاسم الأول',
                first_name_required: 'الاسم الأول *',
                last_name: 'اسم العائلة',
                last_name_required: 'اسم العائلة *',
                date_of_birth: 'تاريخ الميلاد',
                phone: 'رقم الهاتف',
                phone_required: 'رقم الهاتف *',
                email: 'البريد الإلكتروني',
                address: 'العنوان',
                gender: 'الجنس',
                male: 'ذكر',
                female: 'أنثى',
                medical_history: 'التاريخ الطبي',
                search_by_name_phone_email: 'ابحث بالاسم أو الهاتف أو البريد الإلكتروني',
                search_placeholder: 'اكتب اسم المريض أو الهاتف أو البريد الإلكتروني',
                open_patient_by_name: 'فتح المريض حسب الاسم',
                clear: 'مسح',
                showing_all_patients: 'عرض جميع المرضى.',
                showing_n_patients: 'يتم عرض {count} مريض/مرضى.',
                name: 'الاسم',
                actions: 'الإجراءات',
                download_backup: 'تنزيل نسخة احتياطية',
                schedule_appointment: 'جدولة موعد',
                schedule: 'حفظ الموعد',
                select_patient: 'اختر المريض',
                appointment_date_required: 'تاريخ الموعد *',
                appointment_time_required: 'وقت الموعد *',
                previous_month: 'الشهر السابق',
                current_month: 'الشهر الحالي',
                next_month: 'الشهر التالي',
                refresh: 'تحديث',
                holiday_management: 'إدارة العطلات',
                holiday_date: 'تاريخ العطلة *',
                holiday_name: 'اسم العطلة *',
                add_holiday: 'إضافة عطلة',
                date: 'التاريخ',
                holiday: 'العطلة',
                no_holidays_yet: 'لا توجد عطلات بعد',
                optional_note: 'ملاحظة اختيارية',
                reporting_system: 'نظام التقارير',
                financial_management: 'الإدارة المالية',
                weekly_tab: 'أسبوعي',
                monthly_tab: 'شهري',
                lab_tab: 'المعمل',
                weekly_reports: 'أسبوعي',
                monthly_reports: 'شهري',
                lab_reports: 'المعمل',
                management_tab: 'الإدارة',
                billing_tab: 'الفواتير',
                invoices_tab: 'ملخص الفواتير',
                month: 'الشهر',
                run_monthly_report: 'تشغيل التقرير الشهري',
                run_lab_report: 'تشغيل تقرير المعمل',
                print_invoice: 'طباعة فاتورة',
                print_language: 'لغة الطباعة',
                print_language_current: 'نفس لغة التطبيق',
                print_language_arabic: 'العربية',
                print_language_english: 'الإنجليزية',
                invoice_preview_unavailable: 'لا توجد بيانات فاتورة للطباعة بعد.',
                description: 'الوصف',
                start_date: 'تاريخ البداية',
                end_date: 'تاريخ النهاية',
                run_report: 'تشغيل التقرير',
                this_week: 'هذا الأسبوع',
                weekly_range_not_selected: 'لم يتم اختيار نطاق الأسبوع بعد.',
                night_mode: 'الوضع الليلي',
                day_mode: 'الوضع النهاري',
                visits: 'الزيارات',
                revenue: 'الإيرادات',
                expenses: 'المصروفات',
                lab_expenses: 'مصاريف المعمل',
                clinic_gross_profit: 'ربح العيادة الإجمالي',
                profit: 'صافي الربح',
                procedure_catalog: 'كتالوج الإجراءات',
                procedure_name: 'الإجراء',
                procedure_name_required: 'اسم الإجراء *',
                default_price: 'السعر الافتراضي',
                default_lab_expense: 'تكلفة المعمل الافتراضية',
                active: 'مفعّل',
                save_procedure: 'حفظ الإجراء',
                edit_procedure: 'تعديل',
                procedure_saved: 'تم حفظ الإجراء بنجاح.',
                unable_save_procedure: 'تعذر حفظ الإجراء.',
                receivables_tracking: 'متابعة الذمم',
                total_receivables: 'إجمالي الذمم',
                patients_with_balance: 'المرضى الذين عليهم رصيد',
                last_date: 'آخر تاريخ',
                overdue_days: 'أيام التأخير',
                billing_management: 'إدارة الفواتير',
                subtotal_required: 'الإجمالي قبل الخصم *',
                discount: 'الخصم',
                paid_amount: 'المبلغ المدفوع',
                payment_method: 'طريقة الدفع',
                create_invoice: 'إنشاء فاتورة',
                invoice_no: 'رقم الفاتورة',
                balance_due: 'الرصيد المستحق',
                patient_total_invoice: 'فاتورة كلية للمريض',
                generate_total_invoice: 'توليد الفاتورة الكلية',
                audit_log: 'سجل التعديلات',
                action: 'الإجراء',
                entity: 'الكيان',
                details: 'التفاصيل',
                unable_add_billing: 'تعذر إنشاء الفاتورة.',
                no_receivables: 'لا توجد ذمم حالياً.',
                expense_tracking: 'متابعة المصروفات',
                period: 'الفترة:',
                all: 'الكل',
                today: 'اليوم',
                this_month: 'هذا الشهر',
                all_status: 'كل الحالات',
                paid: 'مدفوع',
                postponed: 'مؤجل',
                showing_all_expenses: 'عرض جميع المصروفات.',
                category_required: 'التصنيف *',
                amount_required: 'المبلغ (شيكل) *',
                date_required: 'التاريخ *',
                status_required: 'الحالة *',
                category: 'التصنيف',
                amount: 'المبلغ',
                vendor: 'المورّد',
                add_expense: 'إضافة مصروف',
                no_expenses_yet: 'لا توجد مصروفات بعد',
                technical_support: 'الدعم الفني',
                refresh_help: 'تحديث المساعدة',
                patient_profile: 'ملف المريض',
                cancel: 'إلغاء',
                other: 'أخرى',
                no_data: 'لا توجد بيانات',
                yes: 'نعم',
                no: 'لا',
                range: 'النطاق',
                full_period: 'كامل الفترة',
                weekly_range_text: 'نطاق الأسبوع: من {start} إلى {end}',
                showing_expenses_count: 'يتم عرض {count} مصروف/مصروفات.',
                no_expenses_found: 'لا توجد مصروفات',
                no_appointments: 'لا توجد مواعيد',
                holiday_label: 'عطلة',
                no_holidays_for_day: 'لا توجد عطلات',
                no_appointments_for_day: 'لا توجد مواعيد',
                visit_label: 'زيارة',
                delete: 'حذف',
                edit: 'تعديل',
                delete_expense_confirm: 'هل تريد حذف هذا المصروف؟',
                delete_holiday_confirm: 'هل تريد حذف هذه العطلة؟',
                confirm_delete_patient: 'هل أنت متأكد من حذف هذا المريض؟',
                select_patient_first: 'يرجى كتابة اسم المريض أولا.',
                no_patient_match: 'لم يتم العثور على مريض مطابق للبحث.',
                patient_not_found: 'المريض غير موجود',
                saved_successfully: 'تم الحفظ بنجاح.',
                no_phone: 'لا يوجد رقم هاتف',
                view: 'عرض',
                book: 'حجز',
                min: 'دقيقة',
                followups: 'المتابعات',
                current_balance: 'الرصيد الحالي',
                total_to_pay: 'الإجمالي المطلوب',
                left: 'المتبقي',
                book_for_patient: 'حجز موعد لهذا المريض',
                open_calendar: 'فتح التقويم',
                patient_name: 'اسم المريض',
                followup_sheet: 'نموذج متابعة المريض',
                treatment_procedure: 'الإجراء العلاجي',
                select_procedure: 'اختر الإجراء',
                custom_procedure_name: 'اسم إجراء مخصص',
                custom_procedure_placeholder: 'اكتب اسم الإجراء',
                requires_lab: 'يتطلب معمل',
                price: 'السعر',
                lab_expense: 'مصروف المعمل',
                clinic_profit: 'ربح العيادة',
                payment: 'الدفعة',
                balance: 'الرصيد',
                add_entry: 'إضافة سجل',
                procedure_required: 'يرجى اختيار إجراء أو إدخال اسم إجراء مخصص.',
                medical_images: 'الصور الطبية',
                image_notes: 'ملاحظات الصورة',
                upload_image: 'رفع الصورة',
                file: 'الملف',
                uploaded: 'تاريخ الرفع',
                no_entries_yet: 'لا توجد سجلات بعد',
                unable_save_followup: 'تعذر حفظ المتابعة.',
                unable_schedule_appointment: 'تعذر جدولة الموعد.',
                unable_add_expense: 'تعذر إضافة المصروف.',
                unable_add_holiday: 'تعذر إضافة العطلة.',
                unable_start_visit: 'تعذر بدء الزيارة.',
                visit_started: 'تم بدء الزيارة من الموعد بنجاح.',
                unknown: 'غير معروف',
                confirm_delete: 'هل أنت متأكد من الحذف؟',
                no_entry_found: 'لم يتم العثور على القيد',
                save_failed: 'فشل الحفظ',
                age: 'العمر',
                age_unknown: 'العمر غير مسجل',
                edit_personal_data: 'تعديل البيانات الشخصية',
                edit_entry: 'تعديل القيد',
                save: 'حفظ',
                credit_balance: 'رصيد المريض لدى العيادة',
                edit_notes: 'تعديل الملاحظات',
                session_count: 'الجلسات',
                patient_count: 'المرضى',
                new_entries: 'علاجات جديدة',
                followups_count: 'مراجعات',
                overview: 'نظرة عامة',
                patient_info: 'بيانات المريض',
                total_visits: 'إجمالي الزيارات',
                total_revenue: 'إجمالي الإيرادات',
                navigation: 'التنقل',
                notes: 'الملاحظات'
            }
        };

        function t(key, fallback = '') {
            const value = translations[currentLanguage]?.[key];
            return typeof value === 'string' ? value : fallback;
        }

        function tForLang(lang, key, fallback = '') {
            const selectedLang = lang === 'ar' ? 'ar' : 'en';
            const value = translations[selectedLang]?.[key];
            return typeof value === 'string' ? value : fallback;
        }

        function getInvoicePrintLanguage() {
            const selected = document.getElementById('invoice-print-language')?.value || 'current';
            if (selected === 'ar' || selected === 'en') {
                return selected;
            }
            return currentLanguage === 'ar' ? 'ar' : 'en';
        }

        function getDoctorNameForLanguage(lang) {
            return tForLang(lang, 'doctor_name', translations.en.doctor_name || 'Dr. Wasfy Barzaq');
        }

        function applyTheme() {
            document.body.setAttribute('data-theme', currentTheme);
            const themeToggle = document.getElementById('theme-toggle');
            if (themeToggle) {
                const isDark = currentTheme === 'dark';
                const label = isDark ? t('day_mode', 'Day Mode') : t('night_mode', 'Night Mode');
                themeToggle.textContent = isDark ? '☀️' : '🌙';
                themeToggle.title = label;
                themeToggle.setAttribute('aria-label', label);
            }
        }

        function toggleTheme() {
            currentTheme = currentTheme === 'dark' ? 'light' : 'dark';
            localStorage.setItem('clinic-theme', currentTheme);
            applyTheme();
        }

        function toggleLanguage() {
            currentLanguage = currentLanguage === 'en' ? 'ar' : 'en';
            localStorage.setItem('clinic-language', currentLanguage);
            applyLanguage();
        }

        function applyLanguage() {
            const html = document.documentElement;
            html.lang = currentLanguage;
            html.dir = currentLanguage === 'ar' ? 'rtl' : 'ltr';

            document.querySelectorAll('[data-en][data-ar]').forEach(el => {
                el.textContent = currentLanguage === 'ar'
                    ? el.getAttribute('data-ar')
                    : el.getAttribute('data-en');
            });

            document.querySelectorAll('[data-i18n]').forEach(el => {
                const key = el.getAttribute('data-i18n');
                const text = t(key);
                if (typeof text === 'string') {
                    el.textContent = text;
                }
            });

            document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
                const key = el.getAttribute('data-i18n-placeholder');
                const text = t(key);
                if (typeof text === 'string') {
                    el.placeholder = text;
                }
            });

            const activeTab = document.querySelector('.tab-content.active')?.id;
            if (activeTab === 'dashboard') loadDashboard();
            else if (activeTab === 'patients') filterPatientsTable();
            else if (activeTab === 'appointments') loadAppointments();
            else if (activeTab === 'reports') loadReportsSection();
            else if (activeTab === 'financial') loadFinancialSection();
            else if (activeTab === 'support') loadSupportSection();

            applyTheme();
        }

        // Initialize language on page load
        applyLanguage();

        function toDatetimeLocalValue(dateObj) {
            const pad = (n) => String(n).padStart(2, '0');
            return `${dateObj.getFullYear()}-${pad(dateObj.getMonth() + 1)}-${pad(dateObj.getDate())}T${pad(dateObj.getHours())}:${pad(dateObj.getMinutes())}`;
        }

        function isFridayDateTimeValue(value) {
            if (!value) return false;
            const normalized = String(value).trim().replace(' ', 'T');
            const parsed = new Date(normalized);
            return !Number.isNaN(parsed.getTime()) && parsed.getDay() === 5;
        }

        function monthLabel(dateObj) {
            const locale = currentLanguage === 'ar' ? 'ar-EG' : 'en-US';
            return dateObj.toLocaleString(locale, { month: 'long', year: 'numeric' });
        }

        function parseCurrency(value) {
            const num = parseFloat(value);
            return Number.isFinite(num) ? num : 0;
        }

        async function loadTreatmentProcedures() {
            const response = await fetch('/api/treatment-procedures');
            treatmentProceduresCache = await response.json();
            if (!Array.isArray(treatmentProceduresCache)) {
                treatmentProceduresCache = [];
            }
        }

        function getProcedureById(idValue) {
            const id = parseInt(idValue, 10);
            if (!Number.isFinite(id)) return null;
            return treatmentProceduresCache.find(item => item.id === id) || null;
        }

        function updateFollowupProcedureUi() {
            const select = document.getElementById('followup-procedure-id');
            const customWrap = document.getElementById('followup-custom-procedure-wrap');
            const customInput = document.getElementById('followup-custom-procedure');
            const labExpenseInput = document.getElementById('followup-lab-expense');
            const requiresLabField = document.getElementById('followup-requires-lab');
            if (!select || !customWrap || !customInput || !labExpenseInput || !requiresLabField) return;

            const procedure = getProcedureById(select.value);
            const isCustom = String(select.value) === '';
            const requiresLab = Boolean(procedure && parseInt(procedure.requires_lab, 10) === 1);

            customWrap.style.display = isCustom ? 'block' : 'none';
            customInput.required = isCustom;

            labExpenseInput.disabled = !requiresLab;
            if (!requiresLab) {
                labExpenseInput.value = '0';
            } else if (parseCurrency(labExpenseInput.value) === 0 && procedure) {
                labExpenseInput.value = parseCurrency(procedure.default_lab_expense).toFixed(2);
            }

            requiresLabField.value = requiresLab ? '1' : '0';
        }

        function resetProcedureForm() {
            const idInput = document.getElementById('procedure-id');
            const nameInput = document.getElementById('procedure-name');
            const priceInput = document.getElementById('procedure-default-price');
            const labInput = document.getElementById('procedure-default-lab-expense');
            const requiresLabInput = document.getElementById('procedure-requires-lab');
            const activeInput = document.getElementById('procedure-active');
            const saveBtn = document.getElementById('procedure-save-btn');
            if (!idInput || !nameInput || !priceInput || !labInput || !requiresLabInput || !activeInput || !saveBtn) return;

            idInput.value = '';
            nameInput.value = '';
            priceInput.value = '0';
            labInput.value = '0';
            requiresLabInput.checked = false;
            activeInput.checked = true;
            saveBtn.textContent = t('save_procedure', 'Save Procedure');
        }

        function startEditProcedure(id) {
            const procedure = getProcedureById(id);
            if (!procedure) return;
            const idInput = document.getElementById('procedure-id');
            const nameInput = document.getElementById('procedure-name');
            const priceInput = document.getElementById('procedure-default-price');
            const labInput = document.getElementById('procedure-default-lab-expense');
            const requiresLabInput = document.getElementById('procedure-requires-lab');
            const activeInput = document.getElementById('procedure-active');
            const saveBtn = document.getElementById('procedure-save-btn');
            if (!idInput || !nameInput || !priceInput || !labInput || !requiresLabInput || !activeInput || !saveBtn) return;

            idInput.value = String(procedure.id);
            nameInput.value = procedure.name || '';
            priceInput.value = parseCurrency(procedure.default_price || 0).toFixed(2);
            labInput.value = parseCurrency(procedure.default_lab_expense || 0).toFixed(2);
            requiresLabInput.checked = parseInt(procedure.requires_lab, 10) === 1;
            activeInput.checked = parseInt(procedure.active, 10) === 1;
            saveBtn.textContent = t('edit_procedure', 'Edit');
        }

        function renderProcedureCatalogTable() {
            const tbody = document.getElementById('procedures-body');
            if (!tbody) return;

            if (!treatmentProceduresCache.length) {
                tbody.innerHTML = `<tr><td colspan="6">${t('no_data', 'No data')}</td></tr>`;
                return;
            }

            tbody.innerHTML = treatmentProceduresCache.map(item => {
                const requiresLabText = parseInt(item.requires_lab, 10) === 1 ? t('yes', 'Yes') : t('no', 'No');
                const activeText = parseInt(item.active, 10) === 1 ? t('yes', 'Yes') : t('no', 'No');
                return `
                    <tr>
                        <td>${item.name || ''}</td>
                        <td>${requiresLabText}</td>
                        <td>₪ ${parseCurrency(item.default_price).toFixed(2)}</td>
                        <td>₪ ${parseCurrency(item.default_lab_expense).toFixed(2)}</td>
                        <td>${activeText}</td>
                        <td><button class="btn btn-primary" type="button" onclick="startEditProcedure(${item.id})">${t('edit_procedure', 'Edit')}</button></td>
                    </tr>
                `;
            }).join('');
        }

        async function loadProcedureCatalog() {
            const section = document.getElementById('procedures-body');
            if (!section) return;
            const response = await fetch('/api/treatment-procedures?include_inactive=1');
            treatmentProceduresCache = await response.json();
            if (!Array.isArray(treatmentProceduresCache)) {
                treatmentProceduresCache = [];
            }
            renderProcedureCatalogTable();
        }

        // Tab switching
        function switchTab(tabName, clickedBtn = null) {
            const tabs = document.querySelectorAll('.tab-content');
            const navTabs = document.querySelectorAll('.nav-tab');
            
            tabs.forEach(tab => tab.classList.remove('active'));
            navTabs.forEach(navTab => navTab.classList.remove('active'));
            
            document.getElementById(tabName).classList.add('active');
            if (clickedBtn) {
                clickedBtn.classList.add('active');
            } else {
                const match = Array.from(navTabs).find(btn => btn.getAttribute('onclick')?.includes(`'${tabName}'`));
                if (match) match.classList.add('active');
            }
            
            // Load data for the active tab
            if (tabName === 'dashboard') loadDashboard();
            else if (tabName === 'patients') loadPatients();
            else if (tabName === 'appointments') loadAppointments();
            else if (tabName === 'reports') loadReportsSection();
            else if (tabName === 'financial') loadFinancialSection();
            else if (tabName === 'support') loadSupportSection();
        }

        function switchReportsSubTab(tabName, clickedBtn = null, shouldLoad = true) {
            const container = document.getElementById('reports');
            if (!container) return;

            currentReportsSubTab = tabName;
            localStorage.setItem('reports-subtab', tabName);

            container.querySelectorAll('#reports-sub-tabs .sub-tab').forEach(btn => btn.classList.remove('active'));
            container.querySelectorAll('.sub-tab-content[id^="reports-subtab-"]').forEach(panel => panel.classList.remove('active'));

            if (clickedBtn) {
                clickedBtn.classList.add('active');
            } else {
                const fallbackBtn = container.querySelector(`#reports-sub-tabs .sub-tab[onclick*="'${tabName}'"]`);
                if (fallbackBtn) fallbackBtn.classList.add('active');
            }

            const activePanel = document.getElementById(`reports-subtab-${tabName}`);
            if (activePanel) activePanel.classList.add('active');

            if (!shouldLoad) return;
            if (tabName === 'weekly') loadWeeklyReport();
            else if (tabName === 'monthly') loadMonthlyReport();
            else if (tabName === 'lab') loadLabReport();
        }

        function switchFinancialSubTab(tabName, clickedBtn = null, shouldLoad = true) {
            const container = document.getElementById('financial');
            if (!container) return;

            currentFinancialSubTab = tabName;
            localStorage.setItem('financial-subtab', tabName);

            container.querySelectorAll('#financial-sub-tabs .sub-tab').forEach(btn => btn.classList.remove('active'));
            container.querySelectorAll('.sub-tab-content[id^="financial-subtab-"]').forEach(panel => panel.classList.remove('active'));

            if (clickedBtn) {
                clickedBtn.classList.add('active');
            } else {
                const fallbackBtn = container.querySelector(`#financial-sub-tabs .sub-tab[onclick*="'${tabName}'"]`);
                if (fallbackBtn) fallbackBtn.classList.add('active');
            }

            const activePanel = document.getElementById(`financial-subtab-${tabName}`);
            if (activePanel) activePanel.classList.add('active');

            if (!shouldLoad) return;
            if (tabName === 'management') {
                loadReceivables();
                loadExpenses();
            } else if (tabName === 'billing') {
                loadBilling();
            } else if (tabName === 'invoices') {
                loadPatientsSelect('invoice-patient-select');
            }
        }

        function handleProcedureCatalogToggle(detailsElement) {
            if (detailsElement && detailsElement.open) {
                loadProcedureCatalog();
            }
        }

        let treatmentCatalogCache = [];
        async function loadTreatmentCatalogUI() {
            const rows = await fetch('/api/treatment-catalog?include_inactive=1').then(r => r.json()).catch(() => []);
            treatmentCatalogCache = Array.isArray(rows) ? rows : [];
            const tbody = document.getElementById('treatment-catalog-body');
            if (!tbody) return;
            if (!treatmentCatalogCache.length) {
                tbody.innerHTML = '<tr><td colspan="5">لا توجد بيانات</td></tr>';
                return;
            }
            tbody.innerHTML = treatmentCatalogCache.map(item => `
                <tr>
                    <td>${item.name_ar || ''}</td>
                    <td>${item.name_en || ''}</td>
                    <td>₪${parseFloat(item.default_price||0).toFixed(2)}</td>
                    <td>${item.is_active ? '✓ نشط' : '✗ معطل'}</td>
                    <td>
                        <button class="btn btn-primary btn-sm" onclick="editTreatmentCatalog(${item.id})">تعديل</button>
                        <button class="btn btn-warning btn-sm" onclick="toggleTreatmentCatalog(${item.id},${item.is_active})">${item.is_active?'تعطيل':'تفعيل'}</button>
                    </td>
                </tr>
            `).join('');
        }
        function resetTreatmentCatalogForm() {
            document.getElementById('tc-id').value = '';
            document.getElementById('tc-name-ar').value = '';
            document.getElementById('tc-name-en').value = '';
            document.getElementById('tc-price').value = '0';
        }
        function editTreatmentCatalog(id) {
            const item = treatmentCatalogCache.find(x => Number(x.id) === Number(id));
            if (!item) return;
            document.getElementById('tc-id').value = item.id;
            document.getElementById('tc-name-ar').value = item.name_ar || '';
            document.getElementById('tc-name-en').value = item.name_en || '';
            document.getElementById('tc-price').value = parseFloat(item.default_price||0).toFixed(2);
        }
        async function toggleTreatmentCatalog(id, currentActive) {
            await fetch(`/api/treatment-catalog/${id}`, {
                method: 'PUT',
                headers: {'Content-Type':'application/json'},
                body: JSON.stringify({is_active: currentActive ? 0 : 1})
            });
            loadTreatmentCatalogUI();
        }
        document.addEventListener('DOMContentLoaded', function() {
            const tcForm = document.getElementById('treatment-catalog-form');
            if (tcForm) {
                tcForm.addEventListener('submit', async function(e) {
                    e.preventDefault();
                    const idVal = document.getElementById('tc-id').value.trim();
                    const payload = {
                        name_ar: document.getElementById('tc-name-ar').value.trim(),
                        name_en: document.getElementById('tc-name-en').value.trim(),
                        default_price: parseFloat(document.getElementById('tc-price').value || 0)
                    };
                    if (!payload.name_ar) { alert('الاسم بالعربية مطلوب'); return; }
                    const url = idVal ? `/api/treatment-catalog/${idVal}` : '/api/treatment-catalog';
                    const method = idVal ? 'PUT' : 'POST';
                    const resp = await fetch(url, {method, headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)});
                    if (resp.ok) {
                        resetTreatmentCatalogForm();
                        loadTreatmentCatalogUI();
                    } else {
                        alert('فشل الحفظ');
                    }
                });
            }
        });

        // Quick sidebar collapse behavior: click the small "Navigation" label to toggle
        document.addEventListener('DOMContentLoaded', function() {
            const navLabel = document.querySelector('.nav-tabs-label');
            if (navLabel) {
                navLabel.style.cursor = 'pointer';
                navLabel.title = 'Toggle navigation';
                navLabel.addEventListener('click', () => document.body.classList.toggle('sidebar-collapsed'));
            }
            // Auto-collapse on narrower screens
            function updateSidebarOnResize() {
                if (window.innerWidth <= 980) document.body.classList.add('sidebar-collapsed');
                else document.body.classList.remove('sidebar-collapsed');
            }
            updateSidebarOnResize();
            window.addEventListener('resize', updateSidebarOnResize);
        });

        // Modal functions
        
        function showDatePickerForPatient() {
            showCalendarPickerModal((selectedDate) => {
                const dateInput = document.querySelector('#add-patient-form input[name="date_of_birth"]');
                if (dateInput && selectedDate) {
                    dateInput.value = selectedDate;
                }
            });
        }

        function showCalendarPickerModal(onDateSelect) {
            if (!document.getElementById('date-picker-modal')) {
                const modal = document.createElement('div');
                modal.id = 'date-picker-modal';
                modal.className = 'date-picker-modal';
                modal.innerHTML = `
                    <div class="date-picker-modal-content">
                        <div class="date-picker-modal-header">
                            <button type="button" onclick="changePickerMonth(-1)">❮</button>
                            <div class="date-picker-modal-month" id="picker-month-label"></div>
                            <button type="button" onclick="changePickerMonth(1)">❯</button>
                        </div>
                        <div id="picker-calendar-grid" class="date-picker-grid"></div>
                        <div style="display: flex; gap: 8px; margin-top: 16px;">
                            <button class="btn btn-warning" type="button" onclick="closePickerModal()">Cancel</button>
                            <button class="btn btn-primary" type="button" onclick="selectTodayInPicker()">Today</button>
                        </div>
                    </div>
                </div>
                `;
                document.body.appendChild(modal);
                modal.addEventListener('click', (e) => {
                    if (e.target === modal) closePickerModal();
                });
            }
            window.datePickerCallback = onDateSelect;
            window.pickerDate = new Date();
            renderPickerCalendar();
            document.getElementById('date-picker-modal').classList.add('active');
        }

        function renderPickerCalendar() {
            const year = window.pickerDate.getFullYear();
            const month = window.pickerDate.getMonth();
            const firstDay = new Date(year, month, 1);
            const startDay = firstDay.getDay();
            const daysInMonth = new Date(year, month + 1, 0).getDate();
            const monthLabelEl = document.getElementById('picker-month-label');
            const today = new Date();
            const locale = currentLanguage === 'ar' ? 'ar-EG' : 'en-US';
            const monthStr = window.pickerDate.toLocaleDateString(locale, { month: 'long', year: 'numeric' });
            monthLabelEl.textContent = monthStr;
            const dayNames = currentLanguage === 'ar'
                ? ['الأحد', 'الإثنين', 'الثلاثاء', 'الأربعاء', 'الخميس', 'الجمعة', 'السبت']
                : ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
            const gridEl = document.getElementById('picker-calendar-grid');
            gridEl.innerHTML = dayNames.map(d => `<div class="date-picker-day-name">${d}</div>`).join('') +
                Array.from({length: startDay}, () => '<div class="date-picker-day empty"></div>').join('') +
                Array.from({length: daysInMonth}, (_, i) => {
                    const day = i + 1;
                    const dateStr = `${String(day).padStart(2, '0')}/${String(month + 1).padStart(2, '0')}/${year}`;
                    const isToday = today.getFullYear() === year && today.getMonth() === month && today.getDate() === day;
                    const todayClass = isToday ? 'today' : '';
                    return `<div class="date-picker-day ${todayClass}" onclick="selectPickerDate('${dateStr}')">${day}</div>`;
                }).join('');
        }

        function changePickerMonth(offset) {
            if (!window.pickerDate) window.pickerDate = new Date();
            window.pickerDate = new Date(window.pickerDate.getFullYear(), window.pickerDate.getMonth() + offset, 1);
            renderPickerCalendar();
        }

        function selectPickerDate(dateStr) {
            if (window.datePickerCallback) {
                window.datePickerCallback(dateStr);
            }
            closePickerModal();
        }

        function selectTodayInPicker() {
            const today = new Date();
            const day = String(today.getDate()).padStart(2, '0');
            const month = String(today.getMonth() + 1).padStart(2, '0');
            const year = today.getFullYear();
            selectPickerDate(`${day}/${month}/${year}`);
        }

        function closePickerModal() {
            const modal = document.getElementById('date-picker-modal');
            if (modal) modal.classList.remove('active');
        }

        function showAddPatientModal() {
            document.getElementById('add-patient-modal').classList.add('active');
        }
        
        async function showAddAppointmentModal(patientId = null, preferredDate = null) {
            await loadPatientsSelect('appointment-patient-select');
            const patientSelect = document.getElementById('appointment-patient-select');
            if (patientId) {
                patientSelect.value = String(patientId);
            }
            const dateInput = document.querySelector('#add-appointment-form [name="appointment_date"]');
            if (dateInput) {
                if (preferredDate) {
                    const parsedPreferred = new Date(String(preferredDate).replace(' ', 'T'));
                    if (!Number.isNaN(parsedPreferred.getTime()) && parsedPreferred.getDay() === 5) {
                        parsedPreferred.setDate(parsedPreferred.getDate() + 1);
                    }
                    dateInput.value = toDatetimeLocalValue(parsedPreferred);
                } else if (!dateInput.value) {
                    const defaultDate = new Date(Date.now() + 60 * 60 * 1000);
                    if (defaultDate.getDay() === 5) {
                        defaultDate.setDate(defaultDate.getDate() + 1);
                    }
                    dateInput.value = toDatetimeLocalValue(defaultDate);
                }
                if (isFridayDateTimeValue(dateInput.value)) {
                    const adjustedDate = new Date(String(dateInput.value).replace(' ', 'T'));
                    adjustedDate.setDate(adjustedDate.getDate() + 1);
                    dateInput.value = toDatetimeLocalValue(adjustedDate);
                }
            }
            document.getElementById('add-appointment-modal').classList.add('active');
        }

        function closeModal(modalId) {
            document.getElementById(modalId).classList.remove('active');
        }

        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape') {
                document.querySelectorAll('.modal.active').forEach(m => m.classList.remove('active'));
            }
        });

        // Load patients into select dropdown
        async function loadPatientsSelect(selectId) {
            const response = await fetch('/api/patients');
            const patients = await response.json();
            const select = document.getElementById(selectId);
            select.innerHTML = `<option value="">${t('select_patient', 'Select Patient')}</option>`;
            patients.forEach(patient => {
                select.innerHTML += `<option value="${patient.id}">${patient.first_name} ${patient.last_name}</option>`;
            });
        }
        
        // Dashboard
        async function loadDashboard() {
            const stats = await fetch('/api/stats').then(r => r.json());
            document.getElementById('total-patients').textContent = stats.total_patients;
            document.getElementById('today-appointments').textContent = stats.today_appointments;
            const visitsEl = document.getElementById('total-visits');
            if (visitsEl) visitsEl.textContent = stats.total_visits ?? 0;
            const revenueEl = document.getElementById('total-revenue');
            if (revenueEl) revenueEl.textContent = '₪ ' + (parseFloat(stats.total_revenue) || 0).toLocaleString('en-US', {minimumFractionDigits: 0, maximumFractionDigits: 0});
            
            const appointments = await fetch('/api/appointments/recent').then(r => r.json());
            const tbody = document.getElementById('recent-appointments-body');
            tbody.innerHTML = appointments.map(apt => `
                <tr>
                    <td>${apt.patient_name}</td>
                    <td>${formatApptDate(apt.appointment_date)}</td>
                    <td>${apt.treatment_type || t('no_data', 'No data')}</td>
                    <td><span class="badge badge-${apt.status === 'completed' ? 'success' : apt.status === 'scheduled' ? 'info' : 'warning'}">${apt.status}</span></td>
                </tr>
            `).join('');
        }
        
        // Patients
        async function loadPatients() {
            const patients = await fetch('/api/patients').then(r => r.json());
            patientsCache = patients;
            renderPatientsTable(patientsCache);
        }

        function renderPatientsTable(patients) {
            const tbody = document.getElementById('patients-body');
            tbody.innerHTML = patients.map(patient => `
                <tr>
                    <td>${patient.id}</td>
                    <td><a href="#" onclick="viewPatientProfile(${patient.id}); return false;">${patient.first_name} ${patient.last_name}</a></td>
                    <td>${formatDateDisplay(patient.date_of_birth) || t('no_data', 'No data')}</td>
                    <td>${patient.phone || t('no_data', 'No data')}</td>
                    <td>${patient.email || t('no_data', 'No data')}</td>
                    <td>
                        <div class="action-buttons">
                            <button class="btn btn-primary" onclick="viewPatientProfile(${patient.id})">${t('view', 'View')}</button>
                            <button class="btn btn-success" onclick="showAddAppointmentModal(${patient.id})">${t('book', 'Book')}</button>
                            <button class="btn btn-warning" onclick="deletePatient(${patient.id})">${t('delete', 'Delete')}</button>
                        </div>
                    </td>
                </tr>
            `).join('');

            const status = document.getElementById('patient-search-status');
            if (status) {
                status.textContent = t('showing_n_patients', 'Showing {count} patient(s).').replace('{count}', patients.length);
            }
        }

        function filterPatientsTable() {
            const query = (document.getElementById('patient-search-input')?.value || '').trim().toLowerCase();
            if (!query) {
                renderPatientsTable(patientsCache);
                return;
            }

            const filtered = patientsCache.filter(patient => {
                const fullName = `${patient.first_name || ''} ${patient.last_name || ''}`.toLowerCase();
                return fullName.includes(query)
                    || String(patient.phone || '').toLowerCase().includes(query)
                    || String(patient.email || '').toLowerCase().includes(query);
            });
            renderPatientsTable(filtered);
        }

        function openFirstPatientMatch() {
            const query = (document.getElementById('patient-search-input')?.value || '').trim().toLowerCase();
            if (!query) {
                alert(t('select_patient_first', 'Please type a patient name first.'));
                return;
            }

            const match = patientsCache.find(patient => {
                const fullName = `${patient.first_name || ''} ${patient.last_name || ''}`.toLowerCase();
                return fullName.includes(query)
                    || String(patient.phone || '').toLowerCase().includes(query)
                    || String(patient.email || '').toLowerCase().includes(query);
            });

            if (!match) {
                alert(t('no_patient_match', 'No patient matched your search.'));
                return;
            }

            viewPatientProfile(match.id);
        }

        function clearPatientSearch() {
            const input = document.getElementById('patient-search-input');
            if (input) input.value = '';
            renderPatientsTable(patientsCache);
        }
        
        // Appointments
        async function loadAppointments() {
            const appointments = await fetch('/api/appointments').then(r => r.json());
            appointmentsCache = appointments;
            holidaysCache = await fetch('/api/holidays').then(r => r.json());
            renderAppointmentsCalendar(appointmentsCache);
            renderHolidaysTable();
            const tbody = document.getElementById('appointments-body');
            tbody.innerHTML = appointments.map(apt => `
                <tr>
                    <td>${apt.id}</td>
                    <td><a href="#" onclick="viewPatientProfile(${apt.patient_id}); return false;">${apt.patient_name}</a></td>
                    <td>${formatApptDate(apt.appointment_date)}</td>
                    <td>${apt.duration} ${t('min', 'min')}</td>
                    <td>${apt.treatment_type || t('no_data', 'No data')}</td>
                    <td><span class="badge badge-${apt.status === 'completed' ? 'success' : apt.status === 'scheduled' ? 'info' : 'warning'}">${apt.status}</span></td>
                </tr>
            `).join('');
        }

        function renderAppointmentsCalendar(appointments) {
            const calendar = document.getElementById('appointments-calendar');
            if (!calendar) return;
            const year = currentCalendarDate.getFullYear();
            const month = currentCalendarDate.getMonth();
            const firstDay = new Date(year, month, 1);
            const startDay = firstDay.getDay();
            const daysInMonth = new Date(year, month + 1, 0).getDate();
            const monthLabelElement = document.getElementById('calendar-month-label');
            if (monthLabelElement) {
                monthLabelElement.textContent = monthLabel(currentCalendarDate);
            }

            const grouped = {};
            appointments.forEach(apt => {
                const d = new Date(apt.appointment_date);
                if (d.getFullYear() === year && d.getMonth() === month) {
                    const key = d.getDate();
                    grouped[key] = grouped[key] || [];
                    grouped[key].push(apt);
                }
            });
            
            // Sort appointments within each day by time
            Object.keys(grouped).forEach(day => {
                grouped[day].sort((a, b) => new Date(a.appointment_date) - new Date(b.appointment_date));
            });
            
            // Create a set of holiday dates for this month
            const holidaySet = new Set();
            holidaysCache.forEach(holiday => {
                const hDate = new Date(holiday.holiday_date);
                if (hDate.getFullYear() === year && hDate.getMonth() === month) {
                    holidaySet.add(hDate.getDate());
                }
            });
            
            const dayNames = currentLanguage === 'ar'
                ? ['الأحد', 'الإثنين', 'الثلاثاء', 'الأربعاء', 'الخميس', 'الجمعة', 'السبت']
                : ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
            calendar.innerHTML = dayNames.map(d => `<div class="calendar-day-header">${d}</div>`).join('') + Array.from({length: startDay}, () => '<div></div>').join('') + Array.from({length: daysInMonth}, (_, i) => {
                const day = i + 1;
                const isFriday = new Date(year, month, day).getDay() === 5;
                const isHoliday = isFriday || holidaySet.has(day);
                const holidayMarker = isHoliday ? `<div style="font-size:9px;color:#da4c58;font-weight:700;margin-bottom:3px;">🏖️ ${t('holiday_label', 'Holiday')}</div>` : '';
                const items = (grouped[day] || []).slice(0, 3).map(apt => {
                    const aptTime = new Date(apt.appointment_date).toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'});
                    return `<div class="calendar-event"><a href="#" class="calendar-patient-link" data-patient-id="${apt.patient_id}">${apt.patient_name}</a><br>${aptTime} · ${apt.treatment_type || t('visit_label', 'Visit')}</div>`;
                }).join('');
                const clickableClass = isHoliday ? 'cursor-not-allowed' : 'cursor-pointer';
                const dateStr = `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
                const dayDataAttr = isHoliday ? '' : `data-date="${dateStr}"`;
                return `<div class="calendar-day-cell ${clickableClass}" ${dayDataAttr}><div class="calendar-day-number">${day}</div>${holidayMarker}${items || `<div class="calendar-empty">${t('no_appointments_for_day', 'No appointments')}</div>`}</div>`;
            }).join('');

            if (!calendar.dataset.boundClicks) {
                calendar.addEventListener('click', (e) => {
                    const patientLink = e.target.closest('.calendar-patient-link');
                    if (patientLink) {
                        e.preventDefault();
                        e.stopPropagation();
                        const patientId = parseInt(patientLink.dataset.patientId, 10);
                        if (Number.isFinite(patientId)) viewPatientProfile(patientId);
                        return;
                    }

                    const dayCell = e.target.closest('.calendar-day-cell[data-date]');
                    if (!dayCell) return;
                    scheduleFromCalendarDate(dayCell.dataset.date);
                });
                calendar.dataset.boundClicks = '1';
            }
        }

        function scheduleFromCalendarDate(dateStr) {
            const datetimeLocal = dateStr + 'T09:00';
            showAddAppointmentModal(null, datetimeLocal);
        }

        function renderHolidaysTable() {
            const tbody = document.getElementById('holidays-body');
            if (!tbody) return;
            if (!holidaysCache.length) {
                tbody.innerHTML = `<tr><td colspan="4">${t('no_holidays_yet', 'No holidays yet')}</td></tr>`;
                return;
            }
            tbody.innerHTML = holidaysCache
                .slice()
                .sort((a, b) => String(a.holiday_date).localeCompare(String(b.holiday_date)))
                .map(item => `
                    <tr>
                        <td>${item.holiday_date || ''}</td>
                        <td>${item.name || ''}</td>
                        <td>${item.notes || ''}</td>
                        <td><button class="btn btn-danger" onclick="deleteHoliday(${item.id})">${t('delete', 'Delete')}</button></td>
                    </tr>
                `).join('');
        }

        async function deleteHoliday(id) {
            if (!confirm(t('delete_holiday_confirm', 'Delete this holiday?'))) return;
            await fetch(`/api/holidays/${id}`, { method: 'DELETE' });
            await loadAppointments();
        }

        function changeCalendarMonth(offset) {
            currentCalendarDate = new Date(currentCalendarDate.getFullYear(), currentCalendarDate.getMonth() + offset, 1);
            renderAppointmentsCalendar(appointmentsCache);
        }

        function goToCurrentCalendarMonth() {
            currentCalendarDate = new Date();
            renderAppointmentsCalendar(appointmentsCache);
        }

        function loadAppointmentsCalendar() {
            loadAppointments();
        }

        function getWeekBounds(baseDate = new Date()) {
            const d = new Date(baseDate);
            d.setHours(0, 0, 0, 0);
            const day = d.getDay();
            const diffToMonday = (day + 6) % 7;
            const weekStart = new Date(d);
            weekStart.setDate(d.getDate() - diffToMonday);
            const weekEnd = new Date(weekStart);
            weekEnd.setDate(weekStart.getDate() + 6);
            const toIsoDate = (dateObj) => dateObj.toISOString().slice(0, 10);
            return {
                startDate: toIsoDate(weekStart),
                endDate: toIsoDate(weekEnd)
            };
        }

        async function loadReports(startDateOverride = null, endDateOverride = null) {
            const startDate = startDateOverride ?? document.getElementById('report-start-date').value;
            const endDate = endDateOverride ?? document.getElementById('report-end-date').value;
            const params = new URLSearchParams();
            if (startDate) params.set('start_date', startDate);
            if (endDate) params.set('end_date', endDate);
            const report = await fetch(`/api/reports/summary?${params.toString()}`).then(r => r.json());
            document.getElementById('report-visits').textContent = report.visits;
            const reportRevenue = parseCurrency(report.revenue);
            const reportExpenses = parseCurrency(report.expenses);
            const reportLabExpenses = parseCurrency(report.lab_expenses);
            const reportClinicGrossProfit = parseCurrency(report.clinic_gross_profit);
            const reportProfit = parseCurrency(report.profit);
            document.getElementById('report-revenue').textContent = '₪ ' + reportRevenue.toFixed(2);
            document.getElementById('report-expenses').textContent = '₪ ' + reportExpenses.toFixed(2);
            document.getElementById('report-lab-expenses').textContent = '₪ ' + reportLabExpenses.toFixed(2);
            document.getElementById('report-clinic-gross-profit').textContent = '₪ ' + reportClinicGrossProfit.toFixed(2);
            document.getElementById('report-profit').textContent = '₪ ' + reportProfit.toFixed(2);

            const rangeText = startDate && endDate
                ? `${t('range', 'Range')}: ${formatDateDisplay(startDate)} - ${formatDateDisplay(endDate)}`
                : `${t('range', 'Range')}: ${t('full_period', 'full period')}`;
            document.getElementById('weekly-report-range').textContent = rangeText;
        }

        async function loadWeeklyReportFromPicker() {
            const pickerVal = document.getElementById('weekly-start-picker')?.value;
            const baseDate = pickerVal ? new Date(pickerVal + 'T00:00:00') : new Date();
            const { startDate, endDate } = getWeekBounds(baseDate);
            await _doLoadWeeklyReport(startDate, endDate);
        }

        async function loadWeeklyReport() {
            const { startDate, endDate } = getWeekBounds(new Date());
            await _doLoadWeeklyReport(startDate, endDate);
        }

        async function _doLoadWeeklyReport(startDate, endDate) {
            const weekly = await fetch(`/api/reports/weekly?week_start=${encodeURIComponent(startDate)}`).then(r => r.json());
            document.getElementById('report-visits').textContent = weekly.session_count ?? weekly.visits ?? 0;
            const weeklyRevenue = parseCurrency(weekly.revenue);
            const weeklyExpenses = parseCurrency(weekly.expenses);
            const weeklyLabExpenses = parseCurrency(weekly.lab_expenses);
            const weeklyClinicGrossProfit = parseCurrency(weekly.clinic_gross_profit);
            const weeklyProfit = parseCurrency(weekly.profit);
            document.getElementById('report-revenue').textContent = '₪ ' + weeklyRevenue.toFixed(2);
            document.getElementById('report-expenses').textContent = '₪ ' + weeklyExpenses.toFixed(2);
            document.getElementById('report-lab-expenses').textContent = '₪ ' + weeklyLabExpenses.toFixed(2);
            document.getElementById('report-clinic-gross-profit').textContent = '₪ ' + weeklyClinicGrossProfit.toFixed(2);
            document.getElementById('report-profit').textContent = '₪ ' + weeklyProfit.toFixed(2);
            document.getElementById('weekly-report-range').textContent = t('weekly_range_text', 'Weekly range: {start} to {end}')
                .replace('{start}', weekly.week_start_display || weekly.week_start)
                .replace('{end}', weekly.week_end_display || weekly.week_end);
        }

        async function loadMonthlyReport() {
            const monthInput = document.getElementById('report-month-picker');
            const monthValue = monthInput?.value || new Date().toISOString().slice(0, 7);
            if (monthInput && !monthInput.value) monthInput.value = monthValue;

            const [yearStr, monthStr] = monthValue.split('-');
            const year = parseInt(yearStr, 10);
            const month = parseInt(monthStr, 10);
            if (!Number.isFinite(year) || !Number.isFinite(month)) return;

            const monthStart = `${yearStr}-${String(month).padStart(2, '0')}-01`;
            const monthEndDate = new Date(year, month, 0);
            const monthEnd = `${yearStr}-${String(month).padStart(2, '0')}-${String(monthEndDate.getDate()).padStart(2, '0')}`;
            await loadReports(monthStart, monthEnd);
        }

        async function loadLabReport() {
            const startInput = document.getElementById('report-start-date');
            const endInput = document.getElementById('report-end-date');
            const today = new Date();
            const defaultStart = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-01`;
            const defaultEnd = today.toISOString().slice(0, 10);

            const startDate = startInput?.value || defaultStart;
            const endDate = endInput?.value || defaultEnd;
            if (startInput && !startInput.value) startInput.value = startDate;
            if (endInput && !endInput.value) endInput.value = endDate;

            await loadReports(startDate, endDate);
        }

        async function loadReportsSection() {
            switchReportsSubTab(currentReportsSubTab, null, false);
            if (currentReportsSubTab === 'weekly') {
                await loadWeeklyReport();
            } else if (currentReportsSubTab === 'monthly') {
                await loadMonthlyReport();
            } else {
                await loadLabReport();
            }

            const procedurePanel = document.getElementById('procedure-catalog-panel');
            if (procedurePanel?.open) {
                await loadProcedureCatalog();
            }
        }

        async function loadFinancialSection() {
            switchFinancialSubTab(currentFinancialSubTab, null, false);
            if (currentFinancialSubTab === 'management') {
                await loadReceivables();
                await loadExpenses();
            } else if (currentFinancialSubTab === 'billing') {
                await loadBilling();
            } else {
                await loadPatientsSelect('invoice-patient-select');
            }
        }

        async function loadSupportSection() {
            await loadSupportTips();
            await loadAuditLogs();
        }

        async function loadReceivables() {
            const payload = await fetch('/api/reports/receivables').then(r => r.json());
            const total = parseCurrency(payload.total_receivables || 0);
            const count = parseInt(payload.count || 0, 10);
            const rows = Array.isArray(payload.rows) ? payload.rows : [];

            const totalEl = document.getElementById('receivables-total');
            const countEl = document.getElementById('receivables-count');
            const tbody = document.getElementById('receivables-body');
            if (!totalEl || !countEl || !tbody) return;

            totalEl.textContent = `₪ ${total.toFixed(2)}`;
            countEl.textContent = String(Number.isFinite(count) ? count : 0);

            if (!rows.length) {
                tbody.innerHTML = `<tr><td colspan="6">${t('no_receivables', 'No receivables found.')}</td></tr>`;
                return;
            }

            tbody.innerHTML = rows.map(item => `
                <tr>
                    <td>${item.patient_name || ''}</td>
                    <td>₪ ${parseCurrency(item.total_to_pay).toFixed(2)}</td>
                    <td>₪ ${parseCurrency(item.total_paid).toFixed(2)}</td>
                    <td>₪ ${parseCurrency(item.outstanding).toFixed(2)}</td>
                    <td>${formatDateDisplay(item.last_followup_date) || ''}</td>
                    <td>${parseInt(item.overdue_days || 0, 10)}</td>
                </tr>
            `).join('');
        }

        async function loadBilling() {
            await loadPatientsSelect('billing-patient-select');
            await loadPatientsSelect('invoice-patient-select');

            const items = await fetch('/api/billing').then(r => r.json());
            billingCache = Array.isArray(items) ? items : [];
            const tbody = document.getElementById('billing-body');
            if (!tbody) return;

            if (!billingCache.length) {
                tbody.innerHTML = `<tr><td colspan="8">${t('no_data', 'No data')}</td></tr>`;
                return;
            }

            tbody.innerHTML = billingCache.map(item => `
                <tr>
                    <td>${item.invoice_number || ''}</td>
                    <td>${item.patient_name || ''}</td>
                    <td>₪ ${parseCurrency(item.amount).toFixed(2)}</td>
                    <td>₪ ${parseCurrency(item.paid_amount).toFixed(2)}</td>
                    <td>₪ ${parseCurrency(item.balance_due).toFixed(2)}</td>
                    <td>${item.payment_status || ''}</td>
                    <td>${formatDateDisplay(item.payment_date) || ''}</td>
                    <td>
                        <button class="btn btn-primary" onclick="printBillingInvoice(${item.id})">${t('print_invoice', 'Print Invoice')}</button>
                        <button class="btn btn-danger" onclick="deleteBillingRecord(${item.id})">${t('delete', 'Delete')}</button>
                    </td>
                </tr>
            `).join('');
        }

        async function deleteBillingRecord(id) {
            if (!confirm(t('confirm_delete', 'Are you sure you want to delete?'))) return;
            const resp = await fetch(`/api/billing/${id}`, { method: 'DELETE' });
            if (!resp.ok) { alert('Delete failed'); return; }
            loadBilling();
            loadAuditLogs();
        }

        async function loadPatientInvoiceSummary() {
            const patientId = document.getElementById('invoice-patient-select')?.value;
            const startDate = document.getElementById('invoice-start-date')?.value || '';
            const endDate = document.getElementById('invoice-end-date')?.value || '';
            const tbody = document.getElementById('patient-invoice-body');
            if (!tbody) return;
            if (!patientId) {
                currentPatientInvoicePayload = null;
                tbody.innerHTML = `<tr><td colspan="5">${t('select_patient', 'Select Patient')}</td></tr>`;
                return;
            }

            const params = new URLSearchParams();
            if (startDate) params.set('start_date', startDate);
            if (endDate) params.set('end_date', endDate);
            const payload = await fetch(`/api/patients/${patientId}/invoice-summary?${params.toString()}`).then(r => r.json());
            currentPatientInvoicePayload = payload;
            const items = payload.items || [];
            const totals = payload.totals || {};

            document.getElementById('invoice-total-to-pay').textContent = `₪ ${parseCurrency(totals.total_to_pay).toFixed(2)}`;
            document.getElementById('invoice-total-paid').textContent = `₪ ${parseCurrency(totals.total_paid).toFixed(2)}`;
            document.getElementById('invoice-total-left').textContent = `₪ ${parseCurrency(totals.total_left).toFixed(2)}`;

            if (!items.length) {
                tbody.innerHTML = `<tr><td colspan="5">${t('no_data', 'No data')}</td></tr>`;
                return;
            }

            tbody.innerHTML = items.map(item => `
                <tr>
                    <td>${item.followup_date || ''}</td>
                    <td>${item.treatment_procedure || ''}</td>
                    <td>₪ ${parseCurrency(item.price).toFixed(2)}</td>
                    <td>₪ ${parseCurrency(item.payment).toFixed(2)}</td>
                    <td>₪ ${parseCurrency(item.remaining_amount).toFixed(2)}</td>
                </tr>
            `).join('');
        }

        function openPrintWindow(html) {
            const printWindow = window.open('', '_blank', 'width=900,height=700');
            if (!printWindow) return;
            printWindow.document.write(html);
            printWindow.document.close();
            printWindow.focus();
            printWindow.print();
        }

        function invoiceDocumentTemplate({ title, subtitle, rows, totals, lang = 'en' }) {
            const printLang = lang === 'ar' ? 'ar' : 'en';
            const printDir = printLang === 'ar' ? 'rtl' : 'ltr';
            const totalToPay = parseCurrency(totals?.total_to_pay);
            const totalPaid = parseCurrency(totals?.total_paid);
            const totalLeft = parseCurrency(totals?.total_left);
            return `
<!DOCTYPE html>
<html lang="${printLang}" dir="${printDir}">
<head>
    <meta charset="UTF-8">
    <title>${title}</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 24px; color: #222; direction: ${printDir}; text-align: ${printDir === 'rtl' ? 'right' : 'left'}; }
        h1 { margin: 0 0 6px 0; font-size: 24px; }
        .sub { margin: 0 0 16px 0; color: #555; }
        table { width: 100%; border-collapse: collapse; margin-top: 12px; }
        th, td { border: 1px solid #ddd; padding: 8px; text-align: ${printDir === 'rtl' ? 'right' : 'left'}; }
        th { background: #f3f3f3; }
        .totals { margin-top: 16px; display: flex; gap: 16px; }
        .total-card { border: 1px solid #ddd; border-radius: 8px; padding: 10px 12px; min-width: 140px; }
    </style>
</head>
<body>
    <h1>${title}</h1>
    <p class="sub">${subtitle || ''}</p>
    <table>
        <thead>
            <tr>
                <th>${tForLang(printLang, 'date', 'Date')}</th>
                <th>${tForLang(printLang, 'description', 'Description')}</th>
                <th>${tForLang(printLang, 'amount', 'Amount')}</th>
                <th>${tForLang(printLang, 'paid', 'Paid')}</th>
                <th>${tForLang(printLang, 'balance', 'Balance')}</th>
            </tr>
        </thead>
        <tbody>
            ${rows}
        </tbody>
    </table>
    <div class="totals">
        <div class="total-card">${tForLang(printLang, 'total_to_pay', 'Total to Pay')}: ₪ ${totalToPay.toFixed(2)}</div>
        <div class="total-card">${tForLang(printLang, 'paid', 'Paid')}: ₪ ${totalPaid.toFixed(2)}</div>
        <div class="total-card">${tForLang(printLang, 'left', 'Left')}: ₪ ${totalLeft.toFixed(2)}</div>
    </div>
</body>
</html>
            `;
        }

        function printBillingInvoice(billingId) {
            const printLang = getInvoicePrintLanguage();
            const lang = printLang === 'ar' ? 'ar' : 'en';
            window.open(`/invoice/${billingId}?lang=${lang}`, '_blank');
        }

        function printInvoicePayload(payload) {
            if (!payload || !Array.isArray(payload.items)) {
                alert(t('invoice_preview_unavailable', 'No invoice data to print yet.'));
                return;
            }

            const printLang = getInvoicePrintLanguage();

            const rows = payload.items.length
                ? payload.items.map(item => `
                    <tr>
                        <td>${item.followup_date || ''}</td>
                        <td>${item.treatment_procedure || ''}</td>
                        <td>₪ ${parseCurrency(item.price).toFixed(2)}</td>
                        <td>₪ ${parseCurrency(item.payment).toFixed(2)}</td>
                        <td>₪ ${parseCurrency(item.remaining_amount).toFixed(2)}</td>
                    </tr>
                `).join('')
                : `<tr><td colspan="5">${tForLang(printLang, 'no_data', 'No data')}</td></tr>`;

            const patientName = payload.patient?.name || '';
            const phone = payload.patient?.phone || '';
            const doctorName = getDoctorNameForLanguage(printLang);
            const subtitle = `${tForLang(printLang, 'patient', 'Patient')}: ${patientName}${phone ? ` | ${tForLang(printLang, 'phone', 'Phone')}: ${phone}` : ''} | ${doctorName}`;
            const html = invoiceDocumentTemplate({
                title: tForLang(printLang, 'print_invoice', 'Print Invoice'),
                subtitle,
                rows,
                totals: payload.totals || {},
                lang: printLang
            });
            openPrintWindow(html);
        }

        function printCurrentPatientInvoice() {
            printInvoicePayload(currentPatientInvoicePayload);
        }

        async function printPatientInvoiceById(patientId) {
            const params = new URLSearchParams();
            const payload = await fetch(`/api/patients/${patientId}/invoice-summary?${params.toString()}`).then(r => r.json());
            printInvoicePayload(payload);
        }

        async function loadAuditLogs() {
            const items = await fetch('/api/audit-logs?limit=200').then(r => r.json());
            const tbody = document.getElementById('audit-logs-body');
            if (!tbody) return;

            if (!items || !items.length) {
                tbody.innerHTML = `<tr><td colspan="5">${t('no_data', 'No data')}</td></tr>`;
                return;
            }

            tbody.innerHTML = items.map(item => `
                <tr>
                    <td>${item.id}</td>
                    <td>${formatDateDisplay((item.created_at||'').slice(0,10))} ${(item.created_at||'').slice(11,16)}</td>
                    <td>${item.action_type || ''}</td>
                    <td>${item.entity_type || ''}${item.entity_id ? ` #${item.entity_id}` : ''}</td>
                    <td>${item.details || ''}</td>
                </tr>
            `).join('');
        }

        async function loadExpenses() {
            const expenses = await fetch('/api/expenses').then(r => r.json());
            const selectedPeriod = document.getElementById('expense-filter-period')?.value || 'all';
            const selectedPaymentStatus = document.getElementById('expense-filter-status-select')?.value || 'all';
            const tbody = document.getElementById('expenses-body');
            const status = document.getElementById('expense-filter-status');
            if (!tbody) return;

            const today = new Date();
            today.setHours(0, 0, 0, 0);
            const dayOfWeek = today.getDay();
            const diffToMonday = (dayOfWeek + 6) % 7;
            const weekStart = new Date(today);
            weekStart.setDate(today.getDate() - diffToMonday);
            const weekEnd = new Date(weekStart);
            weekEnd.setDate(weekStart.getDate() + 6);
            const monthStart = new Date(today.getFullYear(), today.getMonth(), 1);
            const monthEnd = new Date(today.getFullYear(), today.getMonth() + 1, 0);

            const filteredExpenses = expenses.filter(item => {
                // Filter by period
                if (selectedPeriod !== 'all') {
                    const rawDate = item.expense_date || '';
                    if (!rawDate) return false;
                    const itemDate = new Date(rawDate);
                    if (Number.isNaN(itemDate.getTime())) return false;
                    itemDate.setHours(0, 0, 0, 0);

                    if (selectedPeriod === 'today') {
                        if (itemDate.getTime() !== today.getTime()) return false;
                    } else if (selectedPeriod === 'week') {
                        if (itemDate < weekStart || itemDate > weekEnd) return false;
                    } else if (selectedPeriod === 'month') {
                        if (itemDate < monthStart || itemDate > monthEnd) return false;
                    }
                }
                
                // Filter by payment status
                if (selectedPaymentStatus !== 'all') {
                    const itemStatus = item.payment_status || 'pending';
                    if (itemStatus !== selectedPaymentStatus) return false;
                }
                
                return true;
            });

            if (!filteredExpenses.length) {
                tbody.innerHTML = `<tr><td colspan="7">${t('no_expenses_found', 'No expenses found')}</td></tr>`;
                if (status) {
                    status.textContent = t('no_expenses_found', 'No expenses found');
                }
                return;
            }
            tbody.innerHTML = filteredExpenses.map(item => `
                <tr>
                    <td>${item.expense_date || ''}</td>
                    <td>${item.category || ''}</td>
                    <td>₪ ${parseCurrency(item.amount).toFixed(2)}</td>
                    <td>
                        <select class="expense-status-select" data-status="${item.payment_status || 'postponed'}" onchange="this.dataset.status=this.value;updateExpenseStatus(${item.id}, this.value)">
                            <option value="paid" ${item.payment_status === 'paid' ? 'selected' : ''}>${t('paid', 'Paid')}</option>
                            <option value="postponed" ${item.payment_status === 'postponed' ? 'selected' : ''}>${t('postponed', 'Postponed')}</option>
                        </select>
                    </td>
                    <td>${item.vendor || ''}</td>
                    <td>${item.notes || ''}</td>
                    <td><button class="btn btn-danger" onclick="deleteExpense(${item.id})">${t('delete', 'Delete')}</button></td>
                </tr>
            `).join('');

            if (status) {
                status.textContent = t('showing_expenses_count', 'Showing {count} expense(s).').replace('{count}', filteredExpenses.length);
            }
        }
        
        async function updateExpenseStatus(id, newStatus) {
            const response = await fetch(`/api/expenses/${id}`, {
                method: 'PUT',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({payment_status: newStatus})
            });
            if (response.ok) {
                loadExpenses();
                loadReports();
                loadAuditLogs();
                loadDashboard();
            }
        }

        async function deleteExpense(id) {
            if (!confirm(t('delete_expense_confirm', 'Delete this expense?'))) return;
            await fetch(`/api/expenses/${id}`, { method: 'DELETE' });
            loadExpenses();
            loadReports();
            loadAuditLogs();
            loadDashboard();
        }

        async function loadSupportTips() {
            const tips = await fetch('/api/support').then(r => r.json());
            const container = document.getElementById('support-content');
            container.innerHTML = tips.map(tip => `<div style="padding:16px;border:1px solid #e5e7eb;border-radius:12px;margin-bottom:12px;"><h4>${tip.title}</h4><p>${tip.detail}</p></div>`).join('');
        }

        async function downloadBackup() {
            window.location.href = '/api/backup';
        }

        function switchProfileTab(tabName, btn) {
            const modal = document.getElementById('patient-profile-modal');
            modal.querySelectorAll('.profile-tab').forEach(b => b.classList.remove('active'));
            modal.querySelectorAll('.profile-tab-content').forEach(p => p.classList.remove('active'));
            if (btn) btn.classList.add('active');
            const panel = modal.querySelector(`#profile-tab-${tabName}`);
            if (panel) panel.classList.add('active');
        }

        async function viewPatientProfile(patientId) {
            if (!treatmentProceduresCache.length) {
                await loadTreatmentProcedures();
            }
            const profile = await fetch(`/api/patients/${patientId}/full-profile`).then(r => r.json());
            const patient = profile.patient;
            currentProfilePatient = patient;
            patientProfileCache[patientId] = patient;
            const content = document.getElementById('patient-profile-content');
            const followups = profile.followups || [];
            followupsCache[patientId] = followups;
            const followupTotals = followups.reduce((acc, item) => {
                acc.totalToPay += parseCurrency(item.price || 0);
                acc.totalPaid += parseCurrency(item.payment || 0);
                return acc;
            }, { totalToPay: 0, totalPaid: 0 });
            const totalToPay = Math.max(0, followupTotals.totalToPay);
            const totalPaid = Math.max(0, followupTotals.totalPaid);
            const totalLeft = Math.max(0, totalToPay - totalPaid);
            currentFollowupBalance = totalLeft;
            content.innerHTML = `
                <div class="profile-stats">
                    <div class="stat-card stat-card-teal">
                        <h3 style="font-size:1.3rem;">${patient.first_name} ${patient.last_name}</h3>
                        <p>📞 ${patient.phone || t('no_phone', 'No phone')}</p>
                        ${profile.age != null ? `<p>🎂 ${profile.age} ${currentLanguage==='ar'?'سنة':'yrs'}${profile.birth_date_display ? ' · ' + profile.birth_date_display : ''}</p>` : ''}
                    </div>
                    <div class="stat-card stat-card-blue">
                        <h3>${profile.appointments.length}</h3>
                        <p>${t('appointments', 'Appointments')}</p>
                    </div>
                    <div class="stat-card stat-card-green">
                        <h3>${followups.length}</h3>
                        <p>${t('followups_count', 'Follow-ups')}</p>
                    </div>
                    <div class="stat-card stat-card-amber">
                        <h3>₪${currentFollowupBalance.toFixed(2)}</h3>
                        <p>${t('current_balance', 'Balance Due')}</p>
                        <p style="font-size:0.8rem;opacity:0.88;">↑ ₪${totalToPay.toFixed(2)} &nbsp;✓ ₪${totalPaid.toFixed(2)}</p>
                    </div>
                    <div class="stat-card">
                        <h3>₪${(profile.credit_balance||0).toFixed(2)}</h3>
                        <p>${t('credit_balance','Credit Balance')}</p>
                    </div>
                </div>

                <nav class="profile-tabs">
                    <button class="profile-tab active" onclick="switchProfileTab('overview', this)">${t('overview','Overview')}</button>
                    <button class="profile-tab" onclick="switchProfileTab('followups', this)">${t('followup_sheet','Follow-ups')} (${followups.length})</button>
                    <button class="profile-tab" onclick="switchProfileTab('images', this)">${t('medical_images','Images')} (${profile.medical_images.length})</button>
                </nav>

                <div id="profile-tab-overview" class="profile-tab-content active">
                    <div class="toolbar-row" style="margin-top:0; margin-bottom:16px; flex-wrap:wrap;">
                        <button class="btn btn-primary" type="button" onclick="openAppointmentFromProfile(${patient.id})">+ ${t('book_for_patient', 'Book Appointment')}</button>
                        <button class="btn btn-success" type="button" onclick="printPatientInvoiceById(${patient.id})">${t('print_invoice', 'Print Invoice')}</button>
                        <button class="btn btn-warning" type="button" onclick="switchTab('appointments')">${t('open_calendar', 'Open Calendar')}</button>
                        <button class="btn btn-primary" type="button" onclick="showEditPatientModalById(${patient.id})">${t('edit_personal_data','Edit Info')}</button>
                    </div>
                    <div class="section-card">
                        <div class="section-card-title">${t('patient_info','Patient Information')}</div>
                        <div class="info-grid">
                            <div class="info-field"><label>${t('patient_name','Name')}</label><span>${patient.first_name} ${patient.last_name}</span></div>
                            <div class="info-field"><label>${t('phone','Phone')}</label><span>${patient.phone || '—'}</span></div>
                            ${profile.birth_date_display ? `<div class="info-field"><label>${t('date_of_birth','Date of Birth')}</label><span>${profile.birth_date_display}</span></div>` : ''}
                            ${patient.gender ? `<div class="info-field"><label>${t('gender','Gender')}</label><span>${patient.gender}</span></div>` : ''}
                            ${patient.address ? `<div class="info-field"><label>${t('address','Address')}</label><span>${patient.address}</span></div>` : ''}
                        </div>
                        ${patient.medical_history ? `<div style="margin-top:14px;"><div class="info-field"><label>${t('medical_history','Medical History')}</label><span style="display:block;white-space:pre-wrap;font-weight:400;line-height:1.6;">${patient.medical_history}</span></div></div>` : ''}
                        ${patient.notes ? `<div style="margin-top:10px;"><div class="info-field"><label>${t('notes','Notes')}</label><span style="display:block;white-space:pre-wrap;font-weight:400;line-height:1.6;">${patient.notes}</span></div></div>` : ''}
                    </div>
                </div>

                <div id="profile-tab-followups" class="profile-tab-content">
                    <details class="form-panel" open>
                        <summary>➕ ${t('add_entry','Add New Entry')}</summary>
                        <div class="form-panel-body">
                        <form id="patient-followup-form">
                            <div class="form-row">
                                <div class="form-group"><label>${t('date','Date')}</label><input type="text" name="followup_date" placeholder="DD/MM/YYYY" title="Enter date in DD/MM/YYYY format" required></div>
                                <div class="form-group">
                                    <label>${t('select_procedure','Select Procedure')}</label>
                                    <select name="procedure_id" id="followup-procedure-id">
                                        <option value="">${t('other','Other / Custom')}</option>
                                        ${treatmentProceduresCache.map(item => `<option value="${item.id}">${item.name}</option>`).join('')}
                                    </select>
                                </div>
                                <div class="form-group" id="followup-custom-procedure-wrap">
                                    <label>${t('custom_procedure_name','Procedure Name')}</label>
                                    <input type="text" name="treatment_procedure" id="followup-custom-procedure" placeholder="${t('custom_procedure_placeholder','Type procedure name')}">
                                </div>
                            </div>
                            <div class="form-row-3">
                                <div class="form-group"><label>${t('price','Price')}</label><input type="number" step="0.01" min="0" name="price" id="followup-price" value="0" required></div>
                                <div class="form-group"><label>${t('lab_expense','Lab Expense')}</label><input type="number" step="0.01" min="0" name="lab_expense" id="followup-lab-expense" value="0"></div>
                                <div class="form-group"><label>${t('payment','Payment')}</label><input type="number" step="0.01" min="0" name="payment" id="followup-payment" value="0" required></div>
                            </div>
                            <div class="form-group">
                                <label>${t('notes','Notes')}</label>
                                <textarea name="notes" placeholder="${t('optional_note','Optional note')}" style="min-height:60px;"></textarea>
                            </div>
                            <input type="hidden" name="requires_lab" id="followup-requires-lab" value="0">
                            <input type="hidden" name="patient_id" value="${patient.id}">
                            <button class="btn btn-primary" type="submit">${t('add_entry','Add Entry')}</button>
                        </form>
                        </div>
                    </details>
                    <div class="table-container">
                        <table>
                            <thead>
                                <tr>
                                    <th>${t('date','Date')}</th>
                                    <th>${t('treatment_procedure','Procedure')}</th>
                                    <th>${t('price','Price')}</th>
                                    <th>${t('lab_expense','Lab')}</th>
                                    <th>${t('clinic_profit','Profit')}</th>
                                    <th>${t('payment','Payment')}</th>
                                    <th>${t('balance','Balance')}</th>
                                    <th>${t('notes','Notes')}</th>
                                    <th>${t('actions','Actions')}</th>
                                </tr>
                            </thead>
                            <tbody id="patient-followups-body">${renderFollowupsRows(followups)}</tbody>
                        </table>
                    </div>
                </div>

                <div id="profile-tab-images" class="profile-tab-content">
                    <details class="form-panel" open>
                        <summary>📤 ${t('upload_image','Upload Image')}</summary>
                        <div class="form-panel-body">
                        <form id="upload-image-form" enctype="multipart/form-data">
                            <input type="hidden" name="patient_id" value="${patient.id}">
                            <div class="form-row">
                                <div class="form-group"><label>${t('file','File')}</label><input type="file" name="image" accept="image/*" required></div>
                                <div class="form-group"><label>${t('notes','Notes')}</label><input type="text" name="notes" placeholder="${t('image_notes','Image notes')}"></div>
                            </div>
                            <button class="btn btn-primary" type="submit">${t('upload_image','Upload')}</button>
                        </form>
                        </div>
                    </details>
                    <div class="table-container" style="margin-top:12px;">
                        <table>
                            <thead><tr><th>${t('file','File')}</th><th>${t('uploaded','Uploaded')}</th><th>${t('notes','Notes')}</th></tr></thead>
                            <tbody>${profile.medical_images.map(img => `<tr><td>${img.file_name}</td><td>${img.uploaded_at}</td><td>${img.notes || ''}</td></tr>`).join('') || `<tr><td colspan="3">${t('no_data','No images yet')}</td></tr>`}</tbody>
                        </table>
                    </div>
                </div>
            `;
            document.getElementById('patient-profile-modal').classList.add('active');
            const followupProcedureSelect = document.getElementById('followup-procedure-id');
            if (followupProcedureSelect) {
                followupProcedureSelect.addEventListener('change', updateFollowupProcedureUi);
                updateFollowupProcedureUi();
            }
            document.getElementById('patient-followup-form').addEventListener('submit', async (e) => {
                e.preventDefault();
                const data = Object.fromEntries(new FormData(e.target));
                if (!data.procedure_id && !String(data.treatment_procedure || '').trim()) {
                    alert(t('procedure_required', 'Please select a procedure or enter a custom procedure name.'));
                    return;
                }
                const response = await fetch(`/api/patients/${patient.id}/followups`, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(data)
                });
                if (!response.ok) {
                    const payload = await response.json().catch(() => ({}));
                    alert(payload.error || t('unable_save_followup', 'Unable to save follow-up.'));
                    return;
                }
                await viewPatientProfile(patientId);
                const followupsBtn = document.querySelector('#patient-profile-modal .profile-tab:nth-child(2)');
                if (followupsBtn) switchProfileTab('followups', followupsBtn);
            });
            document.getElementById('upload-image-form').addEventListener('submit', async (e) => {
                e.preventDefault();
                const formData = new FormData(e.target);
                await fetch('/api/medical-images', {method:'POST', body: formData});
                await viewPatientProfile(patientId);
                const imagesBtn = document.querySelector('#patient-profile-modal .profile-tab:nth-child(3)');
                if (imagesBtn) switchProfileTab('images', imagesBtn);
            });
        }

        function formatDateDisplay(dateStr) {
            if (!dateStr) return '';
            const parts = String(dateStr).substring(0, 10).split('-');
            if (parts.length === 3) return `${parts[2]}/${parts[1]}/${parts[0]}`;
            return dateStr;
        }

        function formatApptDate(dateStr) {
            if (!dateStr) return '';
            try {
                const d = new Date(String(dateStr).replace(' ', 'T'));
                if (isNaN(d.getTime())) return dateStr;
                const day = String(d.getDate()).padStart(2,'0');
                const mon = String(d.getMonth()+1).padStart(2,'0');
                const yr = d.getFullYear();
                const hr = String(d.getHours()).padStart(2,'0');
                const mn = String(d.getMinutes()).padStart(2,'0');
                return `${day}/${mon}/${yr} ${hr}:${mn}`;
            } catch(_) { return dateStr; }
        }

        function renderFollowupsRows(followups) {
            if (!followups || !followups.length) {
                return `<tr><td colspan="9">${t('no_entries_yet', 'No entries yet')}</td></tr>`;
            }
            return followups.map(item => `
                <tr>
                    <td>${formatDateDisplay(item.followup_date) || ''}</td>
                    <td>${item.treatment_procedure || t('no_data', 'No data')}</td>
                    <td>₪${parseFloat(item.price || 0).toFixed(2)}</td>
                    <td>₪${parseFloat(item.lab_expense || 0).toFixed(2)}</td>
                    <td>₪${parseFloat(item.clinic_profit || 0).toFixed(2)}</td>
                    <td>₪${parseFloat(item.payment || 0).toFixed(2)}</td>
                    <td>₪${parseFloat(item.remaining_amount || 0).toFixed(2)}</td>
                    <td>${item.notes || ''}</td>
                    <td>
                        <button class="btn btn-warning btn-icon" onclick="deleteFollowup(${item.patient_id},${item.id})">🗑</button>
                        <button class="btn btn-primary btn-icon" onclick="editFollowupById(${item.patient_id},${item.id})">✏</button>
                    </td>
                </tr>
            `).join('');
        }

        async function deleteFollowup(patientId, followupId) {
            if (!confirm(t('confirm_delete', 'Are you sure you want to delete?'))) return;
            const resp = await fetch(`/api/patients/${patientId}/followups/${followupId}`, {method:'DELETE'});
            if (!resp.ok) {
                alert('Delete failed');
                return;
            }
            viewPatientProfile(patientId);
        }

        let currentEditFollowup = null;
        async function editFollowup(item) {
            currentEditFollowup = item;
            document.getElementById('ef-patient-id').value = item.patient_id || '';
            document.getElementById('ef-followup-id').value = item.id || '';
            document.getElementById('ef-date').value = formatDateDisplay(item.followup_date) || '';
            document.getElementById('ef-procedure').value = item.treatment_procedure || '';
            document.getElementById('ef-price').value = parseFloat(item.price || 0).toFixed(2);
            document.getElementById('ef-payment').value = parseFloat(item.payment || 0).toFixed(2);
            document.getElementById('ef-notes').value = item.notes || '';
            document.getElementById('edit-followup-modal').classList.add('active');
        }

        function editFollowupById(patientId, followupId) {
            const list = followupsCache[patientId] || [];
            const item = list.find(f => Number(f.id) === Number(followupId));
            if (!item) { alert(t('no_entry_found', 'Entry not found')); return; }
            editFollowup(item);
        }

        function showEditPatientModal(patientId, patient) {
            document.getElementById('edit-patient-id').value = patientId;
            document.getElementById('edit-first-name').value = patient.first_name || '';
            document.getElementById('edit-last-name').value = patient.last_name || '';
            document.getElementById('edit-phone').value = patient.phone || '';
            document.getElementById('edit-dob').value = formatDateDisplay(patient.date_of_birth) || '';
            document.getElementById('edit-gender').value = patient.gender || '';
            document.getElementById('edit-address').value = patient.address || '';
            document.getElementById('edit-notes').value = patient.notes || '';
            document.getElementById('edit-patient-modal').classList.add('active');
        }

        function showEditPatientModalById(patientId) {
            const patient = patientProfileCache[patientId];
            if (!patient) { alert('Patient data not loaded'); return; }
            showEditPatientModal(patientId, patient);
        }

        document.addEventListener('DOMContentLoaded', function() {
            const editForm = document.getElementById('edit-patient-form');
            if (editForm) {
                editForm.addEventListener('submit', async function(e) {
                    e.preventDefault();
                    const data = Object.fromEntries(new FormData(e.target));
                    const patientId = data.patient_id;
                    delete data.patient_id;
                    const resp = await fetch(`/api/patients/${patientId}`, {
                        method: 'PUT',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify(data)
                    });
                    if (resp.ok) {
                        closeModal('edit-patient-modal');
                        viewPatientProfile(parseInt(patientId));
                        loadPatients();
                    } else {
                        alert(t('save_failed', 'Save failed'));
                    }
                });
            }
            const editFollowupForm = document.getElementById('edit-followup-form');
            if (editFollowupForm) {
                editFollowupForm.addEventListener('submit', async function(e) {
                    e.preventDefault();
                    const patientId = document.getElementById('ef-patient-id').value;
                    const followupId = document.getElementById('ef-followup-id').value;
                    const payload = {
                        ...currentEditFollowup,
                        followup_date: document.getElementById('ef-date').value,
                        treatment_procedure: document.getElementById('ef-procedure').value,
                        price: parseFloat(document.getElementById('ef-price').value || 0),
                        payment: parseFloat(document.getElementById('ef-payment').value || 0),
                        notes: document.getElementById('ef-notes').value
                    };
                    const resp = await fetch(`/api/patients/${patientId}/followups/${followupId}`, {
                        method: 'PUT',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify(payload)
                    });
                    if (resp.ok) {
                        closeModal('edit-followup-modal');
                        viewPatientProfile(parseInt(patientId));
                    } else {
                        alert(t('save_failed', 'Save failed'));
                    }
                });
            }
        });

        async function openAppointmentFromProfile(patientId) {
            closeModal('patient-profile-modal');
            switchTab('appointments');
            await showAddAppointmentModal(patientId);
        }
        
        // Form submissions
        document.getElementById('add-patient-form').addEventListener('submit', async (e) => {
            e.preventDefault();
            const formData = new FormData(e.target);
            const data = Object.fromEntries(formData);
            const resp = await fetch('/api/patients', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(data)
            });
            if (!resp.ok) {
                const err = await resp.json().catch(() => ({}));
                alert(err.error || t('save_failed', 'Save failed'));
                return;
            }
            closeModal('add-patient-modal');
            e.target.reset();
            loadPatients();
        });
        
        document.getElementById('add-appointment-form').addEventListener('submit', async (e) => {
            e.preventDefault();
            const formData = new FormData(e.target);
            const data = Object.fromEntries(formData);
            if (isFridayDateTimeValue(data.appointment_date)) {
                alert('Friday is a permanent holiday.');
                return;
            }
            const response = await fetch('/api/appointments', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(data)
            });
            const payload = await response.json();
            if (!response.ok) {
                alert(payload.error || t('unable_schedule_appointment', 'Unable to schedule appointment.'));
                return;
            }
            closeModal('add-appointment-modal');
            e.target.reset();
            loadAppointments();
            loadDashboard();
        });

        document.getElementById('expense-form').addEventListener('submit', async (e) => {
            e.preventDefault();
            const data = Object.fromEntries(new FormData(e.target));
            const response = await fetch('/api/expenses', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(data)
            });
            if (!response.ok) {
                alert(t('unable_add_expense', 'Unable to add expense.'));
                return;
            }
            e.target.reset();
            const expenseDateInput = document.getElementById('expense-date');
            if (expenseDateInput) {
                const today = new Date();
                const day = String(today.getDate()).padStart(2, '0');
                const month = String(today.getMonth() + 1).padStart(2, '0');
                const year = today.getFullYear();
                expenseDateInput.value = `${day}/${month}/${year}`;
            }
            loadExpenses();
            loadReports();
            loadDashboard();
        });

        const billingForm = document.getElementById('billing-form');
        if (billingForm) {
            billingForm.addEventListener('submit', async (e) => {
                e.preventDefault();
                const data = Object.fromEntries(new FormData(e.target));
                const response = await fetch('/api/billing', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(data)
                });

                if (!response.ok) {
                    const payload = await response.json().catch(() => ({}));
                    alert(payload.error || t('unable_add_billing', 'Unable to create invoice.'));
                    return;
                }

                e.target.reset();
                const billingDateInput = document.getElementById('billing-date');
                if (billingDateInput) {
                    const today = new Date();
                    const day = String(today.getDate()).padStart(2, '0');
                    const month = String(today.getMonth() + 1).padStart(2, '0');
                    const year = today.getFullYear();
                    billingDateInput.value = `${day}/${month}/${year}`;
                }
                loadBilling();
                loadReceivables();
                loadAuditLogs();
            });
        }

        const procedureForm = document.getElementById('procedure-form');
        if (procedureForm) {
            procedureForm.addEventListener('submit', async (e) => {
                e.preventDefault();
                const idValue = (document.getElementById('procedure-id')?.value || '').trim();
                const payload = {
                    name: (document.getElementById('procedure-name')?.value || '').trim(),
                    default_price: parseCurrency(document.getElementById('procedure-default-price')?.value || 0),
                    default_lab_expense: parseCurrency(document.getElementById('procedure-default-lab-expense')?.value || 0),
                    requires_lab: document.getElementById('procedure-requires-lab')?.checked ? 1 : 0,
                    active: document.getElementById('procedure-active')?.checked ? 1 : 0,
                };

                const isEdit = Boolean(idValue);
                const url = isEdit ? `/api/treatment-procedures/${idValue}` : '/api/treatment-procedures';
                const method = isEdit ? 'PUT' : 'POST';
                const response = await fetch(url, {
                    method,
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(payload)
                });

                if (!response.ok) {
                    const payloadError = await response.json().catch(() => ({}));
                    alert(payloadError.error || t('unable_save_procedure', 'Unable to save procedure.'));
                    return;
                }

                resetProcedureForm();
                await loadProcedureCatalog();
                await loadTreatmentProcedures();
                alert(t('procedure_saved', 'Procedure saved successfully.'));
            });
        }

        const holidayForm = document.getElementById('holiday-form');
        if (holidayForm) {
            holidayForm.addEventListener('submit', async (e) => {
                e.preventDefault();
                const data = Object.fromEntries(new FormData(e.target));
                const response = await fetch('/api/holidays', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(data)
                });
                if (!response.ok) {
                    alert(t('unable_add_holiday', 'Unable to add holiday.'));
                    return;
                }
                e.target.reset();
                await loadAppointments();
            });
        }

        const languageToggleBtn = document.getElementById('language-toggle');
        if (languageToggleBtn) {
            languageToggleBtn.addEventListener('click', toggleLanguage);
        }

        const themeToggleBtn = document.getElementById('theme-toggle');
        if (themeToggleBtn) {
            themeToggleBtn.addEventListener('click', toggleTheme);
        }

        // Delete functions
        async function deletePatient(id) {
            if (!confirm(t('confirm_delete_patient', 'Are you sure you want to delete this patient?'))) return;
            const resp = await fetch(`/api/patients/${id}`, {method: 'DELETE'});
            if (!resp.ok) {
                const p = await resp.json().catch(() => ({}));
                alert(p.error || 'Delete failed');
                return;
            }
            loadPatients();
        }
        
        async function updateAppointmentStatus(id, status) {
            await fetch(`/api/appointments/${id}/status`, {
                method: 'PUT',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({status})
            });
            loadAppointments();
            loadDashboard();
        }

        async function startVisitFromAppointment(appointmentId) {
            const response = await fetch(`/api/visits/from-appointment/${appointmentId}`, {
                method: 'POST'
            });
            if (!response.ok) {
                const payload = await response.json().catch(() => ({}));
                alert(payload.message || payload.error || t('unable_start_visit', 'Unable to start visit.'));
                return;
            }
            alert(t('visit_started', 'Visit started from appointment successfully.'));
            loadAppointments();
            loadDashboard();
        }

        // Initial content
        loadSupportSection();
        loadTreatmentProcedures();
        const expenseDateInput = document.getElementById('expense-date');
        const billingDateInput = document.getElementById('billing-date');
        const today = new Date();
        const day = String(today.getDate()).padStart(2, '0');
        const month = String(today.getMonth() + 1).padStart(2, '0');
        const year = today.getFullYear();
        const todayStr = `${day}/${month}/${year}`;
        if (expenseDateInput) expenseDateInput.value = todayStr;
        if (billingDateInput) billingDateInput.value = todayStr;
        applyTheme();
        applyLanguage();
        
        // Load dashboard on page load
        loadDashboard();
    </script>
</body>
</html>
'''

MOBILE_PORTAL_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Clinic Mobile Downloads</title>
    <style>
        :root {
            --bg-1: #f1f7f8;
            --bg-2: #e7f0ff;
            --panel: #ffffff;
            --line: #dbe4ef;
            --text: #11243a;
            --brand: #0f6d7b;
            --brand-2: #1d7fb7;
            --muted: #627386;
        }
        * { box-sizing: border-box; }
        body {
            margin: 0;
            font-family: 'Segoe UI', Tahoma, sans-serif;
            color: var(--text);
            background:
                radial-gradient(1200px 500px at 100% -30%, #cfe7ff 0%, transparent 60%),
                radial-gradient(1000px 500px at -10% 0%, #cff3ec 0%, transparent 58%),
                linear-gradient(160deg, var(--bg-1), var(--bg-2));
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 16px;
        }
        .card {
            width: min(680px, 100%);
            background: rgba(255,255,255,0.94);
            border: 1px solid #e2ebf5;
            border-radius: 18px;
            box-shadow: 0 14px 36px rgba(19, 39, 66, 0.12);
            overflow: hidden;
        }
        .header {
            padding: 18px 18px 14px;
            color: #fff;
            background: linear-gradient(140deg, var(--brand) 0%, var(--brand-2) 100%);
        }
        .header h1 {
            margin: 0;
            font-size: 1.15rem;
        }
        .header p {
            margin: 8px 0 0;
            opacity: 0.9;
            font-size: 0.92rem;
        }
        .body { padding: 16px; }
        .field { margin-bottom: 12px; }
        .field label {
            display: block;
            margin-bottom: 6px;
            font-weight: 700;
            font-size: 0.9rem;
        }
        input {
            width: 100%;
            border: 1px solid var(--line);
            border-radius: 10px;
            padding: 11px 12px;
            font-size: 0.98rem;
        }
        .actions {
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
            margin-top: 6px;
        }
        button, a.btn {
            border: none;
            border-radius: 10px;
            padding: 10px 14px;
            font-weight: 700;
            cursor: pointer;
            text-decoration: none;
            display: inline-flex;
            align-items: center;
            justify-content: center;
        }
        button.primary, a.primary {
            color: #fff;
            background: linear-gradient(140deg, var(--brand) 0%, var(--brand-2) 100%);
        }
        button.secondary {
            color: var(--text);
            background: #eef4fb;
        }
        button:disabled, a.disabled {
            opacity: 0.5;
            pointer-events: none;
        }
        .hidden { display: none; }
        .meta {
            margin-top: 12px;
            font-size: 0.9rem;
            color: var(--muted);
        }
        .platform-grid {
            margin-top: 14px;
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 10px;
        }
        .platform {
            border: 1px solid var(--line);
            border-radius: 12px;
            padding: 12px;
            background: #fff;
        }
        .platform h3 { margin: 0 0 8px; }
        .platform p {
            margin: 0 0 10px;
            color: var(--muted);
            font-size: 0.9rem;
            min-height: 36px;
        }
        .status {
            margin-top: 12px;
            font-size: 0.9rem;
            min-height: 20px;
        }
    </style>
</head>
<body>
    <div class="card">
        <div class="header">
            <h1>Clinic Mobile Downloads</h1>
            <p>Login with your serial number and choose Android or iOS.</p>
        </div>
        <div class="body">
            <div id="login-box">
                <div class="field">
                    <label for="serial-input">Serial Number</label>
                    <input id="serial-input" placeholder="DENTAL-123456" />
                </div>
                <div class="actions">
                    <button class="primary" onclick="loginWithSerial()">Login</button>
                </div>
            </div>

            <div id="download-box" class="hidden">
                <div class="meta" id="license-meta"></div>
                <div class="platform-grid">
                    <div class="platform">
                        <h3>Android</h3>
                        <p>Download and install the Android clinic companion app.</p>
                        <a id="android-btn" class="btn primary" href="#" target="_blank" rel="noopener">Download Android</a>
                    </div>
                    <div class="platform">
                        <h3>iOS</h3>
                        <p>Download the iOS build/TestFlight link for clinic users.</p>
                        <a id="ios-btn" class="btn primary" href="#" target="_blank" rel="noopener">Download iOS</a>
                    </div>
                </div>
                <div class="actions">
                    <button class="secondary" onclick="resetPortal()">Use another serial</button>
                </div>
            </div>

            <div id="status" class="status"></div>
        </div>
    </div>

    <script>
        const OFFLINE_LICENSE_KEY = 'clinic_offline_license_token';

        function setStatus(message, isError = false) {
            const status = document.getElementById('status');
            status.textContent = message || '';
            status.style.color = isError ? '#c7254e' : '#2d6a4f';
        }

        function setDownloadButton(anchorId, option) {
            const btn = document.getElementById(anchorId);
            if (!option || !option.available || !option.url) {
                btn.classList.add('disabled');
                btn.removeAttribute('href');
                return;
            }
            btn.classList.remove('disabled');
            btn.href = option.url;
        }

        function renderLicense(payload) {
            document.getElementById('login-box').classList.add('hidden');
            document.getElementById('download-box').classList.remove('hidden');
            const meta = `Clinic: ${payload.clinic_name || '-'} | Plan: ${payload.plan_name || '-'} | Expires: ${payload.expires_at || '-'}`;
            document.getElementById('license-meta').textContent = meta;
            setStatus('License ready.');
        }

        async function restoreOfflineLicense() {
            const savedToken = localStorage.getItem(OFFLINE_LICENSE_KEY);
            if (!savedToken) {
                return;
            }

            try {
                const response = await fetch('/api/license/offline-verify', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({offline_license_token: savedToken})
                });
                const payload = await response.json();
                if (!response.ok) {
                    localStorage.removeItem(OFFLINE_LICENSE_KEY);
                    return;
                }

                renderLicense(payload.offline_license || {});
                const downloads = payload.downloads || {};
                if (downloads.android) {
                    setDownloadButton('android-btn', downloads.android);
                }
                if (downloads.ios) {
                    setDownloadButton('ios-btn', downloads.ios);
                }
            } catch (_) {
                // Silent by design: offline restore should not bother the user.
            }
        }

        async function loginWithSerial() {
            const serial = document.getElementById('serial-input').value.trim().toUpperCase();
            if (!serial) {
                setStatus('Please enter your serial number.', true);
                return;
            }

            setStatus('Checking serial...');
            try {
                const response = await fetch('/api/license/login', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({serial_number: serial})
                });
                const payload = await response.json();
                if (!response.ok) {
                    setStatus(payload.error || 'Login failed.', true);
                    return;
                }

                if (payload.offline_license_token) {
                    localStorage.setItem(OFFLINE_LICENSE_KEY, payload.offline_license_token);
                }

                renderLicense(payload);

                setDownloadButton('android-btn', payload.downloads?.android);
                setDownloadButton('ios-btn', payload.downloads?.ios);
                setStatus('Login successful.');
            } catch (error) {
                setStatus('Network error while validating serial.', true);
            }
        }

        function resetPortal() {
            localStorage.removeItem(OFFLINE_LICENSE_KEY);
            document.getElementById('download-box').classList.add('hidden');
            document.getElementById('login-box').classList.remove('hidden');
            document.getElementById('serial-input').value = '';
            setStatus('');
        }

        document.addEventListener('DOMContentLoaded', restoreOfflineLicense);
    </script>
</body>
</html>
'''

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)


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

    # Total visits
    cursor.execute('SELECT COUNT(*) FROM visits')
    total_visits = cursor.fetchone()[0]
    
    # Dashboard revenue source: patient follow-up payments (SUM(payment)).
    cursor.execute('SELECT COALESCE(SUM(payment), 0) FROM patient_followups')
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

@app.route('/api/patients/<int:patient_id>', methods=['DELETE'])
def delete_patient(patient_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # Soft-delete dependent records first to avoid orphans
    cursor.execute('UPDATE patient_followups SET is_deleted = 1 WHERE patient_id = ?', (patient_id,))
    cursor.execute('DELETE FROM patients WHERE id = ?', (patient_id,))
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
        cursor.execute('''
            SELECT pf.*, tp.requires_lab as procedure_requires_lab
            FROM patient_followups pf
            LEFT JOIN treatment_procedures tp ON tp.id = pf.procedure_id
            WHERE pf.patient_id = ?
            ORDER BY pf.followup_date DESC, pf.id DESC
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
        SELECT COALESCE(SUM(price), 0), COALESCE(SUM(payment), 0)
        FROM patient_followups
        WHERE patient_id = ?
    ''', (patient_id,))
    previous_totals = cursor.fetchone() or (0, 0)
    previous_balance = max(as_float(previous_totals[0]) - as_float(previous_totals[1]), 0)

    price = as_float(data.get('price'))
    payment = as_float(data.get('payment'))
    lab_expense = as_float(data.get('lab_expense'))
    clinic_profit = price - lab_expense
    remaining_amount = max(previous_balance + price - payment, 0)

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

    if not requires_lab:
        lab_expense = 0
        clinic_profit = price

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
            price, lab_expense, clinic_profit, payment, remaining_amount, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        patient_id,
        parsed_followup_date,
        data.get('tooth_no'),
        data.get('diagnosis'),
        treatment_procedure,
        procedure_id,
        price,
        lab_expense,
        clinic_profit,
        payment,
        remaining_amount,
        data.get('notes')
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
        append_audit_log(cursor, 'delete', 'patient_followup', followup_id, {'patient_id': patient_id})
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
    payment = as_float(data.get('payment'))
    lab_expense = as_float(data.get('lab_expense'))
    clinic_profit = as_float(data.get('clinic_profit', price - lab_expense))

    cursor.execute('''
        SELECT COALESCE(SUM(price), 0), COALESCE(SUM(payment), 0)
        FROM patient_followups
        WHERE patient_id = ? AND (is_deleted IS NULL OR is_deleted != 1) AND id != ?
    ''', (patient_id, followup_id))
    prev = cursor.fetchone() or (0, 0)
    previous_balance = max(float(prev[0]) - float(prev[1]), 0)
    remaining_amount = max(previous_balance + price - payment, 0)

    cursor.execute('''
        UPDATE patient_followups
        SET followup_date = ?, treatment_procedure = ?, price = ?, lab_expense = ?,
            clinic_profit = ?, payment = ?, remaining_amount = ?, notes = ?
        WHERE id = ? AND patient_id = ?
    ''', (
        parsed_date, data.get('treatment_procedure'), price, lab_expense,
        clinic_profit, payment, remaining_amount, data.get('notes'),
        followup_id, patient_id
    ))
    append_audit_log(cursor, 'update', 'patient_followup', followup_id, {
        'patient_id': patient_id,
        'treatment_procedure': data.get('treatment_procedure'),
        'price': price,
        'payment': payment,
    })
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

        try:
            appointment_date = normalize_datetime_input(data.get('appointment_date'))
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

        cursor.execute('''
            INSERT INTO appointments (patient_id, appointment_date, duration, treatment_type, notes)
            VALUES (?, ?, ?, ?, ?)
        ''', (patient_id, appointment_date, duration,
              data.get('treatment_type'), data.get('notes')))
        conn.commit()
        conn.close()
        return jsonify({'success': True})

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
    if status not in {'scheduled', 'completed', 'cancelled', 'no_show'}:
        conn.close()
        return jsonify({'error': 'Invalid appointment status'}), 400
    cursor.execute('UPDATE appointments SET status = ? WHERE id = ?', (status, appointment_id))
    if cursor.rowcount == 0:
        conn.close()
        return jsonify({'error': 'Appointment not found'}), 404
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
    cursor.execute(f'SELECT COALESCE(SUM(payment), 0) FROM patient_followups WHERE 1=1{clause}', params)
    revenue = cursor.fetchone()[0]

    clause, params = build_date_clause('followup_date', start_date, end_date)
    cursor.execute(f'SELECT COALESCE(SUM(COALESCE(lab_expense, 0)), 0) FROM patient_followups WHERE 1=1{clause}', params)
    lab_expenses = cursor.fetchone()[0]

    clause, params = build_date_clause('followup_date', start_date, end_date)
    cursor.execute(f'SELECT COALESCE(SUM(COALESCE(clinic_profit, COALESCE(price, 0) - COALESCE(lab_expense, 0))), 0) FROM patient_followups WHERE 1=1{clause}', params)
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

    cursor.execute('SELECT COALESCE(SUM(payment), 0) FROM patient_followups WHERE date(followup_date) BETWEEN ? AND ?', (start_str, end_str))
    revenue = cursor.fetchone()[0]

    cursor.execute('SELECT COALESCE(SUM(COALESCE(lab_expense, 0)), 0) FROM patient_followups WHERE date(followup_date) BETWEEN ? AND ?', (start_str, end_str))
    lab_expenses = cursor.fetchone()[0]

    cursor.execute('SELECT COALESCE(SUM(COALESCE(clinic_profit, COALESCE(price, 0) - COALESCE(lab_expense, 0))), 0) FROM patient_followups WHERE date(followup_date) BETWEEN ? AND ?', (start_str, end_str))
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
        'follow_ups': follow_ups_count,
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
            COALESCE(SUM(pf.payment), 0) AS total_paid,
            MAX(pf.followup_date) AS last_followup_date
        FROM patients p
        LEFT JOIN patient_followups pf ON pf.patient_id = p.id
        GROUP BY p.id, p.first_name, p.last_name
        HAVING (COALESCE(SUM(pf.price), 0) - COALESCE(SUM(pf.payment), 0)) > 0
        ORDER BY (COALESCE(SUM(pf.price), 0) - COALESCE(SUM(pf.payment), 0)) DESC, patient_name ASC
    ''')

    rows = []
    total_receivables = 0.0
    today = datetime.now().date()

    for row in cursor.fetchall():
        total_to_pay = float(row['total_to_pay'] or 0)
        total_paid = float(row['total_paid'] or 0)
        outstanding = max(total_to_pay - total_paid, 0.0)
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

    conditions = ['patient_id = ?']
    params = [patient_id]
    if start_date:
        conditions.append('date(followup_date) >= ?')
        params.append(start_date)
    if end_date:
        conditions.append('date(followup_date) <= ?')
        params.append(end_date)
    where_clause = ' AND '.join(conditions)

    cursor.execute(f'''
        SELECT id, followup_date, treatment_procedure, price, payment, remaining_amount, notes
        FROM patient_followups
        WHERE {where_clause}
        ORDER BY followup_date ASC, id ASC
    ''', params)
    items = [dict(row) for row in cursor.fetchall()]

    cursor.execute(f'''
        SELECT
            COALESCE(SUM(price), 0) AS total_to_pay,
            COALESCE(SUM(payment), 0) AS total_paid,
            COALESCE(SUM(remaining_amount), 0) AS running_balance_sum
        FROM patient_followups
        WHERE {where_clause}
    ''', params)
    totals = cursor.fetchone()

    total_to_pay = float((totals['total_to_pay'] if totals else 0) or 0)
    total_paid = float((totals['total_paid'] if totals else 0) or 0)
    total_left = max(total_to_pay - total_paid, 0)

    conn.close()
    return jsonify({
        'patient': {
            'id': patient['id'],
            'name': f"{patient['first_name']} {patient['last_name']}".strip(),
            'phone': patient['phone']
        },
        'items': items,
        'totals': {
            'total_to_pay': total_to_pay,
            'total_paid': total_paid,
            'total_left': total_left
        },
        'range': {
            'start_date': start_date,
            'end_date': end_date
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
    conn.commit()
    conn.close()
    return jsonify({'success': True})

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
                'discount': row_data.get('discount'),
                'paid_amount': row_data.get('paid_amount'),
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

        total_amount = round(max(0.0, subtotal - discount), 2)
        balance_due = round(max(0.0, total_amount - paid_amount), 2)

        if total_amount > 0 and paid_amount >= total_amount:
            payment_status = 'paid'
        elif paid_amount > 0:
            payment_status = 'partial'
        else:
            payment_status = 'pending'

        invoice_number = data.get('invoice_number') or generate_invoice_number()
        
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
                subtotal, discount, paid_amount, balance_due,
                payment_method, payment_status, payment_date
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            data['patient_id'],
            data.get('treatment_id'),
            invoice_number,
            total_amount,
            subtotal,
            discount,
            paid_amount,
            balance_due,
            data.get('payment_method'),
            payment_status,
            payment_date
        ))
        append_audit_log(cursor, 'create', 'billing', cursor.lastrowid, {
            'patient_id': data.get('patient_id'),
            'invoice_number': invoice_number,
            'subtotal': subtotal,
            'discount': discount,
            'paid_amount': paid_amount,
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
    cursor.execute('DELETE FROM billing WHERE id = ?', (billing_id,))
    append_audit_log(cursor, 'delete', 'billing', billing_id, {'id': billing_id})
    conn.commit()
    conn.close()
    return jsonify({'success': True})


@app.route('/invoice/<int:billing_id>')
def billing_invoice(billing_id):
    lang = request.args.get('lang', 'en')
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
            'total': 'Total', 'paid': 'Paid', 'balance': 'Balance Due',
            'method': 'Payment Method', 'status': 'Status', 'clinic': 'Dr. Wasfy Barzaq Dental Clinic'
        },
        'ar': {
            'title': 'فاتورة', 'patient': 'المريض', 'invoice_no': 'رقم الفاتورة',
            'date': 'التاريخ', 'subtotal': 'الإجمالي قبل الخصم', 'discount': 'الخصم',
            'total': 'الإجمالي', 'paid': 'المدفوع', 'balance': 'الرصيد المستحق',
            'method': 'طريقة الدفع', 'status': 'الحالة', 'clinic': 'عيادة د. وصفي برزق للأسنان'
        }
    }
    lbl = labels.get(lang, labels['en'])
    currency = '₪'

    html = f'''<!DOCTYPE html>
<html lang="{lang}" dir="{direction}">
<head>
<meta charset="UTF-8">
<title>{lbl["title"]} {b.get("invoice_number","")}</title>
<style>
  body {{ font-family: Arial, sans-serif; margin: 32px; color: #222; direction: {direction}; }}
  h1 {{ margin: 0 0 4px 0; font-size: 22px; }}
  .clinic {{ color: #555; margin-bottom: 20px; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 16px; }}
  th, td {{ border: 1px solid #ddd; padding: 10px 12px; text-align: {align}; }}
  th {{ background: #f5f5f5; font-weight: 600; }}
  .total-row td {{ font-weight: 700; background: #f9f9f9; }}
  @media print {{ body {{ margin: 16px; }} }}
</style>
</head>
<body>
<h1>{lbl["title"]}</h1>
<div class="clinic">{lbl["clinic"]}</div>
<table>
  <tr><th>{lbl["invoice_no"]}</th><td>{b.get("invoice_number","—")}</td></tr>
  <tr><th>{lbl["patient"]}</th><td>{b.get("patient_name","—")}</td></tr>
  <tr><th>{lbl["date"]}</th><td>{b.get("payment_date") or b.get("created_at","—")}</td></tr>
  <tr><th>{lbl["method"]}</th><td>{b.get("payment_method") or "—"}</td></tr>
  <tr><th>{lbl["status"]}</th><td>{b.get("payment_status","—")}</td></tr>
  <tr><th>{lbl["subtotal"]}</th><td>{currency} {float(b.get("subtotal") or 0):.2f}</td></tr>
  <tr><th>{lbl["discount"]}</th><td>{currency} {float(b.get("discount") or 0):.2f}</td></tr>
  <tr class="total-row"><th>{lbl["total"]}</th><td>{currency} {float(b.get("amount") or 0):.2f}</td></tr>
  <tr><th>{lbl["paid"]}</th><td>{currency} {float(b.get("paid_amount") or 0):.2f}</td></tr>
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

    expires_at = (datetime.utcnow() + timedelta(minutes=PAIRING_CODE_TTL_MINUTES)).strftime('%Y-%m-%d %H:%M:%S')
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
    if int(request_row[3]) == 1 or datetime.utcnow() > expires_at:
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

    snapshot_tables = {}
    total_records = 0
    for table_name in SYNC_TABLES:
        cursor.execute(f'SELECT * FROM {table_name} ORDER BY id ASC')
        rows = [dict(row) for row in cursor.fetchall()]
        snapshot_tables[table_name] = rows
        total_records += len(rows)

    app_instance_id = read_app_setting(cursor, 'app_instance_id', '')
    cursor.execute('''
        INSERT INTO sync_snapshots (source, device_id, table_count, record_count)
        VALUES (?, ?, ?, ?)
    ''', ('export', device['device_id'], len(SYNC_TABLES), total_records))
    cursor.execute('''
        INSERT INTO sync_events (event_type, source_device_id, details)
        VALUES (?, ?, ?)
    ''', ('snapshot_export', device['device_id'], json.dumps({'record_count': total_records})))
    conn.commit()
    conn.close()

    return jsonify({
        'success': True,
        'generated_at': utc_now_iso(),
        'source_instance_id': app_instance_id,
        'table_count': len(SYNC_TABLES),
        'record_count': total_records,
        'tables': snapshot_tables
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

    applied_total = 0
    skipped_total = 0
    by_table = {}

    for table_name in SYNC_TABLES:
        incoming_rows = incoming_tables.get(table_name, [])
        if not isinstance(incoming_rows, list):
            continue

        applied = 0
        skipped = 0
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
            if existing:
                local_updated = parse_timestamp_for_sync(existing['updated_at'] or existing['created_at'])
                incoming_updated = parse_timestamp_for_sync(row_data.get('updated_at') or row_data.get('created_at'))
                if incoming_updated <= local_updated:
                    skipped += 1
                    continue

            if upsert_row(cursor, table_name, row_data):
                applied += 1
            else:
                skipped += 1

        by_table[table_name] = {'applied': applied, 'skipped': skipped}
        applied_total += applied
        skipped_total += skipped

    cursor.execute('''
        INSERT INTO sync_snapshots (source, device_id, table_count, record_count)
        VALUES (?, ?, ?, ?)
    ''', ('import', device['device_id'], len(by_table), applied_total))
    cursor.execute('''
        INSERT INTO sync_events (event_type, source_device_id, details)
        VALUES (?, ?, ?)
    ''', ('snapshot_import', device['device_id'], json.dumps({'applied_total': applied_total, 'skipped_total': skipped_total})))
    conn.commit()
    conn.close()

    return jsonify({
        'success': True,
        'applied_total': applied_total,
        'skipped_total': skipped_total,
        'by_table': by_table
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
    now_dt = datetime.utcnow()
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
        conn.close()
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


@app.route('/api/treatment-catalog', methods=['GET', 'POST'])
def treatment_catalog_collection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    if request.method == 'GET':
        include_inactive = str(request.args.get('include_inactive', '0')).strip() in ('1', 'true')
        if include_inactive:
            cursor.execute('SELECT * FROM treatment_catalog ORDER BY name_ar')
        else:
            cursor.execute('SELECT * FROM treatment_catalog WHERE is_active = 1 ORDER BY name_ar')
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return jsonify(rows)
    data = request.json or {}
    name_ar = str(data.get('name_ar') or '').strip()
    if not name_ar:
        conn.close()
        return jsonify({'error': 'name_ar is required'}), 400
    cursor.execute('INSERT INTO treatment_catalog (name_ar, name_en, default_price) VALUES (?, ?, ?)',
                   (name_ar, str(data.get('name_en') or ''), float(data.get('default_price') or 0)))
    new_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'id': new_id})


@app.route('/api/treatment-catalog/<int:catalog_id>', methods=['PUT', 'DELETE'])
def treatment_catalog_item(catalog_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    if request.method == 'DELETE':
        cursor.execute('UPDATE treatment_catalog SET is_active = 0 WHERE id = ?', (catalog_id,))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    data = request.json or {}
    fields, values = [], []
    for col in ('name_ar', 'name_en', 'default_price', 'is_active'):
        if col in data:
            fields.append(f'{col} = ?')
            values.append(data[col])
    if fields:
        values.append(catalog_id)
        conn.execute(f'UPDATE treatment_catalog SET {", ".join(fields)} WHERE id = ?', values)
        conn.commit()
    conn.close()
    return jsonify({'success': True})


@app.route('/api/patients/<int:patient_id>/credit', methods=['GET'])
def patient_credit(patient_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT COALESCE(SUM(amount), 0) FROM patient_credit_transactions WHERE patient_id = ?', (patient_id,))
    balance = float(cursor.fetchone()[0] or 0)
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
    cursor.execute('INSERT INTO patient_credit_transactions (patient_id, amount, type, note) VALUES (?, ?, ?, ?)',
                 (patient_id, abs(amount), 'credit' if amount >= 0 else 'debit', note))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


def open_browser(port=5000):
    """Open browser after a short delay"""
    import time
    time.sleep(1.5)
    webbrowser.open(f'http://127.0.0.1:{port}')

if __name__ == '__main__':
    host = os.environ.get('CLINIC_HOST', '127.0.0.1')
    port_raw = os.environ.get('CLINIC_PORT', '5000')
    try:
        port = int(port_raw)
    except ValueError:
        port = 5000

    print("\n" + "="*60)
    print("🦷 DENTAL CLINIC MANAGEMENT SYSTEM")
    print("="*60)

    print('\n📊 Initializing database...')
    init_database()

    threading.Thread(target=open_browser, kwargs={'port': port}, daemon=True).start()

    print("\n✅ System ready!")
    print(f'🌐 Opening browser at http://127.0.0.1:{port}')
    if host != '127.0.0.1':
        print(f'📶 LAN mode enabled on {host}:{port}')
    print("\n📝 Press CTRL+C to stop the server\n")
    print("="*60 + "\n")

    app.run(host=host, port=port, debug=False)
