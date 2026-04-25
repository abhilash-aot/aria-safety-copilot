"""Driver Console — Tom in his truck. Phone-first single-column."""

from __future__ import annotations

from pathlib import Path
import sys

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import pandas as pd
import streamlit as st

from app._layout import inject_phone_css
from app._role import enforce_role
from app._data import load_all, all_service_dates, DATA_DIR_DEFAULT
from src.safety.fix_engine import apply_fixes

st.set_page_config(page_title="Safety Copilot — Driver", layout="centered", page_icon="🚚")
inject_phone_css()
enforce_role({"driver"})

# ── Data ──────────────────────────────────────────────────────────────────────

try:
    tables_raw = load_all(DATA_DIR_DEFAULT)
except FileNotFoundError as exc:
    st.error(str(exc))
    st.stop()

st.session_state.setdefault("applied_fixes", [])
tables = apply_fixes(tables_raw, st.session_state["applied_fixes"])

dates = all_service_dates(tables)
if not dates:
    st.warning("No service dates found.")
    st.stop()

drivers = tables["drivers"]
driver_ids = sorted(drivers["driver_id"].dropna().unique().tolist())

# ── Sidebar ───────────────────────────────────────────────────────────────────

st.sidebar.markdown("## 🚚 Driver Console")

service_date = st.sidebar.date_input(
    "Service date",
    value=dates[len(dates) // 2],
    min_value=dates[0],
    max_value=dates[-1],
)

selected_driver_id = st.sidebar.selectbox("Driver", options=driver_ids)

drv_row = drivers[drivers["driver_id"] == selected_driver_id]
if not drv_row.empty:
    drv = drv_row.iloc[0]
    drv_name = f"{str(drv.get('first_name','') or '').title()} {str(drv.get('last_name','') or '').title()}".strip()
    st.sidebar.caption(f"Viewing as **{selected_driver_id}** ({drv_name}) — admin mode")
else:
    drv = None
    drv_name = selected_driver_id

# ── Header card ───────────────────────────────────────────────────────────────

st.markdown(
    f"""<div style="background:linear-gradient(135deg,#0f172a 0%,#1e3a5f 100%);
         border-radius:12px;padding:20px;margin-bottom:16px;color:white;">
      <div style="font-size:1.4rem;font-weight:800;">🚚 {drv_name}</div>
      <div style="font-size:0.9rem;opacity:0.85;margin-top:4px;">
        {selected_driver_id} · {str(drv.get('role_type','') or '').replace('_',' ').title() if drv is not None else ''}
      </div>
    </div>""",
    unsafe_allow_html=True,
)

if drv is not None:
    vehicle_id = str(drv.get("vehicle_id", "") or "")
    depot_id = str(drv.get("home_base_depot_id", "") or "")
    # Trim seconds from "08:00:00" to "08:00" so the Shift cell doesn't get
    # truncated by Streamlit's metric column to "08:00:00–15:0…".
    def _hhmm(t: str) -> str:
        t = str(t or "").strip()
        return t[:5] if len(t) >= 5 else (t or "—")
    shift_start = _hhmm(drv.get("shift_start", ""))
    shift_end   = _hhmm(drv.get("shift_end", ""))
    max_hours = drv.get("max_hours", "—")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Vehicle", vehicle_id or "—")
    with c2:
        st.metric("Depot", depot_id or "—")
    with c3:
        shift_str = f"{shift_start}–{shift_end}" if shift_start != "—" else "—"
        st.metric("Shift", shift_str)
    with c4:
        st.metric("Max", f"{max_hours}h" if max_hours != "—" else "—")

# ── Today's route ─────────────────────────────────────────────────────────────

routes_today = tables["routes"][
    (tables["routes"]["service_date"].astype(str) == str(service_date)) &
    (tables["routes"]["driver_id"] == selected_driver_id)
]

if routes_today.empty:
    st.info(f"No route assigned to **{selected_driver_id}** on **{service_date}**.")

    # Helpful nudges: who else IS driving today, and which dates this driver covers.
    routes_all = tables["routes"]
    same_day = routes_all[routes_all["service_date"].astype(str) == str(service_date)]
    other_drivers = sorted(set(same_day["driver_id"].dropna()) - {selected_driver_id})
    same_drv = routes_all[routes_all["driver_id"] == selected_driver_id]
    other_dates = sorted(set(same_drv["service_date"].dropna().astype(str)))[:6]

    nc1, nc2 = st.columns(2)
    with nc1:
        st.markdown("**🧑‍✈️ Who's driving today?**")
        if other_drivers:
            st.markdown(" ".join(
                f'<span style="background:#f0fdfa;color:#0f766e;border:1px solid #99f6e4;'
                f'padding:3px 9px;border-radius:10px;font-size:0.8rem;font-weight:700;'
                f'margin-right:4px;display:inline-block;margin-bottom:4px;">{d}</span>'
                for d in other_drivers
            ), unsafe_allow_html=True)
        else:
            st.caption("No drivers assigned today.")
    with nc2:
        st.markdown(f"**📅 {selected_driver_id}'s recent routes**")
        if other_dates:
            st.markdown(" ".join(
                f'<span style="background:#eff6ff;color:#1e40af;border:1px solid #bfdbfe;'
                f'padding:3px 9px;border-radius:10px;font-size:0.8rem;font-weight:600;'
                f'margin-right:4px;display:inline-block;margin-bottom:4px;">{d}</span>'
                for d in other_dates
            ), unsafe_allow_html=True)
        else:
            st.caption("This driver has no routes in the dataset.")
    st.stop()

route_row = routes_today.iloc[0]
route_id = route_row["route_id"]

stops_today = tables["stops"][tables["stops"]["route_id"] == route_id].sort_values(
    "sequence_index", na_position="last"
)

# Route summary card
total_stops = int(route_row.get("planned_stops", len(stops_today)))
total_dist = route_row.get("planned_distance_km", 0) or 0
planned_mins = route_row.get("planned_time_minutes", 0) or 0

st.markdown('<div class="section-header">Today\'s Route Summary</div>', unsafe_allow_html=True)
col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Stops", total_stops)
with col2:
    st.metric("Distance", f"{total_dist:.1f} km")
with col3:
    hours = int(planned_mins // 60)
    mins = int(planned_mins % 60)
    st.metric("Est. duration", f"{hours}h {mins}m")

# ── Stops list ────────────────────────────────────────────────────────────────

st.markdown('<div class="section-header">Stop-by-Stop</div>', unsafe_allow_html=True)

clients_idx = tables["clients"].set_index("client_id") if "client_id" in tables["clients"].columns else pd.DataFrame()
requests_idx = tables["requests"].set_index("request_id") if "request_id" in tables["requests"].columns else pd.DataFrame()

def _special_flags(c_row) -> list[str]:
    flags = []
    if c_row.get("mobility_wheelchair"):
        flags.append("🦽 Wheelchair lift required")
    if c_row.get("has_dog_on_premises"):
        flags.append("⚠️ Dog on premises")
    if c_row.get("requires_two_person_team"):
        flags.append("👥 Two-person delivery")
    for allergy_col in [col for col in clients_idx.columns if col.startswith("allergy_") and col.endswith("_severity")]:
        sev = str(c_row.get(allergy_col, "none") or "none").lower()
        if sev in ("severe", "anaphylactic"):
            allergen = allergy_col.replace("allergy_", "").replace("_severity", "")
            flags.append(f"❗ ALLERGEN WARNING: {allergen} {sev}")
    return flags


for i, (_, stop) in enumerate(stops_today.iterrows()):
    client_id = stop.get("client_id")
    request_id = stop.get("request_id")
    seq = stop.get("sequence_index", i + 1)

    # Client info
    c_name, c_addr, flags = "Unknown Client", "", []
    n_items = 0
    tw_start, tw_end = "", ""

    if client_id and client_id in clients_idx.index:
        c = clients_idx.loc[client_id]
        fn = str(c.get("first_name", "") or "").title()
        ln = str(c.get("last_name", "") or "").title()
        c_name = f"{fn} {ln}".strip() or str(client_id)
        street = str(c.get("address_street", "") or "")
        city = str(c.get("address_city", "") or "")
        c_addr = f"{street}, {city}".strip(", ")
        flags = _special_flags(c)

    if request_id and request_id in requests_idx.index:
        req = requests_idx.loc[request_id]
        n_items = int(req.get("quantity_meals", 0) or 0)
        tw_start = str(req.get("time_window_start", "") or "")
        tw_end = str(req.get("time_window_end", "") or "")

    tw_str = f"{tw_start} – {tw_end}" if tw_start else "Flexible"
    flags_html = "".join(
        f'<span style="background:#fef9c3;color:#713f12;font-size:0.78rem;padding:2px 6px;border-radius:10px;margin-right:4px;">{f}</span>'
        for f in flags
    ) if flags else ""

    sev_color = "#fee2e2" if any("ALLERGEN" in f for f in flags) else "#f8fafc"

    st.markdown(
        f"""<div style="background:{sev_color};border:1px solid #e2e8f0;border-radius:10px;
             padding:14px 16px;margin-bottom:12px;">
          <div style="font-weight:700;font-size:1rem;color:#0f172a;">
            Stop {seq} — {c_name}
            <span style="font-size:0.8rem;color:#64748b;font-weight:400;margin-left:8px;">({client_id})</span>
          </div>
          <div style="color:#475569;font-size:0.88rem;margin:4px 0;">📍 {c_addr}</div>
          <div style="color:#475569;font-size:0.88rem;">🕐 Window: {tw_str} · 📦 {n_items} meal(s)</div>
          <div style="margin-top:6px;">{flags_html}</div>
        </div>""",
        unsafe_allow_html=True,
    )

    btn_key = f"stop_{stop.get('route_stop_id', i)}"
    b1, b2, b3 = st.columns(3)
    with b1:
        if st.button("✅ Arrived", key=f"{btn_key}_arr", use_container_width=True):
            st.toast(f"Marked arrived at stop {seq} — {c_name}", icon="✅")
    with b2:
        if st.button("📦 Delivered", key=f"{btn_key}_del", use_container_width=True):
            st.toast(f"Delivery confirmed for {c_name}", icon="📦")
    with b3:
        if st.button("🚪 No answer", key=f"{btn_key}_na", use_container_width=True):
            st.toast(f"No answer logged for {c_name} — supervisor notified", icon="🚪")

    st.markdown("<hr style='margin:4px 0 8px 0;border:none;border-top:1px solid #f1f5f9;'>", unsafe_allow_html=True)
