from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from evals.metrics import TrialResult, aggregate, percentile
from evals.runner import RUNTIME_SYSTEMS, SYSTEM_ORDER, direct_alert_prediction, evaluate


def result(correct: bool) -> TrialResult:
    return TrialResult(
        system="test",
        scenario_id="case",
        seed=1,
        expected_root_cause="oom_killed",
        predicted_root_cause="oom_killed" if correct else "memory_leak",
        diagnosis_status="supported",
        evidence_precision=1.0 if correct else 0.0,
        evidence_recall=0.5,
        remediation_correct=correct,
        policy_safe=True,
        tool_calls=2,
        diagnosis_time_ms=10.0,
    )


def test_aggregate_reports_accuracy_and_unsupported_claims() -> None:
    metrics = aggregate([result(True), result(False)])["test"]
    assert metrics["root_cause_accuracy"] == 0.5
    assert metrics["unsupported_claim_rate"] == 0.5
    assert metrics["policy_safety_rate"] == 1.0


def test_percentile_interpolates_without_external_state() -> None:
    assert percentile([0.0, 10.0], 0.95) == 9.5


def test_direct_baseline_uses_title_overlap() -> None:
    assert direct_alert_prediction("readiness probe path regressed") == "bad_readiness_probe"


def test_each_ablation_disables_exactly_one_full_system_feature() -> None:
    full = asdict(RUNTIME_SYSTEMS["sentinel_full"])
    for name, features in RUNTIME_SYSTEMS.items():
        if not name.startswith("ablation_"):
            continue
        values = asdict(features)
        changed = [key for key in full if values[key] != full[key]]
        assert changed == [name.removeprefix("ablation_no_")]


async def test_evaluation_runs_every_system_in_an_isolated_trace(tmp_path: Path) -> None:
    output = tmp_path / "report"
    rows = await evaluate(output, scenario_limit=1)
    report = json.loads((output / "summary.json").read_text(encoding="utf-8"))

    assert [row.system for row in rows] == list(SYSTEM_ORDER)
    assert len({row.trace_id for row in rows}) == len(SYSTEM_ORDER)
    assert all(len(row.trace_id) == 32 for row in rows)
    assert all(row.total_time_ms > 0 for row in rows)
    assert report["manifest"]["protocol_version"] == "independent-v2"
    assert report["manifest"]["fresh_repository_per_trial"] is True
    assert report["manifest"]["evaluator_labels_in_runtime_snapshot"] is False
