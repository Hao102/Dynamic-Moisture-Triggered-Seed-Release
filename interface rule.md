# Prediction / Control Logic Interface Specification — Tony

## 1. Purpose

This module implements the prediction/control logic and provides the interface used to integrate the prediction module with the simulation/dashboard.

The module is implemented using **RxPY (ReactiveX for Python)**. Instead of returning a completed result table in a single function call, the module exposes an **Observable stream** that emits one event for each seed release.

The prediction/control logic may be refined as Hao's mathematical model and available project data develop, but the interface below should remain stable unless changes are agreed with the relevant team members.

---

## 2. Required Interface

```python
import reactivex as rx


def create_release_stream(
    field_positions: list[float],
    field_moisture: list[float],
    speed_time: list[float],
    speed_values: list[float],
    config: dict[str, float],
) -> rx.Observable:
    """
    Create an RxPY Observable that emits seed-release events in chronological order.

    Inputs
    ------
    field_positions:
        Field positions in metres.

    field_moisture:
        Soil moisture values (%) corresponding to field_positions.

    speed_time:
        Time values in seconds for the vehicle speed profile.

    speed_values:
        Vehicle speed values in metres/second corresponding to speed_time.

    config:
        Control/model parameters used by the prediction/control logic.

    Returns
    -------
    rx.Observable
        Emits one dictionary for each seed-release event.

    Each emitted event represents a positive seed-release signal.

    Invalid input data or processing errors should be reported through
    the Observable's on_error() handler.
    """
```

---

## 3. Configuration Format

Control parameters are grouped into a single `config` dictionary to keep the interface concise and easier to extend.

Example:

```python
config = {
    "target_spacing_m": 0.03,
    "min_moisture": 15.0,
    "max_moisture": 25.0,
    "min_depth_mm": 15.0,
    "max_depth_mm": 40.0,
}
```

The values above are initial development/test parameters. They may be adjusted later according to the mathematical model, available data, and agreed system requirements.

Additional model parameters may be added to `config` later without changing the main function signature.

---

## 4. Release Event Format

Each emitted event must be a dictionary with the following keys:

```python
{
    "time_s": float,
    "position_m": float,
    "speed_m_s": float,
    "moisture_pct": float,
    "target_depth_mm": float,
}
```

Meaning:

- `time_s` — simulated release time in seconds
- `position_m` — position along the field in metres
- `speed_m_s` — vehicle speed at the release point in metres/second
- `moisture_pct` — soil moisture at the release point in percent
- `target_depth_mm` — target seed placement depth in millimetres

Events must be emitted in ascending `time_s` order.

Because the Observable emits only release events, a separate `seeding_signal` field is not required. The presence of an emitted event itself represents a positive seed-release signal.

---

## 5. Supporting Function

```python
def moisture_to_depth(
    moisture_pct: float,
    min_moisture: float,
    max_moisture: float,
    min_depth_mm: float,
    max_depth_mm: float,
) -> float:
    """
    Convert a soil moisture reading into a target seed depth.

    The function remains a normal pure function and may be called from
    the RxPY pipeline, for example through ops.map().

    Moisture values outside the configured range should be clipped rather
    than causing an error.
    """
```

This function represents the current moisture-to-depth mapping used by the control logic. Its internal calculation may be refined later if required by the mathematical model.

---

## 6. Reactive Processing Structure

The internal implementation should follow an RxPY event-stream structure.

A typical processing flow is:

1. Generate or receive movement/position events from the speed profile.
2. Associate the current position with the relevant soil moisture value.
3. Apply the prediction/control decision logic.
4. Filter the stream so that only valid release events continue.
5. Transform valid events into the agreed release-event dictionary format.
6. Emit each release event to subscribers.
7. Call `on_completed()` when the simulation/input stream finishes.
8. Send processing or validation errors through `on_error()`.

Typical RxPY operators may include:

```python
ops.map(...)
ops.filter(...)
```

The exact internal pipeline may be adjusted during implementation as long as the agreed external interface is preserved.

---

## 7. Units

The interface uses the following units:

- Distance: **metres**
- Depth: **millimetres**
- Time: **seconds**
- Speed: **metres/second**
- Moisture: **percent (%)**

If different units are used internally, they must be converted before values cross the module interface.

---

## 8. Input Validation and Error Handling

Input validation will be implemented inside the module.

Examples of invalid input include incompatible array lengths, empty required inputs, invalid configuration values, or data that cannot be processed correctly.

The implementation should not silently ignore processing failures. Errors should be propagated through the RxPY Observable using `on_error()` so that the integration/dashboard layer can handle them appropriately.

---

## 9. Example Development Data

The following data can be used as an initial common development dataset:

```python
import numpy as np

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
}
```

These values are intended for development and interface checking rather than as fixed final project parameters.

---

## 10. Dashboard / Simulation Consumption

The simulation/dashboard can consume the Observable using `subscribe()`.

Example:

```python
events = []

create_release_stream(
    field_positions,
    field_moisture,
    speed_time,
    speed_values,
    config,
).subscribe(
    on_next=lambda event: events.append(event),
    on_error=lambda err: print(f"Error: {err}"),
    on_completed=lambda: print(f"Done: {len(events)} events"),
)
```

The prediction/control module is responsible for producing events according to the agreed interface. The simulation/dashboard is responsible for subscribing to the Observable and using the emitted events for visualisation or further system behaviour.

---

## 11. Interface Stability

The following elements should not be changed without discussion with the relevant integration team members:

- `create_release_stream()` name
- required input data
- `config` structure where changes affect other modules
- Observable return type
- emitted event field names
- interface units

Internal implementation details may be changed independently as long as the external interface remains compatible.

---

## 12. Definition of Done for the Interface

The interface is considered ready for implementation when:

1. `create_release_stream()` uses the agreed RxPY Observable interface.
2. Control/model parameters are passed through the `config` dictionary.
3. Release events use the agreed five-field dictionary format.
4. Each emitted event clearly represents a seed-release signal.
5. Units are consistent across the interface.
6. Invalid inputs and processing errors are surfaced through `on_error()`.
7. The simulation/dashboard can subscribe to and consume the emitted events using the agreed format.
