"""Surplus food matcher — connect a surplus offer to eligible clients.

Pure Python, no Streamlit imports. The Streamlit page in
app/pages/4_🍱_Surplus.py calls match_surplus() and renders the result.

Safety model:
- "active" enrolment only
- Hard allergen stop on severe/anaphylactic severity
- Ranked by food_security_level (severe first), then by proximity
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from src.optimizer.constrained_greedy import _haversine


# ---------------------------------------------------------------------------
# Allergen vocabulary — map user-typed tokens to canonical client columns
# ---------------------------------------------------------------------------

_ALIAS: dict[str, str] = {
    "dairy": "dairy", "milk": "dairy",
    "egg": "egg", "eggs": "egg",
    "fish": "fish",
    "peanut": "peanut", "peanuts": "peanut",
    "soy": "soy", "soya": "soy",
    "tree_nut": "tree_nut", "tree_nuts": "tree_nut", "nut": "tree_nut", "nuts": "tree_nut",
    "wheat": "wheat", "gluten": "wheat",
}

_COL_FOR: dict[str, str] = {
    "dairy":    "allergy_dairy_severity",
    "egg":      "allergy_egg_severity",
    "fish":     "allergy_fish_severity",
    "peanut":   "allergy_peanut_severity",
    "soy":      "allergy_soy_severity",
    "tree_nut": "allergy_tree_nut_severity",
    "wheat":    "allergy_wheat_severity",
}

_HARD_STOP = frozenset({"severe", "anaphylactic"})

# Food security ranking: lower = higher priority
_FOOD_SEC_RANK: dict[str, int] = {
    "severe":   0,
    "moderate": 1,
    "marginal": 2,
    "secure":   3,
}


# ---------------------------------------------------------------------------
# Public dataclasses
# ---------------------------------------------------------------------------

@dataclass
class SurplusOffer:
    name: str
    portions: int
    allergens: list[str] = field(default_factory=list)
    lat: float = 0.0
    lng: float = 0.0
    pickup_by: str = ""
    donor_name: str = ""
    cold_chain: bool = False


@dataclass
class MatchResult:
    client_id: str
    name: str
    address: str
    lat: float
    lng: float
    distance_km: float
    food_security_level: str
    excluded: bool
    exclusion_reason: str = ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _canonical_allergens(tokens: list[str] | None) -> set[str]:
    """Map free-form allergen tokens to the canonical keys used in client cols."""
    out: set[str] = set()
    for tok in (tokens or []):
        key = _ALIAS.get(str(tok).strip().lower())
        if key:
            out.add(key)
    return out


def _hard_stop_reason(row: pd.Series, offer_allergens: set[str]) -> Optional[str]:
    """Return 'dairy allergy (severe)' style string if any offer allergen
    matches a severe/anaphylactic client allergy; None otherwise.
    """
    for allergen in offer_allergens:
        col = _COL_FOR.get(allergen)
        if col is None or col not in row.index:
            continue
        raw = row.get(col)
        if pd.isna(raw):
            continue
        sev = str(raw).strip().lower()
        if sev in _HARD_STOP:
            return f"{allergen} allergy ({sev})"
    return None


def _name(row: pd.Series) -> str:
    first = str(row.get("first_name", "") or "").strip()
    last  = str(row.get("last_name", "") or "").strip()
    full  = f"{first} {last}".strip()
    return full or str(row.get("client_id", "Unknown"))


def _address(row: pd.Series) -> str:
    parts: list[str] = []
    for col in ("address_street", "address_city", "address_postal"):
        val = row.get(col)
        if pd.notna(val) and str(val).strip():
            parts.append(str(val).strip())
    return ", ".join(parts) if parts else "—"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def match_surplus(
    offer: SurplusOffer,
    tables: dict,
    max_results: int = 10,
) -> tuple[list[MatchResult], list[MatchResult]]:
    """Match a surplus offer to eligible active clients.

    Returns (matched, excluded):
      - matched: up to `max_results` eligible clients, ranked by food
        security (severe first), then by proximity (closest first).
      - excluded: up to 5 nearby clients who were blocked by an allergen
        hard stop — included so the UI can show the safety story.
    """
    clients = tables["clients"]

    # Active enrolment + valid coords
    work = clients[
        clients["enrolment_status"].astype(str).str.lower() == "active"
    ].copy()
    work = work.dropna(subset=["lat", "lng"])
    if work.empty:
        return ([], [])

    offer_allergens = _canonical_allergens(offer.allergens)

    matched: list[MatchResult] = []
    excluded: list[MatchResult] = []

    for _, row in work.iterrows():
        lat = float(row["lat"])
        lng = float(row["lng"])
        dist = _haversine(offer.lat, offer.lng, lat, lng)

        reason = _hard_stop_reason(row, offer_allergens)
        food_sec = str(row.get("food_security_level", "") or "").strip().lower() or "unknown"

        result = MatchResult(
            client_id=str(row["client_id"]),
            name=_name(row),
            address=_address(row),
            lat=lat,
            lng=lng,
            distance_km=dist,
            food_security_level=food_sec,
            excluded=bool(reason),
            exclusion_reason=reason or "",
        )

        if reason:
            excluded.append(result)
        else:
            matched.append(result)

    # Rank matched: (food_security_rank, distance)
    matched.sort(
        key=lambda r: (_FOOD_SEC_RANK.get(r.food_security_level, 99), r.distance_km)
    )

    # Rank excluded by proximity only, cap at 5 for demo
    excluded.sort(key=lambda r: r.distance_km)

    return (matched[:max_results], excluded[:5])
