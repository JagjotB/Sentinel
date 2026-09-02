from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import BaseModel, Field

from runtime.budgets import BudgetLedger


class ModelRequest(BaseModel):
    purpose: str
    prompt: str
    prompt_version: str = "v1"
    response_schema: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ModelResponse(BaseModel):
    provider: str
    model: str
    content: dict[str, Any]
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float
    duration_ms: float
    retry_count: int = 0


class ModelProvider(Protocol):
    def complete(self, request: ModelRequest, model: str) -> ModelResponse: ...


@dataclass
class DeterministicProvider:
    name: str = "deterministic"

    def complete(self, request: ModelRequest, model: str) -> ModelResponse:
        started = time.perf_counter()
        digest = hashlib.sha256(request.prompt.encode()).hexdigest()
        content = {
            "summary": f"deterministic response {digest[:12]}",
            "purpose": request.purpose,
        }
        input_tokens = max(1, len(request.prompt) // 4)
        output_tokens = max(1, len(json.dumps(content)) // 4)
        return ModelResponse(
            provider=self.name,
            model=model,
            content=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost_usd=0.0,
            duration_ms=(time.perf_counter() - started) * 1000,
        )


class ModelRouter:
    def __init__(
        self,
        providers: dict[str, ModelProvider] | None = None,
        routes: dict[str, tuple[str, str]] | None = None,
    ) -> None:
        self.providers = providers or {"deterministic": DeterministicProvider()}
        self.routes = routes or {
            "summarization": ("deterministic", "sentinel-stub-fast"),
            "diagnosis": ("deterministic", "sentinel-stub-strong"),
            "verification": ("deterministic", "sentinel-stub-strong"),
        }

    def complete(self, request: ModelRequest, ledger: BudgetLedger) -> ModelResponse:
        provider_name, model = self.routes.get(
            request.purpose, ("deterministic", "sentinel-stub-v1")
        )
        provider = self.providers.get(provider_name)
        if provider is None:
            provider = self.providers["deterministic"]
        response = provider.complete(request, model)
        ledger.consume_model(
            response.input_tokens + response.output_tokens, response.estimated_cost_usd
        )
        return response
