from __future__ import annotations

from pathlib import Path

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from ml.telemetry_anomaly.model import TemporalAutoencoder
from simulator.engine import FEATURES, SimulationSnapshot


class AnomalyResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    anomaly_score: float = Field(ge=0.0)
    is_anomalous: bool
    anomalous_dimensions: list[str]
    onset_timestamp: float | None
    threshold: float
    window_scores: list[float]


class AnomalyDetector:
    def __init__(self, model: TemporalAutoencoder, window_size: int = 12, stride: int = 3) -> None:
        self.model = model
        self.window_size = window_size
        self.stride = stride

    @classmethod
    def from_artifact(cls, path: Path, window_size: int = 12) -> AnomalyDetector:
        return cls(TemporalAutoencoder.load(path), window_size=window_size)

    def predict(self, snapshot: SimulationSnapshot) -> AnomalyResult:
        matrix = np.array(
            [[getattr(point, feature) for feature in FEATURES] for point in snapshot.telemetry],
            dtype=np.float64,
        )
        starts = list(range(0, len(matrix) - self.window_size + 1, self.stride))
        windows = np.stack([matrix[start : start + self.window_size] for start in starts])
        scores = self.model.score(windows)
        maximum_index = int(np.argmax(scores))
        reconstruction = self.model.reconstruct(windows[[maximum_index]])[0]
        normalized_error = np.mean(
            np.abs(windows[maximum_index] - reconstruction) / (np.std(matrix[:60], axis=0) + 1e-6),
            axis=0,
        )
        dimension_order = np.argsort(normalized_error)[::-1]
        dimensions = [FEATURES[index] for index in dimension_order[:3]]
        above = np.flatnonzero(scores > self.model.threshold)
        onset = None
        if len(above):
            point_index = starts[int(above[0])] + self.window_size - 1
            onset = snapshot.telemetry[point_index].timestamp
        return AnomalyResult(
            anomaly_score=float(scores[maximum_index]),
            is_anomalous=bool(scores[maximum_index] > self.model.threshold),
            anomalous_dimensions=dimensions,
            onset_timestamp=onset,
            threshold=self.model.threshold,
            window_scores=[float(score) for score in scores],
        )
