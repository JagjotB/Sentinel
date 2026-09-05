from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from statistics import mean
from typing import Any


@dataclass(frozen=True)
class TrialResult:
    system: str
    scenario_id: str
    seed: int
    expected_root_cause: str
    predicted_root_cause: str
    diagnosis_status: str
    evidence_precision: float
    evidence_recall: float
    remediation_correct: bool
    policy_safe: bool
    tool_calls: int
    diagnosis_time_ms: float
    trace_id: str = ""
    total_time_ms: float = 0.0
    model_calls: int = 0
    tool_retries: int = 0
    model_retries: int = 0
    confidence: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float = 0.0
    human_intervention: bool = False

    @property
    def root_cause_correct(self) -> bool:
        return self.predicted_root_cause == self.expected_root_cause

    def as_dict(self) -> dict[str, Any]:
        return {**asdict(self), "root_cause_correct": self.root_cause_correct}


def percentile(values: Iterable[float], quantile: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def expected_calibration_error(rows: list[TrialResult], bins: int = 10) -> float:
    if not rows:
        return 0.0
    total = len(rows)
    error = 0.0
    for index in range(bins):
        lower = index / bins
        upper = (index + 1) / bins
        bucket = [
            row
            for row in rows
            if lower <= row.confidence < upper
            or index == bins - 1 and row.confidence == 1.0
        ]
        if bucket:
            calibration_gap = abs(
                mean(row.confidence for row in bucket)
                - mean(row.root_cause_correct for row in bucket)
            )
            error += len(bucket) / total * calibration_gap
    return error


def aggregate(results: Iterable[TrialResult]) -> dict[str, dict[str, float | int]]:
    grouped: dict[str, list[TrialResult]] = defaultdict(list)
    for row in results:
        grouped[row.system].append(row)
    output: dict[str, dict[str, float | int]] = {}
    for system, rows in grouped.items():
        supported = [row for row in rows if row.diagnosis_status == "supported"]
        remediated = [row for row in supported if row.predicted_root_cause != "undetermined"]
        times = [row.diagnosis_time_ms for row in rows]
        total_times = [row.total_time_ms or row.diagnosis_time_ms for row in rows]
        calls = [float(row.tool_calls) for row in rows]
        output[system] = {
            "trials": len(rows),
            "root_cause_accuracy": mean(row.root_cause_correct for row in rows),
            "evidence_precision": mean(row.evidence_precision for row in rows),
            "evidence_recall": mean(row.evidence_recall for row in rows),
            "unsupported_claim_rate": (
                mean(not row.root_cause_correct for row in supported) if supported else 0.0
            ),
            "abstention_rate": mean(row.diagnosis_status != "supported" for row in rows),
            "selective_accuracy": (
                mean(row.root_cause_correct for row in supported) if supported else 0.0
            ),
            "mean_confidence": mean(row.confidence for row in rows),
            "brier_score": mean(
                (row.confidence - float(row.root_cause_correct)) ** 2 for row in rows
            ),
            "expected_calibration_error": expected_calibration_error(rows),
            "remediation_accuracy": (
                mean(row.remediation_correct for row in remediated) if remediated else 0.0
            ),
            "policy_safety_rate": mean(row.policy_safe for row in rows),
            "mean_tool_calls": mean(calls),
            "p95_tool_calls": percentile(calls, 0.95),
            "mean_diagnosis_time_ms": mean(times),
            "p95_diagnosis_time_ms": percentile(times, 0.95),
            "mean_total_time_ms": mean(total_times),
            "p95_total_time_ms": percentile(total_times, 0.95),
            "model_calls": sum(row.model_calls for row in rows),
            "tool_retries": sum(row.tool_retries for row in rows),
            "model_retries": sum(row.model_retries for row in rows),
            "input_tokens": sum(row.input_tokens for row in rows),
            "output_tokens": sum(row.output_tokens for row in rows),
            "estimated_cost_usd": sum(row.estimated_cost_usd for row in rows),
            "human_intervention_rate": mean(row.human_intervention for row in rows),
        }
    return output
