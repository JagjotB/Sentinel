from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class AlertIn(BaseModel):
    title: str = Field(min_length=3, max_length=240)
    service: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_.-]+$")
    severity: Literal["SEV-1", "SEV-2", "SEV-3", "SEV-4"]
    labels: dict[str, str] = Field(default_factory=dict)
    annotations: dict[str, str] = Field(default_factory=dict)
    metrics: dict[str, float] = Field(default_factory=dict)
    scenario_id: str | None = None


class IncidentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    title: str
    service: str
    severity: str
    status: str
    scenario_id: str | None
    execution_id: str | None
    diagnosis: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


class EvidenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    source: str
    kind: str
    summary: str
    raw_reference: str
    payload: dict[str, Any]
    observed_at: datetime


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    parent_id: str | None
    agent: str
    title: str
    status: str
    inputs: dict[str, Any]
    outputs: dict[str, Any]
    evidence_ids: list[str]


class WorkItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    incident_id: str
    provider_mode: str
    status: str
    attempts: int
    max_attempts: int
    lease_owner: str | None
    lease_expires_at: datetime | None
    execution_id: str | None
    last_error: str | None
    created_at: datetime
    updated_at: datetime


class TraceEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    tool_name: str
    permission: str
    status: str
    duration_ms: float
    retry_count: int
    evidence_ids: list[str]
    error: str | None
    created_at: datetime


class ApprovalIn(BaseModel):
    decision: Literal["approved", "rejected"]
    actor: str = Field(min_length=2, max_length=120)
    reason: str = Field(min_length=3, max_length=1000)


class ApprovalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    remediation_id: str
    decision: str
    actor: str
    reason: str
    created_at: datetime


class ApprovalTokenOut(BaseModel):
    token: str
    expires_at: int


class ScenarioRunIn(BaseModel):
    scenario_id: str = Field(pattern=r"^[a-z0-9_]+$")


class ErrorOut(BaseModel):
    code: str
    message: str
    request_id: str
