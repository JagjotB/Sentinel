from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Never

import pytest
from pydantic import BaseModel

from agents.service import InvestigationService
from mcp.contracts import (
    ErrorCode,
    PermissionClass,
    ToolContext,
    ToolFailure,
    ToolServer,
    ToolSpec,
)
from persistence.repository import ConflictError, SentinelRepository
from runtime.budgets import BudgetLedger, BudgetPolicy
from runtime.tool_registry import ToolRegistry
from runtime.worker import InvestigationWorker


def create_incident(repository: SentinelRepository, key: str = "queue-test") -> str:
    incident, _ = repository.create_incident(
        title="Payments memory pressure",
        service="payments",
        severity="SEV-2",
        alert={"memory": 0.99},
        idempotency_key=key,
        scenario_id="oom_killed_001",
    )
    repository.update_incident(incident.id, status="queued")
    return incident.id


def test_expired_work_lease_is_reclaimed_and_stale_owner_is_denied(tmp_path: Path) -> None:
    repository = SentinelRepository(f"sqlite:///{tmp_path / 'leases.db'}")
    incident_id = create_incident(repository)
    item, created = repository.enqueue_investigation(
        incident_id,
        scenario_id="oom_killed_001",
        provider_mode="simulator",
    )
    assert created is True
    claimed_at = datetime.now(UTC)
    first = repository.claim_work("worker-a", lease_seconds=1, now=claimed_at)
    assert first is not None
    assert repository.claim_work("worker-b", lease_seconds=1, now=claimed_at) is None

    reclaimed = repository.claim_work(
        "worker-b",
        lease_seconds=30,
        now=claimed_at + timedelta(seconds=2),
    )
    assert reclaimed is not None
    assert reclaimed.id == item.id
    assert reclaimed.attempts == 2
    with pytest.raises(ConflictError):
        repository.complete_work(item.id, "worker-a", execution_id="stale")


async def test_worker_completes_real_investigation_and_records_execution(tmp_path: Path) -> None:
    repository = SentinelRepository(f"sqlite:///{tmp_path / 'worker.db'}")
    incident_id = create_incident(repository, "worker-success")
    queued, _ = repository.enqueue_investigation(
        incident_id,
        scenario_id="oom_killed_001",
        provider_mode="simulator",
    )
    worker = InvestigationWorker(
        repository,
        lambda _: InvestigationService(repository),
        worker_id="worker-test",
        lease_seconds=10,
    )

    completed = await worker.run_once()

    assert completed is not None
    assert completed.id == queued.id
    assert completed.status == "completed"
    assert completed.execution_id
    assert repository.get_incident(incident_id).execution_id == completed.execution_id


async def test_worker_exhaustion_marks_work_and_incident_failed(tmp_path: Path) -> None:
    repository = SentinelRepository(f"sqlite:///{tmp_path / 'worker-fail.db'}")
    incident_id = create_incident(repository, "worker-failure")
    queued, _ = repository.enqueue_investigation(
        incident_id,
        scenario_id="oom_killed_001",
        provider_mode="simulator",
        max_attempts=1,
    )

    class FailingService:
        async def run_incident(self, _: str) -> Never:
            raise RuntimeError("provider unavailable")

    worker = InvestigationWorker(
        repository,
        lambda _: FailingService(),
        worker_id="worker-test",
    )
    failed = await worker.run_once()

    assert failed is not None
    assert failed.id == queued.id
    assert failed.status == "failed"
    assert failed.last_error == "provider unavailable"
    assert repository.get_incident(incident_id).status == "failed_system"


class ToolRequest(BaseModel):
    value: int


async def test_registry_applies_tool_retries_and_persists_count(tmp_path: Path) -> None:
    repository = SentinelRepository(f"sqlite:///{tmp_path / 'tool-retries.db'}")
    incident_id = create_incident(repository, "tool-retry")
    execution = repository.create_execution(incident_id, "b" * 24, BudgetPolicy().as_dict())
    attempts = 0

    async def flaky(_: ToolRequest, __: ToolContext) -> dict[str, object]:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise ToolFailure(ErrorCode.PROVIDER_UNAVAILABLE, "retry me", retryable=True)
        return {"ok": True}

    server = ToolServer()
    server.register(
        ToolSpec(
            "flaky",
            ToolRequest,
            PermissionClass.READ,
            flaky,
            max_retries=1,
        )
    )
    registry = ToolRegistry(repository)
    registry.mount(server)
    context = ToolContext(
        incident_id=incident_id,
        execution_id=execution.id,
        auth_token="sentinel-tool-token",  # noqa: S106 - local test credential
        trace_id="b" * 24,
    )

    result = await registry.call(
        "flaky",
        {"value": 1},
        context,
        BudgetLedger(BudgetPolicy()),
    )
    calls = repository.list_tool_calls(incident_id)

    assert result.data == {"ok": True}
    assert attempts == 2
    assert calls[0].retry_count == 1
    assert calls[0].status == "succeeded"


async def test_registry_circuit_breaker_stops_repeated_provider_calls(tmp_path: Path) -> None:
    repository = SentinelRepository(f"sqlite:///{tmp_path / 'tool-breaker.db'}")
    incident_id = create_incident(repository, "tool-breaker")
    execution = repository.create_execution(incident_id, "c" * 24, BudgetPolicy().as_dict())
    provider_attempts = 0

    async def unavailable(_: ToolRequest, __: ToolContext) -> dict[str, object]:
        nonlocal provider_attempts
        provider_attempts += 1
        raise ToolFailure(ErrorCode.PROVIDER_UNAVAILABLE, "offline", retryable=True)

    server = ToolServer()
    server.register(
        ToolSpec(
            "unavailable",
            ToolRequest,
            PermissionClass.READ,
            unavailable,
            max_retries=0,
        )
    )
    registry = ToolRegistry(repository)
    registry.mount(server)
    context = ToolContext(
        incident_id=incident_id,
        execution_id=execution.id,
        auth_token="sentinel-tool-token",  # noqa: S106 - local test credential
        trace_id="c" * 24,
    )
    ledger = BudgetLedger(BudgetPolicy(max_identical_tool_calls=10))

    for _ in range(4):
        with pytest.raises(ToolFailure):
            await registry.call("unavailable", {"value": 1}, context, ledger)

    calls = repository.list_tool_calls(incident_id)
    assert provider_attempts == 3
    assert calls[-1].status == "circuit_open"
