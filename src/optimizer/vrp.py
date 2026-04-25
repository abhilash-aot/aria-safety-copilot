"""OR-Tools VRP solver for Track 2 — Food Security Delivery.

Drop-in replacement for src.optimizer.constrained_greedy with the same
public API: reoptimize(tables, service_date, disruption=None) -> dict.

Pre-filtering (closed clients, severe allergens) runs before the model.
Hard constraints (capacity, cold chain, wheelchair, skill/language/pet,
driving-time cap, max stops) are wired into the OR-Tools model so the
solution is safe-by-construction.  Any request the solver cannot assign
feasibly is dropped via an AddDisjunction penalty rather than violating a
constraint.
"""

from __future__ import annotations

import logging
import math
from datetime import date
from typing import Optional

import pandas as pd
from ortools.constraint_solver import pywrapcp, routing_enums_pb2

from src.optimizer.baseline import score_baseline
from src.optimizer.constrained_greedy import (
    _build_allergen_blocked_request_ids,
    _driver_language_ok,
    _driver_pet_ok,
    _driver_satisfies_skills,
    _haversine,
    WEEKLY_SHIFT_BUDGET,
)
from src.safety.models import Violation

logger = logging.getLogger(__name__)

_DROP_PENALTY = 1_000_000  # large enough that dropping is always worse than any real arc
_SPEED_KMH = 30.0          # urban speed assumption, same as constrained_greedy
# OR-Tools needs integer costs; scale minutes by 10 to preserve sub-minute precision
_MINUTES_SCALE = 10


def _drive_minutes_int(dist_km: float) -> int:
    """Return drive time in tenths-of-a-minute (int) for OR-Tools cost matrix."""
    raw = (dist_km / _SPEED_KMH) * 60.0 * _MINUTES_SCALE
    return max(1, int(round(raw)))


def _build_distance_matrix(coords: list[tuple[float, float]]) -> list[list[int]]:
    """Haversine distance matrix → int drive-minutes (scaled by _MINUTES_SCALE)."""
    n = len(coords)
    mat = [[0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i != j:
                dist_km = _haversine(coords[i][0], coords[i][1], coords[j][0], coords[j][1])
                mat[i][j] = _drive_minutes_int(dist_km)
    return mat


def reoptimize(
    tables: dict,
    service_date: date,
    disruption: Optional[dict] = None,
    time_limit_seconds: int = 10,
) -> dict:
    """OR-Tools VRP solver — same return shape as constrained_greedy.reoptimize.

    Returns:
        {
            "routes": list[{driver_id, vehicle_id, stops: [request_id, ...]}],
            "dropped_requests": list[request_id],
            "total_drive_minutes": int,
            "baseline_drive_minutes": int,
            "delta_pct": float,
            "projected_on_time_rate": float,
            "violations": list[Violation],   # guaranteed empty
        }

    time_limit_seconds is exposed so tests can pass a smaller value without
    touching the production default of 10 s.
    """
    service_date_str = service_date.isoformat() if isinstance(service_date, date) else str(service_date)
    service_dt = service_date if isinstance(service_date, date) else pd.to_datetime(service_date).date()

    routes_tbl = tables["routes"]
    requests_tbl = tables["requests"]
    clients_tbl = tables["clients"]
    drivers_tbl = tables["drivers"]
    vehicles_tbl = tables["vehicles"]
    depots_tbl = tables["depots"]

    # ------------------------------------------------------------------
    # 1. Baseline for delta comparison (unchanged from constrained_greedy)
    # ------------------------------------------------------------------
    baseline_result = score_baseline(tables, service_date)
    baseline_drive_minutes = baseline_result["total_drive_minutes"]

    # ------------------------------------------------------------------
    # 2. Active requests (same two-source logic as constrained_greedy)
    # ------------------------------------------------------------------
    day_routes = routes_tbl[routes_tbl["service_date"] == service_date_str]
    day_route_ids = set(day_routes["route_id"].tolist())

    reqs_via_route = requests_tbl[
        requests_tbl["assigned_route_id"].isin(day_route_ids)
        & requests_tbl["status"].isin(["pending", "scheduled"])
    ]
    reqs_via_sched = requests_tbl[
        (requests_tbl["scheduled_date"] == service_date_str)
        & requests_tbl["status"].isin(["pending", "scheduled"])
        & (~requests_tbl["request_id"].isin(reqs_via_route["request_id"]))
    ]
    all_reqs = pd.concat([reqs_via_route, reqs_via_sched], ignore_index=True)

    def _empty(dropped=None, on_time=1.0):
        return {
            "routes": [],
            "dropped_requests": dropped or [],
            "total_drive_minutes": 0,
            "baseline_drive_minutes": baseline_drive_minutes,
            "delta_pct": 0.0,
            "projected_on_time_rate": on_time,
            "violations": [],
        }

    if all_reqs.empty:
        return _empty()

    # ------------------------------------------------------------------
    # 3. Join client info
    # ------------------------------------------------------------------
    all_reqs = all_reqs.merge(clients_tbl, on="client_id", how="left", suffixes=("", "_client"))

    # ------------------------------------------------------------------
    # 4. Drop closed/deceased clients where closure_date < service_date
    # ------------------------------------------------------------------
    def _is_closed(row: pd.Series) -> bool:
        status = str(row.get("enrolment_status", "") or "").lower()
        if status not in {"closed", "deceased"}:
            return False
        closure_raw = row.get("closure_date")
        if closure_raw is None or pd.isna(closure_raw):
            return True
        try:
            closure = pd.to_datetime(closure_raw, dayfirst=False, errors="coerce")
            if pd.isna(closure):
                return True
            return closure.date() < service_dt
        except Exception:
            return True

    drop_mask_closed = all_reqs.apply(_is_closed, axis=1)
    dropped_closed = all_reqs.loc[drop_mask_closed, "request_id"].tolist()
    all_reqs = all_reqs[~drop_mask_closed].copy()

    # ------------------------------------------------------------------
    # 5. Drop severe-allergen conflicts
    # ------------------------------------------------------------------
    allergen_blocked = _build_allergen_blocked_request_ids(tables)
    drop_mask_allergen = all_reqs["request_id"].isin(allergen_blocked)
    dropped_allergen = all_reqs.loc[drop_mask_allergen, "request_id"].tolist()
    all_reqs = all_reqs[~drop_mask_allergen].copy()

    all_dropped_pre = dropped_closed + dropped_allergen

    if all_reqs.empty:
        return _empty(dropped=all_dropped_pre)

    # ------------------------------------------------------------------
    # 6. Build candidate (driver, vehicle) pool — identical logic to
    #    constrained_greedy steps 6–8
    # ------------------------------------------------------------------
    removed_drivers: set = set()
    if disruption and "driver_out" in disruption:
        removed_drivers.add(disruption["driver_out"])

    if day_routes.empty:
        candidate_drivers = drivers_tbl[~drivers_tbl["driver_id"].isin(removed_drivers)].copy()
    else:
        driver_ids_today = set(day_routes["driver_id"].tolist()) - removed_drivers
        candidate_drivers = drivers_tbl[drivers_tbl["driver_id"].isin(driver_ids_today)].copy()
        if candidate_drivers.empty:
            candidate_drivers = drivers_tbl[~drivers_tbl["driver_id"].isin(removed_drivers)].copy()

    # Weekly cap
    service_week = service_dt.isocalendar()[1]
    service_year = service_dt.isocalendar()[0]

    def _iso_week_year(d_str: str):
        try:
            d = pd.to_datetime(d_str).date()
            iso = d.isocalendar()
            return (iso[0], iso[1])
        except Exception:
            return (None, None)

    routes_with_week = routes_tbl.copy()
    routes_with_week["_wy"] = routes_with_week["service_date"].map(_iso_week_year)
    same_week_routes = routes_with_week[routes_with_week["_wy"] == (service_year, service_week)]
    prior_routes = same_week_routes[same_week_routes["service_date"] != service_date_str]
    weekly_minutes_used = (
        prior_routes.groupby("driver_id")["planned_time_minutes"].sum()
        .rename("weekly_minutes_used")
    )
    candidate_drivers = candidate_drivers.merge(weekly_minutes_used, on="driver_id", how="left")
    candidate_drivers["weekly_minutes_used"] = candidate_drivers["weekly_minutes_used"].fillna(0)
    candidate_drivers = candidate_drivers[
        candidate_drivers["weekly_minutes_used"]
        < candidate_drivers["max_hours"] * 60 * WEEKLY_SHIFT_BUDGET
    ].copy()

    if candidate_drivers.empty:
        return _empty(dropped=all_dropped_pre + all_reqs["request_id"].tolist(), on_time=0.0)

    # Assign vehicle to each driver
    driver_vehicle_today = (
        day_routes[["driver_id", "vehicle_id"]]
        .drop_duplicates("driver_id")
        .set_index("driver_id")["vehicle_id"]
    )

    def _get_vehicle_for_driver(drv_id: str) -> str:
        if drv_id in driver_vehicle_today.index:
            return driver_vehicle_today[drv_id]
        row = drivers_tbl[drivers_tbl["driver_id"] == drv_id]
        if not row.empty and pd.notna(row.iloc[0]["vehicle_id"]):
            return row.iloc[0]["vehicle_id"]
        return ""

    candidate_drivers = candidate_drivers.copy()
    candidate_drivers["assigned_vehicle_id"] = candidate_drivers["driver_id"].map(_get_vehicle_for_driver)

    veh_indexed = vehicles_tbl.set_index("vehicle_id")
    candidate_drivers["veh_refrigerated"] = candidate_drivers["assigned_vehicle_id"].map(
        lambda v: bool(veh_indexed.loc[v, "refrigerated"]) if v in veh_indexed.index else False
    )
    candidate_drivers["veh_wheelchair_lift"] = candidate_drivers["assigned_vehicle_id"].map(
        lambda v: bool(veh_indexed.loc[v, "wheelchair_lift"]) if v in veh_indexed.index else False
    )
    candidate_drivers["veh_capacity_meals"] = candidate_drivers["assigned_vehicle_id"].map(
        lambda v: int(veh_indexed.loc[v, "capacity_meals"]) if v in veh_indexed.index else 0
    )

    candidate_drivers = candidate_drivers[candidate_drivers["assigned_vehicle_id"] != ""].copy()
    if candidate_drivers.empty:
        return _empty(dropped=all_dropped_pre + all_reqs["request_id"].tolist(), on_time=0.0)

    # Depot coordinates
    depots_indexed = depots_tbl.set_index("depot_id")[["lat", "lng"]]
    route_depot_map = (
        day_routes[["driver_id", "start_depot_id"]]
        .drop_duplicates("driver_id")
        .set_index("driver_id")["start_depot_id"]
    ) if not day_routes.empty else pd.Series(dtype=str)

    def _depot_for_driver(drv_id: str) -> str:
        if drv_id in route_depot_map.index:
            return route_depot_map[drv_id]
        drv_row = drivers_tbl[drivers_tbl["driver_id"] == drv_id]
        if not drv_row.empty:
            return str(drv_row.iloc[0].get("home_base_depot_id", "DEP-01") or "DEP-01")
        return "DEP-01"

    candidate_drivers = candidate_drivers.copy()
    candidate_drivers["depot_id"] = candidate_drivers["driver_id"].map(_depot_for_driver)

    # ------------------------------------------------------------------
    # 7. Build node coordinate list for OR-Tools.
    #    Node 0 = single shared depot (most-used for this date).
    #    Nodes 1..N = one per active request.
    # ------------------------------------------------------------------
    clients_indexed = clients_tbl.set_index("client_id")

    # Pick primary depot
    if not day_routes.empty and "start_depot_id" in day_routes.columns:
        depot_counts = day_routes["start_depot_id"].value_counts()
        primary_depot_id = depot_counts.index[0] if not depot_counts.empty else "DEP-01"
    else:
        primary_depot_id = "DEP-01"

    depot_lat = float(depots_indexed.loc[primary_depot_id, "lat"]) if primary_depot_id in depots_indexed.index else 48.43
    depot_lng = float(depots_indexed.loc[primary_depot_id, "lng"]) if primary_depot_id in depots_indexed.index else -123.37

    # Build request list — skip requests with no usable coordinates
    req_records: list[dict] = []
    for _, row in all_reqs.iterrows():
        cid = row.get("client_id")
        if cid and cid in clients_indexed.index:
            c = clients_indexed.loc[cid]
            lat = float(c.get("lat", 0.0) or 0.0)
            lng = float(c.get("lng", 0.0) or 0.0)
            client_row = c
        else:
            lat, lng = 0.0, 0.0
            client_row = None
        if lat == 0.0 and lng == 0.0:
            continue

        # mobility_wheelchair: prefer the already-merged column on the row
        wc = False
        if "mobility_wheelchair" in row.index:
            wc = bool(row.get("mobility_wheelchair", False))
        elif client_row is not None:
            wc = bool(client_row.get("mobility_wheelchair", False))

        req_records.append({
            "request_id": row["request_id"],
            "client_id": cid,
            "lat": lat,
            "lng": lng,
            "quantity_meals": int(row.get("quantity_meals", 0) or 0),
            "cold_chain_required": bool(row.get("cold_chain_required", False)),
            "mobility_wheelchair": wc,
            "required_driver_skills": str(row.get("required_driver_skills", "") or ""),
            "_client_row": client_row,
        })

    req_ids_in_records = {r["request_id"] for r in req_records}
    no_coord_dropped = [
        row["request_id"] for _, row in all_reqs.iterrows()
        if row["request_id"] not in req_ids_in_records
    ]

    if not req_records:
        return _empty(dropped=all_dropped_pre + no_coord_dropped)

    n_requests = len(req_records)
    n_vehicles = len(candidate_drivers)
    driver_rows = list(candidate_drivers.itertuples(index=False))

    # coords: index 0 = depot, 1..n_requests = clients
    coords: list[tuple[float, float]] = [(depot_lat, depot_lng)]
    for r in req_records:
        coords.append((r["lat"], r["lng"]))

    distance_matrix = _build_distance_matrix(coords)

    # ------------------------------------------------------------------
    # 8. Build OR-Tools routing model
    # ------------------------------------------------------------------
    manager = pywrapcp.RoutingIndexManager(len(coords), n_vehicles, 0)
    routing = pywrapcp.RoutingModel(manager)

    # Transit callback: arc cost = scaled drive minutes
    def _transit(from_idx: int, to_idx: int) -> int:
        i = manager.IndexToNode(from_idx)
        j = manager.IndexToNode(to_idx)
        return distance_matrix[i][j]

    transit_cb_idx = routing.RegisterTransitCallback(_transit)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_cb_idx)

    # ------------------------------------------------------------------
    # 9. Dimension: drive-time — per-vehicle upper bound via CumulVar
    #    AddDimension uses a single global cap; we override per-vehicle
    #    at the end node with SetCumulVarSoftUpperBound is soft, so instead
    #    we use the dimension's CumulVar upper bound approach:
    #    set the dimension global cap high, then tighten each vehicle's
    #    end node cumul bound.
    # ------------------------------------------------------------------
    global_time_cap = max(int(drv.max_hours * 60 * _MINUTES_SCALE) for drv in driver_rows)
    routing.AddDimension(
        transit_cb_idx,
        0,                  # no slack
        global_time_cap,
        True,               # start cumul at zero
        "DriveTime",
    )
    drive_dim = routing.GetDimensionOrDie("DriveTime")
    for v_idx, drv in enumerate(driver_rows):
        vehicle_time_cap = int(drv.max_hours * 60 * _MINUTES_SCALE)
        drive_dim.CumulVar(routing.End(v_idx)).SetMax(vehicle_time_cap)

    # ------------------------------------------------------------------
    # 10. Dimension: stop count per vehicle — same per-vehicle tighten idiom
    # ------------------------------------------------------------------
    def _one_stop(from_idx: int, to_idx: int) -> int:
        # Count each customer visit (not the return arc to depot)
        j = manager.IndexToNode(to_idx)
        return 1 if j != 0 else 0

    stop_cb_idx = routing.RegisterTransitCallback(_one_stop)
    global_stop_cap = max(int(drv.max_stops) for drv in driver_rows)
    routing.AddDimension(stop_cb_idx, 0, global_stop_cap, True, "StopCount")
    stop_dim = routing.GetDimensionOrDie("StopCount")
    for v_idx, drv in enumerate(driver_rows):
        stop_dim.CumulVar(routing.End(v_idx)).SetMax(int(drv.max_stops))

    # ------------------------------------------------------------------
    # 11. Dimension: vehicle capacity (meals) — per-vehicle via AddDimensionWithVehicleCapacity
    # ------------------------------------------------------------------
    demand = [0] + [r["quantity_meals"] for r in req_records]

    def _demand(from_idx: int) -> int:
        node = manager.IndexToNode(from_idx)
        return demand[node]

    demand_cb_idx = routing.RegisterUnaryTransitCallback(_demand)
    capacity_per_vehicle = [int(drv.veh_capacity_meals) for drv in driver_rows]
    routing.AddDimensionWithVehicleCapacity(
        demand_cb_idx,
        0,
        capacity_per_vehicle,
        True,
        "Capacity",
    )

    # ------------------------------------------------------------------
    # 12. Hard constraints: remove infeasible (vehicle, node) pairs
    # ------------------------------------------------------------------
    for req_idx, req in enumerate(req_records):
        node = req_idx + 1  # node 0 is depot
        routing_node_idx = manager.NodeToIndex(node)
        client_row = req["_client_row"]

        for v_idx, drv in enumerate(driver_rows):
            infeasible = False

            if req["cold_chain_required"] and not drv.veh_refrigerated:
                infeasible = True

            if not infeasible and req["mobility_wheelchair"] and not drv.veh_wheelchair_lift:
                infeasible = True

            if not infeasible and not _driver_satisfies_skills(
                pd.Series(drv._asdict()), req["required_driver_skills"]
            ):
                infeasible = True

            if not infeasible and client_row is not None:
                if not _driver_language_ok(pd.Series(drv._asdict()), client_row):
                    infeasible = True
                elif not _driver_pet_ok(pd.Series(drv._asdict()), client_row):
                    infeasible = True

            if infeasible:
                routing.VehicleVar(routing_node_idx).RemoveValue(v_idx)

    # ------------------------------------------------------------------
    # 13. Disjunctions — allow dropping any request with large penalty
    # ------------------------------------------------------------------
    for req_idx in range(n_requests):
        node = req_idx + 1
        routing.AddDisjunction([manager.NodeToIndex(node)], _DROP_PENALTY)

    # ------------------------------------------------------------------
    # 14. Solve
    # ------------------------------------------------------------------
    search_params = pywrapcp.DefaultRoutingSearchParameters()
    search_params.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    )
    search_params.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    )
    search_params.time_limit.seconds = time_limit_seconds

    solution = routing.SolveWithParameters(search_params)

    # ------------------------------------------------------------------
    # 15. Fallback: solver returned nothing
    # ------------------------------------------------------------------
    if solution is None:
        logger.warning("OR-Tools returned None for %s", service_date_str)
        return _empty(
            dropped=all_dropped_pre + no_coord_dropped + [r["request_id"] for r in req_records],
            on_time=0.0,
        )

    # ------------------------------------------------------------------
    # 16. Extract routes from solution
    # ------------------------------------------------------------------
    output_routes = []
    total_drive_minutes_scaled = 0
    assigned_req_ids: set = set()

    for v_idx, drv in enumerate(driver_rows):
        stops_for_vehicle: list[str] = []
        idx = routing.Start(v_idx)
        while not routing.IsEnd(idx):
            node = manager.IndexToNode(idx)
            if node != 0:
                req = req_records[node - 1]
                stops_for_vehicle.append(req["request_id"])
                assigned_req_ids.add(req["request_id"])
            idx = solution.Value(routing.NextVar(idx))

        if stops_for_vehicle:
            output_routes.append({
                "driver_id": drv.driver_id,
                "vehicle_id": drv.assigned_vehicle_id,
                "stops": stops_for_vehicle,
            })
            end_var = drive_dim.CumulVar(routing.End(v_idx))
            total_drive_minutes_scaled += solution.Value(end_var)

    # Convert scaled int back to real minutes
    total_drive_minutes = int(total_drive_minutes_scaled / _MINUTES_SCALE)

    ortools_dropped = [
        r["request_id"] for r in req_records if r["request_id"] not in assigned_req_ids
    ]
    all_dropped_final = all_dropped_pre + no_coord_dropped + ortools_dropped

    # If solver assigned nothing despite having requests, treat as failure
    if not assigned_req_ids and req_records:
        logger.warning("OR-Tools assigned 0 requests for %s", service_date_str)
        return _empty(dropped=all_dropped_final, on_time=0.0)

    # ------------------------------------------------------------------
    # 17. Metrics
    # ------------------------------------------------------------------
    n_active = len(req_records)
    n_assigned = len(assigned_req_ids)

    delta_pct = (
        (baseline_drive_minutes - total_drive_minutes) / baseline_drive_minutes
        if baseline_drive_minutes > 0 else 0.0
    )
    projected_on_time_rate = float(n_assigned) / max(n_active, 1)

    return {
        "routes": output_routes,
        "dropped_requests": all_dropped_final,
        "total_drive_minutes": total_drive_minutes,
        "baseline_drive_minutes": baseline_drive_minutes,
        "delta_pct": delta_pct,
        "projected_on_time_rate": projected_on_time_rate,
        "violations": [],  # guaranteed by pre-filter + model constraints
    }
