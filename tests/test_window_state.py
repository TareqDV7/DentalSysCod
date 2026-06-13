"""Tests for window.window_state.{load,save}.

Persists the window's last x/y/width/height to a JSON file. Robust to
the file missing, being malformed, or containing partial data."""

import json
from pathlib import Path


from window.window_state import (
    clamp_to_screen,
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


# ── clamp_to_screen ─────────────────────────────────────────────────────────

def test_clamp_shrinks_window_larger_than_screen():
    # A 1600x900 window saved on a big monitor, now opened on a 1366x768 screen
    # (work area ~1366x728 after the taskbar) must shrink to fit.
    state = WindowState(x=0, y=0, width=1600, height=900)
    clamped = clamp_to_screen(state, 1366, 728)
    assert clamped.width == 1366
    assert clamped.height == 728


def test_clamp_leaves_window_that_already_fits():
    # 50+1200=1250 <= 1366 and 40+600=640 <= 728, so nothing needs to move.
    state = WindowState(x=50, y=40, width=1200, height=600)
    clamped = clamp_to_screen(state, 1366, 728)
    assert clamped == state


def test_clamp_repositions_window_pushed_off_screen():
    # Saved far to the right of a wider monitor; on the small screen the window
    # would start beyond the right edge — pull it back fully on-screen.
    state = WindowState(x=1500, y=600, width=1000, height=700)
    clamped = clamp_to_screen(state, 1366, 728)
    assert clamped.width == 1000
    assert clamped.height == 700
    assert clamped.x + clamped.width <= 1366
    assert clamped.y + clamped.height <= 728
    assert clamped.x >= 0 and clamped.y >= 0


def test_clamp_unknown_screen_size_is_noop():
    # SystemParametersInfo can fail (returns 0,0) — never distort geometry then.
    state = WindowState(x=10, y=10, width=1600, height=900)
    assert clamp_to_screen(state, 0, 0) == state


def test_clamp_preserves_none_position():
    # WM-chosen position (None) stays None — only size is capped.
    state = WindowState(x=None, y=None, width=1600, height=900)
    clamped = clamp_to_screen(state, 1280, 720)
    assert clamped.width == 1280
    assert clamped.height == 720
    assert clamped.x is None
    assert clamped.y is None
