from __future__ import annotations

import secrets
import time
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Response, status

from api.dependencies import get_repository, require_mutation_token
from api.schemas.incidents import (
    AlertIn,
    ApprovalIn,
    ApprovalOut,
    ApprovalTokenOut,
    EvidenceOut,
    IncidentOut,
    RemediationOut,
    TaskOut,
    TraceEntryOut,
    WorkItemOut,
)
from api.settings import get_settings
from persistence.repository import SentinelRepository
from runtime.executor import RuntimeExecutor
from runtime.remediation_executor import GovernedRemediationExecutor
from runtime.state import RuntimeState
from safety.approvals import ApprovalClaims, ApprovalTokenError, ApprovalTokenManager

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
    if created:
        settings = get_settings()
        provider_mode = settings.tool_provider if alert.scenario_id else "live"
        repository.enqueue_investigation(
            incident.id,
            scenario_id=alert.scenario_id,
            provider_mode=provider_mode,
            max_attempts=settings.worker_max_attempts,
        )
        incident = repository.update_incident(incident.id, status="queued")
    if not created:
        response.status_code = status.HTTP_200_OK
    return IncidentOut.model_validate(incident)


@router.get("/incidents", response_model=list[IncidentOut])
def list_incidents(repository: Repository) -> list[IncidentOut]:
    return [IncidentOut.model_validate(row) for row in repository.list_incidents()]


@router.get("/incidents/{incident_id}", response_model=IncidentOut)
def get_incident(incident_id: str, repository: Repository) -> IncidentOut:
    return IncidentOut.model_validate(repository.get_incident(incident_id))


@router.get("/incidents/{incident_id}/state", response_model=RuntimeState)
def get_incident_state(incident_id: str, repository: Repository) -> RuntimeState:
    incident = repository.get_incident(incident_id)
    if not incident.execution_id:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="incident has no execution yet")
    return RuntimeExecutor(repository).resume(incident.execution_id)


@router.get("/incidents/{incident_id}/evidence", response_model=list[EvidenceOut])
def get_evidence(incident_id: str, repository: Repository) -> list[EvidenceOut]:
    repository.get_incident(incident_id)
    return [EvidenceOut.model_validate(row) for row in repository.list_evidence(incident_id)]


@router.get("/incidents/{incident_id}/tasks", response_model=list[TaskOut])
def get_tasks(incident_id: str, repository: Repository) -> list[TaskOut]:
    repository.get_incident(incident_id)
    return [TaskOut.model_validate(row) for row in repository.list_tasks(incident_id)]


@router.get("/incidents/{incident_id}/work", response_model=WorkItemOut)
def get_work_item(incident_id: str, repository: Repository) -> WorkItemOut:
    repository.get_incident(incident_id)
    return WorkItemOut.model_validate(repository.get_incident_work_item(incident_id))


@router.get("/incidents/{incident_id}/remediations", response_model=list[RemediationOut])
def get_remediations(incident_id: str, repository: Repository) -> list[RemediationOut]:
    repository.get_incident(incident_id)
    return [
        RemediationOut.model_validate(row)
        for row in repository.list_remediations(incident_id)
    ]


@router.get("/incidents/{incident_id}/approvals", response_model=list[ApprovalOut])
def get_approvals(incident_id: str, repository: Repository) -> list[ApprovalOut]:
    repository.get_incident(incident_id)
    return [ApprovalOut.model_validate(row) for row in repository.list_approvals(incident_id)]


@router.get("/incidents/{incident_id}/trace", response_model=list[TraceEntryOut])
def get_trace(incident_id: str, repository: Repository) -> list[TraceEntryOut]:
    repository.get_incident(incident_id)
    return [TraceEntryOut.model_validate(row) for row in repository.list_tool_calls(incident_id)]


@router.post(
    "/incidents/{incident_id}/remediations/{remediation_id}/approval-token",
    response_model=ApprovalTokenOut,
    dependencies=[Depends(require_mutation_token)],
)
def issue_approval_token(
    incident_id: str,
    remediation_id: str,
    actor: str,
    repository: Repository,
) -> ApprovalTokenOut:
    remediation = repository.get_remediation(remediation_id)
    if remediation.incident_id != incident_id:
        repository.get_incident("not-found")
    expires_at = int(time.time()) + 300
    claims = ApprovalClaims(
        incident_id=incident_id,
        remediation_id=remediation_id,
        actor=actor,
        expires_at=expires_at,
        nonce=secrets.token_hex(8),
    )
    repository.register_approval_nonce(**claims.model_dump())
    token = ApprovalTokenManager(get_settings().approval_secret).issue(claims)
    return ApprovalTokenOut(token=token, expires_at=expires_at)


@router.post(
    "/incidents/{incident_id}/remediations/{remediation_id}/approval",
    response_model=ApprovalOut,
    dependencies=[Depends(require_mutation_token)],
)
async def decide_remediation(
    incident_id: str,
    remediation_id: str,
    decision: ApprovalIn,
    repository: Repository,
    approval_token: str = Header(alias="X-Approval-Token", min_length=32),
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=160),
) -> ApprovalOut:
    remediation = repository.get_remediation(remediation_id)
    if remediation.incident_id != incident_id:
        repository.get_incident("not-found")
    try:
        claims = ApprovalTokenManager(get_settings().approval_secret).verify(
            approval_token,
            incident_id=incident_id,
            remediation_id=remediation_id,
            actor=decision.actor,
        )
    except ApprovalTokenError as exc:
        from fastapi import HTTPException

        raise HTTPException(status_code=403, detail=str(exc)) from exc
    approval, created = repository.record_approval_decision(
        nonce=claims.nonce,
        incident_id=incident_id,
        remediation_id=remediation_id,
        decision=decision.decision,
        actor=decision.actor,
        reason=decision.reason,
        idempotency_key=idempotency_key,
    )
    if created and decision.decision == "approved":
        await GovernedRemediationExecutor(
            repository,
            get_settings().resolved_git_repository_path,
        ).execute(remediation_id, decision.actor)
    return ApprovalOut.model_validate(approval)
