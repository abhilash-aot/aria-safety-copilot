"""ARIA — animated character for Safety Copilot.

Uses streamlit-lottie when network is available; falls back to the
polished SVG shield so the demo works offline too.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

# Lottie disabled: the URLs in _LOTTIE_URLS below don't resolve reliably and
# each attempt blocks up to 3s. The SVG fallback is the intended look anyway.
# Flip this to True if you want to experiment with live Lottie animations.
_LOTTIE_AVAILABLE = False
try:
    import requests as _requests  # noqa: F401 — kept for future re-enable
    from streamlit_lottie import st_lottie as _st_lottie  # noqa: F401
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Lottie URLs per state (LottieFiles CDN — free, no token required)
# ---------------------------------------------------------------------------
_LOTTIE_URLS: dict[str, str] = {
    "happy":    "https://assets2.lottiefiles.com/packages/lf20_jR229r.json",
    "ok":       "https://assets2.lottiefiles.com/packages/lf20_x62chJ.json",
    "warning":  "https://assets2.lottiefiles.com/packages/lf20_rovkccnm.json",
    "critical": "https://assets2.lottiefiles.com/packages/lf20_lrhq7gvo.json",
    "thinking": "https://assets2.lottiefiles.com/packages/lf20_qp1q7mct.json",
}

@st.cache_data(ttl=3600, show_spinner=False)
def _fetch_lottie(url: str):
    try:
        r = _requests.get(url, timeout=3)
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None

# ---------------------------------------------------------------------------
# SVG fallback config per state
# ---------------------------------------------------------------------------
_STATES: dict[str, dict] = {
    "happy": {
        "color_main": "#10b981", "color_light": "#6ee7b7", "color_dark": "#065f46",
        "glow": "rgba(16,185,129,0.45)", "anim": "aria-float 3.5s ease-in-out infinite",
        "label": "All clear — clean run today!", "label_color": "#065f46",
        "dx": 0, "dy": 0, "pr": 6,
        "mouth": '<path d="M42 82 Q60 96 78 82" stroke="#0f172a" stroke-width="3" fill="none" stroke-linecap="round"/>',
    },
    "ok": {
        "color_main": "#0f766e", "color_light": "#5eead4", "color_dark": "#134e4a",
        "glow": "rgba(15,118,110,0.35)", "anim": "aria-float 4s ease-in-out infinite",
        "label": "Monitoring — minor issues noted", "label_color": "#0f766e",
        "dx": 0, "dy": 0, "pr": 6,
        "mouth": '<line x1="44" y1="86" x2="76" y2="86" stroke="#0f172a" stroke-width="3" stroke-linecap="round"/>',
    },
    "warning": {
        "color_main": "#d97706", "color_light": "#fde68a", "color_dark": "#92400e",
        "glow": "rgba(217,119,6,0.5)", "anim": "aria-pulse-warn 1.3s ease-in-out infinite",
        "label": "Heads up — safety issues detected", "label_color": "#92400e",
        "dx": 0, "dy": 0, "pr": 8,
        "mouth": '<path d="M42 90 Q60 80 78 90" stroke="#0f172a" stroke-width="3" fill="none" stroke-linecap="round"/>',
    },
    "critical": {
        "color_main": "#dc2626", "color_light": "#fca5a5", "color_dark": "#7f1d1d",
        "glow": "rgba(220,38,38,0.6)", "anim": "aria-shake 0.6s ease-in-out infinite",
        "label": "🚨 Critical alerts — act now!", "label_color": "#7f1d1d",
        "dx": 0, "dy": 2, "pr": 8,
        "mouth": '<ellipse cx="60" cy="89" rx="10" ry="7" fill="#0f172a" opacity="0.9"/>',
    },
    "thinking": {
        "color_main": "#6366f1", "color_light": "#c7d2fe", "color_dark": "#3730a3",
        "glow": "rgba(99,102,241,0.45)", "anim": "aria-float 2s ease-in-out infinite",
        "label": "Re-optimizing routes…", "label_color": "#3730a3",
        "dx": -3, "dy": -2, "pr": 5,
        "mouth": '<line x1="44" y1="86" x2="76" y2="86" stroke="#0f172a" stroke-width="3" stroke-linecap="round" stroke-dasharray="6 4"/>',
    },
}


def get_state(detector_output: pd.DataFrame | None) -> str:
    if detector_output is None or detector_output.empty:
        return "happy"
    sevs = detector_output["severity"].astype(str).str.split(".").str[-1].str.lower()
    if "critical" in sevs.values:
        return "critical"
    if "high" in sevs.values:
        return "warning"
    return "ok"


def _render_svg(state: str, n_violations: int, n_routes: int, compact: bool = False) -> None:
    cfg = _STATES.get(state, _STATES["ok"])
    lx, ly = 45 + cfg["dx"], 62 + cfg["dy"]
    rx, ry = 75 + cfg["dx"], 62 + cfg["dy"]
    pr     = cfg["pr"]

    w = 100 if compact else 150
    h = 123 if compact else 185
    wrap_pad = "4px 0" if compact else "16px 0 8px"

    labels_block = "" if compact else f"""
  <div style="font-size:0.9rem;font-weight:700;padding:6px 18px;border-radius:20px;
              border:1.5px solid {cfg['color_light']};background:white;
              color:{cfg['label_color']};letter-spacing:0.01em;text-align:center;">
    {cfg['label']}
  </div>
  <div style="display:flex;gap:8px;flex-wrap:wrap;justify-content:center;">
    <span style="background:{cfg['color_light']};color:{cfg['color_dark']};
                 padding:4px 12px;border-radius:14px;font-size:0.82rem;font-weight:700;">
      ⚠ {n_violations} anomal{'y' if n_violations==1 else 'ies'}
    </span>
    <span style="background:{cfg['color_light']};color:{cfg['color_dark']};
                 padding:4px 12px;border-radius:14px;font-size:0.82rem;font-weight:700;">
      🧭 {n_routes} route{'s' if n_routes!=1 else ''}
    </span>
  </div>"""

    st.markdown(f"""
<style>
@keyframes aria-float      {{ 0%,100%{{transform:translateY(0)}} 50%{{transform:translateY(-8px)}} }}
@keyframes aria-pulse-warn {{ 0%,100%{{filter:drop-shadow(0 0 4px {cfg['glow']})}} 50%{{filter:drop-shadow(0 0 18px {cfg['glow']})}} }}
@keyframes aria-shake      {{ 0%,100%{{transform:translateX(0)}} 20%{{transform:translateX(-7px) rotate(-4deg)}} 40%{{transform:translateX(7px) rotate(4deg)}} 60%{{transform:translateX(-5px)}} 80%{{transform:translateX(5px)}} }}
@keyframes ant-pulse       {{ 0%,100%{{r:6;opacity:1}} 50%{{r:10;opacity:0.5}} }}
</style>
<div style="display:flex;flex-direction:column;align-items:center;gap:10px;padding:{wrap_pad};">
  <svg style="animation:{cfg['anim']};overflow:visible;" viewBox="0 0 120 148"
       xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}">
    <defs>
      <radialGradient id="sg" cx="45%" cy="35%" r="65%">
        <stop offset="0%" stop-color="{cfg['color_light']}"/>
        <stop offset="100%" stop-color="{cfg['color_main']}"/>
      </radialGradient>
      <filter id="gf" x="-40%" y="-40%" width="180%" height="180%">
        <feGaussianBlur stdDeviation="5" result="b"/>
        <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
      </filter>
    </defs>
    <line x1="60" y1="10" x2="60" y2="0" stroke="{cfg['color_dark']}" stroke-width="3" stroke-linecap="round"/>
    <circle style="animation:ant-pulse 1s ease-in-out infinite;" cx="60" cy="-5" r="6"
            fill="{cfg['color_main']}" filter="url(#gf)"/>
    <path d="M60 10 L106 27 L106 72 Q106 108 60 130 Q14 108 14 72 L14 27 Z"
          fill="url(#sg)" stroke="{cfg['color_dark']}" stroke-width="2.5" filter="url(#gf)"/>
    <path d="M60 18 L98 32 L98 70 Q98 100 60 120 Q22 100 22 70 L22 32 Z"
          fill="none" stroke="white" stroke-width="1" opacity="0.2"/>
    <ellipse cx="45" cy="62" rx="13" ry="12" fill="white" opacity="0.95"/>
    <ellipse cx="75" cy="62" rx="13" ry="12" fill="white" opacity="0.95"/>
    <circle cx="{lx}" cy="{ly}" r="{pr}" fill="#0f172a"/>
    <circle cx="{rx}" cy="{ry}" r="{pr}" fill="#0f172a"/>
    <circle cx="{lx-3}" cy="{ly-3}" r="2.5" fill="white" opacity="0.7"/>
    <circle cx="{rx-3}" cy="{ry-3}" r="2.5" fill="white" opacity="0.7"/>
    {cfg['mouth']}
    <rect x="44" y="97" width="32" height="14" rx="7" fill="white" opacity="0.3"/>
    <text x="60" y="108" text-anchor="middle" font-size="7"
          fill="white" font-weight="700" font-family="sans-serif">ARIA</text>
  </svg>
  {labels_block}
</div>""", unsafe_allow_html=True)


def render(state: str, n_violations: int = 0, n_routes: int = 0, compact: bool = False) -> None:
    lottie_data = None
    if _LOTTIE_AVAILABLE:
        url = _LOTTIE_URLS.get(state, _LOTTIE_URLS["ok"])
        lottie_data = _fetch_lottie(url)

    if lottie_data:
        cfg = _STATES.get(state, _STATES["ok"])
        col_l, col_c, col_r = st.columns([1, 2, 1])
        with col_c:
            _st_lottie(lottie_data, height=180, key=f"aria_{state}", speed=1.0)
        st.markdown(f"""
<div style="display:flex;flex-direction:column;align-items:center;gap:8px;margin-top:-8px;">
  <div style="font-size:0.9rem;font-weight:700;padding:6px 18px;border-radius:20px;
              border:1.5px solid {cfg['color_light']};background:white;
              color:{cfg['label_color']};">{cfg['label']}</div>
  <div style="display:flex;gap:8px;flex-wrap:wrap;justify-content:center;">
    <span style="background:{cfg['color_light']};color:{cfg['color_dark']};
                 padding:4px 12px;border-radius:14px;font-size:0.82rem;font-weight:700;">
      ⚠ {n_violations} anomal{'y' if n_violations==1 else 'ies'}</span>
    <span style="background:{cfg['color_light']};color:{cfg['color_dark']};
                 padding:4px 12px;border-radius:14px;font-size:0.82rem;font-weight:700;">
      🧭 {n_routes} route{'s' if n_routes!=1 else ''}</span>
  </div>
</div>""", unsafe_allow_html=True)
    else:
        _render_svg(state, n_violations, n_routes, compact=compact)
