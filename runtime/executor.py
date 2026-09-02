from __future__ import annotations

import secrets
from collections.abc import Awaitable, Callable

from persistence.repository import SentinelRepository
from runtime.budgets import BudgetExceeded, BudgetLedger, BudgetPolicy
from runtime.checkpoints import CheckpointStore
from runtime.state import ExecutionStatus, RuntimeState
from runtime.tracing import INCIDENTS, span

Workflow = Callable[[RuntimeState, BudgetLedger], Awaitable[RuntimeState]]


class RuntimeExecutor:
    def __init__(
        self,
        repository: SentinelRepository,
        budget_policy: BudgetPolicy | None = None,
    ) -> None:
        self.repository = repository
        self.budget_policy = budget_policy or BudgetPolicy()
        self.checkpoints = CheckpointStore(repository)

    async def execute(self, incident_id: str, workflow: Workflow) -> RuntimeState:
        trace_id = secrets.token_hex(16)
        execution = self.repository.create_execution(
            incident_id, trace_id, self.budget_policy.as_dict()
        )
        self.repository.update_incident(
            incident_id, status=ExecutionStatus.RUNNING.value, execution_id=execution.id
        )
        state = RuntimeState(
            incident_id=incident_id,
            execution_id=execution.id,
            trace_id=trace_id,
            status=ExecutionStatus.RUNNING,
        )
        state = self.checkpoints.save(state)
        ledger = BudgetLedger(self.budget_policy)
        with span("incident.execute", incident_id=incident_id, execution_id=execution.id):
            try:
                state = await workflow(state, ledger)
                state = self.checkpoints.save(state)
            except BudgetExceeded as exc:
                state = state.model_copy(
                    update={
                        "status": ExecutionStatus.HUMAN_ESCALATION,
                        "metadata": {**state.metadata, "termination_reason": exc.reason},
                    }
                )
                state = self.checkpoints.save(state)
            except Exception:
                failed = state.model_copy(update={"status": ExecutionStatus.FAILED_SYSTEM})
                self.checkpoints.save(failed)
                self.repository.set_execution_state(
                    execution.id, ExecutionStatus.FAILED_SYSTEM.value
                )
                self.repository.update_incident(
                    incident_id, status=ExecutionStatus.FAILED_SYSTEM.value
                )
                INCIDENTS.labels(status=ExecutionStatus.FAILED_SYSTEM.value).inc()
                raise
        self.repository.set_execution_state(execution.id, state.status.value)
        self.repository.update_incident(
            incident_id,
            status=state.status.value,
            diagnosis=state.diagnosis.model_dump(mode="json") if state.diagnosis else None,
        )
        INCIDENTS.labels(status=state.status.value).inc()
        return state

    def resume(self, execution_id: str) -> RuntimeState:
        state = self.checkpoints.load(execution_id)
        if state is None:
            raise KeyError(f"no checkpoint for execution: {execution_id}")
        return state
