from __future__ import annotations

import hashlib

from agents.supervisor import SupervisorAgent
from mcp.factory import ToolProviderConfig, mount_investigation_tools
from persistence.repository import SentinelRepository
from runtime.budgets import BudgetPolicy
from runtime.executor import RuntimeExecutor
from runtime.langchain_gateway import LangChainReasoner
from runtime.model_router import ModelRouter
from runtime.state import RuntimeState
from runtime.tool_registry import ToolRegistry
from simulator.catalog import by_id
from simulator.engine import IncidentSimulator


class InvestigationService:
    def __init__(
        self,
        repository: SentinelRepository,
        budget_policy: BudgetPolicy | None = None,
        model_router: ModelRouter | None = None,
        tool_config: ToolProviderConfig | None = None,
    ) -> None:
        self.repository = repository
        self.budget_policy = budget_policy or BudgetPolicy()
        self.reasoner = LangChainReasoner(repository, model_router)
        self.tool_config = tool_config or ToolProviderConfig()

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
        if incident.execution_id and incident.status in {
            "waiting_approval",
            "resolved",
            "insufficient_evidence",
        }:
            return RuntimeExecutor(self.repository, self.budget_policy).resume(
                incident.execution_id
            )
        snapshot = IncidentSimulator().inject(scenario_id)
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
        )

        async def workflow(state: RuntimeState, ledger) -> RuntimeState:  # type: ignore[no-untyped-def]
            return await supervisor.run(state, ledger)

        return await executor.execute(incident.id, workflow)

    @staticmethod
    def trial_key(scenario_id: str, seed: int, system: str) -> str:
        value = f"{scenario_id}:{seed}:{system}"
        return hashlib.sha256(value.encode()).hexdigest()[:16]
