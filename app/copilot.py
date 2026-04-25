"""Safety Copilot — character-driven Streamlit entry point."""

from __future__ import annotations

from pathlib import Path
import hashlib
import json
import sys
import traceback

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import pandas as pd
import streamlit as st
from datetime import date

from shared.src.loaders import load_track2
from src.safety.detectors import run_all
from src.optimizer.constrained_greedy import reoptimize
from src.brief.morning_brief import render_brief as _build_brief
from src.safety.fix_engine import apply_fixes
from src.safety.score import safety_score as _safety_score

import app._sections as sec
import app._character as char
from app._layout import inject_phone_css
from app._calendar import compute_calendar_severity, render_calendar, handle_calendar_click
from app._role import (
    _HIDDEN_PAGES_BY_ROLE,
    _PRIMARY_PAGE_BY_ROLE,
    _ROLE_DISPLAY,
    _inject_role_filter,
    _render_role_chip,
)


def _render_login_gate() -> None:
    """Show the role picker. Sets st.session_state['role'] and reruns on click."""
    st.markdown("""
<div class="login-card">
  <div class="login-shield">🛡️</div>
  <div class="login-title">Safety Copilot</div>
  <div class="login-sub">ARIA — Automated Route Intelligence Assistant</div>
  <div class="login-q">Who's signing in today?</div>
</div>
""", unsafe_allow_html=True)

    c1, c2 = st.columns(2, gap="medium")
    with c1:
        if st.button("🏠  Volunteer Lead", use_container_width=True, key="role_v",
                     help="Mary — Tuesday morning, dispatching today's routes"):
            st.session_state["role"] = "volunteer"; st.rerun()
        if st.button("📊  Coordinator", use_container_width=True, key="role_c",
                     help="Operations manager — weekly KPIs, fleet health, scorecard"):
            st.session_state["role"] = "coordinator"; st.rerun()
    with c2:
        if st.button("🚚  Driver", use_container_width=True, key="role_d",
                     help="Tom in the truck — today's stops, badges, deliveries"):
            st.session_state["role"] = "driver"; st.rerun()
        if st.button("🔐  Auditor", use_container_width=True, key="role_a",
                     help="Inspector view — scorecard + file:line constraint citations"):
            st.session_state["role"] = "auditor"; st.rerun()

    st.divider()
    if st.button("🎭  Demo mode — show every page", use_container_width=True, key="role_demo"):
        st.session_state["role"] = "demo"; st.rerun()


# _inject_role_filter and _render_role_chip live in app/_role.py and are
# imported above so sub-pages can reuse the same logic via enforce_role().


@st.cache_data(show_spinner=False)
def _load(data_dir: str) -> dict:
    return load_track2(data_dir)


def _fixes_fingerprint(fixes: list) -> str:
    """Stable short hash of the applied fixes so cache keys invalidate on any change."""
    if not fixes:
        return "none"
    payload = json.dumps(
        [{"t": f.patch["table"], "w": f.patch["where"], "s": f.patch["set"]} for f in fixes],
        sort_keys=True, default=str,
    )
    return hashlib.md5(payload.encode()).hexdigest()[:12]


@st.cache_data(show_spinner=False)
def _cached_detect(data_dir: str, service_date_iso: str, fixes_key: str) -> pd.DataFrame:
    """Cache key: (data_dir, date, fingerprint of fixes). Re-computes only when those change."""
    tables = apply_fixes(_load(data_dir), st.session_state.get("applied_fixes", []))
    return run_all(tables, date.fromisoformat(service_date_iso))


@st.cache_data(show_spinner=False)
def _cached_optimize(data_dir: str, service_date_iso: str, fixes_key: str) -> dict:
    tables = apply_fixes(_load(data_dir), st.session_state.get("applied_fixes", []))
    return reoptimize(tables, date.fromisoformat(service_date_iso))


def _safe_render(section_name: str, render_fn, *args, **kwargs) -> None:
    """Wrap a section renderer — one bad date doesn't crash the whole page."""
    try:
        render_fn(*args, **kwargs)
    except Exception as exc:
        st.error(f"⚠ {section_name} temporarily unavailable — {type(exc).__name__}")
        with st.expander("Debug details"):
            st.code(traceback.format_exc())


def main() -> None:
    st.set_page_config(
        page_title="Safety Copilot — ARIA",
        layout="centered",
        page_icon="🛡️",
    )
    inject_phone_css()

    # ── Login gate ────────────────────────────────────────────────────────
    # Backdoor: `?role=demo` (or any valid role) sets it without the picker.
    # Useful for screenshot capture, demos, and bookmarkable role-direct links.
    _qp_role = st.query_params.get("role")
    if _qp_role and _qp_role in _ROLE_DISPLAY:
        st.session_state["role"] = _qp_role

    # Until a role is picked, render only the picker card and stop.
    if "role" not in st.session_state:
        _render_login_gate()
        st.stop()
    role = st.session_state["role"]
    _inject_role_filter(role)

    # Drivers and Auditors don't use the operations landing — send them
    # straight to their primary page so they don't see the ops dashboard.
    # Volunteer/Coordinator/Demo stay here on copilot.py.
    _primary = _PRIMARY_PAGE_BY_ROLE.get(role)
    if _primary and not _primary.endswith("copilot.py"):
        st.switch_page(_primary)

    # Handle ?cal_date=... from calendar cell click BEFORE date_input is created.
    handle_calendar_click()

    # ── EARLY SPLASH ──────────────────────────────────────────────────────
    # Paints before heavy compute (calendar scan can take 5–10s cold) so the
    # page never looks blank. Cleared once the first frame of real content
    # is ready to render below.
    _splash = st.empty()
    _splash.markdown("""
<div class="app-splash">
  <div class="splash-shield">🛡️</div>
  <div class="splash-title">Safety Copilot</div>
  <div class="splash-sub">ARIA is scanning today's routes…</div>
  <div class="splash-bar"></div>
  <div class="splash-skel-wrap">
    <div class="splash-skel-row" style="width:72%;"></div>
    <div class="splash-skel-row" style="width:90%;"></div>
    <div class="splash-skel-row" style="width:55%;"></div>
  </div>
</div>
""", unsafe_allow_html=True)

    # ── Sidebar role chip + switch button (top of sidebar) ───────────────
    _render_role_chip(role)

    # ── Sidebar — ARIA brand header (populated once state is known further down;
    #    rendered here first as a placeholder so it sits at the very top). ───
    _aria_header_slot = st.sidebar.empty()

    # Data directory is dev-facing — tucked into an expander so the volunteer
    # sidebar isn't cluttered. Default value is the canonical track-2 raw path.
    with st.sidebar.expander("⚙ Advanced settings", expanded=False):
        data_dir = st.text_input(
            "Data directory",
            value="tracks/food-security-delivery/data/raw",
            label_visibility="collapsed",
        )

    try:
        tables_raw = _load(data_dir)
    except FileNotFoundError as exc:
        st.error(str(exc))
        st.stop()

    st.session_state.setdefault("applied_fixes", [])
    tables = apply_fixes(tables_raw, st.session_state["applied_fixes"])

    all_dates = sorted(
        pd.to_datetime(tables["routes"]["service_date"]).dt.date.dropna().unique()
    )
    if not all_dates:
        st.warning("No service dates found in the routes table.")
        st.stop()

    # Default date only if not already set (by calendar click or prior interaction)
    if "service_date_picker" not in st.session_state:
        st.session_state["service_date_picker"] = all_dates[len(all_dates) // 2]

    service_date = st.sidebar.date_input(
        "Service date",
        min_value=all_dates[0],
        max_value=all_dates[-1],
        key="service_date_picker",
    )

    # Compute calendar severity (cached for the session) and render in sidebar.
    sev_by_date = compute_calendar_severity(data_dir)
    with st.sidebar:
        render_calendar(all_dates, service_date, sev_by_date)

    # ── Compute (cached on date + fixes fingerprint) ──────────────────────
    fixes_key       = _fixes_fingerprint(st.session_state.get("applied_fixes", []))
    date_iso        = service_date.isoformat()
    detector_output = _cached_detect(data_dir, date_iso, fixes_key)
    vrp_output      = _cached_optimize(data_dir, date_iso, fixes_key)
    n_fixes         = len(st.session_state.get("applied_fixes", []))
    brief_output    = _build_brief(service_date, detector_output, vrp_output, tables, fixes_applied=n_fixes)

    state    = char.get_state(detector_output)
    n_routes = len(vrp_output.get("routes", []))
    n_dropped = len(vrp_output.get("dropped_requests", []))

    # ── Populate ARIA sidebar header with state-aware colour + status chip ──
    _STATE_COPY = {
        "happy":    ("ALL CLEAR",        "#10b981"),
        "ok":       ("MONITORING",       "#0f766e"),
        "warning":  ("HEADS UP",         "#d97706"),
        "critical": ("CRITICAL ALERTS",  "#dc2626"),
    }
    state_label, state_color = _STATE_COPY.get(state, ("MONITORING", "#0f766e"))
    _aria_header_slot.markdown(f"""
<div class="aria-sb-header">
  <div class="aria-sb-shield-wrap">
    <div class="aria-sb-shield-ring" style="background:{state_color};"></div>
    <div class="aria-sb-shield">🛡️</div>
  </div>
  <div class="aria-sb-text">
    <div class="aria-sb-name">ARIA</div>
    <div class="aria-sb-sub">Safety Copilot</div>
  </div>
</div>
<div class="aria-sb-status" style="--s:{state_color};">
  <span class="aria-sb-dot"></span>
  <span class="aria-sb-label">{state_label}</span>
  <span class="aria-sb-badge">{len(detector_output)}</span>
</div>
""", unsafe_allow_html=True)

    # All heavy compute done — clear the splash so the real content takes over.
    _splash.empty()

    # ═════════════════════════════════════════════════════════════════════
    # 1. HERO — title first, then compact character + status chips (single source of truth)
    # ═════════════════════════════════════════════════════════════════════
    state_label, state_color = _STATE_COPY.get(state, ("MONITORING", "#0f766e"))
    hero_col_aria, hero_col_title = st.columns([1, 4])
    with hero_col_aria:
        char.render(state, n_violations=len(detector_output), n_routes=n_routes, compact=True)
    with hero_col_title:
        # Build chips — only show non-zero/meaningful ones to reduce noise
        _chips = [
            f'<span class="hero-v2-state" style="--s:{state_color};">'
            f'<span class="hero-v2-state-dot"></span>{state_label}</span>',
            f'<span class="hero-v2-chip"><b>{len(detector_output)}</b> anomalies</span>',
            f'<span class="hero-v2-chip"><b>{n_routes}</b> routes</span>',
        ]
        if n_dropped:
            _chips.append(f'<span class="hero-v2-chip chip-warn"><b>{n_dropped}</b> flagged</span>')
        if n_fixes:
            _chips.append(f'<span class="hero-v2-chip chip-ok"><b>{n_fixes}</b> fixes applied</span>')

        st.markdown(
            f'<div class="hero-v2">'
            f'  <h1 class="hero-v2-title">🛡️ Safety Copilot</h1>'
            f'  <div class="hero-v2-sub">'
            f'    <b>ARIA</b> — Automated Route Intelligence Assistant'
            f'    <span class="hero-v2-sub-sep">·</span>'
            f'    {service_date.strftime("%A, %B %d, %Y")}'
            f'  </div>'
            f'  <div class="hero-v2-chips">{"".join(_chips)}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # Sidebar summary (kept brief since stats now live in hero)
    # Note: removed the duplicate "Quick links" section here — Streamlit's
    # auto-nav at the top of the sidebar already lists the same pages, with
    # the same emoji + label, filtered by role via _inject_role_filter().
    _allowed = {p for p in ["Driver", "Coordinator", "Scorecard", "Safety_Audit", "Surplus"]
                if p not in _HIDDEN_PAGES_BY_ROLE.get(role, [])}

    # ── Risk Snapshot — reframed from "Safety Score" so operators don't panic ──
    # Old version showed "0/100" when raw == current (no fixes applied yet). That
    # math is "% cleared", but the label said "Safety Score" — operators read big
    # red 0 as "schedule is unsafe". Reframed: show *how much risk has been
    # cleared* (intuitive — starts at 0%, climbs as you act).
    raw_violations = _cached_detect(data_dir, date_iso, "none")  # bypass-fixes view
    _score_dict = _safety_score(raw_violations, detector_output)
    raw_pts, cur_pts, cleared = _score_dict["raw_risk"], _score_dict["current_risk"], _score_dict["cleared"]

    if raw_pts == 0:
        _hl, _sub, _bar_pct, _color = (
            "✅ Schedule clean",
            "No safety risks in today's plan.",
            100, "#10b981",
        )
    elif cur_pts == 0:
        _hl, _sub, _bar_pct, _color = (
            f"✅ All {raw_pts} risk pts cleared",
            f"{n_fixes} fix(es) applied — schedule is safe to dispatch.",
            100, "#10b981",
        )
    elif cleared > 0:
        _bar_pct = int(round(cleared / raw_pts * 100))
        _hl, _sub, _color = (
            f"🔧 {cleared} of {raw_pts} risk pts cleared",
            f"{cur_pts} pt(s) remaining · {n_fixes} fix(es) applied · keep going.",
            "#d97706",
        )
    else:
        _hl, _sub, _bar_pct, _color = (
            f"⚠️ {raw_pts} risk pts in today's schedule",
            "Apply fixes below to start clearing them.",
            0, "#dc2626",
        )

    st.markdown(f"""
<div class="risk-snap">
  <div class="risk-snap-row">
    <div>
      <div class="risk-snap-label">RISK SNAPSHOT</div>
      <div class="risk-snap-headline" style="color:{_color};">{_hl}</div>
      <div class="risk-snap-sub">{_sub}</div>
    </div>
    <div class="risk-snap-pct" style="color:{_color};">{_bar_pct}<span>%</span></div>
  </div>
  <div class="risk-snap-bar">
    <div class="risk-snap-fill" style="background:{_color};width:{_bar_pct}%;"></div>
  </div>
  <div class="risk-snap-foot">
    <span class="risk-snap-foot-label">% of raw risk cleared</span>
    <span class="risk-snap-foot-stat">raw {raw_pts} → current {cur_pts}</span>
  </div>
</div>
""", unsafe_allow_html=True)

    # ═════════════════════════════════════════════════════════════════════
    # 2. BRIEFING — ARIA's short narrative
    # ═════════════════════════════════════════════════════════════════════
    st.markdown(
        '<div class="section-header"><span class="section-icon">📋</span>Briefing'
        '<span class="section-meta">ARIA\'s morning report</span></div>',
        unsafe_allow_html=True,
    )
    _safe_render("Briefing", sec.render_brief, brief_output)

    # ═════════════════════════════════════════════════════════════════════
    # 3. THE PLAN — page highlight, now ABOVE Attention so judges see it first
    # ═════════════════════════════════════════════════════════════════════
    _plan_tag = "UPDATED" if n_fixes else "ARIA'S ROUTE"
    st.markdown(
        f'<div class="section-header section-header-xl">'
        f'<span class="section-icon">🗺️</span>The Plan'
        f'<span class="section-tag">{_plan_tag}</span>'
        f'</div>'
        f'<div class="section-sub">Safe-by-construction plan — baseline vs ARIA, '
        f'delivery status, and flowing routes on the map.</div>',
        unsafe_allow_html=True,
    )

    # Compact "rebuild" action — only shown when fixes exist (not a constant CTA)
    if n_fixes:
        rb_c1, rb_c2 = st.columns([3, 1])
        with rb_c1:
            st.caption(f"🔧 {n_fixes} fix(es) applied · the plan below reflects them automatically.")
        with rb_c2:
            if st.button("🔄 Rebuild", use_container_width=True,
                         help="Force a re-optimize pass (plan already updates on every fix)"):
                with st.spinner("ARIA is re-optimizing routes…"):
                    st.rerun()

    _safe_render("The Plan", sec.render_map, vrp_output, tables, service_date=service_date)

    # ═════════════════════════════════════════════════════════════════════
    # 4. NEEDS ATTENTION — the action list
    # ═════════════════════════════════════════════════════════════════════
    _attn_meta = (
        f"{len(detector_output)} issue(s) · {n_fixes} fix(es) applied"
        if n_fixes else f"{len(detector_output)} issue(s)"
    )
    st.markdown(
        f'<div class="section-header"><span class="section-icon">⚡</span>Needs Attention'
        f'<span class="section-meta">{_attn_meta}</span></div>',
        unsafe_allow_html=True,
    )
    if n_fixes:
        st.markdown(
            '<div class="attn-nudge">'
            '✅ Fixes applied — the Plan above has already refreshed. '
            '<a href="#the-plan" onclick="window.scrollTo({top:0,behavior:\'smooth\'});return false;">↑ Scroll up to see</a>.'
            '</div>',
            unsafe_allow_html=True,
        )
    _safe_render("Anomalies", sec.render_anomalies, detector_output, tables)

    # ═════════════════════════════════════════════════════════════════════
    # 5. DEEP DIVES — navigation to sub-pages
    # ═════════════════════════════════════════════════════════════════════
    st.markdown(
        '<div class="section-header"><span class="section-icon">🔎</span>Go Deeper</div>',
        unsafe_allow_html=True,
    )
    # Build a role-aware deep-dive grid (hide cards the role can't access)
    nav_items = []
    if "Coordinator"  in _allowed:
        nav_items.append(("nav-card-fleet",  "📊", "Coordinator",  "Weekly KPIs, burnout watchlist, fleet health", "pages/3_📊_Coordinator.py"))
    if "Surplus"      in _allowed:
        nav_items.append(("nav-card-fleet",  "🍱", "Surplus Match", "Match surplus food to eligible neighbours",   "pages/4_🍱_Surplus.py"))
    if "Scorecard"    in _allowed:
        nav_items.append(("nav-card-score",  "📈", "Scorecard",    "Detector F1, optimizer delta, audit",          "pages/2_📈_Scorecard.py"))
    if "Safety_Audit" in _allowed:
        nav_items.append(("nav-card-audit",  "🔐", "Safety Audit", "8 hard constraints with file:line citations",  "pages/3_🔐_Safety_Audit.py"))

    if nav_items:
        cards_html = ['<div class="nav-card-grid">']
        for cls, icon, title, sub, _ in nav_items:
            cards_html.append(
                f'<div class="nav-card {cls}">'
                f'  <div class="nav-card-icon">{icon}</div>'
                f'  <div class="nav-card-title">{title}</div>'
                f'  <div class="nav-card-sub">{sub}</div>'
                f'</div>'
            )
        cards_html.append('</div>')
        st.markdown("".join(cards_html), unsafe_allow_html=True)

        cols = st.columns(len(nav_items))
        for col, (_, _, title, _, path) in zip(cols, nav_items):
            with col:
                st.page_link(path, label=f"Open {title} →", use_container_width=True)

    st.caption("Safety Copilot · Built for BuildersVault 2026 · Track 2 Food Security Delivery")


if __name__ == "__main__":
    main()
