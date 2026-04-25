"""UI section renderers for the Safety Copilot app — character-driven edition."""

from __future__ import annotations

import re

import folium
from folium.plugins import AntPath
import pandas as pd
import streamlit as st
from streamlit.components.v1 import html as _html
from streamlit_folium import st_folium

# Regex to highlight operator IDs (REQ-, MOW-, CLI-, DRV-, VEH-, RTE-, STP-, ITM-, DEP-)
_ID_PATTERN = re.compile(r"\b(REQ|MOW|CLI|DRV|VEH|RTE|STP|ITM|DEP)-[A-Za-z0-9_-]+\b")

def _highlight_ids(text: str) -> str:
    return _ID_PATTERN.sub(r'<code class="brief-id">\g<0></code>', text)

_SEV_ICON = {
    "critical": "🚨",
    "high":     "⚠️",
    "medium":   "📋",
    "low":      "ℹ️",
    "info":     "•",
}

_VISIBLE_CAP = 30


def _hash_color(value: str) -> list[int]:
    h = abs(hash(str(value)))
    return [h % 200 + 40, (h // 7) % 200 + 40, (h // 13) % 200 + 40]


def _rgb_to_hex(rgb: list[int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)


# ---------------------------------------------------------------------------
# Section A — Morning Brief (typewriter JS effect)
# ---------------------------------------------------------------------------

def _estimate_brief_height(paragraph: str, bullets: list) -> int:
    """Estimate iframe height from content so nothing gets clipped."""
    h = 110  # header + body vertical padding
    para_lines = max(1, (len(paragraph) + 54) // 55)
    h += para_lines * 27
    if bullets:
        h += 22
        for b in bullets:
            b_lines = max(1, (len(b) + 64) // 65)
            h += 18 + b_lines * 24
    return max(320, min(h + 60, 720))


def render_brief(brief_output: dict) -> None:
    """Render the briefing as a Claude-style stream: thinking dots → typewriter → bullets."""
    import json as _json

    paragraph = brief_output.get("paragraph", "") or ""
    bullets   = brief_output.get("bullets", []) or []

    # Raw paragraph drives the typing animation; highlighted HTML is swapped in at end.
    plain_para_js = _json.dumps(paragraph)
    html_para_js  = _json.dumps(_highlight_ids(paragraph))

    bullets_payload = []
    for raw in bullets:
        clean = raw.lstrip("▸•- ").strip()
        bullets_payload.append({"text": clean, "html": _highlight_ids(clean)})
    bullets_js = _json.dumps(bullets_payload)

    n_bullets = len(bullets)
    height    = _estimate_brief_height(paragraph, bullets)

    component_html = f"""
<style>
* {{ box-sizing:border-box; }}
body {{ margin:0; padding:0; font-family:-apple-system,BlinkMacSystemFont,"Inter","Segoe UI",sans-serif; }}

.brief-v2 {{
  background:linear-gradient(135deg,#f0fdfa 0%,#ecfeff 55%,#f0f9ff 100%);
  border:1.5px solid #99f6e4;border-radius:18px;overflow:hidden;
  box-shadow:0 6px 22px rgba(15,118,110,0.1);
  animation:brief-enter 0.5s cubic-bezier(0.34,1.56,0.64,1) both;
}}
@keyframes brief-enter {{ from{{opacity:0;transform:translateY(12px);}} to{{opacity:1;transform:translateY(0);}} }}

.brief-v2-head {{
  display:flex;align-items:center;gap:12px;padding:14px 20px;
  background:linear-gradient(90deg,rgba(15,118,110,0.08),rgba(8,145,178,0.04));
  border-bottom:1px dashed rgba(15,118,110,0.2);
}}
.brief-v2-avatar {{
  width:38px;height:38px;border-radius:50%;
  background:linear-gradient(135deg,#0f766e,#0891b2);
  color:white;font-size:1.1rem;
  display:flex;align-items:center;justify-content:center;flex-shrink:0;
  box-shadow:0 3px 10px rgba(15,118,110,0.35);
  animation:avatar-float 3.5s ease-in-out infinite;
}}
@keyframes avatar-float {{ 0%,100%{{transform:translateY(0);}} 50%{{transform:translateY(-2px);}} }}
.brief-v2-head-text {{ flex:1; }}
.brief-v2-speaker {{
  font-size:0.72rem;font-weight:800;letter-spacing:0.14em;color:#0f766e;line-height:1.2;
}}
.brief-v2-meta {{
  font-size:0.78rem;color:#64748b;margin-top:2px;font-weight:500;
  transition:color 0.3s;
}}
.brief-v2-livedot {{
  width:10px;height:10px;border-radius:50%;background:#10b981;flex-shrink:0;
  animation:live-pulse 1.8s ease-in-out infinite;
}}
@keyframes live-pulse {{
  0%,100%{{box-shadow:0 0 0 0 rgba(16,185,129,0.5);}}
  50% {{box-shadow:0 0 0 7px rgba(16,185,129,0);}}
}}

.brief-v2-body {{ padding:18px 22px 20px; }}

/* Thinking dots phase */
.brief-thinking {{
  display:flex;align-items:center;gap:12px;padding:14px 6px;
  animation:fade-in 0.3s ease-out;
}}
@keyframes fade-in {{ from{{opacity:0;}} to{{opacity:1;}} }}
.thinking-dots {{ display:flex;gap:5px;align-items:center; }}
.thinking-dot {{
  width:9px;height:9px;border-radius:50%;
  background:linear-gradient(135deg,#0f766e,#0891b2);
  animation:dot-bounce 1.2s ease-in-out infinite;
  box-shadow:0 0 8px rgba(15,118,110,0.3);
}}
.thinking-dot:nth-child(1) {{ animation-delay:0s; }}
.thinking-dot:nth-child(2) {{ animation-delay:0.15s; }}
.thinking-dot:nth-child(3) {{ animation-delay:0.3s; }}
@keyframes dot-bounce {{
  0%,60%,100% {{ transform:translateY(0) scale(0.85);opacity:0.5; }}
  30% {{ transform:translateY(-8px) scale(1);opacity:1; }}
}}
.thinking-text {{ color:#64748b;font-size:0.9rem;font-weight:500;font-style:italic; }}

/* Typing phase */
.brief-para {{
  font-size:1rem;line-height:1.68;color:#0f172a;margin:0;
  min-height:1.68rem;
}}
.cursor {{
  display:inline-block;width:3px;height:1.15em;background:#0f766e;
  margin-left:2px;vertical-align:text-bottom;
  animation:blink 0.85s step-end infinite;
  border-radius:1px;
}}
@keyframes blink {{ 0%,100%{{opacity:1;}} 50%{{opacity:0;}} }}

.brief-id {{
  background:#0f172a;color:#67e8f9;
  padding:1px 7px;border-radius:5px;
  font-family:"SF Mono","Monaco","Consolas",monospace;
  font-size:0.85em;font-weight:700;letter-spacing:-0.01em;white-space:nowrap;
}}

/* Bullets phase */
.brief-bullets {{
  list-style:none;padding:14px 0 0 0;margin:14px 0 0 0;
  border-top:1px dashed rgba(15,118,110,0.25);
}}
.brief-bullet {{
  display:flex;align-items:flex-start;gap:10px;
  padding:9px 11px;margin:0 0 6px 0;
  font-size:0.93rem;line-height:1.55;color:#1e293b;
  background:rgba(255,255,255,0.55);border-radius:9px;
  opacity:0;transform:translateX(-12px);
  transition:background 0.2s,transform 0.2s;
}}
.brief-bullet.visible {{
  animation:bullet-in 0.45s cubic-bezier(0.34,1.56,0.64,1) forwards;
}}
@keyframes bullet-in {{
  0% {{ opacity:0;transform:translateX(-12px); }}
  100% {{ opacity:1;transform:translateX(0); }}
}}
.brief-bullet:hover {{ background:rgba(255,255,255,0.95);transform:translateX(3px)!important; }}
.brief-bullet-tick {{
  color:#0891b2;font-weight:900;font-size:1.15rem;line-height:1.3;flex-shrink:0;
}}
.brief-bullet-text {{ flex:1; }}
</style>

<div class="brief-v2">
  <div class="brief-v2-head">
    <div class="brief-v2-avatar">🛡️</div>
    <div class="brief-v2-head-text">
      <div class="brief-v2-speaker">ARIA REPORTS</div>
      <div class="brief-v2-meta" id="meta-text">composing briefing…</div>
    </div>
    <div class="brief-v2-livedot" title="Live feed"></div>
  </div>
  <div class="brief-v2-body">
    <div id="thinking" class="brief-thinking">
      <span class="thinking-dots">
        <span class="thinking-dot"></span>
        <span class="thinking-dot"></span>
        <span class="thinking-dot"></span>
      </span>
      <span class="thinking-text">ARIA is analyzing today's routes…</span>
    </div>
    <p id="paragraph" class="brief-para" style="display:none;"></p>
    <ul id="bullets" class="brief-bullets" style="display:none;"></ul>
  </div>
</div>

<script>
(function() {{
  const plainText = {plain_para_js};
  const htmlText  = {html_para_js};
  const bullets   = {bullets_js};
  const nBullets  = {n_bullets};

  const thinkingEl  = document.getElementById('thinking');
  const paragraphEl = document.getElementById('paragraph');
  const bulletsEl   = document.getElementById('bullets');
  const metaEl      = document.getElementById('meta-text');

  // Phase 1 — thinking (900ms)
  setTimeout(() => {{
    thinkingEl.style.transition = 'opacity 0.25s';
    thinkingEl.style.opacity = '0';
    setTimeout(() => {{
      thinkingEl.style.display = 'none';
      paragraphEl.style.display = 'block';
      metaEl.textContent = 'streaming…';
      startTyping();
    }}, 250);
  }}, 900);

  // Phase 2 — typewriter streams the paragraph
  function startTyping() {{
    let i = 0;
    const speed = 11;  // ms per character
    const cursorHTML = '<span class="cursor"></span>';
    function step() {{
      if (i <= plainText.length) {{
        paragraphEl.innerHTML = escapeHtml(plainText.substring(0, i)) + cursorHTML;
        i++;
        setTimeout(step, speed);
      }} else {{
        // Swap plain → highlighted HTML (reveals ID pills)
        paragraphEl.innerHTML = htmlText;
        setTimeout(revealBullets, 280);
      }}
    }}
    step();
  }}

  // Phase 3 — bullets fade in with stagger
  function revealBullets() {{
    if (nBullets === 0) {{
      metaEl.textContent = 'no actions needed';
      return;
    }}
    metaEl.textContent = nBullets + ' action' + (nBullets === 1 ? '' : 's') + ' for today';
    bulletsEl.style.display = 'block';
    bullets.forEach((b, idx) => {{
      const li = document.createElement('li');
      li.className = 'brief-bullet';
      li.innerHTML = '<span class="brief-bullet-tick">▸</span>'
                   + '<span class="brief-bullet-text">' + b.html + '</span>';
      bulletsEl.appendChild(li);
      setTimeout(() => li.classList.add('visible'), 120 + idx * 140);
    }});
  }}

  function escapeHtml(s) {{
    return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }}
}})();
</script>
"""
    _html(component_html, height=height)


# ---------------------------------------------------------------------------
# Section B — Anomalies (animated cards + fix engine)
# ---------------------------------------------------------------------------

def render_anomalies(detector_output: pd.DataFrame, tables: dict) -> None:
    from src.safety.fix_engine import propose_fixes

    if detector_output is None or detector_output.empty:
        st.markdown("""
<div class="clean-day-banner">
  <div style="font-size:2.8rem;margin-bottom:8px;">🎉</div>
  <div style="color:#14532d;font-size:1.15rem;font-weight:800;margin-bottom:4px;">Clean run — no anomalies today!</div>
  <div style="color:#166534;font-size:0.9rem;">All routes, vehicles, and client assignments pass every safety check.</div>
</div>""", unsafe_allow_html=True)
        st.balloons()
        return

    # Applied-fixes badge + reset
    n_applied = len(st.session_state.get("applied_fixes", []))
    col_a, col_b = st.columns([5, 1])
    with col_a:
        if n_applied:
            st.markdown(
                f'<span class="fix-badge" style="background:#d1fae5; color:#065f46; '
                f'padding:5px 12px; border-radius:14px; font-size:0.9rem; font-weight:600;">'
                f'✅ {n_applied} fix{"es" if n_applied > 1 else ""} applied</span>',
                unsafe_allow_html=True,
            )
    with col_b:
        if n_applied and st.button("Reset", key="reset_fixes"):
            st.session_state["applied_fixes"] = []
            st.rerun()

    # Severity summary bar
    sev_counts = (
        detector_output["severity"].astype(str)
        .str.split(".").str[-1].str.lower()
        .value_counts()
    )
    chips_html = " ".join(
        f'<span style="background:{bg}; color:{fg}; padding:3px 10px; '
        f'border-radius:12px; font-size:0.82rem; font-weight:700;">'
        f'{icon} {sev_counts.get(sev,0)} {sev}</span>'
        for sev, icon, bg, fg in [
            ("critical", "🚨", "#fee2e2", "#7f1d1d"),
            ("high",     "⚠️", "#ffedd5", "#7c2d12"),
            ("medium",   "📋", "#fef9c3", "#713f12"),
            ("low",      "ℹ️",  "#f1f5f9", "#334155"),
        ]
        if sev_counts.get(sev, 0) > 0
    )
    if chips_html:
        st.markdown(f'<div style="margin-bottom:14px; display:flex; gap:8px; flex-wrap:wrap;">{chips_html}</div>',
                    unsafe_allow_html=True)

    def _row_html(row: pd.Series, delay_ms: int = 0) -> str:
        raw_sev   = str(row.get("severity", "info"))
        sev       = raw_sev.split(".")[-1].lower()
        icon      = _SEV_ICON.get(sev, "•")
        rule_pretty = str(row.get("rule", "")).replace("_", " ").title()
        explanation = str(row.get("explanation", ""))
        fix_hint    = str(row.get("suggested_fix", ""))
        delay_style = f"animation-delay:{delay_ms}ms;" if delay_ms else ""
        return (
            f'<div class="violation-{sev}" style="{delay_style}">'
            f'<b>{icon} {rule_pretty}</b><br/>'
            f'<span style="color:#475569;font-size:0.9rem;">{explanation}</span><br/>'
            f'<span style="color:#64748b;font-size:0.85rem;"><i>→ {fix_hint}</i></span>'
            f'</div>'
        )

    visible  = detector_output.iloc[:_VISIBLE_CAP]
    overflow = detector_output.iloc[_VISIBLE_CAP:]

    for i, (_, row) in enumerate(visible.iterrows()):
        st.markdown(_row_html(row, delay_ms=i * 60), unsafe_allow_html=True)

        proposals = propose_fixes(row, tables)
        if not proposals:
            st.caption("No automated fix available for this rule.")
        else:
            st.markdown(f'<span style="color:#0f766e; font-size:0.9rem;">💡 {proposals[0].reasoning}</span>',
                        unsafe_allow_html=True)
            c1, c2 = st.columns([2, 3])
            with c1:
                if st.button("✅ Apply fix", key=f"apply_{i}", type="primary"):
                    st.session_state["applied_fixes"].append(proposals[0])
                    st.toast("✅ Fix applied — plan refreshed", icon="🎉")
                    st.rerun()
            if len(proposals) > 1:
                with st.expander(f"▸ {len(proposals) - 1} alternate fix(es)"):
                    for alt_i, alt in enumerate(proposals[1:], start=1):
                        st.markdown(f'<span style="color:#475569; font-size:0.88rem;">{alt.reasoning}</span>',
                                    unsafe_allow_html=True)
                        if st.button("✅ Apply", key=f"apply_{i}_alt_{alt_i}", type="primary"):
                            st.session_state["applied_fixes"].append(alt)
                            st.toast("✅ Fix applied — plan refreshed", icon="🎉")
                            st.rerun()

    if not overflow.empty:
        with st.expander(f"Show {len(overflow)} more anomalies"):
            for _, row in overflow.iterrows():
                st.markdown(_row_html(row), unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Section C — Map + animated metrics
# ---------------------------------------------------------------------------

_STATUS_STYLE = {
    "completed": {"color": "#10b981", "symbol": "✓", "label": "Delivered"},
    "skipped":   {"color": "#dc2626", "symbol": "✗", "label": "Skipped"},
    "no_answer": {"color": "#f59e0b", "symbol": "?", "label": "No answer"},
    "cancelled": {"color": "#64748b", "symbol": "—", "label": "Cancelled"},
    "rerouted":  {"color": "#3b82f6", "symbol": "→", "label": "Rerouted"},
}


def _status_marker(lat: float, lng: float, status: str, popup_html: str, tooltip: str, faded: bool = False):
    cfg = _STATUS_STYLE.get(status, {"color": "#64748b", "symbol": "•", "label": status})
    opacity = 0.45 if faded else 1.0
    size = 26 if not faded else 20
    font_size = 13 if not faded else 10
    return folium.Marker(
        location=[lat, lng],
        popup=folium.Popup(popup_html, max_width=240),
        tooltip=tooltip,
        icon=folium.DivIcon(
            html=f'<div style="background:{cfg["color"]};color:white;border-radius:50%;'
                 f'width:{size}px;height:{size}px;display:flex;align-items:center;'
                 f'justify-content:center;font-size:{font_size}px;font-weight:800;'
                 f'border:2px solid white;opacity:{opacity};'
                 f'box-shadow:0 2px 6px rgba(0,0,0,0.25);">{cfg["symbol"]}</div>',
            icon_size=(size, size),
            icon_anchor=(size // 2, size // 2),
        ),
    )


def render_map(vrp_output: dict, tables: dict, service_date=None) -> None:
    routes        = vrp_output.get("routes", [])
    delta_pct     = vrp_output.get("delta_pct", 0.0) or 0.0
    on_time       = vrp_output.get("projected_on_time_rate", 0.0) or 0.0
    dropped       = vrp_output.get("dropped_requests", []) or []
    total_min     = int(vrp_output.get("total_drive_minutes", 0) or 0)
    baseline_min  = int(vrp_output.get("baseline_drive_minutes", 0) or 0)

    req_df    = tables["requests"]
    client_df = tables["clients"]
    stops_df  = tables["stops"]
    routes_df = tables["routes"]
    depot_df  = tables["depots"].dropna(subset=["lat", "lng"])

    req_indexed    = req_df.set_index("request_id")[["client_id"]] if "client_id" in req_df.columns else pd.DataFrame()
    client_indexed = client_df.set_index("client_id")[["lat", "lng", "first_name", "last_name"]] \
        if "lat" in client_df.columns else pd.DataFrame()

    # ── Actuals: filter stops to this service_date via routes ──────────────
    day_stops = pd.DataFrame()
    if service_date is not None:
        date_str = str(service_date)
        day_route_ids = routes_df[routes_df["service_date"] == date_str]["route_id"].tolist()
        day_stops = stops_df[stops_df["route_id"].isin(day_route_ids)].copy()

    # ── Delivery summary chips ─────────────────────────────────────────────
    status_counts = day_stops["status"].value_counts().to_dict() if not day_stops.empty else {}
    total_stops = int(sum(status_counts.values()))
    completed_n = int(status_counts.get("completed", 0))
    missed_n    = total_stops - completed_n
    success_rate = (completed_n / total_stops * 100) if total_stops else 0.0

    # ── HERO: Before vs After comparison card ──────────────────────────────
    n_served_aria = sum(len(r.get("stops", [])) for r in routes)
    n_flagged     = len(dropped)
    delta_disp    = int(delta_pct * 100)
    delta_color   = "#10b981" if delta_disp >= 0 else "#dc2626"
    delta_sign    = "▼" if delta_disp >= 0 else "▲"

    st.markdown(f"""
<div class="highlight-panel">
  <div class="hero-caption">ARIA's Safe Plan vs Baseline Schedule</div>
  <div class="compare-grid">
    <div class="compare-col baseline-col">
      <div class="compare-label">BASELINE SCHEDULE</div>
      <div class="compare-value baseline-val">{baseline_min:,}<span class="compare-unit">min</span></div>
      <div class="compare-sub">{missed_n} missed · {completed_n} delivered</div>
    </div>
    <div class="compare-arrow">
      <div class="arrow-badge" style="background:{delta_color};">
        {delta_sign} {abs(delta_disp)}%
      </div>
    </div>
    <div class="compare-col aria-col">
      <div class="compare-label">ARIA OPTIMIZED</div>
      <div class="compare-value aria-val">{total_min:,}<span class="compare-unit">min</span></div>
      <div class="compare-sub">0 violations · safe by construction</div>
    </div>
  </div>

  <div class="hero-stats-row">
    <div class="hero-stat">
      <div class="hero-stat-icon">🎯</div>
      <div class="hero-stat-val">{int(on_time * 100)}%</div>
      <div class="hero-stat-lbl">Projected on-time</div>
    </div>
    <div class="hero-stat">
      <div class="hero-stat-icon">🧭</div>
      <div class="hero-stat-val">{len(routes)}</div>
      <div class="hero-stat-lbl">Active routes</div>
    </div>
    <div class="hero-stat">
      <div class="hero-stat-icon">📦</div>
      <div class="hero-stat-val">{n_served_aria}</div>
      <div class="hero-stat-lbl">Stops served</div>
    </div>
    <div class="hero-stat {'flagged-stat' if n_flagged else ''}">
      <div class="hero-stat-icon">⚠️</div>
      <div class="hero-stat-val">{n_flagged}</div>
      <div class="hero-stat-lbl">Flagged for review</div>
    </div>
  </div>
</div>""", unsafe_allow_html=True)

    if total_stops:
        chips = []
        for st_key in ("completed", "skipped", "no_answer", "cancelled", "rerouted"):
            n = status_counts.get(st_key, 0)
            if n == 0:
                continue
            cfg = _STATUS_STYLE[st_key]
            chips.append(
                f'<span style="background:{cfg["color"]}22;color:{cfg["color"]};'
                f'border:1.5px solid {cfg["color"]};padding:4px 11px;border-radius:13px;'
                f'font-size:0.84rem;font-weight:700;">'
                f'{cfg["symbol"]} {n} {cfg["label"]}</span>'
            )
        st.markdown(
            f'<div style="margin-bottom:10px;display:flex;gap:8px;flex-wrap:wrap;align-items:center;">'
            f'<span style="font-weight:800;color:#0f172a;font-size:0.95rem;">'
            f'{completed_n}/{total_stops} delivered · {success_rate:.0f}% success</span>'
            f'{"".join(chips)}'
            f'</div>',
            unsafe_allow_html=True,
        )

    # ── View toggle — default to "Optimized (ARIA)" so the safe plan leads ──
    view = st.radio(
        "Map view",
        ["🎯 Optimized (ARIA)", "📍 Actuals (today)", "🔀 Both"],
        horizontal=True,
        label_visibility="collapsed",
        key="map_view_mode",
    )

    # ── Build optimized route coords ──────────────────────────────────────
    route_coords: list[dict] = []
    all_lats: list[float] = []
    all_lngs: list[float] = []

    for route in routes:
        driver_id  = route.get("driver_id", "")
        vehicle_id = route.get("vehicle_id", "")
        color_hex  = _rgb_to_hex(_hash_color(driver_id))
        coords: list[tuple[float, float, str]] = []

        for req_id in route.get("stops", []):
            try:
                cid = req_indexed.loc[req_id, "client_id"] if req_id in req_indexed.index else None
                if cid is None:
                    continue
                lat = float(client_indexed.loc[cid, "lat"]) if cid in client_indexed.index else None
                lng = float(client_indexed.loc[cid, "lng"]) if cid in client_indexed.index else None
                if lat is None or lng is None:
                    continue
                coords.append((lat, lng, req_id))
                all_lats.append(lat)
                all_lngs.append(lng)
            except (KeyError, TypeError, ValueError):
                continue

        if coords:
            route_coords.append({
                "driver_id": driver_id, "vehicle_id": vehicle_id,
                "color": color_hex, "coords": coords,
            })

    # Gather actual stop lat/lngs too (for map centering + rendering)
    actual_points: list[dict] = []
    if not day_stops.empty and not client_indexed.empty:
        merged = day_stops.merge(client_indexed, left_on="client_id", right_index=True, how="left")
        for _, s in merged.iterrows():
            if pd.isna(s.get("lat")) or pd.isna(s.get("lng")):
                continue
            actual_points.append({
                "lat": float(s["lat"]), "lng": float(s["lng"]),
                "status": str(s.get("status", "")),
                "route_stop_id": s.get("route_stop_id", ""),
                "client_id": s.get("client_id", ""),
                "first_name": s.get("first_name", ""),
                "last_name": s.get("last_name", ""),
                "failure_reason": s.get("failure_reason", ""),
            })
            all_lats.append(float(s["lat"]))
            all_lngs.append(float(s["lng"]))

    # Map centre
    if all_lats:
        center_lat = sum(all_lats) / len(all_lats)
        center_lng = sum(all_lngs) / len(all_lngs)
    elif not depot_df.empty:
        center_lat = float(depot_df["lat"].median())
        center_lng = float(depot_df["lng"].median())
    else:
        center_lat, center_lng = 48.43, -123.37

    m = folium.Map(location=[center_lat, center_lng], zoom_start=11, tiles="CartoDB positron")

    # Depot markers — pulsing ring + dark pin on top
    for _, dep in depot_df.iterrows():
        lat, lng = float(dep["lat"]), float(dep["lng"])
        # Pulsing halo (animated via CSS)
        folium.Marker(
            location=[lat, lng],
            icon=folium.DivIcon(
                html='<div style="width:46px;height:46px;border-radius:50%;'
                     'background:rgba(15,23,42,0.18);animation:depot-pulse 1.8s ease-in-out infinite;"></div>'
                     '<style>@keyframes depot-pulse{0%{transform:scale(0.6);opacity:0.8}'
                     '100%{transform:scale(1.6);opacity:0}}</style>',
                icon_size=(46, 46), icon_anchor=(23, 23),
            ),
        ).add_to(m)
        # Dark depot pin
        folium.Marker(
            location=[lat, lng],
            popup=folium.Popup(f"<b>🏭 Depot {dep.get('depot_id','')}</b><br/>{dep.get('name','')}", max_width=220),
            tooltip=f"🏭 {dep.get('depot_id','')}",
            icon=folium.DivIcon(
                html='<div style="background:#0f172a;color:white;border-radius:6px;'
                     'width:30px;height:30px;display:flex;align-items:center;'
                     'justify-content:center;font-size:16px;font-weight:800;'
                     'border:2.5px solid white;box-shadow:0 3px 8px rgba(0,0,0,0.4);">🏭</div>',
                icon_size=(30, 30), icon_anchor=(15, 15),
            ),
        ).add_to(m)

    show_actuals = view.startswith("📍") or view.startswith("🔀")
    show_optimized = view.startswith("🎯") or view.startswith("🔀")
    fade_actuals = view.startswith("🔀")

    # Actuals layer
    if show_actuals:
        for p in actual_points:
            fn = p["first_name"] or ""
            ln = p["last_name"] or ""
            fr = p["failure_reason"] or ""
            cfg = _STATUS_STYLE.get(p["status"], {"label": p["status"]})
            popup_html = (
                f'<b>{p["route_stop_id"]}</b><br/>'
                f'{fn} {ln} ({p["client_id"]})<br/>'
                f'Status: <b style="color:{_STATUS_STYLE.get(p["status"],{}).get("color","#000")};">{cfg["label"]}</b>'
                + (f'<br/>Reason: {fr}' if fr and p["status"] != "completed" else "")
            )
            _status_marker(
                p["lat"], p["lng"], p["status"],
                popup_html=popup_html,
                tooltip=f'{cfg["label"]} · {p["client_id"]}',
                faded=fade_actuals,
            ).add_to(m)

    # Optimized layer — AntPath gives a continuous "flowing" animation along the route
    if show_optimized:
        for r in route_coords:
            if len(r["coords"]) >= 2:
                AntPath(
                    locations=[(lat, lng) for lat, lng, _ in r["coords"]],
                    color=r["color"],
                    weight=4,
                    opacity=0.85,
                    delay=800,
                    dash_array=[10, 20],
                    pulse_color="#ffffff",
                    tooltip=f"ARIA route — {r['driver_id']} / {r['vehicle_id']}",
                ).add_to(m)
            for idx, (lat, lng, req_id) in enumerate(r["coords"]):
                folium.Marker(
                    location=[lat, lng],
                    popup=folium.Popup(
                        f'<b>{req_id}</b><br/>ARIA plan · stop #{idx+1}<br/>'
                        f'Driver: {r["driver_id"]}<br/>Vehicle: {r["vehicle_id"]}',
                        max_width=220,
                    ),
                    tooltip=f'#{idx+1} ARIA · {r["driver_id"]}',
                    icon=folium.DivIcon(
                        html=f'<div style="background:{r["color"]};color:white;border-radius:50%;'
                             f'width:24px;height:24px;display:flex;align-items:center;'
                             f'justify-content:center;font-size:11px;font-weight:800;'
                             f'border:2.5px solid white;box-shadow:0 2px 6px rgba(0,0,0,0.3);">'
                             f'{idx+1}</div>',
                        icon_size=(24, 24), icon_anchor=(12, 12),
                    ),
                ).add_to(m)

    # Dropped/flagged markers (always shown)
    for req_id in dropped:
        try:
            cid = req_indexed.loc[req_id, "client_id"] if req_id in req_indexed.index else None
            if cid is None or cid not in client_indexed.index:
                continue
            lat = float(client_indexed.loc[cid, "lat"])
            lng = float(client_indexed.loc[cid, "lng"])
            folium.Marker(
                location=[lat, lng],
                popup=folium.Popup(f'<b>⚠ Flagged</b><br/>{req_id}<br/>Dropped by ARIA — manual review', max_width=220),
                tooltip=f'⚠ Flagged · {req_id}',
                icon=folium.DivIcon(
                    html='<div style="background:#7f1d1d;color:white;border-radius:4px;'
                         'width:22px;height:22px;display:flex;align-items:center;'
                         'justify-content:center;font-size:12px;font-weight:900;'
                         'border:2px solid #fca5a5;box-shadow:0 2px 6px rgba(127,29,29,0.5);">⚠</div>',
                    icon_size=(22, 22), icon_anchor=(11, 11),
                ),
            ).add_to(m)
        except (KeyError, TypeError, ValueError):
            continue

    # Legend overlay (HTML injected into map root)
    legend_html = """
    <div style="position:fixed;top:10px;right:10px;z-index:9999;
                background:rgba(255,255,255,0.96);padding:10px 12px;
                border-radius:10px;border:1px solid #e2e8f0;
                box-shadow:0 4px 12px rgba(0,0,0,0.1);
                font-family:sans-serif;font-size:11px;line-height:1.7;max-width:170px;">
      <div style="font-weight:800;color:#0f172a;margin-bottom:4px;font-size:12px;">Legend</div>
      <div><span style="display:inline-block;width:12px;height:12px;border-radius:50%;background:#10b981;vertical-align:middle;margin-right:6px;"></span>Delivered</div>
      <div><span style="display:inline-block;width:12px;height:12px;border-radius:50%;background:#dc2626;vertical-align:middle;margin-right:6px;"></span>Skipped</div>
      <div><span style="display:inline-block;width:12px;height:12px;border-radius:50%;background:#f59e0b;vertical-align:middle;margin-right:6px;"></span>No answer</div>
      <div><span style="display:inline-block;width:12px;height:12px;border-radius:50%;background:#64748b;vertical-align:middle;margin-right:6px;"></span>Cancelled</div>
      <div><span style="display:inline-block;width:12px;height:12px;background:#7f1d1d;vertical-align:middle;margin-right:6px;"></span>Flagged ⚠</div>
      <div style="border-top:1px solid #e2e8f0;margin-top:5px;padding-top:5px;">
        <span style="display:inline-block;width:12px;height:12px;background:#0f172a;vertical-align:middle;margin-right:6px;"></span>Depot 🏭
      </div>
    </div>"""
    m.get_root().html.add_child(folium.Element(legend_html))

    st.markdown('<div class="map-frame">', unsafe_allow_html=True)
    st_folium(m, width=None, height=560, returned_objects=[])
    st.markdown('</div>', unsafe_allow_html=True)

    # ── Per-route breakdown cards ──────────────────────────────────────────
    if route_coords:
        cards_html = ['<div class="route-breakdown">']
        for r in route_coords:
            cards_html.append(
                f'<div class="route-card" style="border-left-color:{r["color"]};">'
                f'  <div class="route-card-top">'
                f'    <span class="route-dot" style="background:{r["color"]};"></span>'
                f'    <span class="route-driver">{r["driver_id"]}</span>'
                f'    <span class="route-vehicle">{r["vehicle_id"]}</span>'
                f'  </div>'
                f'  <div class="route-card-stats">'
                f'    <span class="route-stops"><b>{len(r["coords"])}</b> stops</span>'
                f'  </div>'
                f'</div>'
            )
        cards_html.append('</div>')
        st.markdown("".join(cards_html), unsafe_allow_html=True)

