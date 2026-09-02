from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass(frozen=True)
class TrainingHistory:
    train_loss: tuple[float, ...]
    validation_loss: tuple[float, ...]


class TemporalAutoencoder:
    """Four-layer temporal autoencoder with explicit NumPy backpropagation."""

    def __init__(
        self, input_dim: int, hidden_dim: int = 32, latent_dim: int = 8, seed: int = 7
    ) -> None:
        rng = np.random.default_rng(seed)
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        self.latent_dim = latent_dim
        self.w1 = rng.normal(0, np.sqrt(2 / input_dim), (input_dim, hidden_dim))
        self.b1 = np.zeros(hidden_dim)
        self.w2 = rng.normal(0, np.sqrt(2 / hidden_dim), (hidden_dim, latent_dim))
        self.b2 = np.zeros(latent_dim)
        self.w3 = rng.normal(0, np.sqrt(2 / latent_dim), (latent_dim, hidden_dim))
        self.b3 = np.zeros(hidden_dim)
        self.w4 = rng.normal(0, np.sqrt(2 / hidden_dim), (hidden_dim, input_dim))
        self.b4 = np.zeros(input_dim)
        self.mean = np.zeros(input_dim)
        self.scale = np.ones(input_dim)
        self.threshold = 0.0

    def fit(
        self,
        train: np.ndarray,
        validation: np.ndarray,
        *,
        epochs: int = 80,
        learning_rate: float = 0.006,
        batch_size: int = 64,
        seed: int = 17,
    ) -> TrainingHistory:
        train_flat = train.reshape(len(train), -1)
        val_flat = validation.reshape(len(validation), -1)
        self.mean = train_flat.mean(axis=0)
        self.scale = train_flat.std(axis=0) + 1e-6
        x_train = (train_flat - self.mean) / self.scale
        x_val = (val_flat - self.mean) / self.scale
        rng = np.random.default_rng(seed)
        train_losses: list[float] = []
        val_losses: list[float] = []
        parameters = [self.w1, self.b1, self.w2, self.b2, self.w3, self.b3, self.w4, self.b4]
        moments = [np.zeros_like(parameter) for parameter in parameters]
        velocities = [np.zeros_like(parameter) for parameter in parameters]
        step = 0
        for _ in range(epochs):
            indices = rng.permutation(len(x_train))
            for start in range(0, len(indices), batch_size):
                step += 1
                batch = x_train[indices[start : start + batch_size]]
                reconstruction, cache = self._forward(batch)
                gradients = self._backward(batch, reconstruction, cache)
                for index, (parameter, gradient) in enumerate(
                    zip(parameters, gradients, strict=True)
                ):
                    moments[index] = 0.9 * moments[index] + 0.1 * gradient
                    velocities[index] = 0.999 * velocities[index] + 0.001 * (gradient**2)
                    m_hat = moments[index] / (1 - 0.9**step)
                    v_hat = velocities[index] / (1 - 0.999**step)
                    parameter -= learning_rate * m_hat / (np.sqrt(v_hat) + 1e-8)
            train_losses.append(float(np.mean((self._forward(x_train)[0] - x_train) ** 2)))
            val_losses.append(float(np.mean((self._forward(x_val)[0] - x_val) ** 2)))
        normal_scores = self.score(validation)
        self.threshold = float(np.quantile(normal_scores, 0.95))
        return TrainingHistory(tuple(train_losses), tuple(val_losses))

    def reconstruct(self, windows: np.ndarray) -> np.ndarray:
        flat = windows.reshape(len(windows), -1)
        normalized = (flat - self.mean) / self.scale
        rebuilt = self._forward(normalized)[0] * self.scale + self.mean
        return rebuilt.reshape(windows.shape)

    def score(self, windows: np.ndarray) -> np.ndarray:
        flat = windows.reshape(len(windows), -1)
        normalized = (flat - self.mean) / self.scale
        rebuilt = self._forward(normalized)[0]
        return np.asarray(np.mean((rebuilt - normalized) ** 2, axis=1), dtype=np.float64)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            path,
            input_dim=self.input_dim,
            hidden_dim=self.hidden_dim,
            latent_dim=self.latent_dim,
            w1=self.w1,
            b1=self.b1,
            w2=self.w2,
            b2=self.b2,
            w3=self.w3,
            b3=self.b3,
            w4=self.w4,
            b4=self.b4,
            mean=self.mean,
            scale=self.scale,
            threshold=self.threshold,
        )

    @classmethod
    def load(cls, path: Path) -> TemporalAutoencoder:
        data = np.load(path)
        model = cls(int(data["input_dim"]), int(data["hidden_dim"]), int(data["latent_dim"]))
        for name in ("w1", "b1", "w2", "b2", "w3", "b3", "w4", "b4", "mean", "scale"):
            setattr(model, name, data[name])
        model.threshold = float(data["threshold"])
        return model

    def _forward(self, x: np.ndarray) -> tuple[np.ndarray, tuple[np.ndarray, ...]]:
        h1 = np.tanh(x @ self.w1 + self.b1)
        latent = np.tanh(h1 @ self.w2 + self.b2)
        h3 = np.tanh(latent @ self.w3 + self.b3)
        output = h3 @ self.w4 + self.b4
        return output, (x, h1, latent, h3)

    def _backward(
        self,
        target: np.ndarray,
        output: np.ndarray,
        cache: tuple[np.ndarray, ...],
    ) -> tuple[np.ndarray, ...]:
        x, h1, latent, h3 = cache
        delta4 = 2 * (output - target) / (target.shape[0] * target.shape[1])
        grad_w4 = h3.T @ delta4
        grad_b4 = delta4.sum(axis=0)
        delta3 = (delta4 @ self.w4.T) * (1 - h3**2)
        grad_w3 = latent.T @ delta3
        grad_b3 = delta3.sum(axis=0)
        delta2 = (delta3 @ self.w3.T) * (1 - latent**2)
        grad_w2 = h1.T @ delta2
        grad_b2 = delta2.sum(axis=0)
        delta1 = (delta2 @ self.w2.T) * (1 - h1**2)
        grad_w1 = x.T @ delta1
        grad_b1 = delta1.sum(axis=0)
        return grad_w1, grad_b1, grad_w2, grad_b2, grad_w3, grad_b3, grad_w4, grad_b4
