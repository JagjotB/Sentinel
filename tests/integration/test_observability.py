from __future__ import annotations

from pathlib import Path

from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from prometheus_client import generate_latest

from agents.service import InvestigationService
from persistence.repository import SentinelRepository
from runtime.budgets import BudgetLedger
from runtime.executor import RuntimeExecutor
from runtime.state import ExecutionStatus, RuntimeState
from runtime.tracing import configure_telemetry, force_flush_telemetry
from runtime.worker import InvestigationWorker


async def test_incident_emits_one_correlated_trace_and_all_metric_families(
    tmp_path: Path,
) -> None:
    exporter = InMemorySpanExporter()
    configure_telemetry("sentinel-test", exporter=exporter)
    exporter.clear()
    repository = SentinelRepository(f"sqlite:///{tmp_path / 'observability.db'}")

    state = await InvestigationService(repository).run_scenario("oom_killed_001")
    assert force_flush_telemetry()

    finished = exporter.get_finished_spans()
    names = {item.name for item in finished}
    trace_ids = {f"{item.context.trace_id:032x}" for item in finished}
    graph_nodes = {
        str(item.attributes.get("node"))
        for item in finished
        if item.name == "agent.graph.node"
    }
    assert state.trace_id in trace_ids
    assert trace_ids == {state.trace_id}
    assert {
        "incident.execute",
        "agent.graph.node",
        "model.call",
        "tool.call",
    }.issubset(names)
    assert {
        "initialize",
        "collect_evidence",
        "diagnose",
        "verify",
        "remediate",
    }.issubset(graph_nodes)

    metrics = generate_latest().decode()
    for family in (
        "sentinel_incidents_total",
        "sentinel_incident_seconds",
        "sentinel_tool_calls_total",
        "sentinel_tool_call_seconds",
        "sentinel_model_calls_total",
        "sentinel_model_tokens_total",
        "sentinel_model_cost_usd_total",
        "sentinel_model_call_seconds",
        "sentinel_diagnosis_seconds",
        "sentinel_retries_total",
        "sentinel_approvals_total",
        "sentinel_errors_total",
        "sentinel_work_items_total",
        "sentinel_abstentions_total",
        "sentinel_http_requests_total",
        "sentinel_http_request_seconds",
    ):
        assert family in metrics


async def test_resume_span_preserves_persisted_trace_id(tmp_path: Path) -> None:
    exporter = InMemorySpanExporter()
    configure_telemetry("sentinel-test", exporter=exporter)
    exporter.clear()
    repository = SentinelRepository(f"sqlite:///{tmp_path / 'resume-trace.db'}")
    incident, _ = repository.create_incident(
        title="trace continuity",
        service="checkout",
        severity="SEV-2",
        alert={"signal": "latency"},
        idempotency_key="trace-continuity",
    )
    executor = RuntimeExecutor(repository)

    async def interrupt(state: RuntimeState, _: BudgetLedger) -> RuntimeState:
        return state

    interrupted = await executor.execute(incident.id, interrupt)
    exporter.clear()

    async def finish(state: RuntimeState, _: BudgetLedger) -> RuntimeState:
        return state.model_copy(update={"status": ExecutionStatus.INSUFFICIENT_EVIDENCE})

    resumed = await RuntimeExecutor(repository).resume_execute(
        interrupted.execution_id, finish
    )
    assert force_flush_telemetry()

    resume_span = next(
        item for item in exporter.get_finished_spans() if item.name == "incident.resume"
    )
    assert resumed.trace_id == interrupted.trace_id
    assert f"{resume_span.context.trace_id:032x}" == interrupted.trace_id


async def test_worker_continues_trace_persisted_by_alert_ingestion(tmp_path: Path) -> None:
    exporter = InMemorySpanExporter()
    configure_telemetry("sentinel-test", exporter=exporter)
    exporter.clear()
    repository = SentinelRepository(f"sqlite:///{tmp_path / 'worker-trace.db'}")
    parent_trace_id = "a" * 32
    incident, _ = repository.create_incident(
        title="queued trace continuity",
        service="checkout",
        severity="SEV-2",
        alert={"signal": "errors"},
        scenario_id="oom_killed_001",
        idempotency_key="queued-trace-continuity",
    )
    repository.enqueue_investigation(
        incident.id,
        scenario_id=incident.scenario_id,
        provider_mode="simulator",
        parent_trace_id=parent_trace_id,
    )
    worker = InvestigationWorker(
        repository,
        lambda _: InvestigationService(repository),
        worker_id="trace-worker",
    )

    completed = await worker.run_once()
    assert completed is not None
    assert completed.execution_id is not None
    assert force_flush_telemetry()

    execution = repository.get_execution(completed.execution_id)
    correlated = [
        item
        for item in exporter.get_finished_spans()
        if item.name in {"worker.investigation", "incident.execute"}
    ]
    assert execution.trace_id == parent_trace_id
    assert {f"{item.context.trace_id:032x}" for item in correlated} == {parent_trace_id}
