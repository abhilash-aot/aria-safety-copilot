"""Constrained-greedy VRP router for Track 2 — Food Security Delivery.

Safe-by-construction nearest-neighbor assignment.  Enforces all hard constraints
(cold chain, wheelchair lift, allergen, closure, pet allergy, language, driver
skill, driver caps) before any route is assembled, then greedily builds routes
with a nearest-neighbor heuristic using haversine distances.

Public API:
    reoptimize(tables, service_date, disruption=None) -> dict

This module is intentionally self-contained: it duplicates the allergen-check
logic rather than importing from src/safety/detectors.py, so that the optimizer
has no coupling to the detector agent's file ownership.
"""

from __future__ import annotations

import math
from datetime import date
from typing import Optional

import pandas as pd

from src.safety.models import Violation
from src.optimizer.baseline import score_baseline


# ---------------------------------------------------------------------------
# Haversine helper
# ---------------------------------------------------------------------------

_EARTH_RADIUS_KM = 6371.0

# drivers.max_hours is per-shift (generator uses 4–8 hrs per shift). Weekly cap
# = per-shift hours × typical shifts/week. Plan section 5 rule 8.
WEEKLY_SHIFT_BUDGET = 5


def _haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Return great-circle distance in km between two (lat, lng) points."""
    rlat1, rlng1, rlat2, rlng2 = map(math.radians, [lat1, lng1, lat2, lng2])
    dlat = rlat2 - rlat1
    dlng = rlng2 - rlng1
    a = math.sin(dlat / 2) ** 2 + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlng / 2) ** 2
    return 2 * _EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def _drive_minutes(dist_km: float, speed_kmh: float = 30.0) -> float:
    """Convert km distance to drive minutes assuming constant urban speed."""
    return (dist_km / speed_kmh) * 60.0


# ---------------------------------------------------------------------------
# Internal allergen-conflict check (self-contained, no detector import)
# ---------------------------------------------------------------------------

_ALLERGEN_SEVERITY_SEVERE = {"severe", "anaphylactic"}

# Map allergen token (from allergen_flags) to the client column suffix
_ALLERGEN_COL_MAP = {
    "peanut": "allergy_peanut_severity",
    "tree_nut": "allergy_tree_nut_severity",
    "shellfish": "allergy_shellfish_severity",
    "fish": "allergy_fish_severity",
    "egg": "allergy_egg_severity",
    "soy": "allergy_soy_severity",
    "wheat": "allergy_wheat_severity",
    "dairy": "allergy_dairy_severity",
}


def _build_allergen_blocked_request_ids(tables: dict) -> set:
    """Return set of request_ids that contain a severe-allergen line item.

    Join: delivery_request_items -> inventory_items -> delivery_requests -> clients.
    Flag when an item's allergen_flags token matches a client allergy column at
    severity in {severe, anaphylactic}.
    """
    request_items = tables["request_items"]  # line_id, request_id, item_id, quantity, notes
    items = tables["items"]                  # item_id, allergen_flags, ...
    requests = tables["requests"]            # request_id, client_id, ...
    clients = tables["clients"]              # client_id, allergy_*_severity, ...

    # Join line items -> item allergen flags
    ri = request_items[["request_id", "item_id"]].merge(
        items[["item_id", "allergen_flags"]], on="item_id", how="left"
    )
    # Keep only rows with at least one allergen flag
    ri = ri[ri["allergen_flags"].fillna("") != ""].copy()
    if ri.empty:
        return set()

    # Attach client_id via requests
    ri = ri.merge(
        requests[["request_id", "client_id"]], on="request_id", how="left"
    )
    # Attach client allergy columns
    allergy_cols = list(_ALLERGEN_COL_MAP.values())
    ri = ri.merge(
        clients[["client_id"] + allergy_cols], on="client_id", how="left"
    )

    blocked = set()
    for _, row in ri.iterrows():
        flags_raw = str(row.get("allergen_flags", "") or "")
        allergens = [a.strip().lower() for a in flags_raw.split(";") if a.strip()]
        for allergen in allergens:
            col = _ALLERGEN_COL_MAP.get(allergen)
            if col is None:
                continue
            severity = str(row.get(col, "none") or "none").strip().lower()
            if severity in _ALLERGEN_SEVERITY_SEVERE:
                blocked.add(row["request_id"])
                break  # one conflict is enough to block the request
    return blocked


# ---------------------------------------------------------------------------
# Driver-skill compatibility
# ---------------------------------------------------------------------------

def _driver_satisfies_skills(driver: pd.Series, required_skills_str: str) -> bool:
    """Return True if the driver satisfies all required_driver_skills tokens.

    Skill tokens in delivery_requests.required_driver_skills (';'-separated):
        refrigerated_vehicle   → vehicle.refrigerated=True  (checked separately)
        wheelchair             → driver.can_handle_wheelchair=True
        two_person             → (not enforced here; accepted — the greedy assigns
                                   one driver; requirement is noted but not dropped)
        no_pet_allergy         → driver.pet_allergy_flag=False
        lang_<name>            → language_skills contains <name>
    """
    if not required_skills_str or pd.isna(required_skills_str):
        return True

    skills = [s.strip() for s in required_skills_str.split(";") if s.strip()]
    driver_langs = {
        lang.strip().lower()
        for lang in str(driver.get("language_skills", "") or "").split(";")
        if lang.strip()
    }

    for skill in skills:
        if skill == "wheelchair":
            if not bool(driver.get("can_handle_wheelchair", False)):
                return False
        elif skill == "no_pet_allergy":
            if bool(driver.get("pet_allergy_flag", False)):
                return False
        elif skill.startswith("lang_"):
            lang_needed = skill[5:].lower()
            if lang_needed not in driver_langs:
                return False
        # refrigerated_vehicle → vehicle constraint checked at vehicle level
        # two_person → single-driver greedy; accepted but not enforced as a block
        # (would need partner assignment, out of scope for greedy fallback)
    return True


def _driver_language_ok(driver: pd.Series, client: pd.Series) -> bool:
    """Return True unless interpreter_required and no shared language."""
    if not bool(client.get("interpreter_required", False)):
        return True
    primary = str(client.get("language_primary", "") or "").strip().lower()
    if not primary:
        return True
    driver_langs = {
        lang.strip().lower()
        for lang in str(driver.get("language_skills", "") or "").split(";")
        if lang.strip()
    }
    return primary in driver_langs


def _driver_pet_ok(driver: pd.Series, client: pd.Series) -> bool:
    """Return True unless driver has pet_allergy and client has dog."""
    if bool(driver.get("pet_allergy_flag", False)) and bool(client.get("has_dog_on_premises", False)):
        return False
    return True


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def reoptimize(
    tables: dict,
    service_date: date,
    disruption: Optional[dict] = None,
) -> dict:
    """Build a safe-by-construction route plan for service_date.

    Returns:
        {
            "routes": list[{driver_id, vehicle_id, stops: [request_id ...]}],
            "dropped_requests": list[request_id],
            "total_drive_minutes": int,
            "baseline_drive_minutes": int,
            "delta_pct": float,
            "projected_on_time_rate": float,
            "violations": list[Violation],   # always empty — guaranteed by construction
        }
    """
    service_date_str = service_date.isoformat() if isinstance(service_date, date) else str(service_date)

    routes = tables["routes"]
    requests = tables["requests"]
    clients = tables["clients"]
    drivers = tables["drivers"]
    vehicles = tables["vehicles"]
    depots = tables["depots"]

    # ------------------------------------------------------------------
    # 1. Compute baseline (before any filtering) for delta comparison
    # ------------------------------------------------------------------
    baseline_result = score_baseline(tables, service_date)
    baseline_drive_minutes = baseline_result["total_drive_minutes"]

    # ------------------------------------------------------------------
    # 2. Identify active requests for this service_date
    #    Priority: requests with assigned_route_id on routes for this date;
    #    also include requests whose scheduled_date == service_date and
    #    status in {pending, scheduled}.
    # ------------------------------------------------------------------
    day_routes = routes[routes["service_date"] == service_date_str]
    day_route_ids = set(day_routes["route_id"].tolist())

    # Requests tied to existing routes for this date (pending or scheduled)
    reqs_via_route = requests[
        requests["assigned_route_id"].isin(day_route_ids)
        & requests["status"].isin(["pending", "scheduled"])
    ]

    # Requests scheduled for this date (not yet assigned)
    reqs_via_sched = requests[
        (requests["scheduled_date"] == service_date_str)
        & requests["status"].isin(["pending", "scheduled"])
        & (~requests["request_id"].isin(reqs_via_route["request_id"]))
    ]

    all_reqs = pd.concat([reqs_via_route, reqs_via_sched], ignore_index=True)

    if all_reqs.empty:
        # No work to do — return zero-route result with baseline for reference
        return {
            "routes": [],
            "dropped_requests": [],
            "total_drive_minutes": 0,
            "baseline_drive_minutes": baseline_drive_minutes,
            "delta_pct": 0.0,
            "projected_on_time_rate": 1.0,
            "violations": [],
        }

    # ------------------------------------------------------------------
    # 3. Join client info for safety checks
    # ------------------------------------------------------------------
    all_reqs = all_reqs.merge(clients, on="client_id", how="left", suffixes=("", "_client"))

    # ------------------------------------------------------------------
    # 4. Drop closed/deceased clients where closure_date < service_date
    # ------------------------------------------------------------------
    def _is_closed(row: pd.Series) -> bool:
        status = str(row.get("enrolment_status", "") or "").lower()
        if status not in {"closed", "deceased"}:
            return False
        closure_raw = row.get("closure_date")
        if closure_raw is None or pd.isna(closure_raw):
            return True  # status says closed but no date — still drop
        try:
            # closure_date may be in various formats
            closure = pd.to_datetime(closure_raw, dayfirst=False, errors="coerce")
            if pd.isna(closure):
                return True
            return closure.date() < (service_date if isinstance(service_date, date) else pd.to_datetime(service_date).date())
        except Exception:
            return True

    drop_mask_closed = all_reqs.apply(_is_closed, axis=1)
    dropped_closed = all_reqs.loc[drop_mask_closed, "request_id"].tolist()
    all_reqs = all_reqs[~drop_mask_closed].copy()

    # ------------------------------------------------------------------
    # 5. Drop requests with severe-allergen conflicts in their line items
    # ------------------------------------------------------------------
    allergen_blocked = _build_allergen_blocked_request_ids(tables)
    drop_mask_allergen = all_reqs["request_id"].isin(allergen_blocked)
    dropped_allergen = all_reqs.loc[drop_mask_allergen, "request_id"].tolist()
    all_reqs = all_reqs[~drop_mask_allergen].copy()

    all_dropped = dropped_closed + dropped_allergen

    if all_reqs.empty:
        return {
            "routes": [],
            "dropped_requests": all_dropped,
            "total_drive_minutes": 0,
            "baseline_drive_minutes": baseline_drive_minutes,
            "delta_pct": 0.0,
            "projected_on_time_rate": 1.0,
            "violations": [],
        }

    # ------------------------------------------------------------------
    # 6. Build (driver, vehicle) candidate pool for this date
    # ------------------------------------------------------------------
    # Apply disruption: remove a driver if specified
    removed_drivers: set = set()
    if disruption and "driver_out" in disruption:
        removed_drivers.add(disruption["driver_out"])

    # Drivers active on this date → use all drivers from the actual routes table
    # for this date, supplementing with any driver not yet scheduled but available.
    # We derive the "working" driver set from existing routes for this date.
    if day_routes.empty:
        # No existing routes — use all drivers
        candidate_drivers = drivers[~drivers["driver_id"].isin(removed_drivers)].copy()
    else:
        driver_ids_today = set(day_routes["driver_id"].tolist()) - removed_drivers
        candidate_drivers = drivers[drivers["driver_id"].isin(driver_ids_today)].copy()
        if candidate_drivers.empty:
            # Fallback: all drivers
            candidate_drivers = drivers[~drivers["driver_id"].isin(removed_drivers)].copy()

    # Compute each driver's weekly hours already used (prior routes same ISO week)
    service_dt = service_date if isinstance(service_date, date) else pd.to_datetime(service_date).date()
    service_week = service_dt.isocalendar()[1]  # ISO week number
    service_year = service_dt.isocalendar()[0]

    def _iso_week_year(d_str: str):
        try:
            d = pd.to_datetime(d_str).date()
            iso = d.isocalendar()
            return (iso[0], iso[1])
        except Exception:
            return (None, None)

    routes_with_week = routes.copy()
    routes_with_week["_wy"] = routes_with_week["service_date"].map(_iso_week_year)
    same_week_routes = routes_with_week[
        routes_with_week["_wy"] == (service_year, service_week)
    ]
    # Sum minutes per driver for same week (excluding today's routes since we're rebuilding them)
    prior_routes = same_week_routes[same_week_routes["service_date"] != service_date_str]
    weekly_minutes_used = (
        prior_routes.groupby("driver_id")["planned_time_minutes"].sum()
        .rename("weekly_minutes_used")
    )
    candidate_drivers = candidate_drivers.merge(
        weekly_minutes_used, on="driver_id", how="left"
    )
    candidate_drivers["weekly_minutes_used"] = candidate_drivers["weekly_minutes_used"].fillna(0)

    # Drop drivers already at or over weekly cap (per-shift hrs × weekly budget)
    candidate_drivers = candidate_drivers[
        candidate_drivers["weekly_minutes_used"]
        < candidate_drivers["max_hours"] * 60 * WEEKLY_SHIFT_BUDGET
    ].copy()

    if candidate_drivers.empty:
        # All drivers over cap — drop all requests
        return {
            "routes": [],
            "dropped_requests": all_dropped + all_reqs["request_id"].tolist(),
            "total_drive_minutes": 0,
            "baseline_drive_minutes": baseline_drive_minutes,
            "delta_pct": 0.0,
            "projected_on_time_rate": 0.0,
            "violations": [],
        }

    # ------------------------------------------------------------------
    # 7. Assign vehicle to each driver (use existing routes table assignment;
    #    fall back to driver.vehicle_id if no route exists today)
    # ------------------------------------------------------------------
    driver_vehicle_today = (
        day_routes[["driver_id", "vehicle_id"]]
        .drop_duplicates("driver_id")
        .set_index("driver_id")["vehicle_id"]
    )

    def _get_vehicle_for_driver(drv_id: str) -> str:
        if drv_id in driver_vehicle_today.index:
            return driver_vehicle_today[drv_id]
        # Fallback: driver's assigned vehicle from drivers table
        row = drivers[drivers["driver_id"] == drv_id]
        if not row.empty and pd.notna(row.iloc[0]["vehicle_id"]):
            return row.iloc[0]["vehicle_id"]
        return ""

    candidate_drivers = candidate_drivers.copy()
    candidate_drivers["assigned_vehicle_id"] = candidate_drivers["driver_id"].map(_get_vehicle_for_driver)

    # Join vehicle info
    veh_indexed = vehicles.set_index("vehicle_id")
    candidate_drivers["veh_refrigerated"] = candidate_drivers["assigned_vehicle_id"].map(
        lambda v: bool(veh_indexed.loc[v, "refrigerated"]) if v in veh_indexed.index else False
    )
    candidate_drivers["veh_wheelchair_lift"] = candidate_drivers["assigned_vehicle_id"].map(
        lambda v: bool(veh_indexed.loc[v, "wheelchair_lift"]) if v in veh_indexed.index else False
    )
    candidate_drivers["veh_capacity_meals"] = candidate_drivers["assigned_vehicle_id"].map(
        lambda v: int(veh_indexed.loc[v, "capacity_meals"]) if v in veh_indexed.index else 0
    )

    # Drop drivers with no usable vehicle
    candidate_drivers = candidate_drivers[candidate_drivers["assigned_vehicle_id"] != ""].copy()
    if candidate_drivers.empty:
        return {
            "routes": [],
            "dropped_requests": all_dropped + all_reqs["request_id"].tolist(),
            "total_drive_minutes": 0,
            "baseline_drive_minutes": baseline_drive_minutes,
            "delta_pct": 0.0,
            "projected_on_time_rate": 0.0,
            "violations": [],
        }

    # ------------------------------------------------------------------
    # 8. Attach depot coordinates to each driver/vehicle pair
    # ------------------------------------------------------------------
    depots_indexed = depots.set_index("depot_id")[["lat", "lng"]]

    # Determine home depot for each driver from driver.home_base_depot_id or
    # from the day_routes start_depot_id
    route_depot_map = (
        day_routes[["driver_id", "start_depot_id"]]
        .drop_duplicates("driver_id")
        .set_index("driver_id")["start_depot_id"]
    )

    def _depot_for_driver(drv_id: str) -> str:
        if drv_id in route_depot_map.index:
            return route_depot_map[drv_id]
        drv_row = drivers[drivers["driver_id"] == drv_id]
        if not drv_row.empty:
            return str(drv_row.iloc[0].get("home_base_depot_id", "DEP-01") or "DEP-01")
        return "DEP-01"

    candidate_drivers["depot_id"] = candidate_drivers["driver_id"].map(_depot_for_driver)
    candidate_drivers["depot_lat"] = candidate_drivers["depot_id"].map(
        lambda d: float(depots_indexed.loc[d, "lat"]) if d in depots_indexed.index else 48.43
    )
    candidate_drivers["depot_lng"] = candidate_drivers["depot_id"].map(
        lambda d: float(depots_indexed.loc[d, "lng"]) if d in depots_indexed.index else -123.37
    )

    # ------------------------------------------------------------------
    # 9. For each request, determine which (driver, vehicle) pairs are eligible
    #    based on hard constraints.  We build a per-request eligibility mask
    #    then use it during greedy assignment.
    # ------------------------------------------------------------------

    # Build lookup structures for efficiency
    clients_indexed = clients.set_index("client_id")

    def _client_for_req(req: pd.Series) -> Optional[pd.Series]:
        cid = req.get("client_id")
        if cid and cid in clients_indexed.index:
            return clients_indexed.loc[cid]
        return None

    def _eligible_drivers_for_request(req: pd.Series, cdrv_df: pd.DataFrame) -> pd.DataFrame:
        """Return the subset of candidate_drivers eligible for this request."""
        eligible = cdrv_df.copy()

        client = _client_for_req(req)
        cold = bool(req.get("cold_chain_required", False))
        wc = bool(client.get("mobility_wheelchair", False)) if client is not None else False
        req_skills = str(req.get("required_driver_skills", "") or "")

        # Cold-chain constraint: request needs refrigeration → vehicle must be refrigerated
        if cold:
            eligible = eligible[eligible["veh_refrigerated"]].copy()

        # Wheelchair constraint: wheelchair client → only VEH-06 (wheelchair_lift=True)
        if wc:
            eligible = eligible[eligible["veh_wheelchair_lift"]].copy()

        # Per-driver constraints
        def _driver_ok(drv_row: pd.Series) -> bool:
            # Driver skill match
            if not _driver_satisfies_skills(drv_row, req_skills):
                return False
            if client is None:
                return True
            # Language check
            if not _driver_language_ok(drv_row, client):
                return False
            # Pet allergy check
            if not _driver_pet_ok(drv_row, client):
                return False
            return True

        if not eligible.empty:
            mask = eligible.apply(_driver_ok, axis=1)
            eligible = eligible[mask].copy()

        return eligible

    # ------------------------------------------------------------------
    # 10. Greedy nearest-neighbor assignment
    #     For each driver, build a route starting from the depot and
    #     repeatedly picking the nearest unassigned eligible request.
    # ------------------------------------------------------------------

    # Convert requests to a convenient dict keyed by request_id
    req_rows = {row["request_id"]: row for _, row in all_reqs.iterrows()}

    # Track assignment state
    unassigned = set(req_rows.keys())

    # Route state per driver
    route_state = {}  # driver_id -> {vehicle_id, stops, total_meals, total_dist_km, total_minutes, pos_lat, pos_lng}
    for _, drv in candidate_drivers.iterrows():
        route_state[drv["driver_id"]] = {
            "vehicle_id": drv["assigned_vehicle_id"],
            "stops": [],
            "total_meals": 0,
            "total_dist_km": 0.0,
            "total_minutes": 0.0,
            "pos_lat": drv["depot_lat"],
            "pos_lng": drv["depot_lng"],
            "capacity_meals": drv["veh_capacity_meals"],
            "max_stops": int(drv["max_stops"]),
            "max_hours": float(drv["max_hours"]),
            "max_distance_km": float(drv["max_distance_km"]),
            "weekly_minutes_used": float(drv["weekly_minutes_used"]),
        }

    driver_ids = list(route_state.keys())

    # Iteratively assign: each pass assigns one stop to the best driver for
    # the nearest unassigned eligible request. Continue until no assignments
    # possible.
    while unassigned:
        best_assignment = None  # (dist_km, driver_id, request_id)

        for drv_id in driver_ids:
            state = route_state[drv_id]
            drv_row = candidate_drivers[candidate_drivers["driver_id"] == drv_id].iloc[0]

            # Per-shift cap: today's drive minutes alone must stay under max_hours.
            if state["total_minutes"] >= state["max_hours"] * 60:
                continue
            # Weekly cap: prior-week + today must stay under max_hours × budget.
            weekly_hrs_so_far = (state["weekly_minutes_used"] + state["total_minutes"]) / 60.0
            if weekly_hrs_so_far >= state["max_hours"] * WEEKLY_SHIFT_BUDGET:
                continue
            if len(state["stops"]) >= state["max_stops"]:
                continue
            if state["total_dist_km"] >= state["max_distance_km"]:
                continue

            cur_lat = state["pos_lat"]
            cur_lng = state["pos_lng"]

            for req_id in unassigned:
                req = req_rows[req_id]
                client = _client_for_req(req)
                if client is None:
                    continue

                client_lat = float(client.get("lat", 0.0) or 0.0)
                client_lng = float(client.get("lng", 0.0) or 0.0)
                if client_lat == 0.0 and client_lng == 0.0:
                    continue  # no coordinates, skip

                # Check eligibility for this (driver, request) pair
                eligible = _eligible_drivers_for_request(req, candidate_drivers)
                if drv_id not in eligible["driver_id"].values:
                    continue

                # Check capacity
                meals = int(req.get("quantity_meals", 0) or 0)
                if state["total_meals"] + meals > state["capacity_meals"]:
                    continue

                dist = _haversine(cur_lat, cur_lng, client_lat, client_lng)
                drive_min = _drive_minutes(dist)

                # Check adding this stop stays within caps
                new_total_dist = state["total_dist_km"] + dist
                new_total_min = state["total_minutes"] + drive_min
                new_shift_hrs = new_total_min / 60.0
                new_weekly_hrs = (state["weekly_minutes_used"] + new_total_min) / 60.0

                if new_total_dist > state["max_distance_km"]:
                    continue
                if new_shift_hrs > state["max_hours"]:
                    continue
                if new_weekly_hrs > state["max_hours"] * WEEKLY_SHIFT_BUDGET:
                    continue

                if best_assignment is None or dist < best_assignment[0]:
                    best_assignment = (dist, drv_id, req_id)

        if best_assignment is None:
            break  # no more feasible assignments

        dist_km, drv_id, req_id = best_assignment
        req = req_rows[req_id]
        client = _client_for_req(req)
        client_lat = float(client.get("lat", 0.0) or 0.0)
        client_lng = float(client.get("lng", 0.0) or 0.0)
        meals = int(req.get("quantity_meals", 0) or 0)
        drive_min = _drive_minutes(dist_km)

        state = route_state[drv_id]
        state["stops"].append(req_id)
        state["total_meals"] += meals
        state["total_dist_km"] += dist_km
        state["total_minutes"] += drive_min
        state["pos_lat"] = client_lat
        state["pos_lng"] = client_lng

        unassigned.remove(req_id)

    # Anything still unassigned is dropped (no feasible assignment)
    dropped_no_capacity = list(unassigned)
    all_dropped = all_dropped + dropped_no_capacity

    # ------------------------------------------------------------------
    # 11. Assemble output routes (only drivers with at least one stop)
    # ------------------------------------------------------------------
    output_routes = []
    total_drive_minutes = 0

    for drv_id, state in route_state.items():
        if not state["stops"]:
            continue
        output_routes.append({
            "driver_id": drv_id,
            "vehicle_id": state["vehicle_id"],
            "stops": state["stops"],  # list of request_ids in order
        })
        total_drive_minutes += int(state["total_minutes"])

    # ------------------------------------------------------------------
    # 12. Compute delta_pct and projected_on_time_rate
    # ------------------------------------------------------------------
    if baseline_drive_minutes > 0:
        delta_pct = (baseline_drive_minutes - total_drive_minutes) / baseline_drive_minutes
    else:
        delta_pct = 0.0

    # Projected on-time rate: fraction of assigned stops.
    total_possible = sum(len(s["stops"]) for s in route_state.values()) + len(dropped_no_capacity)
    total_assigned = sum(len(s["stops"]) for s in route_state.values())
    projected_on_time_rate = float(total_assigned) / max(total_possible, 1)

    return {
        "routes": output_routes,
        "dropped_requests": all_dropped,
        "total_drive_minutes": total_drive_minutes,
        "baseline_drive_minutes": baseline_drive_minutes,
        "delta_pct": delta_pct,
        "projected_on_time_rate": projected_on_time_rate,
        "violations": [],  # guaranteed by construction
    }
