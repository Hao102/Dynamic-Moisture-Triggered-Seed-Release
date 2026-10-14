"""Public control API.

Kept at repository root for compatibility with the original interface spec.
"""
from prediction_control import (
    calculate_release_target,
    create_release_stream,
    evaluate_prediction,
    moisture_to_depth,
    run_dataset_pipeline,
)

DEFAULT_CONFIG: dict[str, float] = {
    "target_spacing_m": 0.03,
    "min_moisture": 1.0,
    "max_moisture": 10.0,
    "min_depth_mm": 15.0,
    "max_depth_mm": 40.0,
    "sensor_offset_m": 0.50,
    "actuator_delay_s": 0.10,
    "actuator_tau_s": 0.15,
    "model_depth_cm": 5.0,
}

__all__ = [
    "DEFAULT_CONFIG", "create_release_stream", "evaluate_prediction",
    "moisture_to_depth", "calculate_release_target", "run_dataset_pipeline",
]
