from __future__ import annotations

import numpy as np


class ZScoreBaseline:
    def __init__(self) -> None:
        self.mean = np.array([])
        self.scale = np.array([])
        self.threshold = 0.0

    def fit(self, normal_windows: np.ndarray, validation_windows: np.ndarray) -> None:
        flattened = normal_windows.reshape(-1, normal_windows.shape[-1])
        self.mean = flattened.mean(axis=0)
        self.scale = flattened.std(axis=0) + 1e-6
        self.threshold = float(np.quantile(self.score(validation_windows), 0.95))

    def score(self, windows: np.ndarray) -> np.ndarray:
        z_scores = np.abs((windows - self.mean) / self.scale)
        return np.asarray(np.max(z_scores, axis=(1, 2)), dtype=np.float64)
