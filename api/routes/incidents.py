from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Response, status

from api.dependencies import get_repository, require_mutation_token
from api.schemas.incidents import (
    AlertIn,
    ApprovalIn,
    ApprovalOut,
    EvidenceOut,
    IncidentOut,
    TaskOut,
    TraceEntryOut,
)
from persistence.repository import SentinelRepository

router = APIRouter(prefix="/v1", tags=["incidents"])
Repository = Annotated[SentinelRepository, Depends(get_repository)]


@router.post(
    "/alerts",
    response_model=IncidentOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_mutation_token)],
)
def ingest_alert(
    alert: AlertIn,
    response: Response,
    repository: Repository,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=160),
) -> IncidentOut:
    incident, created = repository.create_incident(
        title=alert.title,
        service=alert.service,
        severity=alert.severity,
        alert=alert.model_dump(mode="json"),
        scenario_id=alert.scenario_id,
        idempotency_key=idempotency_key,
    )
    if not created:
        response.status_code = status.HTTP_200_OK
    return IncidentOut.model_validate(incident)


@router.get("/incidents", response_model=list[IncidentOut])
def list_incidents(repository: Repository) -> list[IncidentOut]:
    return [IncidentOut.model_validate(row) for row in repository.list_incidents()]


@router.get("/incidents/{incident_id}", response_model=IncidentOut)
def get_incident(incident_id: str, repository: Repository) -> IncidentOut:
    return IncidentOut.model_validate(repository.get_incident(incident_id))


@router.get("/incidents/{incident_id}/evidence", response_model=list[EvidenceOut])
def get_evidence(incident_id: str, repository: Repository) -> list[EvidenceOut]:
    repository.get_incident(incident_id)
    return [EvidenceOut.model_validate(row) for row in repository.list_evidence(incident_id)]


@router.get("/incidents/{incident_id}/tasks", response_model=list[TaskOut])
def get_tasks(incident_id: str, repository: Repository) -> list[TaskOut]:
    repository.get_incident(incident_id)
    return [TaskOut.model_validate(row) for row in repository.list_tasks(incident_id)]


@router.get("/incidents/{incident_id}/trace", response_model=list[TraceEntryOut])
def get_trace(incident_id: str, repository: Repository) -> list[TraceEntryOut]:
    repository.get_incident(incident_id)
    return [TraceEntryOut.model_validate(row) for row in repository.list_tool_calls(incident_id)]


@router.post(
    "/incidents/{incident_id}/remediations/{remediation_id}/approval",
    response_model=ApprovalOut,
    dependencies=[Depends(require_mutation_token)],
)
def decide_remediation(
    incident_id: str,
    remediation_id: str,
    decision: ApprovalIn,
    repository: Repository,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=160),
) -> ApprovalOut:
    remediation = repository.get_remediation(remediation_id)
    if remediation.incident_id != incident_id:
        repository.get_incident("not-found")
    approval = repository.add_approval(
        incident_id=incident_id,
        remediation_id=remediation_id,
        decision=decision.decision,
        actor=decision.actor,
        reason=decision.reason,
        idempotency_key=idempotency_key,
    )
    repository.update_remediation_status(remediation_id, decision.decision)
    repository.add_audit(
        incident_id=incident_id,
        event_type="remediation_decision",
        actor=decision.actor,
        allowed=decision.decision == "approved",
        details={"remediation_id": remediation_id, "decision": decision.decision},
    )
    return ApprovalOut.model_validate(approval)
