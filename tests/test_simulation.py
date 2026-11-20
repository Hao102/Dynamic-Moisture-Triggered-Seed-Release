from types import SimpleNamespace

import numpy as np
import pytest

from prediction_control.simulation import run_simulation


class FakeModel:
    def predict(self, **kwargs):
        return SimpleNamespace(
            moisture_pct=5.0,
            dominant_expert=0,
            expert_weights=(1.0, 0.0),
        )

    def predict_batch(self, X):
        count = len(X)
        return (
            np.full(count, 5.0),
            np.zeros(count, dtype=int),
            np.tile([1.0, 0.0], (count, 1)),
        )


def test_simulation_depth_uses_filtered_model_assisted_moisture():
    log, releases = run_simulation(
        field_positions=[0.0, 1.0],
        field_moisture=[4.0, 4.0],
        speed_time=[0.0, 1.0],
        speed_values=[1.0, 1.0],
        target_spacing_m=0.020,
        control_dt_s=0.1,
        actuator_tau_s=0.15,
        min_moisture=1.0,
        max_moisture=10.0,
        min_depth=15.0,
        max_depth=40.0,
        sensor_offset_m=0.0,
        model=FakeModel(),
        lateral_m=15.0,
    )

    assert log["command_valid"].iloc[:2].tolist() == [False, False]

    ready = log.loc[log["command_valid"]]
    assert not ready.empty

    assert ready["filtered_moisture_pct"].to_numpy() == pytest.approx(4.0)
    assert ready["predicted_moisture_pct"].to_numpy() == pytest.approx(5.0)
    assert ready["control_moisture_pct"].to_numpy() == pytest.approx(4.2)

    expected_depth = 40.0 - ((4.2 - 1.0) / 9.0) * 25.0
    assert ready["target_depth_mm"].to_numpy() == pytest.approx(expected_depth)
    assert set(ready["control_source"]) == {"model_assisted"}

def test_release_uses_controller_observation_available_before_command():
    log, releases = run_simulation(
        field_positions=[0.0, 1.0],
        field_moisture=[4.0, 4.0],
        speed_time=[0.0, 1.0],
        speed_values=[1.0, 1.0],
        target_spacing_m=0.020,
        control_dt_s=0.1,
        actuator_tau_s=0.15,
        min_moisture=1.0,
        max_moisture=10.0,
        min_depth=15.0,
        max_depth=40.0,
        sensor_offset_m=0.0,
        model=FakeModel(),
        lateral_m=15.0,
    )

    assert not releases.empty
    assert (
        releases["observation_time_s"]
        <= releases["command_time_s"] + 1e-12
    ).all()
    assert releases["control_moisture_pct"].to_numpy() == pytest.approx(4.2)
    assert set(releases["control_source"]) == {"model_assisted"}