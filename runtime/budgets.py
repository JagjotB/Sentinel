from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class BudgetPolicy:
    max_runtime_seconds: float = 300.0
    max_model_tokens: int = 60_000
    max_tool_calls: int = 40
    max_subagents: int = 8
    max_identical_tool_calls: int = 3
    max_cost_usd: float = 1.0

    def as_dict(self) -> dict[str, float | int]:
        return {
            "max_runtime_seconds": self.max_runtime_seconds,
            "max_model_tokens": self.max_model_tokens,
            "max_tool_calls": self.max_tool_calls,
            "max_subagents": self.max_subagents,
            "max_identical_tool_calls": self.max_identical_tool_calls,
            "max_cost_usd": self.max_cost_usd,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> BudgetPolicy:
        allowed = {
            "max_runtime_seconds",
            "max_model_tokens",
            "max_tool_calls",
            "max_subagents",
            "max_identical_tool_calls",
            "max_cost_usd",
        }
        return cls(**{key: item for key, item in value.items() if key in allowed})


class BudgetExceeded(RuntimeError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"budget exceeded: {reason}")
        self.reason = reason


@dataclass
class BudgetLedger:
    policy: BudgetPolicy
    started: float = field(default_factory=time.monotonic)
    model_tokens: int = 0
    tool_calls: int = 0
    subagents: int = 0
    estimated_cost_usd: float = 0.0
    identical_calls: dict[str, int] = field(default_factory=dict)
    elapsed_offset_seconds: float = 0.0

    def check_time(self) -> None:
        if self.elapsed_seconds > self.policy.max_runtime_seconds:
            raise BudgetExceeded("runtime_seconds")

    @property
    def elapsed_seconds(self) -> float:
        return self.elapsed_offset_seconds + time.monotonic() - self.started

    def consume_model(self, tokens: int, cost_usd: float) -> None:
        self.check_time()
        self.model_tokens += tokens
        self.estimated_cost_usd += cost_usd
        if self.model_tokens > self.policy.max_model_tokens:
            raise BudgetExceeded("model_tokens")
        if self.estimated_cost_usd > self.policy.max_cost_usd:
            raise BudgetExceeded("cost_usd")

    def consume_tool(self, fingerprint: str) -> None:
        self.check_time()
        self.tool_calls += 1
        self.identical_calls[fingerprint] = self.identical_calls.get(fingerprint, 0) + 1
        if self.tool_calls > self.policy.max_tool_calls:
            raise BudgetExceeded("tool_calls")
        if self.identical_calls[fingerprint] > self.policy.max_identical_tool_calls:
            raise BudgetExceeded("identical_tool_calls")

    def consume_subagent(self) -> None:
        self.check_time()
        self.subagents += 1
        if self.subagents > self.policy.max_subagents:
            raise BudgetExceeded("subagents")

    def snapshot(self) -> dict[str, Any]:
        return {
            "elapsed_seconds": self.elapsed_seconds,
            "model_tokens": self.model_tokens,
            "tool_calls": self.tool_calls,
            "subagents": self.subagents,
            "estimated_cost_usd": self.estimated_cost_usd,
            "identical_calls": dict(self.identical_calls),
        }

    @classmethod
    def from_snapshot(cls, policy: BudgetPolicy, value: dict[str, Any]) -> BudgetLedger:
        identical = value.get("identical_calls", {})
        if not isinstance(identical, dict):
            identical = {}
        return cls(
            policy=policy,
            model_tokens=int(value.get("model_tokens", 0)),
            tool_calls=int(value.get("tool_calls", 0)),
            subagents=int(value.get("subagents", 0)),
            estimated_cost_usd=float(value.get("estimated_cost_usd", 0.0)),
            identical_calls={str(key): int(item) for key, item in identical.items()},
            elapsed_offset_seconds=float(value.get("elapsed_seconds", 0.0)),
        )
