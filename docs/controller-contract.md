# Controller Contract

Status: implementation-aligned architectural contract for the current software prototype. It is not a claim that hardware integration, real-time deadline compliance, physical seed-placement accuracy, or complete operational robustness has been verified.

## Primary deliverable

The primary deliverable is a moisture-responsive seeding-control prototype that:
1. Processes soil-moisture observations sequentially.
2. Produces a target planting depth from filtered sensor moisture and, where available, model-assisted moisture prediction.
3. Generates seed-release events at configured target spacings.
4. Applies sensor-offset and actuator-delay compensation to release timing.
5. Provides dataset replay, visualisation, and diagnostic outputs through the Streamlit dashboard.

The current implementation separates moisture/depth control from seed-release scheduling. This separation is intentional: the dashboard, batch workflow, and future hardware integration should not maintain competing implementations of controller decisions.

## Operating modes

### Sensor-only mode

The moisture/depth controller can operate using valid sensor readings and control configuration without requiring a prediction model, saved model artefact, dashboard, uploaded dataset, or simulation engine.

In sensor-only mode, the controller uses filtered sensor moisture to calculate the target planting depth.

### Prediction-assisted mode

When a trained prediction model is supplied, the controller may use a model prediction alongside filtered sensor moisture to calculate the target planting depth.

The current implementation combines the two values using a fixed model weight:

```text
control moisture =
    (1 - model weight) × filtered sensor moisture
  + model weight × predicted moisture
```

The current default is:

```text
model weight = 0.2
```

Therefore, the default combination is:

```text
control moisture =
    0.8 × filtered sensor moisture
  + 0.2 × predicted moisture
```

These are implementation defaults, not calibrated optimal values.

Prediction generation remains separate from release scheduling. The release-generation component remains responsible for release eligibility, spacing, timing compensation, and release-event generation.

## Component responsibilities

### Moisture and depth controller

`RealtimeController` is the sample-by-sample moisture and depth controller.

It is responsible for:
- Validating individual moisture observations.
- Maintaining a bounded history of valid observations.
- Calculating a rolling median once the filter is ready.
- Producing a target planting depth from control moisture.
- Using an already-trained prediction model when one is supplied.
- Falling back to valid filtered sensor moisture when model prediction is unavailable or invalid.

It is not responsible for:
- Seed-spacing generation.
- Release eligibility.
- Release-command timing.
- Actuator communication.
- Dataset loading.
- Model training.
- Dashboard rendering.
- File access.

One controller instance should be used per seeder row.

### Release-generation component

The release-generation component is responsible for:
- Generating candidate seed positions from configured target spacing.
- Determining release eligibility from control moisture.
- Selecting a controller observation available at or before the command time.
- Applying sensor-offset and actuator-delay compensation.
- Producing a release-event schedule.

It must not maintain a separate moisture-filtering or depth-mapping
implementation.

### Prediction component

The prediction component is responsible for model inference and prediction
metadata.

Model fitting and model loading belong outside the operational controller
update. The controller receives an already-trained model.

### Preprocessing component

The preprocessing component is responsible for validating and preparing
uploaded datasets.

Dataset acceptance does not establish sensor calibration, measurement quality,
or model generalisation.

### Simulation engine

The simulation engine is responsible for:
- Simulated sensor inputs.
- Vehicle movement.
- Actuator behaviour.
- Observation of controller outputs.
- Replay diagnostics.

### Dashboard

The dashboard is responsible for:
- Configuration controls.
- Dataset replay.
- Visualisation.
- Downloadable diagnostics.

The dashboard must not maintain a separate implementation of controller
release decisions.

## Moisture and depth controller

### Controller input

`RealtimeController.update()` processes one new moisture observation at a
time.

```python
position_m: float
raw_moisture_pct: float
```

- `position_m`: current position of the moisture sensor.
- `raw_moisture_pct`: raw moisture measurement at that sensor position.

The caller must call the controller once per new sensor observation. Do not
repeatedly add the same measurement merely because the actuator-control clock
runs faster.

### Controller output

```python
{
    "sensor_position_m": float,
    "measured_moisture_pct": float,
    "filtered_moisture_pct": float,
    "predicted_moisture_pct": float | None,
    "dominant_expert": int,
    "expert0_weight": float,
    "expert1_weight": float,
    "control_moisture_pct": float | None,
    "target_depth_mm": float | None,
    "command_valid": bool,
    "sensor_status": str,
    "control_source": str,
}
```

### Output field meanings

- `sensor_position_m`: position supplied for the current observation.
- `measured_moisture_pct`: raw moisture value supplied to the controller.
- `filtered_moisture_pct`: median-filtered moisture value.
- `predicted_moisture_pct`: model prediction, when a valid model prediction is available.
- `dominant_expert`: index of the dominant mixture-model expert, 
                or `-1` when no valid prediction is available.
- `expert0_weight`: weight assigned to expert 0.
- `expert1_weight`: weight assigned to expert 1.
- `control_moisture_pct`: moisture value used for the depth calculation.
- `target_depth_mm`: target planting depth in millimetres.
- `command_valid`: whether a new valid depth command was produced.
- `sensor_status`: status of the current sensor observation.
- `control_source`: whether the command used sensor-only or model-assisted control.

### Processing sequence

For each new moisture observation, the controller:

1. Validates the raw observation.
2. Updates a bounded history of valid readings.
3. Calculates the rolling median once the filter is ready.
4. Obtains a model prediction using the filtered moisture and configured spatial context, when a model is supplied.
5. Combines filtered moisture with the model prediction.
6. Maps the resulting control moisture to a target planting depth.

### Filtering and warm-up

The current implementation uses a three-observation median window by default.

The first two valid observations are filter warm-up. During warm-up, no new valid depth command is returned.
Invalid observations do not produce a valid new depth command. Replay retains the previous target depth when no new command is available.

The median filter suppresses isolated spikes but introduces response delay.
Sustained moisture changes pass through the filter.

### Depth mapping

Control moisture is mapped inversely to the configured depth range:

```text
lower moisture → larger depth value
higher moisture → smaller depth value
```

Values beyond the configured moisture-mapping range are clipped for depth calculation.

The configured moisture range also determines release eligibility in the current replay. A physically valid moisture measurement can therefore be outside the planting eligibility range.

### Prediction fallback

If no model is supplied, the controller operates in sensor-only mode.

If model prediction is missing or invalid, the controller uses valid filtered sensor moisture as the fallback. Missing or invalid prediction data does not automatically prevent a valid depth command.

Prediction uncertainty is not currently accepted by `RealtimeController` and does not currently affect the control weight.

## Release generation

### Release eligibility

A release candidate is eligible when its control moisture lies within the configured minimum and maximum moisture range.

The current replay generates candidates on an evenly spaced spatial grid using the configured seed spacing.

### Causal observation selection

For release eligibility, the replay selects a controller observation available at or before the calculated command time:

```text
command time = planned release time - configured release delay
```

Candidates without a valid available controller observation are skipped.

### Timing and compensation

For an eligible release candidate:

```text
release time = command time + actuator delay
```

The controller uses the sensor offset, vehicle speed, and actuator delay to determine when to send the release signal.

When available sensor lead time is sufficient, the command is scheduled so that the expected physical release occurs at the target position.

When lead time is insufficient, the command is issued immediately and `compensation_error_m` reports the unavoidable late-release distance:

```text
compensation_error_m = actual release position - target position
```

A positive value indicates a release later than the intended target position.

### Spacing metrics

Target seed spacing is configurable between 0.015 m and 0.060 m.

The individual-gap tolerance target is ±0.001 m.

Diagnostics calculate:

```text
gap = current release position - previous release position

gap error = gap - configured target spacing
```

Reported results include:
- Gap count.
- Mean gap.
- Mean absolute gap error.
- Maximum absolute gap error.
- Percentage within tolerance.

These metrics use replay release positions, not measured planted positions.
Near-zero errors can result from the ideal target grid itself.

`spacing.py` separately provides bounded next-target correction and row-error tracking. It is not yet integrated with a scheduler that handles commands already issued before placement feedback arrives.

## Position reference

`sensor_position_m` is the current position of the moisture sensor.

The moisture sensor is ahead of the seed-release point in the direction of travel. The controller calculates the current release-point position using the configured `sensor_offset_m` and current vehicle speed.

The release-generation component outputs a target release position, which is the position where it intends the next seed to be released.

## Reverse operation

The team has agreed that seeding must not occur while the tractor is reversing.

The current release-generation implementation conservatively rejects non-positive vehicle speed before generating release events. Therefore, no seed is released while reversing.

A more sophisticated reverse-mode behaviour, such as tracking the last released seed and resuming after a defined reverse distance, is not part of the current contract.

## Prediction metadata

`prediction_std_pct` is accepted by the legacy `evaluate_prediction()` function for result metadata but is not used in the control decision.

`model_regime` remains an optional legacy metadata field in `evaluate_prediction()`. It must not influence the control decision. It may be used only for logging and evaluation until the team defines a stable meaning for it.

## Hardware boundary

The controller produces a target-depth command and a release-event schedule.
The hardware actuator receives that schedule and performs the physical release.

The controller does not directly operate the actuator. A future hardware signal interface may translate the controller schedule into an electrical or communication command, but that interface is separate from controller decision logic.

Physical sensors and simulated sensors should feed the same controller through an agreed input interface.

Hardware input/output interfaces are separate from controller logic.

## Current limitations

- `RealtimeController` implements sample-by-sample moisture and depth control, but not a combined release-scheduling interface.
- `release_stream.py` accepts complete input arrays and constructs events before emitting them. Incremental processing of live sensor readings has not yet been established.
- The dashboard replay path and standalone release-stream path use separate release-generation implementations.
- Pending-command-aware scheduling is not implemented.
- Feedback-based row correction is not integrated with pending release commands.
- Live hardware acquisition and actuator communication are not implemented.
- Physical seed-placement validation has not been performed.
- End-to-end runtime deadline validation has not been performed.

A passing replay spacing result does not establish physical seed-placement accuracy.

## Verified Test baseline

Run the selected test suite from the repository root:

```bash
python -m pytest tests/test_validation.py tests/test_integration.py tests/test_release_stream.py -v
```

Environment:
- Python 3.11.x
- pytest 9.2.0
- Project virtual environment: `ICT/.venv`

The suite covers validation, selected component and integration behaviour,
and documented release-stream behaviour.

Passing tests do not establish real-time performance, hardware readiness,
physical accuracy, robustness to every noise distribution, or complete
controller independence.

## Deployment boundary

The present replay should not be connected directly to physical machinery without completing the following integration and safety work:

1. Import and validate the client’s raw spatial-grid CSV (live sensor data).
2. Integrate timestamped live moisture and vehicle-position data from hardware sensors.
3. Calibrate filtering and model assistance against representative noise.
4. Benchmark inference and complete control-cycle latency.
5. Implement pending-command-aware release scheduling.
6. Integrate row correction using measured or explicitly simulated feedback.
7. Validate sensor offset, latency, and actuator behaviour.
8. Measure physical individual seed gaps against the tolerancerequirement.
9. Define hardware startup, stale-data, stopping, recovery, and fault policies.
