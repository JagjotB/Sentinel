from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from langchain_core.tools import BaseTool, StructuredTool

from mcp.contracts import ErrorCode, ToolContext, ToolFailure, ToolResult, ToolServer
from persistence.repository import SentinelRepository
from runtime.budgets import BudgetExceeded, BudgetLedger
from runtime.retries import CircuitBreaker, CircuitOpenError, with_retries
from runtime.tracing import TOOL_CALLS, span


class ToolRegistry:
    def __init__(self, repository: SentinelRepository) -> None:
        self.repository = repository
        self._tools: dict[str, ToolServer] = {}
        self._breakers: dict[str, CircuitBreaker] = {}

    def mount(self, server: ToolServer) -> None:
        for spec in server.list_tools():
            name = str(spec["name"])
            if name in self._tools:
                raise ValueError(f"tool already mounted: {name}")
            self._tools[name] = server

    def schemas(self) -> list[dict[str, Any]]:
        schemas: list[dict[str, Any]] = []
        seen: set[int] = set()
        for server in self._tools.values():
            if id(server) not in seen:
                schemas.extend(server.list_tools())
                seen.add(id(server))
        return schemas

    def langchain_tool(
        self,
        name: str,
        context: ToolContext,
        ledger: BudgetLedger,
    ) -> BaseTool:
        """Expose an audited registry call as a typed LangChain tool."""
        server = self._tools.get(name)
        if server is None:
            raise KeyError(f"unknown tool: {name}")
        spec = server.get_spec(name)

        async def invoke_tool(**arguments: Any) -> dict[str, Any]:
            result = await self.call(name, arguments, context, ledger)
            return result.model_dump(mode="json")

        return StructuredTool.from_function(
            coroutine=invoke_tool,
            name=name,
            description=(
                f"Sentinel {spec.permission.value} tool. Inputs are schema-validated and calls are "
                "budgeted, authorized, traced, and persisted."
            ),
            args_schema=spec.input_model,
        )

    async def call(
        self,
        name: str,
        arguments: dict[str, Any],
        context: ToolContext,
        ledger: BudgetLedger,
    ) -> ToolResult:
        server = self._tools.get(name)
        if server is None:
            raise KeyError(f"unknown tool: {name}")
        request_hash = hashlib.sha256(
            json.dumps([name, arguments], sort_keys=True, default=str).encode()
        ).hexdigest()
        spec = server.get_spec(name)
        breaker = self._breakers.setdefault(name, CircuitBreaker())
        attempts = 0
        started = time.perf_counter()

        async def operation() -> ToolResult:
            nonlocal attempts
            attempts += 1
            ledger.consume_tool(request_hash)
            return await server.call(name, arguments, context)

        try:
            with span(
                "tool.call",
                tool=name,
                incident_id=context.incident_id,
                execution_id=context.execution_id,
                trace_id=context.trace_id,
            ):
                result, retry_count = await with_retries(
                    operation,
                    retries=spec.max_retries,
                    timeout_seconds=spec.timeout_seconds + 0.25,
                    retryable=lambda exc: (
                        isinstance(exc, TimeoutError)
                        or isinstance(exc, ToolFailure) and exc.retryable
                    ),
                    breaker=breaker,
                )
        except Exception as exc:
            duration_ms = (time.perf_counter() - started) * 1000
            if isinstance(exc, BudgetExceeded):
                self.repository.add_tool_call(
                    incident_id=context.incident_id,
                    execution_id=context.execution_id,
                    task_id=context.task_id,
                    tool_name=name,
                    permission=self._permission(name),
                    request_hash=request_hash,
                    status="budget_exceeded",
                    duration_ms=duration_ms,
                    retry_count=max(0, attempts - 1),
                    evidence_ids=[],
                    error=str(exc),
                )
                TOOL_CALLS.labels(tool=name, status="budget_exceeded").inc()
                raise
            if isinstance(exc, ToolFailure):
                status = exc.code.value
                failure = exc
            elif isinstance(exc, CircuitOpenError):
                status = "circuit_open"
                failure = ToolFailure(
                    code=ErrorCode.PROVIDER_UNAVAILABLE,
                    message=str(exc),
                    retryable=True,
                )
            else:
                status = "internal"
                failure = ToolFailure(
                    code=ErrorCode.INTERNAL,
                    message=f"tool registry failed: {name}",
                    retryable=False,
                )
            self.repository.add_tool_call(
                incident_id=context.incident_id,
                execution_id=context.execution_id,
                task_id=context.task_id,
                tool_name=name,
                permission=self._permission(name),
                request_hash=request_hash,
                status=status,
                duration_ms=duration_ms,
                retry_count=max(0, attempts - 1),
                evidence_ids=[],
                error=str(exc),
            )
            TOOL_CALLS.labels(tool=name, status=status).inc()
            if failure is exc:
                raise
            raise failure from exc
        self.repository.add_tool_call(
            incident_id=context.incident_id,
            execution_id=context.execution_id,
            task_id=context.task_id,
            tool_name=name,
            permission=self._permission(name),
            request_hash=request_hash,
            status="succeeded",
            duration_ms=(time.perf_counter() - started) * 1000,
            retry_count=retry_count,
            evidence_ids=[item.id for item in result.evidence],
            error=None,
        )
        TOOL_CALLS.labels(tool=name, status="succeeded").inc()
        return result

    def _permission(self, name: str) -> str:
        for schema in self._tools[name].list_tools():
            if schema["name"] == name:
                return str(schema["permission"])
        raise KeyError(name)
