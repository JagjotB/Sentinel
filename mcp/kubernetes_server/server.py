from __future__ import annotations

from typing import Any

from mcp.contracts import (
    PermissionClass,
    ToolContext,
    ToolResult,
    ToolServer,
    ToolSpec,
    artifact,
)
from mcp.schemas import NamespaceRequest, ResourceRequest
from simulator.engine import SimulationSnapshot


class KubernetesToolServer(ToolServer):
    def __init__(self, snapshot: SimulationSnapshot, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.snapshot = snapshot
        mappings = {
            "get_pods": (NamespaceRequest, self._pods),
            "get_events": (NamespaceRequest, self._events),
            "get_deployment": (ResourceRequest, self._deployment),
            "get_rollout_history": (ResourceRequest, self._rollout),
            "get_service": (ResourceRequest, self._service),
            "get_configmap": (ResourceRequest, self._configmap),
            "get_resource_limits": (ResourceRequest, self._resource_limits),
            "get_namespace_health": (NamespaceRequest, self._health),
        }
        for name, (schema, handler) in mappings.items():
            self.register(ToolSpec(name, schema, PermissionClass.READ, handler))

    async def call(self, name: str, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        result = await super().call(name, arguments, context)
        if result.evidence:
            return result
        evidence = artifact(
            tool=name,
            source="kubernetes",
            kind=name.removeprefix("get_"),
            summary=f"Kubernetes {name.removeprefix('get_').replace('_', ' ')} collected",
            payload=result.data,
            raw=f"simulator://{self.snapshot.scenario.id}/kubernetes/{name}",
        )
        return result.model_copy(update={"evidence": [evidence]})

    def _pods(self, _: NamespaceRequest, __: ToolContext) -> dict[str, Any]:
        return {"items": self.snapshot.kubernetes["pods"]}

    def _events(self, _: NamespaceRequest, __: ToolContext) -> dict[str, Any]:
        return {"items": self.snapshot.kubernetes["events"]}

    def _deployment(self, _: ResourceRequest, __: ToolContext) -> dict[str, Any]:
        return self.snapshot.kubernetes["deployment"]

    def _rollout(self, _: ResourceRequest, __: ToolContext) -> dict[str, Any]:
        return {"revisions": [self.snapshot.deployment]}

    def _service(self, _: ResourceRequest, __: ToolContext) -> dict[str, Any]:
        return self.snapshot.kubernetes["service"]

    def _configmap(self, _: ResourceRequest, __: ToolContext) -> dict[str, Any]:
        return self.snapshot.kubernetes["configmap"]

    def _resource_limits(self, _: ResourceRequest, __: ToolContext) -> dict[str, Any]:
        return self.snapshot.kubernetes["resource_limits"]

    def _health(self, _: NamespaceRequest, __: ToolContext) -> dict[str, Any]:
        pods = self.snapshot.kubernetes["pods"]
        return {"healthy": all(pod["ready"] for pod in pods), "pod_count": len(pods)}
