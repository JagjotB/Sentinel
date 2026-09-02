from __future__ import annotations

import asyncio

import pytest
from pydantic import BaseModel

from mcp.contracts import (
    ErrorCode,
    PermissionClass,
    ToolContext,
    ToolFailure,
    ToolServer,
    ToolSpec,
)
from mcp.git_server import GitToolServer
from mcp.kubernetes_server import KubernetesToolServer
from mcp.observability_server import ObservabilityToolServer
from simulator.engine import IncidentSimulator


@pytest.fixture
def context() -> ToolContext:
    return ToolContext(
        incident_id="inc_test",
        execution_id="exec_test",
        auth_token="sentinel-tool-token",  # noqa: S106 - local test credential
        trace_id="a" * 24,
    )


@pytest.fixture
def snapshot():  # type: ignore[no-untyped-def]
    return IncidentSimulator().inject("oom_killed_001")


async def test_stable_evidence_and_duplicate_deduplication(snapshot, context: ToolContext) -> None:  # type: ignore[no-untyped-def]
    server = KubernetesToolServer(snapshot)
    first = await server.call("get_events", {"namespace": "sentinel-demo"}, context)
    second = await server.call("get_events", {"namespace": "sentinel-demo"}, context)
    assert first.evidence[0].id == second.evidence[0].id
    assert second.deduplicated is True


async def test_malformed_request_is_structured(snapshot, context: ToolContext) -> None:  # type: ignore[no-untyped-def]
    server = KubernetesToolServer(snapshot)
    with pytest.raises(ToolFailure) as error:
        await server.call("get_deployment", {}, context)
    assert error.value.code is ErrorCode.MALFORMED_REQUEST


async def test_auth_failure_and_write_policy(snapshot, context: ToolContext) -> None:  # type: ignore[no-untyped-def]
    git = GitToolServer(snapshot)
    bad_context = context.model_copy(update={"auth_token": "wrong"})
    with pytest.raises(ToolFailure) as auth_error:
        await git.call("get_recent_commits", {}, bad_context)
    assert auth_error.value.code is ErrorCode.AUTH_FAILURE
    with pytest.raises(ToolFailure) as policy_error:
        await git.call(
            "create_proposed_patch_or_pr",
            {"title": "restore limit", "path": "deploy/payments.yaml", "patch": "+ memory: 512Mi"},
            context,
        )
    assert policy_error.value.code is ErrorCode.POLICY_DENIED


async def test_partial_trace_response(snapshot, context: ToolContext) -> None:  # type: ignore[no-untyped-def]
    server = ObservabilityToolServer(snapshot)
    result = await server.call("get_trace", {"trace_id": "f" * 24}, context)
    assert result.partial is True


class SlowRequest(BaseModel):
    value: int


async def test_timeout_contract(context: ToolContext) -> None:
    async def slow(_: BaseModel, __: ToolContext) -> dict[str, object]:
        await asyncio.sleep(0.05)
        return {}

    server = ToolServer()
    server.register(
        ToolSpec("slow", SlowRequest, PermissionClass.READ, slow, timeout_seconds=0.001)
    )
    with pytest.raises(ToolFailure) as error:
        await server.call("slow", {"value": 1}, context)
    assert error.value.code is ErrorCode.TIMEOUT
    assert error.value.retryable is True
