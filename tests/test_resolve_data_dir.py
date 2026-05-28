"""Tests for window.data_dir.resolve_data_dir.

Three rules in priority order:
  1. CLINIC_DATA_DIR env var (used by Docker / cloud node)
  2. Frozen exe with no env var -> %ProgramData%\\DentaCare
  3. Running from source -> directory containing the .py file
"""
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from window.data_dir import resolve_data_dir


def test_env_var_wins_when_set(tmp_path, monkeypatch):
    monkeypatch.setenv('CLINIC_DATA_DIR', str(tmp_path / 'override'))
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, 'executable', str(tmp_path / 'never_used.exe'))
    assert resolve_data_dir() == tmp_path / 'override'


def test_env_var_wins_even_with_whitespace(tmp_path, monkeypatch):
    monkeypatch.setenv('CLINIC_DATA_DIR', f'  {tmp_path / "override"}  ')
    assert resolve_data_dir() == tmp_path / 'override'


def test_env_var_empty_string_treated_as_unset(tmp_path, monkeypatch):
    monkeypatch.setenv('CLINIC_DATA_DIR', '')
    monkeypatch.setattr(sys, 'frozen', False, raising=False)
    script_dir = Path(__file__).parent.parent
    assert resolve_data_dir() == script_dir


def test_frozen_no_env_uses_programdata(monkeypatch, tmp_path):
    monkeypatch.delenv('CLINIC_DATA_DIR', raising=False)
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setenv('PROGRAMDATA', str(tmp_path))
    assert resolve_data_dir() == tmp_path / 'DentaCare'


def test_frozen_no_env_no_programdata_falls_back_to_appdata(monkeypatch, tmp_path):
    monkeypatch.delenv('CLINIC_DATA_DIR', raising=False)
    monkeypatch.delenv('PROGRAMDATA', raising=False)
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))
    # Fallback for unusual Windows installs where ProgramData isn't set.
    assert resolve_data_dir() == tmp_path / 'DentaCare'


def test_source_run_uses_script_directory(monkeypatch):
    monkeypatch.delenv('CLINIC_DATA_DIR', raising=False)
    monkeypatch.setattr(sys, 'frozen', False, raising=False)
    expected = Path(__file__).parent.parent  # the repo root
    assert resolve_data_dir() == expected
