# Refactor - migration test
from prediction_control.dashboard_bridge import run_simulation
from prediction_control.simulation import run_simulation as backend_run_simulation


def test_dashboard_bridge_exposes_independent_backend():
    assert run_simulation is backend_run_simulation