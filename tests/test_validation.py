from copy import deepcopy

import numpy as np
import pandas as pd
import pytest

from prediction_control.dataset_pipeline import REQUIRED_DATA_COLUMNS, load_project_dataset
from prediction_control.hao_model_runtime import FEATURE_COLUMNS, TARGET_COLUMN, HaoMixtureGPRRuntime
from prediction_control.validation import validate_inputs


@pytest.fixture
def valid_config():
    return {
        "target_spacing_m": 0.03,
        "min_moisture": 1.0,
        "max_moisture": 10.0,
        "min_depth_mm": 15.0,
        "max_depth_mm": 40.0,
        "sensor_offset_m": 0.50,
        "actuator_delay_s": 0.10,
        "actuator_tau_s": 0.15,
        "model_depth_cm": 5.0,
    }


@pytest.fixture
def valid_inputs(valid_config):
    return {
        "field_positions": [0.0, 0.14, 0.28, 0.42],
        "field_moisture": [4.0, 4.2, 4.1, 4.3],
        "speed_time": [0.0, 0.1, 0.2, 0.3],
        "speed_values": [1.38, 1.39, 1.38, 1.40],
        "config": valid_config,
    }


def run_validation(data):
    validate_inputs(
        data["field_positions"],
        data["field_moisture"],
        data["speed_time"],
        data["speed_values"],
        data["config"],
    )


def test_valid_input(valid_inputs):
    run_validation(valid_inputs)


@pytest.mark.parametrize(
    "name", ["field_positions", "field_moisture", "speed_time", "speed_values"]
)
def test_empty_input(valid_inputs, name):
    data = deepcopy(valid_inputs)
    data[name] = []

    with pytest.raises(ValueError, match="cannot be empty"):
        run_validation(data)


@pytest.mark.parametrize(
    "name", ["field_positions", "field_moisture", "speed_time", "speed_values"]
)
def test_none_input(valid_inputs, name):
    data = deepcopy(valid_inputs)
    data[name] = None

    with pytest.raises(ValueError, match="cannot be empty"):
        run_validation(data)


def test_position_moisture_length(valid_inputs):
    data = deepcopy(valid_inputs)
    data["field_moisture"].pop()

    with pytest.raises(ValueError, match="same length"):
        run_validation(data)


def test_time_speed_length(valid_inputs):
    data = deepcopy(valid_inputs)
    data["speed_values"].pop()

    with pytest.raises(ValueError, match="same length"):
        run_validation(data)


@pytest.mark.parametrize(
    "name", ["field_positions", "field_moisture", "speed_time", "speed_values"]
)
def test_non_numeric_input(valid_inputs, name):
    data = deepcopy(valid_inputs)
    data[name][1] = "bad"

    with pytest.raises(TypeError, match="must be numeric"):
        run_validation(data)


@pytest.mark.parametrize(
    "name", ["field_positions", "field_moisture", "speed_time", "speed_values"]
)
def test_boolean_input(valid_inputs, name):
    data = deepcopy(valid_inputs)
    data[name][1] = True

    with pytest.raises(TypeError, match="must be numeric"):
        run_validation(data)


@pytest.mark.parametrize(
    "name", ["field_positions", "field_moisture", "speed_time", "speed_values"]
)
@pytest.mark.parametrize("value", [np.nan, np.inf, -np.inf])
def test_non_finite_input(valid_inputs, name, value):
    data = deepcopy(valid_inputs)
    data[name][1] = value

    with pytest.raises(ValueError, match="must be finite"):
        run_validation(data)


def test_position_order(valid_inputs):
    data = deepcopy(valid_inputs)
    data["field_positions"] = [0.0, 0.28, 0.14, 0.42]

    with pytest.raises(ValueError, match="field_positions must be strictly increasing"):
        validate_inputs(**data)


def test_time_order(valid_inputs):
    data = deepcopy(valid_inputs)
    data["speed_time"] = [0.0, 0.2, 0.1, 0.3]

    with pytest.raises(ValueError, match="speed_time must be strictly increasing"):
        run_validation(data)


def test_duplicate_time(valid_inputs):
    data = deepcopy(valid_inputs)
    data["speed_time"] = [0.0, 0.1, 0.1, 0.3]

    with pytest.raises(ValueError, match="speed_time must be strictly increasing"):
        run_validation(data)


def test_negative_speed(valid_inputs):
    data = deepcopy(valid_inputs)
    data["speed_values"][2] = -1.0

    with pytest.raises(ValueError, match="negative speeds"):
        run_validation(data)


def test_zero_speed(valid_inputs):
    data = deepcopy(valid_inputs)
    data["speed_values"][2] = 0.0
    run_validation(data)


def test_none_config(valid_inputs):
    data = deepcopy(valid_inputs)
    data["config"] = None

    with pytest.raises(ValueError, match="config cannot be None"):
        run_validation(data)


def test_config_type(valid_inputs):
    data = deepcopy(valid_inputs)
    data["config"] = [1, 2, 3]

    with pytest.raises(TypeError, match="config must be a mapping"):
        run_validation(data)


@pytest.mark.parametrize(
    "key",
    [
        "target_spacing_m",
        "min_moisture",
        "max_moisture",
        "min_depth_mm",
        "max_depth_mm",
    ],
)
def test_missing_config_key(valid_inputs, key):
    data = deepcopy(valid_inputs)
    del data["config"][key]

    with pytest.raises(ValueError, match="Missing config keys"):
        run_validation(data)


CONFIG_KEYS = [
    "target_spacing_m",
    "min_moisture",
    "max_moisture",
    "min_depth_mm",
    "max_depth_mm",
    "sensor_offset_m",
    "actuator_delay_s",
    "actuator_tau_s",
    "model_depth_cm",
]


@pytest.mark.parametrize("key", CONFIG_KEYS)
def test_config_numeric(valid_inputs, key):
    data = deepcopy(valid_inputs)
    data["config"][key] = "bad"

    with pytest.raises(TypeError, match="must be numeric"):
        run_validation(data)


@pytest.mark.parametrize("key", CONFIG_KEYS)
def test_config_finite(valid_inputs, key):
    data = deepcopy(valid_inputs)
    data["config"][key] = np.nan

    with pytest.raises(ValueError, match="must be finite"):
        run_validation(data)


@pytest.mark.parametrize("spacing", [0.0, -0.03])
def test_spacing_range(valid_inputs, spacing):
    data = deepcopy(valid_inputs)
    data["config"]["target_spacing_m"] = spacing

    with pytest.raises(ValueError, match="target_spacing_m must be greater than 0"):
        run_validation(data)


def test_moisture_threshold_order(valid_inputs):
    data = deepcopy(valid_inputs)
    data["config"]["min_moisture"] = 10.0
    data["config"]["max_moisture"] = 1.0

    with pytest.raises(ValueError, match="min_moisture cannot be greater"):
        run_validation(data)


@pytest.mark.parametrize("key", ["min_depth_mm", "max_depth_mm"])
def test_negative_depth(valid_inputs, key):
    data = deepcopy(valid_inputs)
    data["config"][key] = -1.0

    with pytest.raises(ValueError, match="seed depth values cannot be negative"):
        run_validation(data)


def test_depth_order(valid_inputs):
    data = deepcopy(valid_inputs)
    data["config"]["min_depth_mm"] = 50.0
    data["config"]["max_depth_mm"] = 20.0

    with pytest.raises(ValueError, match="min_depth_mm cannot be greater"):
        run_validation(data)


@pytest.mark.parametrize(
    "key", ["sensor_offset_m", "actuator_delay_s", "actuator_tau_s", "model_depth_cm"]
)
def test_negative_optional_config(valid_inputs, key):
    data = deepcopy(valid_inputs)
    data["config"][key] = -0.01

    with pytest.raises(ValueError, match="must be non-negative"):
        run_validation(data)


def make_dataset():
    data = {column: [1.0, 2.0] for column in REQUIRED_DATA_COLUMNS}
    data["longitudinal_distance_m"] = [0.0, 0.14]
    data["lateral_distance_m"] = [15.0, 15.0]
    data["depth_cm"] = [5.0, 5.0]
    data["time_s"] = [0.0, 0.1]
    data["tractor_speed_kmh"] = [5.0, 5.0]
    data["provided_moisture_vwc_pct"] = [4.0, 4.1]
    data["semi_synthetic_moisture_vwc_pct"] = [4.2, 4.3]
    return pd.DataFrame(data)


def test_dataset_load(tmp_path):
    path = tmp_path / "test.csv"
    make_dataset().to_csv(path, index=False)

    df = load_project_dataset(path)
    assert len(df) == 2
    assert REQUIRED_DATA_COLUMNS.issubset(df.columns)


@pytest.mark.parametrize("column", sorted(REQUIRED_DATA_COLUMNS))
def test_missing_dataset_column(tmp_path, column):
    df = make_dataset().drop(columns=[column])
    path = tmp_path / "test.csv"
    df.to_csv(path, index=False)

    with pytest.raises(ValueError, match="Dataset missing required columns"):
        load_project_dataset(path)


def test_missing_dataset_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_project_dataset(tmp_path / "missing.csv")


def make_model_data():
    data = {column: [1.0, 2.0] for column in FEATURE_COLUMNS}
    data[TARGET_COLUMN] = [4.0, 4.2]
    return pd.DataFrame(data)


def test_model_data():
    HaoMixtureGPRRuntime.validate_dataframe(make_model_data())


def test_empty_model_data():
    columns = FEATURE_COLUMNS + [TARGET_COLUMN]

    with pytest.raises(ValueError, match="Dataset cannot be empty"):
        HaoMixtureGPRRuntime.validate_dataframe(pd.DataFrame(columns=columns))


@pytest.mark.parametrize("column", FEATURE_COLUMNS + [TARGET_COLUMN])
def test_missing_model_column(column):
    df = make_model_data().drop(columns=[column])

    with pytest.raises(ValueError, match="missing required model columns"):
        HaoMixtureGPRRuntime.validate_dataframe(df)


def test_duplicate_position(valid_inputs):
    data = deepcopy(valid_inputs)
    data["field_positions"] = [0.0, 0.14, 0.14, 0.42]

    with pytest.raises(ValueError):
        run_validation(data)


def test_negative_position(valid_inputs):
    data = deepcopy(valid_inputs)
    data["field_positions"] = [-0.14, 0.0, 0.14, 0.28]

    with pytest.raises(ValueError):
        run_validation(data)


def test_negative_time(valid_inputs):
    data = deepcopy(valid_inputs)
    data["speed_time"] = [-0.1, 0.0, 0.1, 0.2]

    with pytest.raises(ValueError):
        run_validation(data)


@pytest.mark.parametrize("value", [-1.0, 101.0])
def test_moisture_range(valid_inputs, value):
    data = deepcopy(valid_inputs)
    data["field_moisture"][1] = value

    with pytest.raises(ValueError):
        run_validation(data)


def test_empty_dataset(tmp_path):
    path = tmp_path / "empty.csv"
    pd.DataFrame(columns=sorted(REQUIRED_DATA_COLUMNS)).to_csv(path, index=False)

    with pytest.raises(ValueError):
        load_project_dataset(path)


def test_dataset_nan(tmp_path):
    df = make_dataset()
    df.loc[1, "provided_moisture_vwc_pct"] = np.nan
    path = tmp_path / "nan.csv"
    df.to_csv(path, index=False)

    with pytest.raises(ValueError):
        load_project_dataset(path)


def test_duplicate_rows(tmp_path):
    df = make_dataset()
    df = pd.concat([df, df.iloc[[1]]], ignore_index=True)
    path = tmp_path / "duplicate.csv"
    df.to_csv(path, index=False)

    with pytest.raises(ValueError):
        load_project_dataset(path)
