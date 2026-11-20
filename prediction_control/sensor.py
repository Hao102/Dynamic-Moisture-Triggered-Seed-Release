# Moisture filtering, independent of the dashboard and model.

from collections import deque
from dataclasses import dataclass
from math import isfinite
from statistics import median


@dataclass(frozen=True)
class SensorReading:
    raw_moisture_pct: float | None
    filtered_moisture_pct: float | None
    valid: bool
    ready: bool
    status: str


class MoistureFilter:
    """Filter a bounded history of valid moisture observations.

    Only current and previous observations are used.
    Invalid observations are not added to the history.
    Create or reset one filter at the beginning of each row.
    """

    def __init__(self, window_size: int = 3):
        if (
            isinstance(window_size, bool)
            or not isinstance(window_size, int)
            or window_size < 3
            or window_size % 2 == 0
        ):
            raise ValueError("window_size must be an odd integer of at least 3")

        self._history = deque(maxlen=window_size)
        self._window_size = window_size

    def reset(self) -> None:
        # Clear history when starting a new row or restarting acquisition.
        self._history.clear()

    def update(self, moisture_pct: float | None) -> SensorReading:
        # Process exactly one new sensor observation.
        if moisture_pct is None or isinstance(moisture_pct, (bool, str, bytes)):
            return SensorReading(None, None, False, False, "invalid")

        try:
            raw = float(moisture_pct)
        except (TypeError, ValueError, OverflowError):
            return SensorReading(None, None, False, False, "invalid")

        if not isfinite(raw) or not 0.0 <= raw <= 100.0:
            return SensorReading(raw, None, False, False, "invalid")

        self._history.append(raw)
        ready = len(self._history) == self._window_size

        # During startup, return the latest observation but mark it unready.
        filtered = float(median(self._history)) if ready else raw

        return SensorReading(
            raw_moisture_pct=raw,
            filtered_moisture_pct=filtered,
            valid=True,
            ready=ready,
            status="filtered" if ready else "warming_up",
        )