"""Persist window size/position across launches.

Writes a small JSON file at %LOCALAPPDATA%\\DentaCare\\window-state.json
(or wherever the caller picks). All operations are best-effort: load
errors return defaults, save errors are swallowed. The window app must
keep working even on a read-only or locked profile.
"""

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional


DEFAULT_WIDTH = 1280
DEFAULT_HEIGHT = 800

# Windows parks hidden top-level windows at coords like (-32000, -32000) and
# may report a tiny dummy size. Treat anything that crosses these thresholds
# as "the window is currently hidden, ignore its geometry."
_HIDDEN_COORD_THRESHOLD = -10000
_MIN_REAL_WIDTH = 400
_MIN_REAL_HEIGHT = 300


def is_hidden_geometry(x, y, width, height) -> bool:
    """Return True if the given window geometry looks like a hidden/minimized
    Windows window (off-screen sentinel coords or implausibly small size).
    Callers use this to skip persisting bogus state right before close."""
    if x is not None and x < _HIDDEN_COORD_THRESHOLD:
        return True
    if y is not None and y < _HIDDEN_COORD_THRESHOLD:
        return True
    if width < _MIN_REAL_WIDTH or height < _MIN_REAL_HEIGHT:
        return True
    return False


def clamp_to_screen(state: "WindowState", screen_w: int, screen_h: int) -> "WindowState":
    """Return a copy of `state` guaranteed to fit on a screen_w x screen_h work
    area (taskbar already excluded). Caps the size to the screen and pulls a
    positioned window fully back on-screen. A non-positive screen dimension means
    "unknown" (e.g. SystemParametersInfo failed) and leaves that axis untouched,
    so we never distort geometry on a guess.

    This is what stops a window sized on a large monitor from opening with its
    edges/buttons off the bottom or right of a smaller laptop screen."""
    new_w = min(state.width, screen_w) if screen_w > 0 else state.width
    new_h = min(state.height, screen_h) if screen_h > 0 else state.height
    new_x, new_y = state.x, state.y
    if screen_w > 0 and new_x is not None:
        new_x = max(0, min(new_x, screen_w - new_w))
    if screen_h > 0 and new_y is not None:
        new_y = max(0, min(new_y, screen_h - new_h))
    return WindowState(width=new_w, height=new_h, x=new_x, y=new_y)


@dataclass(frozen=True)
class WindowState:
    width: int = DEFAULT_WIDTH
    height: int = DEFAULT_HEIGHT
    x: Optional[int] = None  # None = let the WM choose (centered usually)
    y: Optional[int] = None


def load_window_state(path: Path) -> WindowState:
    """Read window state from `path`. Returns a default WindowState if the
    file is missing, malformed, or unreadable. Partial data merges over
    defaults (so a file with only {"width": 1600} returns width=1600 +
    defaults for everything else)."""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return WindowState()

    if not isinstance(data, dict):
        return WindowState()

    return WindowState(
        width=int(data.get('width', DEFAULT_WIDTH)),
        height=int(data.get('height', DEFAULT_HEIGHT)),
        x=data.get('x'),
        y=data.get('y'),
    )


def save_window_state(state: WindowState, path: Path) -> None:
    """Write window state to `path`. Best-effort: parent dir is created if
    missing; any I/O failure is swallowed (caller doesn't need to handle)."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(asdict(state), f)
    except (OSError, PermissionError):
        pass
