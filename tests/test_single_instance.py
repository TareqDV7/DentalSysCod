"""Tests for window.single_instance.SingleInstanceGuard.

Windows named-mutex single-instance guard used by the desktop exe entry
point to stop a second app window spawning. Every test patches MUTEX_NAME
to a unique value so the real running DentaCare app (if any) and parallel
test runs never collide on the actual production mutex name.
"""

import sys
import types
import uuid

import pytest

from window import single_instance
from window.single_instance import SingleInstanceGuard


@pytest.fixture(autouse=True)
def _unique_mutex_name(monkeypatch):
    monkeypatch.setattr(single_instance, 'MUTEX_NAME', f'DentaCare-Test-{uuid.uuid4()}')


def test_first_instance_acquires_mutex():
    guard = SingleInstanceGuard()
    try:
        assert guard.is_first_instance is True
        assert guard._handle is not None
    finally:
        guard.release()


def test_second_guard_sees_existing_mutex():
    guard1 = SingleInstanceGuard()
    guard2 = SingleInstanceGuard()
    try:
        assert guard1.is_first_instance is True
        assert guard2.is_first_instance is False
    finally:
        guard1.release()
        guard2.release()


def test_release_then_reacquire():
    guard1 = SingleInstanceGuard()
    guard1.release()
    guard2 = SingleInstanceGuard()
    try:
        assert guard2.is_first_instance is True
    finally:
        guard2.release()


def test_release_is_idempotent():
    guard = SingleInstanceGuard()
    guard.release()
    assert guard._handle is None
    guard.release()
    assert guard._handle is None


def test_context_manager_releases():
    with SingleInstanceGuard() as g:
        assert g.is_first_instance is True
        assert g._handle is not None
    assert g._handle is None


def test_non_windows_is_noop(monkeypatch):
    monkeypatch.setattr(sys, 'platform', 'linux')
    guard = SingleInstanceGuard()
    assert guard.is_first_instance is True
    assert guard._handle is None
    guard.release()


def test_ctypes_failure_fails_open(monkeypatch):
    monkeypatch.setitem(sys.modules, 'ctypes', types.ModuleType('ctypes'))
    guard = SingleInstanceGuard()
    assert guard.is_first_instance is True
    assert guard._handle is None


def test_release_swallows_ctypes_error():
    guard = SingleInstanceGuard()
    assert guard._handle is not None
    real_ctypes = sys.modules['ctypes']
    sys.modules['ctypes'] = types.ModuleType('ctypes')
    try:
        guard.release()
    finally:
        sys.modules['ctypes'] = real_ctypes
    assert guard._handle is None
