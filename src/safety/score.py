"""Safety-score helper — severity-weighted risk score for a day.

Used on the Home hero to show "100/100 safe" vs the raw schedule, and
to make the climbing-score story visible as the operator applies fixes.
"""

from __future__ import annotations

import pandas as pd

# Severity → risk weight. Tuned so a single CRITICAL dominates many LOWs.
_RISK_WEIGHT = {
    "critical": 10,
    "high":     5,
    "medium":   2,
    "low":      1,
}


def risk_points(violations_df: pd.DataFrame) -> int:
    """Sum of risk weights across all violations in the DataFrame."""
    if violations_df is None or violations_df.empty:
        return 0
    sev = (
        violations_df["severity"]
        .astype(str).str.lower().str.split(".").str[-1]
    )
    return int(sev.map(_RISK_WEIGHT).fillna(0).sum())


def safety_score(raw: pd.DataFrame, current: pd.DataFrame) -> dict:
    """Compute the safety score (0–100) and the cleared-risk delta.

    Args:
        raw:     violations on the unmodified schedule (no fixes applied).
        current: violations on the current schedule (with overlay fixes).

    Returns:
        {
            "raw_risk":     int,
            "current_risk": int,
            "cleared":      int,    # raw_risk - current_risk, clamped >= 0
            "score":        int,    # 0..100; 100 if no risk to begin with
        }
    """
    raw_risk     = risk_points(raw)
    current_risk = risk_points(current)
    cleared      = max(0, raw_risk - current_risk)
    score        = (
        int(round(100 * (1 - current_risk / raw_risk)))
        if raw_risk > 0 else 100
    )
    return {
        "raw_risk":     raw_risk,
        "current_risk": current_risk,
        "cleared":      cleared,
        "score":        score,
    }
