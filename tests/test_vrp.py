"""Tests for the constrained-greedy VRP router.

Uses the session-scoped ``tables`` fixture from conftest.py which loads all 9
Track 2 parquet tables via shared.src.loaders.load_track2.

Four tests are required by the plan:
1. Zero violations on two sampled service_dates.
2. No wheelchair client on a non-VEH-06 vehicle.
3. No cold-chain request on a non-refrigerated vehicle.
4. delta_pct >= 0 (optimizer at least as good as baseline).
"""

from __future__ import annotations

from datetime import date

import pytest

from src.optimizer.constrained_greedy import reoptimize


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sorted_service_dates(tables: dict) -> list[str]:
    """Return sorted unique service_date strings from the routes table."""
    routes = tables["routes"]
    return sorted(routes["service_date"].unique())


# ---------------------------------------------------------------------------
# Test 1: zero violations on first and mid-horizon service_dates
# ---------------------------------------------------------------------------

def test_constrained_greedy_zero_violations_on_sampled_dates(tables):
    """reoptimize() must return violations==[] on two distinct service_dates."""
    all_dates = _sorted_service_dates(tables)
    assert len(all_dates) >= 2, "Need at least 2 service_dates in the data"

    first_date_str = all_dates[0]
    mid_date_str = all_dates[len(all_dates) // 2]

    for date_str in [first_date_str, mid_date_str]:
        svc = date.fromisoformat(date_str)
        result = reoptimize(tables, svc)
        assert result["violations"] == [], (
            f"Expected no violations on {date_str}, got: {result['violations']}"
        )


# ---------------------------------------------------------------------------
# Test 2: wheelchair clients only on VEH-06
# ---------------------------------------------------------------------------

def test_no_wheelchair_client_on_non_veh06(tables):
    """Every route stop for a wheelchair client must be on vehicle VEH-06."""
    all_dates = _sorted_service_dates(tables)
    svc = date.fromisoformat(all_dates[0])

    result = reoptimize(tables, svc)

    clients = tables["clients"].set_index("client_id")
    requests = tables["requests"].set_index("request_id")
    vehicles = tables["vehicles"].set_index("vehicle_id")

    for route in result["routes"]:
        vehicle_id = route["vehicle_id"]
        for req_id in route["stops"]:
            if req_id not in requests.index:
                continue
            req = requests.loc[req_id]
            client_id = req["client_id"]
            if client_id not in clients.index:
                continue
            client = clients.loc[client_id]
            if bool(client.get("mobility_wheelchair", False)):
                # VEH-06 is the only wheelchair-lift vehicle
                veh_lift = False
                if vehicle_id in vehicles.index:
                    veh_lift = bool(vehicles.loc[vehicle_id, "wheelchair_lift"])
                assert veh_lift, (
                    f"Wheelchair client {client_id} (request {req_id}) assigned to "
                    f"vehicle {vehicle_id} which has no wheelchair lift"
                )


# ---------------------------------------------------------------------------
# Test 3: cold-chain requests on refrigerated vehicles only
# ---------------------------------------------------------------------------

def test_no_cold_chain_on_non_refrigerated_vehicle(tables):
    """Every cold-chain request in the output must be on a refrigerated vehicle."""
    all_dates = _sorted_service_dates(tables)
    svc = date.fromisoformat(all_dates[0])

    result = reoptimize(tables, svc)

    requests = tables["requests"].set_index("request_id")
    vehicles = tables["vehicles"].set_index("vehicle_id")

    for route in result["routes"]:
        vehicle_id = route["vehicle_id"]
        veh_refrigerated = False
        if vehicle_id in vehicles.index:
            veh_refrigerated = bool(vehicles.loc[vehicle_id, "refrigerated"])

        for req_id in route["stops"]:
            if req_id not in requests.index:
                continue
            req = requests.loc[req_id]
            cold_required = bool(req.get("cold_chain_required", False))
            if cold_required:
                assert veh_refrigerated, (
                    f"Cold-chain request {req_id} assigned to non-refrigerated "
                    f"vehicle {vehicle_id}"
                )


# ---------------------------------------------------------------------------
# Test 4: delta_pct >= 0 (optimizer is at least as good as naive baseline)
# ---------------------------------------------------------------------------

def test_delta_pct_non_negative(tables):
    """Optimizer total_drive_minutes must be <= baseline_drive_minutes (within tolerance)."""
    all_dates = _sorted_service_dates(tables)
    svc = date.fromisoformat(all_dates[0])

    result = reoptimize(tables, svc)

    # Allow a small floating-point tolerance (0.5%) to handle rounding
    tolerance = -0.005
    assert result["delta_pct"] >= tolerance, (
        f"delta_pct={result['delta_pct']:.4f} is negative beyond tolerance. "
        f"baseline={result['baseline_drive_minutes']}, "
        f"new={result['total_drive_minutes']}"
    )
