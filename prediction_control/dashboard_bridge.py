"""Drop-in backend for Manan's unchanged ``run_simulation`` UI API."""
from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd

from interface import DEFAULT_CONFIG
from .dataset_pipeline import load_project_dataset
from .hao_model_runtime import HaoMixtureGPRRuntime, FEATURE_COLUMNS
from .prediction_logic import evaluate_prediction

ROOT = Path(__file__).resolve().parents[1]
DATASET_PATH = ROOT / "data" / "integration" / "final_semi_synthetic_winter_wheat_v2.csv"
MODEL_PATH = ROOT / "models" / "hao_mixture_gpr_runtime.joblib"

_DATASET = None
_MODEL = None

def _resources():
    global _DATASET, _MODEL
    if _DATASET is None:
        _DATASET = load_project_dataset(DATASET_PATH)
    if _MODEL is None:
        _MODEL = HaoMixtureGPRRuntime.load(MODEL_PATH) if MODEL_PATH.exists() else HaoMixtureGPRRuntime().fit(_DATASET)
    return _DATASET, _MODEL


def _estimate_lateral(field_positions, field_moisture, depth_cm=5.0):
    df, _ = _resources()
    positions = np.asarray(field_positions, float)
    moisture = np.asarray(field_moisture, float)
    candidates = np.linspace(0.0, 30.0, 61)
    errors=[]
    for lat in candidates:
        lo = 0.0 if lat <= 15 else 15.0
        hi = 15.0 if lat <= 15 else 30.0
        a=df[(np.isclose(df.lateral_distance_m,lo))&(np.isclose(df.depth_cm,depth_cm))].sort_values('longitudinal_distance_m')
        b=df[(np.isclose(df.lateral_distance_m,hi))&(np.isclose(df.depth_cm,depth_cm))].sort_values('longitudinal_distance_m')
        w=0.0 if hi==lo else (lat-lo)/(hi-lo)
        base=(1-w)*a.provided_moisture_vwc_pct.to_numpy(float)+w*b.provided_moisture_vwc_pct.to_numpy(float)
        basepos=a.longitudinal_distance_m.to_numpy(float)
        expected=np.interp(positions,basepos,base)
        errors.append(np.mean((expected-moisture)**2))
    return float(candidates[int(np.argmin(errors))])


def run_simulation(field_positions, field_moisture, speed_time, speed_values,
                   target_spacing_m, control_dt_s, actuator_tau_s,
                   min_moisture, max_moisture, min_depth, max_depth):
    _, model = _resources()
    field_positions=np.asarray(field_positions,float)
    field_moisture=np.asarray(field_moisture,float)
    speed_time=np.asarray(speed_time,float)
    speed_values=np.asarray(speed_values,float)
    lateral=_estimate_lateral(field_positions, field_moisture)
    depth_cm=5.0

    times=np.arange(0.0,float(speed_time.max()),float(control_dt_s))
    speeds=np.interp(times,speed_time,speed_values)
    positions=np.zeros_like(times)
    if len(times)>1:
        positions[1:]=np.cumsum(speeds[:-1]*float(control_dt_s))
    positions=np.clip(positions,field_positions.min(),field_positions.max())
    measured=np.interp(positions,field_positions,field_moisture)
    X=np.column_stack([positions,np.full(len(positions),lateral),np.full(len(positions),depth_cm),measured])
    pred,std,regime=model.predict_batch(X)

    config=dict(DEFAULT_CONFIG)
    config.update({
        'target_spacing_m':float(target_spacing_m),
        'min_moisture':float(min_moisture), 'max_moisture':float(max_moisture),
        'min_depth_mm':float(min_depth), 'max_depth_mm':float(max_depth),
        'actuator_tau_s':float(actuator_tau_s),
    })
    target=np.array([evaluate_prediction(p,m,s,config,predicted_moisture=pr)['target_depth_mm']
                     for p,m,s,pr in zip(positions,measured,speeds,pred)],float)
    actual=np.empty_like(target)
    if len(target):
        actual[0]=target[0]
        alpha=float(control_dt_s)/(float(actuator_tau_s)+float(control_dt_s))
        for i in range(1,len(target)):
            actual[i]=actual[i-1]+alpha*(target[i]-actual[i-1])
    log=pd.DataFrame({'time_s':times,'position_m':positions,'speed_m_s':speeds,
        'moisture_pct':pred,'target_depth_mm':target,'actuator_depth_mm':actual,
        'measured_moisture_pct':measured,'predicted_moisture_pct':pred,
        'prediction_std_pct':std,'model_regime':regime})

    targets=np.arange(positions.min(),positions.max()+1e-12,float(target_spacing_m))
    rt=np.interp(targets,positions,times); rs=np.interp(targets,positions,speeds)
    rm=np.interp(targets,field_positions,field_moisture)
    RX=np.column_stack([targets,np.full(len(targets),lateral),np.full(len(targets),depth_cm),rm])
    rp,rstd,rreg=model.predict_batch(RX)
    release_rows=[]
    for p,t,s,m,pr,sd,rg in zip(targets,rt,rs,rm,rp,rstd,rreg):
        d=evaluate_prediction(p,m,s,config,predicted_moisture=pr,prediction_std=sd,model_regime=int(rg))
        if d['should_release']:
            release_rows.append({'time_s':float(t),'position_m':float(p),'speed_m_s':float(s),
                'moisture_pct':float(pr),'target_depth_mm':d['target_depth_mm'],
                'actuator_depth_mm':float(np.interp(t,times,actual)),
                'measured_moisture_pct':float(m),'predicted_moisture_pct':float(pr),
                'prediction_std_pct':float(sd),'model_regime':int(rg)})
    return log,pd.DataFrame(release_rows)
