import pytest

from prediction_control.sensor import MoistureFilter


def test_filter_reports_startup():
    sensor = MoistureFilter()

    reading = sensor.update(4.0)

    assert reading.valid is True
    assert reading.ready is False
    assert reading.status == "warming_up"
    assert reading.filtered_moisture_pct == pytest.approx(4.0)


def test_filter_rejects_isolated_high_spike():
    sensor = MoistureFilter()

    sensor.update(4.0)
    sensor.update(4.1)
    reading = sensor.update(20.0)

    assert reading.ready is True
    assert reading.raw_moisture_pct == pytest.approx(20.0)
    assert reading.filtered_moisture_pct == pytest.approx(4.1)


def test_filter_rejects_isolated_low_spike():
    sensor = MoistureFilter()

    sensor.update(4.0)
    sensor.update(4.1)
    reading = sensor.update(0.0)

    assert reading.filtered_moisture_pct == pytest.approx(4.0)


def test_filter_accepts_sustained_change():
    sensor = MoistureFilter()

    for value in [4.0, 4.0, 4.0]:
        sensor.update(value)

    first = sensor.update(8.0)
    second = sensor.update(8.0)

    assert first.filtered_moisture_pct == pytest.approx(4.0)
    assert second.filtered_moisture_pct == pytest.approx(8.0)


@pytest.mark.parametrize(
    "value",
    [None, float("nan"), float("inf"), -1.0, 101.0, True, "bad"],
)
def test_invalid_reading_is_not_used(value):
    sensor = MoistureFilter()

    for moisture in [4.0, 4.1, 4.2]:
        sensor.update(moisture)

    invalid = sensor.update(value)

    assert invalid.valid is False
    assert invalid.ready is False
    assert invalid.filtered_moisture_pct is None

    recovered = sensor.update(4.3)
    assert recovered.filtered_moisture_pct == pytest.approx(4.2)


def test_reset_clears_previous_row_history():
    sensor = MoistureFilter()

    for value in [4.0, 4.0, 4.0]:
        sensor.update(value)

    sensor.reset()
    reading = sensor.update(8.0)

    assert reading.ready is False
    assert reading.filtered_moisture_pct == pytest.approx(8.0)


@pytest.mark.parametrize("window_size", [0, 1, 2, 4, -3, True, 3.5])
def test_invalid_window_size_is_rejected(window_size):
    with pytest.raises(ValueError, match="odd integer"):
        MoistureFilter(window_size=window_size)