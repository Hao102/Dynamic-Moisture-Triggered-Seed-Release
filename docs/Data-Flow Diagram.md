# Level 1 Data-Flow Diagram
## Dynamic Moisture-Triggered Seed Release Simulation

## 1. Purpose and Scope

This document explains the Level 1 Data-Flow Diagram (DFD), which describes a prediction-enabled simulation path: measured field observations provide model inputs, and model predictions can inform moisture-based control decisions.

Vehicle movement and hydraulic depth response are simulated. The numbered processes represent logical responsibilities and data transformations, not independent services or a strict execution order.


## 2. Diagram

![Level 1 data-flow diagram of the Dynamic Moisture-Triggered Seed Release Simulation](<./images/L1 Data-Flow Diagram.png>)

*Figure 1. Level 1 DFD showing field-data loading, sensor-data replay, moisture prediction, moisture-based control decisions, simulated depth response, and presentation of run results. Predicted moisture is supplied to the control process in the prediction-enabled execution path.*

## 3. External Entities

| Entity | Responsibility |
|---|---|
| E1. Research collaborator / dataset provider | Supplies field datasets containing moisture observations and associated spatial or operational data. |
| E2. Operator / reviewer | Supplies uploaded data and run configuration and receives animations, charts, tables, warnings, and CSV exports. |

The dataset provider supplies data for simulation; the operator configures and reviews runs through the dashboard.

## 4. Data Stores

### D1. Available Field Datasets

D1 represents available input datasets, including the default dataset. It contains the soil-moisture observations and associated fields required to prepare a simulated pass. Process 1.0 reads this store.

#### Client Raw Spatial-Grid Data

Original client-supplied spatial moisture-grid data is stored under `data/raw/`.

The current dashboard uploader does not directly accept the client raw format. A future importer must normalise the spatial grid, validate missing metadata and unexpected cells, and convert the data into the dashboard’s internal replay format.

### D2. Saved Model Artefact

D2 represents a saved trained model used by Process 5.0. Where an appropriate artefact is unavailable, the loaded dataset can support fallback model fitting. The diagram does not claim that fallback fitting automatically writes a new artefact to D2.

### D3. In-Memory Run Results

D3 holds logical run outputs such as continuous decision logs, simulated actuator depths, release records, predicted moisture, and moisture profiles. It is an in-memory results store, not a persistent database. Explicit CSV export provides a way to retain selected outputs.

## 5. Processes

### 1.0 Load and Validate Inputs

This process receives the default dataset from D1 or an uploaded dataset from E2, together with the run configuration. Settings include seed spacing, moisture and depth ranges, sensor offset, depth-command frequency, and the assumed actuator-response parameter.

Loading and validation check required fields and applicable numeric, length, ordering, timestamp, and configuration conditions. These checks establish whether inputs satisfy software preconditions; they do not prove measurement accuracy or dataset suitability for every modelling purpose.

Validated data and settings pass to Process 2.0. Validation messages pass to Process 6.0. The dataset can also be supplied to Process 5.0 for fallback model fitting.

### 2.0 Prepare Selected Path and Replay Sensor Data

This process selects or interpolates the requested lateral path and uses the speed profile and timestamps to construct simulated vehicle movement. Dataset moisture observations are replayed as sensor values, with the configured offset representing the sensor's position ahead of the seed-placement point.

It supplies three data groups:

- Measured moisture, position, time, speed, and control settings to Process 3.0.
- Trajectory, timing, and simulation settings to Process 4.0.
- Position, lateral location, depth, and measured-moisture features to Process 5.0.

These flows support simulation. They do not establish that observation history, sensor lead time, and planting events have been fully synchronised and verified.

### 3.0 Generate Moisture-Based Control Decisions

### 3.0 Filter Moisture and Generate Depth Commands

This process receives replayed sensor observations and operating information from Process 2.0, together with predicted moisture from Process 5.0 when a model is available.

For each new observation, the controller:
1. Validates the raw moisture observation.
2. Updates a bounded history of valid readings.
3. Calculates a rolling median once the filter is ready.
4. Obtains a model prediction using the filtered moisture and configured spatial context, when a model is supplied.
5. Combines filtered sensor moisture with the model prediction.
6. Maps the resulting control moisture to a target planting depth.

The current implementation uses a three-observation median window and a model
weight of 0.2:

```text
control moisture =
    0.8 × filtered sensor moisture
  + 0.2 × predicted moisture
```

These are implementation defaults, not calibrated optimal values.

The depth rule is:
- Higher control moisture requests shallower planting.
- Lower control moisture requests deeper planting.
- Requested depth remains within the configured limits.

The controller returns a valid target-depth command only after the median filter is ready. Invalid observations and filter warm-up observations do not produce a new valid depth command. Replay retains the previous target depth in those cases.

If no model is supplied, the controller operates in sensor-only mode. If a model prediction is missing or invalid, the controller falls back to valid filtered sensor moisture.

Prediction uncertainty is not currently accepted by the controller and does not affect the control weight.

This process does not itself authorise or schedule seed release. It supplies controller observations and target-depth commands to Process 4.0. A continuous decision log passes to D3.

### 4.0 Generate Release Events and Simulate Depth Response

This process receives controller observations and target-depth commands from Process 3.0, together with trajectory, timing, and simulation settings from Process 2.0.

It performs two related replay responsibilities:
1. Generates candidate seed positions and determines release eligibility.
2. Simulates actuator movement toward successive target-depth commands.

Release candidates are generated on a spatial grid using the configured seed spacing. A candidate is eligible when its control moisture lies within the configured minimum and maximum moisture range.

For release eligibility, the replay selects a controller observation available
at or before the calculated command time:

```text
command time = planned release time - configured release delay
```

Candidates without a valid available controller observation are skipped.
The replay then applies sensor-offset and actuator-delay compensation:

```text
release time = command time + actuator delay
```

When available sensor lead time is sufficient, the command is scheduled so that expected physical release occurs at the target position. When lead time is insufficient, the command is issued immediately and the unavoidable late-release distance is recorded as `compensation_error_m`.

The simulated actuator starts at the configured minimum depth and moves toward successive target-depth commands using the configured response time constant. Requested depth remains separate from simulated achieved depth.

Release records associate simulated events with timing, position, moisture, requested depth, and achieved depth, as available in the selected implementation. Results pass to D3.

This process does not demonstrate a live scheduler that predicts unknown future vehicle motion, manages all pending actuator commands, or corrects future releases from measured seed-placement feedback.


### 5.0 Generate Moisture Predictions

This process receives spatial and measured-moisture features from Process 2.0. It uses a saved model from D2 or a model fitted from the loaded dataset supplied by Process 1.0.

Its outputs have two distinct destinations:
1. **Process 3.0:** predicted moisture available for model-assisted depth control.
2. **D3:** predicted moisture and moisture profiles for visualisation and review.

The control flow should not be interpreted as sending entire visualisation profiles into the decision function. Only the prediction values required by that function are supplied for control. Any additional model metadata retained in run outputs is diagnostic unless explicitly consumed by the controller.

Prediction is not equivalent to sensor-noise filtering. The controller performs separate bounded median filtering of sensor observations before using model assistance. 
Claims of denoising, confidence, uncertainty, or improved accuracy require evidence from the model’s training objective and evaluation.

The current controller combines filtered sensor moisture with predicted moisture using a fixed model weight. It does not currently use prediction uncertainty to adjust that weight.

### 6.0 Present Results and Export Logs

This process reads run results from D3 and presents them to E2 through the dashboard. Outputs include animations, moisture comparisons, requested and achieved depth plots, decision and release tables, exploratory moisture diagnostics, and CSV exports.

Validation messages from Process 1.0 are also presented here. Valid runs with zero releases are represented explicitly rather than treated as an application failure.

## 6. Data-Flow Summary

| Source | Destination | Data |
|---|---|---|
| E1 | D1 | Field dataset |
| D1 | 1.0 | Default dataset |
| E2 | 1.0 | Uploaded dataset and run configuration |
| 1.0 | 2.0 | Validated dataset and settings |
| 1.0 | 5.0 | Dataset for fallback model fitting |
| 1.0 | 6.0 | Validation errors |
| 2.0 | 3.0 | Replayed measured moisture, position, time, speed, and control settings |
| 2.0 | 4.0 | Trajectory, timing, and simulation settings |
| 2.0 | 5.0 | Position, lateral location, depth, and measured-moisture features |
| D2 | 5.0 | Saved model |
| 5.0 | 3.0 | Predicted moisture for optional model-assisted depth control |
| 3.0 | 4.0 | Controller observations, target-depth commands, and contionuous decsion log |
| 3.0 | D3 | Continuous decision log |
| 4.0 | D3 | Simulated actuator depths and release records |
| 5.0 | D3 | Predicted moisture and moisture profiles |
| D3 | 6.0 | Run results |
| 6.0 | E2 | Animation, charts, tables, warnings, and CSV exports |

## 7. Interpretation of Control and Diagnostic Outputs

The prediction-enabled control path is:

```text
Field data -> Validation -> Selected-path preparation and replay
                                      |
                                      +--> Moisture prediction
                                      |            |
                                      v            v
                        Median filtering and model-assisted
                                  depth control
                                      |
                                      +--> Controller observations
                                      |    and target-depth commands
                                      |
                                      v
                    Release eligibility, causal observation
                       selection, and timing compensation
                                      |
                                      v
                    Simulated actuator response and release records
                                      |
                                      v
                          Run results and presentation
```

The dashboard replay path and the standalone RxPY release-stream path are separate release-generation implementations. Both use the shared moisture-to-depth and release-eligibility rules, but they do not currently share one unified release-scheduling implementation.

The standalone release-stream implementation accepts complete input arrays and constructs release events before emitting them. It is not an incremental live-sensor processing implementation.

| Measure | Interpretation |
|---|---|
| Depth tracking error | Simulated achieved depth minus requested depth, with the relevant time and ground-location reference stated. |
| Model-relative depth deviation | Simulated seed depth minus a depth selected through a separate model-based moisture-target search. |
| Suggested horizontal shift | A diagnostic shift toward a nearby model-derived moisture match; not measured placement error. |

## 8. Assumptions and Limitations

1. The depicted control path uses supplied model predictions and dashboard configurations
2. Actuator response is assumed and has not been calibrated against physical hydraulic performance.
3. Command frequency does not specify actuator travel (hydraulic-depth) speed, fixed latency, or maximum seed throughput.
4. Complete observation-history alignment, look-ahead scheduling, and physical command delivery remain to be verified.
5. D3 contains temporary data; durable retention requires export or another explicit persistence mechanism.
6. Logical data flows do not prove real-time execution guarantees or end-to-end integration of every backend module.

