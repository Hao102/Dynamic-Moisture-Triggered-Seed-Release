import pytest

from prediction_control.spacing import SpacingController


def test_initial_target_is_row_start():
    controller = SpacingController(row_start_m=2.0)

    assert controller.next_target()["planned_position_m"] == pytest.approx(2.0)


def test_small_position_error_is_corrected_next_gap():
    controller = SpacingController(target_spacing_m=0.020)

    controller.record_placement(0.0008)
    plan = controller.next_target()

    assert plan["ideal_position_m"] == pytest.approx(0.020)
    assert plan["planned_position_m"] == pytest.approx(0.020)
    assert plan["planned_position_m"] - 0.0008 == pytest.approx(0.0192)


def test_large_error_is_corrected_gradually():
    controller = SpacingController(target_spacing_m=0.020)

    controller.record_placement(0.003)

    for expected in [0.022, 0.041, 0.060]:
        plan = controller.next_target()
        assert plan["planned_position_m"] == pytest.approx(expected)

        event = controller.record_placement(plan["planned_position_m"])
        assert event["within_tolerance"] is True

    assert event["grid_position_error_m"] == pytest.approx(0.0)


def test_gap_outside_tolerance_is_reported_not_hidden():
    controller = SpacingController(target_spacing_m=0.020)

    controller.record_placement(0.0)
    event = controller.record_placement(0.022)

    assert event["spacing_error_m"] == pytest.approx(0.002)
    assert event["within_tolerance"] is False
    assert controller.summary()["within_tolerance_rate_pct"] == 0.0


def test_first_seed_has_no_gap_metric():
    controller = SpacingController()

    event = controller.record_placement(0.0)

    assert event["planted_gap_m"] is None
    assert event["within_tolerance"] is None
    assert controller.summary()["gap_count"] == 0


def test_cumulative_gap_error_excludes_initial_offset():
    controller = SpacingController(target_spacing_m=0.020)

    controller.record_placement(0.002)
    event = controller.record_placement(0.022)

    assert event["grid_position_error_m"] == pytest.approx(0.002)
    assert event["cumulative_gap_error_m"] == pytest.approx(0.0)


def test_reset_starts_independent_row():
    controller = SpacingController(target_spacing_m=0.020)
    controller.record_placement(0.0)
    controller.record_placement(0.020)

    controller.reset(row_start_m=1.0)

    assert controller.summary()["seed_count"] == 0
    assert controller.next_target()["planned_position_m"] == pytest.approx(1.0)


@pytest.mark.parametrize("spacing", [0.014, 0.031])
def test_spacing_outside_operating_range_is_rejected(spacing):
    with pytest.raises(ValueError, match="between"):
        SpacingController(target_spacing_m=spacing)


def test_duplicate_placement_is_rejected():
    controller = SpacingController()
    controller.record_placement(0.0)

    with pytest.raises(ValueError, match="strictly increasing"):
        controller.record_placement(0.0)