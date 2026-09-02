from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from dataclasses import dataclass

import numpy as np

from retrieval.ingest import Document

TOKEN = re.compile(r"[a-z0-9_]+")


@dataclass(frozen=True)
class SearchResult:
    document: Document
    score: float
    lexical_score: float
    vector_score: float
    rank: int

    @property
    def citation(self) -> dict[str, str]:
        return {
            "source_id": self.document.id,
            "source_uri": self.document.source_uri,
            "title": self.document.title,
        }


class HybridSearch:
    def __init__(self, documents: list[Document], vector_dimensions: int = 192) -> None:
        self.documents = documents
        self.vector_dimensions = vector_dimensions
        self._tokens = [self.tokenize(item.title + " " + item.body) for item in documents]
        self._document_frequencies = Counter(
            token for tokens in self._tokens for token in set(tokens)
        )
        self._average_length = sum(map(len, self._tokens)) / max(1, len(self._tokens))
        self._vectors = np.stack([self.embed(item.title + " " + item.body) for item in documents])

    def search(
        self,
        query: str,
        *,
        limit: int = 10,
        lexical_weight: float = 0.55,
    ) -> list[SearchResult]:
        query_tokens = self.tokenize(query)
        query_vector = self.embed(query)
        lexical = np.array(
            [self._bm25(query_tokens, tokens) for tokens in self._tokens], dtype=np.float64
        )
        if lexical.max(initial=0.0) > 0:
            lexical /= lexical.max()
        vector = self._vectors @ query_vector
        vector = (vector + 1.0) / 2.0
        combined = lexical_weight * lexical + (1 - lexical_weight) * vector
        order = np.argsort(combined)[::-1][:limit]
        return [
            SearchResult(
                document=self.documents[index],
                score=float(combined[index]),
                lexical_score=float(lexical[index]),
                vector_score=float(vector[index]),
                rank=rank,
            )
            for rank, index in enumerate(order, 1)
        ]

    def tokenize(self, text: str) -> list[str]:
        return TOKEN.findall(text.lower())

    def embed(self, text: str) -> np.ndarray:
        vector = np.zeros(self.vector_dimensions, dtype=np.float64)
        tokens = self.tokenize(text)
        for token in tokens:
            digest = hashlib.blake2b(token.encode(), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "big") % self.vector_dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign * (1.0 + math.log1p(len(token)))
        norm = np.linalg.norm(vector)
        return vector / norm if norm else vector

    def _bm25(self, query: list[str], document: list[str]) -> float:
        counts = Counter(document)
        score = 0.0
        for token in query:
            frequency = counts[token]
            if not frequency:
                continue
            doc_frequency = self._document_frequencies[token]
            inverse_frequency = math.log(
                1 + (len(self.documents) - doc_frequency + 0.5) / (doc_frequency + 0.5)
            )
            denominator = frequency + 1.2 * (
                1 - 0.75 + 0.75 * len(document) / max(1, self._average_length)
            )
            score += inverse_frequency * frequency * 2.2 / denominator
        return score
