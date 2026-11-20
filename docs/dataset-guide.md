# Dataset Guide

This guide explains the dataset format accepted by the dashboard, the default demonstration dataset and model, and the boundary between the current internal format and the client’s raw spatial-grid data.

Dataset acceptance does not establish sensor calibration, measurement quality, or model generalisation.

## Dashboard dataset format

The dashboard accepts an internal-format CSV with the following columns:

| Column | Meaning |
|---|---|
| `longitudinal_distance_m` | Position along the field |
| `lateral_distance_m` | Position across the field |
| `depth_cm` | Measurement or model depth |
| `provided_moisture_vwc_pct` | Measured or provided volumetric moisture percentage |
| `semi_synthetic_moisture_vwc_pct` | Current supervised model training target |
| `time_s` | Replay timing |
| `tractor_speed_kmh` | Replay vehicle speed |

The dashboard currently requires data at 5 cm depth.

Use this file as the reference layout:

```text
data/integration/final_semi_synthetic_winter_wheat_v2.csv
```

## Required checks

Before uploading a dataset, confirm that:
- All required columns are present.
- Numeric fields contain valid finite values.
- Timestamps are ordered and suitable for replay.
- Vehicle speed is non-negative.
- Moisture and depth values are physically plausible.
- The dataset covers the intended longitudinal and lateral field extent.
- The dataset is at the required 5 cm measurement depth.

The dashboard validates software preconditions. Passing validation does not prove that the data are accurate, representative, or suitable for every modelling purpose.

## Default demonstration dataset

The default dashboard dataset is:

```text
data/integration/final_semi_synthetic_winter_wheat_v2.csv
```

The default dashboard model is:

```text
models/hao_mixture_gpr_runtime.joblib
```

The dashboard attempts to load the default model for the default dataset. If no usable model is loaded, it trains one in memory.
A model trained during a dashboard session is not automatically saved to disk.

## Model inputs and target

The current model uses these input features:
- Longitudinal position.
- Lateral position.
- Depth.
- Provided moisture.

The supervised training target is:

```text
semi_synthetic_moisture_vwc_pct
```

Model fitting and loading belong outside the operational controller update. The controller receives an already-trained model.

## Client raw data

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

## Future raw-data importer

A future importer should:

1. Parse the spatial grid and header metadata.
2. Validate missing cells and unexpected values.
3. Convert grid coordinates to longitudinal and lateral distances.
4. Add replay timing and vehicle-speed fields.
5. Produce the internal dashboard CSV format.
6. Report all assumptions and transformations explicitly.

Until that importer is implemented, client raw spatial-grid data cannot be loaded directly through the dashboard uploader.

## Dataset limitations

- The current dashboard uploader accepts the internal CSV format, not the client raw spatial-grid format.
- The current dashboard requires data at 5 cm depth.
- Dataset acceptance does not establish sensor calibration or measurement quality.
- A compatible dataset does not guarantee model generalisation.
- Replay timing and vehicle-speed fields are required for the current dashboard replay workflow.
- A dataset prepared for the dashboard must include all required columns and follow the reference layout.

