from __future__ import annotations

from typing import Any

from mcp.contracts import PermissionClass, ToolContext, ToolResult, ToolServer, ToolSpec, artifact
from mcp.schemas import IncidentRequest, IncidentSearch, StoreResolutionRequest
from simulator.engine import SimulationSnapshot


class IncidentKnowledgeToolServer(ToolServer):
    def __init__(self, snapshot: SimulationSnapshot, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.snapshot = snapshot
        self.register(
            ToolSpec(
                "search_incidents", IncidentSearch, PermissionClass.READ, self._search_incidents
            )
        )
        self.register(
            ToolSpec("get_incident", IncidentRequest, PermissionClass.READ, self._incident)
        )
        self.register(
            ToolSpec("search_runbooks", IncidentSearch, PermissionClass.READ, self._runbooks)
        )
        self.register(
            ToolSpec(
                "store_resolution",
                StoreResolutionRequest,
                PermissionClass.LOW_RISK_WRITE,
                self._store,
            )
        )

    async def call(self, name: str, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        result = await super().call(name, arguments, context)
        item = artifact(
            tool=name,
            source="incident_knowledge",
            kind="retrieval",
            summary=f"Knowledge result for {name.replace('_', ' ')}",
            payload=result.data,
            raw=f"simulator://{self.snapshot.scenario.id}/knowledge/{name}",
        )
        return result.model_copy(update={"evidence": [item]})

    def _search_incidents(self, request: IncidentSearch, _: ToolContext) -> dict[str, Any]:
        item = {
            "id": f"hist_{self.snapshot.scenario.root_cause}",
            "title": self.snapshot.scenario.title,
            "root_cause": self.snapshot.scenario.root_cause,
            "score": 0.93,
        }
        return {"items": [item][: request.limit]}

    def _incident(self, request: IncidentRequest, _: ToolContext) -> dict[str, Any]:
        return {
            "id": request.incident_id,
            "ground_truth": self.snapshot.scenario.model_dump(mode="json"),
        }

    def _runbooks(self, request: IncidentSearch, _: ToolContext) -> dict[str, Any]:
        words = set(request.query.lower().split())
        ranked = sorted(
            self.snapshot.runbooks,
            key=lambda row: len(words & set((row["title"] + " " + row["body"]).lower().split())),
            reverse=True,
        )
        return {"items": ranked[: request.limit]}

    def _store(self, request: StoreResolutionRequest, _: ToolContext) -> dict[str, Any]:
        return {
            "stored": True,
            "incident_id": request.incident_id,
            "root_cause": request.root_cause,
        }
