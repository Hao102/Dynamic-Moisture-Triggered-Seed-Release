import pytest

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
def test_sensor_only_stream_applies_actuator_delay():
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

    assert [event["position_m"] for event in events] == pytest.approx(
        [index * 0.03 + 0.1 for index in range(11)]
    )
    assert [event["time_s"] for event in events] == pytest.approx(
        [index * 0.03 + 0.1 for index in range(11)]
    )

# test for sensor offset compensation
# current spatial-compensation contract: with a 0.05 m sensor offset and constant 1 m/s speed, each release time is the nominal position time minus 0.05 seconds. 
# It does not yet establish the physical sign convention, live-stream timing, or hardware behaviour.
def test_sensor_only_stream_applies_sensor_offset():
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

    assert [event["position_m"] for event in events] == pytest.approx(
        [index * 0.03 for index in range(11)]
    )
    assert [event["time_s"] for event in events] == pytest.approx(
        [index * 0.03 + 0.05 for index in range(11)]
    )