from collections.abc import Mapping, Sequence
import numpy as np

from .compensation import calculate_release_target
from .prediction_logic import evaluate_prediction
from .validation import validate_inputs


def _build_release_events(field_positions, field_moisture, speed_time, speed_values, config):
    validate_inputs(field_positions, field_moisture, speed_time, speed_values, config)
    field_positions = np.asarray(field_positions, dtype=float)
    field_moisture = np.asarray(field_moisture, dtype=float)
    speed_time = np.asarray(speed_time, dtype=float)
    speed_values = np.asarray(speed_values, dtype=float)

    # Build vehicle position from velocity using trapezoidal integration.
    positions = np.empty(len(speed_time), dtype=float)
    positions[0] = field_positions[0]
    for i in range(1, len(speed_time)):
        dt = speed_time[i] - speed_time[i-1]
        positions[i] = positions[i-1] + 0.5 * (speed_values[i-1] + speed_values[i]) * dt

    end = min(float(positions[-1]), float(field_positions[-1]))
    targets = np.arange(float(positions[0]), end + 1e-12, float(config["target_spacing_m"]))
    target_time = np.interp(targets, positions, speed_time)
    target_speed = np.interp(target_time, speed_time, speed_values)
    target_moisture = np.interp(targets, field_positions, field_moisture)

    events = []
    for p, t, speed, moisture in zip(targets, target_time, target_speed, target_moisture):
        decision = evaluate_prediction(p, moisture, speed, config)
        if not decision["should_release"]:
            continue
        events.append(calculate_release_target({"time_s": float(t), **decision}, config))
    return events


def create_release_stream(
    field_positions: list[float], field_moisture: list[float],
    speed_time: list[float], speed_values: list[float],
    config: dict[str, float],
):
    """Create an RxPY stream with exact target-spacing release events.

    Unlike the original V1 scan rule, this implementation can emit multiple
    release positions between two sensor/control samples.
    """
    try:
        import reactivex as rx
    except ImportError as exc:
        raise ImportError("reactivex is required for create_release_stream; install requirements.txt") from exc

    def factory(_scheduler=None):
        return rx.from_iterable(_build_release_events(
            field_positions, field_moisture, speed_time, speed_values, config
        ))
    return rx.defer(factory)
