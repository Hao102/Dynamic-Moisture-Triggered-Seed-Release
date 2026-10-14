import math
from collections.abc import Mapping, Sequence

REQUIRED_CONFIG_KEYS = {
    "target_spacing_m", "min_moisture", "max_moisture",
    "min_depth_mm", "max_depth_mm",
}
OPTIONAL_NON_NEGATIVE_KEYS = {
    "sensor_offset_m", "actuator_delay_s", "actuator_tau_s", "model_depth_cm",
}


def _validate_not_empty(values: Sequence[float], name: str) -> None:
    if values is None or len(values) == 0:
        raise ValueError(f"{name} cannot be empty")


def _validate_numeric_values(values: Sequence[float], name: str) -> None:
    for index, value in enumerate(values):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(f"{name}[{index}] must be numeric, got {type(value).__name__}")
        if not math.isfinite(value):
            raise ValueError(f"{name}[{index}] must be finite, got {value}")


def _validate_config(config: Mapping[str, float]) -> None:
    if config is None:
        raise ValueError("config cannot be None")
    if not isinstance(config, Mapping):
        raise TypeError("config must be a mapping/dictionary")
    missing = REQUIRED_CONFIG_KEYS - set(config)
    if missing:
        raise ValueError(f"Missing config keys: {sorted(missing)}")
    for key in REQUIRED_CONFIG_KEYS | (OPTIONAL_NON_NEGATIVE_KEYS & set(config)):
        value = config[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(f"config['{key}'] must be numeric")
        if not math.isfinite(value):
            raise ValueError(f"config['{key}'] must be finite")
    if config["target_spacing_m"] <= 0:
        raise ValueError("target_spacing_m must be greater than 0")
    if config["min_moisture"] > config["max_moisture"]:
        raise ValueError("min_moisture cannot be greater than max_moisture")
    if config["min_depth_mm"] < 0 or config["max_depth_mm"] < 0:
        raise ValueError("seed depth values cannot be negative")
    if config["min_depth_mm"] > config["max_depth_mm"]:
        raise ValueError("min_depth_mm cannot be greater than max_depth_mm")
    for key in OPTIONAL_NON_NEGATIVE_KEYS:
        if key in config and config[key] < 0:
            raise ValueError(f"config['{key}'] must be non-negative")


def validate_inputs(field_positions, field_moisture, speed_time, speed_values, config) -> None:
    _validate_not_empty(field_positions, "field_positions")
    _validate_not_empty(field_moisture, "field_moisture")
    _validate_not_empty(speed_time, "speed_time")
    _validate_not_empty(speed_values, "speed_values")
    if len(field_positions) != len(field_moisture):
        raise ValueError("field_positions and field_moisture must have the same length")
    if len(speed_time) != len(speed_values):
        raise ValueError("speed_time and speed_values must have the same length")
    _validate_numeric_values(field_positions, "field_positions")
    _validate_numeric_values(field_moisture, "field_moisture")
    _validate_numeric_values(speed_time, "speed_time")
    _validate_numeric_values(speed_values, "speed_values")
    if any(field_positions[i] < field_positions[i - 1] for i in range(1, len(field_positions))):
        raise ValueError("field_positions must be sorted in ascending order")
    if any(speed_time[i] <= speed_time[i - 1] for i in range(1, len(speed_time))):
        raise ValueError("speed_time must be strictly increasing")
    if any(speed < 0 for speed in speed_values):
        raise ValueError("speed_values cannot contain negative speeds")
    _validate_config(config)
