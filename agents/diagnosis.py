from __future__ import annotations

import json
import re

from runtime.state import Diagnosis, Evidence
from simulator.catalog import FAULT_SPECS


class DiagnosisAgent:
    name = "diagnosis"

    def run(self, evidence: list[Evidence]) -> tuple[Diagnosis, list[dict[str, object]]]:
        rendered = [
            (
                item,
                f"{item.summary} {json.dumps(item.payload, sort_keys=True, default=str)}".lower(),
            )
            for item in evidence
        ]
        hypotheses: list[dict[str, object]] = []
        for _, cause, _, _, expected, remediations in FAULT_SPECS:
            signatures = set(cause.split("_")) | {
                token for evidence_name in expected for token in evidence_name.split("_")
            }
            scores: list[tuple[float, str]] = []
            for item, text in rendered:
                matched = sum(
                    1 for signature in signatures if re.search(rf"\b{re.escape(signature)}\b", text)
                )
                exact = 3 if cause in text else 0
                score = item.relevance * (matched + exact)
                if score > 0:
                    scores.append((score, item.id))
            hypotheses.append(
                {
                    "root_cause": cause,
                    "score": sum(score for score, _ in scores),
                    "evidence_ids": [item_id for _, item_id in sorted(scores, reverse=True)],
                    "recommended_action": remediations[0],
                }
            )
        hypotheses.sort(key=lambda item: float(item["score"]), reverse=True)
        leader = hypotheses[0]
        runner_up = hypotheses[1]
        leader_score = float(leader["score"])
        margin = leader_score - float(runner_up["score"])
        evidence_ids = list(dict.fromkeys(leader["evidence_ids"]))[:8]
        confidence = min(0.98, 0.45 + 0.04 * leader_score + 0.03 * max(0.0, margin))
        supported = len(evidence_ids) >= 2 and confidence >= 0.62
        diagnosis = Diagnosis(
            status="supported" if supported else "insufficient_evidence",
            root_cause=str(leader["root_cause"]) if supported else "undetermined",
            confidence=confidence if supported else min(confidence, 0.49),
            evidence_ids=evidence_ids if supported else [],
            missing_evidence=[] if supported else ["additional corroborating signal"],
            recommended_action=str(leader["recommended_action"])
            if supported
            else "collect evidence",
            risk_class="low_risk_write" if supported else "read",
            reasoning_summary=(
                "Evidence-derived signatures were ranked across infrastructure, telemetry, logs, "
                "changes, and history. No hidden chain-of-thought is persisted."
            ),
        )
        diagnosis.validate_against({item.id for item in evidence})
        return diagnosis, hypotheses[:5]
