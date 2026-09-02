from __future__ import annotations

from persistence.repository import RemediationRecord, SentinelRepository
from runtime.sandbox import ProposalSandbox
from runtime.state import Diagnosis


class RemediationAgent:
    name = "remediation"

    def __init__(self) -> None:
        self.sandbox = ProposalSandbox()

    def run(
        self, incident_id: str, diagnosis: Diagnosis, repository: SentinelRepository
    ) -> RemediationRecord:
        if diagnosis.status != "supported":
            raise ValueError("remediation requires a verified supported diagnosis")
        patchable = {
            "oom_killed": (
                "infrastructure/kubernetes/demo-services.yaml",
                "- memory: 256Mi\n+ memory: 512Mi",
            ),
            "bad_readiness_probe": (
                "infrastructure/kubernetes/demo-services.yaml",
                "- path: /readyz\n+ path: /healthz",
            ),
            "bad_configmap": (
                "config/checkout.env",
                "- PAYMENTS_URL=http://payment\n+ PAYMENTS_URL=http://payments",
            ),
        }
        if diagnosis.root_cause in patchable:
            path, patch = patchable[diagnosis.root_cause]
            self.sandbox.validate_path(path)
            self.sandbox.validate_patch(patch)
            plan = {
                "type": "patch_proposal",
                "path": path,
                "patch": patch,
                "execution": "requires human approval; never auto-merge",
            }
        else:
            plan = {
                "type": "rollback_proposal",
                "revision": "previous-known-good",
                "execution": "requires human approval; validate health before traffic restore",
            }
        return repository.add_remediation(
            incident_id=incident_id,
            action=diagnosis.recommended_action,
            risk_class="low_risk_write",
            plan=plan,
            validation={
                "diagnosis_supported": True,
                "evidence_ids": diagnosis.evidence_ids,
                "sandbox_valid": True,
                "destructive": False,
            },
            status="pending_approval",
        )
