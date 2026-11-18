"""Drop-in backend for Manan's unchanged ``run_simulation`` UI API."""
from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd

from interface import DEFAULT_CONFIG
from .dataset_pipeline import load_project_dataset
from .hao_model_runtime import HaoMixtureGPRRuntime
from .prediction_logic import evaluate_prediction
from .validation import validate_inputs

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
    *,
    model=None,
    lateral_m=None,
):
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

    # Convert NumPy containers to ordinary lists without coercing values.
    validation_inputs = [
        values.tolist() if isinstance(values, np.ndarray) else values
        for values in (
            field_positions,
            field_moisture,
            speed_time,
            speed_values,
        )
    ]

    validate_inputs(*validation_inputs, config)

    if not np.isfinite(control_dt_s) or control_dt_s <= 0:
        raise ValueError("control_dt_s must be finite and greater than 0")

    if len(speed_time) < 2:
        raise ValueError("At least two speed timestamps are required")

    if speed_time[-1] <= 0:
        raise ValueError("The final speed timestamp must be greater than 0")

    # Run the moisture-triggered seed-release control simulation.

    if model is None:
        _, model = _resources()

    field_positions = np.asarray(field_positions, float)
    field_moisture = np.asarray(field_moisture, float)
    speed_time = np.asarray(speed_time, float)
    speed_values = np.asarray(speed_values, float)

    lateral = (
        float(lateral_m)
        if lateral_m is not None
        else _estimate_lateral(field_positions, field_moisture)
    )
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

    # Determine the requested target depth at each control update.
    # Retain the complete decision at each control update.
    decisions = [
        evaluate_prediction(
            position,
            moisture,
            speed,
            config,
        )
        for position, moisture, speed, predicted_moisture in zip(
            sensor_positions,
            sensor_moisture,
            speeds,
            pred,
        )
    ]

    target = np.array(
        [decision["target_depth_mm"] for decision in decisions],
        dtype=float,
    )

    # retaining two additional outputs
    release_eligible = np.array(
        [decision["should_release"] for decision in decisions],
        dtype=bool,
    )

    control_moisture = np.array(
        [decision["moisture_pct"] for decision in decisions],
        dtype=float,
    )

    # Simulated actuator response with commands held between updates.
    # Assume the actuator starts at the first requested depth.
    actual = np.empty_like(target)
    tau = float(actuator_tau_s)

    if len(target):
        actual[0] = target[0]

    for i in range(1, len(target)):
        elapsed_s = float(times[i] - times[i - 1])
        previous_command = target[i - 1]

        if tau == 0.0:
            actual[i] = previous_command
        else:
            decay = np.exp(-elapsed_s / tau)
            actual[i] = (
                previous_command
                + (actual[i - 1] - previous_command) * decay
            )

    # Continuous control log for the animation, charts, and diagnostics.
    log = pd.DataFrame({
        "time_s": times,
        "position_m": positions,
        "sensor_position_m": sensor_positions,
        "speed_m_s": speeds,
        "moisture_pct": control_moisture,
        "target_depth_mm": target,
        "actuator_depth_mm": actual,
        "measured_moisture_pct": sensor_moisture,
        "predicted_moisture_pct": pred,
        "control_moisture_pct": control_moisture,
        "release_eligible": release_eligible,
        "decision_reason": [
            "within_moisture_range"
            if eligible
            else "outside_moisture_range"
            for eligible in release_eligible
        ],
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

    # Evaluate each candidate using moisture at its target ground position.
    # Sensor offset will determine observation lead time, not shift this lookup.
    sensor_positions_for_release = targets.copy()

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

    # Find the command active at each release time.
    command_indices = np.searchsorted(times, release_times, side="right") - 1
    command_indices = np.clip(command_indices, 0, len(times) - 1)
    elapsed_since_command = (release_times - times[command_indices])

    if tau == 0.0:
        release_actual_depth = target[command_indices].copy()
    else:
        release_actual_depth = (
            target[command_indices]
            + (
                actual[command_indices]
                - target[command_indices]
            )
            * np.exp(-elapsed_since_command / tau)
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
        )

        if decision["should_release"]:
            release_rows.append({
                "time_s": float(release_times[i]),
                "position_m": float(target_position),
                "sensor_position_m": float(
                    sensor_positions_for_release[i]
                ),
                "speed_m_s": float(release_speeds[i]),
                "moisture_pct": float(decision["moisture_pct"]),
                "target_depth_mm": decision["target_depth_mm"],
                "actuator_depth_mm": float(release_actual_depth[i]),
                "measured_moisture_pct": float(release_moisture[i]),
                "predicted_moisture_pct": float(release_predictions[i]),
                "dominant_expert": int(release_dominant[i]),
                "expert_0_weight": float(release_weights[i, 0]),
                "expert_1_weight": float(release_weights[i, 1]),
            })

# Patch: handle runs with zero releases (edge case)
    release_columns = [
        "time_s",
        "position_m",
        "sensor_position_m",
        "speed_m_s",
        "moisture_pct",
        "target_depth_mm",
        "actuator_depth_mm",
        "measured_moisture_pct",
        "predicted_moisture_pct",
        "dominant_expert",
        "expert_0_weight",
        "expert_1_weight",
    ]
    releases = pd.DataFrame(release_rows, columns=release_columns)

    return log, releases