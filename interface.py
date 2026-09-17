import reactivex as rx


DEFAULT_CONFIG: dict[str, float] = {
    "target_spacing_m": 0.03,
    "min_moisture": 15.0,
    "max_moisture": 25.0,
    "min_depth_mm": 15.0,
    "max_depth_mm": 40.0,
}


def create_release_stream(
    field_positions: list[float],
    field_moisture: list[float],
    speed_time: list[float],
    speed_values: list[float],
    config: dict[str, float],
) -> rx.Observable:
    raise NotImplementedError


def moisture_to_depth(
    moisture_pct: float,
    min_moisture: float,
    max_moisture: float,
    min_depth_mm: float,
    max_depth_mm: float,
) -> float:
    raise NotImplementedError
