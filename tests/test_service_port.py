# tests/test_service_port.py
"""Service-port handshake: the service binds a free port and publishes it to a
small file in the shared data dir; the window launcher reads that file so it
always points at the right server instead of a hard-coded 5000 (which collides
when another local Flask app — or a second DentaCare copy — owns the port)."""
import socket

import dental_clinic
from window import service_port


def _grab_free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_port_is_available_true_for_free_port():
    port = _grab_free_port()
    assert dental_clinic._port_is_available('127.0.0.1', port) is True


def test_port_is_available_false_when_bound():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('127.0.0.1', 0))
    s.listen()
    port = s.getsockname()[1]
    try:
        assert dental_clinic._port_is_available('127.0.0.1', port) is False
    finally:
        s.close()


def test_resolve_service_port_keeps_preferred_when_free():
    port = _grab_free_port()
    assert dental_clinic._resolve_service_port('127.0.0.1', port) == port


def test_resolve_service_port_falls_back_when_busy():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('127.0.0.1', 0))
    s.listen()
    busy = s.getsockname()[1]
    try:
        chosen = dental_clinic._resolve_service_port('127.0.0.1', busy)
        assert chosen != busy
        assert dental_clinic._port_is_available('127.0.0.1', chosen) is True
    finally:
        s.close()


def test_resolve_service_port_tolerates_bad_preferred():
    # A non-numeric CLINIC_PORT must not crash startup.
    chosen = dental_clinic._resolve_service_port('127.0.0.1', 'not-a-port')
    assert isinstance(chosen, int) and 1 <= chosen <= 65535


def test_write_service_port_file_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(dental_clinic, '_DATA_DIR', tmp_path)
    dental_clinic._write_service_port_file(54321)
    written = (tmp_path / dental_clinic.SERVICE_PORT_FILENAME).read_text(encoding='utf-8').strip()
    assert written == '54321'


def test_window_reads_published_port(tmp_path, monkeypatch):
    monkeypatch.setenv('CLINIC_DATA_DIR', str(tmp_path))
    (tmp_path / service_port.SERVICE_PORT_FILENAME).write_text('51999', encoding='utf-8')
    assert service_port.read_service_port() == 51999
    assert service_port.service_url() == 'http://127.0.0.1:51999'


def test_window_falls_back_to_default_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.setenv('CLINIC_DATA_DIR', str(tmp_path))
    assert service_port.read_service_port() == service_port.DEFAULT_SERVICE_PORT


def test_window_falls_back_to_default_on_garbage(tmp_path, monkeypatch):
    monkeypatch.setenv('CLINIC_DATA_DIR', str(tmp_path))
    (tmp_path / service_port.SERVICE_PORT_FILENAME).write_text('not-a-number', encoding='utf-8')
    assert service_port.read_service_port() == service_port.DEFAULT_SERVICE_PORT
