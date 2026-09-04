from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel

from mcp.contracts import (
    ErrorCode,
    Handler,
    PermissionClass,
    ToolContext,
    ToolFailure,
    ToolResult,
    ToolServer,
    ToolSpec,
    artifact,
)
from mcp.schemas import NamespaceRequest, ResourceRequest
from simulator.faults.kubernetes import CommandRunner, SubprocessCommandRunner


class LiveKubernetesToolServer(ToolServer):
    """Read-only kubectl adapter restricted to one configured namespace."""

    def __init__(
        self,
        *,
        namespace: str = "sentinel-demo",
        kubectl_context: str = "",
        runner: CommandRunner | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.namespace = namespace
        self.kubectl_context = kubectl_context
        self.runner = runner or SubprocessCommandRunner()
        mappings: dict[str, tuple[type[BaseModel], Handler]] = {
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
            self.register(ToolSpec(name, schema, PermissionClass.READ, handler, timeout_seconds=10))

    async def call(self, name: str, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        result = await super().call(name, arguments, context)
        item = artifact(
            tool=name,
            source="kubernetes",
            kind=name.removeprefix("get_"),
            summary=f"Live Kubernetes {name.removeprefix('get_').replace('_', ' ')} collected",
            payload=result.data,
            raw=f"kubernetes://{self.kubectl_context or 'current'}/{self.namespace}/{name}",
        )
        return result.model_copy(update={"evidence": [item]})

    def _pods(self, request: NamespaceRequest, _: ToolContext) -> dict[str, Any]:
        return self._json(request.namespace, "get", "pods", "-o", "json")

    def _events(self, request: NamespaceRequest, _: ToolContext) -> dict[str, Any]:
        return self._json(
            request.namespace,
            "get",
            "events",
            "--sort-by=.metadata.creationTimestamp",
            "-o",
            "json",
        )

    def _deployment(self, request: ResourceRequest, _: ToolContext) -> dict[str, Any]:
        return self._json(request.namespace, "get", f"deployment/{request.service}", "-o", "json")

    def _rollout(self, request: ResourceRequest, _: ToolContext) -> dict[str, Any]:
        output = self._run(
            request.namespace, "rollout", "history", f"deployment/{request.service}"
        )
        return {"service": request.service, "history": output}

    def _service(self, request: ResourceRequest, _: ToolContext) -> dict[str, Any]:
        return self._json(request.namespace, "get", f"service/{request.service}", "-o", "json")

    def _configmap(self, request: ResourceRequest, _: ToolContext) -> dict[str, Any]:
        name = (
            "sentinel-demo-config"
            if request.service in {"checkout", "payments"}
            else request.service
        )
        return self._json(request.namespace, "get", f"configmap/{name}", "-o", "json")

    def _resource_limits(self, request: ResourceRequest, context: ToolContext) -> dict[str, Any]:
        deployment = self._deployment(request, context)
        spec = deployment.get("spec", {})
        template = spec.get("template", {}) if isinstance(spec, dict) else {}
        pod_spec = template.get("spec", {}) if isinstance(template, dict) else {}
        containers = pod_spec.get("containers", []) if isinstance(pod_spec, dict) else []
        return {
            "service": request.service,
            "containers": [
                {"name": row.get("name"), "resources": row.get("resources", {})}
                for row in containers
                if isinstance(row, dict)
            ],
        }

    def _health(self, request: NamespaceRequest, _: ToolContext) -> dict[str, Any]:
        payload = self._pods(request, _)
        items = payload.get("items", [])
        pods = [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []
        ready = 0
        for pod in pods:
            status = pod.get("status", {})
            conditions = status.get("conditions", []) if isinstance(status, dict) else []
            if any(
                condition.get("type") == "Ready" and condition.get("status") == "True"
                for condition in conditions
                if isinstance(condition, dict)
            ):
                ready += 1
        return {"healthy": ready == len(pods) and bool(pods), "ready": ready, "total": len(pods)}

    def _json(self, namespace: str, *arguments: str) -> dict[str, Any]:
        output = self._run(namespace, *arguments)
        try:
            parsed = json.loads(output)
        except json.JSONDecodeError as exc:
            raise ToolFailure(
                ErrorCode.PROVIDER_UNAVAILABLE,
                "kubectl returned invalid JSON",
                retryable=True,
            ) from exc
        if not isinstance(parsed, dict):
            raise ToolFailure(ErrorCode.INTERNAL, "kubectl result was not an object")
        return parsed

    def _run(self, namespace: str, *arguments: str) -> str:
        if namespace != self.namespace:
            raise ToolFailure(ErrorCode.POLICY_DENIED, "namespace is outside the configured scope")
        args = ["kubectl"]
        if self.kubectl_context:
            args.extend(["--context", self.kubectl_context])
        args.extend([*arguments, "--namespace", namespace])
        result = self.runner.run(args, timeout_seconds=10)
        if result.returncode != 0:
            raise ToolFailure(
                ErrorCode.PROVIDER_UNAVAILABLE,
                result.stderr.strip() or "kubectl command failed",
                retryable=True,
            )
        return result.stdout
