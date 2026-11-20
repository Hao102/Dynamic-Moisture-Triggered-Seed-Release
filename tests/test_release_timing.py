import pytest

from prediction_control.release_timing import latest_available_index


def test_uses_latest_sample_at_or_before_command_time():
    assert latest_available_index([0.0, 0.1, 0.2], 0.15) == 1


def test_uses_sample_exactly_at_command_time():
    assert latest_available_index([0.0, 0.1, 0.2], 0.1) == 1


def test_returns_none_before_first_sample():
    assert latest_available_index([0.0, 0.1, 0.2], -0.01) is None


@pytest.mark.parametrize(
    "sample_times",
    [
        [],
        [0.0, 0.1, 0.1],
        [0.0, 0.2, 0.1],
        [0.0, float("nan"), 0.2],
    ],
)
def test_rejects_invalid_sample_times(sample_times):
    with pytest.raises(ValueError):
        latest_available_index(sample_times, 0.15)


def test_rejects_non_finite_command_time():
    with pytest.raises(ValueError, match="command_time must be finite"):
        latest_available_index([0.0, 0.1], float("nan"))