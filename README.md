# Dynamic Moisture-Triggered Seed Release System

A moisture-responsive seeding prototype developed to demonstrate noise-handled soil-moisture processing, model-assisted planting-depth control, and seed-release simulation under changing vehicle speed.

The controller follows two rules:
- Drier soil requests deeper planting.
- Wetter soil requests shallower planting.

The repository separates the sample-by-sample controller from the Streamlit dashboard. The dashboard provides configuration, dataset replay, visualisation, and downloadable diagnostics.

## 1. Handover Status

The current version is a tested software prototype with dataset-replay visualisation. It is not a validated hardware deployment or a hard real-time system.

| Capability | Current status |
|---|---|
| Sequential moisture processing | Implemented in the independent controller |
| Bounded-history median filtering | Implemented and unit-tested |
| Sensor-led model assistance | Implemented |
| Moisture-to-depth mapping | Implemented and tested |
| Simulated actuator depth response | Implemented |
| Release eligibility based on observations available before command time | Implemented in replay |
| Configurable seed spacing | Dashboard range: 15–60 mm |
| Individual gap tolerance reporting | ±1 mm target, evaluated on replay release positions |
| Bounded row-correction component | Unit-tested separately; not integrated with pending release commands |
| Client raw spatial-grid CSV importer | Not implemented |
| Live hardware acquisition and actuator communication | Not implemented |
| Physical seed-placement validation | Not performed |
| End-to-end runtime deadline validation | Not performed |

A passing replay spacing result does not establish physical seed-placement accuracy.

## 2. Quick Start

Run the launcher appropriate to your operating system from a terminal in the repository directory.

Both launchers:
1. Run from the repository root.
2. Create the local environment at `ICT/.venv` if needed.
3. Install or check dependencies from `requirements.txt`.
4. Start the Streamlit dashboard.

#### Pre-requisites:
- Python must already be installed. 
- Internet access may be required for dependency installation.

Virtual environments are platform-specific. Do not copy `ICT/.venv` between operating systems; create it locally using the appropriate launcher.
Keep the terminal open while using the dashboard. Press `Ctrl+C` to stop it.

On first run, the dashboard may take a minute to load and display. After a minute, kindly attempt to reload the webpage. 
Else, manual setup may be required.

### macOS and Linux

```bash
bash run_unix.sh
```

### Windows

Double-click `run_windows.bat`, or run:

```bat
.\run_windows.bat
```

### Launcher verification

- macOS: launcher and default dashboard simulation verified.
- Linux: launcher and default dashboard simulation verified.
- Windows: not yet verified.

Manual setup instructions are provided below.

### Manual setup — Windows, macOS, and Linux

Use the following instructions if you prefer manual setup or the launchers did not work.

Run all commands from the repository root - the directory containing
`final_dashboard.py`, `requirements.txt`, and the launchers.


#### Create or activate the virtual environment

The project’s virtual environment is located at:

```text
ICT/.venv/
```

If it already exists, skip creation and activate it.

For a fresh checkout, create it with:

```bash
python -m venv ICT/.venv
```

Depending on your installation, you may need to use `python3` above instead.

Activate it on macOS/Linux:

```bash
source ICT/.venv/bin/activate
```

Activate it on Windows PowerShell:

```powershell
.\ICT\.venv\Scripts\Activate.ps1
```

Activate it on Windows Command Prompt:

```bat
ICT\.venv\Scripts\activate.bat
```

Remain at the repository root after activation. Do not change into `ICT/` to run the application.

#### Install dependencies

With the virtual environment activated, run:

```bash
python -m pip install -r requirements.txt
```

For development and testing:

```bash
python -m pip install -r requirements-dev.txt
```

#### Run the dashboard

From the repository root:

```bash
python -m streamlit run final_dashboard.py
```

Open the URL displayed in the terminal.

For the default demonstration:

1. Leave the optional dataset upload empty.
2. Configure the seeder line, seed spacing, depth range, and actuator settings.
3. Click `Run Simulation`.
4. Review the animation and result tabs.

The default dashboard dataset is:

```text
data/integration/final_semi_synthetic_winter_wheat_v2.csv
```

The saved default model is:

```text
models/hao_mixture_gpr_runtime.joblib
```

The dashboard attempts to load the default model for the default dataset. If no usable model is loaded, it trains one in memory. A compatible uploaded dataset also follows the dashboard training workflow.

Do not assume that a model trained in a dashboard session is automatically saved to disk.

## 3. System Architecture

### Dashboard replay path

```text
final_dashboard.py
    |
    v
prediction_control/dashboard_bridge.py
    |
    v
prediction_control/simulation.py
    |
    +--> control_loop.py
    |       |
    |       +--> sensor.py
    |       +--> hao_model_runtime.py
    |       +--> prediction_logic.py
```

`dashboard_bridge.py` preserves the dashboard-facing `run_simulation()` API. It delegates implementation to `simulation.py`.

`RealtimeController()` in `control_loop.py` is independent of Streamlit, dataset loading, model training, and file access. It receives an already-trained model and processes individual moisture observations.

### Other execution paths

The repository also retains:

- `dataset_pipeline.py`: the existing batch dataset/prediction/control workflow.
- `release_stream.py`: the standalone sensor-only RxPY release API.
- `main.py`: the existing command-line batch entry point.

These paths are not interchangeable with the dashboard replay path. In particular, the batch pipeline can use model predictions directly, while the updated dashboard controller uses filtered sensor moisture with model assistance.

## 4. Moisture and Depth Control

### Processing sequence

For each new moisture observation:
1. Validate the observation.
2. Update a bounded history of valid readings.
3. Calculate the rolling median once the filter is ready.
4. Obtain a model prediction using the filtered moisture and spatial context.
5. Combine filtered moisture with the model prediction.
6. Map the resulting control moisture to target planting depth.

The current replay configuration uses a three-observation median window and a model weight of 0.2:

```text
control moisture =
    0.8 × filtered sensor moisture
  + 0.2 × predicted moisture
```

These are implementation defaults, not calibrated optimal values.
The median filter suppresses isolated spikes but introduces response delay. Sustained moisture changes pass through the filter.

### Startup and invalid observations
- The first two valid observations are filter warm-up.
- During warm-up, no new valid depth command is returned.
- Invalid observations do not produce a valid new depth command.
- Replay holds the previous target depth when no new command is available.
- The simulated initial depth is the configured minimum depth.
- An invalid model prediction falls back to valid filtered sensor moisture.
- Model-only operation during sensor dropout is not implemented.

For live integration, call the controller once per new sensor observation. Do not repeatedly add the same measurement merely because the actuator-control clock runs faster.

### Depth mapping

Control moisture is mapped inversely to the configured depth range:

```text
lower moisture → larger depth value
higher moisture → smaller depth value
```

Values beyond the configured mapping range are clipped for depth calculation.
The configured moisture range also determines release eligibility in the current replay. 
A physically valid moisture measurement can therefore be outside the planting eligibility range.

## 5. Motion, Release Timing, and Spacing

The replay interpolates the supplied vehicle-speed profile, derives seeder position, and samples moisture at the configured sensor offset ahead of the seeder.

Release candidates are generated on a spatial grid using the configured seed spacing.

For release eligibility, the replay selects a controller observation available at or before the calculated command time:

```text
command time = planned release time − configured release delay
```

Candidates without a valid available controller observation are skipped.

### Important timing limitation

The replay uses the recorded motion profile. It does not demonstrate a live scheduler that predicts unknown future vehicle motion, manages all pending actuator commands, and corrects future releases from measured seed-placement feedback.

The depth actuator time constant and seed-release delay are separate parameters:

- `actuator_tau_s`: simulated depth-response time constant.
- `actuator_delay_s`: configured seed-release latency.

### Spacing metrics

Target seed spacing is configurable between 0.015 and 0.060 m. The individual-gap tolerance target is ±0.001 m.

Diagnostics calculate:

```text
gap = current release position − previous release position

gap error = gap − configured target spacing
```

Reported results include gap count, mean gap, mean absolute gap error, maximum absolute gap error, and percentage within tolerance.

These use replay release positions, not measured planted positions. Near-zero errors can result from the ideal target grid itself.

`spacing.py` separately provides bounded next-target correction and row-error tracking. It is not yet integrated with a scheduler that handles commands already issued before placement feedback arrives.

## 6. Datasets and Model Training

### Currently supported dashboard upload

The dashboard accepts an internal-format CSV with these columns:

| Column | Meaning |
|---|---|
| `longitudinal_distance_m` | Position along the field |
| `lateral_distance_m` | Position across the field |
| `depth_cm` | Measurement/model depth |
| `provided_moisture_vwc_pct` | Measured/provided volumetric moisture percentage |
| `semi_synthetic_moisture_vwc_pct` | Current supervised model training target |
| `time_s` | Replay timing |
| `tractor_speed_kmh` | Replay vehicle speed |

The dashboard currently requires data at 5 cm depth. Use the default integration CSV as the reference layout.

Dataset acceptance does not establish sensor calibration, measurement quality, or model generalisation.

### Client raw data

Original client data is stored under:

```text
data/raw/
```

The client format is a spatial moisture grid:

- Longitudinal distance down the rows.
- Lateral distances across the columns.
- Volumetric moisture percentages in the cells.
- Multiple header rows.

This raw format is not directly accepted by the current dashboard uploader.

A future importer should normalise this format and report missing metadata and unexpected cells explicitly.

### Model implementation

`hao_model_runtime.py` implements:

- Feature scaling.
- A two-component Gaussian-mixture gate.
- Two Gaussian-process experts.
- Probability-weighted expert predictions.

The current inference API returns predicted moisture, dominant expert, and expert weights. 
Expert weights are not prediction uncertainty intervals.

To run the existing training script:

```bash
python scripts/train_model.py
```

Model fitting and loading belong outside the operational controller update.

## 7. Dashboard Outputs

The dashboard provides:

- Animation.
- 3D moisture model.
- Seeding errors.
- Release log.
- Controller diagnostics.

## 8. Repository Guide

```text
.
├── final_dashboard.py          # Streamlit interface - main Dashboard code
├── interface.py                # Existing public compatibility API
├── main.py                     # Existing batch entry point
├── run_unix.sh                 # macOS/Linux setup and dashboard launcher
├── run_windows.bat             # Windows setup and dashboard launcher
├── ICT/
│   └── .venv/                  # Local Python environment; not committed
│
├── requirements.txt
├── requirements-dev.txt
│
├── prediction_control/
│   ├── __init__.py
│   ├── sensor.py               # Stateful moisture filtering
│   ├── control_loop.py         # Independent moisture/depth controller
│   ├── simulation.py           # Dataset replay and actuator simulation
│   ├── dashboard_bridge.py     # Dashboard compatibility adapter
│   ├── spacing.py              # Gap metrics and bounded correction component
│   ├── release_timing.py       # Tested causal sample-selection helper
│   ├── compensation.py         # Existing offset/delay compensation
│   ├── prediction_logic.py     # Moisture-to-depth and legacy decision rules
│   ├── release_stream.py       # Standalone sensor-only RxPY path
│   ├── dataset_pipeline.py     # Internal dataset and batch workflow
│   ├── hao_model_runtime.py    # Model training/inference implementation
│   └── validation.py           # Batch input/configuration validation
│
├── data/
│   ├── raw/                    # Original client data
│   └── integration/            # Current internal-use datasets (including default)
│   
├── models/                     # Saved model artefacts
├── outputs/                    # Generated batch outputs
├── scripts/                    # Training/data-preparation utilities
├── tests/                      # Automated tests
├── docs/                       # Contracts and architecture documentation
├── Jupyter Notebooks/          # Modelling experiments
```

Generated caches and other artefacts are not operational controller components.

## 9. Testing

Run the complete suite:

```bash
python -m pytest -q
```

Tests cover filtering, depth direction, model assistance, startup, invalid observations, spacing calculations, causal sample selection, replay integration, legacy release compensation, and validation.

Passing tests do not establish physical accuracy, robustness to every noise distribution, or real-time deadline compliance.

## 10. Existing Utilities

The repository retains the batch entry point:

```bash
python main.py
```

It also retains a dashboard-data preparation utility:

```bash
python scripts/prepare_dashboard_data.py
```

The preparation utility is associated with:

```text
data/integration/winter_wheat_dashboard_input.xlsx
```

That workbook is not the current CSV dashboard-upload contract. It is used to generate the semi-synthetic dataset that is used by default.

The batch entry point and utility scripts are separate from the updated dashboard replay. 

## 11. Further Engineering and Validation

Priority remaining work:

1. Import and validate the client’s raw spatial-grid CSV.
2. Integrate timestamped live moisture and vehicle-position acquisition.
3. Calibrate filtering and model assistance against representative noise.
4. Benchmark inference and complete control-cycle latency.
5. Implement pending-command-aware release scheduling.
6. Integrate row correction using measured or explicitly simulated feedback.
7. Validate sensor offset, latency, and actuator behaviour.
8. Measure physical individual seed gaps against the ±1 mm requirement.
9. Define hardware startup, stale-data, stopping, recovery, and fault policies.

The present replay should not be connected directly to physical machinery without these integration and safety decisions.

## 12. Further Documentation

## Further Documentation

- [Documentation index](docs/docs.md)
- [Handover notes](docs/handover.md)
- [Controller contract](docs/controller-contract.md)
- [Dataset guide](docs/dataset-guide.md)
- [Data-Flow Diagram](docs/Data-Flow%20Diagram.md)

Some supporting documents may describe earlier execution paths.