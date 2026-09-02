from __future__ import annotations

from typing import Any

from mcp.contracts import PermissionClass, ToolContext, ToolResult, ToolServer, ToolSpec, artifact
from mcp.schemas import LogSearch, MetricsQuery, ResourceRequest, TraceRequest
from simulator.engine import SimulationSnapshot


class ObservabilityToolServer(ToolServer):
    def __init__(self, snapshot: SimulationSnapshot, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.snapshot = snapshot
        self.register(
            ToolSpec("query_prometheus", MetricsQuery, PermissionClass.READ, self._metrics)
        )
        self.register(ToolSpec("search_logs", LogSearch, PermissionClass.READ, self._logs))
        self.register(ToolSpec("get_trace", TraceRequest, PermissionClass.READ, self._trace))
        self.register(ToolSpec("query_alerts", ResourceRequest, PermissionClass.READ, self._alerts))
        self.register(ToolSpec("get_service_slo", ResourceRequest, PermissionClass.READ, self._slo))

    async def call(self, name: str, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        result = await super().call(name, arguments, context)
        partial = name == "get_trace" and not result.data.get("spans")
        item = artifact(
            tool=name,
            source="observability",
            kind=name,
            summary=f"Observability result for {name.replace('_', ' ')}",
            payload=result.data,
            raw=f"simulator://{self.snapshot.scenario.id}/observability/{name}",
        )
        return result.model_copy(update={"evidence": [item], "partial": partial})

    def _metrics(self, _: MetricsQuery, __: ToolContext) -> dict[str, Any]:
        return {"series": [point.model_dump(mode="json") for point in self.snapshot.telemetry]}

    def _logs(self, request: LogSearch, _: ToolContext) -> dict[str, Any]:
        query = request.query.lower()
        rows = [
            row.model_dump(mode="json")
            for row in self.snapshot.logs
            if row.service == request.service and (not query or query in row.message.lower())
        ]
        return {"items": rows[: request.limit], "total": len(rows)}

    def _trace(self, request: TraceRequest, _: ToolContext) -> dict[str, Any]:
        rows = [row for row in self.snapshot.logs if row.trace_id == request.trace_id]
        return {
            "trace_id": request.trace_id,
            "spans": [row.model_dump(mode="json") for row in rows],
        }

    def _alerts(self, request: ResourceRequest, _: ToolContext) -> dict[str, Any]:
        return {"alerts": [{"service": request.service, "state": "firing", "severity": "SEV-2"}]}

    def _slo(self, request: ResourceRequest, _: ToolContext) -> dict[str, Any]:
        return {"service": request.service, "availability_target": 0.999, "burn_rate": 14.2}
