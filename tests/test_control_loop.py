from types import SimpleNamespace

import pytest

from prediction_control.control_loop import RealtimeController


CONFIG = {
    "min_moisture": 1.0,
    "max_moisture": 10.0,
    "min_depth_mm": 15.0,
    "max_depth_mm": 40.0,
}


class FakeModel:
    def __init__(self, value):
        self.value = value
        self.calls = []

    def predict(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(moisture_pct=self.value)


def feed(controller, values):
    result = None
    for index, value in enumerate(values):
        result = controller.update(index * 0.14, value)
    return result


def test_startup_does_not_issue_depth_command():
    controller = RealtimeController(CONFIG)

    result = controller.update(0.0, 4.0)

    assert result["command_valid"] is False
    assert result["target_depth_mm"] is None


def test_drier_soil_requests_deeper_depth():
    dry = feed(RealtimeController(CONFIG), [2.0, 2.0, 2.0])
    wet = feed(RealtimeController(CONFIG), [8.0, 8.0, 8.0])

    assert dry["command_valid"] is True
    assert wet["command_valid"] is True
    assert dry["target_depth_mm"] > wet["target_depth_mm"]


def test_model_assists_filtered_sensor():
    model = FakeModel(5.0)
    controller = RealtimeController(
        CONFIG, model=model, model_weight=0.2
    )

    result = feed(controller, [4.0, 4.0, 4.0])

    assert result["control_moisture_pct"] == pytest.approx(4.2)
    assert result["predicted_moisture_pct"] == pytest.approx(5.0)
    assert result["control_source"] == "model_assisted"
    assert len(model.calls) == 1
    assert model.calls[0]["measured_moisture_pct"] == pytest.approx(4.0)


def test_spike_is_filtered_before_model_inference():
    model = FakeModel(4.0)
    controller = RealtimeController(CONFIG, model=model)

    result = feed(controller, [4.0, 4.0, 20.0])

    assert result["measured_moisture_pct"] == pytest.approx(20.0)
    assert result["filtered_moisture_pct"] == pytest.approx(4.0)
    assert result["control_moisture_pct"] == pytest.approx(4.0)
    assert model.calls[0]["measured_moisture_pct"] == pytest.approx(4.0)


def test_invalid_reading_does_not_call_model_or_issue_command():
    model = FakeModel(4.0)
    controller = RealtimeController(CONFIG, model=model)
    feed(controller, [4.0, 4.0, 4.0])

    result = controller.update(0.42, None)

    assert result["command_valid"] is False
    assert result["target_depth_mm"] is None
    assert len(model.calls) == 1


def test_invalid_prediction_falls_back_to_filtered_sensor():
    controller = RealtimeController(
        CONFIG, model=FakeModel(float("nan"))
    )

    result = feed(controller, [4.0, 4.0, 4.0])

    assert result["command_valid"] is True
    assert result["control_moisture_pct"] == pytest.approx(4.0)
    assert result["control_source"] == "sensor_only_invalid_prediction"


def test_reset_requires_new_filter_warmup():
    controller = RealtimeController(CONFIG)
    feed(controller, [4.0, 4.0, 4.0])

    controller.reset()
    result = controller.update(0.0, 8.0)

    assert result["command_valid"] is False
    assert result["sensor_status"] == "warming_up"