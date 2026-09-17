from collections.abc import Mapping, Sequence

import numpy as np
import reactivex as rx
from reactivex import operators as ops

from .prediction_logic import evaluate_prediction
from .validation import validate_inputs


def _build_movement_samples(
    field_positions: Sequence[float],
    field_moisture: Sequence[float],
    speed_time: Sequence[float],
    speed_values: Sequence[float],
) -> list[dict]:
    """
    Convert the speed profile into time/position/moisture samples.

    Position is estimated by integrating speed over time using the
    trapezoidal rule. Moisture is interpolated from the field-position data.

    This is a baseline implementation for the initial pipeline.
    """
    samples: list[dict] = []
    current_position = float(field_positions[0])

    for i, current_time in enumerate(speed_time):
        current_speed = float(speed_values[i])

        if i > 0:
            dt = float(speed_time[i] - speed_time[i - 1])
            previous_speed = float(speed_values[i - 1])

            # Trapezoidal integration of velocity over the time interval.
            current_position += 0.5 * (
                previous_speed + current_speed
            ) * dt

        current_moisture = float(
            np.interp(
                current_position,
                field_positions,
                field_moisture,
            )
        )

        samples.append(
            {
                "time_s": float(current_time),
                "position_m": current_position,
                "speed_m_s": current_speed,
                "moisture_pct": current_moisture,
            }
        )

    return samples


def _apply_prediction(sample: dict, config: Mapping[str, float]) -> dict:
    prediction = evaluate_prediction(
        position=sample["position_m"],
        moisture=sample["moisture_pct"],
        speed=sample["speed_m_s"],
        config=config,
    )

    return {
        **sample,
        **prediction,
    }


def _apply_spacing_rule(
    state: dict,
    item: dict,
    target_spacing_m: float,
) -> dict:
    """
    Baseline stateful spacing rule.

    This keeps track of the last emitted release position. The final spacing
    behaviour can be refined later together with the mathematical model and
    compensation logic.
    """
    last_release_position = state["last_release_position"]

    spacing_ok = (
        last_release_position is None
        or item["position_m"] - last_release_position >= target_spacing_m
    )

    emit = item["should_release"] and spacing_ok

    return {
        "last_release_position": (
            item["position_m"] if emit else last_release_position
        ),
        "item": item,
        "emit": emit,
    }


def _build_release_event(state: dict) -> dict:
    item = state["item"]

    # Each emitted dictionary represents a positive seed-release signal.
    # TODO: apply sensor offset / actuator-delay compensation here later.
    return {
        "time_s": float(item["time_s"]),
        "position_m": float(item["position_m"]),
        "speed_m_s": float(item["speed_m_s"]),
        "moisture_pct": float(item["moisture_pct"]),
        "target_depth_mm": float(item["target_depth_mm"]),
    }


def create_release_stream(
    field_positions: list[float],
    field_moisture: list[float],
    speed_time: list[float],
    speed_values: list[float],
    config: dict[str, float],
) -> rx.Observable:
    """
    Create the initial RxPY release-event stream.

    Validation and sample construction are deferred until subscription so that
    exceptions are propagated through RxPY's on_error() path.
    """

    def stream_factory(_scheduler=None):
        validate_inputs(
            field_positions=field_positions,
            field_moisture=field_moisture,
            speed_time=speed_time,
            speed_values=speed_values,
            config=config,
        )

        samples = _build_movement_samples(
            field_positions=field_positions,
            field_moisture=field_moisture,
            speed_time=speed_time,
            speed_values=speed_values,
        )

        return rx.from_iterable(samples).pipe(
            # 1. Apply the baseline prediction/control logic.
            ops.map(
                lambda sample: _apply_prediction(
                    sample,
                    config,
                )
            ),

            # 2. Keep release spacing as stream state.
            ops.scan(
                lambda state, item: _apply_spacing_rule(
                    state,
                    item,
                    config["target_spacing_m"],
                ),
                seed={
                    "last_release_position": None,
                    "item": None,
                    "emit": False,
                },
            ),

            # 3. Allow only actual release events to continue downstream.
            ops.filter(lambda state: state["emit"]),

            # 4. Convert the internal state into the agreed external event schema.
            ops.map(_build_release_event),
        )

    return rx.defer(stream_factory)
