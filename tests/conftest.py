"""Pytest configuration and shared fixtures for Track 2 tests.

sys.path setup ensures both src.* and shared.src.* resolve from the repo root,
mirroring the _KIT_ROOT trick used in shared/app/streamlit_app.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Repo root is one level above the tests/ directory.
# Insert at index 0 so our src/ takes priority over any installed packages.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from shared.src.loaders import load_track2  # noqa: E402


@pytest.fixture(scope="session")
def tables():
    """Session-scoped fixture that loads all 9 Track 2 parquet tables.

    Calls shared.src.loaders.load_track2 with the canonical raw data path.
    Session scope means the parquet files are read once per pytest run.
    """
    data_dir = _REPO_ROOT / "tracks" / "food-security-delivery" / "data" / "raw"
    return load_track2(data_dir)
