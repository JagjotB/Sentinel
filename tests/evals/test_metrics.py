from __future__ import annotations

from evals.metrics import TrialResult, aggregate, percentile
from evals.runner import direct_alert_prediction


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
