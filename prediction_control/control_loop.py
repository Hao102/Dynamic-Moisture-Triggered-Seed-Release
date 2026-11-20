"""Stateful, sample-by-sample moisture and depth control.

No dashboard imports, dataset loading, model training, or file access.
Release scheduling and spacing control are separate responsibilities.
"""

from math import isfinite

from .prediction_logic import moisture_to_depth
from .sensor import MoistureFilter


class RealtimeController:
    """One controller instance per seeder row.

    The model must already be trained. Its predict() method must return
    an object with a moisture_pct attribute.

    Model assistance is optional: valid filtered sensor data remains
    usable when no model is supplied.
    """

    def __init__(
        self,
        config,
        *,
        model=None,
        lateral_m=15.0,
        depth_cm=5.0,
        window_size=3,
        model_weight=0.2,
    ):
        if not isfinite(model_weight) or not 0.0 <= model_weight <= 0.5:
            raise ValueError("model_weight must be between 0 and 0.5")

        self.config = dict(config)
        self.model = model
        self.lateral_m = float(lateral_m)
        self.depth_cm = float(depth_cm)
        self.model_weight = float(model_weight)
        self.sensor = MoistureFilter(window_size=window_size)

    def reset(self):
        # Reset sensor history before starting another row.
        self.sensor.reset()

    def update(self, position_m, raw_moisture_pct):
        """Process one new moisture observation at the sensor position.

        Returns a depth command only after the filter is ready.
        Does not authorise or schedule seed release.
        """
        position_m = float(position_m)
        if not isfinite(position_m) or position_m < 0:
            raise ValueError("position_m must be finite and non-negative")

        reading = self.sensor.update(raw_moisture_pct)

        result = {
            "sensor_position_m": position_m,
            "measured_moisture_pct": reading.raw_moisture_pct,
            "filtered_moisture_pct": reading.filtered_moisture_pct,
            "predicted_moisture_pct": None,
            "control_moisture_pct": None,
            "target_depth_mm": None,
            "command_valid": False,
            "sensor_status": reading.status,
            "control_source": "unavailable",
        }

        if not reading.valid or not reading.ready:
            return result

        filtered = reading.filtered_moisture_pct
        control = filtered
        source = "sensor_only"

        if self.model is not None and self.model_weight > 0.0:
            prediction = self.model.predict(
                position_m=position_m,
                lateral_m=self.lateral_m,
                depth_cm=self.depth_cm,
                measured_moisture_pct=filtered,
            )
            predicted = float(prediction.moisture_pct)

            if isfinite(predicted) and 0.0 <= predicted <= 100.0:
                result["predicted_moisture_pct"] = predicted
                control = (
                    (1.0 - self.model_weight) * filtered
                    + self.model_weight * predicted
                )
                source = "model_assisted"
            else:
                source = "sensor_only_invalid_prediction"

        result.update({
            "control_moisture_pct": control,
            "target_depth_mm": moisture_to_depth(
                control,
                self.config["min_moisture"],
                self.config["max_moisture"],
                self.config["min_depth_mm"],
                self.config["max_depth_mm"],
            ),
            "command_valid": True,
            "control_source": source,
        })

        return result