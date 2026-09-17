from collections.abc import Mapping


def moisture_to_depth(
    moisture_pct: float,
    min_moisture: float,
    max_moisture: float,
    min_depth_mm: float,
    max_depth_mm: float,
) -> float:
    """
    Baseline moisture-to-depth mapping.

    This is an initial implementation only.
    Replace/refine the internal mathematical relationship when Hao's
    final mathematical model is available.
    """
    clipped_moisture = max(
        min_moisture,
        min(moisture_pct, max_moisture),
    )

    moisture_range = max_moisture - min_moisture

    # Avoid division by zero if both moisture bounds are identical.
    if moisture_range == 0:
        return float(min_depth_mm)

    moisture_ratio = (
        clipped_moisture - min_moisture
    ) / moisture_range

    # Baseline assumption only:
    # wetter soil -> shallower target depth.
    depth_range = max_depth_mm - min_depth_mm
    target_depth = max_depth_mm - moisture_ratio * depth_range

    return float(target_depth)


def evaluate_prediction(
    position: float,
    moisture: float,
    speed: float,
    config: Mapping[str, float],
) -> dict:
    """
    Baseline prediction/control interface.

    Expected output structure is intentionally stable so that Hao's final
    mathematical model can replace the internal decision rule later without
    changing the RxPY pipeline or dashboard interface.
    """
    target_depth = moisture_to_depth(
        moisture_pct=moisture,
        min_moisture=config["min_moisture"],
        max_moisture=config["max_moisture"],
        min_depth_mm=config["min_depth_mm"],
        max_depth_mm=config["max_depth_mm"],
    )

    # TODO:
    # Replace this baseline decision rule with final mathematical model.
    #
    # Current placeholder:
    # seed only when moisture lies inside the configured range.
    should_release = (
        config["min_moisture"]
        <= moisture
        <= config["max_moisture"]
    )

    return {
        "position_m": float(position),
        "speed_m_s": float(speed),
        "moisture_pct": float(moisture),
        "should_release": bool(should_release),
        "target_depth_mm": float(target_depth),
    }
