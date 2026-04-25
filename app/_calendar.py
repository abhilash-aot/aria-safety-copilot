"""Severity calendar — per-date worst-severity colour map + clickable grid.

Click handling uses URL query params so clicks work without a custom component.
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from shared.src.loaders import load_track2
from src.safety.detectors import run_all


_SEV_COLOR = {
    "critical": "#dc2626",
    "high":     "#ea580c",
    "medium":   "#d97706",
    "low":      "#64748b",
    "none":     "#10b981",
}
_SEV_LABEL = {
    "critical": "Critical",
    "high":     "High",
    "medium":   "Medium",
    "low":      "Low",
    "none":     "Clean",
}


def _day_severity(dfv) -> str:
    if dfv is None or dfv.empty:
        return "none"
    sevs = dfv["severity"].astype(str).str.split(".").str[-1].str.lower()
    for level in ("critical", "high", "medium", "low"):
        if level in sevs.values:
            return level
    return "none"


@st.cache_data(show_spinner="📅 Scanning severity across all dates…")
def compute_calendar_severity(data_dir: str) -> dict:
    """Return {iso_date_str: {'sev': level, 'count': int}} for every service date.

    Computed on the RAW tables (no session fixes applied). The cache survives for
    the whole session, so the first render pays the cost once.
    """
    tables = load_track2(data_dir)
    all_dates = sorted(
        pd.to_datetime(tables["routes"]["service_date"]).dt.date.dropna().unique()
    )
    out: dict = {}
    for d in all_dates:
        dfv = run_all(tables, d)
        out[str(d)] = {"sev": _day_severity(dfv), "count": int(len(dfv))}
    return out


def _month_grid(all_dates: list) -> list:
    """Build a list of contiguous dates from the Monday ≤ first to the Sunday ≥ last."""
    if not all_dates:
        return []
    first, last = all_dates[0], all_dates[-1]
    start = first - timedelta(days=first.weekday())
    end   = last  + timedelta(days=(6 - last.weekday()))
    cells, cur = [], start
    while cur <= end:
        cells.append(cur)
        cur += timedelta(days=1)
    return cells


def render_calendar(all_dates: list, selected_date: date, sev_by_date: dict) -> None:
    """Render the sidebar severity calendar (7-col grid, clickable cells)."""
    st.markdown("### 📅 Severity calendar")

    all_dates_set = {str(d) for d in all_dates}
    cells         = _month_grid(all_dates)

    # CSS once per render
    st.markdown("""<style>
    .cal-grid{display:grid;grid-template-columns:repeat(7,1fr);gap:3px;}
    .cal-head{text-align:center;font-weight:800;color:#64748b;font-size:0.68rem;padding:4px 0;letter-spacing:0.04em;}
    .cal-cell{
      position:relative;text-align:center;padding:8px 2px;border-radius:7px;
      font-size:0.85rem;font-weight:700;text-decoration:none;display:block;
      transition:transform 0.18s,box-shadow 0.18s;line-height:1.1;
    }
    .cal-cell.off{background:#f1f5f9;color:#cbd5e1;cursor:default;}
    .cal-cell.on {color:white;animation:cell-pop 0.35s cubic-bezier(0.34,1.56,0.64,1) both;}
    .cal-cell.on:hover{transform:scale(1.08);box-shadow:0 4px 12px rgba(15,23,42,0.18);}
    .cal-cell.on.selected{
      box-shadow:0 0 0 2.5px #0f172a,0 4px 12px rgba(15,23,42,0.25);
      transform:scale(1.06);animation:selected-pulse 2s ease-in-out infinite;
    }
    @keyframes cell-pop{0%{opacity:0;transform:scale(0.6);}100%{opacity:1;transform:scale(1);}}
    @keyframes selected-pulse{0%,100%{box-shadow:0 0 0 2.5px #0f172a,0 0 0 0 rgba(15,23,42,0.35);}
                              50%    {box-shadow:0 0 0 2.5px #0f172a,0 0 0 7px rgba(15,23,42,0);}}
    .cal-badge{
      position:absolute;top:-4px;right:-4px;background:white;
      border-radius:50%;min-width:15px;height:15px;padding:0 3px;
      display:flex;align-items:center;justify-content:center;
      font-size:0.58rem;font-weight:800;border:1.5px solid currentColor;
    }
    .cal-legend{display:flex;flex-wrap:wrap;gap:10px;margin-top:10px;}
    .cal-leg-item{display:inline-flex;align-items:center;gap:4px;font-size:0.7rem;color:#475569;}
    .cal-leg-sw{display:inline-block;width:10px;height:10px;border-radius:2px;}
    </style>""", unsafe_allow_html=True)

    # Weekday header
    header = "".join(f'<div class="cal-head">{d}</div>' for d in ["M", "T", "W", "T", "F", "S", "S"])

    # Cells
    cells_html = []
    for d in cells:
        if str(d) not in all_dates_set:
            cells_html.append(f'<div class="cal-cell off">{d.day}</div>')
            continue
        info   = sev_by_date.get(str(d), {"sev": "none", "count": 0})
        sev    = info["sev"]
        count  = info["count"]
        color  = _SEV_COLOR[sev]
        selected = "selected" if d == selected_date else ""
        badge = (
            f'<span class="cal-badge" style="color:{color};">{count}</span>'
            if count else ""
        )
        cells_html.append(
            f'<a class="cal-cell on {selected}" href="?cal_date={d}" target="_self" '
            f'style="background:{color};" '
            f'title="{_SEV_LABEL[sev]} — {count} issue(s) on {d.strftime("%a %b %d")}">'
            f'{d.day}{badge}</a>'
        )

    st.markdown(
        f'<div class="cal-grid">{header}{"".join(cells_html)}</div>',
        unsafe_allow_html=True,
    )

    # Legend
    legend = "".join(
        f'<span class="cal-leg-item">'
        f'<span class="cal-leg-sw" style="background:{_SEV_COLOR[sev]};"></span>'
        f'{_SEV_LABEL[sev]}</span>'
        for sev in ("none", "medium", "high", "critical")
    )
    st.markdown(f'<div class="cal-legend">{legend}</div>', unsafe_allow_html=True)


def handle_calendar_click() -> None:
    """Read `?cal_date=YYYY-MM-DD` from the URL and write it to session state.

    Must be called BEFORE the date_input is created so the initial value
    reflects the clicked cell.
    """
    qp = st.query_params
    if "cal_date" not in qp:
        return
    try:
        chosen = date.fromisoformat(qp["cal_date"])
        st.session_state["service_date_picker"] = chosen
    except (ValueError, TypeError):
        pass
