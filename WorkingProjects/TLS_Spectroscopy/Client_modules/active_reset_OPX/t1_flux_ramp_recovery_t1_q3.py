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
    evaluate_t1_recovery_sweep,
)


METHODS = (
    "passive_1000",
    "active_400",
    "active_600",
    "active_800",
    "active_1000",
)
ACTIVE_DELAYS_US = {
    "active_400": 400.0,
    "active_600": 600.0,
    "active_800": 800.0,
    "active_1000": 1000.0,
}
METHOD_LABELS = {
    "passive_1000": "reset off, 1000 us",
    "active_400": "reset on, 400 us",
    "active_600": "reset on, 600 us",
    "active_800": "reset on, 800 us",
    "active_1000": "reset on, 1000 us",
}
T1_MATCH_RELATIVE_TOLERANCE = 0.15
P0_MATCH_ABSOLUTE_TOLERANCE = 0.12
P1_MATCH_ABSOLUTE_TOLERANCE = 0.12


def _method_config(method):
    method = str(method)
    if method == "passive_1000":
        return "none", 1000.0
    if method in ACTIVE_DELAYS_US:
        return "opx_unbounded", ACTIVE_DELAYS_US[method]
    raise ValueError(f"unknown T1 recovery method {method!r}")


def _final_evaluation(fits, round_fits):
    return evaluate_t1_recovery_sweep(
        fits,
        round_fits,
        candidate_delays_us=ACTIVE_DELAYS_US,
        baseline_method="passive_1000",
        max_relative_tau_difference=T1_MATCH_RELATIVE_TOLERANCE,
        max_abs_p0_difference=P0_MATCH_ABSOLUTE_TOLERANCE,
        max_abs_p1_difference=P1_MATCH_ABSOLUTE_TOLERANCE,
    )


def _plot(rows, fits, equivalence, path):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    colors = {method: f"C{index}" for index, method in enumerate(METHODS)}
    fig, axes = plt.subplots(1, 2, figsize=(14, 5.2))
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
    rows_by_method = {row["method"]: row for row in equivalence.get("rows", [])}
    if "passive_1000" in fitted and rows_by_method:
        baseline_position = fitted.index("passive_1000")
        first = next(iter(rows_by_method.values()))
        for comparison in first["rounds"].values():
            if "passive_tau_us" in comparison:
                axes[1].plot(
                    baseline_position,
                    comparison["passive_tau_us"],
                    "ko",
                    ms=4,
                )
    for method, row in rows_by_method.items():
        if method not in fitted:
            continue
        position = fitted.index(method)
        for comparison in row["rounds"].values():
            if "active_tau_us" in comparison:
                axes[1].plot(position, comparison["active_tau_us"], "ko", ms=4)
    if "passive_1000" in fits:
        baseline = float(fits["passive_1000"]["tau_us"])
        axes[1].axhspan(
            baseline * (1.0 - T1_MATCH_RELATIVE_TOLERANCE),
            baseline * (1.0 + T1_MATCH_RELATIVE_TOLERANCE),
            color=colors["passive_1000"],
            alpha=0.10,
        )
    selected_delay = equivalence.get("selected_active_relax_us")
    selection = "none" if selected_delay is None else f"{selected_delay:g} us"
    axes[0].set(
        xscale="log",
        xlabel="T1 delay [us]",
        ylabel="Excited fraction",
        title=f"Flux-ramp reset recovery: {equivalence['status']}",
    )
    axes[1].set(
        ylabel="Fitted T1 [us]",
        title=f"Shortest round-stable recovery: {selection}",
    )
    axes[1].set_xticks(
        positions,
        [METHOD_LABELS[method] for method in fitted],
        rotation=18,
        ha="right",
    )
    axes[0].legend(fontsize=8)
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
    benchmark.ROUNDS = 3
    benchmark.SHOTS_PER_POINT_PER_ROUND = 150
    benchmark.T1_MIN_US = 1.0
    benchmark.T1_MAX_US = 750.0
    benchmark.T1_POINTS = 15
    benchmark.PASSIVE_RELAX_US = 1000.0
    benchmark.ACTIVE_RELAX_US = 400.0
    benchmark.EXCURSION_GAIN = -20000.0
    benchmark.OUTPUT_TAG = "T1_flux_ramp_recovery_T1"
    benchmark.T1_MATCH_RELATIVE_TOLERANCE = T1_MATCH_RELATIVE_TOLERANCE
    benchmark.P0_MATCH_ABSOLUTE_TOLERANCE = P0_MATCH_ABSOLUTE_TOLERANCE
    benchmark.P1_MATCH_ABSOLUTE_TOLERANCE = P1_MATCH_ABSOLUTE_TOLERANCE
    benchmark.RAISE_ON_FAILURE = False
    benchmark._method_config = _method_config
    benchmark._final_evaluation = _final_evaluation
    benchmark._plot = _plot
    benchmark.main()


if __name__ == "__main__":
    main()
