from __future__ import annotations

import hashlib
import time

from agents.supervisor import SupervisorAgent
from mcp.factory import ToolProviderConfig, mount_investigation_tools
from persistence.repository import SentinelRepository
from runtime.budgets import BudgetPolicy
from runtime.executor import RuntimeExecutor
from runtime.features import InvestigationFeatures
from runtime.langchain_gateway import LangChainReasoner
from runtime.model_router import ModelRouter
from runtime.state import ExecutionStatus, RuntimeState
from runtime.tool_registry import ToolRegistry
from simulator.catalog import by_id
from simulator.engine import IncidentSimulator, SimulationSnapshot
from simulator.models import RuntimeScenario


class InvestigationService:
    def __init__(
        self,
        repository: SentinelRepository,
        budget_policy: BudgetPolicy | None = None,
        model_router: ModelRouter | None = None,
        tool_config: ToolProviderConfig | None = None,
        features: InvestigationFeatures | None = None,
    ) -> None:
        self.repository = repository
        self.budget_policy = budget_policy or BudgetPolicy()
        self.reasoner = LangChainReasoner(repository, model_router)
        self.tool_config = tool_config or ToolProviderConfig()
        self.features = features or InvestigationFeatures()

    async def run_scenario(self, scenario_id: str) -> RuntimeState:
        scenario = by_id(scenario_id)
        idempotency = f"scenario-{scenario_id}"
        incident, _ = self.repository.create_incident(
            title=scenario.title,
            service=scenario.service,
            severity="SEV-2",
            alert={
                "title": scenario.title,
                "service": scenario.service,
                "severity": "SEV-2",
                "scenario_id": scenario_id,
            },
            scenario_id=scenario_id,
            idempotency_key=idempotency,
        )
        return await self.run_incident(incident.id)

    async def run_incident(self, incident_id: str) -> RuntimeState:
        incident = self.repository.get_incident(incident_id)
        if self.tool_config.mode == "simulator":
            if not incident.scenario_id:
                raise ValueError("simulator investigations require a scenario_id")
            snapshot = IncidentSimulator().inject(incident.scenario_id)
        else:
            snapshot = self._live_snapshot(incident.title, incident.service)
        tools = ToolRegistry(self.repository)
        mount_investigation_tools(tools, self.repository, snapshot, self.tool_config)
        executor = RuntimeExecutor(self.repository, self.budget_policy)
        supervisor = SupervisorAgent(
            self.repository,
            tools,
            snapshot,
            executor.checkpoints,
            self.reasoner,
            use_snapshot_models=self.tool_config.mode == "simulator",
            features=self.features,
        )

        async def workflow(state: RuntimeState, ledger) -> RuntimeState:  # type: ignore[no-untyped-def]
            return await supervisor.run(state, ledger)

        if incident.execution_id and incident.status not in {"failed_system"}:
            state = executor.resume(incident.execution_id)
            if state.status.terminal or state.status is ExecutionStatus.WAITING_APPROVAL:
                return state
            return await executor.resume_execute(incident.execution_id, workflow)
        return await executor.execute(incident.id, workflow)

    @staticmethod
    def _live_snapshot(title: str, service: str) -> SimulationSnapshot:
        """Supply routing context without simulator observations or evaluator labels."""
        scenario = RuntimeScenario(
            id="live_observation",
            title=title,
            category="live",
            service=service,
            difficulty="hard",
            seed=0,
        )
        return SimulationSnapshot(
            scenario=scenario,
            telemetry=(),
            logs=(),
            kubernetes={},
            deployment={},
            runbooks=(),
            injected_at=time.time(),
        )

    @staticmethod
    def trial_key(scenario_id: str, seed: int, system: str) -> str:
        value = f"{scenario_id}:{seed}:{system}"
        return hashlib.sha256(value.encode()).hexdigest()[:16]
