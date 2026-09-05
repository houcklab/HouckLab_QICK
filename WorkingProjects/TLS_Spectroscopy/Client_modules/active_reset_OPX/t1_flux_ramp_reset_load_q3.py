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


from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.analysis import (
    evaluate_t1_load_attribution,
)


METHODS = (
    "passive_1000",
    "park_hold_1000",
    "readout_x2_1000",
    "pi_readout_x2_1000",
    "active_1000",
)
METHOD_LABELS = {
    "passive_1000": "passive",
    "park_hold_1000": "park hold only",
    "readout_x2_1000": "park + 2 readouts",
    "pi_readout_x2_1000": "park + 2 pi/readouts",
    "active_1000": "true active reset",
}
METHOD_SCHEMES = {
    "passive_1000": "none",
    "park_hold_1000": "diagnostic_hold",
    "readout_x2_1000": "diagnostic_readout",
    "pi_readout_x2_1000": "diagnostic_pi_readout",
    "active_1000": "opx_unbounded",
}
DIAGNOSTIC_CYCLES = 2
DIAGNOSTIC_HOLD_US = 65.1
INTER_SHOT_DELAY_US = 1000.0
ROUNDS = 12
SHOTS_PER_POINT_PER_ROUND = 40
T1_DELAYS_US = np.asarray([1.0, 35.0, 100.0, 250.0, 750.0])
RANDOM_SEED = 20260905
T1_MATCH_RELATIVE_TOLERANCE = 0.15
P0_MATCH_ABSOLUTE_TOLERANCE = 0.12
P1_MATCH_ABSOLUTE_TOLERANCE = 0.12


def _method_config(method):
    method = str(method)
    if method not in METHOD_SCHEMES:
        raise ValueError(f"unknown T1 reset-load method {method!r}")
    return METHOD_SCHEMES[method], INTER_SHOT_DELAY_US


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
    return evaluate_t1_load_attribution(
        fits,
        round_fits,
        baseline_method="passive_1000",
        active_method="active_1000",
        staged_methods={
            "park_hold_1000": "park_dwell",
            "readout_x2_1000": "reset_readout_load",
            "pi_readout_x2_1000": "reset_pi_load",
        },
        max_relative_tau_difference=T1_MATCH_RELATIVE_TOLERANCE,
        max_abs_p0_difference=P0_MATCH_ABSOLUTE_TOLERANCE,
        max_abs_p1_difference=P1_MATCH_ABSOLUTE_TOLERANCE,
    )


def _plot(rows, fits, equivalence, path):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    colors = {method: f"C{index}" for index, method in enumerate(METHODS)}
    fig, axes = plt.subplots(1, 3, figsize=(17, 5.2))
    for method in METHODS:
        selected = [row for row in rows if row["method"] == method]
        x = np.asarray([row["delay_us"] for row in selected], dtype=float)
        y = np.asarray([row["excited_fraction"] for row in selected], dtype=float)
        low = np.asarray([row["excited_ci95_low"] for row in selected], dtype=float)
        high = np.asarray([row["excited_ci95_high"] for row in selected], dtype=float)
        axes[0].errorbar(
            x,
            y,
            yerr=(y - low, high - y),
            fmt="o",
            ms=3,
            capsize=2,
            color=colors[method],
            label=METHOD_LABELS[method],
        )
        if method in fits:
            fit = fits[method]
            dense = np.logspace(np.log10(x.min()), np.log10(x.max()), 400)
            fitted = fit["P0"] + (fit["P1"] - fit["P0"]) * np.exp(
                -dense / fit["tau_us"]
            )
            axes[0].plot(dense, fitted, color=colors[method])
        attempts = np.asarray(
            [row["mean_reset_attempts"] for row in selected], dtype=float
        )
        axes[2].plot(
            x,
            attempts,
            "o-",
            ms=3,
            color=colors[method],
            label=METHOD_LABELS[method],
        )
    fitted = [method for method in METHODS if method in fits]
    positions = np.arange(len(fitted))
    axes[1].bar(
        positions,
        [fits[method]["tau_us"] for method in fitted],
        yerr=[fits[method]["tau_err_us"] for method in fitted],
        capsize=4,
        color=[colors[method] for method in fitted],
        alpha=0.78,
    )
    for method, round_values in equivalence.get("comparisons", {}).items():
        for comparison in round_values.get("rounds", {}).values():
            if "active_tau_us" not in comparison:
                continue
            if method in fitted:
                axes[1].plot(
                    fitted.index(method),
                    comparison["active_tau_us"],
                    "ko",
                    ms=3,
                )
    axes[0].set(
        xscale="log",
        xlabel="T1 delay [us]",
        ylabel="Excited fraction",
        title=f"Reset-load attribution: {equivalence['diagnosis']}",
    )
    axes[1].set(
        ylabel="Fitted T1 [us]",
        title="Aggregate T1 and round fits",
    )
    axes[1].set_xticks(
        positions,
        [METHOD_LABELS[method] for method in fitted],
        rotation=20,
        ha="right",
    )
    axes[2].set(
        xscale="log",
        xlabel="T1 delay [us]",
        ylabel="Post-readout cycles",
        title="Applied reset load",
    )
    axes[0].legend(fontsize=8)
    axes[2].legend(fontsize=8)
    for axis in axes:
        axis.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def main():
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX import (
        t1_equivalence_q3 as benchmark,
    )

    benchmark.METHODS = METHODS
    benchmark.ROUNDS = ROUNDS
    benchmark.SHOTS_PER_POINT_PER_ROUND = SHOTS_PER_POINT_PER_ROUND
    benchmark.T1_DELAYS_US = T1_DELAYS_US
    benchmark.PASSIVE_RELAX_US = INTER_SHOT_DELAY_US
    benchmark.ACTIVE_RELAX_US = INTER_SHOT_DELAY_US
    benchmark.EXCURSION_GAIN = -20000.0
    benchmark.OUTPUT_TAG = "T1_flux_ramp_reset_load_paired"
    benchmark.T1_MATCH_RELATIVE_TOLERANCE = T1_MATCH_RELATIVE_TOLERANCE
    benchmark.P0_MATCH_ABSOLUTE_TOLERANCE = P0_MATCH_ABSOLUTE_TOLERANCE
    benchmark.P1_MATCH_ABSOLUTE_TOLERANCE = P1_MATCH_ABSOLUTE_TOLERANCE
    benchmark.RAISE_ON_FAILURE = False
    benchmark.OPX_OVERRIDES = dict(benchmark.OPX_OVERRIDES)
    benchmark.OPX_OVERRIDES.update({
        "opx_diagnostic_cycles": DIAGNOSTIC_CYCLES,
        "opx_diagnostic_hold_us": DIAGNOSTIC_HOLD_US,
    })
    benchmark._method_config = _method_config
    benchmark._schedule = _schedule
    benchmark._final_evaluation = _final_evaluation
    benchmark._plot = _plot
    benchmark.main()


if __name__ == "__main__":
    main()
