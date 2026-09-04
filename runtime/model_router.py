from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any, Protocol, cast

from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from runtime.budgets import BudgetLedger
from runtime.retries import CircuitBreaker, CircuitOpenError


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
        offline_response = request.metadata.get("offline_response")
        if isinstance(offline_response, dict):
            content = offline_response
        else:
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


@dataclass
class LangChainProvider:
    """Provider adapter for any LangChain-supported hosted or local chat model."""

    name: str
    chat_model: BaseChatModel

    def complete(self, request: ModelRequest, model: str) -> ModelResponse:
        started = time.perf_counter()
        message = self.chat_model.invoke([HumanMessage(content=request.prompt)])
        content = self._json_object(message.content)
        usage: Any = message.usage_metadata or {}
        return ModelResponse(
            provider=self.name,
            model=model,
            content=content,
            input_tokens=int(usage.get("input_tokens", 0)),
            output_tokens=int(usage.get("output_tokens", 0)),
            estimated_cost_usd=float(message.response_metadata.get("estimated_cost_usd", 0.0)),
            duration_ms=(time.perf_counter() - started) * 1000,
        )

    @staticmethod
    def _json_object(content: str | list[str | dict[str, Any]]) -> dict[str, Any]:
        if isinstance(content, str):
            rendered = content.strip()
        else:
            rendered = "".join(
                str(block.get("text", "")) if isinstance(block, dict) else block
                for block in content
            ).strip()
        if rendered.startswith("```"):
            lines = rendered.splitlines()
            rendered = "\n".join(lines[1:-1]).strip()
        parsed = json.loads(rendered)
        if not isinstance(parsed, dict):
            raise ValueError("model response must be a JSON object")
        return cast(dict[str, Any], parsed)


class ModelRouter:
    def __init__(
        self,
        providers: dict[str, ModelProvider] | None = None,
        routes: dict[str, tuple[str, str]] | None = None,
        max_provider_retries: int = 1,
    ) -> None:
        self.providers = providers or {"deterministic": DeterministicProvider()}
        self.routes = routes or {
            "summarization": ("deterministic", "sentinel-stub-fast"),
            "diagnosis": ("deterministic", "sentinel-stub-strong"),
            "verification": ("deterministic", "sentinel-stub-strong"),
        }
        self.max_provider_retries = max_provider_retries
        self._breakers: dict[str, CircuitBreaker] = {}

    def complete(self, request: ModelRequest, ledger: BudgetLedger) -> ModelResponse:
        provider_name, model = self.routes.get(
            request.purpose, ("deterministic", "sentinel-stub-v1")
        )
        provider = self.providers.get(provider_name)
        fallback = self.providers.get("deterministic", DeterministicProvider())
        if provider is None:
            provider = fallback
        if provider is fallback:
            response = provider.complete(request, model)
        else:
            response = self._complete_with_fallback(
                provider_name,
                provider,
                fallback,
                request,
                model,
            )
        ledger.consume_model(
            response.input_tokens + response.output_tokens, response.estimated_cost_usd
        )
        return response

    def _complete_with_fallback(
        self,
        provider_name: str,
        provider: ModelProvider,
        fallback: ModelProvider,
        request: ModelRequest,
        model: str,
    ) -> ModelResponse:
        breaker = self._breakers.setdefault(provider_name, CircuitBreaker())
        failures = 0
        for attempt in range(self.max_provider_retries + 1):
            try:
                breaker.before_call()
                response = provider.complete(request, model)
                breaker.success()
                return response.model_copy(update={"retry_count": attempt})
            except CircuitOpenError:
                failures = max(1, failures)
                break
            except Exception:
                failures += 1
                breaker.failure()
                if attempt < self.max_provider_retries:
                    time.sleep(0.01 * (2**attempt))
        return fallback.complete(request, "sentinel-stub-fallback").model_copy(
            update={"retry_count": failures}
        )


def build_model_router(provider_name: str, model_name: str) -> ModelRouter:
    """Create a router from application configuration without hiding setup failures."""
    if provider_name == "deterministic":
        return ModelRouter(
            routes={
                "summarization": (provider_name, model_name),
                "diagnosis": (provider_name, model_name),
                "verification": (provider_name, model_name),
            }
        )
    try:
        initialized = init_chat_model(
            model=model_name,
            model_provider=provider_name,
            temperature=0,
        )
    except (ImportError, ValueError) as exc:
        raise RuntimeError(
            f"could not initialize LangChain provider {provider_name!r}; "
            "install the matching provider extra and verify credentials"
        ) from exc
    return ModelRouter(
        providers={
            provider_name: LangChainProvider(provider_name, initialized),
            "deterministic": DeterministicProvider(),
        },
        routes={
            "summarization": (provider_name, model_name),
            "diagnosis": (provider_name, model_name),
            "verification": (provider_name, model_name),
        },
    )
