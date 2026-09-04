from __future__ import annotations

from typing import Any

from mcp.contracts import (
    ErrorCode,
    PermissionClass,
    ToolContext,
    ToolFailure,
    ToolResult,
    ToolServer,
    ToolSpec,
    artifact,
)
from mcp.schemas import IncidentRequest, IncidentSearch, StoreResolutionRequest
from retrieval import HybridSearch, build_corpus
from simulator.engine import SimulationSnapshot


class IncidentKnowledgeToolServer(ToolServer):
    def __init__(self, snapshot: SimulationSnapshot, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.snapshot = snapshot
        self.documents = build_corpus(exclude_scenario_ids={snapshot.scenario.id})
        self.search = HybridSearch(self.documents)
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
        results = [
            result
            for result in self.search.search(request.query, limit=request.limit * 2)
            if result.document.source_type == "historical_incident"
        ][: request.limit]
        return {
            "items": [
                {
                    "id": result.document.id,
                    "title": result.document.title,
                    "score": result.score,
                    "source_uri": result.document.source_uri,
                }
                for result in results
            ]
        }

    def _incident(self, request: IncidentRequest, _: ToolContext) -> dict[str, Any]:
        document = next((item for item in self.documents if item.id == request.incident_id), None)
        if document is None or document.source_type != "historical_incident":
            raise ToolFailure(
                ErrorCode.NOT_FOUND,
                f"unknown historical incident: {request.incident_id}",
            )
        return {
            "id": document.id,
            "title": document.title,
            "body": document.body,
            "source_uri": document.source_uri,
        }

    def _runbooks(self, request: IncidentSearch, _: ToolContext) -> dict[str, Any]:
        results = [
            result
            for result in self.search.search(request.query, limit=len(self.documents))
            if result.document.source_type == "runbook"
        ][: request.limit]
        return {
            "items": [
                {
                    "id": result.document.id,
                    "title": result.document.title,
                    "body": result.document.body,
                    "source_uri": result.document.source_uri,
                    "score": result.score,
                }
                for result in results
            ]
        }

    def _store(self, request: StoreResolutionRequest, _: ToolContext) -> dict[str, Any]:
        return {
            "stored": True,
            "incident_id": request.incident_id,
            "root_cause": request.root_cause,
        }
