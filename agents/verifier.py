from __future__ import annotations

import json

from pydantic import BaseModel, Field

from runtime.budgets import BudgetLedger
from runtime.langchain_gateway import LangChainReasoner, ModelCallContext, ModelInvocation
from runtime.state import Diagnosis, Evidence


class VerificationDecision(BaseModel):
    verified: bool
    tested_alternatives: list[str] = Field(default_factory=list)
    contradictory_evidence_ids: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    rationale: str = Field(min_length=3, max_length=1000)


class VerifierAgent:
    name = "verifier"

    ALTERNATIVES = {
        "oom_killed": ("traffic_spike", "db_pool_exhaustion"),
        "db_pool_exhaustion": ("dependency_timeout", "cpu_throttling"),
        "dns_failure": ("network_policy_denied", "dependency_timeout"),
        "queue_saturation": ("downstream_rate_limit", "cpu_throttling"),
    }

    async def run_with_model(
        self,
        diagnosis: Diagnosis,
        evidence: list[Evidence],
        reasoner: LangChainReasoner,
        context: ModelCallContext,
        ledger: BudgetLedger,
    ) -> tuple[Diagnosis, dict[str, object], ModelInvocation]:
        fallback_diagnosis, fallback_report = self.run(diagnosis, evidence)
        tested_alternatives = fallback_report.get("tested_alternatives", [])
        contradictory_evidence_ids = fallback_report.get("contradictory_evidence_ids", [])
        if not isinstance(tested_alternatives, list):
            tested_alternatives = []
        if not isinstance(contradictory_evidence_ids, list):
            contradictory_evidence_ids = []
        fallback = VerificationDecision(
            verified=bool(fallback_report["verified"]),
            tested_alternatives=[str(item) for item in tested_alternatives],
            contradictory_evidence_ids=[str(item) for item in contradictory_evidence_ids],
            missing_evidence=list(fallback_diagnosis.missing_evidence),
            rationale=str(fallback_report.get("reason", "Evidence and alternatives were checked.")),
        )
        decision, invocation = await reasoner.invoke_structured(
            purpose="verification",
            prompt_version="verification-v2",
            system_prompt=(
                "Act as an independent verifier. Attempt to falsify the proposed diagnosis using "
                "the supplied evidence and alternatives. Reject unsupported citations and require "
                "independent corroboration before marking the diagnosis verified."
            ),
            payload={
                "diagnosis": diagnosis.model_dump(mode="json"),
                "evidence": [item.model_dump(mode="json") for item in evidence],
                "alternatives": list(self.ALTERNATIVES.get(diagnosis.root_cause, ())),
            },
            schema=VerificationDecision,
            offline_response=fallback,
            context=context,
            ledger=ledger,
        )
        known_ids = {item.id for item in evidence}
        unknown_ids = set(decision.contradictory_evidence_ids) - known_ids
        if unknown_ids:
            raise ValueError(f"verifier referenced unknown evidence: {sorted(unknown_ids)}")
        report: dict[str, object] = {
            "verified": decision.verified,
            "tested_alternatives": decision.tested_alternatives,
            "contradictory_evidence_ids": decision.contradictory_evidence_ids,
            "missing_evidence": decision.missing_evidence,
            "rationale": decision.rationale,
            "checks": [
                "citation_existence",
                "alternative_signature_search",
                "evidence_coverage",
                "langchain_structured_output",
            ],
        }
        if not decision.verified:
            verified = diagnosis.model_copy(
                update={
                    "status": "insufficient_evidence",
                    "confidence": min(0.49, diagnosis.confidence),
                    "evidence_ids": [],
                    "contradictory_evidence_ids": decision.contradictory_evidence_ids,
                    "missing_evidence": decision.missing_evidence
                    or ["independent signal to resolve contradiction"],
                    "risk_class": "read",
                }
            )
        else:
            verified = diagnosis.model_copy(
                update={"contradictory_evidence_ids": decision.contradictory_evidence_ids}
            )
        verified.validate_against(known_ids)
        return verified, report, invocation

    def run(
        self, diagnosis: Diagnosis, evidence: list[Evidence]
    ) -> tuple[Diagnosis, dict[str, object]]:
        if diagnosis.status != "supported":
            return diagnosis, {"verified": False, "reason": "diagnosis abstained"}
        alternatives = self.ALTERNATIVES.get(diagnosis.root_cause, ())
        contradictions = [
            item.id
            for item in evidence
            if any(alternative in json.dumps(item.payload).lower() for alternative in alternatives)
        ]
        cited_fraction = len(diagnosis.evidence_ids) / max(1, len(evidence))
        verified = len(contradictions) <= 1 and cited_fraction >= 0.08
        report = {
            "verified": verified,
            "tested_alternatives": list(alternatives),
            "contradictory_evidence_ids": contradictions,
            "checks": ["citation_existence", "alternative_signature_search", "evidence_coverage"],
        }
        if not verified:
            return (
                diagnosis.model_copy(
                    update={
                        "status": "insufficient_evidence",
                        "confidence": min(0.49, diagnosis.confidence),
                        "evidence_ids": [],
                        "contradictory_evidence_ids": contradictions,
                        "missing_evidence": ["independent signal to resolve contradiction"],
                        "risk_class": "read",
                    }
                ),
                report,
            )
        return diagnosis.model_copy(update={"contradictory_evidence_ids": contradictions}), report
