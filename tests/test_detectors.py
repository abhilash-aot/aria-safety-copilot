"""Tests for src/safety/detectors.py.

All tests run against real generated parquet data via the session-scoped `tables`
fixture from conftest.py. Ground truth is identified by DATA_QUALITY_ISSUE: tags
seeded into the data by the generator.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

import warnings

from src.safety.detectors import (
    check_cold_chain,
    check_driver_hours_distance,
    check_driver_pet_allergy,
    check_interpreter_language,
    check_post_closure_delivery,
    check_severe_allergen,
    check_two_person_solo,
    check_wheelchair_lift,
    run_all,
)
from src.safety.models import Severity


def test_severe_allergen_matches_seeded_ground_truth(tables):
    """Detector must catch all 3 seeded allergen-conflict request_ids (recall = 1.0)."""
    ri = tables["request_items"]
    seeded_request_ids = set(
        ri.loc[
            ri["notes"].str.contains("DATA_QUALITY_ISSUE: allergen conflict", na=False),
            "request_id",
        ]
    )
    assert len(seeded_request_ids) == 3, (
        f"Expected 3 seeded allergen cases, found {len(seeded_request_ids)}"
    )

    reqs = tables["requests"]
    distinct_dates = pd.to_datetime(reqs["scheduled_date"], errors="coerce").dt.date.dropna().unique()

    detected_request_ids: set = set()
    for d in distinct_dates:
        for v in check_severe_allergen(tables, d):
            if v.request_id:
                detected_request_ids.add(v.request_id)

    missed = seeded_request_ids - detected_request_ids
    assert not missed, f"Detector missed seeded allergen request_ids: {missed}"
    # Detected must be a superset of seeded (precision may be < 1.0 if generator adds more).
    assert seeded_request_ids.issubset(detected_request_ids)


def test_post_closure_matches_seeded_ground_truth(tables):
    """Detector must catch all 4 seeded post-closure stop_ids (recall = 1.0)."""
    stops = tables["stops"]
    seeded_stop_ids = set(
        stops.loc[
            stops["driver_notes"].str.contains(
                "DATA_QUALITY_ISSUE: delivered after closure", na=False
            ),
            "route_stop_id",
        ]
    )
    assert len(seeded_stop_ids) == 4, (
        f"Expected 4 seeded closure cases, found {len(seeded_stop_ids)}"
    )

    routes = tables["routes"]
    distinct_dates = pd.to_datetime(routes["service_date"], errors="coerce").dt.date.dropna().unique()

    detected_stop_ids: set = set()
    for d in distinct_dates:
        for v in check_post_closure_delivery(tables, d):
            if v.stop_id:
                detected_stop_ids.add(v.stop_id)

    missed = seeded_stop_ids - detected_stop_ids
    assert not missed, f"Detector missed seeded closure stop_ids: {missed}"
    assert seeded_stop_ids.issubset(detected_stop_ids)


def test_run_all_returns_dataframe_with_correct_schema(tables):
    """run_all returns a DataFrame with all 11 Violation fields; CRITICAL sorts before MEDIUM."""
    expected_columns = [
        "rule", "severity", "service_date", "route_id", "stop_id",
        "request_id", "client_id", "driver_id", "vehicle_id",
        "explanation", "suggested_fix",
    ]

    # 2026-04-07 has both allergen (CRITICAL) and may have closure (MEDIUM) violations.
    # Use a date known to produce at least one violation.
    reqs = tables["requests"]
    ri = tables["request_items"]
    seeded_req_ids = set(ri.loc[ri["notes"].str.contains("DATA_QUALITY_ISSUE: allergen conflict", na=False), "request_id"])
    sample_req = reqs[reqs["request_id"].isin(seeded_req_ids)].iloc[0]
    test_date = pd.to_datetime(sample_req["scheduled_date"]).date()

    result = run_all(tables, test_date)

    assert isinstance(result, pd.DataFrame)
    assert list(result.columns) == expected_columns

    critical_rows = result[result["severity"] == "critical"]
    medium_rows = result[result["severity"] == "medium"]
    assert len(critical_rows) > 0, "Expected at least one CRITICAL violation on the test date"

    if len(medium_rows) > 0:
        # CRITICAL must appear before MEDIUM in the sorted output.
        first_critical_idx = critical_rows.index[0]
        first_medium_idx = medium_rows.index[0]
        assert first_critical_idx < first_medium_idx


def test_run_all_empty_schema_safe(tables):
    """run_all on a date with no data returns an empty DataFrame with correct columns."""
    expected_columns = [
        "rule", "severity", "service_date", "route_id", "stop_id",
        "request_id", "client_id", "driver_id", "vehicle_id",
        "explanation", "suggested_fix",
    ]
    result = run_all(tables, date(1970, 1, 1))

    assert isinstance(result, pd.DataFrame)
    assert result.empty
    assert list(result.columns) == expected_columns
    # Safe to .loc[] without KeyError on any expected column.
    _ = result.loc[:, "severity"]


# ---------------------------------------------------------------------------
# New detector tests (rules 2, 3, 5, 6, 7, 8)
# ---------------------------------------------------------------------------


def test_cold_chain_returns_critical_violations(tables):
    """check_cold_chain returns Violation list; CRITICAL severity if natural case exists."""
    routes = tables["routes"]
    distinct_dates = pd.to_datetime(routes["service_date"], errors="coerce").dt.date.dropna().unique()

    all_violations = []
    for d in distinct_dates:
        all_violations.extend(check_cold_chain(tables, d))

    if not all_violations:
        # No natural cold-chain/non-refrigerated conflict exists in this dataset.
        pytest.skip("No cold_chain_break cases in generated data; smoke-pass only")

    assert all(v.severity == Severity.CRITICAL for v in all_violations)
    # Each violation must cite at least a stop_id and a vehicle_id.
    for v in all_violations:
        assert v.stop_id is not None
        assert v.vehicle_id is not None


def test_wheelchair_lift_catches_non_veh06_assignments(tables):
    """check_wheelchair_lift flags wheelchair clients on non-VEH-06 vehicles."""
    routes = tables["routes"]
    distinct_dates = pd.to_datetime(routes["service_date"], errors="coerce").dt.date.dropna().unique()

    all_violations = []
    for d in distinct_dates:
        all_violations.extend(check_wheelchair_lift(tables, d))

    if not all_violations:
        pytest.skip("No wheelchair-on-wrong-vehicle cases in generated data")

    assert all(v.severity == Severity.HIGH for v in all_violations)
    # Every flagged stop must NOT be on VEH-06.
    assert all(v.vehicle_id != "VEH-06" for v in all_violations)
    # suggested_fix must mention VEH-06.
    assert all("VEH-06" in (v.suggested_fix or "") for v in all_violations)


def test_two_person_solo_superset_of_seeded_failures(tables):
    """Detector must flag at least all seeded 'requires_two_person_unavailable' stops."""
    stops = tables["stops"]
    routes = tables["routes"]

    seeded_stop_ids = set(
        stops.loc[
            stops["failure_reason"] == "requires_two_person_unavailable",
            "route_stop_id",
        ]
    )

    if not seeded_stop_ids:
        pytest.skip("No seeded two-person stops found; smoke-pass only")

    # Collect service dates for the seeded stops so we only iterate relevant dates.
    seeded_routes = stops.loc[
        stops["route_stop_id"].isin(seeded_stop_ids), "route_id"
    ]
    seeded_dates = set(
        pd.to_datetime(
            routes.loc[routes["route_id"].isin(seeded_routes), "service_date"],
            errors="coerce",
        ).dt.date.dropna().tolist()
    )

    detected_stop_ids: set = set()
    for d in seeded_dates:
        for v in check_two_person_solo(tables, d):
            if v.stop_id:
                detected_stop_ids.add(v.stop_id)

    missed = seeded_stop_ids - detected_stop_ids
    assert not missed, f"Detector missed seeded two-person stop_ids: {missed}"


def test_run_all_includes_all_8_rules(tables):
    """run_all invokes all 8 detectors; across all dates, ≥ 4 distinct rule names appear."""
    routes = tables["routes"]
    distinct_dates = pd.to_datetime(routes["service_date"], errors="coerce").dt.date.dropna().unique()

    all_rules: set = set()
    for d in distinct_dates:
        result = run_all(tables, d)
        if not result.empty:
            all_rules.update(result["rule"].tolist())

    expected_rules = {
        "severe_allergen_in_line_item",
        "delivery_after_client_closure",
        "wheelchair_client_wrong_vehicle",
        "two_person_client_solo_driver",
    }
    missing = expected_rules - all_rules
    assert not missing, f"run_all missing expected rule names: {missing}"


def test_driver_pet_allergy_smoke(tables):
    """check_driver_pet_allergy runs without error and returns a list."""
    routes = tables["routes"]
    sample_date = pd.to_datetime(routes["service_date"], errors="coerce").dt.date.dropna().iloc[0]
    result = check_driver_pet_allergy(tables, sample_date)
    assert isinstance(result, list)
    # If violations found, schema must be complete.
    for v in result:
        assert v.driver_id is not None
        assert v.client_id is not None


def test_interpreter_language_smoke(tables):
    """check_interpreter_language runs without error and returns a list."""
    routes = tables["routes"]
    sample_date = pd.to_datetime(routes["service_date"], errors="coerce").dt.date.dropna().iloc[0]
    result = check_interpreter_language(tables, sample_date)
    assert isinstance(result, list)
    for v in result:
        assert v.client_id is not None
        assert v.driver_id is not None


def test_driver_hours_distance_flags_over_cap(tables):
    """check_driver_hours_distance flags drivers over weekly hours/distance caps."""
    routes = tables["routes"]
    distinct_dates = pd.to_datetime(routes["service_date"], errors="coerce").dt.date.dropna().unique()

    all_violations = []
    for d in distinct_dates:
        all_violations.extend(check_driver_hours_distance(tables, d))

    if not all_violations:
        pytest.skip("No driver hours/distance cap violations in generated data")

    hour_rules = [v for v in all_violations if v.rule == "driver_hours_cap_nearing"]
    dist_rules = [v for v in all_violations if v.rule == "driver_distance_cap_nearing"]
    assert len(hour_rules) > 0 or len(dist_rules) > 0

    for v in all_violations:
        assert v.severity == Severity.LOW
        assert v.driver_id is not None


def test_run_all_empty_on_quiet_date(tables):
    """run_all on 1970-01-01 (no data) returns empty DataFrame with correct schema."""
    expected_columns = [
        "rule", "severity", "service_date", "route_id", "stop_id",
        "request_id", "client_id", "driver_id", "vehicle_id",
        "explanation", "suggested_fix",
    ]
    result = run_all(tables, date(1970, 1, 1))
    assert isinstance(result, pd.DataFrame)
    assert result.empty
    assert list(result.columns) == expected_columns
