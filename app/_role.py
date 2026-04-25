"""Per-page role guard + sidebar chip + nav filter.

Sub-pages should call `enforce_role(allowed_roles)` near the top, after
inject_phone_css(). This:
  - Sends users without a role back to the login gate (copilot.py)
  - Sends users whose role isn't in allowed_roles back to their primary page
  - Renders the same role chip + Switch role button in the sidebar
  - Injects the same role-based nav filter so the sidebar matches the home

Keeps role logic in one place — sub-pages just declare their allowed roles.
"""

from __future__ import annotations

import streamlit as st


_HIDDEN_PAGES_BY_ROLE: dict[str, list[str]] = {
    "volunteer":   ["Driver", "Coordinator", "Scorecard", "Safety_Audit"],
    "driver":      ["Home", "Coordinator", "Scorecard", "Safety_Audit", "Surplus"],
    "coordinator": ["Driver", "Scorecard", "Safety_Audit"],
    "auditor":     ["Home", "Driver", "Coordinator", "Surplus"],
    "demo":        [],
}

_PRIMARY_PAGE_BY_ROLE: dict[str, str] = {
    "volunteer":   "copilot.py",
    "driver":      "pages/2_🚚_Driver.py",
    "coordinator": "copilot.py",
    "auditor":     "pages/2_📈_Scorecard.py",
    "demo":        "copilot.py",
}

_ROLE_DISPLAY: dict[str, tuple[str, str]] = {
    "volunteer":   ("🏠", "Volunteer Lead"),
    "driver":      ("🚚", "Driver"),
    "coordinator": ("📊", "Coordinator"),
    "auditor":     ("🔐", "Auditor"),
    "demo":        ("🎭", "Demo mode"),
}


def _inject_role_filter(role: str) -> None:
    hidden = _HIDDEN_PAGES_BY_ROLE.get(role, [])
    if not hidden:
        return
    rules: list[str] = []
    for p in hidden:
        if p == "Home":
            rules.append(
                '[data-testid="stSidebarNavLink"]:has(span[label="copilot"])'
                '{display:none!important;}'
            )
        else:
            rules.append(
                f'[data-testid="stSidebarNavLink"][href$="/{p}"]'
                f'{{display:none!important;}}'
            )
    st.markdown(f"<style>{''.join(rules)}</style>", unsafe_allow_html=True)


def _render_role_chip(role: str) -> None:
    icon, label = _ROLE_DISPLAY.get(role, ("👤", "Signed in"))
    st.sidebar.markdown(f"""
<div class="role-chip">
  <div class="role-chip-icon">{icon}</div>
  <div class="role-chip-text">
    <div class="role-chip-label">{label}</div>
    <div class="role-chip-sub">SIGNED IN</div>
  </div>
</div>
""", unsafe_allow_html=True)
    if st.sidebar.button("↩ Switch role", key=f"switch_role_{role}", use_container_width=True):
        st.session_state.pop("role", None)
        st.switch_page("copilot.py")


def enforce_role(allowed: set[str]) -> str:
    """Guard the page: redirect if no role / wrong role; render chip + filter.

    Call this near the top of every sub-page (after inject_phone_css).
    `allowed` should be a set of role names (e.g. {"volunteer", "coordinator"}).
    "demo" always passes.
    """
    if "role" not in st.session_state:
        # No login → bounce to landing where the gate will render.
        st.switch_page("copilot.py")
    role = st.session_state["role"]

    if role != "demo" and role not in allowed:
        # Wrong role for this page → send to their primary page.
        target = _PRIMARY_PAGE_BY_ROLE.get(role, "copilot.py")
        st.switch_page(target)

    _render_role_chip(role)
    _inject_role_filter(role)
    return role
