from __future__ import annotations

from pathlib import Path

from agents.base import InvestigationContext
from mcp.contracts import evidence_id
from retrieval import HybridSearch, LearnedReranker, build_corpus
from retrieval.ingest import query_from_alert
from runtime.state import Evidence


class RetrievalAgent:
    name = "retrieval"

    def __init__(self, reranker_path: Path | None = None) -> None:
        self.reranker_path = reranker_path or (
            Path(__file__).resolve().parents[1] / "ml" / "artifacts" / "incident_reranker.json"
        )
        self.reranker = LearnedReranker.load(self.reranker_path)

    async def run(self, context: InvestigationContext, task_id: str) -> list[Evidence]:
        scenario = context.snapshot.scenario
        query = query_from_alert(scenario)
        search = HybridSearch(build_corpus(exclude_scenario_ids={scenario.id}))
        candidates = search.search(query, limit=20)
        results = self.reranker.rerank(query, candidates)[:5]
        payload = {
            "query": query,
            "results": [
                {
                    "score": result.score,
                    "citation": result.citation,
                    "metadata": result.document.metadata,
                }
                for result in results
            ],
        }
        evidence = Evidence(
            id=evidence_id("learned_incident_reranker", payload),
            source="retrieval",
            kind="historical_incident_reranking",
            summary=(
                f"Top historical match: {results[0].document.title} "
                f"({results[0].document.metadata['root_cause']})"
            ),
            raw_reference=results[0].document.source_uri,
            payload=payload,
            relevance=0.88,
        )
        return [context.store_evidence(evidence, task_id)]
