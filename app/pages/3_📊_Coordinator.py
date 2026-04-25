"""Coordinator Console — weekly operations + fleet health.

Two tabs:
  - Weekly Operations: KPIs, burnout watchlist, evaluation scorecard, route table.
  - Fleet Health:      driver utilization gauges + vehicle capability cards.

The Fleet tab replaces the separate Fleet page (consolidated).
"""

from __future__ import annotations

from datetime import timedelta, date as date_type, datetime as _dt
from pathlib import Path
import re as _re
import sys

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import numpy as np
import pandas as pd
import streamlit as st

from app._layout import inject_phone_css
from app._role import enforce_role
from app._fleet_view import render_fleet_health
from app._data import load_all, DATA_DIR_DEFAULT
from src.safety.fix_engine import apply_fixes

st.set_page_config(page_title="Safety Copilot — Coordinator", layout="wide", page_icon="📊")
inject_phone_css()
enforce_role({"coordinator"})

# ── Data ──────────────────────────────────────────────────────────────────
try:
    tables_raw = load_all(DATA_DIR_DEFAULT)
except FileNotFoundError as exc:
    st.error(str(exc))
    st.stop()

st.session_state.setdefault("applied_fixes", [])
tables  = apply_fixes(tables_raw, st.session_state["applied_fixes"])
routes  = tables["routes"]
drivers = tables["drivers"]
stops   = tables["stops"]


# ── ISO-week helpers ──────────────────────────────────────────────────────
def _iso_week(d_str) -> tuple:
    try:
        d = pd.to_datetime(d_str).date()
        iso = d.isocalendar()
        return (iso[0], iso[1])
    except Exception:
        return (None, None)


routes_work = routes.copy()
routes_work["_wy"]   = routes_work["service_date"].apply(_iso_week)
routes_work["_date"] = pd.to_datetime(routes_work["service_date"], errors="coerce").dt.date

week_map: dict[str, tuple] = {}
for wy in routes_work["_wy"].dropna().unique():
    if wy[0] is None:
        continue
    jan4 = date_type(wy[0], 1, 4)
    mon = jan4 - timedelta(days=jan4.isocalendar()[2] - 1) + timedelta(weeks=wy[1] - 1)
    sun = mon + timedelta(days=6)
    label = f"W{wy[1]:02d}: {mon.strftime('%b')} {mon.day} – {sun.strftime('%b')} {sun.day}, {sun.year}"
    week_map[label] = wy

week_labels = sorted(week_map.keys(), reverse=True)


# ── Sidebar ────────────────────────────────────────────────────────────────
st.sidebar.markdown("## 📊 Coordinator Console")
selected_week_label = st.sidebar.selectbox("Week", options=week_labels, index=0)
selected_wy = week_map[selected_week_label]
depot_choice = st.sidebar.selectbox("Depot filter", options=["All depots", "DEP-01", "DEP-02"])

week_routes = routes_work[routes_work["_wy"] == selected_wy].copy()
if depot_choice != "All depots":
    week_routes = week_routes[week_routes["start_depot_id"] == depot_choice]
week_route_ids = set(week_routes["route_id"].tolist())
week_stops = stops[stops["route_id"].isin(week_route_ids)]

# Date range for header
if not week_routes.empty:
    min_d = week_routes["_date"].dropna().min()
    max_d = week_routes["_date"].dropna().max()
    week_range_str = (
        f"{min_d.strftime('%A, %b')} {min_d.day} to "
        f"{max_d.strftime('%A, %b')} {max_d.day}, {max_d.year}"
    ) if min_d else selected_week_label
else:
    week_range_str = selected_week_label


# ── Header ────────────────────────────────────────────────────────────────
st.markdown(
    f"""<div style="margin-bottom:18px;">
      <div style="font-size:1.6rem;font-weight:800;color:#0f172a;letter-spacing:-0.01em;">
        📊 Coordinator Console
      </div>
      <div style="color:#475569;font-size:0.95rem;margin-top:2px;">
        Week of {week_range_str}
      </div>
    </div>""",
    unsafe_allow_html=True,
)


# ── Tabs ───────────────────────────────────────────────────────────────────
tab_weekly, tab_fleet = st.tabs(["📅 Weekly Operations", "🚚 Fleet Health"])

with tab_weekly:
    # KPI grid
    total_stops = len(week_stops)
    mean_on_time = (
        week_routes["on_time_rate"].dropna().mean()
        if "on_time_rate" in week_routes.columns else float("nan")
    )
    mean_on_time_str = f"{mean_on_time*100:.1f}%" if not np.isnan(mean_on_time) else "N/A"
    total_drive_mins = int(week_routes["planned_time_minutes"].fillna(0).sum())

    # Fairness Gini over drivers' weekly minutes
    drv_weekly_mins = week_routes.groupby("driver_id")["planned_time_minutes"].sum()
    if len(drv_weekly_mins) > 1:
        arr = np.sort(drv_weekly_mins.values.astype(float))
        n = len(arr)
        idx = np.arange(1, n + 1)
        gini = (
            (2 * np.sum(idx * arr) / (n * arr.sum()) - (n + 1) / n)
            if arr.sum() > 0 else 0.0
        )
    else:
        gini = 0.0

    try:
        import streamlit_shadcn_ui as ui
        _use_ui = True
    except Exception:
        _use_ui = False

    st.markdown('<div class="section-header">Weekly KPIs</div>', unsafe_allow_html=True)
    cols = st.columns(4)
    for col, (title, content, desc) in zip(
        cols,
        [
            ("Total stops",       str(total_stops),                    "planned this week"),
            ("Mean on-time rate", mean_on_time_str,                    "across routes this week"),
            ("Total drive time",  f"{total_drive_mins:,} min",         "planned minutes"),
            ("Fairness Gini",     f"{gini:.3f}",                       "0 = perfect equality"),
        ],
    ):
        with col:
            if _use_ui:
                ui.metric_card(title=title, content=content, description=desc)
            else:
                st.metric(title, content, desc)

    # Driver burnout watchlist
    st.markdown('<div class="section-header">Driver Burnout Watchlist</div>', unsafe_allow_html=True)
    drv_indexed = drivers.set_index("driver_id")
    rows = []
    for drv_id, total_mins in drv_weekly_mins.items():
        if drv_id not in drv_indexed.index:
            continue
        drv = drv_indexed.loc[drv_id]
        per_shift = float(drv.get("max_hours", 0) or 0)
        cap_hrs = per_shift * 5
        hours_used = total_mins / 60.0
        ratio = hours_used / cap_hrs if cap_hrs > 0 else 0.0
        rows.append({
            "driver_id":  drv_id,
            "name":       f"{str(drv.get('first_name','') or '').title()} "
                          f"{str(drv.get('last_name','') or '').title()}".strip(),
            "hours_used": round(hours_used, 1),
            "cap_hours":  round(cap_hrs, 0),
            "ratio":      round(ratio, 3),
            "on_time_rate": drv.get("on_time_rate", float("nan")),
        })
    burnout_df = pd.DataFrame(rows).sort_values("ratio", ascending=False) if rows else pd.DataFrame()

    if burnout_df.empty:
        st.info("No driver data for this week.")
    else:
        for _, r in burnout_df.iterrows():
            ratio = r["ratio"]
            bg = "background:#fee2e2" if ratio > 1.0 else ("background:#fef9c3" if ratio > 0.85 else "")
            icon = "🔴" if ratio > 1.0 else ("🟡" if ratio > 0.85 else ("🟠" if ratio > 0.7 else "🟢"))
            on_time_str = f"{r['on_time_rate']*100:.0f}%" if not pd.isna(r["on_time_rate"]) else "—"
            st.markdown(
                f'<div style="{bg};border:1px solid #e2e8f0;border-radius:8px;padding:10px 14px;'
                f'margin-bottom:6px;font-size:0.9rem;">'
                f'{icon} <b>{r["driver_id"]}</b> {r["name"]} — '
                f'{r["hours_used"]}h / {int(r["cap_hours"])}h cap '
                f'({ratio*100:.0f}%) · on-time {on_time_str}</div>',
                unsafe_allow_html=True,
            )

    # Scorecard — a compact summary + link to the dedicated Scorecard page.
    # Used to embed the full SCORECARD.md here, but that duplicated the
    # /Scorecard page entirely — coordinator had to scroll past it twice.
    st.markdown('<div class="section-header">Evaluation Scorecard</div>', unsafe_allow_html=True)
    scorecard_path = _REPO_ROOT / "eval" / "SCORECARD.md"
    sc_json_path = _REPO_ROOT / "eval" / "scorecard.json"

    avg_recall_str = "—"
    delta_str = "—"
    if sc_json_path.exists():
        try:
            import json as _json
            sc = _json.loads(sc_json_path.read_text(encoding="utf-8"))
            # Real keys are detector_accuracy and optimizer_delta (not the names
            # I assumed earlier).
            dets = sc.get("detector_accuracy", {})
            recalls = [d.get("recall", 0) for d in dets.values()]
            if recalls:
                avg_recall_str = f"{sum(recalls) / len(recalls) * 100:.0f}%"
            delta_pct = sc.get("optimizer_delta", {}).get("mean_delta_pct")
            if delta_pct is not None:
                # mean_delta_pct is stored as a fraction (0.8905), display as %
                delta_str = f"{delta_pct * 100:.0f}%"
        except Exception:
            pass

    last_gen = (
        _dt.fromtimestamp(scorecard_path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        if scorecard_path.exists() else "never"
    )

    sc_a, sc_b, sc_c = st.columns([2, 2, 1])
    with sc_a:
        st.metric("Avg detector recall", avg_recall_str, help="Across the 3 seeded ground-truth rule families")
    with sc_b:
        st.metric("Optimizer drive-time delta", delta_str, help="ARIA vs baseline")
    with sc_c:
        if st.button("🔄 Regenerate", key="regen_scorecard", use_container_width=True,
                     help=f"Last regenerated: {last_gen}"):
            with st.spinner("Running detector accuracy, optimizer delta on 14 dates, constraint audit…"):
                try:
                    from eval.scorecard import main as _scorecard_main
                    _scorecard_main(
                        out_dir=str(_REPO_ROOT / "eval"),
                        data_dir=str(_REPO_ROOT / "tracks" / "food-security-delivery" / "data" / "raw"),
                    )
                    st.success("Scorecard regenerated.")
                except Exception as exc:
                    st.error(f"Regeneration failed: {exc}")
            st.rerun()

    st.page_link(
        "pages/2_📈_Scorecard.py",
        label="📈 Open the full Scorecard page →",
        use_container_width=True,
    )
    st.caption(f"Last regenerated: {last_gen}")

    # Weekly route table
    st.markdown('<div class="section-header">Weekly Route Table</div>', unsafe_allow_html=True)
    if week_routes.empty:
        st.info("No routes for this week/depot.")
    else:
        display_cols = [
            "route_id", "service_date", "driver_id", "vehicle_id",
            "planned_time_minutes", "actual_time_minutes", "route_status", "on_time_rate",
        ]
        avail = [c for c in display_cols if c in week_routes.columns]
        st.dataframe(
            week_routes[avail].sort_values(
                ["service_date", "route_id"] if "service_date" in avail else ["route_id"]
            ).reset_index(drop=True),
            use_container_width=True,
            hide_index=True,
            column_config={
                "route_id":             st.column_config.TextColumn("Route", width="small"),
                "service_date":         st.column_config.TextColumn("Date", width="small"),
                "driver_id":            st.column_config.TextColumn("Driver", width="small"),
                "vehicle_id":           st.column_config.TextColumn("Vehicle", width="small"),
                "planned_time_minutes": st.column_config.NumberColumn("Planned min", format="%d"),
                "actual_time_minutes":  st.column_config.NumberColumn("Actual min", format="%.0f"),
                "route_status":         st.column_config.TextColumn("Status"),
                "on_time_rate":         st.column_config.ProgressColumn(
                    "On-time", min_value=0.0, max_value=1.0, format="%.0f%%"),
            },
        )


with tab_fleet:
    render_fleet_health(tables)
