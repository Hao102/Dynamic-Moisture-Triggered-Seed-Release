"""Runtime implementation of Hao's current Mixture Gaussian Process model.

This module mirrors Model 4 in Hao's latest CODE SPRINT 4 notebook:

    StandardScaler
        -> GaussianMixture(2 experts)
        -> two Gaussian Process experts
        -> probability-weighted soft mixture prediction

The GMM gate and scaler remain fixed after the initial fit. During real-time
updates, each expert keeps up to 400 labelled samples and is refitted using
its previously learned kernel with optimizer=None.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import ConstantKernel, RBF, WhiteKernel
from sklearn.mixture import GaussianMixture
from sklearn.preprocessing import StandardScaler

FEATURE_COLUMNS = [
    "longitudinal_distance_m",
    "lateral_distance_m",
    "depth_cm",
    "provided_moisture_vwc_pct",
]
TARGET_COLUMN = "semi_synthetic_moisture_vwc_pct"

N_EXPERTS = 2
WINDOW_SIZE = 400
RANDOM_STATE = 42


@dataclass(frozen=True)
class ModelPrediction:
    moisture_pct: float
    dominant_expert: int
    expert_weights: tuple[float, float]


def _kernel(n_features: int):
    return (
        ConstantKernel(1.0, (1e-3, 1e3))
        * RBF(np.ones(n_features), (1e-2, 1e3))
        + WhiteKernel(1e-4, (1e-8, 1e-1))
    )


class HaoMixtureGPRRuntime:
    """Deployable wrapper matching Hao's latest Model 4 implementation."""

    def __init__(self, window_size: int = WINDOW_SIZE):
        self.window_size = int(window_size)
        self.scaler = StandardScaler()
        self.gate = GaussianMixture(
            n_components=N_EXPERTS,
            n_init=3,
            random_state=RANDOM_STATE,
        )
        self.experts: dict[int, GaussianProcessRegressor] = {}
        self.buffers: dict[int, tuple[np.ndarray, np.ndarray]] = {}
        self.kernels: dict[int, object] = {}
        self.is_fitted = False

    @staticmethod
    def validate_dataframe(df: pd.DataFrame) -> None:
        required = set(FEATURE_COLUMNS + [TARGET_COLUMN])
        missing = sorted(required - set(df.columns))
        if missing:
            raise ValueError(f"Dataset is missing required model columns: {missing}")
        if df.empty:
            raise ValueError("Dataset cannot be empty")

    @staticmethod
    def training_optimizer(objective, initial_theta, bounds):
        result = minimize(
            objective,
            initial_theta,
            method="L-BFGS-B",
            jac=True,
            bounds=bounds,
            options={
                "maxiter": 150,
                "maxls": 50,
                "ftol": 1e-6,
                "gtol": 1e-5,
            },
        )
        return result.x, result.fun

    def fit(self, df: pd.DataFrame) -> "HaoMixtureGPRRuntime":
        self.validate_dataframe(df)
        X = df[FEATURE_COLUMNS].to_numpy(dtype=float)
        y = df[TARGET_COLUMN].to_numpy(dtype=float)

        z = self.scaler.fit_transform(X)
        groups = self.gate.fit_predict(z)

        self.experts.clear()
        self.buffers.clear()
        self.kernels.clear()

        for k in range(N_EXPERTS):
            indices = np.flatnonzero(groups == k)
            if len(indices) == 0:
                raise RuntimeError(f"No samples assigned to expert {k}")

            if len(indices) > self.window_size:
                indices = indices[
                    np.linspace(0, len(indices) - 1, self.window_size, dtype=int)
                ]

            expert = GaussianProcessRegressor(
                kernel=_kernel(X.shape[1]),
                alpha=1e-8,
                normalize_y=True,
                optimizer=self.training_optimizer,
                random_state=RANDOM_STATE,
            ).fit(z[indices], y[indices])

            self.experts[k] = expert
            self.kernels[k] = copy.deepcopy(expert.kernel_)
            self.buffers[k] = (z[indices].copy(), y[indices].copy())

        self.is_fitted = True
        return self

    def _check_fitted(self) -> None:
        if not self.is_fitted or len(self.experts) != N_EXPERTS:
            raise RuntimeError("HaoMixtureGPRRuntime has not been fitted")

    def predict_batch(self, X: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Return prediction, dominant expert, and expert probabilities."""
        self._check_fitted()
        X = np.asarray(X, dtype=float)
        if X.ndim == 1:
            X = X.reshape(1, -1)
        if X.shape[1] != len(FEATURE_COLUMNS):
            raise ValueError(
                f"Expected {len(FEATURE_COLUMNS)} model features, got {X.shape[1]}"
            )

        z = self.scaler.transform(X)
        weights = self.gate.predict_proba(z)
        means = np.column_stack(
            [self.experts[k].predict(z) for k in range(N_EXPERTS)]
        )
        predictions = np.sum(weights * means, axis=1)
        dominant_experts = np.argmax(weights, axis=1).astype(int)
        return predictions, dominant_experts, weights

    def predict(
        self,
        position_m: float,
        lateral_m: float,
        depth_cm: float,
        measured_moisture_pct: float,
    ) -> ModelPrediction:
        X = np.array(
            [[position_m, lateral_m, depth_cm, measured_moisture_pct]],
            dtype=float,
        )
        prediction, dominant, weights = self.predict_batch(X)
        return ModelPrediction(
            moisture_pct=float(prediction[0]),
            dominant_expert=int(dominant[0]),
            expert_weights=(float(weights[0, 0]), float(weights[0, 1])),
        )

    def update(self, new_rows: pd.DataFrame) -> None:
        self._check_fitted()
        self.validate_dataframe(new_rows)

        X = new_rows[FEATURE_COLUMNS].to_numpy(dtype=float)
        y = new_rows[TARGET_COLUMN].to_numpy(dtype=float)
        z = self.scaler.transform(X)
        groups = self.gate.predict(z)

        for k in range(N_EXPERTS):
            selected = groups == k
            if not selected.any():
                continue

            bx, by = self.buffers[k]
            bx = np.vstack([bx, z[selected]])[-self.window_size :]
            by = np.concatenate([by, y[selected]])[-self.window_size :]

            self.buffers[k] = (bx, by)
            self.experts[k] = GaussianProcessRegressor(
                kernel=copy.deepcopy(self.kernels[k]),
                optimizer=None,
                alpha=1e-8,
                normalize_y=True,
                random_state=RANDOM_STATE,
            ).fit(bx, by)

    def save(self, path: str | Path) -> None:
        self._check_fitted()
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path)

    @classmethod
    def load(cls, path: str | Path) -> "HaoMixtureGPRRuntime":
        obj = joblib.load(path)
        if not isinstance(obj, cls):
            raise TypeError(f"Unexpected model artifact type: {type(obj).__name__}")
        obj._check_fitted()
        return obj
