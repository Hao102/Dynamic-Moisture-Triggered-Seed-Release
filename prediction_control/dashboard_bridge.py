"""Compatibility adapter for the existing dashboard simulation API.

Control and simulation implementation must remain outside this module.
"""

from .simulation import run_simulation

__all__ = ["run_simulation"]