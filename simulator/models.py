from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Scenario(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str = Field(pattern=r"^[a-z0-9_]+$")
    title: str
    category: str
    service: str
    fault_injector: str
    root_cause: str
    expected_evidence: list[str] = Field(min_length=2)
    acceptable_remediations: list[str] = Field(min_length=1)
    forbidden_actions: list[str] = Field(min_length=1)
    difficulty: Literal["easy", "medium", "hard"]
    seed: int = Field(ge=0)


class RuntimeScenario(BaseModel):
    """Only fields observable by the running system; evaluator labels are intentionally absent."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(pattern=r"^[a-z0-9_]+$")
    title: str
    category: str
    service: str
    difficulty: Literal["easy", "medium", "hard"]
    seed: int = Field(ge=0)


class StructuredLog(BaseModel):
    timestamp: float
    service: str
    level: Literal["INFO", "WARN", "ERROR"]
    message: str
    trace_id: str


class TelemetryPoint(BaseModel):
    timestamp: float
    cpu: float
    memory: float
    request_rate: float
    error_rate: float
    p95_latency: float
    queue_depth: float
    db_connections: float
    network_io: float
