from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
from prediction_control.hao_model_runtime import HaoMixtureGPRRuntime

df = pd.read_csv(ROOT / 'data' / 'integration' / 'final_semi_synthetic_winter_wheat_v2.csv')
model = HaoMixtureGPRRuntime().fit(df)
path = ROOT / 'models' / 'hao_mixture_gpr_runtime.joblib'
model.save(path)
print(f'Saved: {path}')
