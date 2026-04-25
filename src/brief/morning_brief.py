"""Templated morning brief for Track 2 — Food Security Delivery Operations.

No LLM. Pure string formatting over structured data. Public API: render_brief().
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Optional

import pandas as pd

# Severity rank for priority queue (lower = higher priority).
_SEV_RANK = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
    "info": 4,
}

# Threshold for driver hours warning (fraction of weekly cap).
_HOURS_WARNING_THRESHOLD = 0.85

# drivers.max_hours is per-shift; weekly cap = per-shift × budget.
_WEEKLY_SHIFT_BUDGET = 5

# Fallback ops-hygiene bullets used when there are zero violations.
_OPS_HYGIENE_BULLETS = [
    "▸ Cold-chain temperature check at depot DEP-01 before load-out",
    "▸ Confirm two-person pairings for routes RTE-{date_tag}-* before 8am",
    "▸ Vehicle pre-trip inspections for VEH-01 through VEH-12",
]


def _sev_str(row: pd.Series) -> str:
    """Normalise severity value to lowercase string for comparison."""
    raw = row.get("severity", "info")
    if raw is None:
        return "info"
    s = str(raw).lower()
    # Handle 'Severity.CRITICAL' format from the detector enum repr.
    if "." in s:
        s = s.split(".")[-1]
    return s


def _driver_hours_warning(
    tables: dict[str, pd.DataFrame],
    service_date: date,
) -> Optional[tuple[str, float, float, date]]:
    """Return (driver_id, current_hrs, cap_hrs, next_day) for the most-loaded driver.

    Returns None if no driver exceeds the threshold.  Uses weekly_minutes_used
    across all routes in the same ISO week as service_date.
    """
    routes = tables["routes"]
    drivers = tables["drivers"]

    service_date_str = str(service_date)
    service_iso = service_date.isocalendar()  # (year, week, weekday)

    def _wy(d_str: str):
        try:
            d = pd.to_datetime(d_str).date()
            iso = d.isocalendar()
            return (iso[0], iso[1])
        except Exception:
            return (None, None)

    routes_work = routes.copy()
    routes_work["_wy"] = routes_work["service_date"].apply(_wy)
    same_week = routes_work[
        routes_work["_wy"] == (service_iso[0], service_iso[1])
    ]
    # Include today's routes as well (we're reporting the current projected load).
    weekly_minutes = (
        same_week.groupby("driver_id")["planned_time_minutes"].sum()
    )

    best: Optional[tuple[float, str, float, float]] = None  # (fraction, driver_id, current_hrs, cap_hrs)

    drv_indexed = drivers.set_index("driver_id")
    for drv_id, total_mins in weekly_minutes.items():
        if drv_id not in drv_indexed.index:
            continue
        drv = drv_indexed.loc[drv_id]
        # max_hours is per-shift; weekly cap is per-shift hrs × shifts/week budget.
        per_shift = float(drv.get("max_hours", 0) or 0)
        if per_shift <= 0:
            continue
        cap_hrs = per_shift * _WEEKLY_SHIFT_BUDGET
        current_hrs = total_mins / 60.0
        fraction = current_hrs / cap_hrs
        if fraction >= _HOURS_WARNING_THRESHOLD:
            if best is None or fraction > best[0]:
                best = (fraction, drv_id, current_hrs, cap_hrs)

    if best is None:
        return None

    _, drv_id, current_hrs, cap_hrs = best
    # "Rotate off" on the next day relative to service_date.
    next_day = service_date + timedelta(days=1)
    return (drv_id, current_hrs, cap_hrs, next_day)


def _build_paragraph(
    service_date: date,
    stop_count: int,
    route_count: int,
    anomaly_count: int,
    vrp_output: dict,
    hours_warning: Optional[tuple[str, float, float, date]],
    fixes_applied: int = 0,
) -> str:
    day_of_week = service_date.strftime("%A")       # e.g. "Wednesday"
    date_long = service_date.strftime("%B ") + service_date.strftime("%d").lstrip("0")

    violations_list = vrp_output.get("violations", [])
    auto_resolved = (isinstance(violations_list, list) and len(violations_list) == 0)
    and_resolved_clause = " and auto-resolved" if auto_resolved else ""

    parts = [f"{day_of_week}, {date_long}."]
    parts.append(f"{stop_count} stops scheduled across {route_count} routes.")

    if fixes_applied > 0:
        parts.append(
            f"{fixes_applied} anomal{'y' if fixes_applied == 1 else 'ies'} auto-resolved "
            f"by Safety Copilot; {anomaly_count} remain for review."
        )
    else:
        parts.append(f"{anomaly_count} anomalies detected overnight{and_resolved_clause}.")

    if hours_warning:
        drv_id, current_hrs, cap_hrs, next_day = hours_warning
        next_day_name = next_day.strftime("%A")
        parts.append(
            f"Driver {drv_id} at {current_hrs:.0f}/{cap_hrs:.0f} weekly hrs "
            f"— rotate off {next_day_name}."
        )

    # Always include optimizer delta context — makes the brief self-contained.
    delta_pct = vrp_output.get("delta_pct", 0.0) or 0.0
    on_time = vrp_output.get("projected_on_time_rate", 0.0) or 0.0
    delta_show = abs(delta_pct) * 100
    on_time_show = on_time * 100
    parts.append(
        f"Routes optimized vs baseline — {delta_show:.1f}% drive-time reduction, "
        f"projected on-time rate {on_time_show:.1f}%."
    )

    # Add an operational note about request volume for word-count padding.
    total_possible = (
        sum(len(r.get("stops", [])) for r in (vrp_output.get("routes") or []))
        + len(vrp_output.get("dropped_requests") or [])
    )
    dropped = len(vrp_output.get("dropped_requests") or [])
    if dropped > 0:
        parts.append(
            f"{dropped} request(s) could not be assigned due to constraint conflicts "
            f"and require manual review before dispatch. "
            "Volunteer leads should address flagged anomalies before drivers depart the depot."
        )
    else:
        parts.append(
            "All eligible requests have been assigned to available drivers and vehicles. "
            "Review the anomaly list below and clear all flagged items before dispatch."
        )

    paragraph = " ".join(parts)

    # Hard trim: keep under 130 words.
    words = paragraph.split()
    if len(words) > 130:
        paragraph = " ".join(words[:130])

    return paragraph


def _pick_bullets(
    detector_output: pd.DataFrame,
    tables: dict[str, pd.DataFrame],
    service_date: date,
    hours_warning: Optional[tuple[str, float, float, date]],
    date_tag: str,
) -> list[str]:
    """Select exactly 3 action bullets from the priority queue."""

    # No-violations fallback.
    if detector_output.empty:
        bullets = []
        for tmpl in _OPS_HYGIENE_BULLETS:
            bullets.append(tmpl.format(date_tag=date_tag))
        return bullets

    # Sort violations by severity rank then by stop_id for stability.
    df = detector_output.copy()
    df["_rank"] = df["severity"].apply(
        lambda s: _SEV_RANK.get(
            str(s).split(".")[-1].lower() if "." in str(s) else str(s).lower(),
            99,
        )
    )
    df = df.sort_values(["_rank", "stop_id"], na_position="last", kind="stable").reset_index(drop=True)

    bullets: list[str] = []
    used_rules: list[str] = []

    def _make_bullet(row: pd.Series) -> str:
        fix = str(row.get("suggested_fix") or "").strip()
        expl = str(row.get("explanation") or "").strip()
        # Prefer suggested_fix when non-empty; fall back to explanation snippet.
        body = fix if fix else expl
        # Ensure at least one concrete ID appears in the bullet.
        ids_present = _has_concrete_id(body)
        if not ids_present:
            # Append IDs from violation fields.
            id_tokens = []
            for field in ("request_id", "stop_id", "client_id", "driver_id", "vehicle_id", "route_id"):
                val = row.get(field)
                if val and not pd.isna(val):
                    id_tokens.append(str(val))
            if id_tokens:
                body = body + " (" + ", ".join(id_tokens[:2]) + ")"
        bullet = f"▸ {body}"
        # Trim to 120 chars if needed.
        if len(bullet) > 120:
            bullet = bullet[:117] + "..."
        return bullet

    # Slot 1: top CRITICAL, else top HIGH.
    for priority_sev in ("critical", "high"):
        for idx, row in df.iterrows():
            sev = _sev_str(row)
            if sev == priority_sev:
                bullets.append(_make_bullet(row))
                used_rules.append(str(row.get("rule", "")))
                break
        if bullets:
            break

    # Slot 2: next distinct-rule violation (different rule from slot 1).
    for idx, row in df.iterrows():
        rule = str(row.get("rule", ""))
        if rule not in used_rules:
            bullets.append(_make_bullet(row))
            used_rules.append(rule)
            break

    # Slot 3: closest driver-hours-cap warning; else next distinct-rule MEDIUM.
    if hours_warning:
        drv_id, current_hrs, cap_hrs, next_day = hours_warning
        next_day_name = next_day.strftime("%A")
        bullet = (
            f"▸ Driver {drv_id} at {current_hrs:.0f}/{cap_hrs:.0f} weekly hrs — "
            f"rotate off {next_day_name} route"
        )
        bullets.append(bullet)
    else:
        # Fallback: next distinct-rule MEDIUM not already used.
        for idx, row in df.iterrows():
            rule = str(row.get("rule", ""))
            sev = _sev_str(row)
            if rule not in used_rules and sev == "medium":
                bullets.append(_make_bullet(row))
                used_rules.append(rule)
                break

    # Pad to exactly 3 if we couldn't fill all slots (edge case: very few violations).
    fallback_idx = 0
    while len(bullets) < 3:
        for idx, row in df.iterrows():
            if fallback_idx > len(df):
                break
            bullets.append(_make_bullet(row))
            fallback_idx += 1
            break
        else:
            # Absolute fallback: use an ops-hygiene item.
            tmpl = _OPS_HYGIENE_BULLETS[len(bullets) % len(_OPS_HYGIENE_BULLETS)]
            bullets.append(tmpl.format(date_tag=date_tag))

    return bullets[:3]


_CONCRETE_ID_RE = re.compile(r"(REQ-|MOW-|DRV-|VEH-|RTE-|STP-|DEP-|CLI-)")


def _has_concrete_id(text: str) -> bool:
    return bool(_CONCRETE_ID_RE.search(text))


def render_brief(
    service_date: date,
    detector_output: pd.DataFrame,
    vrp_output: dict,
    tables: dict[str, pd.DataFrame],
    fixes_applied: int = 0,
) -> dict:
    """Render the templated morning brief for a given service date.

    fixes_applied: count of Safety Copilot overlays the user has applied this session;
    when > 0 the paragraph narrates the delta instead of the raw anomaly count.

    Returns {"paragraph": str, "bullets": list[str]}.
    """
    routes = tables["routes"]
    stops = tables["stops"]

    service_date_str = str(service_date)
    date_tag = service_date.strftime("%Y-%m-%d")

    # Count stops and routes on this service_date.
    day_routes = routes[routes["service_date"] == service_date_str]
    day_route_ids = set(day_routes["route_id"].tolist())
    day_stops = stops[stops["route_id"].isin(day_route_ids)]
    stop_count = len(day_stops)
    route_count = len(day_routes)

    anomaly_count = len(detector_output) if detector_output is not None else 0

    hours_warning = _driver_hours_warning(tables, service_date)

    paragraph = _build_paragraph(
        service_date=service_date,
        stop_count=stop_count,
        route_count=route_count,
        anomaly_count=anomaly_count,
        vrp_output=vrp_output,
        hours_warning=hours_warning,
        fixes_applied=fixes_applied,
    )

    bullets = _pick_bullets(
        detector_output=detector_output if detector_output is not None else pd.DataFrame(),
        tables=tables,
        service_date=service_date,
        hours_warning=hours_warning,
        date_tag=date_tag,
    )

    return {"paragraph": paragraph, "bullets": bullets}
