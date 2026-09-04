from __future__ import annotations

from agents.base import InvestigationContext
from runtime.state import Evidence


class ChangeAnalysisAgent:
    name = "change_analysis"

    async def run(self, context: InvestigationContext, task_id: str) -> list[Evidence]:
        evidence = await context.call_tool("get_recent_commits", {}, task_id)
        commits = evidence[0].payload.get("commits", []) if evidence else []
        if not isinstance(commits, list) or not commits or not isinstance(commits[0], dict):
            return evidence
        revision = str(commits[0].get("revision", ""))
        if not revision:
            return evidence
        evidence.extend(
            await context.call_tool("get_diff", {"base": f"{revision}^", "head": revision}, task_id)
        )
        return evidence
