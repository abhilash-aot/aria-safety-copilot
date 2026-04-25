"""Command-line preview of the Safety Copilot pipeline for a given service_date.

Usage:
    python3 demo.py                 # uses 2026-04-14
    python3 demo.py 2026-04-15
"""

from __future__ import annotations

import sys
from datetime import date

from shared.src.loaders import load_track2
from src.safety.detectors import run_all
from src.optimizer.constrained_greedy import reoptimize
from src.brief.morning_brief import render_brief


def main(service_date: date) -> None:
    tables = load_track2("tracks/food-security-delivery/data/raw")

    detector_output = run_all(tables, service_date)
    vrp_output = reoptimize(tables, service_date)
    brief = render_brief(service_date, detector_output, vrp_output, tables)

    line = "─" * 72
    print(f"\n{line}\nSafety Copilot — {service_date}\n{line}\n")

    print("MORNING BRIEF")
    print(brief["paragraph"])
    print()
    for b in brief["bullets"]:
        print(b)

    print(f"\n{line}\nTOP ANOMALIES (of {len(detector_output)})\n{line}")
    for _, row in detector_output.head(8).iterrows():
        sev = str(row["severity"]).upper().replace("SEVERITY.", "")
        print(f"[{sev:8s}] {row['rule']}")
        print(f"           {row['explanation']}")
        if row["suggested_fix"]:
            print(f"           → {row['suggested_fix']}")

    print(f"\n{line}\nOPTIMIZER\n{line}")
    print(f"Routes built        : {len(vrp_output['routes'])}")
    print(f"Dropped requests    : {len(vrp_output['dropped_requests'])}")
    print(f"Drive minutes       : {vrp_output['total_drive_minutes']} (baseline {vrp_output['baseline_drive_minutes']})")
    print(f"Delta vs baseline   : {vrp_output['delta_pct']*100:+.1f}%")
    print(f"Projected on-time   : {vrp_output['projected_on_time_rate']*100:.1f}%")
    print(f"Safety violations   : {len(vrp_output['violations'])}  (guaranteed 0)")
    print()


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "2026-04-14"
    y, m, d = (int(x) for x in arg.split("-"))
    main(date(y, m, d))
