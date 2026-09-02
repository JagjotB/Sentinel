from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ExecutionStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    RESOLVED = "resolved"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    HUMAN_ESCALATION = "human_escalation"
    BLOCKED_EXTERNAL_DEPENDENCY = "blocked_external_dependency"
    FAILED_SYSTEM = "failed_system"

    @property
    def terminal(self) -> bool:
        return self in {
            self.RESOLVED,
            self.INSUFFICIENT_EVIDENCE,
            self.HUMAN_ESCALATION,
            self.BLOCKED_EXTERNAL_DEPENDENCY,
            self.FAILED_SYSTEM,
        }


class TaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class Evidence(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str
    source: str
    kind: str
    summary: str
    raw_reference: str
    payload: dict[str, Any]
    observed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    relevance: float = Field(default=0.5, ge=0.0, le=1.0)


class AgentTask(BaseModel):
    id: str
    parent_id: str | None = None
    agent: str
    title: str
    status: TaskStatus = TaskStatus.PENDING
    inputs: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, Any] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)


class StepRecord(BaseModel):
    id: str
    task_id: str
    agent: str
    status: TaskStatus
    inputs: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, Any] = Field(default_factory=dict)
    model: str | None = None
    tool: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None


class Diagnosis(BaseModel):
    status: Literal["supported", "insufficient_evidence", "escalate"]
    root_cause: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_ids: list[str] = Field(default_factory=list)
    contradictory_evidence_ids: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    recommended_action: str
    risk_class: Literal["read", "low_risk_write", "destructive"]
    reasoning_summary: str = Field(min_length=3, max_length=2000)

    def validate_against(self, evidence_ids: set[str]) -> None:
        referenced = set(self.evidence_ids) | set(self.contradictory_evidence_ids)
        missing = referenced - evidence_ids
        if self.status == "supported" and not self.evidence_ids:
            raise ValueError("a supported diagnosis requires evidence")
        if missing:
            raise ValueError(f"diagnosis references unknown evidence: {sorted(missing)}")


class RuntimeState(BaseModel):
    incident_id: str
    execution_id: str
    trace_id: str
    status: ExecutionStatus = ExecutionStatus.PENDING
    tasks: list[AgentTask] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    steps: list[StepRecord] = Field(default_factory=list)
    diagnosis: Diagnosis | None = None
    remediation: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    checkpoint_sequence: int = 0

    @model_validator(mode="after")
    def diagnosis_has_provenance(self) -> RuntimeState:
        if self.diagnosis:
            self.diagnosis.validate_against({item.id for item in self.evidence})
        return self
