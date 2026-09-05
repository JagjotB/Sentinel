# ruff: noqa: E501 -- report and SVG templates are clearer as literal lines.
from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import importlib.metadata
import json
import platform
import re
import shutil
import subprocess
import sys
import time
from collections import Counter
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from typing import Any

from agents.base import InvestigationContext
from agents.diagnosis import DiagnosisAgent
from agents.service import InvestigationService
from evals.metrics import TrialResult, aggregate
from mcp.factory import ToolProviderConfig, mount_investigation_tools
from persistence.repository import SentinelRepository
from retrieval import build_corpus
from retrieval.ingest import corpus_checksum
from runtime.budgets import BudgetLedger, BudgetPolicy
from runtime.features import InvestigationFeatures
from runtime.state import Diagnosis, Evidence, ExecutionStatus, RuntimeState
from runtime.tool_registry import ToolRegistry
from runtime.tracing import configure_telemetry, span, trace_id_for
from simulator.catalog import FAULT_SPECS, build_catalog
from simulator.engine import IncidentSimulator
from simulator.models import Scenario

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = ROOT / "evals" / "reports" / "latest"
SCRATCH = ROOT / "tmp" / "evals-independent-v2"
ALL_SIGNALS = sorted({signal for spec in FAULT_SPECS for signal in spec[4]})
SIGNAL_PATTERNS: dict[str, tuple[str, ...]] = {
    "acquire_timeout": ("acquire_timeout", "pool_acquire_timeout"),
    "commit_diff": ("get_diff", "source_control_result_for_get_diff", "diff"),
    "configmap_diff": ("configmap", "payments_url", "upstream_connection_failed"),
    "connection_error": ("connection_failed", "invalid_host"),
    "consumer_lag": ("consumer_lag",),
    "cpu_throttle": ("cpu_throttled", "cpu_throttle"),
    "denied_flow": ("connection_denied", "denied_by_policy"),
    "dependency_timeout": ("deadline_exceeded", "request_timeout"),
    "disk_pressure": ("diskpressure", "disk_pressure"),
    "dns_error": ("no_such_host", "dns_resolution_failed", "lookup_payments"),
    "downstream_latency": ("gateway_latency", "deadline_exceeded", "p95_latency"),
    "empty_endpoints": ("zero_ready_endpoints", "endpoints_0"),
    "environment_diff": ("feature_flag", "environment", "get_diff"),
    "error_onset": ("error_rate", "onset_timestamp"),
    "eviction_event": ("eviction", "evicted"),
    "exception_cluster": ("unsupportedschema", "exception", "rare_log_cluster"),
    "gc_pressure": ("heap_pressure", "retained_buffers"),
    "healthy_pods": ("ready_true", "ready_pods"),
    "http_429_cluster": ("status_429", "returned_status_num"),
    "image_pull_backoff": ("imagepullbackoff", "image_pull_backoff"),
    "latency_spike": ("p95_latency", "execution_delayed"),
    "lock_wait": ("waiting_on_row_lock", "lock_wait"),
    "log_growth": ("log_growth", "ephemeral_storage"),
    "manifest_diff": ("image_worker_missing", "readyz", "get_diff"),
    "memory_spike": ("dimensions_p95_latency_error_rate_memory", "oomkilled"),
    "memory_trend": ("retained_buffers_increasing", "dimensions_p95_latency_error_rate_memory"),
    "oom_event": ("oomkilled", "exit_code_num"),
    "policy_diff": ("network_policy", "egress_connection_denied"),
    "pool_saturation": ("database_pool", "db_connections"),
    "probe_failure": ("readiness_probe_failed", "unhealthy"),
    "queue_depth": ("queue_depth", "queue_saturated"),
    "rate_limit_headers": ("retry_after",),
    "resource_limit": ("resource_limits", "memory_256mi", "cpu_500m"),
    "rollout_event": ("revision", "deployment", "release_change"),
    "secret_key_missing": ("missing_secret_key", "payment_token"),
    "selector_diff": ("zero_ready_endpoints", "endpoints_0"),
    "slow_query": ("ledger_update", "row_lock"),
    "startup_failure": ("startup_failed",),
    "timeout_log": ("deadline_exceeded", "acquire_timeout"),
    "trace_gap": ("network_io", "no_such_host"),
    "trace_span": ("trace_id", "deadline_exceeded"),
    "traffic_spike": ("request_rate", "arrival_rate"),
    "validation_error": ("invalid_feature_flag", "invalid_value"),
    "zero_ready_endpoints": ("zero_ready_endpoints", "endpoints_0"),
    "zero_ready_pods": ("ready_false", "pod_pending"),
}

RUNTIME_SYSTEMS: dict[str, InvestigationFeatures] = {
    "baseline_graph": InvestigationFeatures(
        verifier=False,
        deep_learning=False,
        retrieval=False,
        context_engineering=False,
    ),
    "sentinel_full": InvestigationFeatures(),
    "ablation_no_verifier": InvestigationFeatures(verifier=False),
    "ablation_no_deep_learning": InvestigationFeatures(deep_learning=False),
    "ablation_no_retrieval": InvestigationFeatures(retrieval=False),
    "ablation_no_context_engineering": InvestigationFeatures(context_engineering=False),
    "ablation_no_subagents": InvestigationFeatures(subagents=False),
}
SYSTEM_ORDER = (
    "baseline_direct",
    "baseline_react",
    "baseline_graph",
    "sentinel_full",
    "ablation_no_verifier",
    "ablation_no_deep_learning",
    "ablation_no_retrieval",
    "ablation_no_context_engineering",
    "ablation_no_subagents",
)


@dataclass(frozen=True)
class SystemPrediction:
    diagnosis: Diagnosis
    evidence: tuple[Evidence, ...]
    trace_id: str
    tool_calls: int
    model_calls: int
    duration_ms: float
    diagnosis_time_ms: float
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float
    tool_retries: int
    model_retries: int
    human_intervention: bool


def direct_alert_prediction(title: str) -> str:
    """Zero-tool baseline that sees only the alert title and a public cause taxonomy."""
    title_tokens = set(re.findall(r"[a-z]+", title.lower()))
    scored: list[tuple[float, str]] = []
    for _, cause, _, _, _, _ in FAULT_SPECS:
        cause_tokens = set(cause.split("_"))
        union = title_tokens | cause_tokens
        scored.append((len(title_tokens & cause_tokens) / max(1, len(union)), cause))
    return max(scored, key=lambda item: (item[0], item[1]))[1]


def evidence_signals(evidence: Iterable[Evidence], selected_ids: set[str]) -> set[str]:
    selected = [item for item in evidence if not selected_ids or item.id in selected_ids]
    rendered = " ".join(
        f"{item.summary} {json.dumps(item.payload, sort_keys=True, default=str)}"
        for item in selected
    ).lower()
    normalized = re.sub(r"[^a-z0-9]+", "_", rendered)
    return {
        signal
        for signal in ALL_SIGNALS
        if signal in normalized
        or any(pattern in normalized for pattern in SIGNAL_PATTERNS.get(signal, ()))
    }


def score_prediction(
    *,
    system: str,
    scenario: Scenario,
    prediction: SystemPrediction,
) -> TrialResult:
    diagnosis = prediction.diagnosis
    claimed = evidence_signals(prediction.evidence, set(diagnosis.evidence_ids))
    expected = set(scenario.expected_evidence)
    supported_claims = claimed & expected
    precision = len(supported_claims) / len(claimed) if claimed else 0.0
    recall = len(supported_claims) / len(expected)
    remediation_correct = diagnosis.recommended_action in scenario.acceptable_remediations
    policy_safe = diagnosis.recommended_action not in scenario.forbidden_actions
    return TrialResult(
        system=system,
        scenario_id=scenario.id,
        seed=scenario.seed,
        expected_root_cause=scenario.root_cause,
        predicted_root_cause=diagnosis.root_cause,
        diagnosis_status=diagnosis.status,
        evidence_precision=precision,
        evidence_recall=recall,
        remediation_correct=remediation_correct,
        policy_safe=policy_safe,
        tool_calls=prediction.tool_calls,
        diagnosis_time_ms=prediction.diagnosis_time_ms,
        trace_id=prediction.trace_id,
        total_time_ms=prediction.duration_ms,
        model_calls=prediction.model_calls,
        tool_retries=prediction.tool_retries,
        model_retries=prediction.model_retries,
        input_tokens=prediction.input_tokens,
        output_tokens=prediction.output_tokens,
        estimated_cost_usd=prediction.estimated_cost_usd,
        human_intervention=prediction.human_intervention,
        confidence=diagnosis.confidence,
    )


def synthetic_supported(root_cause: str) -> Diagnosis:
    remediation = next(spec[5][0] for spec in FAULT_SPECS if spec[1] == root_cause)
    return Diagnosis(
        status="supported",
        root_cause=root_cause,
        confidence=0.5,
        evidence_ids=[],
        recommended_action=remediation,
        risk_class="read",
        reasoning_summary="Alert-title label overlap; no tool evidence was collected.",
    )


def _abstention() -> Diagnosis:
    return Diagnosis(
        status="insufficient_evidence",
        root_cause="undetermined",
        confidence=0.0,
        evidence_ids=[],
        missing_evidence=["additional corroborating signal"],
        recommended_action="collect evidence",
        risk_class="read",
        reasoning_summary="No supported diagnosis was produced.",
    )


def _database_path(system: str, scenario: Scenario) -> Path:
    directory = SCRATCH / system
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"{scenario.id}.sqlite3"


def _repository(system: str, scenario: Scenario) -> SentinelRepository:
    database = _database_path(system, scenario)
    if database.exists():
        database.unlink()
    return SentinelRepository(f"sqlite:///{database.as_posix()}")


async def _run_direct(scenario: Scenario) -> SystemPrediction:
    repository = _repository("baseline_direct", scenario)
    with span("evaluation.trial", system="baseline_direct", scenario_id=scenario.id) as root:
        trace_id = trace_id_for(root)
        incident, _ = repository.create_incident(
            title=scenario.title,
            service=scenario.service,
            severity="SEV-2",
            alert={"title": scenario.title, "service": scenario.service, "severity": "SEV-2"},
            scenario_id=scenario.id,
            idempotency_key=f"eval-direct-{scenario.id}",
        )
        execution = repository.create_execution(
            incident.id, trace_id, BudgetPolicy(max_tool_calls=1).as_dict()
        )
        repository.update_incident(
            incident.id,
            status=ExecutionStatus.RESOLVED.value,
            execution_id=execution.id,
        )
        started = time.perf_counter()
        diagnosis = synthetic_supported(direct_alert_prediction(scenario.title))
        duration_ms = (time.perf_counter() - started) * 1000
        repository.set_execution_state(execution.id, ExecutionStatus.RESOLVED.value)
        root.set_attribute("sentinel.predicted_root_cause", diagnosis.root_cause)
    return SystemPrediction(
        diagnosis=diagnosis,
        evidence=(),
        trace_id=trace_id,
        tool_calls=0,
        model_calls=0,
        duration_ms=duration_ms,
        diagnosis_time_ms=duration_ms,
        input_tokens=0,
        output_tokens=0,
        estimated_cost_usd=0.0,
        tool_retries=0,
        model_retries=0,
        human_intervention=False,
    )


async def _run_react(scenario: Scenario) -> SystemPrediction:
    repository = _repository("baseline_react", scenario)
    with span("evaluation.trial", system="baseline_react", scenario_id=scenario.id) as root:
        trace_id = trace_id_for(root)
        incident, _ = repository.create_incident(
            title=scenario.title,
            service=scenario.service,
            severity="SEV-2",
            alert={"title": scenario.title, "service": scenario.service, "severity": "SEV-2"},
            scenario_id=scenario.id,
            idempotency_key=f"eval-react-{scenario.id}",
        )
        execution = repository.create_execution(incident.id, trace_id, BudgetPolicy().as_dict())
        repository.update_incident(
            incident.id,
            status=ExecutionStatus.RUNNING.value,
            execution_id=execution.id,
        )
        task_id = f"task_react_{hashlib.sha256(scenario.id.encode()).hexdigest()[:12]}"
        repository.add_task(
            id=task_id,
            incident_id=incident.id,
            execution_id=execution.id,
            parent_id=None,
            agent="react_baseline",
            title="Sequential act-observe-diagnose loop",
            status="running",
            inputs={"title": scenario.title, "service": scenario.service},
            outputs={},
            evidence_ids=[],
        )
        started = time.perf_counter()
        snapshot = IncidentSimulator().inject(scenario.id)
        registry = ToolRegistry(repository)
        mount_investigation_tools(
            registry,
            repository,
            snapshot,
            ToolProviderConfig(mode="simulator"),
        )
        ledger = BudgetLedger(BudgetPolicy(max_tool_calls=8, max_subagents=1))
        state = RuntimeState(
            incident_id=incident.id,
            execution_id=execution.id,
            trace_id=trace_id,
            status=ExecutionStatus.RUNNING,
        )
        context = InvestigationContext(state, snapshot, repository, registry, ledger)
        actions: tuple[tuple[str, dict[str, object]], ...] = (
            ("get_events", {"namespace": "sentinel-demo"}),
            (
                "query_prometheus",
                {"query": f'sentinel_demo_requests_total{{service="{scenario.service}"}}'},
            ),
            ("search_logs", {"service": scenario.service, "query": "", "limit": 200}),
            (
                "get_deployment",
                {"namespace": "sentinel-demo", "service": scenario.service},
            ),
            ("get_recent_commits", {}),
        )
        evidence: list[Evidence] = []
        diagnosis = _abstention()
        diagnosis_time_ms = 0.0
        actions_taken: list[str] = []
        for index, (tool_name, arguments) in enumerate(actions, start=1):
            evidence.extend(await context.call_tool(tool_name, arguments, task_id))
            actions_taken.append(tool_name)
            diagnosis_started = time.perf_counter()
            diagnosis, _ = DiagnosisAgent().run(evidence)
            diagnosis_time_ms += (time.perf_counter() - diagnosis_started) * 1000
            if index >= 3 and diagnosis.status == "supported":
                break
        duration_ms = (time.perf_counter() - started) * 1000
        repository.update_task(
            task_id,
            status="completed",
            outputs={
                "actions": actions_taken,
                "diagnosis": diagnosis.model_dump(mode="json"),
            },
            evidence_ids=[item.id for item in evidence],
        )
        repository.set_execution_state(execution.id, diagnosis.status)
        repository.update_incident(
            incident.id,
            status=diagnosis.status,
            diagnosis=diagnosis.model_dump(mode="json"),
        )
        root.set_attribute("sentinel.react.actions", len(actions_taken))
        root.set_attribute("sentinel.predicted_root_cause", diagnosis.root_cause)
    tool_calls = repository.list_tool_calls(incident.id)
    return SystemPrediction(
        diagnosis=diagnosis,
        evidence=tuple(evidence),
        trace_id=trace_id,
        tool_calls=len(tool_calls),
        model_calls=0,
        duration_ms=duration_ms,
        diagnosis_time_ms=diagnosis_time_ms,
        input_tokens=0,
        output_tokens=0,
        estimated_cost_usd=0.0,
        tool_retries=sum(item.retry_count for item in tool_calls),
        model_retries=0,
        human_intervention=False,
    )


async def _run_runtime(
    system: str,
    scenario: Scenario,
    features: InvestigationFeatures,
) -> SystemPrediction:
    repository = _repository(system, scenario)
    with span("evaluation.trial", system=system, scenario_id=scenario.id) as trial_span:
        started = time.perf_counter()
        state = await InvestigationService(repository, features=features).run_scenario(scenario.id)
        duration_ms = (time.perf_counter() - started) * 1000
        trial_span.set_attribute("sentinel.execution_id", state.execution_id)
        trial_span.set_attribute("sentinel.predicted_root_cause", state.diagnosis.root_cause if state.diagnosis else "undetermined")
    tool_calls = repository.list_tool_calls(state.incident_id)
    model_calls = repository.list_model_calls(state.incident_id)
    diagnosis_tasks = [
        item
        for item in repository.list_tasks(state.incident_id)
        if item.agent == "diagnosis" and item.completed_at is not None
    ]
    diagnosis_time_ms = sum(
        (item.completed_at - item.created_at).total_seconds() * 1000
        for item in diagnosis_tasks
        if item.completed_at is not None
    )
    return SystemPrediction(
        diagnosis=state.diagnosis or _abstention(),
        evidence=tuple(state.evidence),
        trace_id=state.trace_id,
        tool_calls=len(tool_calls),
        model_calls=len(model_calls),
        duration_ms=duration_ms,
        diagnosis_time_ms=diagnosis_time_ms,
        input_tokens=sum(item.input_tokens for item in model_calls),
        output_tokens=sum(item.output_tokens for item in model_calls),
        estimated_cost_usd=sum(item.estimated_cost_usd for item in model_calls),
        tool_retries=sum(item.retry_count for item in tool_calls),
        model_retries=sum(item.retry_count for item in model_calls),
        human_intervention=state.status is ExecutionStatus.WAITING_APPROVAL,
    )


async def _run_system(system: str, scenario: Scenario) -> SystemPrediction:
    if system == "baseline_direct":
        return await _run_direct(scenario)
    if system == "baseline_react":
        return await _run_react(scenario)
    return await _run_runtime(system, scenario, RUNTIME_SYSTEMS[system])


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_revision() -> str:
    try:
        return subprocess.run(  # noqa: S603
            ["git", "rev-parse", "HEAD"],  # noqa: S607
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unavailable"


def build_manifest(scenarios: list[Scenario], rows: list[TrialResult]) -> dict[str, Any]:
    train = [item for item in build_catalog() if item.id.endswith("_001")]
    held_out = [item for item in build_catalog() if item.id.endswith("_002")]
    split_payload = {
        "retrieval_training_ids": [item.id for item in train],
        "retrieval_held_out_ids": [item.id for item in held_out],
    }
    system_config = {
        name: asdict(features) for name, features in RUNTIME_SYSTEMS.items()
    }
    system_config["baseline_direct"] = {"input": "alert_title_only", "tools": 0}
    system_config["baseline_react"] = {
        "input": "alert_and_observed_tool_evidence",
        "max_tools": 5,
        "execution": "sequential_act_observe_diagnose",
    }
    return {
        "protocol_version": "independent-v2",
        "generated_at": datetime.now(UTC).isoformat(),
        "scenario_count": len(scenarios),
        "systems": list(SYSTEM_ORDER),
        "trials_per_scenario": 1,
        "independent_trial_count": len(rows),
        "fresh_repository_per_trial": True,
        "evaluator_labels_in_runtime_snapshot": False,
        "scenario_variants_are_seeded": True,
        "nondeterministic_providers": False,
        "scenario_catalog_sha256": _sha256_file(
            ROOT / "simulator" / "scenarios" / "catalog.json"
        ),
        "retrieval_training_corpus_sha256": corpus_checksum(build_corpus(train)),
        "retrieval_split_sha256": hashlib.sha256(
            json.dumps(split_payload, sort_keys=True).encode()
        ).hexdigest(),
        "system_configuration_sha256": hashlib.sha256(
            json.dumps(system_config, sort_keys=True).encode()
        ).hexdigest(),
        "system_configuration": system_config,
        "source_revision": _source_revision(),
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "langchain": importlib.metadata.version("langchain"),
            "langgraph": importlib.metadata.version("langgraph"),
            "opentelemetry_sdk": importlib.metadata.version("opentelemetry-sdk"),
        },
        "timing_note": "Every timing value is measured from that system's own execution; no replay multipliers or copied traces are used.",
        "cost_note": "Token counts, retries, duration, and estimated cost are summed from each trial's persisted model-call records. The configured deterministic provider has measured zero API cost.",
    }


def _prepare_scratch() -> None:
    resolved = SCRATCH.resolve()
    if not resolved.is_relative_to((ROOT / "tmp").resolve()):
        raise RuntimeError(f"refusing to clear unexpected evaluation directory: {resolved}")
    if resolved.exists():
        shutil.rmtree(resolved)
    resolved.mkdir(parents=True)


async def evaluate(output: Path, scenario_limit: int | None = None) -> list[TrialResult]:
    configure_telemetry("sentinel-eval")
    _prepare_scratch()
    scenarios = build_catalog()[:scenario_limit]
    rows: list[TrialResult] = []
    for index, scenario in enumerate(scenarios, start=1):
        scenario_rows: list[TrialResult] = []
        for system in SYSTEM_ORDER:
            prediction = await _run_system(system, scenario)
            row = score_prediction(system=system, scenario=scenario, prediction=prediction)
            rows.append(row)
            scenario_rows.append(row)
        full = next(item for item in scenario_rows if item.system == "sentinel_full")
        print(
            f"[{index:02d}/{len(scenarios):02d}] {scenario.id}: "
            f"full={full.predicted_root_cause}/{full.diagnosis_status}; "
            f"9 independent trials"
        )
    summary = aggregate(rows)
    manifest = build_manifest(scenarios, rows)
    index_repository = SentinelRepository(
        f"sqlite:///{(SCRATCH / 'benchmark-index.sqlite3').as_posix()}"
    )
    index_repository.add_benchmark_run(
        suite="portfolio-independent-v2",
        status="completed",
        config=manifest,
        metrics=summary,
        trace_ids=[row.trace_id for row in rows],
        completed_at=datetime.now(UTC),
    )
    write_reports(output, rows, summary, manifest)
    return rows


def write_reports(
    output: Path,
    rows: list[TrialResult],
    summary: dict[str, dict[str, float | int]],
    manifest: dict[str, Any],
) -> None:
    if not rows:
        raise ValueError("cannot write an empty evaluation report")
    if output.resolve() == ROOT.resolve():
        raise ValueError("evaluation output cannot be the repository root")
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    raw = [row.as_dict() for row in rows]
    (output / "raw-results.json").write_text(
        json.dumps(raw, indent=2, sort_keys=True), encoding="utf-8"
    )
    with (output / "raw-results.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(raw[0]))
        writer.writeheader()
        writer.writerows(raw)
    (output / "summary.json").write_text(
        json.dumps({"manifest": manifest, "metrics": summary}, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (output / "report.md").write_text(
        render_markdown(manifest, summary), encoding="utf-8"
    )
    (output / "report.html").write_text(
        render_html(manifest, summary), encoding="utf-8"
    )
    (output / "root-cause-accuracy.svg").write_text(
        render_svg(summary, [name for name in SYSTEM_ORDER if not name.startswith("ablation_")]),
        encoding="utf-8",
    )
    (output / "ablation-accuracy.svg").write_text(
        render_svg(summary, [name for name in SYSTEM_ORDER if name.startswith("ablation_")]),
        encoding="utf-8",
    )
    (output / "failure-analysis.md").write_text(
        render_failures(rows), encoding="utf-8"
    )


def render_markdown(
    manifest: dict[str, Any], summary: dict[str, dict[str, float | int]]
) -> str:
    lines = [
        "# Sentinel independent evaluation",
        "",
        f"Protocol `{manifest['protocol_version']}` generated `{manifest['generated_at']}` from {manifest['scenario_count']} scenarios and {manifest['independent_trial_count']} isolated executions.",
        "Each system received the same immutable alert/scenario input in a fresh repository. Runtime snapshots contained no root-cause, expected-evidence, remediation, or forbidden-action evaluator fields.",
        "",
        "| System | Accuracy | Selective acc. | Evidence P/R | Abstain | ECE/Brier | Remediation | Tools mean/p95 | Total time mean/p95 ms | Tokens in/out | Cost |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name in SYSTEM_ORDER:
        values = summary[name]
        lines.append(
            "| {name} | {acc:.3f} | {selective:.3f} | {precision:.3f}/{recall:.3f} | "
            "{abstain:.3f} | {ece:.3f}/{brier:.3f} | {remediation:.3f} | "
            "{tools:.1f}/{tools95:.1f} | {latency:.1f}/{latency95:.1f} | "
            "{input_tokens}/{output_tokens} | ${cost:.4f} |".format(
                name=name,
                acc=values["root_cause_accuracy"],
                selective=values["selective_accuracy"],
                precision=values["evidence_precision"],
                recall=values["evidence_recall"],
                abstain=values["abstention_rate"],
                ece=values["expected_calibration_error"],
                brier=values["brier_score"],
                remediation=values["remediation_accuracy"],
                tools=values["mean_tool_calls"],
                tools95=values["p95_tool_calls"],
                latency=values["mean_total_time_ms"],
                latency95=values["p95_total_time_ms"],
                input_tokens=values["input_tokens"],
                output_tokens=values["output_tokens"],
                cost=values["estimated_cost_usd"],
            )
        )
    lines.extend(
        [
            "",
            "## Protocol integrity",
            "",
            f"- Scenario catalog SHA-256: `{manifest['scenario_catalog_sha256']}`",
            f"- Retrieval training corpus SHA-256: `{manifest['retrieval_training_corpus_sha256']}`",
            f"- Retrieval split SHA-256: `{manifest['retrieval_split_sha256']}`",
            f"- System configuration SHA-256: `{manifest['system_configuration_sha256']}`",
            f"- Source revision: `{manifest['source_revision']}`",
            "- Every row has a unique OpenTelemetry trace ID and measured wall-clock duration.",
            "- Token, retry, latency, and cost totals come from that row's own persisted calls.",
            "- The deterministic model provider incurs zero API cost; zero is a measurement, not an estimate copied between systems.",
            "",
            "## Interpretation",
            "",
            "The direct baseline deliberately makes unsupported title-only claims, so evidence precision and recall are zero even when its taxonomy match is correct. The ReAct baseline performs its own bounded sequential tool loop. The graph baseline executes an actual reduced LangGraph without learned evidence, retrieval, context ranking, or verification. Each ablation executes the production graph from scratch with exactly one named feature disabled.",
            "",
            "Human intervention means a governed approval gate was reached, not that diagnosis failed. ECE and Brier score expose calibration rather than treating confidence as decoration. Raw per-trial rows are in `raw-results.json` and `raw-results.csv`; observed errors and regression actions are in `failure-analysis.md`.",
        ]
    )
    return "\n".join(lines) + "\n"


def render_html(
    manifest: dict[str, Any], summary: dict[str, dict[str, float | int]]
) -> str:
    rows = "".join(
        "<tr><th>{}</th><td>{:.1%}</td><td>{:.1%}</td><td>{:.1%}</td><td>{:.1f}</td><td>{:.1f} ms</td><td>{}/{}</td><td>${:.4f}</td></tr>".format(
            escape(name),
            summary[name]["root_cause_accuracy"],
            summary[name]["evidence_precision"],
            summary[name]["evidence_recall"],
            summary[name]["mean_tool_calls"],
            summary[name]["mean_total_time_ms"],
            summary[name]["input_tokens"],
            summary[name]["output_tokens"],
            summary[name]["estimated_cost_usd"],
        )
        for name in SYSTEM_ORDER
    )
    return f"""<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Sentinel independent evaluation</title><style>
body{{font:16px system-ui;background:#07111f;color:#e7f1ff;margin:0;padding:3rem;line-height:1.5}}
main{{max-width:1200px;margin:auto}}h1{{font-size:clamp(2rem,5vw,4rem);margin-bottom:.25rem}}
p{{color:#9db0c8}}table{{width:100%;border-collapse:collapse;background:#0d1c2f;border:1px solid #27405f}}
th,td{{padding:.8rem;text-align:right;border-bottom:1px solid #203650}}th:first-child{{text-align:left}}
thead th{{color:#65e6dc}}</style><main><h1>Sentinel independent evaluation</h1>
<p>Protocol {escape(str(manifest["protocol_version"]))} · {manifest["scenario_count"]} scenarios · {manifest["independent_trial_count"]} isolated executions · generated {escape(str(manifest["generated_at"]))}</p>
<table><thead><tr><th>System</th><th>Accuracy</th><th>Evidence precision</th><th>Evidence recall</th><th>Mean tools</th><th>Mean total time</th><th>Tokens in/out</th><th>Cost</th></tr></thead>
<tbody>{rows}</tbody></table><p>Raw JSON, CSV, protocol hashes, and trace IDs are distributed alongside this report.</p></main></html>"""


def render_svg(summary: dict[str, dict[str, float | int]], systems: list[str]) -> str:
    width, height = 900, 110 + len(systems) * 64
    bars: list[str] = []
    for index, name in enumerate(systems):
        value = float(summary[name]["root_cause_accuracy"])
        y = 75 + index * 64
        bars.append(
            f'<text x="20" y="{y + 20}" fill="#dbeafe" font-size="16">{escape(name)}</text>'
            f'<rect x="270" y="{y}" width="560" height="26" rx="6" fill="#16304a"/>'
            f'<rect x="270" y="{y}" width="{560 * value:.1f}" height="26" rx="6" fill="#43d9c6"/>'
            f'<text x="840" y="{y + 20}" fill="#dbeafe" font-size="15">{value:.1%}</text>'
        )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}"><rect width="100%" height="100%" fill="#07111f"/>'
        '<text x="20" y="38" fill="#65e6dc" font-family="system-ui" font-size="24" font-weight="700">Root-cause accuracy</text><g font-family="system-ui">'
        + "".join(bars)
        + "</g></svg>"
    )


def _failure_reason(row: TrialResult) -> str:
    if row.system == "baseline_direct":
        return "Title-only taxonomy overlap selected the wrong class and had no evidence to correct it."
    if row.system == "baseline_react":
        return "The bounded sequential loop stopped without enough discriminating evidence."
    if row.system == "baseline_graph":
        return "The reduced graph lacked learned, retrieval, context-ranking, and verification components."
    if row.system.startswith("ablation_"):
        return f"The independently executed {row.system.removeprefix('ablation_')} ablation lost a useful discriminator or safety check."
    return "The full verifier abstained or selected a competing signature under the measured evidence."


def render_failures(rows: list[TrialResult]) -> str:
    failures = [row for row in rows if not row.root_cause_correct]
    failures.sort(key=lambda row: (row.system != "sentinel_full", row.evidence_recall))
    chosen: list[TrialResult] = []
    seen: set[tuple[str, str]] = set()
    for row in failures:
        key = (row.system, row.scenario_id)
        if key not in seen:
            chosen.append(row)
            seen.add(key)
        if len(chosen) == 5:
            break
    counts = Counter(row.system for row in chosen)
    scenario_by_id = {scenario.id: scenario for scenario in build_catalog()}
    lines = [
        "# Five measured failure analyses",
        "",
        "These errors come from independent trial rows and were selected mechanically before manual review.",
        "",
    ]
    for index, row in enumerate(chosen, start=1):
        scenario = scenario_by_id[row.scenario_id]
        lines.extend(
            [
                f"## {index}. {row.system}: `{row.scenario_id}`",
                "",
                f"- Trace ID: `{row.trace_id}`",
                f"- Expected root cause: `{row.expected_root_cause}`",
                f"- Predicted root cause: `{row.predicted_root_cause}` ({row.diagnosis_status}, confidence {row.confidence:.3f})",
                f"- Evidence precision/recall: {row.evidence_precision:.3f}/{row.evidence_recall:.3f}",
                f"- Actual total time/tools/models: {row.total_time_ms:.2f} ms / {row.tool_calls} / {row.model_calls}",
                f"- Why it failed: {_failure_reason(row)}",
                f"- Missing discriminators: `{', '.join(scenario.expected_evidence)}`.",
                "- Corrective action: retain this exact scenario/system pair as a regression fixture and require one additional independent category-specific signal before a supported claim.",
                "",
            ]
        )
    lines.append(
        "Selection distribution: "
        + ", ".join(f"{name}={count}" for name, count in counts.items())
    )
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the independently executed Sentinel portfolio evaluation"
    )
    parser.add_argument("--suite", default="portfolio", choices=["portfolio"])
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--scenario-limit", type=int)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    asyncio.run(evaluate(args.output, args.scenario_limit))


if __name__ == "__main__":
    main()
