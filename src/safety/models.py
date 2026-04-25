"""Safety data models for Track 2 — Food Security Delivery Operations.

Shared primitive imported by the detector agent, optimizer, brief, and eval harness.
No behavior beyond dataclass / enum basics.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Optional


class Severity(str, Enum):
    CRITICAL = "critical"    # hospitalizable
    HIGH = "high"            # safety
    MEDIUM = "medium"        # compliance
    LOW = "low"              # efficiency
    INFO = "info"


@dataclass
class Violation:
    rule: str                        # e.g. "severe_allergen_in_line_item"
    severity: Severity
    service_date: date
    route_id: Optional[str]
    stop_id: Optional[str]
    request_id: Optional[str]
    client_id: Optional[str]
    driver_id: Optional[str]
    vehicle_id: Optional[str]
    explanation: str                 # human-readable, cites specific IDs
    suggested_fix: Optional[str]     # e.g. "Reassign to VEH-06"
