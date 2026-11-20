# Helper - selection of the latest controller output available at command time.

import numpy as np


def latest_available_index(sample_times, command_time):
    # Return the latest sample index available at command_time.
    # Returns None when no sample is available yet. No future sample is used.
    
    sample_times = np.asarray(sample_times, dtype=float)
    command_time = float(command_time)

    if sample_times.ndim != 1 or sample_times.size == 0:
        raise ValueError("sample_times must be a non-empty one-dimensional array")

    if not np.all(np.isfinite(sample_times)):
        raise ValueError("sample_times must contain only finite values")

    if not np.isfinite(command_time):
        raise ValueError("command_time must be finite")

    if np.any(np.diff(sample_times) <= 0):
        raise ValueError("sample_times must be strictly increasing")

    index = int(np.searchsorted(sample_times, command_time, side="right")) - 1
    return index if index >= 0 else None