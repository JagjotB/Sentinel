from __future__ import annotations

import numpy as np


def binary_metrics(labels: np.ndarray, scores: np.ndarray, threshold: float) -> dict[str, float]:
    predictions = scores > threshold
    labels_bool = labels.astype(bool)
    true_positive = int(np.sum(predictions & labels_bool))
    false_positive = int(np.sum(predictions & ~labels_bool))
    false_negative = int(np.sum(~predictions & labels_bool))
    true_negative = int(np.sum(~predictions & ~labels_bool))
    precision = true_positive / max(1, true_positive + false_positive)
    recall = true_positive / max(1, true_positive + false_negative)
    f1 = 2 * precision * recall / max(1e-12, precision + recall)
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "accuracy": (true_positive + true_negative) / max(1, len(labels)),
        "auroc": _auroc(labels, scores),
        "auprc": _auprc(labels, scores),
    }


def onset_error(labels: np.ndarray, scores: np.ndarray, threshold: float) -> float:
    expected = np.flatnonzero(labels)
    detected = np.flatnonzero(scores > threshold)
    if not len(expected) or not len(detected):
        return float(len(labels))
    return float(abs(int(expected[0]) - int(detected[0])))


def _auroc(labels: np.ndarray, scores: np.ndarray) -> float:
    order = np.argsort(scores)
    ranks = np.empty_like(order)
    ranks[order] = np.arange(1, len(scores) + 1)
    positives = labels.astype(bool)
    count_positive = int(positives.sum())
    count_negative = len(labels) - count_positive
    if count_positive == 0 or count_negative == 0:
        return 0.5
    rank_sum = int(ranks[positives].sum())
    return (rank_sum - count_positive * (count_positive + 1) / 2) / (
        count_positive * count_negative
    )


def _auprc(labels: np.ndarray, scores: np.ndarray) -> float:
    order = np.argsort(scores)[::-1]
    sorted_labels = labels[order]
    positives = max(1, int(labels.sum()))
    true_positives = np.cumsum(sorted_labels)
    precision = true_positives / np.arange(1, len(labels) + 1)
    return float(np.sum(precision * sorted_labels) / positives)
