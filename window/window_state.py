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
