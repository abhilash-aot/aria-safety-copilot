"""Fleet Health view — reusable render called from the Coordinator page.

Moved out of `app/pages/1_📊_Fleet.py` during consolidation so Coordinator
can host Fleet as a tab instead of having two pages that overlap.
"""

from __future__ import annotations

import streamlit as st

_FLEET_CSS = """<style>
.fleet-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:14px;margin-top:12px;}
.driver-card{
  background:white;border:1px solid #e2e8f0;border-radius:14px;padding:16px;
  box-shadow:0 3px 12px rgba(15,23,42,0.06);
  animation:slide-in 0.4s ease-out both;
  transition:transform 0.25s,box-shadow 0.25s;position:relative;overflow:hidden;
}
.driver-card:hover{transform:translateY(-3px);box-shadow:0 10px 28px rgba(15,118,110,0.15);}
.driver-card::before{content:"";position:absolute;top:0;left:0;right:0;height:4px;
  background:linear-gradient(90deg,#0f766e,#0891b2);}
.driver-top{display:flex;align-items:center;gap:12px;margin-bottom:12px;}
.avatar{width:44px;height:44px;border-radius:50%;
  background:linear-gradient(135deg,#0f766e,#0891b2);color:white;font-weight:800;font-size:1.05rem;
  display:flex;align-items:center;justify-content:center;flex-shrink:0;
  box-shadow:0 4px 12px rgba(15,118,110,0.35);}
.driver-name{font-weight:800;color:#0f172a;font-size:0.98rem;line-height:1.2;}
.driver-sub{color:#64748b;font-size:0.78rem;}
.chip-row{display:flex;gap:5px;flex-wrap:wrap;margin-top:8px;}
.cap-chip{background:#f0fdfa;color:#0f766e;border:1px solid #99f6e4;
  padding:3px 9px;border-radius:10px;font-size:0.72rem;font-weight:700;}
.cap-chip.warn{background:#fff7ed;color:#c2410c;border-color:#fdba74;}
.cap-chip.lang{background:#eef2ff;color:#4338ca;border-color:#c7d2fe;}
.gauge-wrap{display:flex;align-items:center;gap:12px;margin-top:10px;}
.gauge-svg{flex-shrink:0;}
.gauge-label{flex:1;font-size:0.78rem;color:#475569;}
.gauge-label b{display:block;color:#0f172a;font-size:0.92rem;}
.veh-card{background:white;border:1px solid #e2e8f0;border-radius:14px;padding:16px;
  box-shadow:0 3px 12px rgba(15,23,42,0.06);animation:slide-in 0.4s ease-out both;
  transition:transform 0.25s,box-shadow 0.25s;position:relative;overflow:hidden;}
.veh-card:hover{transform:translateY(-3px);box-shadow:0 10px 28px rgba(8,145,178,0.18);}
.veh-head{display:flex;align-items:center;gap:10px;margin-bottom:10px;}
.veh-icon{width:44px;height:44px;border-radius:10px;
  background:linear-gradient(135deg,#0891b2,#6366f1);color:white;font-size:1.35rem;
  display:flex;align-items:center;justify-content:center;
  box-shadow:0 4px 12px rgba(8,145,178,0.3);}
.veh-id{font-weight:800;color:#0f172a;font-size:0.95rem;}
.veh-sub{color:#64748b;font-size:0.78rem;}
.cap-bar{width:100%;height:8px;background:#f1f5f9;border-radius:4px;margin-top:8px;overflow:hidden;position:relative;}
.cap-fill{height:100%;background:linear-gradient(90deg,#0f766e,#0891b2);border-radius:4px;
  animation:cap-grow 1.1s cubic-bezier(0.4,0,0.2,1) both;}
@keyframes cap-grow{from{width:0;}}
</style>"""

WEEKLY_BUDGET = 5  # shifts per week


def _initials(name: str) -> str:
    parts = str(name).split()
    return (parts[0][0] + (parts[-1][0] if len(parts) > 1 else "")).upper() if parts else "??"


def _gauge(pct: float) -> str:
    pct = max(0, min(pct, 120))
    r = 28
    circ = 2 * 3.14159 * r
    offset = circ - (min(pct, 100) / 100) * circ
    color = "#dc2626" if pct > 100 else "#d97706" if pct >= 85 else "#0f766e"
    return f"""
<svg class="gauge-svg" width="70" height="70" viewBox="0 0 70 70">
  <circle cx="35" cy="35" r="{r}" stroke="#f1f5f9" stroke-width="7" fill="none"/>
  <circle cx="35" cy="35" r="{r}" stroke="{color}" stroke-width="7" fill="none"
          stroke-linecap="round" transform="rotate(-90 35 35)"
          stroke-dasharray="{circ}" stroke-dashoffset="{circ}"
          style="animation:gauge-fill 1.2s cubic-bezier(0.4,0,0.2,1) forwards;">
    <animate attributeName="stroke-dashoffset" from="{circ}" to="{offset}" dur="1.1s" fill="freeze" begin="0.1s"/>
  </circle>
  <text x="35" y="41" text-anchor="middle" font-size="14" font-weight="800" fill="{color}">{int(pct)}%</text>
</svg>"""


def render_fleet_health(tables: dict) -> None:
    """Render the Fleet Health view (KPI strip + driver cards + vehicle cards)."""
    st.markdown(_FLEET_CSS, unsafe_allow_html=True)

    drivers  = tables["drivers"]
    vehicles = tables["vehicles"]
    routes   = tables["routes"]

    util_df = routes.groupby("driver_id")["planned_time_minutes"].sum().reset_index()
    util_df.columns = ["driver_id", "total_min"]
    util_df = drivers.merge(util_df, on="driver_id", how="left").fillna({"total_min": 0})
    util_df["weekly_cap_min"] = util_df["max_hours"] * 60 * WEEKLY_BUDGET
    util_df["util_pct"] = (util_df["total_min"] / util_df["weekly_cap_min"] * 100).clip(0, 120)

    total_drivers = len(drivers)
    over_cap  = int((util_df["util_pct"] > 100).sum())
    near_cap  = int(((util_df["util_pct"] >= 85) & (util_df["util_pct"] <= 100)).sum())
    ref_veh   = int((vehicles["refrigerated"] == True).sum())
    lift_veh  = int((vehicles["wheelchair_lift"] == True).sum())

    st.markdown(f"""
<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px;margin:14px 0;">
  <div style="background:linear-gradient(135deg,#f0fdfa,#f8fafc);border:1.5px solid #ccfbf1;border-radius:12px;padding:14px;text-align:center;">
    <div style="font-size:0.78rem;color:#475569;font-weight:600;">DRIVERS</div>
    <div style="font-size:1.6rem;font-weight:900;color:#0f766e;">{total_drivers}</div>
  </div>
  <div style="background:linear-gradient(135deg,#fffbeb,#fefce8);border:1.5px solid #fde68a;border-radius:12px;padding:14px;text-align:center;">
    <div style="font-size:0.78rem;color:#475569;font-weight:600;">NEAR CAP (≥85%)</div>
    <div style="font-size:1.6rem;font-weight:900;color:#d97706;">{near_cap}</div>
  </div>
  <div style="background:linear-gradient(135deg,#fff1f2,#fef2f2);border:1.5px solid #fecaca;border-radius:12px;padding:14px;text-align:center;">
    <div style="font-size:0.78rem;color:#475569;font-weight:600;">OVER CAP</div>
    <div style="font-size:1.6rem;font-weight:900;color:#dc2626;">{over_cap}</div>
  </div>
  <div style="background:linear-gradient(135deg,#eff6ff,#eef2ff);border:1.5px solid #bfdbfe;border-radius:12px;padding:14px;text-align:center;">
    <div style="font-size:0.78rem;color:#475569;font-weight:600;">REFRIGERATED</div>
    <div style="font-size:1.6rem;font-weight:900;color:#2563eb;">{ref_veh}/{len(vehicles)}</div>
  </div>
  <div style="background:linear-gradient(135deg,#f5f3ff,#faf5ff);border:1.5px solid #ddd6fe;border-radius:12px;padding:14px;text-align:center;">
    <div style="font-size:0.78rem;color:#475569;font-weight:600;">WHEELCHAIR LIFT</div>
    <div style="font-size:1.6rem;font-weight:900;color:#7c3aed;">{lift_veh}/{len(vehicles)}</div>
  </div>
</div>
""", unsafe_allow_html=True)

    # Drivers
    st.markdown('<div class="section-header"><span class="section-icon">👥</span>Drivers</div>',
                unsafe_allow_html=True)
    cards = ['<div class="fleet-grid">']
    for _, d in util_df.iterrows():
        langs = str(d.get("language_skills", "") or "").split(";")
        lang_chips = " ".join(f'<span class="cap-chip lang">{l.strip()}</span>' for l in langs[:3] if l.strip())
        certs = []
        if bool(d.get("can_handle_wheelchair", False)):
            certs.append('<span class="cap-chip">♿ wheelchair</span>')
        if bool(d.get("pet_allergy_flag", False)):
            certs.append('<span class="cap-chip warn">🐶 pet allergy</span>')
        cert_chips = " ".join(certs)
        name = (d.get("first_name", "") or "Driver")
        last = (d.get("last_name", "") or "")
        full = f"{name} {last}".strip()
        cards.append(f"""
<div class="driver-card">
  <div class="driver-top">
    <div class="avatar">{_initials(full)}</div>
    <div>
      <div class="driver-name">{full}</div>
      <div class="driver-sub">{d['driver_id']} · {int(d.get('max_hours',0))}h/shift</div>
    </div>
  </div>
  <div class="gauge-wrap">
    {_gauge(float(d['util_pct']))}
    <div class="gauge-label">
      <b>{int(d['total_min']):,} min planned</b>
      Weekly cap {int(d['weekly_cap_min']):,} min
    </div>
  </div>
  <div class="chip-row">{lang_chips}{cert_chips}</div>
</div>""")
    cards.append("</div>")
    st.markdown("".join(cards), unsafe_allow_html=True)

    # Vehicles
    st.markdown('<div class="section-header"><span class="section-icon">🚚</span>Vehicles</div>',
                unsafe_allow_html=True)
    veh_cards = ['<div class="fleet-grid">']
    max_cap = float(vehicles["capacity_meals"].max() or 1)
    for _, v in vehicles.iterrows():
        icon = "🚚" if v.get("capacity_meals", 0) >= 80 else "🚐"
        badges = []
        if bool(v.get("refrigerated", False)):
            badges.append('<span class="cap-chip">❄️ refrigerated</span>')
        if bool(v.get("wheelchair_lift", False)):
            badges.append('<span class="cap-chip lang">♿ lift</span>')
        cap_meals = int(v.get("capacity_meals", 0) or 0)
        cap_pct = (cap_meals / max_cap * 100) if max_cap > 0 else 0
        veh_cards.append(f"""
<div class="veh-card">
  <div class="veh-head">
    <div class="veh-icon">{icon}</div>
    <div>
      <div class="veh-id">{v['vehicle_id']}</div>
      <div class="veh-sub">{v.get('make','')} {v.get('model','')}</div>
    </div>
  </div>
  <div class="chip-row">{"".join(badges)}</div>
  <div style="margin-top:10px;">
    <div style="display:flex;justify-content:space-between;font-size:0.78rem;color:#475569;">
      <span>Capacity</span><b style="color:#0f766e;">{cap_meals} meals</b>
    </div>
    <div class="cap-bar"><div class="cap-fill" style="width:{cap_pct:.0f}%;"></div></div>
  </div>
</div>""")
    veh_cards.append("</div>")
    st.markdown("".join(veh_cards), unsafe_allow_html=True)
