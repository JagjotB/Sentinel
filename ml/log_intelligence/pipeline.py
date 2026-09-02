from __future__ import annotations

import hashlib
import re
from collections import Counter
from typing import Any

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from simulator.models import StructuredLog

TOKEN = re.compile(r"[a-zA-Z_]+")
NUMERIC = re.compile(r"\b(?:\d+|0x[a-fA-F0-9]+)\b")
UUID = re.compile(r"\b[a-fA-F0-9]{8}(?:-[a-fA-F0-9]{4}){3}-[a-fA-F0-9]{12}\b")
IP = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")


class LogCluster(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str
    template: str
    count: int = Field(gt=0)
    novelty: float = Field(ge=0.0, le=1.0)
    relevance: float = Field(ge=0.0, le=1.0)
    first_timestamp: float
    last_timestamp: float
    raw_references: list[str]


class LogIntelligence:
    def __init__(self, embedding_dimensions: int = 96) -> None:
        self.embedding_dimensions = embedding_dimensions

    def analyze(self, logs: tuple[StructuredLog, ...]) -> list[LogCluster]:
        grouped: dict[str, list[tuple[int, StructuredLog]]] = {}
        for index, row in enumerate(logs):
            grouped.setdefault(self.normalize(row.message), []).append((index, row))
        total = max(1, len(logs))
        newest = max((row.timestamp for row in logs), default=0.0)
        clusters: list[LogCluster] = []
        for template, rows in grouped.items():
            count = len(rows)
            levels = Counter(row.level for _, row in rows)
            rarity = 1.0 - min(1.0, count / total)
            severity = min(1.0, (levels["ERROR"] * 1.0 + levels["WARN"] * 0.4) / count)
            recency = 1.0 if newest == rows[-1][1].timestamp else 0.5
            novelty = min(1.0, rarity * 0.75 + self._embedding_novelty(template) * 0.25)
            relevance = min(1.0, severity * 0.55 + rarity * 0.25 + recency * 0.2)
            cluster_id = hashlib.sha256(template.encode()).hexdigest()[:12]
            clusters.append(
                LogCluster(
                    id=f"logc_{cluster_id}",
                    template=template,
                    count=count,
                    novelty=novelty,
                    relevance=relevance,
                    first_timestamp=rows[0][1].timestamp,
                    last_timestamp=rows[-1][1].timestamp,
                    raw_references=[f"log://{index}" for index, _ in rows[:10]],
                )
            )
        return sorted(clusters, key=lambda item: item.relevance, reverse=True)

    def normalize(self, message: str) -> str:
        value = UUID.sub("<UUID>", message)
        value = IP.sub("<IP>", value)
        return NUMERIC.sub("<NUM>", value).strip().lower()

    def embed(self, text: str) -> np.ndarray:
        vector = np.zeros(self.embedding_dimensions, dtype=np.float64)
        for token in TOKEN.findall(text.lower()):
            digest = hashlib.blake2b(token.encode(), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "big") % self.embedding_dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        norm = np.linalg.norm(vector)
        return vector / norm if norm else vector

    def evidence_payload(self, logs: tuple[StructuredLog, ...], limit: int = 5) -> dict[str, Any]:
        clusters = self.analyze(logs)[:limit]
        return {
            "clusters": [cluster.model_dump(mode="json") for cluster in clusters],
            "raw_log_count": len(logs),
            "context_cluster_count": len(clusters),
            "compression_ratio": len(logs) / max(1, len(clusters)),
        }

    def _embedding_novelty(self, template: str) -> float:
        vector = self.embed(template)
        return float(min(1.0, np.count_nonzero(vector) / 12))
