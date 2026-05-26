"""Tests for window.window_state.{load,save}.

Persists the window's last x/y/width/height to a JSON file. Robust to
the file missing, being malformed, or containing partial data."""

import json
from pathlib import Path

import pytest

from window.window_state import load_window_state, save_window_state, WindowState


def test_save_then_load_roundtrip(tmp_path):
    state = WindowState(x=100, y=200, width=1280, height=800)
    save_window_state(state, tmp_path / 'state.json')
    loaded = load_window_state(tmp_path / 'state.json')
    assert loaded == state


def test_load_missing_file_returns_default():
    state = load_window_state(Path('/no/such/file.json'))
    assert state.width == 1280
    assert state.height == 800
    assert state.x is None
    assert state.y is None


def test_load_malformed_json_returns_default(tmp_path):
    p = tmp_path / 'state.json'
    p.write_text('not valid json {{{')
    state = load_window_state(p)
    assert state.width == 1280


def test_load_partial_data_fills_missing_keys_with_defaults(tmp_path):
    p = tmp_path / 'state.json'
    p.write_text(json.dumps({'width': 1600}))
    state = load_window_state(p)
    assert state.width == 1600
    assert state.height == 800   # default kicks in
    assert state.x is None       # default


def test_save_creates_parent_directory(tmp_path):
    target = tmp_path / 'sub' / 'dir' / 'state.json'
    save_window_state(WindowState(x=0, y=0, width=100, height=100), target)
    assert target.exists()


def test_save_does_not_raise_on_permission_error(tmp_path, monkeypatch):
    """Saving must be best-effort — if we can't write, we don't crash the
    window app. A future launch just gets defaults."""
    def bad_open(*a, **kw):
        raise PermissionError('nope')
    monkeypatch.setattr('builtins.open', bad_open)
    # Should not raise.
    save_window_state(WindowState(x=0, y=0, width=100, height=100), tmp_path / 'x.json')
