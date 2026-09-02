from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from retrieval.hybrid_search import SearchResult


class LearnedReranker:
    """Small trained logistic reranker over transparent retrieval features."""

    def __init__(self) -> None:
        self.weights = np.zeros(5, dtype=np.float64)
        self.bias = 0.0

    def fit(
        self,
        training_rows: list[tuple[str, SearchResult, int]],
        *,
        epochs: int = 200,
        learning_rate: float = 0.08,
    ) -> None:
        matrix = np.stack([self.features(query, result) for query, result, _ in training_rows])
        labels = np.array([label for _, _, label in training_rows], dtype=np.float64)
        positive_weight = float(np.sum(labels == 0) / max(1, np.sum(labels == 1)))
        sample_weights = np.where(labels == 1, positive_weight, 1.0)
        for _ in range(epochs):
            probabilities = self._sigmoid(matrix @ self.weights + self.bias)
            error = (probabilities - labels) * sample_weights
            normalizer = float(sample_weights.sum())
            self.weights -= learning_rate * (matrix.T @ error / normalizer + 0.001 * self.weights)
            self.bias -= learning_rate * float(error.sum() / normalizer)

    def rerank(self, query: str, results: list[SearchResult]) -> list[SearchResult]:
        scored = [
            (
                float(self._sigmoid(self.features(query, result) @ self.weights + self.bias)),
                result,
            )
            for result in results
        ]
        return [
            SearchResult(
                document=result.document,
                score=score,
                lexical_score=result.lexical_score,
                vector_score=result.vector_score,
                rank=rank,
            )
            for rank, (score, result) in enumerate(
                sorted(scored, reverse=True, key=lambda row: row[0]), 1
            )
        ]

    def features(self, query: str, result: SearchResult) -> np.ndarray:
        query_terms = set(query.lower().split())
        title_terms = set(result.document.title.lower().split())
        overlap = len(query_terms & title_terms) / max(1, len(query_terms))
        runbook = 1.0 if result.document.source_type == "runbook" else 0.0
        return np.array(
            [result.lexical_score, result.vector_score, result.score, overlap, runbook],
            dtype=np.float64,
        )

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"weights": self.weights.tolist(), "bias": self.bias}, indent=2) + "\n",
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: Path) -> LearnedReranker:
        values = json.loads(path.read_text(encoding="utf-8"))
        reranker = cls()
        reranker.weights = np.array(values["weights"], dtype=np.float64)
        reranker.bias = float(values["bias"])
        return reranker

    @staticmethod
    def _sigmoid(value: np.ndarray | float) -> np.ndarray | float:
        result = np.asarray(1.0 / (1.0 + np.exp(-np.clip(value, -30, 30))))
        if np.isscalar(value):
            return float(result)
        return result
