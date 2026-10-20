"""End-to-end dataset -> Hao model -> Tony control -> release events pipeline."""
from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd

from .compensation import calculate_release_target
from .hao_model_runtime import FEATURE_COLUMNS, HaoMixtureGPRRuntime
from .prediction_logic import evaluate_prediction

REQUIRED_DATA_COLUMNS = set(FEATURE_COLUMNS + [
    "time_s", "tractor_speed_kmh", "semi_synthetic_moisture_vwc_pct"
])


def load_project_dataset(path: str | Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    missing = sorted(REQUIRED_DATA_COLUMNS - set(df.columns))
    if missing:
        raise ValueError(f"Dataset missing required columns: {missing}")
    return df


def build_path_dataframe(df: pd.DataFrame, lateral_m: float = 15.0, depth_cm: float = 5.0) -> pd.DataFrame:
    lateral_values = np.sort(df["lateral_distance_m"].unique().astype(float))
    depth_values = np.sort(df["depth_cm"].unique().astype(float))
    if not np.any(np.isclose(depth_values, depth_cm)):
        raise ValueError(f"depth_cm={depth_cm} is unavailable; choose from {depth_values.tolist()}")

    exact = lateral_values[np.isclose(lateral_values, lateral_m)]
    if len(exact):
        path = df[(np.isclose(df["lateral_distance_m"], exact[0])) & (np.isclose(df["depth_cm"], depth_cm))].copy()
        return path.sort_values("longitudinal_distance_m").reset_index(drop=True)

    if lateral_m < lateral_values.min() or lateral_m > lateral_values.max():
        raise ValueError(f"lateral_m must be between {lateral_values.min()} and {lateral_values.max()}")
    lo = lateral_values[lateral_values < lateral_m].max()
    hi = lateral_values[lateral_values > lateral_m].min()
    low = df[(np.isclose(df["lateral_distance_m"], lo)) & (np.isclose(df["depth_cm"], depth_cm))].sort_values("longitudinal_distance_m")
    high = df[(np.isclose(df["lateral_distance_m"], hi)) & (np.isclose(df["depth_cm"], depth_cm))].sort_values("longitudinal_distance_m")
    if len(low) != len(high):
        raise ValueError("Lateral source lines are not aligned")
    w = (lateral_m - lo) / (hi - lo)
    path = low.copy()
    for col in ["provided_moisture_vwc_pct", "semi_synthetic_moisture_vwc_pct"]:
        path[col] = (1-w) * low[col].to_numpy(dtype=float) + w * high[col].to_numpy(dtype=float)
    path["lateral_distance_m"] = float(lateral_m)
    return path.reset_index(drop=True)


def predict_path(path_df: pd.DataFrame, model: HaoMixtureGPRRuntime) -> pd.DataFrame:
    X = path_df[FEATURE_COLUMNS].to_numpy(dtype=float)
    prediction, dominant_expert, expert_weights = model.predict_batch(X)
    result = path_df.copy()
    result["predicted_moisture_pct"] = prediction
    result["dominant_expert"] = dominant_expert
    result["expert_0_weight"] = expert_weights[:, 0]
    result["expert_1_weight"] = expert_weights[:, 1]
    result["speed_m_s"] = result["tractor_speed_kmh"].astype(float) / 3.6
    return result


def build_control_log(predicted_path: pd.DataFrame, config: dict[str, float]) -> pd.DataFrame:
    rows = []
    for row in predicted_path.itertuples(index=False):
        decision = evaluate_prediction(
            position=float(row.longitudinal_distance_m),
            moisture=float(row.provided_moisture_vwc_pct),
            speed=float(row.speed_m_s),
            config=config,
            predicted_moisture=float(row.predicted_moisture_pct),
        )
        rows.append({
            "time_s": float(row.time_s),
            **decision,
            "dominant_expert": int(row.dominant_expert),
            "expert_0_weight": float(row.expert_0_weight),
            "expert_1_weight": float(row.expert_1_weight),
        })
    return pd.DataFrame(rows)


def build_release_events(predicted_path: pd.DataFrame, config: dict[str, float]) -> pd.DataFrame:
    if predicted_path.empty:
        return pd.DataFrame()

    pos = predicted_path["longitudinal_distance_m"].to_numpy(dtype=float)
    time = predicted_path["time_s"].to_numpy(dtype=float)
    speed = predicted_path["speed_m_s"].to_numpy(dtype=float)
    measured = predicted_path["provided_moisture_vwc_pct"].to_numpy(dtype=float)
    predicted = predicted_path["predicted_moisture_pct"].to_numpy(dtype=float)
    dominant = predicted_path["dominant_expert"].to_numpy(dtype=float)
    weight_0 = predicted_path["expert_0_weight"].to_numpy(dtype=float)
    weight_1 = predicted_path["expert_1_weight"].to_numpy(dtype=float)

    spacing = float(config["target_spacing_m"])
    targets = np.arange(pos.min(), pos.max() + 1e-12, spacing)
    target_time = np.interp(targets, pos, time)
    target_speed = np.interp(targets, pos, speed)
    target_measured = np.interp(targets, pos, measured)
    target_predicted = np.interp(targets, pos, predicted)
    target_dominant = np.rint(np.interp(targets, pos, dominant)).astype(int)
    target_weight_0 = np.interp(targets, pos, weight_0)
    target_weight_1 = np.interp(targets, pos, weight_1)

    events = []
    for p, t, s, m, pred, de, w0, w1 in zip(
        targets, target_time, target_speed, target_measured,
        target_predicted, target_dominant, target_weight_0, target_weight_1
    ):
        decision = evaluate_prediction(p, m, s, config, predicted_moisture=pred)
        if not decision["should_release"]:
            continue
        planned = {
            "time_s": float(t),
            **decision,
            "dominant_expert": int(de),
            "expert_0_weight": float(w0),
            "expert_1_weight": float(w1),
        }
        events.append(calculate_release_target(planned, config))
    return pd.DataFrame(events)


def run_dataset_pipeline(df: pd.DataFrame, model: HaoMixtureGPRRuntime, config: dict[str, float],
                         lateral_m: float = 15.0, depth_cm: float = 5.0):
    path = build_path_dataframe(df, lateral_m=lateral_m, depth_cm=depth_cm)
    predicted_path = predict_path(path, model)
    log = build_control_log(predicted_path, config)
    releases = build_release_events(predicted_path, config)
    return log, releases
