from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from evals.metrics import TrialResult, aggregate, percentile
from evals.runner import (
    RUNTIME_SYSTEMS,
    SYSTEM_ORDER,
    direct_alert_prediction,
    evaluate,
    evidence_signals,
)
from runtime.state import Evidence


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


def test_evidence_signal_rubric_maps_observable_artifacts() -> None:
    evidence = [
        Evidence(
            id="ev_event",
            source="kubernetes",
            kind="events",
            summary="container terminated reason=OOMKilled exit_code=137",
            payload={},
            raw_reference="kubernetes://event",
        ),
        Evidence(
            id="ev_anomaly",
            source="telemetry",
            kind="learned_anomaly",
            summary="dimensions p95_latency, error_rate, memory",
            payload={},
            raw_reference="model://anomaly",
        ),
        Evidence(
            id="ev_limits",
            source="kubernetes",
            kind="resource_limits",
            summary="Kubernetes resource limits collected",
            payload={"memory": "256Mi"},
            raw_reference="kubernetes://limits",
        ),
    ]

    signals = evidence_signals(evidence, {item.id for item in evidence})

    assert {"oom_event", "memory_spike", "resource_limit"}.issubset(signals)


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


def test_checked_in_independent_report_has_complete_provenance() -> None:
    root = Path(__file__).resolve().parents[2]
    report = json.loads(
        (root / "evals" / "reports" / "latest" / "summary.json").read_text(
            encoding="utf-8"
        )
    )
    raw = json.loads(
        (root / "evals" / "reports" / "latest" / "raw-results.json").read_text(
            encoding="utf-8"
        )
    )
    manifest = report["manifest"]

    assert manifest["protocol_version"] == "independent-v2"
    assert manifest["independent_trial_count"] == 324
    assert Counter(row["system"] for row in raw) == Counter(
        {system: 36 for system in SYSTEM_ORDER}
    )
    assert len({row["trace_id"] for row in raw}) == 324
    assert all(len(row["trace_id"]) == 32 for row in raw)
    assert all(row["total_time_ms"] > 0 for row in raw)
    catalog = root / "simulator" / "scenarios" / "catalog.json"
    assert manifest["scenario_catalog_sha256"] == hashlib.sha256(
        catalog.read_bytes()
    ).hexdigest()
