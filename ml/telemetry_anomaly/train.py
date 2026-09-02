from __future__ import annotations

import argparse
import json
from pathlib import Path

from ml.telemetry_anomaly.baseline import ZScoreBaseline
from ml.telemetry_anomaly.data import build_dataset
from ml.telemetry_anomaly.evaluate import binary_metrics, onset_error
from ml.telemetry_anomaly.model import TemporalAutoencoder


def train(*, quick: bool = False, root: Path | None = None) -> dict[str, object]:
    base = root or Path(__file__).resolve().parents[1]
    artifact_dir = base / "artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    dataset = build_dataset()
    train_normal = dataset.train.x[dataset.train.y == 0]
    validation_normal = dataset.validation.x[dataset.validation.y == 0]
    model = TemporalAutoencoder(dataset.window_size * len(dataset.feature_names))
    history = model.fit(
        train_normal,
        validation_normal,
        epochs=30 if quick else 90,
        learning_rate=0.005,
    )
    neural_scores = model.score(dataset.test.x)
    neural_metrics = binary_metrics(dataset.test.y, neural_scores, model.threshold)
    neural_metrics["onset_window_error"] = onset_error(
        dataset.test.y, neural_scores, model.threshold
    )
    baseline = ZScoreBaseline()
    baseline.fit(train_normal, validation_normal)
    baseline_scores = baseline.score(dataset.test.x)
    baseline_metrics = binary_metrics(dataset.test.y, baseline_scores, baseline.threshold)
    model_path = artifact_dir / "telemetry_autoencoder.npz"
    model.save(model_path)
    result: dict[str, object] = {
        "artifact": str(model_path.relative_to(base.parent)),
        "dataset": {
            "train_windows": len(dataset.train.x),
            "validation_windows": len(dataset.validation.x),
            "test_windows": len(dataset.test.x),
            "features": list(dataset.feature_names),
            "window_size": dataset.window_size,
        },
        "neural": neural_metrics,
        "zscore_baseline": baseline_metrics,
        "final_train_loss": history.train_loss[-1],
        "final_validation_loss": history.validation_loss[-1],
        "threshold": model.threshold,
    }
    (artifact_dir / "telemetry_metrics.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Train Sentinel telemetry anomaly models")
    parser.add_argument("--quick", action="store_true")
    args = parser.parse_args()
    print(json.dumps(train(quick=args.quick), indent=2))


if __name__ == "__main__":
    main()
