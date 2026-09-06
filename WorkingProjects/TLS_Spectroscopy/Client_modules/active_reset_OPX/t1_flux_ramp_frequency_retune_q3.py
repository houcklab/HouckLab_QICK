import json
from pathlib import Path
import sys

import numpy as np


_root = Path(__file__).resolve()
for parent in _root.parents:
    if (parent / "WorkingProjects").is_dir():
        if str(parent) not in sys.path:
            sys.path.insert(0, str(parent))
        break
else:
    raise RuntimeError("Could not locate the HouckLab_QICK repository root")


QUBIT = "q3"
METHODS = (
    "passive_1000",
    "active_100",
    "active_25_default",
    "active_25_payload",
    "active_25_both",
)
METHOD_LABELS = {
    "passive_1000": "no reset, 1000 us",
    "active_100": "active reset, 100 us",
    "active_25_default": "active 25 us, base frequency",
    "active_25_payload": "active 25 us, payload retuned",
    "active_25_both": "active 25 us, payload/reset retuned",
}
DIAGNOSTIC_RESULT_PATH = None
BASELINE_FREQUENCY_MHZ = None
ACTIVE25_FREQUENCY_MHZ = None
T1_MATCH_RELATIVE_TOLERANCE = 0.15
P0_MATCH_ABSOLUTE_TOLERANCE = 0.12
P1_MATCH_ABSOLUTE_TOLERANCE = 0.12


def _latest_result(outer_folder):
    if DIAGNOSTIC_RESULT_PATH is not None:
        path = Path(DIAGNOSTIC_RESULT_PATH)
        if not path.is_file():
            raise FileNotFoundError(path)
        return path
    paths = list(
        (Path(outer_folder) / QUBIT).glob(
            f"{QUBIT}_*/{QUBIT}_*_active_reset_OPX_flux_cycle_spectroscopy/result.json"
        )
    )
    if not paths:
        raise FileNotFoundError("no completed flux-cycle spectroscopy result found")
    return max(paths, key=lambda path: path.stat().st_mtime)


def _load_frequencies(path):
    values = json.loads(Path(path).read_text())
    evaluation = values["evaluation"]
    if not bool(evaluation["active_100_control_passed"]):
        raise ValueError("active-100 spectroscopy control did not pass")
    if not bool(evaluation["short_shape_healthy"]):
        raise ValueError("short-cycle spectroscopy line is not healthy")
    fits = values["fits"]
    passive = fits["passive_1000"]
    active = fits["active_25"]
    if bool(passive.get("boundary_peak", False)) or bool(
        active.get("boundary_peak", False)
    ):
        raise ValueError("spectroscopy peak lies on the sweep boundary")
    frequencies = np.asarray(
        [passive["center_mhz"], active["center_mhz"]], dtype=float
    )
    if not np.all(np.isfinite(frequencies)):
        raise ValueError("spectroscopy centers must be finite")
    return tuple(float(value) for value in frequencies)


def _method_config(method):
    values = {
        "passive_1000": ("none", 1000.0),
        "active_100": ("opx_unbounded", 100.0),
        "active_25_default": ("opx_unbounded", 25.0),
        "active_25_payload": ("opx_unbounded", 25.0),
        "active_25_both": ("opx_unbounded", 25.0),
    }
    try:
        return values[str(method)]
    except KeyError as exc:
        raise ValueError(f"unknown frequency-retune method {method!r}") from exc


def _method_overrides(method):
    baseline = float(BASELINE_FREQUENCY_MHZ)
    active = float(ACTIVE25_FREQUENCY_MHZ)
    if not np.isfinite(baseline) or not np.isfinite(active):
        raise ValueError("diagnostic frequencies must be finite")
    values = {
        "passive_1000": (baseline, baseline),
        "active_100": (baseline, baseline),
        "active_25_default": (baseline, baseline),
        "active_25_payload": (active, baseline),
        "active_25_both": (active, active),
    }
    try:
        payload_frequency, reset_frequency = values[str(method)]
    except KeyError as exc:
        raise ValueError(f"unknown frequency-retune method {method!r}") from exc
    return {
        "qubit_pi_freq": float(payload_frequency),
        "reset_pi_freq": float(reset_frequency),
    }


def _final_evaluation(fits, round_fits):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.analysis import evaluate_t1_frequency_retune

    return evaluate_t1_frequency_retune(
        fits,
        max_relative_tau_difference=T1_MATCH_RELATIVE_TOLERANCE,
        max_abs_p0_difference=P0_MATCH_ABSOLUTE_TOLERANCE,
        max_abs_p1_difference=P1_MATCH_ABSOLUTE_TOLERANCE,
    )


def _plot(rows, fits, equivalence, path):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX import t1_flux_ramp_lifecycle_q3 as lifecycle

    lifecycle.METHODS = METHODS
    lifecycle.METHOD_LABELS = METHOD_LABELS
    lifecycle.T1_MATCH_RELATIVE_TOLERANCE = T1_MATCH_RELATIVE_TOLERANCE
    lifecycle._plot(rows, fits, equivalence, path)


def main():
    global BASELINE_FREQUENCY_MHZ, ACTIVE25_FREQUENCY_MHZ

    from WorkingProjects.TLS_Spectroscopy.Client_modules.Calib.initialize import outerFolder
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX import t1_equivalence_q3 as benchmark

    diagnostic_path = _latest_result(outerFolder)
    BASELINE_FREQUENCY_MHZ, ACTIVE25_FREQUENCY_MHZ = _load_frequencies(
        diagnostic_path
    )
    benchmark.METHODS = METHODS
    benchmark.ROUNDS = 8
    benchmark.SHOTS_PER_POINT_PER_ROUND = 40
    benchmark.T1_DELAYS_US = np.asarray([1.0, 35.0, 100.0, 250.0, 750.0])
    benchmark.PASSIVE_RELAX_US = 1000.0
    benchmark.ACTIVE_RELAX_US = 25.0
    benchmark.EXCURSION_GAIN = -20000.0
    benchmark.OUTPUT_TAG = "T1_flux_ramp_frequency_retune"
    benchmark.T1_MATCH_RELATIVE_TOLERANCE = T1_MATCH_RELATIVE_TOLERANCE
    benchmark.P0_MATCH_ABSOLUTE_TOLERANCE = P0_MATCH_ABSOLUTE_TOLERANCE
    benchmark.P1_MATCH_ABSOLUTE_TOLERANCE = P1_MATCH_ABSOLUTE_TOLERANCE
    benchmark.RAISE_ON_FAILURE = False
    benchmark._method_config = _method_config
    benchmark._method_overrides = _method_overrides
    benchmark._final_evaluation = _final_evaluation
    benchmark._plot = _plot
    benchmark.main()


if __name__ == "__main__":
    main()
