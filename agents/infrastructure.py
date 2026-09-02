from __future__ import annotations

from agents.base import InvestigationContext
from runtime.state import Evidence


class InfrastructureAgent:
    name = "infrastructure"

    async def run(self, context: InvestigationContext, task_id: str) -> list[Evidence]:
        namespace = {"namespace": "sentinel-demo"}
        service = {"namespace": "sentinel-demo", "service": context.snapshot.scenario.service}
        calls = [
            ("get_pods", namespace),
            ("get_events", namespace),
            ("get_deployment", service),
            ("get_resource_limits", service),
            ("get_namespace_health", namespace),
        ]
        if context.snapshot.scenario.category == "kubernetes":
            calls.extend([("get_service", service), ("get_configmap", service)])
        evidence: list[Evidence] = []
        for name, arguments in calls:
            evidence.extend(await context.call_tool(name, arguments, task_id))
        return evidence
