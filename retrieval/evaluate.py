from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

from retrieval.hybrid_search import HybridSearch, SearchResult
from retrieval.ingest import build_corpus, corpus_checksum, query_from_alert
from retrieval.rerank import LearnedReranker
from simulator.catalog import build_catalog


def train_and_evaluate(root: Path | None = None) -> dict[str, object]:
    base = root or Path(__file__).resolve().parents[1]
    scenarios = build_catalog()
    training_scenarios = scenarios[::2]
    evaluation_scenarios = scenarios[1::2]
    documents = build_corpus(training_scenarios)
    index = HybridSearch(documents)
    training_rows: list[tuple[str, SearchResult, int]] = []
    for scenario in training_scenarios:
        query = query_from_alert(scenario)
        for result in index.search(query, limit=len(documents)):
            label = int(result.document.metadata["root_cause"] == scenario.root_cause)
            training_rows.append((query, result, label))
    reranker = LearnedReranker()
    reranker.fit(training_rows)
    metrics: dict[str, list[float]] = {
        "hybrid_recall_at_5": [],
        "hybrid_mrr": [],
        "hybrid_ndcg_at_5": [],
        "reranker_recall_at_5": [],
        "reranker_mrr": [],
        "reranker_ndcg_at_5": [],
    }
    for scenario in evaluation_scenarios:
        query = query_from_alert(scenario)
        initial = index.search(query, limit=20)
        reranked = reranker.rerank(query, initial)
        _append_metrics(metrics, "hybrid", initial, scenario.root_cause)
        _append_metrics(metrics, "reranker", reranked, scenario.root_cause)
    summary = {name: float(np.mean(values)) for name, values in metrics.items()}
    artifact_dir = base / "ml" / "artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    reranker.save(artifact_dir / "incident_reranker.json")
    output: dict[str, object] = {
        "documents": len(documents),
        "training_pairs": len(training_rows),
        "queries": len(evaluation_scenarios),
        "split": {
            "strategy": "scenario_variant_holdout",
            "training_scenario_ids": [item.id for item in training_scenarios],
            "evaluation_scenario_ids": [item.id for item in evaluation_scenarios],
            "training_corpus_checksum": corpus_checksum(documents),
            "evaluator_labels_available_to_query": False,
        },
        "metrics": summary,
    }
    (artifact_dir / "retrieval_metrics.json").write_text(
        json.dumps(output, indent=2) + "\n", encoding="utf-8"
    )
    return output


def _append_metrics(
    metrics: dict[str, list[float]], prefix: str, results: list[SearchResult], cause: str
) -> None:
    relevance = [int(row.document.metadata["root_cause"] == cause) for row in results]
    metrics[f"{prefix}_recall_at_5"].append(float(any(relevance[:5])))
    reciprocal = next((1.0 / rank for rank, value in enumerate(relevance, 1) if value), 0.0)
    metrics[f"{prefix}_mrr"].append(reciprocal)
    dcg = sum(value / math.log2(rank + 1) for rank, value in enumerate(relevance[:5], 1))
    ideal_count = min(5, sum(relevance))
    ideal = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_count + 1))
    metrics[f"{prefix}_ndcg_at_5"].append(dcg / ideal if ideal else 0.0)
