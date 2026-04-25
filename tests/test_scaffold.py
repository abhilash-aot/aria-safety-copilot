"""Scaffold smoke test — confirms the core modules import cleanly.

This file provides a minimal passing test so that ``pytest tests/ -q`` exits 0
before the detector and router agents have populated the other test files.
"""

from __future__ import annotations


def test_imports() -> None:
    """Verify that the two shared primitives are importable without error."""
    from src.safety.models import Severity, Violation  # noqa: F401
    from src.io.golden_join import build_stops_enriched  # noqa: F401


def test_severity_values() -> None:
    """Severity enum has exactly the 5 values the plan specifies."""
    from src.safety.models import Severity

    assert Severity.CRITICAL == "critical"
    assert Severity.HIGH == "high"
    assert Severity.MEDIUM == "medium"
    assert Severity.LOW == "low"
    assert Severity.INFO == "info"
    assert len(list(Severity)) == 5


def test_violation_fields() -> None:
    """Violation dataclass accepts all 11 fields without error."""
    from datetime import date

    from src.safety.models import Severity, Violation

    v = Violation(
        rule="test_rule",
        severity=Severity.HIGH,
        service_date=date(2026, 4, 21),
        route_id="RTE-001",
        stop_id="STP-001",
        request_id="REQ-001",
        client_id="MOW-001",
        driver_id="DRV-001",
        vehicle_id="VEH-001",
        explanation="Test explanation with RTE-001 and MOW-001",
        suggested_fix="Do something",
    )
    assert v.rule == "test_rule"
    assert v.severity is Severity.HIGH
