"""Baseline route quality scorer for Track 2 — Food Security Delivery.

Lifted from cell 7 of tracks/food-security-delivery/notebooks/00_quickstart.ipynb
(the "Baseline model, greedy route quality scorer" cell).  The scoring logic is
preserved exactly so that the optimizer's delta_pct is an apples-to-apples
comparison.

Public API:
    score_baseline(tables, service_date) -> dict
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd


def score_baseline(tables: dict, service_date: date) -> dict:
    """Score the kit's greedy baseline for a single service_date.

    Returns a dict with:
        total_drive_minutes     int   sum of planned_time_minutes for routes on that date
        projected_on_time_rate  float mean on_time_rate across those routes
        per_route               list[dict]  one entry per route with detail fields

    The scoring uses the same composite formula as notebook cell 7:
        quality_score = 0.4*on_time_rate + 0.3*completion_rate
                        + 0.2*skill_match_rate - 0.1*cold_chain_violations_norm

    Drive-time proxy is planned_time_minutes from the routes table, which is the
    best available pre-computed estimate without re-solving haversine distances.
    """
    routes = tables["routes"]
    stops = tables["stops"]
    drivers = tables["drivers"]

    # Filter to the requested service_date (string comparison is safe here because
    # routes.service_date is stored as object/string in the parquet).
    service_date_str = service_date.isoformat() if isinstance(service_date, date) else str(service_date)
    day_routes = routes[routes["service_date"] == service_date_str].copy()

    if day_routes.empty:
        return {
            "total_drive_minutes": 0,
            "projected_on_time_rate": 0.0,
            "per_route": [],
        }

    route_ids = day_routes["route_id"].tolist()
    day_stops = stops[stops["route_id"].isin(route_ids)].copy()

    # ---- Golden join: attach driver skill info for skill_match calculation ----
    # Replicate notebook cell 7's stops_enriched join for skill_match_rate:
    # stops + drivers (via routes)
    route_driver = day_routes[["route_id", "driver_id"]].copy()
    drivers_slim = drivers[["driver_id", "can_handle_wheelchair"]].copy()
    day_stops = (
        day_stops
        .merge(route_driver, on="route_id", how="left")
        .merge(drivers_slim, on="driver_id", how="left")
    )
    # Clients table carries mobility_wheelchair — but the notebook used `wheelchair_user`
    # (notebook schema), which maps to `mobility_wheelchair` in the real parquet.
    clients = tables["clients"]
    clients_slim = clients[["client_id", "mobility_wheelchair"]].copy()
    day_stops = day_stops.merge(clients_slim, on="client_id", how="left")

    # ---- Grouped metrics, mirroring notebook cell 7 exactly ----
    route_stops_grp = day_stops.groupby("route_id")

    # completion_rate: fraction of stops with status == 'completed' or 'delivered'
    # (notebook used 'completed'; real data uses 'delivered' — treat both as success)
    def _completion(g: pd.DataFrame) -> float:
        if len(g) == 0:
            return 0.0
        success = g["status"].isin(["completed", "delivered"]).sum()
        return float(success) / len(g)

    completion = route_stops_grp.apply(_completion).rename("completion_rate")

    def _skill_match(g: pd.DataFrame) -> float:
        if len(g) == 0:
            return 1.0
        wc_clients = g["mobility_wheelchair"].fillna(False)
        lift = g["can_handle_wheelchair"].fillna(False)
        needs_lift = wc_clients
        matched = (~needs_lift) | lift
        return float(matched.sum()) / len(g)

    skill_match = route_stops_grp.apply(_skill_match).rename("skill_match_rate")

    cold_violations = route_stops_grp.apply(
        lambda g: (g["failure_reason"] == "cold_chain_violation").sum()
    ).rename("cold_chain_violations")
    max_cv = max(cold_violations.max(), 1)
    cold_violations_norm = (cold_violations / max_cv).rename("cold_chain_violations_norm")

    score_df = (
        day_routes[["route_id", "driver_id", "on_time_rate", "planned_stops",
                    "actual_stops", "planned_time_minutes"]]
        .merge(completion.reset_index(), on="route_id", how="left")
        .merge(skill_match.reset_index(), on="route_id", how="left")
        .merge(cold_violations.reset_index(), on="route_id", how="left")
        .merge(cold_violations_norm.reset_index(), on="route_id", how="left")
        .fillna({
            "on_time_rate": 0.0,
            "completion_rate": 0.0,
            "skill_match_rate": 1.0,
            "cold_chain_violations": 0,
            "cold_chain_violations_norm": 0.0,
        })
    )

    score_df["quality_score"] = (
        0.4 * score_df["on_time_rate"]
        + 0.3 * score_df["completion_rate"]
        + 0.2 * score_df["skill_match_rate"]
        - 0.1 * score_df["cold_chain_violations_norm"]
    )

    # nn_savings_estimate_pct — notebook cell 7's placeholder heuristic
    score_df["nn_savings_estimate_pct"] = np.where(
        score_df["planned_stops"] > 0,
        (1 - score_df["quality_score"]) * 15.0,
        0.0,
    )

    total_drive = int(score_df["planned_time_minutes"].sum())
    mean_on_time = float(score_df["on_time_rate"].mean())

    per_route = score_df[[
        "route_id", "driver_id", "on_time_rate", "completion_rate",
        "skill_match_rate", "cold_chain_violations", "quality_score",
        "nn_savings_estimate_pct", "planned_time_minutes",
    ]].to_dict(orient="records")

    return {
        "total_drive_minutes": total_drive,
        "projected_on_time_rate": mean_on_time,
        "per_route": per_route,
    }
