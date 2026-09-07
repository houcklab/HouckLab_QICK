import numpy as np


def distributed_p0_reference_indices(total_shots, max_sweeps=10):
    total_shots = int(total_shots)
    max_sweeps = int(max_sweeps)
    if total_shots <= 0:
        raise ValueError("total_shots must be positive")
    if max_sweeps < 2:
        raise ValueError("max_sweeps must be at least two")
    if total_shots <= max_sweeps:
        return tuple(range(total_shots))
    sweep_count = max_sweeps - max_sweeps % 2
    pair_count = sweep_count // 2
    max_even = ((total_shots - 2) // 2) * 2
    even_indices = np.rint(np.linspace(0, max_even, pair_count)).astype(int)
    even_indices -= even_indices % 2
    indices = tuple(
        int(value)
        for even in even_indices
        for value in (even, even + 1)
    )
    if len(indices) != sweep_count or len(set(indices)) != sweep_count:
        raise ValueError("could not distribute unique P0 reference sweeps")
    return indices


def canonicalize_bidirectional_records(values):
    values = np.asarray(values)
    if values.ndim != 3 or values.shape[2] != 3:
        raise ValueError("three-point records must have shape (shots, dc, 3)")
    canonical = values.copy()
    canonical[1::2] = canonical[1::2, ::-1]
    return canonical


def reduce_bidirectional_states(states, p0_reference_shot_indices):
    states = np.asarray(states, dtype=float)
    if states.ndim != 3 or states.shape[0] != 3:
        raise ValueError("three-point states must have shape (3, dc, shots)")
    shots = int(states.shape[2])
    if shots < 2:
        raise ValueError("bidirectional acquisition requires at least two shots")
    reference_indices = tuple(int(value) for value in p0_reference_shot_indices)
    if not reference_indices:
        raise ValueError("at least one P0 reference shot is required")
    if len(set(reference_indices)) != len(reference_indices):
        raise ValueError("P0 reference shot indices must be unique")
    if min(reference_indices) < 0 or max(reference_indices) >= shots:
        raise ValueError("P0 reference shot indices are outside the shot range")
    up_mask = np.arange(shots) % 2 == 0
    down_mask = ~up_mask
    p0_up_indices = [value for value in reference_indices if value % 2 == 0]
    p0_down_indices = [value for value in reference_indices if value % 2 == 1]
    if not p0_up_indices or not p0_down_indices:
        raise ValueError("P0 references must cover both scan directions")
    p0_up_value = float(np.mean(states[0, :, p0_up_indices]))
    p0_down_value = float(np.mean(states[0, :, p0_down_indices]))
    p0_value = (
        p0_up_value * len(p0_up_indices)
        + p0_down_value * len(p0_down_indices)
    ) / len(reference_indices)
    dc_points = int(states.shape[1])
    p0_up = np.full(dc_points, p0_up_value, dtype=float)
    p0_down = np.full(dc_points, p0_down_value, dtype=float)
    p0 = np.full(dc_points, p0_value, dtype=float)
    p1_up = np.mean(states[1][:, up_mask], axis=1)
    p1_down = np.mean(states[1][:, down_mask], axis=1)
    ps_up = np.mean(states[2][:, up_mask], axis=1)
    ps_down = np.mean(states[2][:, down_mask], axis=1)
    up_shots = int(np.count_nonzero(up_mask))
    down_shots = int(np.count_nonzero(down_mask))
    return {
        "P0": p0,
        "P0_scan_up": p0_up,
        "P0_scan_down": p0_down,
        "P1": (up_shots * p1_up + down_shots * p1_down) / shots,
        "P1_scan_up": p1_up,
        "P1_scan_down": p1_down,
        "Ps": (up_shots * ps_up + down_shots * ps_down) / shots,
        "Ps_scan_up": ps_up,
        "Ps_scan_down": ps_down,
        "dc_scan_up_shots": up_shots,
        "dc_scan_down_shots": down_shots,
        "p0_reference_sweeps": len(reference_indices),
        "p0_reference_up_sweeps": len(p0_up_indices),
        "p0_reference_down_sweeps": len(p0_down_indices),
    }
