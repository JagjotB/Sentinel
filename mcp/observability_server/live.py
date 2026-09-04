from __future__ import annotations

import json
from typing import Any

import httpx

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
from mcp.schemas import LogSearch, MetricsQuery, ResourceRequest, TraceRequest
from simulator.faults.kubernetes import CommandRunner, SubprocessCommandRunner


class LiveObservabilityToolServer(ToolServer):
    def __init__(
        self,
        *,
        prometheus_url: str = "http://localhost:9090",
        tempo_url: str = "",
        namespace: str = "sentinel-demo",
        runner: CommandRunner | None = None,
        http_transport: httpx.BaseTransport | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.prometheus_url = prometheus_url.rstrip("/")
        self.tempo_url = tempo_url.rstrip("/")
        self.namespace = namespace
        self.runner = runner or SubprocessCommandRunner()
        self.http_transport = http_transport
        self.register(
            ToolSpec("query_prometheus", MetricsQuery, PermissionClass.READ, self._metrics)
        )
        self.register(ToolSpec("search_logs", LogSearch, PermissionClass.READ, self._logs))
        self.register(ToolSpec("get_trace", TraceRequest, PermissionClass.READ, self._trace))
        self.register(ToolSpec("query_alerts", ResourceRequest, PermissionClass.READ, self._alerts))
        self.register(ToolSpec("get_service_slo", ResourceRequest, PermissionClass.READ, self._slo))

    async def call(self, name: str, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        result = await super().call(name, arguments, context)
        item = artifact(
            tool=name,
            source="observability",
            kind=name,
            summary=f"Live observability result for {name.replace('_', ' ')}",
            payload=result.data,
            raw=f"observability://{name}",
        )
        partial = name == "get_trace" and not result.data.get("spans")
        return result.model_copy(update={"evidence": [item], "partial": partial})

    def _metrics(self, request: MetricsQuery, _: ToolContext) -> dict[str, Any]:
        if request.start is not None and request.end is not None:
            return self._prometheus(
                "/api/v1/query_range",
                {"query": request.query, "start": request.start, "end": request.end, "step": 5},
            )
        return self._prometheus("/api/v1/query", {"query": request.query})

    def _logs(self, request: LogSearch, _: ToolContext) -> dict[str, Any]:
        args = [
            "kubectl",
            "logs",
            f"deployment/{request.service}",
            "--namespace",
            self.namespace,
            f"--tail={request.limit}",
        ]
        result = self.runner.run(args, timeout_seconds=10)
        if result.returncode != 0:
            raise ToolFailure(
                ErrorCode.PROVIDER_UNAVAILABLE,
                result.stderr.strip() or "kubectl logs failed",
                retryable=True,
            )
        query = request.query.lower()
        rows: list[object] = []
        for line in result.stdout.splitlines():
            if query and query not in line.lower():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                rows.append({"message": line})
        return {"items": rows, "total": len(rows), "source": "kubernetes_logs"}

    def _trace(self, request: TraceRequest, _: ToolContext) -> dict[str, Any]:
        if not self.tempo_url:
            return {"trace_id": request.trace_id, "spans": [], "reason": "tempo_not_configured"}
        return self._http_json(f"{self.tempo_url}/api/traces/{request.trace_id}")

    def _alerts(self, _: ResourceRequest, __: ToolContext) -> dict[str, Any]:
        return self._prometheus("/api/v1/alerts", {})

    def _slo(self, request: ResourceRequest, _: ToolContext) -> dict[str, Any]:
        success = (
            'sum(rate(sentinel_demo_requests_total{service="'
            f'{request.service}",status=~"2.."}}[5m]))'
        )
        total = f'sum(rate(sentinel_demo_requests_total{{service="{request.service}"}}[5m]))'
        return {
            "service": request.service,
            "success": self._prometheus("/api/v1/query", {"query": success}),
            "total": self._prometheus("/api/v1/query", {"query": total}),
        }

    def _prometheus(
        self,
        path: str,
        params: dict[str, str | int | float | bool | None],
    ) -> dict[str, Any]:
        payload = self._http_json(f"{self.prometheus_url}{path}", params)
        if payload.get("status") != "success":
            raise ToolFailure(
                ErrorCode.PROVIDER_UNAVAILABLE,
                "Prometheus query failed",
                retryable=True,
            )
        return payload

    def _http_json(
        self,
        url: str,
        params: dict[str, str | int | float | bool | None] | None = None,
    ) -> dict[str, Any]:
        try:
            with httpx.Client(transport=self.http_transport, timeout=10) as client:
                response = client.get(url, params=params)
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ToolFailure(
                ErrorCode.PROVIDER_UNAVAILABLE,
                f"observability provider unavailable: {url}",
                retryable=True,
            ) from exc
        if not isinstance(payload, dict):
            raise ToolFailure(ErrorCode.INTERNAL, "observability result was not an object")
        return payload
