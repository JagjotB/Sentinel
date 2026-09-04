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
from persistence.repository import NotFoundError, SentinelRepository
from retrieval import HybridSearch, build_corpus


class LiveIncidentKnowledgeToolServer(ToolServer):
    def __init__(self, repository: SentinelRepository, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.repository = repository
        self.runbook_search = HybridSearch(
            [document for document in build_corpus() if document.source_type == "runbook"]
        )
        self.register(
            ToolSpec(
                "search_incidents",
                IncidentSearch,
                PermissionClass.READ,
                self._search_incidents,
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
            kind="retrieval" if name != "store_resolution" else "resolution",
            summary=f"Live knowledge result for {name.replace('_', ' ')}",
            payload=result.data,
            raw=f"sentinel://incidents/{context.incident_id}/{name}",
        )
        return result.model_copy(update={"evidence": [item]})

    def _search_incidents(self, request: IncidentSearch, _: ToolContext) -> dict[str, Any]:
        terms = set(request.query.lower().split())
        ranked: list[tuple[int, dict[str, object]]] = []
        for incident in self.repository.list_incidents(limit=500):
            searchable = f"{incident.title} {incident.service} {incident.status}".lower()
            score = len(terms & set(searchable.split()))
            if score:
                ranked.append(
                    (
                        score,
                        {
                            "id": incident.id,
                            "title": incident.title,
                            "service": incident.service,
                            "status": incident.status,
                            "score": score / max(1, len(terms)),
                        },
                    )
                )
        ranked.sort(key=lambda row: row[0], reverse=True)
        return {"items": [item for _, item in ranked[: request.limit]]}

    def _incident(self, request: IncidentRequest, _: ToolContext) -> dict[str, Any]:
        try:
            incident = self.repository.get_incident(request.incident_id)
        except NotFoundError as exc:
            raise ToolFailure(ErrorCode.NOT_FOUND, str(exc)) from exc
        evidence = self.repository.list_evidence(incident.id)
        return {
            "id": incident.id,
            "title": incident.title,
            "service": incident.service,
            "severity": incident.severity,
            "status": incident.status,
            "diagnosis": incident.diagnosis,
            "evidence_ids": [item.id for item in evidence],
            "created_at": incident.created_at.isoformat(),
        }

    def _runbooks(self, request: IncidentSearch, _: ToolContext) -> dict[str, Any]:
        results = self.runbook_search.search(request.query, limit=request.limit)
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

    def _store(self, request: StoreResolutionRequest, context: ToolContext) -> dict[str, Any]:
        known_evidence = {item.id for item in self.repository.list_evidence(request.incident_id)}
        unknown = set(request.evidence_ids) - known_evidence
        if unknown:
            raise ToolFailure(
                ErrorCode.MALFORMED_REQUEST,
                f"resolution references unknown evidence: {sorted(unknown)}",
            )
        self.repository.update_incident(
            request.incident_id,
            status="resolved",
            diagnosis={
                "root_cause": request.root_cause,
                "resolution": request.resolution,
                "evidence_ids": request.evidence_ids,
            },
        )
        self.repository.add_audit(
            incident_id=request.incident_id,
            event_type="resolution_stored",
            actor="incident_tool",
            allowed=True,
            details={
                "execution_id": context.execution_id,
                "root_cause": request.root_cause,
                "evidence_ids": request.evidence_ids,
            },
        )
        return {"stored": True, "incident_id": request.incident_id, "status": "resolved"}
