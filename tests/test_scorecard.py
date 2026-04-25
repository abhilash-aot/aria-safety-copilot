"""Smoke tests for eval/scorecard.py.

These tests run the full scorecard pipeline (detectors + optimizer) so they are
marked slow — run with `pytest -m slow` or included in default run (no -m filter).
Each test calls main() into a tmp_path so it never overwrites eval/scorecard.json.
"""

from __future__ import annotations

import json

import pytest


@pytest.mark.slow
def test_scorecard_regenerates_without_exception(tmp_path):
    from eval.scorecard import main
    main(out_dir=str(tmp_path), data_dir="tracks/food-security-delivery/data/raw")
    assert (tmp_path / "scorecard.json").exists()
    assert (tmp_path / "SCORECARD.md").exists()


@pytest.mark.slow
def test_scorecard_json_has_expected_top_level_keys(tmp_path):
    from eval.scorecard import main
    main(out_dir=str(tmp_path), data_dir="tracks/food-security-delivery/data/raw")
    with open(tmp_path / "scorecard.json") as f:
        data = json.load(f)
    assert "detector_accuracy" in data
    assert "optimizer_delta" in data
    assert "constraint_audit" in data


@pytest.mark.slow
def test_detector_seeded_recall_is_100_percent(tmp_path):
    from eval.scorecard import main
    main(out_dir=str(tmp_path), data_dir="tracks/food-security-delivery/data/raw")
    with open(tmp_path / "scorecard.json") as f:
        data = json.load(f)
    assert data["detector_accuracy"]["severe_allergen"]["recall"] == 1.0
    assert data["detector_accuracy"]["post_closure"]["recall"] == 1.0
