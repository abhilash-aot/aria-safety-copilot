"""Surplus Food Matching — connect a surplus food offer to eligible clients."""

from __future__ import annotations

from pathlib import Path
import sys

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import folium
import streamlit as st
from streamlit_folium import st_folium

from shared.src.loaders import load_track2
from app._layout import inject_phone_css
from app._role import enforce_role
from src.surplus.matcher import SurplusOffer, MatchResult, match_surplus

# Rough Canadian food-bank valuation per portion (used for impact chip).
_AVG_COST_PER_PORTION_CAD = 8


# ---------------------------------------------------------------------------
# Page setup
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Surplus Match · Safety Copilot", layout="centered", page_icon="🍱")
inject_phone_css()
enforce_role({"volunteer", "coordinator"})

# Page-local CSS
st.markdown("""<style>
.surplus-hero{
  display:flex;align-items:center;gap:14px;margin-bottom:16px;
  animation:slide-in 0.5s ease-out;
}
.surplus-hero-icon{
  font-size:2.2rem;width:60px;height:60px;border-radius:14px;
  background:linear-gradient(135deg,#fed7aa,#fbbf24);
  display:flex;align-items:center;justify-content:center;flex-shrink:0;
  box-shadow:0 4px 14px rgba(251,191,36,0.35);
  animation:surplus-icon-float 3s ease-in-out infinite;
}
@keyframes surplus-icon-float{0%,100%{transform:translateY(0) rotate(0);}50%{transform:translateY(-3px) rotate(-3deg);}}

.offer-card{
  background:linear-gradient(135deg,#fffbeb,#fef3c7);
  border:1.5px solid #fde68a;border-radius:14px;padding:16px 18px;margin-bottom:12px;
  box-shadow:0 3px 12px rgba(217,119,6,0.1);
  animation:slide-in 0.4s ease-out;
}
.offer-card-title{font-weight:800;color:#92400e;font-size:1.05rem;margin-bottom:6px;}
.offer-card-meta{color:#78350f;font-size:0.88rem;line-height:1.65;}
.offer-card-meta b{color:#451a03;}
.offer-allergen-chip{
  display:inline-block;background:#0f172a;color:#fde68a;
  padding:2px 9px;border-radius:7px;font-size:0.78rem;font-weight:700;
  font-family:"SF Mono","Monaco","Consolas",monospace;margin-right:4px;
}
.offer-impact-chip{
  display:inline-block;margin-left:6px;background:#dcfce7;color:#065f46;
  border:1px solid #86efac;padding:3px 10px;border-radius:10px;
  font-size:0.78rem;font-weight:700;
  animation:impact-pop 0.4s cubic-bezier(0.34,1.56,0.64,1) 0.2s both;
}
@keyframes impact-pop{0%{opacity:0;transform:scale(0.7);}70%{transform:scale(1.08);}100%{opacity:1;transform:scale(1);}}

/* Map frame — mirror the Plan page style, lighter */
.surplus-map-wrap{
  border-radius:14px;padding:3px;margin:4px 0 16px;
  background:linear-gradient(135deg,#fbbf24,#10b981,#0891b2,#fbbf24);
  background-size:300% 300%;
  animation:surplus-frame-shift 10s ease-in-out infinite;
  box-shadow:0 6px 22px rgba(15,118,110,0.15);
}
.surplus-map-wrap>iframe,.surplus-map-wrap>div{border-radius:11px;overflow:hidden;}
@keyframes surplus-frame-shift{0%,100%{background-position:0% 50%;}50%{background-position:100% 50%;}}

/* Summary panel — dark, mirrors the Plan hero style */
.match-summary{
  background:linear-gradient(135deg,#0f172a 0%,#134e4a 55%,#0f766e 100%);
  background-size:200% 200%;
  animation:surplus-panel-shift 12s ease-in-out infinite,
            slide-in 0.55s cubic-bezier(0.34,1.56,0.64,1) both;
  color:white;border-radius:18px;padding:22px;margin:14px 0 18px;
  box-shadow:0 12px 36px rgba(15,23,42,0.3);
  position:relative;overflow:hidden;
}
@keyframes surplus-panel-shift{0%,100%{background-position:0% 50%;}50%{background-position:100% 50%;}}
.match-summary::before{
  content:"";position:absolute;inset:0;pointer-events:none;
  background:radial-gradient(at 80% 10%,rgba(103,232,249,0.22),transparent 50%),
             radial-gradient(at 10% 90%,rgba(251,191,36,0.18),transparent 50%);
}
.match-summary-cap{
  font-size:0.72rem;font-weight:800;letter-spacing:0.14em;text-transform:uppercase;
  color:rgba(255,255,255,0.7);margin-bottom:10px;text-align:center;
}
.match-summary-row{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;position:relative;z-index:1;}
.match-summary-stat{text-align:center;padding:6px 4px;}
.match-summary-val{font-size:1.9rem;font-weight:900;line-height:1;color:#67e8f9;font-variant-numeric:tabular-nums;}
.match-summary-val.warn{color:#fca5a5;}
.match-summary-val.ok{color:#a7f3d0;}
.match-summary-lbl{font-size:0.7rem;color:rgba(255,255,255,0.7);letter-spacing:0.06em;margin-top:4px;font-weight:600;}
@media(max-width:600px){ .match-summary-row{grid-template-columns:repeat(2,1fr);} }

/* Match card */
.match-card{
  background:white;border:1px solid #e2e8f0;border-left:5px solid #10b981;
  border-radius:12px;padding:13px 16px;margin-bottom:10px;
  box-shadow:0 2px 8px rgba(15,23,42,0.06);
  animation:slide-in 0.35s ease-out both;
  transition:transform 0.2s,box-shadow 0.2s;
}
.match-card:hover{transform:translateX(3px);box-shadow:0 6px 18px rgba(16,185,129,0.18);}
.match-card.prio-severe  {border-left-color:#dc2626;}
.match-card.prio-moderate{border-left-color:#ea580c;}
.match-card.prio-marginal{border-left-color:#d97706;}
.match-card.prio-secure  {border-left-color:#64748b;}

.match-card-top{display:flex;align-items:center;gap:10px;margin-bottom:4px;}
.match-prio-chip{
  font-size:0.68rem;font-weight:800;letter-spacing:0.1em;
  padding:3px 9px;border-radius:10px;flex-shrink:0;
}
.prio-severe  .match-prio-chip{background:#fee2e2;color:#7f1d1d;border:1px solid #fca5a5;}
.prio-moderate .match-prio-chip{background:#ffedd5;color:#7c2d12;border:1px solid #fdba74;}
.prio-marginal .match-prio-chip{background:#fef3c7;color:#713f12;border:1px solid #fcd34d;}
.prio-secure  .match-prio-chip{background:#f1f5f9;color:#334155;border:1px solid #cbd5e1;}

.match-card-name{font-weight:800;color:#0f172a;font-size:0.98rem;flex:1;}
.match-card-dist{
  font-size:0.82rem;color:#0f766e;font-weight:700;
  background:#f0fdfa;border:1px solid #ccfbf1;padding:3px 9px;border-radius:10px;
  font-variant-numeric:tabular-nums;
}
.match-card-addr{color:#64748b;font-size:0.85rem;margin-top:2px;}

/* Excluded card */
.xcl-card{
  background:linear-gradient(90deg,#fff1f2,#fef2f2);
  border:1px solid #fecaca;border-left:5px solid #dc2626;
  border-radius:12px;padding:13px 16px;margin-bottom:10px;
  box-shadow:0 2px 8px rgba(220,38,38,0.1);
  animation:slide-in 0.35s ease-out both;
}
.xcl-card-top{display:flex;align-items:center;gap:10px;margin-bottom:4px;}
.xcl-card-badge{
  font-size:0.68rem;font-weight:800;letter-spacing:0.1em;
  background:#7f1d1d;color:white;padding:3px 9px;border-radius:10px;flex-shrink:0;
}
.xcl-card-name{font-weight:800;color:#7f1d1d;font-size:0.98rem;flex:1;}
.xcl-card-dist{
  font-size:0.82rem;color:#be123c;font-weight:700;
  background:white;border:1px solid #fecaca;padding:3px 9px;border-radius:10px;
  font-variant-numeric:tabular-nums;
}
.xcl-card-reason{
  color:#7f1d1d;font-size:0.88rem;margin-top:4px;font-weight:600;
}
.xcl-card-reason code{
  background:#7f1d1d;color:#fecaca;padding:1px 7px;border-radius:5px;
  font-family:"SF Mono","Monaco","Consolas",monospace;font-size:0.82em;
}

.sub-section-title{
  font-weight:800;color:#0f172a;font-size:0.92rem;margin:16px 0 8px 0;
  display:flex;align-items:center;gap:8px;
}
.sub-section-title .cnt{
  background:#f1f5f9;color:#475569;font-size:0.72rem;font-weight:700;
  padding:2px 8px;border-radius:10px;margin-left:auto;
}
.xcl-section-title{color:#7f1d1d;}
.xcl-section-title .cnt{background:#fee2e2;color:#7f1d1d;}
</style>""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Hero
# ---------------------------------------------------------------------------
st.markdown("""
<div class="surplus-hero">
  <div class="surplus-hero-icon">🍱</div>
  <div>
    <div class="hero-v2-title" style="font-size:1.65rem;">Surplus Match</div>
    <div class="hero-v2-sub">Connect surplus food to hungry neighbours before it's wasted</div>
  </div>
</div>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Demo presets — 3 scenarios showing different safety stories
# ---------------------------------------------------------------------------
DEMO_OFFERS: dict[str, SurplusOffer] = {
    "🍛 Chicken Curry — dairy allergen": SurplusOffer(
        name="Chicken Curry",
        portions=30,
        allergens=["dairy"],
        lat=48.4267, lng=-123.3692,
        pickup_by="11:00 PM tonight",
        donor_name="Noodle Box Restaurant",
        cold_chain=True,
    ),
    "🥜 Thai Peanut Bowl — peanut allergen": SurplusOffer(
        name="Thai Peanut Bowl",
        portions=22,
        allergens=["peanut"],
        lat=48.4336, lng=-123.3547,
        pickup_by="9:30 PM tonight",
        donor_name="Green Leaf Kitchen",
        cold_chain=False,
    ),
    "🥖 Bread Loaves — wheat allergen": SurplusOffer(
        name="Fresh Bread Loaves",
        portions=48,
        allergens=["wheat"],
        lat=48.4210, lng=-123.3781,
        pickup_by="8:00 AM tomorrow",
        donor_name="Cobb's Bread",
        cold_chain=False,
    ),
}


# ---------------------------------------------------------------------------
# Form — demo preset selector + manual fallback
# ---------------------------------------------------------------------------
mode = st.radio(
    "Offer source",
    ["Demo presets", "Enter manually"],
    horizontal=True,
    label_visibility="collapsed",
)

if mode == "Demo presets":
    preset_name = st.selectbox(
        "Demo preset",
        list(DEMO_OFFERS.keys()),
        label_visibility="collapsed",
    )
    offer = DEMO_OFFERS[preset_name]
else:
    with st.container():
        c1, c2 = st.columns(2)
        with c1:
            name     = st.text_input("Food item", value="Pasta Marinara")
            portions = st.number_input("Portions available", min_value=1, value=20, step=1)
            donor    = st.text_input("Donor name", value="Community Kitchen")
            pickup   = st.text_input("Pickup by", value="10:00 PM tonight")
        with c2:
            allergens_str = st.text_input("Allergens (comma-separated)", value="wheat, dairy")
            lat           = st.number_input("Pickup latitude",  value=48.4267, format="%.4f")
            lng           = st.number_input("Pickup longitude", value=-123.3692, format="%.4f")
            cold          = st.checkbox("Requires cold chain", value=False)

        offer = SurplusOffer(
            name=name,
            portions=int(portions),
            allergens=[a.strip() for a in allergens_str.split(",") if a.strip()],
            lat=float(lat),
            lng=float(lng),
            pickup_by=pickup,
            donor_name=donor,
            cold_chain=bool(cold),
        )


# ---------------------------------------------------------------------------
# Offer preview card
# ---------------------------------------------------------------------------
_allergen_chips = " ".join(
    f'<span class="offer-allergen-chip">{a}</span>' for a in offer.allergens
) or '<span style="color:#78350f;">no declared allergens</span>'

_cold_chip = (
    '<span class="offer-allergen-chip" style="background:#0c4a6e;color:#bae6fd;">❄️ cold chain</span>'
    if offer.cold_chain else ""
)

_impact_cad = offer.portions * _AVG_COST_PER_PORTION_CAD

st.markdown(f"""
<div class="offer-card">
  <div class="offer-card-title">🍱 {offer.name} — {offer.portions} portions</div>
  <div class="offer-card-meta">
    From <b>{offer.donor_name}</b> · Pickup by <b>{offer.pickup_by}</b><br/>
    Allergens: {_allergen_chips} {_cold_chip}
    <span class="offer-impact-chip">💚 ~${_impact_cad} saved from landfill</span>
  </div>
</div>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Find matches button
# ---------------------------------------------------------------------------
find = st.button("🔍 Find Matches", type="primary", use_container_width=True)


# Auto-run in demo mode so judges see results instantly; manual mode waits
# for an explicit click so the form isn't constantly re-matching.
should_match = find or (mode == "Demo presets")

if not should_match:
    st.info("Fill the form above and click **Find Matches**.")
    st.stop()


# ---------------------------------------------------------------------------
# Compute matches
# ---------------------------------------------------------------------------
try:
    tables = load_track2("tracks/food-security-delivery/data/raw")
except FileNotFoundError as exc:
    st.error(str(exc))
    st.stop()

with st.spinner("🔍 Scanning active clients for eligible matches…"):
    matched, excluded = match_surplus(offer, tables, max_results=10)


# ---------------------------------------------------------------------------
# Summary panel
# ---------------------------------------------------------------------------
n_matched  = len(matched)
n_excluded = len(excluded)
portions   = offer.portions
if matched:
    nearest   = min(m.distance_km for m in matched)
    farthest  = max(m.distance_km for m in matched)
    dist_str  = f"{nearest:.1f}–{farthest:.1f} km"
else:
    dist_str  = "—"

st.markdown(f"""
<div class="match-summary">
  <div class="match-summary-cap">MATCH RESULTS</div>
  <div class="match-summary-row">
    <div class="match-summary-stat">
      <div class="match-summary-val ok">{n_matched}</div>
      <div class="match-summary-lbl">ELIGIBLE MATCHES</div>
    </div>
    <div class="match-summary-stat">
      <div class="match-summary-val warn">{n_excluded}</div>
      <div class="match-summary-lbl">EXCLUDED FOR SAFETY</div>
    </div>
    <div class="match-summary-stat">
      <div class="match-summary-val">{portions}</div>
      <div class="match-summary-lbl">PORTIONS READY</div>
    </div>
    <div class="match-summary-stat">
      <div class="match-summary-val" style="font-size:1.15rem;color:#fde68a;padding-top:10px;">
        {dist_str}
      </div>
      <div class="match-summary-lbl">DISTANCE RANGE</div>
    </div>
  </div>
</div>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Mini-map — pickup + matched (green) + excluded (red) with connecting lines
# ---------------------------------------------------------------------------
if matched or excluded:
    # Centre on pickup for tight framing
    fmap = folium.Map(location=[offer.lat, offer.lng], zoom_start=12, tiles="CartoDB positron")

    # Connecting lines: pickup → each matched client (subtle teal)
    for m in matched:
        folium.PolyLine(
            locations=[(offer.lat, offer.lng), (m.lat, m.lng)],
            color="#0f766e", weight=2, opacity=0.35, dash_array="4,6",
        ).add_to(fmap)

    # Matched client pins — green dots, numbered by rank
    for i, m in enumerate(matched, start=1):
        folium.Marker(
            location=[m.lat, m.lng],
            popup=folium.Popup(
                f'<b>#{i} · {m.name}</b><br/>{m.food_security_level.title()} food insecurity'
                f'<br/>{m.distance_km:.1f} km from pickup<br/>{m.client_id}',
                max_width=240,
            ),
            tooltip=f"#{i} {m.name} · {m.distance_km:.1f} km",
            icon=folium.DivIcon(
                html=f'<div style="background:#10b981;color:white;border-radius:50%;'
                     f'width:26px;height:26px;display:flex;align-items:center;justify-content:center;'
                     f'font-size:11px;font-weight:800;border:2.5px solid white;'
                     f'box-shadow:0 2px 8px rgba(16,185,129,0.55);">{i}</div>',
                icon_size=(26, 26), icon_anchor=(13, 13),
            ),
        ).add_to(fmap)

    # Excluded client pins — red X
    for x in excluded:
        folium.Marker(
            location=[x.lat, x.lng],
            popup=folium.Popup(
                f'<b>🚫 Blocked · {x.name}</b><br/>{x.exclusion_reason}'
                f'<br/>{x.distance_km:.1f} km from pickup<br/>{x.client_id}',
                max_width=240,
            ),
            tooltip=f"🚫 {x.name} · {x.exclusion_reason}",
            icon=folium.DivIcon(
                html='<div style="background:#dc2626;color:white;border-radius:50%;'
                     'width:22px;height:22px;display:flex;align-items:center;justify-content:center;'
                     'font-size:14px;font-weight:900;border:2px solid white;'
                     'box-shadow:0 2px 6px rgba(220,38,38,0.55);">×</div>',
                icon_size=(22, 22), icon_anchor=(11, 11),
            ),
        ).add_to(fmap)

    # Pickup pin — amber, large, on top
    folium.Marker(
        location=[offer.lat, offer.lng],
        popup=folium.Popup(
            f'<b>🍱 {offer.name}</b><br/>{offer.portions} portions · {offer.donor_name}'
            f'<br/>Pickup by {offer.pickup_by}',
            max_width=240,
        ),
        tooltip=f"🍱 Pickup · {offer.donor_name}",
        icon=folium.DivIcon(
            html='<div style="background:linear-gradient(135deg,#fbbf24,#f59e0b);'
                 'color:#7c2d12;border-radius:10px;width:38px;height:38px;'
                 'display:flex;align-items:center;justify-content:center;font-size:1.2rem;'
                 'border:3px solid white;box-shadow:0 4px 12px rgba(251,191,36,0.55);">🍱</div>',
            icon_size=(38, 38), icon_anchor=(19, 19),
        ),
    ).add_to(fmap)

    # Inline legend overlay
    fmap.get_root().html.add_child(folium.Element("""
    <div style="position:fixed;top:10px;right:10px;z-index:9999;
                background:rgba(255,255,255,0.96);padding:9px 11px;
                border-radius:9px;border:1px solid #e2e8f0;
                box-shadow:0 4px 12px rgba(0,0,0,0.1);
                font-family:sans-serif;font-size:11px;line-height:1.7;max-width:160px;">
      <div style="font-weight:800;color:#0f172a;margin-bottom:3px;font-size:12px;">Legend</div>
      <div><span style="display:inline-block;width:14px;height:14px;border-radius:3px;background:linear-gradient(135deg,#fbbf24,#f59e0b);vertical-align:middle;margin-right:6px;">🍱</span>Pickup</div>
      <div><span style="display:inline-block;width:12px;height:12px;border-radius:50%;background:#10b981;vertical-align:middle;margin-right:6px;"></span>Eligible match</div>
      <div><span style="display:inline-block;width:12px;height:12px;border-radius:50%;background:#dc2626;vertical-align:middle;margin-right:6px;"></span>Blocked (allergen)</div>
    </div>"""))

    st.markdown('<div class="surplus-map-wrap">', unsafe_allow_html=True)
    st_folium(fmap, width=None, height=380, returned_objects=[])
    st.markdown('</div>', unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Matched clients
# ---------------------------------------------------------------------------
_PRIO_LABEL = {
    "severe":   "SEVERE",
    "moderate": "MODERATE",
    "marginal": "MARGINAL",
    "secure":   "SECURE",
}

if matched:
    st.markdown(
        f'<div class="sub-section-title">'
        f'<span class="section-icon">✅</span>Top matches '
        f'<span class="cnt">{n_matched} found</span></div>',
        unsafe_allow_html=True,
    )
    cards_html = []
    for m in matched:
        fs = m.food_security_level if m.food_security_level in _PRIO_LABEL else "secure"
        prio_label = _PRIO_LABEL.get(fs, "—")
        cards_html.append(f"""
<div class="match-card prio-{fs}">
  <div class="match-card-top">
    <span class="match-prio-chip">{prio_label}</span>
    <span class="match-card-name">{m.name}</span>
    <span class="match-card-dist">📍 {m.distance_km:.1f} km</span>
  </div>
  <div class="match-card-addr">{m.client_id} · {m.address}</div>
</div>""")
    st.markdown("".join(cards_html), unsafe_allow_html=True)
else:
    st.warning("No eligible matches found. Try widening the offer (fewer allergens) or check active client coverage.")


# ---------------------------------------------------------------------------
# Excluded (safety story)
# ---------------------------------------------------------------------------
if excluded:
    st.markdown(
        f'<div class="sub-section-title xcl-section-title">'
        f'<span class="section-icon">🚫</span>Excluded for safety '
        f'<span class="cnt">{n_excluded} blocked</span></div>',
        unsafe_allow_html=True,
    )
    st.caption(
        "These clients are nearby, but this offer contains an allergen "
        "they have a **severe or anaphylactic** reaction to. The matcher blocks "
        "them automatically — no human risk of a delivery mistake."
    )
    xcl_html = []
    for x in excluded:
        xcl_html.append(f"""
<div class="xcl-card">
  <div class="xcl-card-top">
    <span class="xcl-card-badge">BLOCKED</span>
    <span class="xcl-card-name">{x.name}</span>
    <span class="xcl-card-dist">📍 {x.distance_km:.1f} km</span>
  </div>
  <div class="xcl-card-reason">🔴 <code>{x.exclusion_reason}</code> · {x.client_id}</div>
</div>""")
    st.markdown("".join(xcl_html), unsafe_allow_html=True)
