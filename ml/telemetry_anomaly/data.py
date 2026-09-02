from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from simulator.catalog import build_catalog
from simulator.engine import FEATURES, IncidentSimulator


@dataclass(frozen=True)
class DatasetSplit:
    x: np.ndarray
    y: np.ndarray
    scenario_ids: tuple[str, ...]


@dataclass(frozen=True)
class TelemetryDataset:
    train: DatasetSplit
    validation: DatasetSplit
    test: DatasetSplit
    feature_names: tuple[str, ...]
    window_size: int


def build_dataset(window_size: int = 12, stride: int = 6) -> TelemetryDataset:
    scenarios = build_catalog()
    buckets: dict[str, list[tuple[np.ndarray, int, str]]] = {
        "train": [],
        "validation": [],
        "test": [],
    }
    for index, scenario in enumerate(scenarios):
        bucket = (
            "train" if index % 5 not in {3, 4} else ("validation" if index % 5 == 3 else "test")
        )
        snapshot = IncidentSimulator().inject(scenario.id)
        matrix = np.array(
            [[getattr(point, feature) for feature in FEATURES] for point in snapshot.telemetry],
            dtype=np.float64,
        )
        onset_index = int(snapshot.injected_at - snapshot.telemetry[0].timestamp)
        for start in range(0, len(matrix) - window_size + 1, stride):
            end = start + window_size
            label = int(end > onset_index + 3)
            buckets[bucket].append((matrix[start:end], label, scenario.id))

    def split(name: str) -> DatasetSplit:
        rows = buckets[name]
        return DatasetSplit(
            x=np.stack([row[0] for row in rows]),
            y=np.array([row[1] for row in rows], dtype=np.int64),
            scenario_ids=tuple(row[2] for row in rows),
        )

    return TelemetryDataset(
        train=split("train"),
        validation=split("validation"),
        test=split("test"),
        feature_names=FEATURES,
        window_size=window_size,
    )
