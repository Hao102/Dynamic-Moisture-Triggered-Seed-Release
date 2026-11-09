"""Drop-in backend for Manan's unchanged ``run_simulation`` UI API."""
from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd

from interface import DEFAULT_CONFIG
from .dataset_pipeline import load_project_dataset
from .hao_model_runtime import HaoMixtureGPRRuntime
from .prediction_logic import evaluate_prediction

ROOT = Path(__file__).resolve().parents[1]
DATASET_PATH = ROOT / "data" / "integration" / "final_semi_synthetic_winter_wheat_v2.csv"
MODEL_PATH = ROOT / "models" / "hao_mixture_gpr_runtime.joblib"

_DATASET = None
_MODEL = None


def _resources():
    global _DATASET, _MODEL
    if _DATASET is None:
        _DATASET = load_project_dataset(DATASET_PATH)
    if _MODEL is None:
        _MODEL = HaoMixtureGPRRuntime.load(MODEL_PATH) if MODEL_PATH.exists() else HaoMixtureGPRRuntime().fit(_DATASET)
    return _DATASET, _MODEL


def _estimate_lateral(field_positions, field_moisture, depth_cm=5.0):
    df, _ = _resources()
    positions = np.asarray(field_positions, float)
    moisture = np.asarray(field_moisture, float)
    candidates = np.linspace(0.0, 30.0, 61)
    errors = []
    for lat in candidates:
        lo = 0.0 if lat <= 15 else 15.0
        hi = 15.0 if lat <= 15 else 30.0
        a = df[(np.isclose(df.lateral_distance_m, lo)) & (np.isclose(df.depth_cm, depth_cm))].sort_values("longitudinal_distance_m")
        b = df[(np.isclose(df.lateral_distance_m, hi)) & (np.isclose(df.depth_cm, depth_cm))].sort_values("longitudinal_distance_m")
        w = 0.0 if hi == lo else (lat-lo)/(hi-lo)
        base = (1-w) * a.provided_moisture_vwc_pct.to_numpy(float) + w * b.provided_moisture_vwc_pct.to_numpy(float)
        basepos = a.longitudinal_distance_m.to_numpy(float)
        expected = np.interp(positions, basepos, base)
        errors.append(np.mean((expected-moisture)**2))
    return float(candidates[int(np.argmin(errors))])

def run_simulation(
    field_positions,
    field_moisture,
    speed_time,
    speed_values,
    target_spacing_m,
    control_dt_s,
    actuator_tau_s,
    min_moisture,
    max_moisture,
    min_depth,
    max_depth,
    sensor_offset_m=0.50,
):
    # Run the moisture-triggered seed-release control simulation.

    _, model = _resources()

    field_positions = np.asarray(field_positions, float)
    field_moisture = np.asarray(field_moisture, float)
    speed_time = np.asarray(speed_time, float)
    speed_values = np.asarray(speed_values, float)

    if len(field_positions) == 0:
        raise ValueError("The field position array is empty.")

    if len(field_moisture) != len(field_positions):
        raise ValueError(
            "field_positions and field_moisture must have the same length."
        )

    lateral = _estimate_lateral(field_positions, field_moisture)
    depth_cm = 5.0

    # Create control-loop timestamps at the selected control frequency.
    times = np.arange(
        0.0,
        float(speed_time.max()),
        float(control_dt_s),
    )

    # Interpolate vehicle speed at each control-loop timestamp.
    speeds = np.interp(times, speed_time, speed_values)

    # Integrate speed to obtain the seeder position at each control update.
    positions = np.zeros_like(times)
    if len(times) > 1:
        positions[1:] = np.cumsum(
            speeds[:-1] * float(control_dt_s)
        )

    # Keep the simulated seeder within the available field extent.
    positions = np.clip(
        positions,
        field_positions.min(),
        field_positions.max(),
    )

    # The sensor is located ahead of the seeder by sensor_offset_m.
    sensor_positions = np.clip(
        positions + float(sensor_offset_m),
        field_positions.min(),
        field_positions.max(),
    )

    # Moisture measured at the sensor location ahead of the seeder.
    sensor_moisture = np.interp(
        sensor_positions,
        field_positions,
        field_moisture,
    )

    # Prepare model inputs: position, lateral distance, depth, and moisture.
    X = np.column_stack([
        sensor_positions,
        np.full(len(sensor_positions), lateral),
        np.full(len(sensor_positions), depth_cm),
        sensor_moisture,
    ])

    # Predict moisture at the requested model depth.
    pred, dominant, weights = model.predict_batch(X)

    # Build the control configuration from the dashboard inputs.
    config = dict(DEFAULT_CONFIG)
    config.update({
        "target_spacing_m": float(target_spacing_m),
        "min_moisture": float(min_moisture),
        "max_moisture": float(max_moisture),
        "min_depth_mm": float(min_depth),
        "max_depth_mm": float(max_depth),
        "actuator_tau_s": float(actuator_tau_s),
        "sensor_offset_m": float(sensor_offset_m),
    })

    # Determine the requested target depth at each control update.
    target = np.array([
        evaluate_prediction(
            position,
            moisture,
            speed,
            config,
            predicted_moisture=predicted_moisture,
        )["target_depth_mm"]
        for position, moisture, speed, predicted_moisture in zip(
            sensor_positions,
            sensor_moisture,
            speeds,
            pred,
        )
    ], float)

    # Model the actuator response as a first-order lag.
    actual = np.empty_like(target)

    if len(target):
        actual[0] = target[0]

        alpha = float(control_dt_s) / (
            float(actuator_tau_s) + float(control_dt_s)
        )

        for i in range(1, len(target)):
            actual[i] = actual[i - 1] + alpha * (
                target[i] - actual[i - 1]
            )

    # Continuous control log for the animation, charts, and diagnostics.
    log = pd.DataFrame({
        "time_s": times,
        "position_m": positions,
        "sensor_position_m": sensor_positions,
        "speed_m_s": speeds,
        "moisture_pct": pred,
        "target_depth_mm": target,
        "actuator_depth_mm": actual,
        "measured_moisture_pct": sensor_moisture,
        "predicted_moisture_pct": pred,
        "dominant_expert": dominant,
        "expert_0_weight": weights[:, 0],
        "expert_1_weight": weights[:, 1],
    })

    # Generate evenly spaced target seed positions.
    targets = np.arange(
        positions.min(),
        positions.max() + 1e-12,
        float(target_spacing_m),
    )

    # For each target seed position, evaluate moisture at the sensor location
    # that is sensor_offset_m ahead of the release point.
    sensor_positions_for_release = np.clip(
        targets + float(sensor_offset_m),
        field_positions.min(),
        field_positions.max(),
    )

    release_moisture = np.interp(
        sensor_positions_for_release,
        field_positions,
        field_moisture,
    )

    RX = np.column_stack([
        sensor_positions_for_release,
        np.full(len(sensor_positions_for_release), lateral),
        np.full(len(sensor_positions_for_release), depth_cm),
        release_moisture,
    ])

    # Predict moisture for each potential release location.
    release_predictions, release_dominant, release_weights = (
        model.predict_batch(RX)
    )

    release_times = np.interp(
        targets,
        positions,
        times,
    )

    release_speeds = np.interp(
        targets,
        positions,
        speeds,
    )

    release_rows = []

    for i, target_position in enumerate(targets):
        decision = evaluate_prediction(
            target_position,
            release_moisture[i],
            release_speeds[i],
            config,
            predicted_moisture=release_predictions[i],
        )

        if decision["should_release"]:
            release_rows.append({
                "time_s": float(release_times[i]),
                "position_m": float(target_position),
                "sensor_position_m": float(
                    sensor_positions_for_release[i]
                ),
                "speed_m_s": float(release_speeds[i]),
                "moisture_pct": float(release_predictions[i]),
                "target_depth_mm": decision["target_depth_mm"],
                "actuator_depth_mm": float(
                    np.interp(
                        release_times[i],
                        times,
                        actual,
                    )
                ),
                "measured_moisture_pct": float(release_moisture[i]),
                "predicted_moisture_pct": float(release_predictions[i]),
                "dominant_expert": int(release_dominant[i]),
                "expert_0_weight": float(release_weights[i, 0]),
                "expert_1_weight": float(release_weights[i, 1]),
            })

    return log, pd.DataFrame(release_rows)