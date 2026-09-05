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
    evaluate_t1_flux_lifecycle,
)


METHODS = (
    "passive_1000",
    "passive_400",
    "active_1000",
    "active_400",
)
METHOD_CONFIGS = {
    "passive_1000": ("none", 1000.0),
    "passive_400": ("none", 400.0),
    "active_1000": ("opx_unbounded", 1000.0),
    "active_400": ("opx_unbounded", 400.0),
}
METHOD_LABELS = {
    "passive_1000": "reset off, 1000 us",
    "passive_400": "reset off, 400 us",
    "active_1000": "reset on, 1000 us",
    "active_400": "reset on, 400 us",
}
T1_MATCH_RELATIVE_TOLERANCE = 0.20
P0_MATCH_ABSOLUTE_TOLERANCE = 0.12
P1_MATCH_ABSOLUTE_TOLERANCE = 0.12


def _method_config(method):
    try:
        return METHOD_CONFIGS[str(method)]
    except KeyError as exc:
        raise ValueError(f"unknown T1 lifecycle method {method!r}") from exc


def _equivalence(fits):
    return evaluate_t1_flux_lifecycle(
        fits,
        max_relative_tau_difference=T1_MATCH_RELATIVE_TOLERANCE,
        max_abs_p0_difference=P0_MATCH_ABSOLUTE_TOLERANCE,
        max_abs_p1_difference=P1_MATCH_ABSOLUTE_TOLERANCE,
    )


def _plot(rows, fits, equivalence, path):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(13, 4.8))
    colors = {method: f"C{index}" for index, method in enumerate(METHODS)}
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
    fitted_methods = [method for method in METHODS if method in fits]
    tau = [fits[method]["tau_us"] for method in fitted_methods]
    tau_error = [fits[method]["tau_err_us"] for method in fitted_methods]
    axes[1].bar(
        np.arange(len(fitted_methods)),
        tau,
        yerr=tau_error,
        capsize=4,
        color=[colors[method] for method in fitted_methods],
    )
    axes[1].set_xticks(
        np.arange(len(fitted_methods)),
        [METHOD_LABELS[method] for method in fitted_methods],
        rotation=18,
        ha="right",
    )
    if "passive_1000" in fits:
        baseline = float(fits["passive_1000"]["tau_us"])
        axes[1].axhspan(
            baseline * (1.0 - T1_MATCH_RELATIVE_TOLERANCE),
            baseline * (1.0 + T1_MATCH_RELATIVE_TOLERANCE),
            color=colors["passive_1000"],
            alpha=0.12,
        )
    axes[0].set(
        xscale="log",
        xlabel="T1 delay [us]",
        ylabel="Excited fraction",
        title=f"Flux-ramp lifecycle: {equivalence['diagnosis']}",
    )
    axes[1].set(ylabel="Fitted T1 [us]", title="Factorial comparison")
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
    benchmark.ROUNDS = 2
    benchmark.SHOTS_PER_POINT_PER_ROUND = 150
    benchmark.T1_MIN_US = 1.0
    benchmark.T1_MAX_US = 750.0
    benchmark.T1_POINTS = 15
    benchmark.PASSIVE_RELAX_US = 1000.0
    benchmark.ACTIVE_RELAX_US = 400.0
    benchmark.EXCURSION_GAIN = -20000.0
    benchmark.OUTPUT_TAG = "T1_flux_ramp_lifecycle"
    benchmark.RAISE_ON_FAILURE = False
    benchmark._method_config = _method_config
    benchmark._equivalence = _equivalence
    benchmark._plot = _plot
    benchmark.main()


if __name__ == "__main__":
    main()
