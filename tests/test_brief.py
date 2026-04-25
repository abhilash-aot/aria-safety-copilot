"""Tests for src/brief/morning_brief.py — templated morning brief.

All tests use the session-scoped `tables` fixture from conftest.py.
Service date is the first real date found in tables['routes']['service_date'].
"""

from __future__ import annotations

import re
from datetime import date

import pandas as pd
import pytest

from src.brief.morning_brief import render_brief
from src.optimizer.constrained_greedy import reoptimize
from src.safety.detectors import run_all

# Regex for at least one concrete ID in a bullet.
_ID_RE = re.compile(r"(REQ-|MOW-|DRV-|VEH-|RTE-|STP-|DEP-|CLI-)")


def _first_service_date(tables: dict) -> date:
    """Return the first real service_date from routes, as a date object."""
    dates = tables["routes"]["service_date"].dropna().unique()
    date_str = sorted(dates)[0]
    return pd.to_datetime(date_str).date()


def _get_brief(tables: dict, service_date: date | None = None) -> dict:
    if service_date is None:
        service_date = _first_service_date(tables)
    detector_output = run_all(tables, service_date)
    vrp_output = reoptimize(tables, service_date)
    return render_brief(service_date, detector_output, vrp_output, tables)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_brief_paragraph_word_count(tables):
    result = _get_brief(tables)
    words = result["paragraph"].split()
    assert 60 <= len(words) <= 150, (
        f"Paragraph word count {len(words)} outside [60, 150]: {result['paragraph']!r}"
    )


def test_brief_has_exactly_three_bullets(tables):
    result = _get_brief(tables)
    assert len(result["bullets"]) == 3, (
        f"Expected 3 bullets, got {len(result['bullets'])}: {result['bullets']}"
    )


def test_every_bullet_has_concrete_id(tables):
    result = _get_brief(tables)
    for bullet in result["bullets"]:
        assert _ID_RE.search(bullet), (
            f"Bullet has no concrete ID (REQ-/MOW-/DRV-/VEH-/RTE-/STP-/DEP-): {bullet!r}"
        )


def test_brief_no_violations_fallback(tables):
    """Empty detector output (no-data date) must still produce 3 valid bullets."""
    no_data_date = date(1970, 1, 1)
    empty_detector = pd.DataFrame(
        columns=[
            "rule", "severity", "service_date", "route_id", "stop_id",
            "request_id", "client_id", "driver_id", "vehicle_id",
            "explanation", "suggested_fix",
        ]
    )
    # reoptimize on an unknown date returns a minimal valid dict.
    try:
        vrp_output = reoptimize(tables, no_data_date)
    except Exception:
        vrp_output = {
            "routes": [],
            "dropped_requests": [],
            "total_drive_minutes": 0,
            "baseline_drive_minutes": 0,
            "delta_pct": 0.0,
            "projected_on_time_rate": 1.0,
            "violations": [],
        }

    result = render_brief(no_data_date, empty_detector, vrp_output, tables)

    assert len(result["bullets"]) == 3, (
        f"Expected 3 bullets in fallback, got {len(result['bullets'])}"
    )
    for bullet in result["bullets"]:
        assert _ID_RE.search(bullet), (
            f"Fallback bullet has no concrete ID: {bullet!r}"
        )


def test_brief_paragraph_mentions_date(tables):
    service_date = _first_service_date(tables)
    result = _get_brief(tables, service_date)
    paragraph = result["paragraph"]

    day_name = service_date.strftime("%A")       # e.g. "Wednesday"
    month_name = service_date.strftime("%B")     # e.g. "March"

    assert day_name in paragraph, (
        f"Day-of-week '{day_name}' not found in paragraph: {paragraph!r}"
    )
    assert month_name in paragraph, (
        f"Month name '{month_name}' not found in paragraph: {paragraph!r}"
    )
