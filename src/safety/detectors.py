"""Safety detector rules for Track 2 — Food Security Delivery Operations.

Each check_* function is a pure function over the tables dict from load_track2().
No I/O, no side effects — all display happens in the Streamlit layer or test harness.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import date
from typing import Dict, List

import pandas as pd

from src.safety.models import Severity, Violation

# ISO week helper: return (year, week) for a date so weekly aggregations are
# anchored to the same calendar week as service_date.
def _iso_week_key(d: date):
    iso = d.isocalendar()
    return (iso[0], iso[1])

# Severity sort order for run_all.
_SEVERITY_RANK: Dict[str, int] = {
    Severity.CRITICAL: 0,
    Severity.HIGH: 1,
    Severity.MEDIUM: 2,
    Severity.LOW: 3,
    Severity.INFO: 4,
}

# Map allergen token (from items.allergen_flags) to the client severity column.
_ALLERGEN_TO_COL: Dict[str, str] = {
    "dairy":    "allergy_dairy_severity",
    "egg":      "allergy_egg_severity",
    "fish":     "allergy_fish_severity",
    "peanut":   "allergy_peanut_severity",
    "soy":      "allergy_soy_severity",
    "tree_nut": "allergy_tree_nut_severity",
    "wheat":    "allergy_wheat_severity",
}

_SEVERE_LEVELS = frozenset({"severe", "anaphylactic"})

# drivers.max_hours is per-shift (generator sets 4–8). Weekly cap = per-shift × budget.
_WEEKLY_SHIFT_BUDGET = 5


def check_severe_allergen(
    tables: Dict[str, pd.DataFrame],
    service_date: date,
) -> List[Violation]:
    """Flag line items where the item allergen matches a client's severe/anaphylactic allergy.

    Joins request_items → items → requests → clients, restricted to the given service_date.
    Emits one Violation per (request_id, allergen_token) pair so duplicate line items
    for the same allergen in the same request produce a single flag.
    """
    items = tables["items"]
    ri = tables["request_items"]
    reqs = tables["requests"]
    clients = tables["clients"]

    # Filter requests to this date; requests uses scheduled_date not service_date.
    date_str = str(service_date)
    day_reqs = reqs[reqs["scheduled_date"] == date_str]
    if day_reqs.empty:
        return []

    allergy_cols = list(_ALLERGEN_TO_COL.values())
    client_cols = ["client_id"] + allergy_cols

    joined = (
        ri.merge(items[["item_id", "allergen_flags"]], on="item_id", how="inner")
          .merge(day_reqs[["request_id", "client_id", "scheduled_date"]], on="request_id", how="inner")
          .merge(clients[client_cols], on="client_id", how="left")
    )

    # Deduplicate: one row per (request_id, item_id, allergen_token).
    seen: set = set()
    violations: List[Violation] = []

    for _, row in joined.iterrows():
        flags_raw = row["allergen_flags"]
        if pd.isna(flags_raw) or flags_raw == "":
            continue
        tokens = [t.strip() for t in str(flags_raw).split(";") if t.strip()]
        for tok in tokens:
            col = _ALLERGEN_TO_COL.get(tok)
            if col is None:
                continue
            severity_val = row.get(col, None)
            if pd.isna(severity_val) or severity_val not in _SEVERE_LEVELS:
                continue
            key = (row["request_id"], row["item_id"], tok)
            if key in seen:
                continue
            seen.add(key)
            violations.append(Violation(
                rule="severe_allergen_in_line_item",
                severity=Severity.CRITICAL,
                service_date=service_date,
                route_id=None,
                stop_id=None,
                request_id=row["request_id"],
                client_id=row["client_id"],
                driver_id=None,
                vehicle_id=None,
                explanation=(
                    f"{row['request_id']} / {row['client_id']} / {row['item_id']}: "
                    f"allergen '{tok}' flagged; client severity is '{severity_val}'"
                ),
                suggested_fix=f"Remove item {row['item_id']} or substitute allergen-free",
            ))

    return violations


def check_post_closure_delivery(
    tables: Dict[str, pd.DataFrame],
    service_date: date,
) -> List[Violation]:
    """Flag stops where delivery is planned after the client's file closure date.

    Filters route_stops to the given service_date via the routes table, then checks
    planned_arrival.date() > clients.closure_date for closed/deceased clients.
    """
    stops = tables["stops"]
    routes = tables["routes"]
    clients = tables["clients"]

    # Filter routes to this service_date.
    date_str = str(service_date)
    day_routes = routes[routes["service_date"] == date_str][["route_id", "service_date", "driver_id", "vehicle_id"]]
    if day_routes.empty:
        return []

    # Parse mixed-format closure dates; dayfirst=True handles DD/MM/YYYY tokens.
    clients_work = clients.copy()
    clients_work["closure_date_parsed"] = pd.to_datetime(
        clients_work["closure_date"], format="mixed", dayfirst=True, errors="coerce"
    )

    closed_clients = clients_work[
        clients_work["enrolment_status"].isin({"closed", "deceased"})
        & clients_work["closure_date_parsed"].notna()
    ][["client_id", "closure_date_parsed"]]

    if closed_clients.empty:
        return []

    day_stops = stops.merge(day_routes, on="route_id", how="inner")
    day_stops = day_stops.merge(closed_clients, on="client_id", how="inner")

    # planned_arrival is datetime64; compare date portions.
    violations: List[Violation] = []
    for _, row in day_stops.iterrows():
        arrival_date = pd.Timestamp(row["planned_arrival"]).date()
        closure_dt = row["closure_date_parsed"]
        if pd.isna(closure_dt):
            continue
        closure_d = closure_dt.date()
        if arrival_date > closure_d:
            violations.append(Violation(
                rule="delivery_after_client_closure",
                severity=Severity.MEDIUM,
                service_date=service_date,
                route_id=row["route_id"],
                stop_id=row["route_stop_id"],
                request_id=row.get("request_id"),
                client_id=row["client_id"],
                driver_id=row.get("driver_id"),
                vehicle_id=row.get("vehicle_id"),
                explanation=(
                    f"{row['route_stop_id']} / {row.get('request_id')} / {row['client_id']}: "
                    f"planned arrival {arrival_date} is after closure {closure_d}"
                ),
                suggested_fix=f"Cancel stop — client file closed since {closure_d}",
            ))

    return violations


def check_cold_chain(
    tables: Dict[str, pd.DataFrame],
    service_date: date,
) -> List[Violation]:
    """Flag requests needing cold-chain delivered by a non-refrigerated vehicle.

    Join path: stops -> requests -> routes -> vehicles, filtered to service_date.
    """
    stops = tables["stops"]
    reqs = tables["requests"]
    routes = tables["routes"]
    vehicles = tables["vehicles"]

    date_str = str(service_date)
    day_routes = routes[routes["service_date"] == date_str][["route_id", "vehicle_id"]]
    if day_routes.empty:
        return []

    cold_reqs = reqs[reqs["cold_chain_required"] == True][["request_id", "client_id", "cold_chain_required"]]
    if cold_reqs.empty:
        return []

    non_ref = vehicles[vehicles["refrigerated"] == False][["vehicle_id"]]

    joined = (
        stops[["route_stop_id", "route_id", "request_id", "client_id"]]
        .merge(cold_reqs[["request_id"]], on="request_id", how="inner")
        .merge(day_routes, on="route_id", how="inner")
        .merge(non_ref, on="vehicle_id", how="inner")
    )

    violations: List[Violation] = []
    for _, row in joined.iterrows():
        violations.append(Violation(
            rule="cold_chain_break",
            severity=Severity.CRITICAL,
            service_date=service_date,
            route_id=row["route_id"],
            stop_id=row["route_stop_id"],
            request_id=row["request_id"],
            client_id=row.get("client_id"),
            driver_id=None,
            vehicle_id=row["vehicle_id"],
            explanation=(
                f"{row['route_stop_id']} / {row['request_id']}: cold_chain_required "
                f"but vehicle {row['vehicle_id']} is not refrigerated"
            ),
            suggested_fix=f"Reassign route {row['route_id']} to a refrigerated vehicle",
        ))
    return violations


def check_wheelchair_lift(
    tables: Dict[str, pd.DataFrame],
    service_date: date,
) -> List[Violation]:
    """Flag wheelchair clients assigned to a vehicle without a lift (non VEH-06).

    VEH-06 is the only vehicle with wheelchair_lift=True in the fleet.
    """
    stops = tables["stops"]
    routes = tables["routes"]
    clients = tables["clients"]

    date_str = str(service_date)
    day_routes = routes[routes["service_date"] == date_str][["route_id", "vehicle_id", "driver_id"]]
    if day_routes.empty:
        return []

    wc_clients = clients[clients["mobility_wheelchair"] == True][["client_id"]]
    if wc_clients.empty:
        return []

    joined = (
        stops[["route_stop_id", "route_id", "client_id"]]
        .merge(wc_clients, on="client_id", how="inner")
        .merge(day_routes, on="route_id", how="inner")
    )
    # Only flag non-VEH-06 assignments (VEH-06 is wheelchair_lift=True).
    flagged = joined[joined["vehicle_id"] != "VEH-06"]

    violations: List[Violation] = []
    for _, row in flagged.iterrows():
        violations.append(Violation(
            rule="wheelchair_client_wrong_vehicle",
            severity=Severity.HIGH,
            service_date=service_date,
            route_id=row["route_id"],
            stop_id=row["route_stop_id"],
            request_id=None,
            client_id=row["client_id"],
            driver_id=row.get("driver_id"),
            vehicle_id=row["vehicle_id"],
            explanation=(
                f"{row['route_stop_id']} / {row['client_id']}: wheelchair client "
                f"assigned to {row['vehicle_id']} which has no wheelchair lift"
            ),
            suggested_fix="Reassign to VEH-06",
        ))
    return violations


def check_two_person_solo(
    tables: Dict[str, pd.DataFrame],
    service_date: date,
) -> List[Violation]:
    """Flag two-person clients where the route has only a single driver.

    v1 heuristic: every route has exactly one driver_id (confirmed by schema probe),
    so any stop for a requires_two_person_team client is flagged.
    """
    stops = tables["stops"]
    routes = tables["routes"]
    clients = tables["clients"]

    date_str = str(service_date)
    # Include partner_driver_id when present so applied fixes suppress re-detection.
    route_cols = ["route_id", "driver_id"] + (
        ["partner_driver_id"] if "partner_driver_id" in routes.columns else []
    )
    day_routes = routes[routes["service_date"] == date_str][route_cols]
    if day_routes.empty:
        return []

    tp_clients = clients[clients["requires_two_person_team"] == True][["client_id"]]
    if tp_clients.empty:
        return []

    joined = (
        stops[["route_stop_id", "route_id", "client_id", "request_id"]]
        .merge(tp_clients, on="client_id", how="inner")
        .merge(day_routes, on="route_id", how="inner")
    )

    violations: List[Violation] = []
    for _, row in joined.iterrows():
        # Applied partner_driver_id overlay satisfies the two-person requirement.
        partner = row.get("partner_driver_id")
        if partner is not None and not pd.isna(partner) and str(partner).strip():
            continue
        violations.append(Violation(
            rule="two_person_client_solo_driver",
            severity=Severity.HIGH,
            service_date=service_date,
            route_id=row["route_id"],
            stop_id=row["route_stop_id"],
            request_id=row.get("request_id"),
            client_id=row["client_id"],
            driver_id=row.get("driver_id"),
            vehicle_id=None,
            explanation=(
                f"{row['route_stop_id']} / {row['client_id']} / {row.get('driver_id')}: "
                f"client requires two-person team but route {row['route_id']} has one driver"
            ),
            suggested_fix=f"Add a second trained driver to route {row['route_id']}",
        ))
    return violations


def check_driver_pet_allergy(
    tables: Dict[str, pd.DataFrame],
    service_date: date,
) -> List[Violation]:
    """Flag stops where a pet-allergic driver visits a client with a dog on premises."""
    stops = tables["stops"]
    routes = tables["routes"]
    clients = tables["clients"]
    drivers = tables["drivers"]

    date_str = str(service_date)
    day_routes = routes[routes["service_date"] == date_str][["route_id", "driver_id"]]
    if day_routes.empty:
        return []

    allergy_drivers = drivers[drivers["pet_allergy_flag"] == True][["driver_id"]]
    dog_clients = clients[clients["has_dog_on_premises"] == True][["client_id"]]

    if allergy_drivers.empty or dog_clients.empty:
        return []

    joined = (
        stops[["route_stop_id", "route_id", "client_id", "request_id"]]
        .merge(dog_clients, on="client_id", how="inner")
        .merge(day_routes, on="route_id", how="inner")
        .merge(allergy_drivers, on="driver_id", how="inner")
    )

    violations: List[Violation] = []
    for _, row in joined.iterrows():
        violations.append(Violation(
            rule="driver_pet_allergy_conflict",
            severity=Severity.MEDIUM,
            service_date=service_date,
            route_id=row["route_id"],
            stop_id=row["route_stop_id"],
            request_id=row.get("request_id"),
            client_id=row["client_id"],
            driver_id=row["driver_id"],
            vehicle_id=None,
            explanation=(
                f"{row['route_stop_id']} / {row['client_id']} / {row['driver_id']}: "
                f"driver has pet allergy; client has dog on premises"
            ),
            suggested_fix=f"Reassign {row['route_stop_id']} to a non-allergic driver",
        ))
    return violations


def check_interpreter_language(
    tables: Dict[str, pd.DataFrame],
    service_date: date,
) -> List[Violation]:
    """Flag stops where interpreter is required but driver lacks the client's language.

    English is always available; only non-English clients are checked.
    """
    stops = tables["stops"]
    routes = tables["routes"]
    clients = tables["clients"]
    drivers = tables["drivers"]

    date_str = str(service_date)
    day_routes = routes[routes["service_date"] == date_str][["route_id", "driver_id"]]
    if day_routes.empty:
        return []

    # Only non-English clients who need an interpreter are meaningful gaps.
    interp_clients = clients[
        (clients["interpreter_required"] == True)
        & (clients["language_primary"] != "English")
    ][["client_id", "language_primary"]]
    if interp_clients.empty:
        return []

    joined = (
        stops[["route_stop_id", "route_id", "client_id", "request_id"]]
        .merge(interp_clients, on="client_id", how="inner")
        .merge(day_routes, on="route_id", how="inner")
        .merge(drivers[["driver_id", "language_skills"]], on="driver_id", how="inner")
    )

    violations: List[Violation] = []
    for _, row in joined.iterrows():
        driver_langs = {s.strip() for s in str(row["language_skills"]).split(";")}
        if row["language_primary"] in driver_langs:
            continue
        violations.append(Violation(
            rule="interpreter_language_gap",
            severity=Severity.MEDIUM,
            service_date=service_date,
            route_id=row["route_id"],
            stop_id=row["route_stop_id"],
            request_id=row.get("request_id"),
            client_id=row["client_id"],
            driver_id=row["driver_id"],
            vehicle_id=None,
            explanation=(
                f"{row['route_stop_id']} / {row['client_id']} / {row['driver_id']}: "
                f"client needs {row['language_primary']} interpreter; "
                f"driver speaks {row['language_skills']}"
            ),
            suggested_fix=(
                f"Reassign to a driver with {row['language_primary']} skills "
                f"or arrange a phone interpreter"
            ),
        ))
    return violations


def check_driver_hours_distance(
    tables: Dict[str, pd.DataFrame],
    service_date: date,
) -> List[Violation]:
    """Flag drivers whose weekly planned hours or distance exceeds their cap.

    Uses the ISO week containing service_date; aggregates all routes that week.
    Caps: hours -> max_hours * 60 * WEEKLY_SHIFT_BUDGET minutes; distance ->
    max_distance_km * WEEKLY_SHIFT_BUDGET (soft).
    """
    routes = tables["routes"]
    drivers = tables["drivers"]

    iso_year, iso_week = _iso_week_key(service_date)

    # Vectorised ISO week extraction over all routes.
    routes_dt = pd.to_datetime(routes["service_date"], errors="coerce")
    iso_cal = routes_dt.dt.isocalendar()
    week_mask = (iso_cal["year"].astype(int) == iso_year) & (iso_cal["week"].astype(int) == iso_week)
    week_routes = routes[week_mask][["route_id", "driver_id", "planned_time_minutes", "planned_distance_km"]]
    if week_routes.empty:
        return []

    weekly = week_routes.groupby("driver_id").agg(
        weekly_minutes=("planned_time_minutes", "sum"),
        weekly_dist=("planned_distance_km", "sum"),
    ).reset_index()
    weekly = weekly.merge(
        drivers[["driver_id", "max_hours", "max_distance_km"]], on="driver_id", how="left"
    )

    violations: List[Violation] = []
    for _, row in weekly.iterrows():
        max_min = row["max_hours"] * 60 * _WEEKLY_SHIFT_BUDGET
        if row["weekly_minutes"] > max_min:
            violations.append(Violation(
                rule="driver_hours_cap_nearing",
                severity=Severity.LOW,
                service_date=service_date,
                route_id=None,
                stop_id=None,
                request_id=None,
                client_id=None,
                driver_id=row["driver_id"],
                vehicle_id=None,
                explanation=(
                    f"{row['driver_id']}: planned {row['weekly_minutes']} min "
                    f"this week exceeds weekly cap of {int(max_min)} min "
                    f"({row['max_hours']}h/shift × {_WEEKLY_SHIFT_BUDGET} shifts)"
                ),
                suggested_fix=f"Redistribute routes to reduce {row['driver_id']} weekly hours",
            ))
        max_dist = row["max_distance_km"] * _WEEKLY_SHIFT_BUDGET
        if row["weekly_dist"] > max_dist:
            violations.append(Violation(
                rule="driver_distance_cap_nearing",
                severity=Severity.LOW,
                service_date=service_date,
                route_id=None,
                stop_id=None,
                request_id=None,
                client_id=None,
                driver_id=row["driver_id"],
                vehicle_id=None,
                explanation=(
                    f"{row['driver_id']}: planned {row['weekly_dist']:.1f} km "
                    f"this week exceeds soft cap of {max_dist:.1f} km"
                ),
                suggested_fix=f"Redistribute routes to reduce {row['driver_id']} weekly distance",
            ))
    return violations


def run_all(tables: Dict[str, pd.DataFrame], service_date: date) -> pd.DataFrame:
    """Run all implemented detector rules and return a unified sorted DataFrame.

    Columns match Violation dataclass fields exactly. Returns an empty DataFrame with
    the correct schema when there are no violations so callers can .loc[] safely.
    """
    columns = [
        "rule", "severity", "service_date", "route_id", "stop_id",
        "request_id", "client_id", "driver_id", "vehicle_id",
        "explanation", "suggested_fix",
    ]

    all_violations: List[Violation] = []
    all_violations.extend(check_severe_allergen(tables, service_date))
    all_violations.extend(check_cold_chain(tables, service_date))
    all_violations.extend(check_wheelchair_lift(tables, service_date))
    all_violations.extend(check_two_person_solo(tables, service_date))
    all_violations.extend(check_post_closure_delivery(tables, service_date))
    all_violations.extend(check_driver_pet_allergy(tables, service_date))
    all_violations.extend(check_interpreter_language(tables, service_date))
    all_violations.extend(check_driver_hours_distance(tables, service_date))

    if not all_violations:
        return pd.DataFrame(columns=columns)

    df = pd.DataFrame([asdict(v) for v in all_violations], columns=columns)
    df["_sev_rank"] = df["severity"].map(_SEVERITY_RANK).fillna(99)
    df = df.sort_values(
        ["_sev_rank", "service_date", "stop_id"],
        na_position="last",
        kind="stable",
    ).drop(columns=["_sev_rank"]).reset_index(drop=True)

    return df
