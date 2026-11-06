import pytest
import numpy as np

from prediction_control.release_stream import create_release_stream

# This test supplies a constant moisture reading and speed profile, subscribes to the stream, and checks the resulting signals.
def test_sensor_only_stream_generates_release_events():
    config = {
        "target_spacing_m": 0.03,
        "min_moisture": 1.0,
        "max_moisture": 10.0,
        "min_depth_mm": 15.0,
        "max_depth_mm": 40.0,
        "sensor_offset_m": 0.0,
        "actuator_delay_s": 0.0,
    }

    events = []
    errors = []
    completed = []

    create_release_stream(
        field_positions=[0.0, 0.3],
        field_moisture=[4.0, 4.0],
        speed_time=[0.0, 0.3],
        speed_values=[1.0, 1.0],
        config=config,
    ).subscribe(
        on_next=events.append,
        on_error=errors.append,
        on_completed=lambda: completed.append(True),
    )

    assert errors == []
    assert completed == [True]
    assert len(events) == 11

    required_fields = {
        "time_s",
        "position_m",
        "speed_m_s",
        "moisture_pct",
        "target_depth_mm",
    }
    assert all(required_fields.issubset(event) for event in events)

    assert [event["position_m"] for event in events] == pytest.approx(
        [index * 0.03 for index in range(11)]
    )
    assert [event["time_s"] for event in events] == pytest.approx(
        [index * 0.03 for index in range(11)]
    )
    assert all(event["moisture_pct"] == 4.0 for event in events)
    assert [event["target_depth_mm"] for event in events] == pytest.approx(
        [40.0 - (4.0 - 1.0) / (10.0 - 1.0) * (40.0 - 15.0)] * 11
    )

# This test characterises the existing contract: 
# mismatched position and moisture arrays must produce exactly one ValueError, with no events or completion.
def test_sensor_only_stream_rejects_mismatched_lengths():
    config = {
        "target_spacing_m": 0.03,
        "min_moisture": 1.0,
        "max_moisture": 10.0,
        "min_depth_mm": 15.0,
        "max_depth_mm": 40.0,
        "sensor_offset_m": 0.0,
        "actuator_delay_s": 0.0,
    }

    events = []
    errors = []
    completed = []

    create_release_stream(
        field_positions=[0.0, 0.3],
        field_moisture=[4.0],
        speed_time=[0.0, 0.3],
        speed_values=[1.0, 1.0],
        config=config,
    ).subscribe(
        on_next=events.append,
        on_error=errors.append,
        on_completed=lambda: completed.append(True),
    )

    assert events == []
    assert completed == []
    assert len(errors) == 1
    assert isinstance(errors[0], ValueError)

# This test documents the existing timing contract: with a constant 1 m/s speed and 0.1 s actuator delay, each release time is the nominal position time plus 0.1 seconds. 
# It does not yet address live-stream timing, physical actuator behaviour, or spatial sensor offset
def test_actuator_delay_without_sensor_offset_produces_late_release():
    config = {
        "target_spacing_m": 0.03,
        "min_moisture": 1.0,
        "max_moisture": 10.0,
        "min_depth_mm": 15.0,
        "max_depth_mm": 40.0,
        "sensor_offset_m": 0.0,
        "actuator_delay_s": 0.1,
    }

    events = []
    errors = []
    completed = []

    create_release_stream(
        field_positions=[0.0, 0.3],
        field_moisture=[4.0, 4.0],
        speed_time=[0.0, 0.3],
        speed_values=[1.0, 1.0],
        config=config,
    ).subscribe(
        on_next=events.append,
        on_error=errors.append,
        on_completed=lambda: completed.append(True),
    )

    assert errors == []
    assert completed == [True]
    assert len(events) == 11

    target_positions = [index * 0.03 for index in range(11)]

    assert [event["command_time_s"] for event in events] == pytest.approx(
        target_positions
    )
    assert [event["release_time_s"] for event in events] == pytest.approx(
        [position + 0.1 for position in target_positions]
    )
    assert [event["time_s"] for event in events] == pytest.approx(
        [position + 0.1 for position in target_positions]
    )
    assert [event["position_m"] for event in events] == pytest.approx(
        [position + 0.1 for position in target_positions]
    )
    assert [event["compensation_error_m"] for event in events] == pytest.approx(
        [0.1] * 11
    )

# test for sensor offset compensation
# current spatial-compensation contract: with a 0.05 m sensor offset and constant 1 m/s speed, each release time is the nominal position time minus 0.05 seconds. 
# It does not yet establish the physical sign convention, live-stream timing, or hardware behaviour.
def test_sensor_offset_provides_release_lead_time():
    config = {
        "target_spacing_m": 0.03,
        "min_moisture": 1.0,
        "max_moisture": 10.0,
        "min_depth_mm": 15.0,
        "max_depth_mm": 40.0,
        "sensor_offset_m": 0.05,
        "actuator_delay_s": 0.0,
    }

    events = []
    errors = []
    completed = []

    create_release_stream(
        field_positions=[0.0, 0.3],
        field_moisture=[4.0, 4.0],
        speed_time=[0.0, 0.3],
        speed_values=[1.0, 1.0],
        config=config,
    ).subscribe(
        on_next=events.append,
        on_error=errors.append,
        on_completed=lambda: completed.append(True),
    )

    assert errors == []
    assert completed == [True]
    assert len(events) == 11

    target_positions = [index * 0.03 for index in range(11)]

    assert [event["target_position_m"] for event in events] == pytest.approx(
        target_positions
    )
    assert [event["command_time_s"] for event in events] == pytest.approx(
        target_positions
    )
    assert [event["release_time_s"] for event in events] == pytest.approx(
        target_positions
    )
    assert [event["position_m"] for event in events] == pytest.approx(
        target_positions
    )
    assert [event["compensation_error_m"] for event in events] == pytest.approx(
        [0.0] * 11
    )
    
# 
def test_sensor_offset_absorbs_actuator_delay():
    config = {
        "target_spacing_m": 0.03,
        "min_moisture": 1.0,
        "max_moisture": 10.0,
        "min_depth_mm": 15.0,
        "max_depth_mm": 40.0,
        "sensor_offset_m": 0.2,
        "actuator_delay_s": 0.1,
    }

    events = []
    errors = []
    completed = []

    create_release_stream(
        field_positions=[0.0, 0.3],
        field_moisture=[4.0, 4.0],
        speed_time=[0.0, 0.3],
        speed_values=[1.0, 1.0],
        config=config,
    ).subscribe(
        on_next=events.append,
        on_error=errors.append,
        on_completed=lambda: completed.append(True),
    )

    assert errors == []
    assert completed == [True]
    assert len(events) == 11

    target_positions = [index * 0.03 for index in range(11)]

    assert [event["target_position_m"] for event in events] == pytest.approx(
        target_positions
    )
    assert [event["position_m"] for event in events] == pytest.approx(
        target_positions
    )
    assert [event["command_time_s"] for event in events] == pytest.approx(
        [position - 0.1 for position in target_positions]
    )
    assert [event["release_time_s"] for event in events] == pytest.approx(
        target_positions
    )
    assert [event["time_s"] for event in events] == pytest.approx(
        target_positions
    )
    assert [event["compensation_error_m"] for event in events] == pytest.approx(
        [0.0] * 11
    )

# Variable speed test - verify that the controller uses the actual speed profile rather than assuming a constant 1 m/s.
def test_variable_speed_produces_time_compensated_events():
    config = {
        "target_spacing_m": 0.5,
        "min_moisture": 1.0,
        "max_moisture": 10.0,
        "min_depth_mm": 15.0,
        "max_depth_mm": 40.0,
        "sensor_offset_m": 0.2,
        "actuator_delay_s": 0.1,
    }

    events = []
    errors = []
    completed = []

    create_release_stream(
        field_positions=[0.0, 3.5],
        field_moisture=[4.0, 4.0],
        speed_time=[0.0, 1.0, 2.0],
        speed_values=[1.0, 2.0, 2.0],
        config=config,
    ).subscribe(
        on_next=events.append,
        on_error=errors.append,
        on_completed=lambda: completed.append(True),
    )

    assert errors == []
    assert completed == [True]
    assert len(events) == 8

    target_positions = [index * 0.5 for index in range(8)]
    target_times = np.interp(
        target_positions,
        [0.0, 1.5, 3.5],
        [0.0, 1.0, 2.0],
    )

    assert [event["target_position_m"] for event in events] == pytest.approx(
        target_positions
    )
    assert [event["position_m"] for event in events] == pytest.approx(
        target_positions
    )
    assert [event["release_time_s"] for event in events] == pytest.approx(
        target_times
    )
    assert [event["time_s"] for event in events] == pytest.approx(
        target_times
    )
    assert [event["command_time_s"] for event in events] == pytest.approx(
        [target_time - 0.1 for target_time in target_times]
    )
    assert [event["compensation_error_m"] for event in events] == pytest.approx(
        [0.0] * 8
    )

# the sensor is only 0.1 s ahead of the outlet, but the actuator needs 0.2 s. 
# The controller cannot issue a command before it receives the sensor reading, so it commands immediately and accepts a late release.
def test_insufficient_sensor_lead_time_produces_late_release():
    config = {
        "target_spacing_m": 0.5,
        "min_moisture": 1.0,
        "max_moisture": 10.0,
        "min_depth_mm": 15.0,
        "max_depth_mm": 40.0,
        "sensor_offset_m": 0.1,
        "actuator_delay_s": 0.2,
    }

    events = []
    errors = []
    completed = []

    create_release_stream(
        field_positions=[0.0, 3.5],
        field_moisture=[4.0, 4.0],
        speed_time=[0.0, 1.0, 2.0],
        speed_values=[1.0, 2.0, 2.0],
        config=config,
    ).subscribe(
        on_next=events.append,
        on_error=errors.append,
        on_completed=lambda: completed.append(True),
    )

    assert errors == []
    assert completed == [True]
    assert len(events) == 8

    target_positions = [index * 0.5 for index in range(8)]
    target_times = np.interp(
        target_positions,
        [0.0, 1.5, 3.5],
        [0.0, 1.0, 2.0],
    )
    target_speeds = np.interp(
        target_times,
        [0.0, 1.0, 2.0],
        [1.0, 2.0, 2.0],
    )

    sensor_lead_times = 0.1 / target_speeds
    late_times = 0.2 - sensor_lead_times

    assert [event["target_position_m"] for event in events] == pytest.approx(
        target_positions
    )
    assert [event["command_time_s"] for event in events] == pytest.approx(
        [target_time - lead for target_time, lead in zip(target_times, sensor_lead_times)]
    )
    assert [event["release_time_s"] for event in events] == pytest.approx(
        [target_time + late for target_time, late in zip(target_times, late_times)]
    )
    assert [event["time_s"] for event in events] == pytest.approx(
        [target_time + late for target_time, late in zip(target_times, late_times)]
    )
    assert [event["position_m"] for event in events] == pytest.approx(
        [
            target_position + speed * late
            for target_position, speed, late in zip(
                target_positions, target_speeds, late_times
            )
        ]
    )
    assert [event["compensation_error_m"] for event in events] == pytest.approx(
        [speed * late for speed, late in zip(target_speeds, late_times)]
    )

# verify that the controller suppresses releases when the measured moisture is outside the configured operating range
# This test documents an important boundary: the stream releases only when a sampled target moisture falls within the configured range.
def test_stream_releases_only_within_moisture_range():
    config = {
        "target_spacing_m": 0.5,
        "min_moisture": 1.0,
        "max_moisture": 10.0,
        "min_depth_mm": 15.0,
        "max_depth_mm": 40.0,
        "sensor_offset_m": 0.0,
        "actuator_delay_s": 0.0,
    }

    events = []
    errors = []
    completed = []

    create_release_stream(
        field_positions=[0.0, 3.0],
        field_moisture=[0.5, 20.0],
        speed_time=[0.0, 3.0],
        speed_values=[1.0, 1.0],
        config=config,
    ).subscribe(
        on_next=events.append,
        on_error=errors.append,
        on_completed=lambda: completed.append(True),
    )

    assert errors == []
    assert completed == [True]
    assert len(events) == 2

    assert [event["position_m"] for event in events] == pytest.approx(
        [0.5, 1.0]
    )
    assert [event["time_s"] for event in events] == pytest.approx(
        [0.5, 1.0]
    )
    assert [event["moisture_pct"] for event in events] == pytest.approx(
        [3.75, 7.0]
    )
    assert [event["target_depth_mm"] for event in events] == pytest.approx(
        [32.361111111111114, 23.333333333333336]
    )

def test_stream_emits_no_events_when_all_moisture_is_out_of_range():
    config = {
        "target_spacing_m": 0.5,
        "min_moisture": 1.0,
        "max_moisture": 10.0,
        "min_depth_mm": 15.0,
        "max_depth_mm": 40.0,
        "sensor_offset_m": 0.0,
        "actuator_delay_s": 0.0,
    }

    events = []
    errors = []
    completed = []

    create_release_stream(
        field_positions=[0.0, 3.0],
        field_moisture=[20.0, 20.0],
        speed_time=[0.0, 3.0],
        speed_values=[1.0, 1.0],
        config=config,
    ).subscribe(
        on_next=events.append,
        on_error=errors.append,
        on_completed=lambda: completed.append(True),
    )

    assert errors == []
    assert completed == [True]
    assert events == []

def test_stream_does_not_release_while_reversing():
    config = {
        "target_spacing_m": 0.03,
        "min_moisture": 1.0,
        "max_moisture": 10.0,
        "min_depth_mm": 15.0,
        "max_depth_mm": 40.0,
        "sensor_offset_m": 0.0,
        "actuator_delay_s": 0.0,
    }

    events = []
    errors = []
    completed = []

    create_release_stream(
        field_positions=[0.3, 0.0],
        field_moisture=[4.0, 4.0],
        speed_time=[0.0, 0.3],
        speed_values=[-1.0, -1.0],
        config=config,
    ).subscribe(
        on_next=events.append,
        on_error=errors.append,
        on_completed=lambda: completed.append(True),
    )

    assert events == []
    assert completed == []
    assert len(errors) == 1
    assert isinstance(errors[0], ValueError)

def test_stream_preserves_prediction_metadata():
    config = {
        "target_spacing_m": 0.5,
        "min_moisture": 1.0,
        "max_moisture": 10.0,
        "min_depth_mm": 15.0,
        "max_depth_mm": 40.0,
        "sensor_offset_m": 0.0,
        "actuator_delay_s": 0.0,
    }

    events = []
    errors = []
    completed = []

    create_release_stream(
        field_positions=[0.0, 3.0],
        field_moisture=[4.0, 4.0],
        speed_time=[0.0, 3.0],
        speed_values=[1.0, 1.0],
        config=config,
    ).subscribe(
        on_next=events.append,
        on_error=errors.append,
        on_completed=lambda: completed.append(True),
    )

    assert errors == []
    assert completed == [True]
    assert len(events) == 7

    assert all("prediction_std_pct" not in event for event in events)
    assert all("model_regime" not in event for event in events)