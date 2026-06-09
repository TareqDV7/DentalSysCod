"""Tests for window.window_state.{load,save}.

Persists the window's last x/y/width/height to a JSON file. Robust to
the file missing, being malformed, or containing partial data."""

import json
from pathlib import Path


from window.window_state import (
    is_hidden_geometry,
    load_window_state,
    save_window_state,
    WindowState,
)


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


def test_is_hidden_geometry_flags_windows_hidden_sentinel():
    # Windows parks hidden top-level windows at -32000,-32000 with a tiny size.
    assert is_hidden_geometry(-32000, -32000, 160, 28) is True


def test_is_hidden_geometry_flags_only_off_screen_x():
    assert is_hidden_geometry(-32000, 100, 1280, 800) is True


def test_is_hidden_geometry_flags_only_off_screen_y():
    assert is_hidden_geometry(100, -32000, 1280, 800) is True


def test_is_hidden_geometry_flags_implausibly_small_size():
    # No off-screen coord but dimensions too small to be a real window.
    assert is_hidden_geometry(100, 100, 200, 100) is True


def test_is_hidden_geometry_accepts_normal_windows():
    assert is_hidden_geometry(0, 0, 1280, 800) is False
    assert is_hidden_geometry(100, 200, 1600, 900) is False
    # None coords (WM-chosen) with normal size are also fine.
    assert is_hidden_geometry(None, None, 1280, 800) is False


def test_is_hidden_geometry_accepts_negative_but_on_screen_coords():
    # A window pulled slightly off the left edge is still legitimately placed;
    # only the -32000 sentinel range counts as hidden.
    assert is_hidden_geometry(-200, 100, 1280, 800) is False
