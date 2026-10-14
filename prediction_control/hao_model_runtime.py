"""Runtime implementation used by Tony's control module.

This file does not modify Hao's ``New Version.ipynb``.  It implements the
Model 4 architecture documented there so the notebook model can be called from
the production/control code:

    StandardScaler -> GaussianMixture(3 regimes) -> one GPR per regime.

The runtime uses Hao's real-time GPR kernel/settings and a 1000-sample rolling
window per regime.  The fitted artifact is an integration artifact owned by the
control layer, not a replacement for Hao's notebook.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
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
N_REGIMES = 3
WINDOW_SIZE = 1000
INITIAL_SAMPLES_PER_REGIME = 350
RANDOM_STATE = 42

@dataclass(frozen=True)
class ModelPrediction:
    moisture_pct: float
    uncertainty_pct: float
    regime: int


def _kernel(n_features: int):
    return (
        ConstantKernel(1.0)
        * RBF(np.ones(n_features))
        + WhiteKernel(0.001)
    )


def _new_realtime_gpr(n_features: int) -> GaussianProcessRegressor:
    return GaussianProcessRegressor(
        kernel=_kernel(n_features),
        normalize_y=True,
        optimizer=None,
        random_state=RANDOM_STATE,
    )


class HaoMixtureGPRRuntime:
    """Reusable inference/update wrapper around Hao's Model 4 architecture."""

    def __init__(self, window_size: int = WINDOW_SIZE):
        self.window_size = int(window_size)
        self.scaler = StandardScaler()
        self.gmm = GaussianMixture(n_components=N_REGIMES, random_state=RANDOM_STATE)
        self.models: dict[int, GaussianProcessRegressor] = {}
        self.regime_X: dict[int, np.ndarray] = {}
        self.regime_y: dict[int, np.ndarray] = {}
        self.is_fitted = False

    @staticmethod
    def validate_dataframe(df: pd.DataFrame) -> None:
        required = set(FEATURE_COLUMNS + [TARGET_COLUMN])
        missing = sorted(required - set(df.columns))
        if missing:
            raise ValueError(f"Dataset is missing required model columns: {missing}")
        if df.empty:
            raise ValueError("Dataset cannot be empty")

    def fit(self, df: pd.DataFrame) -> "HaoMixtureGPRRuntime":
        self.validate_dataframe(df)
        X = df[FEATURE_COLUMNS].to_numpy(dtype=float)
        y = df[TARGET_COLUMN].to_numpy(dtype=float)
        X_scaled = self.scaler.fit_transform(X)
        regimes = self.gmm.fit_predict(X_scaled)

        self.models.clear()
        self.regime_X.clear()
        self.regime_y.clear()
        rng = np.random.default_rng(RANDOM_STATE)

        # Hao's notebook first optimizes a GPR for each regime, then the
        # real-time stage reuses fixed kernels (optimizer=None).  For the
        # deployable Tony runtime we use a deterministic representative subset
        # per regime for the initial cubic-cost GPR fit.  This is an integration
        # performance adaptation; Hao's notebook itself remains untouched.
        for regime in range(N_REGIMES):
            idx_all = np.flatnonzero(regimes == regime)
            if len(idx_all) == 0:
                raise RuntimeError(f"No samples assigned to regime {regime}")
            fit_idx = idx_all
            if len(fit_idx) > INITIAL_SAMPLES_PER_REGIME:
                fit_idx = rng.choice(fit_idx, size=INITIAL_SAMPLES_PER_REGIME, replace=False)

            initial_model = GaussianProcessRegressor(
                kernel=_kernel(X.shape[1]),
                normalize_y=True,
                random_state=RANDOM_STATE,
                n_restarts_optimizer=0,
            )
            initial_model.fit(X_scaled[fit_idx], y[fit_idx])
            self.models[regime] = initial_model

            # Keep the newest bounded observations for future periodic updates.
            window_idx = idx_all[-self.window_size:]
            self.regime_X[regime] = X_scaled[window_idx].copy()
            self.regime_y[regime] = y[window_idx].copy()

        self.is_fitted = True
        return self

    def _check_fitted(self) -> None:
        if not self.is_fitted or len(self.models) != N_REGIMES:
            raise RuntimeError("HaoMixtureGPRRuntime has not been fitted")

    def predict_batch(self, X: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        self._check_fitted()
        X = np.asarray(X, dtype=float)
        if X.ndim == 1:
            X = X.reshape(1, -1)
        if X.shape[1] != len(FEATURE_COLUMNS):
            raise ValueError(f"Expected {len(FEATURE_COLUMNS)} model features, got {X.shape[1]}")
        X_scaled = self.scaler.transform(X)
        regimes = self.gmm.predict(X_scaled).astype(int)
        means = np.empty(len(X_scaled), dtype=float)
        stds = np.empty(len(X_scaled), dtype=float)
        for regime in range(N_REGIMES):
            idx = np.flatnonzero(regimes == regime)
            if not len(idx):
                continue
            mean, std = self.models[regime].predict(X_scaled[idx], return_std=True)
            means[idx] = mean
            stds[idx] = std
        return means, stds, regimes

    def predict(self, position_m: float, lateral_m: float, depth_cm: float,
                measured_moisture_pct: float) -> ModelPrediction:
        X = np.array([[position_m, lateral_m, depth_cm, measured_moisture_pct]], dtype=float)
        mean, std, regime = self.predict_batch(X)
        return ModelPrediction(float(mean[0]), float(std[0]), int(regime[0]))

    def update(self, new_rows: pd.DataFrame) -> None:
        """Predict-before-update compatible periodic batch update.

        Call this only after predictions for the incoming batch have been used.
        Only regimes present in ``new_rows`` are retrained.
        """
        self._check_fitted()
        self.validate_dataframe(new_rows)
        X = new_rows[FEATURE_COLUMNS].to_numpy(dtype=float)
        y = new_rows[TARGET_COLUMN].to_numpy(dtype=float)
        X_scaled = self.scaler.transform(X)
        regimes = self.gmm.predict(X_scaled).astype(int)
        for regime in range(N_REGIMES):
            idx = np.flatnonzero(regimes == regime)
            if not len(idx):
                continue
            X_all = np.vstack([self.regime_X[regime], X_scaled[idx]])[-self.window_size:]
            y_all = np.concatenate([self.regime_y[regime], y[idx]])[-self.window_size:]
            learned_kernel = getattr(self.models[regime], "kernel_", _kernel(X.shape[1]))
            model = GaussianProcessRegressor(
                kernel=learned_kernel, normalize_y=True, optimizer=None, random_state=RANDOM_STATE
            )
            model.fit(X_all, y_all)
            self.models[regime] = model
            self.regime_X[regime] = X_all
            self.regime_y[regime] = y_all

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
