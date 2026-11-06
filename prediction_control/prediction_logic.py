from collections.abc import Mapping


def moisture_to_depth(
    moisture_pct: float,
    min_moisture: float,
    max_moisture: float,
    min_depth_mm: float,
    max_depth_mm: float,
) -> float:
    """Map model-predicted moisture to the requested seeding depth.

    The control-layer rule remains intentionally simple and configurable:
    wetter soil -> shallower target depth.
    """
    clipped_moisture = max(min_moisture, min(float(moisture_pct), max_moisture))
    moisture_range = max_moisture - min_moisture
    if moisture_range == 0:
        return float(min_depth_mm)
    moisture_ratio = (clipped_moisture - min_moisture) / moisture_range
    depth_range = max_depth_mm - min_depth_mm
    return float(max_depth_mm - moisture_ratio * depth_range)


def evaluate_prediction(
    position: float,
    moisture: float,
    speed: float,
    config: Mapping[str, float],
    *,
    predicted_moisture: float | None = None,
    prediction_std: float | None = None,
    model_regime: int | None = None,
) -> dict:
    """Convert moisture prediction into a control decision.

    ``moisture`` is the measured/provided sensor value.  When Hao's model is
    connected, ``predicted_moisture`` is the value used for the control
    decision.  Omitting it preserves backward compatibility with the original
    Tony interface.
    """
    control_moisture = float(moisture if predicted_moisture is None else predicted_moisture)
    target_depth = moisture_to_depth(
        control_moisture,
        config["min_moisture"],
        config["max_moisture"],
        config["min_depth_mm"],
        config["max_depth_mm"],
    )
    should_release = config["min_moisture"] <= control_moisture <= config["max_moisture"]

    result = {
        "position_m": float(position),
        "speed_m_s": float(speed),
        "moisture_pct": control_moisture,
        "measured_moisture_pct": float(moisture),
        "predicted_moisture_pct": control_moisture,
        "should_release": bool(should_release),
        "target_depth_mm": float(target_depth),
    }
    if prediction_std is not None:
        result["prediction_std_pct"] = float(prediction_std)
    if model_regime is not None:
        result["model_regime"] = int(model_regime)
    return result
