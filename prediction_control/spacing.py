# Individual seed-gap tracking and bounded row-position correction.

from math import isfinite


class SpacingController:
    """Track one row using actual or explicitly simulated seed positions.

    The ideal grid stays anchored to row_start_m. After each placement,
    choose the next position as close as possible to that grid while
    respecting the allowed gap relative to the last planted seed.

    This plans a target; it cannot guarantee physical placement accuracy.
    """

    def __init__(
        self,
        target_spacing_m=0.03,
        tolerance_m=0.001,
        row_start_m=0.0,
    ):
        if (
            not isfinite(target_spacing_m)
            or not 0.015 <= target_spacing_m <= 0.030
        ):
            raise ValueError("target_spacing_m must be between 0.015 and 0.030")

        if (
            not isfinite(tolerance_m)
            or not 0.0 < tolerance_m < target_spacing_m
        ):
            raise ValueError("tolerance_m must be positive and less than spacing")

        if not isfinite(row_start_m) or row_start_m < 0.0:
            raise ValueError("row_start_m must be finite and non-negative")

        self.spacing = float(target_spacing_m)
        self.tolerance = float(tolerance_m)
        self.reset(row_start_m)

    def reset(self, row_start_m=0.0):
        # Start another row without changing spacing or tolerance.
        if not isfinite(row_start_m) or row_start_m < 0.0:
            raise ValueError("row_start_m must be finite and non-negative")

        self.row_start = float(row_start_m)
        self.seed_count = 0
        self.last_position = None
        self.first_position = None
        self.gap_count = 0
        self.within_tolerance_count = 0
        self.sum_absolute_gap_error = 0.0
        self.max_absolute_gap_error = 0.0

    def next_target(self):
        # Return ideal-grid and corrected targets for the next seed.
        ideal = self.row_start + self.seed_count * self.spacing

        if self.last_position is None:
            corrected = ideal
        else:
            minimum = self.last_position + self.spacing - self.tolerance
            maximum = self.last_position + self.spacing + self.tolerance
            corrected = max(minimum, min(ideal, maximum))

        return {
            "seed_index": self.seed_count,
            "ideal_position_m": ideal,
            "planned_position_m": corrected,
            "planned_grid_offset_m": corrected - ideal,
        }

    def record_placement(self, position_m):
        """Record feedback for one seed, in planting order.

        Call only after obtaining actual or simulated placement feedback,
        not merely after issuing a release command.
        """
        position = float(position_m)
        if not isfinite(position) or position < 0.0:
            raise ValueError("position_m must be finite and non-negative")

        if self.last_position is not None and position <= self.last_position:
            raise ValueError("placement positions must be strictly increasing")

        plan = self.next_target()
        gap = None
        gap_error = None
        within = None

        if self.last_position is None:
            self.first_position = position
        else:
            gap = position - self.last_position
            gap_error = gap - self.spacing
            within = abs(gap_error) <= self.tolerance + 1e-12

            self.gap_count += 1
            self.within_tolerance_count += int(within)
            self.sum_absolute_gap_error += abs(gap_error)
            self.max_absolute_gap_error = max(
                self.max_absolute_gap_error, abs(gap_error)
            )

        grid_error = position - plan["ideal_position_m"]
        cumulative_gap_error = (
            position - self.first_position - self.seed_count * self.spacing
        )

        self.last_position = position
        self.seed_count += 1

        return {
            **plan,
            "planted_position_m": position,
            "placement_error_m": position - plan["planned_position_m"],
            "grid_position_error_m": grid_error,
            "planted_gap_m": gap,
            "spacing_error_m": gap_error,
            "within_tolerance": within,
            "cumulative_gap_error_m": cumulative_gap_error,
        }

    def summary(self):
        # Return row metrics without storing an unbounded event history.
        return {
            "target_spacing_m": self.spacing,
            "spacing_tolerance_m": self.tolerance,
            "seed_count": self.seed_count,
            "gap_count": self.gap_count,
            "within_tolerance_count": self.within_tolerance_count,
            "within_tolerance_rate_pct": (
                100.0 * self.within_tolerance_count / self.gap_count
                if self.gap_count else None
            ),
            "mean_absolute_spacing_error_m": (
                self.sum_absolute_gap_error / self.gap_count
                if self.gap_count else None
            ),
            "max_absolute_spacing_error_m": (
                self.max_absolute_gap_error if self.gap_count else None
            ),
        }