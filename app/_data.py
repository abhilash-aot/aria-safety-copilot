"""Shared cached data loading for all Safety Copilot pages."""

from __future__ import annotations

from datetime import date
from pathlib import Path
import sys

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import pandas as pd
import streamlit as st

from shared.src.loaders import load_track2
from src.safety.detectors import run_all
from src.optimizer.constrained_greedy import reoptimize
from src.brief.morning_brief import render_brief as _build_brief


DATA_DIR_DEFAULT = "tracks/food-security-delivery/data/raw"


@st.cache_data
def _load(data_dir: str) -> dict:
    return load_track2(data_dir)


def _detect(tables: dict, service_date: date) -> pd.DataFrame:
    return run_all(tables, service_date)


def _optimize(tables: dict, service_date: date) -> dict:
    return reoptimize(tables, service_date)


def load_all(data_dir: str = DATA_DIR_DEFAULT):
    """Return (tables_raw,) — caller applies fixes overlay."""
    return _load(data_dir)


def detect(tables: dict, service_date: date) -> pd.DataFrame:
    return _detect(tables, service_date)


def optimize(tables: dict, service_date: date) -> dict:
    return _optimize(tables, service_date)


def build_brief(service_date: date, detector_output, vrp_output: dict, tables: dict, fixes_applied: int = 0) -> dict:
    return _build_brief(service_date, detector_output, vrp_output, tables, fixes_applied=fixes_applied)


def all_service_dates(tables: dict) -> list[date]:
    return sorted(
        pd.to_datetime(tables["routes"]["service_date"]).dt.date.dropna().unique()
    )
