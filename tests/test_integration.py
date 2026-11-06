from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from prediction_control.compensation import calculate_release_target
from prediction_control.prediction_logic import evaluate_prediction
from prediction_control.dataset_pipeline import build_path_dataframe

ROOT=Path(__file__).resolve().parents[1]

def test_dataset_schema_and_path():
    df=pd.read_csv(ROOT/'data'/'integration'/'final_semi_synthetic_winter_wheat_v2.csv')
    path=build_path_dataframe(df,15.0,5.0)
    assert len(path)==1720
    assert np.isclose(path['lateral_distance_m'].iloc[0],15.0)

def test_prediction_uses_model_value():
    config={'target_spacing_m':0.03,'min_moisture':1.0,'max_moisture':10.0,'min_depth_mm':15.0,'max_depth_mm':40.0}
    out=evaluate_prediction(1.0,3.0,1.0,config,predicted_moisture=8.0)
    assert out['measured_moisture_pct']==3.0
    assert out['moisture_pct']==8.0
    assert out['target_depth_mm'] < 25.0

def test_compensation_hits_target_when_lead_time_is_sufficient():
    event={'time_s':1.0,'position_m':2.0,'speed_m_s':1.0}
    out=calculate_release_target(event,{'sensor_offset_m':0.5,'actuator_delay_s':0.1})
    assert np.isclose(out['position_m'],2.0)
    assert np.isclose(out['compensation_error_m'],0.0)

def test_compensation_schedules_command_before_target_time():
    event = {
        "time_s": 1.0,
        "position_m": 2.0,
        "speed_m_s": 1.0,
    }
    config = {
        "sensor_offset_m": 0.5,
        "actuator_delay_s": 0.1,
    }

    result = calculate_release_target(event, config)

    assert result["target_position_m"] == pytest.approx(2.0)
    assert result["command_time_s"] == pytest.approx(1.4)
    assert result["release_time_s"] == pytest.approx(1.5)
    assert result["position_m"] == pytest.approx(2.0)
    assert result["compensation_error_m"] == pytest.approx(0.0)
