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

This process receives measured observations and operating information from Process 2.0 and predicted moisture from Process 5.0.

In the prediction-enabled path, the supplied prediction is the moisture value used for the decision. The measured value remains available for traceability. In the measured-only alternative, the prediction override is omitted and the controller uses measured moisture instead. The diagram depicts the former path, not a claim that both values are automatically blended or filtered.

The agreed depth rule is:

- Higher control moisture requests shallower planting.
- Lower control moisture requests deeper planting.
- Requested depth remains within the configured limits.

The controller separately checks whether control moisture lies within the permitted release range. It can therefore return a bounded depth request even when a seed release is not eligible.

Depth-command update frequency is configurable, with 10 Hz as the current default. It describes the interval between commands, not hydraulic travel capability, fixed actuator latency, or seed-release capacity.

Requested depths, eligibility results, and decision records pass to Process 4.0. A continuous decision log passes to D3.

### 4.0 Simulate Depth Response and Assemble Release Records

This process combines controller outputs with trajectory, timing, and simulation settings. It simulates actuator movement toward successive depth commands using an assumed response model, retaining requested depth separately from simulated achieved depth.

Release records are assembled from candidate planting locations and eligibility decisions. Records associate simulated events with timing, position, moisture, requested depth, and achieved depth, as available in the selected implementation.

The results pass to D3. This process is not evidence that the dashboard executes a fully verified shared release-stream or compensation implementation. Full look-ahead scheduling and hardware calibration remain separate integration and verification tasks.

### 5.0 Generate Moisture Predictions

This process receives spatial and measured-moisture features from Process 2.0. It uses a saved model from D2 or a model fitted from the loaded dataset supplied by Process 1.0.

Its outputs have two distinct destinations:

1. **Process 3.0:** predicted moisture used for control in the prediction-enabled path.
2. **D3:** predicted moisture and moisture profiles for visualisation and review.

The control flow should not be interpreted as sending entire visualisation profiles into the decision function. Only the prediction values required by that function are supplied for control. Any additional model metadata retained in run outputs is diagnostic unless explicitly consumed by the controller.

Prediction is not automatically equivalent to sensor-noise filtering. Claims of denoising, confidence, uncertainty, or improved accuracy require evidence from the model's training objective and evaluation. Predicted moisture is not ground-truth soil moisture.

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
| 5.0 | 3.0 | Predicted moisture for control |
| 3.0 | 4.0 | Requested depths, moisture eligibility, and decision records |
| 3.0 | D3 | Continuous decision log |
| 4.0 | D3 | Simulated actuator depths and release records |
| 5.0 | D3 | Predicted moisture and moisture profiles |
| D3 | 6.0 | Run results |
| 6.0 | E2 | Animation, charts, tables, warnings, and CSV exports |

## 7. Interpretation of Control and Diagnostic Outputs

The prediction-enabled control path is:

```text
Field data -> Validation -> Selected-path preparation and replay
                                      |              |
                                      |              v
                                      |       Moisture prediction
                                      |              |
                                      v              v
                                    Control decisions
                                            |
                                            v
                            Simulated response and release records
                                            |
                                            v
                                Run results and presentation
```

| Measure | Interpretation |
|---|---|
| Depth tracking error | Simulated achieved depth minus requested depth, with the relevant time and ground-location reference stated. |
| Model-relative depth deviation | Simulated seed depth minus a depth selected through a separate model-based moisture-target search. |
| Suggested horizontal shift | A diagnostic shift toward a nearby model-derived moisture match; not measured placement error. |

## 8. Assumptions and Limitations

1. The depicted control path uses supplied model predictions and dashboard configurations
2. Actuator response is assumed and has not been calibrated against physical hydraulic performance.
3. Command frequency does not specify actuator travel speed, fixed latency, or maximum seed throughput.
4. Complete observation-history alignment, look-ahead scheduling, and physical command delivery remain to be verified.
5. D3 contains temporary data; durable retention requires export or another explicit persistence mechanism.
6. Logical data flows do not prove real-time execution guarantees or end-to-end integration of every backend module.