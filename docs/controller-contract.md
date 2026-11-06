# Controller Contract

Status: agreed architectural intent; not a claim that all capabilities
are implemented or verified.

## Primary deliverable

The primary deliverable is an independent controller that processes
sensor inputs and generates seed-release signals.

## Operating modes

### Sensor-only mode

The controller must operate using valid sensor readings and control
configuration without requiring a prediction model, saved model
artefact, dashboard, uploaded dataset, or simulation engine.

### Prediction-assisted mode

The controller may use relevant prediction outputs alongside sensor
readings to improve release and depth decisions.

The controller remains responsible for the final decision. Prediction
generation must remain separate from release scheduling.

The rules for prediction freshness, spatial/depth matching, quality,
and fallback remain to be specified.

## Component responsibilities

- Controller: release decisions, spacing, timing compensation, and
  release-signal generation.
- Prediction component: model inference and prediction metadata.
- Preprocessing: validation and preparation of uploaded datasets.
- Simulation engine: simulated sensor inputs, movement, actuator
  behaviour, and observation of controller outputs.
- Dashboard: input/configuration controls and visualisation of results.

The simulation and dashboard must not maintain competing implementations
of controller release decisions.

## Deployment boundary

Physical sensors and simulated sensors should feed the same controller
through an agreed input interface.

Hardware input/output adapters are separate from the controller logic.

## Current limitations

The existing release-stream implementation accepts complete input arrays
and constructs events before emitting them. Incremental processing of
live sensor readings has not yet been established.

The dashboard bridge and dataset pipeline currently generate release
events through separate execution paths.

Passing existing tests does not establish real-time performance,
hardware readiness, or complete controller independence.

## Verified test baseline

Command, run from the repository root:

    python -m pytest tests/test_validation.py tests/test_integration.py -v

Environment:
- Python 3.11.5
- pytest 9.2.0
- Project virtual environment: ICT/.venv

Result:
- 98 passed in 1.91 seconds

This baseline covers validation and selected component/integration
behaviour, not the complete controller contract.