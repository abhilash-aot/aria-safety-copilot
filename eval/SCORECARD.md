# Scorecard — Track 2 Safety Copilot

Generated 2026-04-23T23:00:12Z from `/Users/shabeeb/Work/Other Hacks/social victoria/buildersvault-hackathon-build/tracks/food-security-delivery/data/raw`.

## Detector Accuracy

| Rule | Ground truth | TP | FP | FN | Precision | Recall | F1 |
|---|---|---|---|---|---|---|---|
| Severe allergen | 3 | 3 | 0 | 0 | 1.00 | 1.00 | 1.00 |
| Post-closure delivery | 4 | 4 | 148 | 0 | 0.03 | 1.00 | 0.05 |
| Two-person solo | 7 | 7 | 233 | 0 | 0.03 | 1.00 | 0.06 |

## Optimizer Delta

Sampled 11 service dates (every-other from sorted unique dates).

| Metric | Value | Note |
|---|---|---|
| mean_delta_pct | 89.05% | Drive-time reduction vs baseline (see caution below) |
| mean_drops_per_day | 56.8 | Requests dropped due to hard-constraint conflicts |
| mean_projected_on_time_rate | 35.58% | Fraction of safe requests assigned |
| mean_routes_per_day | 2.3 | Active routes in optimized plan |
| mean_total_minutes | 70 | Optimized total drive minutes |
| mean_baseline_minutes | 3623 | Original schedule drive minutes |

> **Caution on delta_pct:** The constrained-greedy drops requests that violate hard safety
> constraints (allergen conflicts, post-closure deliveries, driver-cap breaches). The resulting
> plan covers fewer stops than the baseline, so a high `delta_pct` reflects a *smaller safe*
> *workload* in less drive time — not equivalent work done more efficiently.
> Always read `mean_drops_per_day` alongside `delta_pct`.

## Constraint Audit

Optimizer output: **0 CRITICAL, 0 HIGH** violations across 11 sampled dates.

Raw schedule baseline: mean **0.09 CRITICAL** + **15.82 HIGH** violations per day.

## How to Regenerate

```
python eval/scorecard.py --out eval/
```

Commit both `eval/scorecard.json` and `eval/SCORECARD.md` after regenerating.
