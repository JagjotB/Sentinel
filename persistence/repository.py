from __future__ import annotations

import hashlib
import json
import secrets
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any, TypeVar

from sqlalchemy import Engine, create_engine, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from persistence.migration_runner import run_migrations
from persistence.models import (
    ApprovalNonceRecord,
    ApprovalRecord,
    AuditRecord,
    BenchmarkRunRecord,
    CheckpointRecord,
    EvidenceRecord,
    ExecutionRecord,
    IdempotencyRecord,
    IncidentRecord,
    ModelCallRecord,
    RemediationRecord,
    TaskRecord,
    ToolCallRecord,
    WorkItemRecord,
)

RecordT = TypeVar("RecordT")


def new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(8)}"


def canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


class ConflictError(RuntimeError):
    pass


class AuthorizationError(RuntimeError):
    pass


class NotFoundError(RuntimeError):
    pass


class SentinelRepository:
    def __init__(self, database_url: str = "sqlite:///./sentinel.db") -> None:
        connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
        self.engine: Engine = create_engine(database_url, connect_args=connect_args)
        run_migrations(self.engine)
        self._sessions = sessionmaker(bind=self.engine, expire_on_commit=False)

    def create_incident(
        self,
        *,
        title: str,
        service: str,
        severity: str,
        alert: dict[str, Any],
        idempotency_key: str,
        scenario_id: str | None = None,
    ) -> tuple[IncidentRecord, bool]:
        request_hash = canonical_hash(alert)
        with self._sessions() as session, session.begin():
            existing = session.get(IdempotencyRecord, ("alert", idempotency_key))
            if existing:
                if existing.request_hash != request_hash:
                    raise ConflictError("idempotency key was reused with a different alert")
                return self._require(session, IncidentRecord, existing.resource_id), False
            incident = IncidentRecord(
                id=new_id("inc"),
                title=title,
                service=service,
                severity=severity,
                status="created",
                alert=alert,
                scenario_id=scenario_id,
            )
            session.add(incident)
            session.add(
                IdempotencyRecord(
                    namespace="alert",
                    key=idempotency_key,
                    resource_id=incident.id,
                    request_hash=request_hash,
                )
            )
            try:
                session.flush()
            except IntegrityError as exc:
                raise ConflictError("concurrent duplicate alert ingestion") from exc
            session.expunge(incident)
            return incident, True

    def get_incident(self, incident_id: str) -> IncidentRecord:
        with self._sessions() as session:
            incident = self._require(session, IncidentRecord, incident_id)
            session.expunge(incident)
            return incident

    def list_incidents(self, limit: int = 100) -> list[IncidentRecord]:
        with self._sessions() as session:
            rows = list(
                session.scalars(
                    select(IncidentRecord).order_by(IncidentRecord.created_at.desc()).limit(limit)
                )
            )
            for row in rows:
                session.expunge(row)
            return rows

    def update_incident(
        self,
        incident_id: str,
        *,
        status: str | None = None,
        execution_id: str | None = None,
        diagnosis: dict[str, Any] | None = None,
    ) -> IncidentRecord:
        with self._sessions() as session, session.begin():
            incident = self._require(session, IncidentRecord, incident_id)
            if status is not None:
                incident.status = status
            if execution_id is not None:
                incident.execution_id = execution_id
            if diagnosis is not None:
                incident.diagnosis = diagnosis
            incident.updated_at = datetime.now(UTC)
            session.flush()
            session.expunge(incident)
            return incident

    def create_execution(
        self, incident_id: str, trace_id: str, budget: dict[str, Any]
    ) -> ExecutionRecord:
        with self._sessions() as session, session.begin():
            self._require(session, IncidentRecord, incident_id)
            execution = ExecutionRecord(
                id=new_id("exec"),
                incident_id=incident_id,
                state="pending",
                trace_id=trace_id,
                budget=budget,
            )
            session.add(execution)
            session.flush()
            session.expunge(execution)
            return execution

    def get_execution(self, execution_id: str) -> ExecutionRecord:
        with self._sessions() as session:
            execution = self._require(session, ExecutionRecord, execution_id)
            session.expunge(execution)
            return execution

    def enqueue_investigation(
        self,
        incident_id: str,
        *,
        scenario_id: str | None,
        provider_mode: str,
        parent_trace_id: str | None = None,
        max_attempts: int = 3,
    ) -> tuple[WorkItemRecord, bool]:
        with self._sessions() as session, session.begin():
            self._require(session, IncidentRecord, incident_id)
            existing = session.scalar(
                select(WorkItemRecord).where(WorkItemRecord.incident_id == incident_id)
            )
            if existing is not None:
                session.expunge(existing)
                return existing, False
            record = WorkItemRecord(
                id=new_id("work"),
                incident_id=incident_id,
                scenario_id=scenario_id,
                provider_mode=provider_mode,
                parent_trace_id=parent_trace_id,
                status="queued",
                max_attempts=max_attempts,
            )
            session.add(record)
            session.flush()
            session.expunge(record)
            return record, True

    def get_work_item(self, work_item_id: str) -> WorkItemRecord:
        with self._sessions() as session:
            record = self._require(session, WorkItemRecord, work_item_id)
            session.expunge(record)
            return record

    def get_incident_work_item(self, incident_id: str) -> WorkItemRecord:
        with self._sessions() as session:
            record = session.scalar(
                select(WorkItemRecord).where(WorkItemRecord.incident_id == incident_id)
            )
            if record is None:
                raise NotFoundError(f"WorkItemRecord not found for incident: {incident_id}")
            session.expunge(record)
            return record

    def claim_work(
        self,
        worker_id: str,
        *,
        lease_seconds: float = 60.0,
        now: datetime | None = None,
    ) -> WorkItemRecord | None:
        claimed_at = now or datetime.now(UTC)
        with self._sessions() as session, session.begin():
            eligible = (
                WorkItemRecord.attempts < WorkItemRecord.max_attempts,
                WorkItemRecord.available_at <= claimed_at,
                or_(
                    WorkItemRecord.status == "queued",
                    (
                        (WorkItemRecord.status == "leased")
                        & (WorkItemRecord.lease_expires_at <= claimed_at)
                    ),
                ),
            )
            statement = (
                select(WorkItemRecord)
                .where(*eligible)
                .order_by(WorkItemRecord.available_at, WorkItemRecord.created_at)
                .limit(1)
            )
            if self.engine.dialect.name != "sqlite":
                statement = statement.with_for_update(skip_locked=True)
            record = session.scalar(statement)
            if record is None:
                return None
            if self.engine.dialect.name == "sqlite":
                claimed_id = session.scalar(
                    update(WorkItemRecord)
                    .where(WorkItemRecord.id == record.id, *eligible)
                    .values(
                        status="leased",
                        attempts=WorkItemRecord.attempts + 1,
                        lease_owner=worker_id,
                        lease_expires_at=claimed_at + timedelta(seconds=lease_seconds),
                        updated_at=claimed_at,
                    )
                    .returning(WorkItemRecord.id)
                    .execution_options(synchronize_session=False)
                )
                if claimed_id is None:
                    return None
                session.refresh(record)
                session.expunge(record)
                return record
            record.status = "leased"
            record.attempts += 1
            record.lease_owner = worker_id
            record.lease_expires_at = claimed_at + timedelta(seconds=lease_seconds)
            record.updated_at = claimed_at
            session.flush()
            session.expunge(record)
            return record

    def heartbeat_work(
        self,
        work_item_id: str,
        worker_id: str,
        *,
        lease_seconds: float = 60.0,
    ) -> WorkItemRecord:
        now = datetime.now(UTC)
        with self._sessions() as session, session.begin():
            record = self._require(session, WorkItemRecord, work_item_id)
            self._require_lease(record, worker_id)
            record.lease_expires_at = now + timedelta(seconds=lease_seconds)
            record.updated_at = now
            session.flush()
            session.expunge(record)
            return record

    def complete_work(
        self,
        work_item_id: str,
        worker_id: str,
        *,
        execution_id: str,
    ) -> WorkItemRecord:
        now = datetime.now(UTC)
        with self._sessions() as session, session.begin():
            record = self._require(session, WorkItemRecord, work_item_id)
            self._require_lease(record, worker_id)
            record.status = "completed"
            record.execution_id = execution_id
            record.lease_owner = None
            record.lease_expires_at = None
            record.completed_at = now
            record.updated_at = now
            session.flush()
            session.expunge(record)
            return record

    def fail_work(
        self,
        work_item_id: str,
        worker_id: str,
        error: str,
        *,
        retry_delay_seconds: float = 1.0,
    ) -> WorkItemRecord:
        now = datetime.now(UTC)
        with self._sessions() as session, session.begin():
            record = self._require(session, WorkItemRecord, work_item_id)
            self._require_lease(record, worker_id)
            exhausted = record.attempts >= record.max_attempts
            record.status = "failed" if exhausted else "queued"
            record.available_at = now + timedelta(seconds=retry_delay_seconds)
            record.last_error = error[:4_000]
            record.lease_owner = None
            record.lease_expires_at = None
            record.completed_at = now if exhausted else None
            record.updated_at = now
            session.flush()
            session.expunge(record)
            return record

    def set_execution_state(self, execution_id: str, state: str) -> None:
        with self._sessions() as session, session.begin():
            execution = self._require(session, ExecutionRecord, execution_id)
            execution.state = state
            if state in {"resolved", "insufficient_evidence", "human_escalation", "failed_system"}:
                execution.completed_at = datetime.now(UTC)

    def add_task(self, **values: Any) -> TaskRecord:
        return self._add(TaskRecord(id=values.pop("id", new_id("task")), **values))

    def update_task(
        self, task_id: str, *, status: str, outputs: dict[str, Any], evidence_ids: list[str]
    ) -> None:
        with self._sessions() as session, session.begin():
            task = self._require(session, TaskRecord, task_id)
            task.status = status
            task.outputs = outputs
            task.evidence_ids = evidence_ids
            task.completed_at = datetime.now(UTC)

    def add_evidence(self, **values: Any) -> EvidenceRecord:
        evidence_id = values.pop("id", f"ev_{canonical_hash(values)[:16]}")
        with self._sessions() as session, session.begin():
            existing = session.get(EvidenceRecord, evidence_id)
            if existing:
                session.expunge(existing)
                return existing
            record = EvidenceRecord(id=evidence_id, **values)
            session.add(record)
            session.flush()
            session.expunge(record)
            return record

    def list_evidence(self, incident_id: str) -> list[EvidenceRecord]:
        return self._list(EvidenceRecord, EvidenceRecord.incident_id == incident_id)

    def list_tasks(self, incident_id: str) -> list[TaskRecord]:
        return self._list(TaskRecord, TaskRecord.incident_id == incident_id)

    def add_checkpoint(self, **values: Any) -> CheckpointRecord:
        return self._add(CheckpointRecord(id=values.pop("id", new_id("cp")), **values))

    def latest_checkpoint(self, execution_id: str) -> CheckpointRecord | None:
        with self._sessions() as session:
            checkpoint = session.scalar(
                select(CheckpointRecord)
                .where(CheckpointRecord.execution_id == execution_id)
                .order_by(CheckpointRecord.sequence.desc())
                .limit(1)
            )
            if checkpoint:
                session.expunge(checkpoint)
            return checkpoint

    def add_tool_call(self, **values: Any) -> ToolCallRecord:
        return self._add(ToolCallRecord(id=values.pop("id", new_id("tool")), **values))

    def add_model_call(self, **values: Any) -> ModelCallRecord:
        return self._add(ModelCallRecord(id=values.pop("id", new_id("model")), **values))

    def list_model_calls(self, incident_id: str) -> list[ModelCallRecord]:
        return self._list(ModelCallRecord, ModelCallRecord.incident_id == incident_id)

    def add_remediation(self, **values: Any) -> RemediationRecord:
        return self._add(RemediationRecord(id=values.pop("id", new_id("rem")), **values))

    def get_remediation(self, remediation_id: str) -> RemediationRecord:
        with self._sessions() as session:
            record = self._require(session, RemediationRecord, remediation_id)
            session.expunge(record)
            return record

    def register_approval_nonce(
        self,
        *,
        nonce: str,
        incident_id: str,
        remediation_id: str,
        actor: str,
        expires_at: int,
    ) -> ApprovalNonceRecord:
        with self._sessions() as session, session.begin():
            self._require(session, IncidentRecord, incident_id)
            remediation = self._require(session, RemediationRecord, remediation_id)
            if remediation.incident_id != incident_id:
                raise NotFoundError(f"RemediationRecord not found: {remediation_id}")
            record = ApprovalNonceRecord(
                nonce=nonce,
                incident_id=incident_id,
                remediation_id=remediation_id,
                actor=actor,
                expires_at=expires_at,
            )
            session.add(record)
            session.flush()
            session.expunge(record)
            return record

    def record_approval_decision(
        self,
        *,
        nonce: str,
        incident_id: str,
        remediation_id: str,
        decision: str,
        actor: str,
        reason: str,
        idempotency_key: str,
    ) -> tuple[ApprovalRecord, bool]:
        request_hash = canonical_hash(
            {
                "incident_id": incident_id,
                "remediation_id": remediation_id,
                "decision": decision,
                "actor": actor,
                "reason": reason,
            }
        )
        now = datetime.now(UTC)
        with self._sessions() as session, session.begin():
            existing = session.scalar(
                select(ApprovalRecord).where(
                    ApprovalRecord.idempotency_key == idempotency_key
                )
            )
            if existing is not None:
                if existing.request_hash != request_hash:
                    raise ConflictError(
                        "approval idempotency key was reused with a different decision"
                    )
                session.expunge(existing)
                return existing, False
            consumed_nonce = session.scalar(
                update(ApprovalNonceRecord)
                .where(
                    ApprovalNonceRecord.nonce == nonce,
                    ApprovalNonceRecord.incident_id == incident_id,
                    ApprovalNonceRecord.remediation_id == remediation_id,
                    ApprovalNonceRecord.actor == actor,
                    ApprovalNonceRecord.expires_at >= int(now.timestamp()),
                    ApprovalNonceRecord.used_at.is_(None),
                )
                .values(used_at=now)
                .returning(ApprovalNonceRecord.nonce)
                .execution_options(synchronize_session=False)
            )
            if consumed_nonce is None:
                raise AuthorizationError("approval token was already used or was not issued")
            remediation = self._require(session, RemediationRecord, remediation_id)
            if remediation.incident_id != incident_id:
                raise NotFoundError(f"RemediationRecord not found: {remediation_id}")
            record = ApprovalRecord(
                id=new_id("approval"),
                incident_id=incident_id,
                remediation_id=remediation_id,
                decision=decision,
                actor=actor,
                reason=reason,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
            )
            remediation.status = decision
            session.add(record)
            session.add(
                AuditRecord(
                    id=new_id("audit"),
                    incident_id=incident_id,
                    event_type="remediation_decision",
                    actor=actor,
                    allowed=decision == "approved",
                    details={
                        "remediation_id": remediation_id,
                        "decision": decision,
                        "approval_nonce": nonce,
                    },
                )
            )
            session.flush()
            session.expunge(record)
            return record, True

    def list_remediations(self, incident_id: str) -> list[RemediationRecord]:
        return self._list(RemediationRecord, RemediationRecord.incident_id == incident_id)

    def list_approvals(self, incident_id: str) -> list[ApprovalRecord]:
        return self._list(ApprovalRecord, ApprovalRecord.incident_id == incident_id)

    def update_remediation_execution(
        self,
        remediation_id: str,
        *,
        status: str,
        execution_details: dict[str, Any],
    ) -> RemediationRecord:
        with self._sessions() as session, session.begin():
            remediation = self._require(session, RemediationRecord, remediation_id)
            remediation.status = status
            remediation.validation = {
                **remediation.validation,
                "execution": execution_details,
            }
            session.flush()
            session.expunge(remediation)
            return remediation

    def add_benchmark_run(self, **values: Any) -> BenchmarkRunRecord:
        return self._add(BenchmarkRunRecord(id=values.pop("id", new_id("bench")), **values))

    def add_audit(self, **values: Any) -> AuditRecord:
        return self._add(AuditRecord(id=values.pop("id", new_id("audit")), **values))

    def list_tool_calls(self, incident_id: str) -> list[ToolCallRecord]:
        return self._list(ToolCallRecord, ToolCallRecord.incident_id == incident_id)

    @staticmethod
    def _require_lease(record: WorkItemRecord, worker_id: str) -> None:
        if record.status != "leased" or record.lease_owner != worker_id:
            raise ConflictError("work item is not leased by this worker")

    def _add(self, record: RecordT) -> RecordT:
        with self._sessions() as session, session.begin():
            session.add(record)
            session.flush()
            session.expunge(record)
            return record

    def _list(self, record_type: type[RecordT], predicate: Any) -> list[RecordT]:
        with self._sessions() as session:
            rows: Sequence[RecordT] = session.scalars(select(record_type).where(predicate)).all()
            result = list(rows)
            for row in result:
                session.expunge(row)
            return result

    @staticmethod
    def _require(session: Session, record_type: type[RecordT], record_id: Any) -> RecordT:
        record = session.get(record_type, record_id)
        if record is None:
            raise NotFoundError(f"{record_type.__name__} not found: {record_id}")
        return record
