# Dynamic Moisture-Triggered Seed Release System

## Setup

For the first run, open the project directory:

```bash
cd ICT
```

Create a Python virtual environment:

```bash
python -m venv .venv
```

Activate the virtual environment on Windows:

```bash
.venv\Scripts\activate
```

Install the required dependencies:

```bash
python -m pip install -r requirements.txt
```

---

## Train the Runtime Prediction Model

For the first run, train the runtime model using:

```bash
python scripts/train_model.py
```

This command generates:

```text
models/hao_mixture_gpr_runtime.joblib
```

The model only needs to be retrained when the input dataset is replaced or updated.

---

## Prepare Dashboard Input Data

Run:

```bash
python scripts/prepare_dashboard_data.py
```

This generates the dashboard-compatible dataset:

```text
data/integration/winter_wheat_dashboard_input.xlsx
```

This file is used by the Streamlit visualisation module.

---

## Run the Integrated Pipeline

Run the complete prediction and control pipeline with:

```bash
python main.py
```

The system generates the following output files:

```text
outputs/
├── control_log.csv
├── release_events.csv
└── model_smoke_metrics.json
```

### `control_log.csv`

Contains the result for each sensor/control sample, including information such as:

- position
- vehicle speed
- measured soil moisture
- predicted soil moisture
- prediction uncertainty
- model regime
- target seeding depth

### `release_events.csv`

Contains the actual simulated seed release events, including:

- target release position
- command time
- release time
- predicted moisture
- target seeding depth
- actuator compensation information

---

## Run the Visualisation Dashboard

Start the Streamlit dashboard with:

```bash
streamlit run run_dashboard.py
```

Then open the local Streamlit URL shown in the terminal, normally:

```text
http://localhost:8501
```

Upload:

```text
data/integration/winter_wheat_dashboard_input.xlsx
```

and click **Run Simulation**.

The dashboard displays the integrated results from the prediction and control pipeline, including soil moisture, machine movement, seeding depth, release events, spacing statistics, and simulation animations.
