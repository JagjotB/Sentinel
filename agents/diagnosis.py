from __future__ import annotations

import json
import re
from typing import TypedDict

from runtime.budgets import BudgetLedger
from runtime.context_manager import ContextManager, ContextWindow
from runtime.langchain_gateway import LangChainReasoner, ModelCallContext, ModelInvocation
from runtime.state import Diagnosis, Evidence
from simulator.catalog import FAULT_SPECS


class Hypothesis(TypedDict):
    root_cause: str
    score: float
    evidence_ids: list[str]
    recommended_action: str


class DiagnosisAgent:
    name = "diagnosis"

    async def run_with_model(
        self,
        evidence: list[Evidence],
        reasoner: LangChainReasoner,
        context: ModelCallContext,
        ledger: BudgetLedger,
        context_window: ContextWindow | None = None,
    ) -> tuple[Diagnosis, list[Hypothesis], ModelInvocation]:
        fallback, hypotheses = self.run(evidence)
        window = context_window or ContextManager().build(evidence, "diagnose incident")
        diagnosis, invocation = await reasoner.invoke_structured(
            purpose="diagnosis",
            prompt_version="diagnosis-v2",
            system_prompt=(
                "Act as Sentinel's diagnosis agent. Select the best supported root cause from the "
                "ranked candidates. Cite only supplied evidence IDs, abstain when corroboration is "
                "weak, and produce a concise reasoning summary."
            ),
            payload={
                "evidence_context": window.text,
                "available_evidence_ids": list(window.evidence_ids),
                "dropped_evidence_count": window.dropped_count,
                "ranked_hypotheses": hypotheses,
            },
            schema=Diagnosis,
            offline_response=fallback,
            context=context,
            ledger=ledger,
        )
        known_causes = {str(item["root_cause"]) for item in hypotheses}
        if diagnosis.status == "supported" and diagnosis.root_cause not in known_causes:
            raise ValueError(f"model selected an unknown root cause: {diagnosis.root_cause}")
        diagnosis.validate_against({item.id for item in evidence})
        return diagnosis, hypotheses, invocation

    def run(self, evidence: list[Evidence]) -> tuple[Diagnosis, list[Hypothesis]]:
        rendered = [
            (
                item,
                f"{item.summary} {json.dumps(item.payload, sort_keys=True, default=str)}".lower(),
            )
            for item in evidence
        ]
        hypotheses: list[Hypothesis] = []
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
                if item.source == "retrieval":
                    results = item.payload.get("results", [])
                    if isinstance(results, list) and results:
                        first = results[0]
                        if isinstance(first, dict):
                            metadata = first.get("metadata", {})
                            candidate = (
                                metadata.get("root_cause")
                                if isinstance(metadata, dict)
                                else None
                            )
                            if candidate == cause:
                                scores.append((4.0 * item.relevance, item.id))
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
