from __future__ import annotations

from pathlib import Path

from retrieval.citations import render_context
from retrieval.evaluate import train_and_evaluate
from retrieval.hybrid_search import HybridSearch
from retrieval.ingest import build_corpus, corpus_checksum, query_from_alert
from simulator.catalog import build_catalog


def test_hybrid_retrieval_preserves_provenance() -> None:
    documents = build_corpus()
    index = HybridSearch(documents)
    results = index.search("payments OOMKilled memory limit manifest diff", limit=5)
    assert results
    assert all(result.citation["source_id"] for result in results)
    assert all(result.citation["source_uri"] for result in results)
    assert "source=" in render_context(results)
    assert corpus_checksum(documents) == corpus_checksum(build_corpus())


def test_learned_reranker_is_trained_and_evaluated(tmp_path: Path) -> None:
    report = train_and_evaluate(tmp_path)
    metrics = report["metrics"]
    assert metrics["reranker_recall_at_5"] >= 0.9
    assert metrics["reranker_mrr"] >= 0.5
    assert (tmp_path / "ml" / "artifacts" / "incident_reranker.json").exists()


def test_retrieval_evaluation_keeps_labels_and_held_out_incidents_out_of_queries() -> None:
    scenarios = build_catalog()
    training = scenarios[::2]
    held_out = scenarios[1::2]
    documents = build_corpus(training)
    document_ids = {document.id for document in documents}
    assert all(f"incident_{scenario.id}" not in document_ids for scenario in held_out)
    for scenario in held_out:
        query = query_from_alert(scenario)
        assert scenario.root_cause not in query
        assert all(label not in query for label in scenario.expected_evidence)
