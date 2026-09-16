"""Pure configuration for the temporary 3-point/OFF to 5-point/ON crossover."""

import os


ENVIRONMENT_VARIABLE = "Q3_PROTOCOL_CROSSOVER_PHASE"
COMMON = {
    "wall_clock_duration_min": 30.0,
    "freq_min_ghz": 3.9,
    "freq_max_ghz": 4.3,
    "dc_min": -20550,
    "dc_max": -11800,
    "sync_directory": "Z:/FluxTeam/Data/.qick_qua_sync",
}
PHASES = {
    "legacy_off": {
        "apply_flux_tail_compensation": False,
        "protocol_crossover_phase": "legacy_off",
        "protocol_crossover_calibration": "current_5pt_frozen",
        "output_suffix": "TLS_Protocol_Crossover_3pt_OFF",
        "sync_session": "q3_q5_protocol_crossover_20260916_3pt_off",
    },
    "current_on": {
        "apply_flux_tail_compensation": True,
        "protocol_crossover_phase": "current_on",
        "protocol_crossover_calibration": "current_5pt_frozen",
        "output_suffix": "TLS_Protocol_Crossover_5pt_ON",
        "sync_session": "q3_q5_protocol_crossover_20260916_5pt_on",
    },
}


def apply_phase(params, *, expected, environ=None):
    """Return params with the requested crossover arm applied, if enabled."""
    if expected not in PHASES:
        raise ValueError(f"unknown protocol-crossover phase: {expected}")
    environ = os.environ if environ is None else environ
    requested = str(environ.get(ENVIRONMENT_VARIABLE, "")).strip().lower()
    configured = dict(params)
    if not requested:
        return configured
    if requested != expected:
        raise ValueError(
            f"{ENVIRONMENT_VARIABLE}={requested!r} cannot run the {expected!r} runner"
        )
    configured.update(COMMON)
    configured.update(PHASES[expected])
    return configured


def enabled(expected, environ=None):
    """Whether this process is the requested crossover arm."""
    environ = os.environ if environ is None else environ
    return str(environ.get(ENVIRONMENT_VARIABLE, "")).strip().lower() == expected


def annotate_metadata(metadata, params):
    """Copy crossover provenance into per-run metadata when present."""
    tagged = dict(metadata)
    for key in ("protocol_crossover_phase", "protocol_crossover_calibration"):
        if key in params:
            tagged[key] = params[key]
    return tagged
