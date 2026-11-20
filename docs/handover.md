# Handover Notes

## Current state

The repository contains a tested software prototype for moisture-responsive seeding-depth control and seed-release replay.

The dashboard supports dataset replay, configuration, visualisation, and downloadable diagnostics. It uses an internal-format CSV dataset and can use a saved model artefact or train a model in memory.

## What is implemented

- Sample-by-sample moisture filtering and target-depth control.
- Three-observation median filtering.
- Optional model-assisted moisture control.
- Moisture-to-depth mapping.
- Dataset replay with vehicle-speed interpolation.
- Spatial-grid release candidates.
- Release-eligibility checks.
- Sensor-offset and actuator-delay compensation.
- Replay spacing diagnostics.
- Dashboard animation, charts, tables, and CSV exports.
- Automated tests for selected controller, release, validation, and integration behaviour.

## What is NOT implemented

- Client raw spatial-grid CSV importer.
- Live sensor acquisition.
- Live vehicle-position acquisition.
- Hardware actuator communication.
- Pending-command-aware release scheduling.
- Feedback-based row correction integrated with pending commands.
- Physical seed-placement validation.
- Real-time deadline validation.
- Model-only operation during sensor dropout.

## Not yet verified

- Windows launcher execution.
- Physical hardware integration.
- Field-scale performance.
- Model generalisation beyond available data.

## Where to start

1. Read the root `README.md`.
2. Read `docs/controller-contract.md`.
3. Run the test suite.
4. Run the dashboard using the default dataset.
5. Review `prediction_control/control_loop.py` and
   `prediction_control/simulation.py`.
6. Review the remaining work in the README.

## Do NOT connect to machinery

Do not connect this software directly to physical machinery until live acquisition, actuator communication, pending-command scheduling, fault handling, and physical validation are implemented and reviewed.

