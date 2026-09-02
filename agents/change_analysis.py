from __future__ import annotations

from agents.base import InvestigationContext
from runtime.state import Evidence


class ChangeAnalysisAgent:
    name = "change_analysis"

    async def run(self, context: InvestigationContext, task_id: str) -> list[Evidence]:
        revision = context.snapshot.deployment["revision"]
        evidence = await context.call_tool("get_recent_commits", {}, task_id)
        evidence.extend(
            await context.call_tool("get_diff", {"base": f"{revision}^", "head": revision}, task_id)
        )
        return evidence
