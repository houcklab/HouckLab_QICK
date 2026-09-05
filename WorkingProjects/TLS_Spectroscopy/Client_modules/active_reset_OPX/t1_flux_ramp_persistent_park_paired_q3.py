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


from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX import (
    t1_flux_ramp_recovery_t1_q3 as recovery,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.analysis import (
    evaluate_paired_t1_recovery_sweep,
)


METHODS = (
    "passive_1000",
    "persistent_25",
    "persistent_100",
    "persistent_400",
    "per_shot_1000",
)
PERSISTENT_DELAYS_US = {
    "persistent_25": 25.0,
    "persistent_100": 100.0,
    "persistent_400": 400.0,
}
CANDIDATE_DELAYS_US = {
    **PERSISTENT_DELAYS_US,
    "per_shot_1000": 1000.0,
}
METHOD_LABELS = {
    "passive_1000": "reset off, per-shot park, 1000 us",
    "persistent_25": "reset on, persistent park, 25 us",
    "persistent_100": "reset on, persistent park, 100 us",
    "persistent_400": "reset on, persistent park, 400 us",
    "per_shot_1000": "reset on, per-shot park, 1000 us",
}
ROUNDS = 12
SHOTS_PER_POINT_PER_ROUND = 40
T1_DELAYS_US = np.asarray([1.0, 35.0, 100.0, 250.0, 750.0])
RANDOM_SEED = 20260905
T1_MATCH_RELATIVE_TOLERANCE = 0.15
P0_MATCH_ABSOLUTE_TOLERANCE = 0.08
P1_MATCH_ABSOLUTE_TOLERANCE = 0.08
MAX_HETEROGENEITY_I2 = 0.5


def _method_config(method):
    method = str(method)
    if method == "passive_1000":
        return "none", 1000.0
    if method in PERSISTENT_DELAYS_US:
        return "opx_unbounded", PERSISTENT_DELAYS_US[method]
    if method == "per_shot_1000":
        return "opx_unbounded", 1000.0
    raise ValueError(f"unknown persistent-park T1 method {method!r}")


def _method_overrides(method):
    return {"opx_persistent_park": str(method) in PERSISTENT_DELAYS_US}


def _schedule(delays):
    rng = np.random.default_rng(RANDOM_SEED)
    output = []
    for round_index in range(ROUNDS):
        for delay_index in rng.permutation(len(delays)):
            for method_index in rng.permutation(len(METHODS)):
                output.append(
                    (round_index, METHODS[int(method_index)], int(delay_index))
                )
    return output


def _final_evaluation(fits, round_fits):
    result = evaluate_paired_t1_recovery_sweep(
        fits,
        round_fits,
        candidate_delays_us=CANDIDATE_DELAYS_US,
        baseline_method="passive_1000",
        control_method="per_shot_1000",
        max_relative_tau_difference=T1_MATCH_RELATIVE_TOLERANCE,
        max_abs_p0_difference=P0_MATCH_ABSOLUTE_TOLERANCE,
        max_abs_p1_difference=P1_MATCH_ABSOLUTE_TOLERANCE,
        max_heterogeneity_i2=MAX_HETEROGENEITY_I2,
    )
    selected = next(
        (
            row for row in result["rows"]
            if row["method"] in PERSISTENT_DELAYS_US and row["passed"]
        ),
        None,
    )
    result["selected_method"] = None if selected is None else selected["method"]
    result["selected_active_relax_us"] = (
        None if selected is None else selected["active_relax_us"]
    )
    result["status"] = (
        "pass" if result["control_passed"] and selected is not None else "fail"
    )
    return result


def _plot(rows, fits, equivalence, path):
    recovery.METHODS = METHODS
    recovery.METHOD_LABELS = METHOD_LABELS
    recovery.T1_MATCH_RELATIVE_TOLERANCE = T1_MATCH_RELATIVE_TOLERANCE
    recovery._plot(rows, fits, equivalence, path)


def main():
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX import (
        t1_equivalence_q3 as benchmark,
    )

    benchmark.METHODS = METHODS
    benchmark.ROUNDS = ROUNDS
    benchmark.SHOTS_PER_POINT_PER_ROUND = SHOTS_PER_POINT_PER_ROUND
    benchmark.T1_DELAYS_US = T1_DELAYS_US
    benchmark.PASSIVE_RELAX_US = 1000.0
    benchmark.ACTIVE_RELAX_US = min(PERSISTENT_DELAYS_US.values())
    benchmark.EXCURSION_GAIN = -20000.0
    benchmark.OUTPUT_TAG = "T1_flux_ramp_persistent_park_paired"
    benchmark.T1_MATCH_RELATIVE_TOLERANCE = T1_MATCH_RELATIVE_TOLERANCE
    benchmark.P0_MATCH_ABSOLUTE_TOLERANCE = P0_MATCH_ABSOLUTE_TOLERANCE
    benchmark.P1_MATCH_ABSOLUTE_TOLERANCE = P1_MATCH_ABSOLUTE_TOLERANCE
    benchmark.RAISE_ON_FAILURE = False
    benchmark.RANDOM_SEED = RANDOM_SEED
    benchmark._method_config = _method_config
    benchmark._method_overrides = _method_overrides
    benchmark._schedule = _schedule
    benchmark._final_evaluation = _final_evaluation
    benchmark._plot = _plot
    benchmark.main()


if __name__ == "__main__":
    main()
