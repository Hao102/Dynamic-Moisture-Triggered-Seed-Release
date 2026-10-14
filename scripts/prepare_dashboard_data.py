from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd

src = ROOT / 'data' / 'integration' / 'final_semi_synthetic_winter_wheat_v2.csv'
out = ROOT / 'data' / 'integration' / 'winter_wheat_dashboard_input.xlsx'
df = pd.read_csv(src)
base = df[df['depth_cm'] == 5].pivot(
    index='longitudinal_distance_m',
    columns='lateral_distance_m',
    values='provided_moisture_vwc_pct',
).reset_index()
base = base[['longitudinal_distance_m', 0.0, 15.0, 30.0]]
with pd.ExcelWriter(out, engine='openpyxl') as writer:
    pd.DataFrame([
        ['Generated from final_semi_synthetic_winter_wheat_v2.csv'],
        ['5 cm moisture layer'],
        ['distance_m / lateral moisture (%)'],
    ]).to_excel(writer, index=False, header=False, startrow=0)
    base.to_excel(writer, index=False, header=False, startrow=3)
print(out)
