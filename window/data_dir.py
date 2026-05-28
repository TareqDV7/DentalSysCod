"""Data directory resolution.

Three rules in priority order:
  1. CLINIC_DATA_DIR env var (whitespace trimmed; empty string ignored)
  2. Frozen exe with no env var -> %ProgramData%\\DentaCare (Windows-standard
     machine-wide app-data location, writable by the service account)
  3. Running from source -> the script's own directory (today's behavior,
     preserved so dev workflow is unchanged)

The "frozen + no env + no PROGRAMDATA" branch falls back to %LOCALAPPDATA%
so the function never raises on unusual Windows installs.
"""

import os
import sys
from pathlib import Path


def resolve_data_dir() -> Path:
    """Return the directory the app should use for DB, uploads, backups, logs."""
    env_value = os.environ.get('CLINIC_DATA_DIR', '').strip()
    if env_value:
        return Path(env_value)

    if getattr(sys, 'frozen', False):
        program_data = os.environ.get('PROGRAMDATA', '').strip()
        if program_data:
            return Path(program_data) / 'DentaCare'
        local_app_data = os.environ.get('LOCALAPPDATA', '').strip()
        if local_app_data:
            return Path(local_app_data) / 'DentaCare'
        # Last-ditch: home directory.
        return Path.home() / 'DentaCare'

    # Source / dev mode: directory containing dental_clinic.py (the repo root).
    # We resolve via the package's own __file__ since this module lives in
    # window/ — one level under the repo root.
    return Path(__file__).resolve().parent.parent
