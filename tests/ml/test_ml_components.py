from __future__ import annotations

from pathlib import Path

import numpy as np

from ml.log_intelligence import LogIntelligence
from ml.telemetry_anomaly.data import build_dataset
from ml.telemetry_anomaly.evaluate import binary_metrics
from ml.telemetry_anomaly.infer import AnomalyDetector
from ml.telemetry_anomaly.model import TemporalAutoencoder
from simulator.engine import IncidentSimulator


def test_dataset_split_has_no_scenario_leakage() -> None:
    dataset = build_dataset()
    train = set(dataset.train.scenario_ids)
    validation = set(dataset.validation.scenario_ids)
    test = set(dataset.test.scenario_ids)
    assert train.isdisjoint(validation)
    assert train.isdisjoint(test)
    assert validation.isdisjoint(test)
    assert dataset.train.x.shape[-2:] == (dataset.window_size, len(dataset.feature_names))


def test_model_training_serialization_and_inference(tmp_path: Path) -> None:
    dataset = build_dataset()
    train_normal = dataset.train.x[dataset.train.y == 0]
    validation_normal = dataset.validation.x[dataset.validation.y == 0]
    model = TemporalAutoencoder(dataset.window_size * len(dataset.feature_names), hidden_dim=16)
    history = model.fit(train_normal, validation_normal, epochs=4, batch_size=128)
    assert history.train_loss[-1] < history.train_loss[0]
    artifact = tmp_path / "model.npz"
    model.save(artifact)
    detector = AnomalyDetector.from_artifact(artifact, window_size=dataset.window_size)
    result = detector.predict(IncidentSimulator().inject("oom_killed_001"))
    assert result.anomaly_score >= 0
    assert len(result.anomalous_dimensions) == 3


def test_binary_metrics_are_calculated_correctly() -> None:
    metrics = binary_metrics(np.array([0, 0, 1, 1]), np.array([0.1, 0.2, 0.8, 0.9]), threshold=0.5)
    assert metrics["f1"] == 1.0
    assert metrics["auroc"] == 1.0


def test_log_intelligence_normalizes_clusters_and_compresses() -> None:
    snapshot = IncidentSimulator().inject("oom_killed_001")
    intelligence = LogIntelligence()
    payload = intelligence.evidence_payload(snapshot.logs)
    assert payload["raw_log_count"] == len(snapshot.logs)
    assert payload["context_cluster_count"] < payload["raw_log_count"]
    assert payload["clusters"][0]["relevance"] >= payload["clusters"][-1]["relevance"]
    assert "137" not in intelligence.normalize("process exited 137")
