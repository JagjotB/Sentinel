from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from persistence.repository import SentinelRepository
from runtime.budgets import BudgetLedger, BudgetPolicy
from runtime.executor import RuntimeExecutor
from runtime.model_router import (
    DeterministicProvider,
    ModelRequest,
    ModelResponse,
    ModelRouter,
)
from runtime.retries import CircuitBreaker, with_retries
from runtime.state import ExecutionStatus, RuntimeState


async def test_worker_interruption_resumes_from_durable_checkpoint(tmp_path: Path) -> None:
    repository = SentinelRepository(f"sqlite:///{tmp_path / 'recovery.db'}")
    incident, _ = repository.create_incident(
        title="worker recovery",
        service="worker",
        severity="SEV-2",
        alert={"test": "worker interruption"},
        idempotency_key="worker-recovery",
    )
    executor = RuntimeExecutor(repository)

    async def interrupted(state: RuntimeState, _: BudgetLedger) -> RuntimeState:
        executor.checkpoints.save(
            state.model_copy(update={"metadata": {"completed_stage": "evidence"}})
        )
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await executor.execute(incident.id, interrupted)
    checkpoint = repository.latest_checkpoint(repository.get_incident(incident.id).execution_id)
    assert checkpoint is not None

    async def continued(state: RuntimeState, _: BudgetLedger) -> RuntimeState:
        assert state.metadata["completed_stage"] == "evidence"
        return state.model_copy(update={"status": ExecutionStatus.INSUFFICIENT_EVIDENCE})

    recovered = await executor.resume_execute(checkpoint.execution_id, continued)
    assert recovered.status is ExecutionStatus.INSUFFICIENT_EVIDENCE
    assert recovered.checkpoint_sequence > checkpoint.sequence


async def test_tool_timeout_retries_then_succeeds() -> None:
    attempts = 0

    async def flaky() -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            await asyncio.sleep(0.03)
        return "ok"

    result, retries = await with_retries(
        flaky,
        retries=2,
        timeout_seconds=0.01,
        retryable=lambda exc: isinstance(exc, TimeoutError),
        base_delay=0.0,
    )
    assert result == "ok"
    assert retries == 1


async def test_circuit_breaker_opens_after_repeated_tool_failure() -> None:
    breaker = CircuitBreaker(failure_threshold=2, reset_after_seconds=60)

    async def unavailable() -> None:
        raise ConnectionError("provider unavailable")

    for _ in range(2):
        with pytest.raises(ConnectionError):
            await with_retries(
                unavailable,
                retries=0,
                timeout_seconds=0.1,
                retryable=lambda _: True,
                breaker=breaker,
            )
    with pytest.raises(RuntimeError, match="circuit breaker is open"):
        breaker.before_call()


class FailingProvider:
    def complete(self, request: ModelRequest, model: str) -> ModelResponse:
        del request, model
        raise ConnectionError("model provider unavailable")


def test_model_provider_failure_uses_auditable_local_fallback() -> None:
    router = ModelRouter(
        providers={"remote": FailingProvider(), "deterministic": DeterministicProvider()},
        routes={"diagnosis": ("remote", "unavailable-model")},
    )
    response = router.complete(
        ModelRequest(purpose="diagnosis", prompt="summarize evidence"),
        BudgetLedger(BudgetPolicy()),
    )
    assert response.provider == "deterministic"
    assert response.model == "sentinel-stub-fallback"
    assert response.retry_count == 1
