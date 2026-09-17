import numpy as np

from prediction_control.release_stream import create_release_stream


def main() -> None:
    # Initial development data.
    # Replace this later with the cleaned/project dataset.
    field_positions = list(np.linspace(0, 100, 200))
    field_moisture = list(
        20 + 5 * np.sin(np.array(field_positions) / 10)
    )

    speed_time = list(np.linspace(0, 60, 100))
    speed_values = [1.5] * 100

    config = {
        "target_spacing_m": 0.03,
        "min_moisture": 15.0,
        "max_moisture": 25.0,
        "min_depth_mm": 15.0,
        "max_depth_mm": 40.0,

        # Add these when the compensation module is implemented:
        # "sensor_offset_m": 0.5,
        # "actuator_delay_s": 0.1,
    }

    release_events = []

    stream = create_release_stream(
        field_positions=field_positions,
        field_moisture=field_moisture,
        speed_time=speed_time,
        speed_values=speed_values,
        config=config,
    )

    stream.subscribe(
        on_next=lambda event: release_events.append(event),
        on_error=lambda error: print(f"Control pipeline error: {error}"),
        on_completed=lambda: print(
            f"Control pipeline completed: {len(release_events)} release events"
        ),
    )

    # Temporary development output only.
    # Manan's dashboard can later subscribe directly to the Observable.
    for event in release_events[:10]:
        print(event)


if __name__ == "__main__":
    main()
