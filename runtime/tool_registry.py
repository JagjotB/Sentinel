from __future__ import annotations

import hashlib
import json
from typing import Any

from mcp.contracts import ToolContext, ToolFailure, ToolResult, ToolServer
from persistence.repository import SentinelRepository
from runtime.budgets import BudgetLedger


class ToolRegistry:
    def __init__(self, repository: SentinelRepository) -> None:
        self.repository = repository
        self._tools: dict[str, ToolServer] = {}

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
        ledger.consume_tool(request_hash)
        try:
            result = await server.call(name, arguments, context)
        except ToolFailure as exc:
            self.repository.add_tool_call(
                incident_id=context.incident_id,
                execution_id=context.execution_id,
                task_id=context.task_id,
                tool_name=name,
                permission=self._permission(name),
                request_hash=request_hash,
                status=exc.code.value,
                duration_ms=0.0,
                retry_count=0,
                evidence_ids=[],
                error=str(exc),
            )
            raise
        self.repository.add_tool_call(
            incident_id=context.incident_id,
            execution_id=context.execution_id,
            task_id=context.task_id,
            tool_name=name,
            permission=self._permission(name),
            request_hash=request_hash,
            status="succeeded",
            duration_ms=result.duration_ms,
            retry_count=0,
            evidence_ids=[item.id for item in result.evidence],
            error=None,
        )
        return result

    def _permission(self, name: str) -> str:
        for schema in self._tools[name].list_tools():
            if schema["name"] == name:
                return str(schema["permission"])
        raise KeyError(name)
