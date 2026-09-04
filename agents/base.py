from __future__ import annotations

from dataclasses import dataclass

from mcp.contracts import ToolContext, ToolResult
from persistence.repository import SentinelRepository
from runtime.budgets import BudgetLedger
from runtime.state import Evidence, RuntimeState
from runtime.tool_registry import ToolRegistry
from simulator.engine import SimulationSnapshot


@dataclass
class InvestigationContext:
    state: RuntimeState
    snapshot: SimulationSnapshot
    repository: SentinelRepository
    tools: ToolRegistry
    ledger: BudgetLedger

    async def call_tool(
        self, name: str, arguments: dict[str, object], task_id: str
    ) -> list[Evidence]:
        tool_context = ToolContext(
            incident_id=self.state.incident_id,
            execution_id=self.state.execution_id,
            task_id=task_id,
            auth_token="sentinel-tool-token",  # noqa: S106 - local adapter boundary
            trace_id=self.state.trace_id,
        )
        tool = self.tools.langchain_tool(name, tool_context, self.ledger)
        raw_result = await tool.ainvoke(
            arguments,
            config={
                "tags": ["sentinel", f"tool:{name}"],
                "metadata": {
                    "incident_id": self.state.incident_id,
                    "execution_id": self.state.execution_id,
                    "task_id": task_id,
                    "trace_id": self.state.trace_id,
                },
            },
        )
        result = ToolResult.model_validate(raw_result)
        evidence: list[Evidence] = []
        for item in result.evidence:
            record = self.repository.add_evidence(
                id=item.id,
                incident_id=self.state.incident_id,
                task_id=task_id,
                source=item.source,
                kind=item.kind,
                summary=item.summary,
                raw_reference=item.raw_reference,
                payload=item.payload,
            )
            evidence.append(
                Evidence(
                    id=record.id,
                    source=record.source,
                    kind=record.kind,
                    summary=record.summary,
                    raw_reference=record.raw_reference,
                    payload=record.payload,
                    observed_at=record.observed_at,
                )
            )
        return evidence

    def store_evidence(self, evidence: Evidence, task_id: str) -> Evidence:
        record = self.repository.add_evidence(
            id=evidence.id,
            incident_id=self.state.incident_id,
            task_id=task_id,
            source=evidence.source,
            kind=evidence.kind,
            summary=evidence.summary,
            raw_reference=evidence.raw_reference,
            payload=evidence.payload,
            observed_at=evidence.observed_at,
        )
        return Evidence.model_validate(
            {
                "id": record.id,
                "source": record.source,
                "kind": record.kind,
                "summary": record.summary,
                "raw_reference": record.raw_reference,
                "payload": record.payload,
                "observed_at": record.observed_at,
                "relevance": evidence.relevance,
            }
        )
