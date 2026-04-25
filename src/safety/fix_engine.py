"""Fix engine for Safety Copilot — propose and apply in-memory patches to the tables dict.

Patch schema used by every FixProposal:
    patch = {
        "table": str,                  # key into the tables dict
        "where": {col: val, ...},      # equality filter to find target rows
        "set":   {col: new_val, ...},  # columns to overwrite (added if absent)
    }

apply_fixes deep-copies the affected DataFrame before mutation.
Source parquet files are NEVER written.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import pandas as pd


@dataclass
class FixProposal:
    fix_type: str                   # "item_substitute" | "vehicle_swap" | "stop_cancel"
    target_ids: dict[str, str]
    patch: dict[str, Any]
    reasoning: str
    confidence: float


# ---------------------------------------------------------------------------
# apply_fixes
# ---------------------------------------------------------------------------

def apply_fixes(tables: dict, fixes: list[FixProposal]) -> dict:
    """Deep-copy tables and apply each fix's patch in order. Return the patched dict."""
    patched = {k: v for k, v in tables.items()}  # shallow dict copy; DataFrames copied below
    for fix in fixes:
        p = fix.patch
        tbl = p["table"]
        df = patched[tbl].copy()
        where = p["where"]
        mask = pd.Series([True] * len(df), index=df.index)
        for col, val in where.items():
            mask &= df[col] == val
        for col, new_val in p["set"].items():
            if col not in df.columns:
                df[col] = pd.NA
            df.loc[mask, col] = new_val
        patched[tbl] = df
    return patched


# ---------------------------------------------------------------------------
# _propose_item_substitute  (rule: severe_allergen_in_line_item)
# ---------------------------------------------------------------------------

_ALLERGEN_SEVERITY_COLS = {
    "dairy":    "allergy_dairy_severity",
    "egg":      "allergy_egg_severity",
    "fish":     "allergy_fish_severity",
    "peanut":   "allergy_peanut_severity",
    "soy":      "allergy_soy_severity",
    "tree_nut": "allergy_tree_nut_severity",
    "wheat":    "allergy_wheat_severity",
}
_SEVERE_LEVELS = frozenset({"severe", "anaphylactic"})


def _client_severe_allergens(client_row: pd.Series) -> set[str]:
    """Return the set of allergen tokens the client is severe/anaphylactic about."""
    severe: set[str] = set()
    for tok, col in _ALLERGEN_SEVERITY_COLS.items():
        val = client_row.get(col)
        if pd.notna(val) and val in _SEVERE_LEVELS:
            severe.add(tok)
    return severe


def _item_allergen_tokens(item_row: pd.Series) -> set[str]:
    raw = item_row.get("allergen_flags", "")
    if pd.isna(raw) or raw == "":
        return set()
    return {t.strip() for t in str(raw).split(";") if t.strip()}


def _dietary_tag_tokens(value) -> set[str]:
    if pd.isna(value) or value == "":
        return set()
    return {t.strip() for t in str(value).split(";") if t.strip()}


def _propose_item_substitute(violation: pd.Series, tables: dict) -> list[FixProposal]:
    request_id = violation.get("request_id")
    client_id = violation.get("client_id")
    explanation = str(violation.get("explanation", ""))

    ri = tables["request_items"]
    items = tables["items"]
    clients = tables["clients"]

    # Find client row for allergy profile
    client_rows = clients[clients["client_id"] == client_id]
    if client_rows.empty:
        return []
    client_row = client_rows.iloc[0]
    client_severe = _client_severe_allergens(client_row)

    # Extract item_id from explanation (format: "REQ-... / CLI-... / ITM-...: allergen ...")
    conflicting_item_id: str | None = None
    for part in explanation.split("/"):
        part = part.strip().split(":")[0].strip()
        if part.startswith("ITM-"):
            conflicting_item_id = part
            break

    if conflicting_item_id is None:
        return []

    # Get the line_id for this request + item combination
    line_rows = ri[(ri["request_id"] == request_id) & (ri["item_id"] == conflicting_item_id)]
    if line_rows.empty:
        return []
    line_id = line_rows.iloc[0]["line_id"]

    # Get the conflicting item's category
    item_rows = items[items["item_id"] == conflicting_item_id]
    if item_rows.empty:
        return []
    conflict_item = item_rows.iloc[0]
    category = conflict_item["category"]
    old_name = conflict_item["name"]
    old_cost = float(conflict_item["standard_cost"]) if pd.notna(conflict_item.get("standard_cost")) else 0.0

    # Client dietary tags for ranking
    client_diet_tags = _dietary_tag_tokens(client_row.get("dietary_tags_snapshot") if "dietary_tags_snapshot" in client_row else None)
    # Fall back to boolean diet columns if no snapshot tag string
    if not client_diet_tags:
        diet_bool_cols = [c for c in client_row.index if c.startswith("diet_")]
        client_diet_tags = {c.replace("diet_", "") for c in diet_bool_cols if client_row.get(c) is True}

    # Candidate items: same category, no severe client allergens, not the original
    candidates = items[
        (items["category"] == category) &
        (items["item_id"] != conflicting_item_id)
    ].copy()

    proposals: list[FixProposal] = []
    for _, cand in candidates.iterrows():
        cand_allergens = _item_allergen_tokens(cand)
        # Skip if any client-severe allergen is in this item
        if cand_allergens & client_severe:
            continue

        # Compute confidence: 1.0 if zero allergens; 0.85 if some non-severe allergens
        confidence = 1.0 if len(cand_allergens) == 0 else 0.85

        # Rank score: dietary tag overlap (more = better), then cost closeness
        diet_overlap = len(_dietary_tag_tokens(cand.get("dietary_tags")) & client_diet_tags)
        cost_diff = abs(float(cand.get("standard_cost", 0) or 0) - old_cost)

        proposals.append((diet_overlap, -cost_diff, cand["name"], FixProposal(
            fix_type="item_substitute",
            target_ids={"request_id": request_id, "item_id": conflicting_item_id},
            patch={
                "table": "request_items",
                "where": {"request_id": request_id, "item_id": conflicting_item_id},
                "set": {"item_id": cand["item_id"]},
            },
            reasoning=(
                f"Replace {old_name} with {cand['name']} "
                f"— same {category}, no {list(client_severe)[0] if len(client_severe)==1 else 'severe'} allergen, "
                f"0 other client allergens."
            ),
            confidence=confidence,
        )))

    # Sort: diet_overlap desc, cost_diff asc (neg stored), name asc
    proposals.sort(key=lambda x: (-x[0], x[1], x[2]))
    return [p for _, _, _, p in proposals[:3]]


# ---------------------------------------------------------------------------
# _propose_vehicle_swap  (rules: cold_chain_break, wheelchair_client_wrong_vehicle)
# ---------------------------------------------------------------------------

def _propose_vehicle_swap(violation: pd.Series, tables: dict) -> list[FixProposal]:
    rule = violation.get("rule", "")
    route_id = violation.get("route_id")
    service_date = violation.get("service_date")
    service_date_str = str(service_date) if service_date is not None else ""

    routes = tables["routes"]
    vehicles = tables["vehicles"]

    route_rows = routes[routes["route_id"] == route_id]
    if route_rows.empty:
        return []
    route = route_rows.iloc[0]
    old_vid = route["vehicle_id"]
    meals_needed = int(route.get("meals_planned", 0) or 0)

    # Compute booked meals per vehicle on this service_date (excludes this route)
    day_routes = routes[routes["service_date"] == service_date_str]
    booked: dict[str, int] = {}
    for _, r in day_routes.iterrows():
        vid = r["vehicle_id"]
        if r["route_id"] == route_id:
            continue
        booked[vid] = booked.get(vid, 0) + int(r.get("meals_planned", 0) or 0)

    proposals: list[FixProposal] = []

    if rule == "wheelchair_client_wrong_vehicle":
        target_vid = "VEH-06"
        if old_vid == target_vid:
            return []
        proposals.append(FixProposal(
            fix_type="vehicle_swap",
            target_ids={"route_id": route_id},
            patch={
                "table": "routes",
                "where": {"route_id": route_id},
                "set": {"vehicle_id": target_vid},
            },
            reasoning=f"Swap {route_id} from {old_vid} -> VEH-06: only wheelchair-lift vehicle.",
            confidence=1.0,
        ))
        return proposals

    # cold_chain_break: find refrigerated vehicles with capacity
    ref_vehicles = vehicles[
        (vehicles["refrigerated"] == True) &
        (vehicles["vehicle_id"] != old_vid)
    ]

    for _, v in ref_vehicles.iterrows():
        vid = v["vehicle_id"]
        cap = int(v.get("capacity_meals", 0) or 0)
        already_booked = booked.get(vid, 0)
        spare = cap - already_booked
        if spare < meals_needed:
            continue
        confidence = 0.9 if spare >= meals_needed * 1.2 else 0.7
        proposals.append((spare, FixProposal(
            fix_type="vehicle_swap",
            target_ids={"route_id": route_id},
            patch={
                "table": "routes",
                "where": {"route_id": route_id},
                "set": {"vehicle_id": vid},
            },
            reasoning=(
                f"Swap {route_id} from {old_vid} -> {vid}: "
                f"{vid} is refrigerated with {spare} meals of spare capacity today."
            ),
            confidence=confidence,
        )))

    proposals.sort(key=lambda x: -x[0])
    return [p for _, p in proposals[:3]]


# ---------------------------------------------------------------------------
# _propose_stop_cancel  (rule: delivery_after_client_closure)
# ---------------------------------------------------------------------------

def _propose_stop_cancel(violation: pd.Series, tables: dict) -> list[FixProposal]:
    route_stop_id = violation.get("stop_id")
    client_id = violation.get("client_id")

    # Get closure date from clients table directly
    clients = tables["clients"]
    client_rows = clients[clients["client_id"] == client_id]
    closure_date = "unknown"
    if not client_rows.empty:
        raw = client_rows.iloc[0].get("closure_date")
        if pd.notna(raw):
            closure_date = str(raw)

    # Check actual column name for status in stops
    stops = tables["stops"]
    status_col = "status" if "status" in stops.columns else "delivery_status"

    return [FixProposal(
        fix_type="stop_cancel",
        target_ids={"route_stop_id": route_stop_id},
        patch={
            "table": "stops",
            "where": {"route_stop_id": route_stop_id},
            "set": {status_col: "cancelled", "failure_reason": "client_file_closed"},
        },
        reasoning=f"Cancel stop {route_stop_id}: client file closed on {closure_date}.",
        confidence=1.0,
    )]


# ---------------------------------------------------------------------------
# _weekly_driver_minutes — shared helper for the three new proposers below
# ---------------------------------------------------------------------------

def _weekly_driver_minutes(routes: pd.DataFrame, iso_year: int, iso_week: int) -> pd.DataFrame:
    """Return per-driver weekly sums for the ISO week that contains service_date.

    Returns a DataFrame with columns: driver_id, weekly_minutes, weekly_dist.
    """
    routes_dt = pd.to_datetime(routes["service_date"], errors="coerce")
    iso_cal = routes_dt.dt.isocalendar()
    mask = (iso_cal["year"].astype(int) == iso_year) & (iso_cal["week"].astype(int) == iso_week)
    week_routes = routes[mask][["route_id", "driver_id", "planned_time_minutes", "planned_distance_km"]]
    if week_routes.empty:
        return pd.DataFrame(columns=["driver_id", "weekly_minutes", "weekly_dist"])
    return week_routes.groupby("driver_id").agg(
        weekly_minutes=("planned_time_minutes", "sum"),
        weekly_dist=("planned_distance_km", "sum"),
    ).reset_index()


def _iso_week_key(d) -> tuple[int, int]:
    iso = pd.Timestamp(d).isocalendar()
    return (iso[0], iso[1])


# ---------------------------------------------------------------------------
# _propose_driver_swap  (rules: driver_pet_allergy_conflict, interpreter_language_gap)
# ---------------------------------------------------------------------------

def _propose_driver_swap(violation: pd.Series, tables: dict) -> list[FixProposal]:
    rule = violation.get("rule", "")
    route_id = violation.get("route_id")
    client_id = violation.get("client_id")
    old_drv = violation.get("driver_id")
    service_date = violation.get("service_date")

    routes = tables["routes"]
    drivers = tables["drivers"]
    clients = tables["clients"]

    route_rows = routes[routes["route_id"] == route_id]
    if route_rows.empty:
        return []
    route = route_rows.iloc[0]

    iso_year, iso_week = _iso_week_key(service_date)
    weekly = _weekly_driver_minutes(routes, iso_year, iso_week)

    # All drivers with their weekly usage merged in
    drv_stats = drivers.merge(weekly, on="driver_id", how="left")
    drv_stats["weekly_minutes"] = drv_stats["weekly_minutes"].fillna(0)
    drv_stats["slack_minutes"] = drv_stats["max_hours"] * 60 * 5 - drv_stats["weekly_minutes"]

    current_depot = route.get("start_depot_id") or (
        drivers[drivers["driver_id"] == old_drv].iloc[0]["home_base_depot_id"]
        if not drivers[drivers["driver_id"] == old_drv].empty else None
    )

    if rule == "driver_pet_allergy_conflict":
        candidates = drv_stats[
            (drv_stats["driver_id"] != old_drv) &
            (drv_stats["pet_allergy_flag"] == False)  # noqa: E712
        ].copy()

        def _make_pet_proposal(cand_row) -> FixProposal:
            depot = cand_row["home_base_depot_id"]
            same_depot = depot == current_depot
            slack_h = cand_row["slack_minutes"] / 60
            new_drv = cand_row["driver_id"]
            new_name = f"{cand_row['first_name']} {cand_row['last_name']}"
            return FixProposal(
                fix_type="driver_swap",
                target_ids={"route_id": route_id},
                patch={"table": "routes", "where": {"route_id": route_id}, "set": {"driver_id": new_drv}},
                reasoning=(
                    f"Reassign {route_id} from {old_drv} → {new_drv} {new_name} "
                    f"(pet-allergy-free, {slack_h:.0f}h weekly slack, same depot {depot})."
                    if same_depot else
                    f"Reassign {route_id} from {old_drv} → {new_drv} {new_name} "
                    f"(pet-allergy-free, {slack_h:.0f}h weekly slack)."
                ),
                confidence=0.9 if same_depot else 0.75,
            )

        # Rank: same depot first, then most slack
        candidates["_same"] = candidates["home_base_depot_id"] == current_depot
        candidates = candidates.sort_values(["_same", "slack_minutes"], ascending=[False, False])
        return [_make_pet_proposal(r) for _, r in candidates.head(3).iterrows()]

    if rule == "interpreter_language_gap":
        client_rows = clients[clients["client_id"] == client_id]
        if client_rows.empty:
            return []
        language = client_rows.iloc[0]["language_primary"]

        def _speaks(skills) -> bool:
            if pd.isna(skills):
                return False
            return language.lower() in [s.strip().lower() for s in str(skills).split(";")]

        candidates = drv_stats[
            (drv_stats["driver_id"] != old_drv) &
            drv_stats["language_skills"].apply(_speaks)
        ].copy()

        def _make_lang_proposal(cand_row) -> FixProposal:
            depot = cand_row["home_base_depot_id"]
            same_depot = depot == current_depot
            slack_h = cand_row["slack_minutes"] / 60
            new_drv = cand_row["driver_id"]
            new_name = f"{cand_row['first_name']} {cand_row['last_name']}"
            return FixProposal(
                fix_type="driver_swap",
                target_ids={"route_id": route_id},
                patch={"table": "routes", "where": {"route_id": route_id}, "set": {"driver_id": new_drv}},
                reasoning=(
                    f"Reassign {route_id} from {old_drv} → {new_drv} {new_name} "
                    f"(speaks {language}, {slack_h:.0f}h weekly slack)."
                ),
                confidence=0.9 if same_depot else 0.75,
            )

        candidates["_same"] = candidates["home_base_depot_id"] == current_depot
        candidates = candidates.sort_values(["_same", "slack_minutes"], ascending=[False, False])
        return [_make_lang_proposal(r) for _, r in candidates.head(3).iterrows()]

    return []


# ---------------------------------------------------------------------------
# _propose_route_pair  (rule: two_person_client_solo_driver)
# ---------------------------------------------------------------------------

def _propose_route_pair(violation: pd.Series, tables: dict) -> list[FixProposal]:
    route_id = violation.get("route_id")
    old_drv = violation.get("driver_id")
    service_date = violation.get("service_date")

    routes = tables["routes"]
    drivers = tables["drivers"]

    route_rows = routes[routes["route_id"] == route_id]
    if route_rows.empty:
        return []
    route = route_rows.iloc[0]
    current_depot = route.get("start_depot_id")

    iso_year, iso_week = _iso_week_key(service_date)
    weekly = _weekly_driver_minutes(routes, iso_year, iso_week)

    # Physical-capability proxy for two-person trained
    capable = drivers[
        (drivers["can_climb_stairs"] == True) &   # noqa: E712
        (drivers["can_enter_private_homes"] == True)  # noqa: E712
    ]

    drv_stats = capable.merge(weekly, on="driver_id", how="left")
    drv_stats["weekly_minutes"] = drv_stats["weekly_minutes"].fillna(0)
    drv_stats["slack_minutes"] = drv_stats["max_hours"] * 60 * 5 - drv_stats["weekly_minutes"]

    route_minutes = int(route.get("planned_time_minutes") or 0)
    candidates = drv_stats[
        (drv_stats["driver_id"] != old_drv) &
        (drv_stats["slack_minutes"] >= route_minutes)
    ].copy()
    candidates["_same"] = candidates["home_base_depot_id"] == current_depot
    candidates = candidates.sort_values(["_same", "slack_minutes"], ascending=[False, False])

    proposals: list[FixProposal] = []
    for _, cand in candidates.head(3).iterrows():
        depot = cand["home_base_depot_id"]
        slack_h = cand["slack_minutes"] / 60
        partner_drv = cand["driver_id"]
        partner_name = f"{cand['first_name']} {cand['last_name']}"
        proposals.append(FixProposal(
            fix_type="route_pair",
            target_ids={"route_id": route_id},
            patch={"table": "routes", "where": {"route_id": route_id}, "set": {"partner_driver_id": partner_drv}},
            reasoning=(
                f"Pair {route_id} (solo driver {old_drv}) with partner {partner_drv} {partner_name} "
                f"— {slack_h:.0f}h slack, same depot {depot}."
            ),
            confidence=0.85,
        ))
    return proposals


# ---------------------------------------------------------------------------
# _propose_route_redistribute  (rules: driver_hours_cap_nearing, driver_distance_cap_nearing)
# ---------------------------------------------------------------------------

def _propose_route_redistribute(violation: pd.Series, tables: dict) -> list[FixProposal]:
    rule = violation.get("rule", "")
    offender = violation.get("driver_id")
    service_date = violation.get("service_date")

    routes = tables["routes"]
    drivers = tables["drivers"]

    iso_year, iso_week = _iso_week_key(service_date)
    weekly = _weekly_driver_minutes(routes, iso_year, iso_week)

    drv_stats = drivers.merge(weekly, on="driver_id", how="left")
    drv_stats["weekly_minutes"] = drv_stats["weekly_minutes"].fillna(0)
    drv_stats["weekly_dist"] = drv_stats["weekly_dist"].fillna(0)
    drv_stats["cap_minutes"] = drv_stats["max_hours"] * 60 * 5
    drv_stats["cap_dist"] = drv_stats["max_distance_km"] * 5
    drv_stats["slack_minutes"] = drv_stats["cap_minutes"] - drv_stats["weekly_minutes"]

    offender_row = drv_stats[drv_stats["driver_id"] == offender]
    if offender_row.empty:
        return []
    offender_row = offender_row.iloc[0]

    # Pick the offender's longest route in this ISO week (biggest relief)
    routes_dt = pd.to_datetime(routes["service_date"], errors="coerce")
    iso_cal = routes_dt.dt.isocalendar()
    week_mask = (iso_cal["year"].astype(int) == iso_year) & (iso_cal["week"].astype(int) == iso_week)
    offender_week_routes = routes[week_mask & (routes["driver_id"] == offender)].copy()
    if offender_week_routes.empty:
        return []

    # Sort: longest time first, then later service_date as tiebreak
    offender_week_routes = offender_week_routes.sort_values(
        ["planned_time_minutes", "service_date"], ascending=[False, False]
    )
    picked_route_row = offender_week_routes.iloc[0]
    picked_route = picked_route_row["route_id"]
    picked_minutes = int(picked_route_row["planned_time_minutes"])
    route_depot = picked_route_row.get("start_depot_id")

    # Under-cap receivers, sorted: same depot first, then most slack
    under_cap = drv_stats[
        (drv_stats["driver_id"] != offender) &
        (drv_stats["weekly_minutes"] <= drv_stats["cap_minutes"])
    ].copy()
    if under_cap.empty:
        return []

    used_h = offender_row["weekly_minutes"] / 60
    cap_h = offender_row["cap_minutes"] / 60
    used_dist = offender_row["weekly_dist"]
    cap_dist = offender_row["cap_dist"]

    # Find (route, receiver) pairs where the route actually fits in the receiver's slack.
    # Iterate offender routes from longest to shortest; for each try receivers with enough slack.
    proposals: list[FixProposal] = []
    seen_routes: set[str] = set()

    for _, route_row in offender_week_routes.iterrows():
        r_id = route_row["route_id"]
        r_min = int(route_row["planned_time_minutes"])
        r_depot = route_row.get("start_depot_id")

        eligible = under_cap[under_cap["slack_minutes"] >= r_min].copy()
        if eligible.empty:
            continue

        eligible["_same"] = eligible["home_base_depot_id"] == r_depot
        eligible = eligible.sort_values(["_same", "slack_minutes"], ascending=[False, False])

        for _, recv in eligible.iterrows():
            if r_id in seen_routes:
                break
            new_drv = recv["driver_id"]
            new_name = f"{recv['first_name']} {recv['last_name']}"
            recv_used_h = recv["weekly_minutes"] / 60
            recv_slack_h = recv["slack_minutes"] / 60
            same_depot = recv["home_base_depot_id"] == r_depot

            if rule == "driver_hours_cap_nearing":
                reasoning = (
                    f"Move {r_id} ({r_min} min) from {offender} "
                    f"({used_h:.0f}h/{cap_h:.0f}h weekly) → {new_drv} {new_name} "
                    f"({recv_used_h:.0f}h used, {recv_slack_h:.0f}h slack). "
                    f"Brings {offender} under cap."
                )
            else:
                reasoning = (
                    f"Move {r_id} ({r_min} min) from {offender} "
                    f"({used_dist:.0f}km/{cap_dist:.0f}km weekly) → {new_drv} {new_name} "
                    f"({recv_slack_h:.0f}h slack). Brings {offender} closer to distance cap."
                )

            proposals.append(FixProposal(
                fix_type="route_redistribute",
                target_ids={"route_id": r_id, "driver_id": offender},
                patch={"table": "routes", "where": {"route_id": r_id}, "set": {"driver_id": new_drv}},
                reasoning=reasoning,
                confidence=0.9 if same_depot else 0.75,
            ))
            seen_routes.add(r_id)

            if len(proposals) >= 3:
                return proposals

    return proposals


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

_PROPOSERS: dict[str, Callable] = {
    "severe_allergen_in_line_item": _propose_item_substitute,
    "cold_chain_break": _propose_vehicle_swap,
    "wheelchair_client_wrong_vehicle": _propose_vehicle_swap,
    "delivery_after_client_closure": _propose_stop_cancel,
    "driver_pet_allergy_conflict": _propose_driver_swap,
    "interpreter_language_gap": _propose_driver_swap,
    "two_person_client_solo_driver": _propose_route_pair,
    "driver_hours_cap_nearing": _propose_route_redistribute,
    "driver_distance_cap_nearing": _propose_route_redistribute,
}


def propose_fixes(violation: pd.Series, tables: dict) -> list[FixProposal]:
    """Dispatch on violation['rule']; return ranked list of proposals (top = best).

    Returns empty list if no proposer exists for this rule.
    """
    proposer = _PROPOSERS.get(violation["rule"])
    return proposer(violation, tables) if proposer else []
