from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from mcp.contracts import ErrorCode, ToolContext, ToolFailure
from mcp.git_server.live import LiveGitToolServer
from mcp.incidents_server.live import LiveIncidentKnowledgeToolServer
from mcp.kubernetes_server.live import LiveKubernetesToolServer
from mcp.observability_server.live import LiveObservabilityToolServer
from persistence.repository import SentinelRepository
from simulator.faults.kubernetes import CommandResult


class FakeRunner:
    def __init__(self, responses: dict[str, str] | None = None) -> None:
        self.responses = responses or {}
        self.calls: list[list[str]] = []

    def run(
        self,
        args: list[str],
        *,
        input_text: str | None = None,
        timeout_seconds: float = 60.0,
    ) -> CommandResult:
        del input_text, timeout_seconds
        self.calls.append(args)
        output = next((value for key, value in self.responses.items() if key in args), "{}")
        return CommandResult(args=args, returncode=0, stdout=output)


@pytest.fixture
def context() -> ToolContext:
    return ToolContext(
        incident_id="inc_live",
        execution_id="exec_live",
        auth_token="sentinel-tool-token",  # noqa: S106 - local test credential
        trace_id="a" * 24,
    )


async def test_live_kubernetes_uses_scoped_argv_and_returns_evidence(
    context: ToolContext,
) -> None:
    payload = {
        "items": [
            {
                "metadata": {"name": "payments-1"},
                "status": {"conditions": [{"type": "Ready", "status": "True"}]},
            }
        ]
    }
    runner = FakeRunner({"pods": json.dumps(payload)})
    server = LiveKubernetesToolServer(
        namespace="sentinel-demo",
        kubectl_context="sentinel-kind",
        runner=runner,
    )

    result = await server.call("get_namespace_health", {"namespace": "sentinel-demo"}, context)

    assert result.data == {"healthy": True, "ready": 1, "total": 1}
    assert result.evidence[0].raw_reference.startswith("kubernetes://sentinel-kind/")
    assert runner.calls == [
        [
            "kubectl",
            "--context",
            "sentinel-kind",
            "get",
            "pods",
            "-o",
            "json",
            "--namespace",
            "sentinel-demo",
        ]
    ]


async def test_live_kubernetes_rejects_namespace_escape(context: ToolContext) -> None:
    server = LiveKubernetesToolServer(namespace="sentinel-demo", runner=FakeRunner())
    with pytest.raises(ToolFailure) as error:
        await server.call("get_pods", {"namespace": "production"}, context)
    assert error.value.code is ErrorCode.POLICY_DENIED


async def test_live_prometheus_and_tempo_contracts(context: ToolContext) -> None:
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        if request.url.path.startswith("/api/traces/"):
            return httpx.Response(200, json={"traceID": "b" * 24, "batches": []})
        return httpx.Response(
            200,
            json={"status": "success", "data": {"resultType": "vector", "result": []}},
        )

    server = LiveObservabilityToolServer(
        prometheus_url="http://prometheus.test",
        tempo_url="http://tempo.test",
        runner=FakeRunner(),
        http_transport=httpx.MockTransport(handler),
    )
    metrics = await server.call(
        "query_prometheus",
        {"query": 'up{service="payments"}'},
        context,
    )
    trace = await server.call("get_trace", {"trace_id": "b" * 24}, context)

    assert metrics.data["status"] == "success"
    assert trace.partial is True
    assert any("/api/v1/query" in url for url in requested)
    assert any("/api/traces/" in url for url in requested)


async def test_live_git_reads_and_governed_patch_write(
    context: ToolContext,
    tmp_path: Path,
) -> None:
    runner = FakeRunner(
        {
            "log": "abc123\x1f2026-01-01T00:00:00Z\x1fSentinel\x1ffix payments\n",
        }
    )
    server = LiveGitToolServer(tmp_path, runner=runner)
    commits = await server.call("get_recent_commits", {}, context)
    assert commits.data["commits"][0]["revision"] == "abc123"

    with pytest.raises(ToolFailure) as denied:
        await server.call(
            "create_proposed_patch_or_pr",
            {"title": "Raise memory", "path": "deploy/payments.yaml", "patch": "+memory: 1Gi"},
            context,
        )
    assert denied.value.code is ErrorCode.POLICY_DENIED

    approved = context.model_copy(update={"approved_write": True})
    patch = await server.call(
        "create_proposed_patch_or_pr",
        {"title": "Raise memory", "path": "deploy/payments.yaml", "patch": "+memory: 1Gi"},
        approved,
    )
    artifact = tmp_path / str(patch.data["artifact"])
    assert artifact.read_text(encoding="utf-8") == "+memory: 1Gi"
    assert artifact.resolve().is_relative_to((tmp_path / ".sentinel" / "proposals").resolve())


async def test_live_incident_search_uses_repository_data_without_scenario_labels(
    context: ToolContext,
    tmp_path: Path,
) -> None:
    repository = SentinelRepository(f"sqlite:///{tmp_path / 'sentinel.db'}")
    incident, _ = repository.create_incident(
        title="Payments latency alert",
        service="payments",
        severity="high",
        alert={"latency_ms": 912},
        idempotency_key="live-adapter-test",
        scenario_id="secret_evaluator_label",
    )
    server = LiveIncidentKnowledgeToolServer(repository)

    result = await server.call("search_incidents", {"query": "payments latency"}, context)
    item = result.data["items"][0]

    assert item["id"] == incident.id
    assert "scenario_id" not in item
    assert "root_cause" not in item
