"""Sensor-to-release timing / position compensation logic."""


def calculate_release_target(event, config):
    """Calculate the compensated release timing or position for a detected condition."""
    # TODO: Account for sensor-to-release distance, actuator latency,
    #       machine speed, and any agreed compensation rules.
    raise NotImplementedError("TODO: implement release compensation logic")
