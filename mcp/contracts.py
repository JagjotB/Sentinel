from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class PermissionClass(StrEnum):
    READ = "read"
    LOW_RISK_WRITE = "low_risk_write"
    DESTRUCTIVE = "destructive"


class ErrorCode(StrEnum):
    MALFORMED_REQUEST = "malformed_request"
    TIMEOUT = "timeout"
    AUTH_FAILURE = "auth_failure"
    NOT_FOUND = "not_found"
    POLICY_DENIED = "policy_denied"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    INTERNAL = "internal"


class ToolContext(BaseModel):
    model_config = ConfigDict(frozen=True)
    incident_id: str
    execution_id: str
    task_id: str | None = None
    auth_token: str
    approved_write: bool = False
    trace_id: str


class EvidenceArtifact(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str = Field(pattern=r"^ev_[a-f0-9]{16}$")
    source: str
    kind: str
    summary: str
    raw_reference: str
    payload: dict[str, Any]


class ToolResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    tool: str
    data: dict[str, Any]
    evidence: list[EvidenceArtifact] = Field(default_factory=list)
    partial: bool = False
    deduplicated: bool = False
    duration_ms: float = 0.0


class ToolFailure(RuntimeError):
    def __init__(self, code: ErrorCode, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


InputModel = type[BaseModel]
Handler = Callable[..., dict[str, Any] | Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    input_model: InputModel
    permission: PermissionClass
    handler: Handler
    timeout_seconds: float = 3.0
    max_retries: int = 1


def evidence_id(tool: str, payload: dict[str, Any]) -> str:
    canonical = json.dumps({"tool": tool, "payload": payload}, sort_keys=True, default=str)
    return f"ev_{hashlib.sha256(canonical.encode()).hexdigest()[:16]}"


def artifact(
    *, tool: str, source: str, kind: str, summary: str, payload: dict[str, Any], raw: str
) -> EvidenceArtifact:
    return EvidenceArtifact(
        id=evidence_id(tool, payload),
        source=source,
        kind=kind,
        summary=summary,
        raw_reference=raw,
        payload=payload,
    )


class ToolServer:
    """Small MCP-compatible core with schemas, authorization, timeout, and deduplication."""

    def __init__(self, *, auth_token: str = "sentinel-tool-token") -> None:  # noqa: S107
        self._auth_token = auth_token
        self._specs: dict[str, ToolSpec] = {}
        self._cache: dict[str, ToolResult] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._specs:
            raise ValueError(f"duplicate tool: {spec.name}")
        self._specs[spec.name] = spec

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": spec.name,
                "permission": spec.permission.value,
                "timeout_seconds": spec.timeout_seconds,
                "max_retries": spec.max_retries,
                "inputSchema": spec.input_model.model_json_schema(),
            }
            for spec in self._specs.values()
        ]

    def get_spec(self, name: str) -> ToolSpec:
        spec = self._specs.get(name)
        if spec is None:
            raise KeyError(f"unknown tool: {name}")
        return spec

    async def call(self, name: str, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        if not secrets_equal(context.auth_token, self._auth_token):
            raise ToolFailure(ErrorCode.AUTH_FAILURE, "tool authentication failed")
        spec = self._specs.get(name)
        if spec is None:
            raise ToolFailure(ErrorCode.NOT_FOUND, f"unknown tool: {name}")
        if spec.permission is PermissionClass.DESTRUCTIVE:
            raise ToolFailure(ErrorCode.POLICY_DENIED, "destructive tools are disabled")
        if spec.permission is PermissionClass.LOW_RISK_WRITE and not context.approved_write:
            raise ToolFailure(ErrorCode.POLICY_DENIED, "write requires explicit approval")
        try:
            request = spec.input_model.model_validate(arguments)
        except ValidationError as exc:
            raise ToolFailure(ErrorCode.MALFORMED_REQUEST, str(exc)) from exc
        cache_key = _call_hash(name, request.model_dump(mode="json"), context.incident_id)
        if cache_key in self._cache:
            return self._cache[cache_key].model_copy(update={"deduplicated": True})
        started = time.perf_counter()
        try:
            output = spec.handler(request, context)
            if inspect.isawaitable(output):
                output = await asyncio.wait_for(output, timeout=spec.timeout_seconds)
        except TimeoutError as exc:
            raise ToolFailure(ErrorCode.TIMEOUT, f"tool timed out: {name}", retryable=True) from exc
        except ToolFailure:
            raise
        except Exception as exc:
            raise ToolFailure(ErrorCode.INTERNAL, f"tool failed: {name}", retryable=False) from exc
        result = ToolResult(
            tool=name,
            data=output,
            duration_ms=(time.perf_counter() - started) * 1000,
        )
        self._cache[cache_key] = result
        return result


def _call_hash(name: str, arguments: dict[str, Any], incident_id: str) -> str:
    value = json.dumps([name, arguments, incident_id], sort_keys=True, default=str)
    return hashlib.sha256(value.encode()).hexdigest()


def secrets_equal(left: str, right: str) -> bool:
    import hmac

    return hmac.compare_digest(left, right)
