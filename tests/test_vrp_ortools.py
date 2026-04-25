"""Tests for the OR-Tools VRP solver (src/optimizer/vrp.py).

All tests use the session-scoped `tables` fixture from conftest.py.
The time_limit_seconds=3 override keeps the full suite well under 2 minutes.
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.optimizer.vrp import reoptimize


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sorted_dates(tables: dict) -> list:
    return sorted(
        pd.to_datetime(tables["routes"]["service_date"]).dt.date.dropna().unique()
    )


_REQUIRED_KEYS = {
    "routes",
    "dropped_requests",
    "total_drive_minutes",
    "baseline_drive_minutes",
    "delta_pct",
    "projected_on_time_rate",
    "violations",
}


# ---------------------------------------------------------------------------
# 1. Dict shape
# ---------------------------------------------------------------------------

def test_ortools_returns_correct_dict_shape(tables):
    dates = _sorted_dates(tables)
    d = dates[len(dates) // 2]
    result = reoptimize(tables, d, time_limit_seconds=3)
    assert set(result.keys()) == _REQUIRED_KEYS, f"Missing keys: {_REQUIRED_KEYS - set(result.keys())}"
    assert isinstance(result["routes"], list)
    assert isinstance(result["dropped_requests"], list)
    assert isinstance(result["total_drive_minutes"], int)
    assert isinstance(result["baseline_drive_minutes"], int)
    assert isinstance(result["delta_pct"], float)
    assert isinstance(result["projected_on_time_rate"], float)
    assert isinstance(result["violations"], list)


# ---------------------------------------------------------------------------
# 2. Zero violations on sampled dates
# ---------------------------------------------------------------------------

def test_ortools_zero_violations_on_sampled_dates(tables):
    dates = _sorted_dates(tables)
    sampled = [dates[0], dates[len(dates) // 2], dates[-1]]
    for d in sampled:
        result = reoptimize(tables, d, time_limit_seconds=3)
        assert result["violations"] == [], f"Expected no violations on {d}, got {result['violations']}"


# ---------------------------------------------------------------------------
# 3. Wheelchair constraint: any assigned wheelchair client must use VEH-06
# ---------------------------------------------------------------------------

def test_ortools_respects_wheelchair_constraint(tables):
    clients = tables["clients"]
    reqs = tables["requests"]
    wc_client_ids = set(clients[clients["mobility_wheelchair"] == True]["client_id"].tolist())

    dates = _sorted_dates(tables)
    # Check across first, middle, last dates to maximise chance of hitting wc assignments
    for d in [dates[0], dates[len(dates) // 2], dates[-1]]:
        result = reoptimize(tables, d, time_limit_seconds=3)
        for route in result["routes"]:
            for req_id in route["stops"]:
                req_row = reqs[reqs["request_id"] == req_id]
                if req_row.empty:
                    continue
                cid = req_row.iloc[0]["client_id"]
                if cid in wc_client_ids:
                    assert route["vehicle_id"] == "VEH-06", (
                        f"Wheelchair client {cid} assigned to {route['vehicle_id']} "
                        f"on {d} — must be VEH-06"
                    )


# ---------------------------------------------------------------------------
# 4. Cold chain: refrigerated vehicle required
# ---------------------------------------------------------------------------

def test_ortools_respects_cold_chain(tables):
    reqs = tables["requests"]
    vehicles = tables["vehicles"]
    refrigerated_veh_ids = set(
        vehicles[vehicles["refrigerated"] == True]["vehicle_id"].tolist()
    )

    dates = _sorted_dates(tables)
    for d in [dates[0], dates[len(dates) // 2], dates[-1]]:
        result = reoptimize(tables, d, time_limit_seconds=3)
        for route in result["routes"]:
            for req_id in route["stops"]:
                req_row = reqs[reqs["request_id"] == req_id]
                if req_row.empty:
                    continue
                cold = bool(req_row.iloc[0].get("cold_chain_required", False))
                if cold:
                    assert route["vehicle_id"] in refrigerated_veh_ids, (
                        f"Cold-chain request {req_id} assigned to non-refrigerated "
                        f"vehicle {route['vehicle_id']} on {d}"
                    )


# ---------------------------------------------------------------------------
# 5. Disruption: removed driver never appears in output
# ---------------------------------------------------------------------------

def test_ortools_disruption_still_feasible(tables):
    dates = _sorted_dates(tables)
    d = dates[len(dates) // 2]

    # Pick a real driver present on this date
    day_routes = tables["routes"][tables["routes"]["service_date"] == d.isoformat()]
    if day_routes.empty:
        pytest.skip(f"No routes on {d}")

    removed_driver = day_routes["driver_id"].iloc[0]
    result = reoptimize(tables, d, disruption={"driver_out": removed_driver}, time_limit_seconds=3)

    # Must return a valid dict (no exception)
    assert set(result.keys()) == _REQUIRED_KEYS

    # Removed driver must not appear in any route
    for route in result["routes"]:
        assert route["driver_id"] != removed_driver, (
            f"Removed driver {removed_driver} still appears in routes on {d}"
        )
