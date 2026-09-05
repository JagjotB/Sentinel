from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

from persistence.repository import SentinelRepository
from runtime.budgets import BudgetExceeded, BudgetLedger, BudgetPolicy
from runtime.checkpoints import CheckpointStore
from runtime.state import ExecutionStatus, RuntimeState
from runtime.tracing import (
    ABSTENTIONS,
    ERRORS,
    INCIDENT_LATENCY,
    INCIDENTS,
    span,
    trace_id_for,
)

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
        started = time.perf_counter()
        with span("incident.execute", incident_id=incident_id) as root_span:
            trace_id = trace_id_for(root_span)
            execution = self.repository.create_execution(
                incident_id, trace_id, self.budget_policy.as_dict()
            )
            root_span.set_attribute("sentinel.execution_id", execution.id)
            root_span.set_attribute("sentinel.trace_id", trace_id)
            self.repository.update_incident(
                incident_id, status=ExecutionStatus.RUNNING.value, execution_id=execution.id
            )
            state = RuntimeState(
                incident_id=incident_id,
                execution_id=execution.id,
                trace_id=trace_id,
                status=ExecutionStatus.RUNNING,
                metadata={
                    "budget_usage": BudgetLedger(self.budget_policy).snapshot(),
                    "budget_policy": self.budget_policy.as_dict(),
                },
            )
            state = self.checkpoints.save(state)
            ledger = BudgetLedger(self.budget_policy)
            try:
                state = await workflow(state, ledger)
                state = self._with_budget(state, ledger)
                state = self.checkpoints.save(state)
            except BudgetExceeded as exc:
                state = state.model_copy(
                    update={
                        "status": ExecutionStatus.HUMAN_ESCALATION,
                        "metadata": {
                            **state.metadata,
                            "termination_reason": exc.reason,
                            "budget_usage": ledger.snapshot(),
                        },
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
                ERRORS.labels(component="incident", code="failed_system").inc()
                raise
            finally:
                INCIDENT_LATENCY.labels(operation="execute").observe(
                    time.perf_counter() - started
                )
        self.repository.set_execution_state(execution.id, state.status.value)
        self.repository.update_incident(
            incident_id,
            status=state.status.value,
            diagnosis=state.diagnosis.model_dump(mode="json") if state.diagnosis else None,
        )
        INCIDENTS.labels(status=state.status.value).inc()
        self._record_abstention(state)
        return state

    def resume(self, execution_id: str) -> RuntimeState:
        state = self.checkpoints.load(execution_id)
        if state is None:
            raise KeyError(f"no checkpoint for execution: {execution_id}")
        return state

    async def resume_execute(self, execution_id: str, workflow: Workflow) -> RuntimeState:
        """Continue an interrupted execution from its latest durable checkpoint."""
        state = self.resume(execution_id)
        if state.status.terminal:
            return state
        execution = self.repository.get_execution(execution_id)
        policy = BudgetPolicy.from_dict(execution.budget)
        usage = state.metadata.get("budget_usage", {})
        ledger = BudgetLedger.from_snapshot(policy, usage if isinstance(usage, dict) else {})
        started = time.perf_counter()
        with span(
            "incident.resume",
            parent_trace_id=state.trace_id,
            incident_id=state.incident_id,
            execution_id=state.execution_id,
            trace_id=state.trace_id,
        ):
            try:
                state = await workflow(state, ledger)
                state = self._with_budget(state, ledger)
                state = self.checkpoints.save(state)
            except BudgetExceeded as exc:
                state = state.model_copy(
                    update={
                        "status": ExecutionStatus.HUMAN_ESCALATION,
                        "metadata": {
                            **state.metadata,
                            "termination_reason": exc.reason,
                            "budget_usage": ledger.snapshot(),
                        },
                    }
                )
                state = self.checkpoints.save(state)
            except Exception:
                state = state.model_copy(update={"status": ExecutionStatus.FAILED_SYSTEM})
                state = self.checkpoints.save(state)
                self.repository.set_execution_state(
                    execution_id, ExecutionStatus.FAILED_SYSTEM.value
                )
                self.repository.update_incident(
                    state.incident_id, status=ExecutionStatus.FAILED_SYSTEM.value
                )
                INCIDENTS.labels(status=ExecutionStatus.FAILED_SYSTEM.value).inc()
                ERRORS.labels(component="incident", code="failed_system").inc()
                raise
            finally:
                INCIDENT_LATENCY.labels(operation="resume").observe(
                    time.perf_counter() - started
                )
        self.repository.set_execution_state(execution_id, state.status.value)
        self.repository.update_incident(
            state.incident_id,
            status=state.status.value,
            diagnosis=state.diagnosis.model_dump(mode="json") if state.diagnosis else None,
        )
        INCIDENTS.labels(status=state.status.value).inc()
        self._record_abstention(state)
        return state

    @staticmethod
    def _record_abstention(state: RuntimeState) -> None:
        if state.status in {
            ExecutionStatus.INSUFFICIENT_EVIDENCE,
            ExecutionStatus.HUMAN_ESCALATION,
        }:
            reason = str(state.metadata.get("termination_reason", state.status.value))
            ABSTENTIONS.labels(reason=reason).inc()

    @staticmethod
    def _with_budget(state: RuntimeState, ledger: BudgetLedger) -> RuntimeState:
        return state.model_copy(
            update={"metadata": {**state.metadata, "budget_usage": ledger.snapshot()}}
        )
