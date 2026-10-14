"""Sensor-to-release timing and position compensation."""
from __future__ import annotations

from collections.abc import Mapping


def calculate_release_target(event: dict, config: Mapping[str, float]) -> dict:
    """Apply sensor offset and actuator latency to a planned seed position.

    Assumption: the moisture sensor is ``sensor_offset_m`` ahead of the seed
    outlet in the direction of travel.  The command is scheduled so that the
    physical release occurs at the target position whenever there is enough
    lead time.  If actuator delay is larger than the available travel time,
    ``compensation_error_m`` reports the unavoidable late-release distance.
    """
    speed = float(event.get("speed_m_s", 0.0))
    target_position = float(event["position_m"])
    sensed_time = float(event["time_s"])
    offset = float(config.get("sensor_offset_m", 0.0))
    delay = float(config.get("actuator_delay_s", 0.0))

    if speed <= 0:
        return {
            **event,
            "target_position_m": target_position,
            "command_time_s": sensed_time,
            "release_time_s": sensed_time + delay,
            "position_m": target_position,
            "compensation_error_m": 0.0,
        }

    travel_time = offset / speed
    wait_before_command = max(travel_time - delay, 0.0)
    command_time = sensed_time + wait_before_command
    release_time = command_time + delay
    late_time = max(delay - travel_time, 0.0)
    actual_position = target_position + speed * late_time

    return {
        **event,
        "target_position_m": target_position,
        "command_time_s": float(command_time),
        "release_time_s": float(release_time),
        "time_s": float(release_time),
        "position_m": float(actual_position),
        "compensation_error_m": float(actual_position - target_position),
    }
