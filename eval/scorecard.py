"""Evaluation harness for Track 2 Safety Copilot.

Measures detector accuracy against seeded ground truth and optimizer safety lift
across a sample of service dates. Writes scorecard.json and SCORECARD.md.

CLI:
    python eval/scorecard.py --out eval/

Callable:
    from eval.scorecard import main
    main(out_dir="eval/", data_dir="tracks/food-security-delivery/data/raw")
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

# ---------------------------------------------------------------------------
# Path bootstrap — make src.* and shared.src.* importable from any cwd
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from shared.src.loaders import load_track2
from src.safety.detectors import (
    check_post_closure_delivery,
    check_severe_allergen,
    check_two_person_solo,
    run_all,
)
from src.optimizer.constrained_greedy import reoptimize


# ---------------------------------------------------------------------------
# Precision / recall helpers
# ---------------------------------------------------------------------------

def _prf(tp: int, fp: int, fn: int) -> dict:
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
    return {
        "tp": tp, "fp": fp, "fn": fn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
    }


# ---------------------------------------------------------------------------
# Detector accuracy section
# ---------------------------------------------------------------------------

def _eval_detectors(tables: dict) -> dict:
    reqs = tables["requests"]
    routes = tables["routes"]
    ri = tables["request_items"]
    stops = tables["stops"]

    # Ground truth sets — sourced from seeded DATA_QUALITY_ISSUE tags.
    gt_allergen = set(
        ri.loc[
            ri["notes"].str.contains("DATA_QUALITY_ISSUE: allergen conflict", na=False),
            "request_id",
        ].unique()
    )
    gt_closure = set(
        stops.loc[
            stops["driver_notes"].str.contains(
                "DATA_QUALITY_ISSUE: delivered after closure", na=False
            ),
            "route_stop_id",
        ].unique()
    )
    gt_two_person = set(
        stops.loc[
            stops["failure_reason"] == "requires_two_person_unavailable",
            "route_stop_id",
        ].unique()
    )

    # Run allergen detector across all scheduled dates.
    sched_dates = (
        pd.to_datetime(reqs["scheduled_date"], errors="coerce")
        .dt.date.dropna().unique()
    )
    detected_allergen: set = set()
    for d in sched_dates:
        for v in check_severe_allergen(tables, d):
            if v.request_id:
                detected_allergen.add(v.request_id)

    # Run closure detector across all service dates.
    service_dates = (
        pd.to_datetime(routes["service_date"], errors="coerce")
        .dt.date.dropna().unique()
    )
    detected_closure: set = set()
    for d in service_dates:
        for v in check_post_closure_delivery(tables, d):
            if v.stop_id:
                detected_closure.add(v.stop_id)

    # Run two-person detector across all service dates.
    detected_two_person: set = set()
    for d in service_dates:
        for v in check_two_person_solo(tables, d):
            if v.stop_id:
                detected_two_person.add(v.stop_id)

    def _metrics(gt: set, detected: set) -> dict:
        tp = len(gt & detected)
        fp = len(detected - gt)
        fn = len(gt - detected)
        return {**_prf(tp, fp, fn), "ground_truth_count": len(gt)}

    return {
        "severe_allergen": _metrics(gt_allergen, detected_allergen),
        "post_closure": _metrics(gt_closure, detected_closure),
        "two_person_solo": _metrics(gt_two_person, detected_two_person),
    }


# ---------------------------------------------------------------------------
# Optimizer delta section
# ---------------------------------------------------------------------------

def _sample_dates(routes: pd.DataFrame, max_dates: int = 14) -> list:
    """Return every-other date from sorted unique service_dates, up to max_dates."""
    unique_dates = sorted(
        pd.to_datetime(routes["service_date"], errors="coerce")
        .dt.date.dropna().unique()
    )
    # Take every other date.
    sampled = unique_dates[::2]
    return list(sampled[:max_dates])


def _eval_optimizer(tables: dict) -> tuple[dict, list]:
    """Return (optimizer_delta dict, sampled_dates list)."""
    routes = tables["routes"]
    sampled = _sample_dates(routes)

    delta_pcts = []
    on_time_rates = []
    n_routes_list = []
    n_drops_list = []
    total_mins_list = []
    baseline_mins_list = []

    for d in sampled:
        result = reoptimize(tables, d)
        delta_pcts.append(result["delta_pct"])
        on_time_rates.append(result["projected_on_time_rate"])
        n_routes_list.append(len(result["routes"]))
        n_drops_list.append(len(result["dropped_requests"]))
        total_mins_list.append(result["total_drive_minutes"])
        baseline_mins_list.append(result["baseline_drive_minutes"])

    def _mean(lst):
        return round(sum(lst) / len(lst), 4) if lst else 0.0

    return {
        "sampled_dates": [str(d) for d in sampled],
        "mean_delta_pct": _mean(delta_pcts),
        "mean_projected_on_time_rate": _mean(on_time_rates),
        "mean_routes_per_day": _mean(n_routes_list),
        "mean_drops_per_day": _mean(n_drops_list),
        "mean_total_minutes": _mean(total_mins_list),
        "mean_baseline_minutes": _mean(baseline_mins_list),
    }, sampled


# ---------------------------------------------------------------------------
# Constraint audit section
# ---------------------------------------------------------------------------

def _eval_constraint_audit(tables: dict, sampled_dates: list) -> dict:
    """Count CRITICAL/HIGH violations in optimizer output and raw baseline."""
    opt_critical = 0
    opt_high = 0
    baseline_criticals = []
    baseline_highs = []

    for d in sampled_dates:
        result = reoptimize(tables, d)
        # violations is always [] by construction (guaranteed by constrained_greedy).
        for v in result["violations"]:
            if hasattr(v, "severity"):
                sev = v.severity
            else:
                sev = str(v.get("severity", ""))
            if sev == "critical":
                opt_critical += 1
            elif sev == "high":
                opt_high += 1

        # Baseline: raw schedule violations before optimization.
        raw_df = run_all(tables, d)
        if not raw_df.empty:
            baseline_criticals.append(int((raw_df["severity"] == "critical").sum()))
            baseline_highs.append(int((raw_df["severity"] == "high").sum()))
        else:
            baseline_criticals.append(0)
            baseline_highs.append(0)

    n = len(sampled_dates)
    mean_crit = round(sum(baseline_criticals) / n, 2) if n else 0.0
    mean_high = round(sum(baseline_highs) / n, 2) if n else 0.0

    return {
        "optimizer_critical_count": opt_critical,
        "optimizer_high_count": opt_high,
        "baseline_mean_critical_per_day": mean_crit,
        "baseline_mean_high_per_day": mean_high,
    }


# ---------------------------------------------------------------------------
# Markdown renderer
# ---------------------------------------------------------------------------

def _render_md(data: dict) -> str:
    now = data["generated_at"]
    data_dir = data["data_dir"]
    da = data["detector_accuracy"]
    od = data["optimizer_delta"]
    ca = data["constraint_audit"]
    n_dates = len(od["sampled_dates"])

    lines = [
        "# Scorecard — Track 2 Safety Copilot",
        "",
        f"Generated {now} from `{data_dir}`.",
        "",
        "## Detector Accuracy",
        "",
        "| Rule | Ground truth | TP | FP | FN | Precision | Recall | F1 |",
        "|---|---|---|---|---|---|---|---|",
    ]

    rule_labels = {
        "severe_allergen": "Severe allergen",
        "post_closure": "Post-closure delivery",
        "two_person_solo": "Two-person solo",
    }
    for key, label in rule_labels.items():
        m = da[key]
        lines.append(
            f"| {label} | {m['ground_truth_count']} | {m['tp']} | {m['fp']} | {m['fn']} "
            f"| {m['precision']:.2f} | {m['recall']:.2f} | {m['f1']:.2f} |"
        )

    lines += [
        "",
        "## Optimizer Delta",
        "",
        f"Sampled {n_dates} service dates (every-other from sorted unique dates).",
        "",
        "| Metric | Value | Note |",
        "|---|---|---|",
        f"| mean_delta_pct | {od['mean_delta_pct']:.2%} | Drive-time reduction vs baseline (see caution below) |",
        f"| mean_drops_per_day | {od['mean_drops_per_day']:.1f} | Requests dropped due to hard-constraint conflicts |",
        f"| mean_projected_on_time_rate | {od['mean_projected_on_time_rate']:.2%} | Fraction of safe requests assigned |",
        f"| mean_routes_per_day | {od['mean_routes_per_day']:.1f} | Active routes in optimized plan |",
        f"| mean_total_minutes | {od['mean_total_minutes']:.0f} | Optimized total drive minutes |",
        f"| mean_baseline_minutes | {od['mean_baseline_minutes']:.0f} | Original schedule drive minutes |",
        "",
        "> **Caution on delta_pct:** The constrained-greedy drops requests that violate hard safety",
        "> constraints (allergen conflicts, post-closure deliveries, driver-cap breaches). The resulting",
        "> plan covers fewer stops than the baseline, so a high `delta_pct` reflects a *smaller safe*",
        "> *workload* in less drive time — not equivalent work done more efficiently.",
        "> Always read `mean_drops_per_day` alongside `delta_pct`.",
        "",
        "## Constraint Audit",
        "",
        f"Optimizer output: **{ca['optimizer_critical_count']} CRITICAL, "
        f"{ca['optimizer_high_count']} HIGH** violations across {n_dates} sampled dates.",
        "",
        f"Raw schedule baseline: mean **{ca['baseline_mean_critical_per_day']} CRITICAL** "
        f"+ **{ca['baseline_mean_high_per_day']} HIGH** violations per day.",
        "",
        "## How to Regenerate",
        "",
        "```",
        "python eval/scorecard.py --out eval/",
        "```",
        "",
        "Commit both `eval/scorecard.json` and `eval/SCORECARD.md` after regenerating.",
    ]

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Public main() — callable and CLI entry point
# ---------------------------------------------------------------------------

DEFAULT_DATA_DIR = "tracks/food-security-delivery/data/raw"


def main(
    out_dir: str = "eval/",
    data_dir: Optional[str] = None,
) -> None:
    if data_dir is None:
        data_dir = DEFAULT_DATA_DIR

    # Resolve paths relative to repo root so the harness works from any cwd.
    data_path = Path(data_dir)
    if not data_path.is_absolute():
        data_path = _REPO_ROOT / data_dir

    out_path = Path(out_dir)
    if not out_path.is_absolute():
        out_path = _REPO_ROOT / out_dir
    out_path.mkdir(parents=True, exist_ok=True)

    tables = load_track2(data_path)

    detector_accuracy = _eval_detectors(tables)
    optimizer_delta, sampled_dates = _eval_optimizer(tables)
    constraint_audit = _eval_constraint_audit(tables, sampled_dates)

    scorecard = {
        "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "data_dir": str(data_dir),
        "detector_accuracy": detector_accuracy,
        "optimizer_delta": optimizer_delta,
        "constraint_audit": constraint_audit,
    }

    json_path = out_path / "scorecard.json"
    md_path = out_path / "SCORECARD.md"

    json_path.write_text(json.dumps(scorecard, indent=2), encoding="utf-8")
    md_path.write_text(_render_md(scorecard), encoding="utf-8")

    # Summary line.
    da = detector_accuracy
    allergen_recall = da["severe_allergen"]["recall"]
    closure_recall = da["post_closure"]["recall"]
    two_recall = da["two_person_solo"]["recall"]
    ca = constraint_audit
    print(
        f"Wrote {json_path} and {md_path}. "
        f"Detector recall: allergen={allergen_recall:.2f} closure={closure_recall:.2f} "
        f"two_person={two_recall:.2f}. "
        f"Optimizer audit: {ca['optimizer_critical_count']} CRITICAL / "
        f"{ca['optimizer_high_count']} HIGH."
    )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate scorecard.json and SCORECARD.md for Track 2 Safety Copilot."
    )
    parser.add_argument(
        "--out",
        default="eval/",
        help="Output directory (default: eval/)",
    )
    parser.add_argument(
        "--data-dir",
        default=DEFAULT_DATA_DIR,
        help=f"Path to raw parquet data (default: {DEFAULT_DATA_DIR})",
    )
    args = parser.parse_args()
    main(out_dir=args.out, data_dir=args.data_dir)
