# Controller Contract

Status: agreed architectural intent and controller interface; not a claim
that all capabilities are implemented or verified.

## Primary deliverable

The primary deliverable is an independent controller that processes sensor
inputs and generates seed-release signals.

## Operating modes

### Sensor-only mode

The controller must operate using valid sensor readings and control
configuration without requiring a prediction model, saved model artefact,
dashboard, uploaded dataset, or simulation engine.

### Prediction-assisted mode

The controller may use a valid moisture prediction alongside the measured
moisture reading to determine the release decision and target depth.

The controller remains responsible for the final release decision.
Prediction generation must remain separate from release scheduling.

## Controller interface

The controller processes one sensor reading at a time in real time.

### Controller input

```python
{
    "timestamp_s": float,
    "sensor_position_m": float,
    "speed_m_s": float,
    "measured_moisture_pct": float,
    "predicted_moisture_pct": float | None,
    "prediction_std_pct": float | None,
}
```

### Controller output

```python
{
    "should_release": bool,
    "target_depth_mm": float,
    "target_position_m": float,
    "command_time_s": float,
    "release_time_s": float,
    "compensation_error_m": float,
    "used_prediction": bool,
    "prediction_valid": bool,
}
```

## Field meanings

### Input fields

- `timestamp_s`: time of the sensor reading.
- `sensor_position_m`: current position of the moisture sensor.
- `speed_m_s`: current vehicle speed.
- `measured_moisture_pct`: moisture measured by the sensor.
- `predicted_moisture_pct`: optional moisture prediction supplied by the
  prediction component.
- `prediction_std_pct`: optional uncertainty associated with the moisture
  prediction.

### Output fields

- `should_release`: whether the controller instructs a seed release.
- `target_depth_mm`: intended seed depth.
- `target_position_m`: position where the controller intends the next seed
  to be released.
- `command_time_s`: time at which the seed-release signal should be sent.
- `release_time_s`: expected time at which the seed physically releases.
- `compensation_error_m`: unavoidable release-position error when the
  available sensor lead time is insufficient to absorb the actuator delay.
- `used_prediction`: whether prediction data was used for the control
  decision.
- `prediction_valid`: whether the supplied prediction data was valid.

## Position reference

`sensor_position_m` is the current position of the moisture sensor.

The moisture sensor is ahead of the seed-release point in the direction of
travel. The controller calculates the current release-point position using
the configured `sensor_offset_m` and current vehicle speed.

The controller outputs `target_position_m`, which is the position where it
intends the next seed to be released.

## Timing and compensation

The controller must distinguish:

- `command_time_s`: when to send the seed-release signal.
- `release_time_s`: when the seed is expected to physically release.

The relationship is:

```text
release_time_s = command_time_s + actuator_delay_s
```

The actuator response delay is represented by `actuator_delay_s`. The
controller uses the sensor offset, vehicle speed, and actuator delay to
determine when to send the release signal.

If the available sensor lead time is sufficient, the controller schedules
the command so that the expected physical release occurs at
`target_position_m`.

If the available lead time is insufficient, the controller commands
immediately and reports the unavoidable late-release distance through
`compensation_error_m`.

## Prediction fallback

If prediction data is missing or invalid, the controller logs the condition
for metrics and evaluation, then uses measured moisture as the fallback.

The controller remains responsible for deciding whether the fallback
moisture is within the configured release range.

Missing or invalid prediction data must not automatically prevent seeding.

## Prediction metadata

`model_regime` is removed from the controller interface until the prediction
team defines its meaning.

If it is reintroduced later, it must be optional prediction metadata used for
logging and evaluation only. It must not be treated as a controller input or
a control decision input.

## Hardware boundary

The controller produces a seed-release signal schedule. The hardware
actuator receives that signal and performs the physical release.

The controller does not directly operate the actuator. A future hardware
signal interface may translate the controller schedule into an electrical
or communication command, but that interface is separate from controller
decision logic.

## Component responsibilities

- Controller: release decisions, spacing, timing compensation, and
  release-signal scheduling.
- Prediction component: model inference and prediction metadata.
- Preprocessing: validation and preparation of uploaded datasets.
- Simulation engine: simulated sensor inputs, movement, actuator behaviour,
  and observation of controller outputs.
- Dashboard: input/configuration controls and visualisation of results.

The simulation and dashboard must not maintain competing implementations
of controller release decisions.

## Reverse operation

The team has agreed that seeding must not occur while the tractor is
reversing.

The current implementation conservatively rejects negative speed before
generating release events. Therefore, no seed is released while reversing.

A more sophisticated reverse-mode behaviour, such as tracking the last
released seed and resuming after a defined reverse distance, is not part of
the current contract.

## Deployment boundary

Physical sensors and simulated sensors should feed the same controller
through an agreed input interface.

Hardware input/output interfaces are separate from the controller logic.

## Current limitations

The existing release-stream implementation accepts complete input arrays
and constructs events before emitting them. Incremental processing of live
sensor readings has not yet been established.

The dashboard bridge and dataset pipeline currently generate release events
through separate execution paths.

Passing existing tests does not establish real-time performance, hardware
readiness, or complete controller independence.

## Verified test baseline

Command, run from the repository root:

```bash
python -m pytest tests/test_validation.py tests/test_integration.py tests/test_release_stream.py -v
```

Environment:
- Python 3.11.5
- pytest 9.2.0
- Project virtual environment: `ICT/.venv`

The suite covers validation, selected component/integration behaviour, and
the documented release-stream controller contracts. It does not establish
real-time performance, hardware readiness, or complete controller
independence.