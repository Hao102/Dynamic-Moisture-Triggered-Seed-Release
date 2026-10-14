"""Run Manan's original Streamlit app with Tony's new backend.

The visualization source file is read-only and remains byte-for-byte unchanged.
Run with:  streamlit run run_dashboard.py
"""
import ast
from pathlib import Path

ROOT=Path(__file__).resolve().parent
SOURCE=ROOT/'visualization'/'seed_dashboard'/'app.py'

replacement=ast.parse('def run_simulation(field_positions, field_moisture, speed_time, speed_values,\n                   target_spacing_m, control_dt_s, actuator_tau_s,\n                   min_moisture, max_moisture, min_depth, max_depth):\n    from prediction_control.dashboard_bridge import run_simulation as _run\n    return _run(field_positions, field_moisture, speed_time, speed_values,\n                target_spacing_m, control_dt_s, actuator_tau_s,\n                min_moisture, max_moisture, min_depth, max_depth)\n').body[0]
source=SOURCE.read_text(encoding='utf-8')
tree=ast.parse(source, filename=str(SOURCE))
found=False
for i,node in enumerate(tree.body):
    if isinstance(node,ast.FunctionDef) and node.name=='run_simulation':
        ast.copy_location(replacement,node); tree.body[i]=replacement; found=True; break
if not found: raise RuntimeError('run_simulation not found in visualization/app.py')
ast.fix_missing_locations(tree)
exec(compile(tree,str(SOURCE),'exec'),{'__name__':'__main__','__file__':str(SOURCE)})
