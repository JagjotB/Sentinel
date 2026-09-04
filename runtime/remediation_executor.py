from __future__ import annotations

from pathlib import Path
from typing import Any

from mcp.contracts import ToolContext
from mcp.git_server.live import LiveGitToolServer
from persistence.models import RemediationRecord
from persistence.repository import SentinelRepository
from runtime.budgets import BudgetLedger, BudgetPolicy
from runtime.sandbox import ProposalSandbox
from runtime.tool_registry import ToolRegistry


class GovernedRemediationExecutor:
    """Materializes approved low-risk proposals without applying or merging them."""

    def __init__(self, repository: SentinelRepository, repository_root: Path) -> None:
        self.repository = repository
        self.repository_root = repository_root.resolve()
        self.sandbox = ProposalSandbox()

    async def execute(self, remediation_id: str, actor: str) -> RemediationRecord:
        remediation = self.repository.get_remediation(remediation_id)
        if remediation.status != "approved":
            raise ValueError("remediation must have an approved decision before execution")
        plan = remediation.plan
        if plan.get("type") != "patch_proposal":
            record = self.repository.update_remediation_execution(
                remediation_id,
                status="approved_manual_execution",
                execution_details={
                    "executed": False,
                    "reason": "rollback proposals require an operator-controlled deployment system",
                },
            )
            self.repository.add_audit(
                incident_id=remediation.incident_id,
                event_type="remediation_manual_execution_required",
                actor=actor,
                allowed=True,
                details={"remediation_id": remediation_id, "action": remediation.action},
            )
            return record
        path, patch = self._validated_patch(plan)
        incident = self.repository.get_incident(remediation.incident_id)
        if not incident.execution_id:
            raise ValueError("approved remediation has no investigation execution")
        execution = self.repository.get_execution(incident.execution_id)
        registry = ToolRegistry(self.repository)
        registry.mount(LiveGitToolServer(self.repository_root))
        result = await registry.call(
            "create_proposed_patch_or_pr",
            {
                "title": remediation.action,
                "path": path,
                "patch": patch,
            },
            ToolContext(
                incident_id=incident.id,
                execution_id=execution.id,
                auth_token="sentinel-tool-token",  # noqa: S106 - local adapter boundary
                approved_write=True,
                trace_id=execution.trace_id,
            ),
            BudgetLedger(BudgetPolicy(max_tool_calls=3, max_identical_tool_calls=1)),
        )
        record = self.repository.update_remediation_execution(
            remediation_id,
            status="proposal_materialized",
            execution_details={
                "executed": True,
                "boundary": "patch_artifact_only",
                **result.data,
            },
        )
        self.repository.add_audit(
            incident_id=incident.id,
            event_type="remediation_proposal_materialized",
            actor=actor,
            allowed=True,
            details={
                "remediation_id": remediation_id,
                "artifact": result.data.get("artifact"),
                "sha256": result.data.get("sha256"),
            },
        )
        return record

    def _validated_patch(self, plan: dict[str, Any]) -> tuple[str, str]:
        path = self.sandbox.validate_path(str(plan.get("path", "")))
        patch = str(plan.get("patch", ""))
        self.sandbox.validate_patch(patch)
        if not patch:
            raise ValueError("approved patch proposal is empty")
        return path, patch
