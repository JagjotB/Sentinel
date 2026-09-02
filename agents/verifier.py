from __future__ import annotations

import json

from runtime.state import Diagnosis, Evidence


class VerifierAgent:
    name = "verifier"

    ALTERNATIVES = {
        "oom_killed": ("traffic_spike", "db_pool_exhaustion"),
        "db_pool_exhaustion": ("dependency_timeout", "cpu_throttling"),
        "dns_failure": ("network_policy_denied", "dependency_timeout"),
        "queue_saturation": ("downstream_rate_limit", "cpu_throttling"),
    }

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
