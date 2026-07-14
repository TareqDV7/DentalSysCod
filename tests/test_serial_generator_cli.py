"""Tests for serial_generator.py CLI/batch plumbing.

Crypto primitives (sign/verify/keypair) are covered by test_serial_ed25519.py.
This file covers create_serial_batch's CSV export and main()'s argparse CLI —
the vendor-side offline license-minting tool, run out-of-band from the app.
"""

import csv
import json
import sys

import pytest

import serial_generator


@pytest.fixture
def signing_key(tmp_path):
    priv_b64, pub_b64 = serial_generator.generate_keypair()
    key_file = tmp_path / 'key.json'
    key_file.write_text(json.dumps({'alg': 'ed25519', 'private': priv_b64}))
    return str(key_file), pub_b64


# --------------------------------------------------------------------- #
# create_serial_batch
# --------------------------------------------------------------------- #

def test_create_serial_batch_returns_one_license_per_device(signing_key):
    key_file, pub_b64 = signing_key
    licenses = serial_generator.create_serial_batch(
        clinic_name='Smile Dental', clinic_code='SMD',
        devices=['DEV-A', 'DEV-B', 'DEV-C'],
        signing_key_file=key_file,
    )
    assert len(licenses) == 3
    serials = {lic['serial'] for lic in licenses}
    assert len(serials) == 3
    for lic in licenses:
        ok, payload = serial_generator.verify_serial_token(lic['offline_token'], pub_b64)
        assert ok is True
        assert payload['device_id'] in ('DEV-A', 'DEV-B', 'DEV-C')


def test_create_serial_batch_csv_export(tmp_path, signing_key):
    key_file, _ = signing_key
    out = tmp_path / 'out.csv'
    licenses = serial_generator.create_serial_batch(
        clinic_name='Smile Dental', clinic_code='SMD',
        devices=['DEV-A', 'DEV-B'],
        signing_key_file=key_file, output_file=str(out),
    )
    assert out.exists()
    with open(out, newline='', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 2
    assert rows[0]['Clinic Name'] == 'Smile Dental'
    assert rows[0]['Offline Token'] == licenses[0]['offline_token']


def test_create_serial_batch_csv_error_is_nonfatal(tmp_path, capsys, signing_key):
    key_file, _ = signing_key
    licenses = serial_generator.create_serial_batch(
        clinic_name='Smile Dental', clinic_code='SMD',
        devices=['DEV-A'],
        signing_key_file=key_file, output_file=str(tmp_path),
    )
    assert len(licenses) == 1
    assert 'Error exporting' in capsys.readouterr().out


def test_create_serial_batch_requires_key_file():
    with pytest.raises(FileNotFoundError):
        serial_generator.create_serial_batch(
            clinic_name='Smile Dental', clinic_code='SMD',
            devices=['DEV-A'], signing_key_file=None,
        )


# --------------------------------------------------------------------- #
# main() CLI
# --------------------------------------------------------------------- #

def test_main_genkey_writes_key_and_prints_pub(tmp_path, monkeypatch, capsys):
    out = tmp_path / 'k.json'
    monkeypatch.setattr(sys, 'argv', ['serial_generator.py', '--genkey', str(out)])
    rc = serial_generator.main()
    assert rc == 0
    assert out.exists()
    data = json.loads(out.read_text())
    assert data['alg'] == 'ed25519'
    assert 'private' in data
    assert 'Public key' in capsys.readouterr().out


def test_main_single_device(monkeypatch, capsys, signing_key):
    key_file, pub_b64 = signing_key
    monkeypatch.setattr(sys, 'argv', [
        'serial_generator.py', '--clinic', 'Smile Dental', '--code', 'SMD',
        '--device', 'LAPTOP-ABC', '--key-file', key_file,
    ])
    rc = serial_generator.main()
    assert rc == 0
    out = capsys.readouterr().out
    assert 'SERIAL NUMBER:' in out
    token = [line for line in out.splitlines() if '.' in line and line.strip().count('.') == 1][0].strip()
    ok, payload = serial_generator.verify_serial_token(token, pub_b64)
    assert ok is True
    assert payload['clinic_name'] == 'Smile Dental'


def test_main_batch_devices_file_csv(tmp_path, monkeypatch, signing_key):
    key_file, _ = signing_key
    devices_file = tmp_path / 'devices.txt'
    devices_file.write_text('DEV-A\nDEV-B\n\n')
    out = tmp_path / 's.csv'
    monkeypatch.setattr(sys, 'argv', [
        'serial_generator.py', '--clinic', 'Smile Dental', '--code', 'SMD',
        '--devices-file', str(devices_file), '--output', str(out),
        '--key-file', key_file,
    ])
    rc = serial_generator.main()
    assert rc == 0
    with open(out, newline='', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 2


def test_main_batch_json_output(tmp_path, monkeypatch, signing_key):
    key_file, _ = signing_key
    devices_file = tmp_path / 'devices.txt'
    devices_file.write_text('DEV-A\nDEV-B\n')
    out = tmp_path / 's.json'
    monkeypatch.setattr(sys, 'argv', [
        'serial_generator.py', '--clinic', 'Smile Dental', '--code', 'SMD',
        '--devices-file', str(devices_file), '--output', str(out),
        '--key-file', key_file, '--json',
    ])
    rc = serial_generator.main()
    assert rc == 0
    records = json.loads(out.read_text())
    assert len(records) == 2
    assert not out.with_suffix('.csv').exists()


def test_main_requires_device_or_devices_file(monkeypatch, signing_key):
    key_file, _ = signing_key
    monkeypatch.setattr(sys, 'argv', [
        'serial_generator.py', '--clinic', 'Smile Dental', '--code', 'SMD',
        '--key-file', key_file,
    ])
    with pytest.raises(SystemExit):
        serial_generator.main()


def test_main_rejects_long_clinic_code(monkeypatch, signing_key):
    key_file, _ = signing_key
    monkeypatch.setattr(sys, 'argv', [
        'serial_generator.py', '--clinic', 'Smile Dental', '--code', 'TOOLONG',
        '--device', 'DEV-A', '--key-file', key_file,
    ])
    with pytest.raises(SystemExit):
        serial_generator.main()


def test_main_missing_key_file_errors_fast(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, 'argv', [
        'serial_generator.py', '--clinic', 'Smile Dental', '--code', 'SMD',
        '--device', 'DEV-A', '--key-file', str(tmp_path / 'nope.json'),
    ])
    with pytest.raises(SystemExit):
        serial_generator.main()


def test_main_empty_devices_file_returns_1(tmp_path, monkeypatch, signing_key):
    key_file, _ = signing_key
    devices_file = tmp_path / 'devices.txt'
    devices_file.write_text('\n\n   \n')
    monkeypatch.setattr(sys, 'argv', [
        'serial_generator.py', '--clinic', 'Smile Dental', '--code', 'SMD',
        '--devices-file', str(devices_file), '--key-file', key_file,
    ])
    rc = serial_generator.main()
    assert rc == 1


def test_main_devices_file_not_found_returns_1(tmp_path, monkeypatch, capsys, signing_key):
    key_file, _ = signing_key
    monkeypatch.setattr(sys, 'argv', [
        'serial_generator.py', '--clinic', 'Smile Dental', '--code', 'SMD',
        '--devices-file', str(tmp_path / 'nope.txt'), '--key-file', key_file,
    ])
    rc = serial_generator.main()
    assert rc == 1
    assert 'File not found' in capsys.readouterr().out
