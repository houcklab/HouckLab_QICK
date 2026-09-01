"""Zero-span parity validation harness (spec 2026-06-01).

Composes ZeroSpanParity acquisition + analyze_ZeroSpanParity primitives into the
9-stage contrast/SNR validation chain. Strobe-only. Collate-only report.
"""
import os
import json
import datetime
from contextlib import contextmanager

import numpy as np
import h5py
import matplotlib.pyplot as plt

from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.utils import (
    modulated_strobe_acquire,
    find_two_tone_peaks,
)
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.analyze_ZeroSpanParity import (
    classify_parity_trace,
    verify_modulation,
    projected_histogram_snr,
    contrast_from_sweeps,
    dwell_time_statistics,
    sliding_window_switch_rate,
    bin_size_sweep,
    threshold_stability,
    detect_bursts,
)

# Default classifier for every stage that has to turn IQ into parity bits.
# "apriori_axis" (not "apriori"): these are driven steady-state traces, so both
# parity states sit on the same side of the g/e midpoint and midpoint
# thresholding labels the whole trace one state. See classify_parity_trace.
DEFAULT_CLASSIFIER = "apriori_axis"


def _classify(I, Q, separator, method=None):
    """Classify a trace, falling back to kmeans when no separator is available.

    Every stage used to hard-code method="apriori", which raises ValueError when
    separator is None -- and the orchestrator passes None whenever the run is
    configured for kmeans classification, so stages 3/7/8 crashed outright in that
    configuration.
    """
    if method is None:
        method = DEFAULT_CLASSIFIER
    if separator is None and method in ("apriori", "apriori_axis"):
        method = "kmeans"
    return classify_parity_trace(I, Q, separator=separator, method=method)


@contextmanager
def _preserve_cfg(experiment, *keys):
    """Snapshot the named cfg keys and unconditionally restore them on exit.

    Stages that sweep read_pulse_freq / parity_drive_freq / qubit_gain mutate
    experiment.cfg in a loop; without this an exception mid-sweep would leave
    the experiment parked at a swept value. set_qubit_gain is called explicitly
    by callers to rebuild the program after restoring the gain.
    """
    saved = {k: experiment.cfg.get(k) for k in keys}
    try:
        yield
    finally:
        experiment.cfg.update(saved)


def _timestamp():
    return datetime.datetime.now().strftime("%Y_%m_%d_%H_%M_%S")


ANALYSIS_VERSION = "1.0"


def _stage_sidecar(experiment, stage, scalars, arrays=None, extra_meta=None, out_dir=None):
    """Write a self-describing JSON (metadata + scalars) and an .h5 (raw arrays).

    Returns (json_path, h5_path). Arrays make every stage reprocessable offline.
    """
    cfg = getattr(experiment, "cfg", {})
    base_dir = out_dir or os.path.dirname(getattr(experiment, "fname", "") or ".") or "."
    base = os.path.join(base_dir, f"{stage}_{_timestamp()}")
    meta = {
        "stage": stage,
        "timestamp": datetime.datetime.now().isoformat(),
        "device": cfg.get("device"),
        "mode": cfg.get("mode", "strobe"),
        "sample_period_us": cfg.get("sample_period_us"),
        "reps": cfg.get("reps_per_chunk", cfg.get("reps")),
        "read_pulse_freq": cfg.get("read_pulse_freq"),
        "parity_drive_freq": cfg.get("parity_drive_freq"),
        "qubit_gain": cfg.get("qubit_gain"),
        "read_pulse_gain": cfg.get("pulse_gain"),
        "bin_us": (extra_meta or {}).get("bin_us"),
        "threshold": (extra_meta or {}).get("threshold"),
        # len(), not bool(): gap_indices arrives as an ndarray from the
        # acquisition modules, and bool() on an array raises "truth value of an
        # array is ambiguous" (including on an empty one, under numpy 2).
        "gap_indices_present": len(np.atleast_1d(
            (arrays or {}).get("gap_indices") if (arrays or {}).get("gap_indices")
            is not None else [])) > 0,
        "analysis_version": ANALYSIS_VERSION,
    }
    meta.update(extra_meta or {})
    meta["scalars"] = {k: (None if v is None else (float(v) if np.isscalar(v) and not isinstance(v, str) else v))
                       for k, v in scalars.items()}
    json_path = base + ".json"
    with open(json_path, "w") as fh:
        json.dump(meta, fh, indent=2, default=str)
    h5_path = base + ".h5"
    if arrays:
        with h5py.File(h5_path, "w") as f:
            for k, v in arrays.items():
                if v is None:
                    continue
                if k == "gap_indices":
                    f.create_dataset(k, data=np.asarray(list(v), dtype=int))
                elif (isinstance(v, (list, tuple)) and len(v)
                      and all(isinstance(x, (str, bytes, type(None))) for x in v)):
                    # e.g. chunk_wall_clock_starts: h5py cannot write numpy's '<U..'
                    # dtype, so encode as variable-length UTF-8.
                    f.create_dataset(
                        k, data=np.asarray([("" if x is None else str(x)) for x in v],
                                           dtype=h5py.string_dtype("utf-8")))
                else:
                    f.create_dataset(k, data=np.asarray(v))
            for mk, mv in meta.items():
                if mk == "scalars":
                    continue
                f.attrs[mk] = "" if mv is None else mv
    return json_path, h5_path


def _plot_modulation(scores, t_us, reference, vm, out_path):
    # No matplotlib.use() here (or anywhere in this module): use() switches the
    # backend for the whole session, so calling it inside a plot helper silently
    # disables every interactive plot in the runner from that point on. savefig +
    # close works on any backend.
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(t_us / 1e6, scores, lw=0.5, label="V(t) recovered")
    span = np.nanmax(scores) - np.nanmin(scores) if scores.size else 1.0
    ax.plot(t_us / 1e6, np.nanmin(scores) + reference * span, "r-", alpha=0.5,
            label="injected on/off")
    ax.set_xlabel("time (s)")
    ax.set_ylabel("projected V")
    ax.set_title(f"Modulation check  corr={vm['correlation']:.2f}  depth={vm['modulation_depth']:.2f}  snr={vm['snr']:.2f}")
    ax.legend(loc="best", fontsize=8)
    fig.tight_layout()
    fig.savefig(out_path, dpi=200)
    plt.close(fig)


def run_modulation_check(experiment, separator, modulation_freq_hz=25.0, n_periods=10,
                         progress=False, out_dir=None, classifier_method=None):
    """Stage 3: artificial square-wave modulation sanity gate.

    One block = one half-period (explicit factor of 2). Builds an alternating
    [G_on, 0] schedule, acquires, projects, and verifies recovery.
    """
    sp_us = float(experiment.cfg["sample_period_us"])
    g_on = experiment.cfg["qubit_gain"]
    reps_per_block = int(round(1.0 / (2.0 * modulation_freq_hz * sp_us * 1e-6)))
    reps_per_block = max(1, reps_per_block)
    actual_freq = 1.0 / (2.0 * reps_per_block * sp_us * 1e-6)
    schedule = [g_on, 0] * int(n_periods)
    acq = modulated_strobe_acquire(experiment, schedule, reps_per_block, progress=progress)
    cls = _classify(acq["I"], acq["Q"], separator, classifier_method)
    vm = verify_modulation(cls["scores"], acq["t_us"], acq["modulation_reference"],
                           gap_indices=acq["gap_indices"])
    # The schedule's true frequency, from the integer reps_per_block actually used.
    # verify_modulation also estimates it from the reference; keep BOTH so a
    # disagreement is visible rather than overwritten -- that disagreement is
    # exactly what exposed modulated_strobe_acquire silently running a different
    # block length than requested.
    vm["injected_freq_hz_estimated"] = vm.get("injected_freq_hz")
    vm["injected_freq_hz"] = actual_freq
    vm["reps_per_block"] = reps_per_block
    vm["samples_per_block_actual"] = int(acq["I"].size // max(len(schedule), 1))
    arrays = {"I": acq["I"], "Q": acq["Q"], "t_us": acq["t_us"],
              "scores": cls["scores"], "modulation_reference": acq["modulation_reference"],
              "gap_indices": acq["gap_indices"]}
    json_path, _ = _stage_sidecar(experiment, "3_modulation_check", scalars=vm, arrays=arrays,
                                  extra_meta={"reps_per_block": reps_per_block,
                                              "n_periods": n_periods,
                                              "modulation_freq_hz": actual_freq}, out_dir=out_dir)
    _plot_modulation(cls["scores"], acq["t_us"], acq["modulation_reference"], vm,
                     json_path.replace(".json", ".png"))
    return {**vm, "acq": acq, "classification": cls, "sidecar": json_path}


def _mean_complex_response(experiment, progress=False):
    data = experiment.acquire(progress=progress)
    return complex(np.mean(data["I"]) + 1j * np.mean(data["Q"]))


def _plot_contrast(c, out_path, xlabel="read_pulse_freq (MHz)"):
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(c["freqs"], np.abs(c["Z_on"]), label="|Z_on|")
    ax.plot(c["freqs"], np.abs(c["Z_off"]), label="|Z_off|")
    ax.plot(c["freqs"], c["contrast"], "k-", label="|Z_on - Z_off|")
    if np.isfinite(c["best_freq"]):
        ax.axvline(c["best_freq"], color="r", ls="--", label=f"best={c['best_freq']:.3f}")
    ax.set_xlabel(xlabel)
    ax.set_ylabel("response")
    # Stage 2 (contrast vs qubit freq) has no meaningful contrast SNR; only
    # annotate it when a finite value was actually computed (stage 1).
    snr = c.get("contrast_snr")
    if snr is not None and np.isfinite(snr):
        ax.set_title(f"Contrast  snr={snr:.2f}")
    else:
        ax.set_title("Contrast")
    ax.legend(loc="best", fontsize=8)
    fig.tight_layout()
    fig.savefig(out_path, dpi=200)
    plt.close(fig)


def run_static_contrast(experiment, freq_list, qubit_gain_on, progress=False, out_dir=None):
    """Stage 1: sweep read_pulse_freq, drive ON vs OFF, max |Z_on - Z_off|.

    Z = <I + iQ> averaged per point. NOT calibrated S21.
    Returns contrast_from_sweeps result; best_freq is the recommended read_pulse_freq.
    """
    freq_list = np.asarray(freq_list, dtype=float).ravel()
    Z_on = np.empty(freq_list.size, dtype=complex)
    Z_off = np.empty(freq_list.size, dtype=complex)
    base_gain = experiment.cfg["qubit_gain"]
    with _preserve_cfg(experiment, "read_pulse_freq", "qubit_gain"):
        for i, fr in enumerate(freq_list):
            experiment.cfg["read_pulse_freq"] = float(fr)
            experiment.set_qubit_gain(qubit_gain_on)
            Z_on[i] = _mean_complex_response(experiment, progress=progress)
            experiment.set_qubit_gain(0)
            Z_off[i] = _mean_complex_response(experiment, progress=progress)
    experiment.set_qubit_gain(base_gain)
    c = contrast_from_sweeps(freq_list, Z_on, Z_off)
    arrays = {"freqs": c["freqs"], "Z_on_real": c["Z_on"].real, "Z_on_imag": c["Z_on"].imag,
              "Z_off_real": c["Z_off"].real, "Z_off_imag": c["Z_off"].imag, "contrast": c["contrast"]}
    scalars = {"best_freq": c["best_freq"], "max_contrast": c["max_contrast"],
               "contrast_snr": c["contrast_snr"]}
    json_path, _ = _stage_sidecar(experiment, "1_static_contrast", scalars=scalars, arrays=arrays,
                                  out_dir=out_dir)
    _plot_contrast(c, json_path.replace(".json", ".png"))
    return {**c, "sidecar": json_path}


def run_contrast_vs_qubit_freq(experiment, qfreq_list, progress=False, out_dir=None):
    """Stage 2: contrast(f_q) = |<Z>_drive_on - <Z>_drive_off| vs qubit drive freq.

    No telegraph exists at each driven steady state, so DO NOT use histogram
    bimodality here -- use complex-response difference against a drive-off baseline.
    Run this at the resonator probe point already optimized by stage 1.
    """
    qfreq_list = np.asarray(qfreq_list, dtype=float).ravel()
    base_gain = experiment.cfg["qubit_gain"]
    with _preserve_cfg(experiment, "parity_drive_freq", "qubit_gain"):
        # drive-off baseline at current probe point
        experiment.set_qubit_gain(0)
        z_off = _mean_complex_response(experiment, progress=progress)
        contrast = np.empty(qfreq_list.size, dtype=float)
        z_on = np.empty(qfreq_list.size, dtype=complex)
        for i, fq in enumerate(qfreq_list):
            experiment.cfg["parity_drive_freq"] = float(fq)
            experiment.set_qubit_gain(base_gain)
            z_on[i] = _mean_complex_response(experiment, progress=progress)
            contrast[i] = abs(z_on[i] - z_off)
    experiment.set_qubit_gain(base_gain)
    peaks = find_two_tone_peaks(qfreq_list, contrast)
    arrays = {"qfreqs": qfreq_list, "contrast": contrast,
              "z_on_real": z_on.real, "z_on_imag": z_on.imag}
    scalars = {"z_off_real": z_off.real, "z_off_imag": z_off.imag,
               "peak_sep": peaks.get("peak_sep")}
    json_path, _ = _stage_sidecar(experiment, "2_contrast_vs_qubit_freq", scalars=scalars,
                                  arrays=arrays, out_dir=out_dir)
    _plot_contrast({"freqs": qfreq_list, "Z_on": z_on, "Z_off": np.full(qfreq_list.size, z_off),
                    "contrast": contrast,
                    "best_freq": float(qfreq_list[int(np.argmax(contrast))]) if contrast.size else np.nan,
                    "contrast_snr": np.nan},
                   json_path.replace(".json", ".png"), xlabel="parity_drive_freq (MHz)")
    return {"qfreqs": qfreq_list, "contrast": contrast, "z_on": z_on, "z_off": z_off,
            "peaks": peaks, "sidecar": json_path}


class CrossRunComparison:
    """Collect (swept_param, {metric: value}) across runs; emit table + plot.

    Used by stage 7 (run_environment_sweep) to record multiple metrics per
    environment setting, because readout power changes both measurement SNR and
    real parity dynamics. (Stages 5/6 have their own comparison shapes -- see
    run_bin_size_sweep / run_threshold_stability -- and stage 8 builds its own
    results dict.)
    """
    METRICS = ("switch_rate", "separation_snr", "mean_dwell", "mean_signal_level")

    def __init__(self, param_name):
        self.param_name = param_name
        self._rows = []

    def add(self, param_value, metrics):
        self._rows.append((param_value, dict(metrics)))

    def table(self):
        self._rows.sort(key=lambda r: r[0])
        out = {self.param_name: [r[0] for r in self._rows]}
        keys = set()
        for _, m in self._rows:
            keys.update(m.keys())
        for k in keys:
            out[k] = [r[1].get(k) for r in self._rows]
        return out

    def plot(self, out_path):
        tbl = self.table()
        metrics = [k for k in self.METRICS if k in tbl]
        fig, axes = plt.subplots(len(metrics), 1, figsize=(8, 2.4 * max(1, len(metrics))), sharex=True)
        if len(metrics) == 1:
            axes = [axes]
        x = tbl[self.param_name]
        for ax, k in zip(axes, metrics):
            ax.plot(x, tbl[k], "o-")
            ax.set_ylabel(k)
        axes[-1].set_xlabel(self.param_name)
        axes[0].set_title("Cross-run comparison")
        fig.tight_layout()
        fig.savefig(out_path, dpi=200)
        plt.close(fig)
        return out_path


def _trace_metrics(experiment, separator, window_us=1000.0, progress=False,
                   classifier_method=None):
    """Acquire one strobe trace, classify, return the 4 stage-7 metrics."""
    data = experiment.acquire(progress=progress)
    cls = _classify(data["I"], data["Q"], separator, classifier_method)
    # Debounce before BOTH derived quantities so the reported rate and the
    # reported dwell times describe the same bit sequence.
    from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.analyze_ZeroSpanParity import (
        _debounce_bits_segmented,
    )
    bits = _debounce_bits_segmented(cls["binary_states"],
                                    data.get("gap_indices"), 2)
    rate = sliding_window_switch_rate(bits, data["t_us"], window_us,
                                      gap_indices=data.get("gap_indices"))
    dw = dwell_time_statistics(bits, data["t_us"],
                               gap_indices=data.get("gap_indices"))
    h = projected_histogram_snr(cls["scores"])
    return {"switch_rate": float(np.mean(rate["rate_Hz"])) if rate["rate_Hz"].size else 0.0,
            "separation_snr": h["separation_snr"],
            "mean_dwell": 0.5 * (dw["mean_0"] + dw["mean_1"]),
            "mean_signal_level": float(np.mean(np.abs(data["I"] + 1j * data["Q"])))}


def run_environment_sweep(experiment, separator, param_name, param_values, set_param,
                          window_us=1000.0, progress=False, out_dir=None,
                          classifier_method=None):
    """Stage 7: vary an environment knob (power/detuning/drive-off), record 4 metrics each.

    set_param(experiment, value) applies the swept parameter (caller-provided so this
    stays decoupled from YOKO/attenuator/cfg specifics). Temperature is logged manually.
    """
    cmp = CrossRunComparison(param_name)
    for v in param_values:
        set_param(experiment, v)
        cmp.add(v, _trace_metrics(experiment, separator, window_us=window_us,
                                  progress=progress,
                                  classifier_method=classifier_method))
    tbl = cmp.table()
    json_path, _ = _stage_sidecar(experiment, f"7_environment_{param_name}",
                                  scalars={"n_points": len(param_values)},
                                  arrays=None, extra_meta={"table": tbl}, out_dir=out_dir)
    cmp.plot(json_path.replace(".json", ".png"))
    return {"table": tbl, "comparison": cmp, "sidecar": json_path}


def _signed_level(experiment, separator, progress=False, classifier_method=None):
    """Mean projected V relative to the separator midpoint, plus separation SNR."""
    data = experiment.acquire(progress=progress)
    cls = _classify(data["I"], data["Q"], separator, classifier_method)
    h = projected_histogram_snr(cls["scores"])
    return float(np.mean(cls["scores"])), h["separation_snr"]


def run_control_suite(experiment, separator, variants=("A", "B", "C", "D"), detune_mhz=50.0,
                      parity_freqs=None, progress=False, out_dir=None,
                      classifier_method=None):
    """Stage 8: A=drive off, B=detuned, C=probe off-res, D=swap branch (auto both).

    Contrast should vanish for A/B/C; assignment should reverse for D
    (branch_sign_flip True is the strong evidence).
    """
    cfg = experiment.cfg
    base = {"qubit_gain": cfg["qubit_gain"], "parity_drive_freq": cfg.get("parity_drive_freq"),
            "read_pulse_freq": cfg.get("read_pulse_freq")}
    results = {}

    with _preserve_cfg(experiment, "qubit_gain", "parity_drive_freq", "read_pulse_freq"):
        # drive-off reference for sign baseline
        experiment.set_qubit_gain(0)
        off_level, _ = _signed_level(experiment, separator, progress=progress, classifier_method=classifier_method)
        experiment.set_qubit_gain(base["qubit_gain"])

        if "A" in variants:
            experiment.set_qubit_gain(0)
            lvl, snr = _signed_level(experiment, separator, progress=progress, classifier_method=classifier_method)
            results["A"] = {"label": "drive_off", "mean_level": lvl, "separation_snr": snr}
            experiment.set_qubit_gain(base["qubit_gain"])
        if "B" in variants:
            experiment.cfg["parity_drive_freq"] = (base["parity_drive_freq"] or 0.0) + detune_mhz
            experiment.set_qubit_gain(base["qubit_gain"])
            lvl, snr = _signed_level(experiment, separator, progress=progress, classifier_method=classifier_method)
            results["B"] = {"label": "drive_detuned", "mean_level": lvl, "separation_snr": snr}
            experiment.cfg["parity_drive_freq"] = base["parity_drive_freq"]
        if "C" in variants:
            experiment.cfg["read_pulse_freq"] = (base["read_pulse_freq"] or 0.0) + detune_mhz
            lvl, snr = _signed_level(experiment, separator, progress=progress, classifier_method=classifier_method)
            results["C"] = {"label": "probe_off_resonance", "mean_level": lvl, "separation_snr": snr}
            experiment.cfg["read_pulse_freq"] = base["read_pulse_freq"]
        if "D" in variants:
            pf = parity_freqs or {"lower": base["parity_drive_freq"], "higher": base["parity_drive_freq"]}
            experiment.cfg["parity_drive_freq"] = float(pf["lower"])
            experiment.set_qubit_gain(base["qubit_gain"])
            lvl_lo, snr_lo = _signed_level(experiment, separator, progress=progress, classifier_method=classifier_method)
            experiment.cfg["parity_drive_freq"] = float(pf["higher"])
            lvl_hi, snr_hi = _signed_level(experiment, separator, progress=progress, classifier_method=classifier_method)
            sgn_lo = int(np.sign(lvl_lo - off_level))
            sgn_hi = int(np.sign(lvl_hi - off_level))
            results["D"] = {"label": "swap_branch", "mean_level_lower": lvl_lo, "mean_level_higher": lvl_hi,
                            "separation_snr_lower": snr_lo, "separation_snr_higher": snr_hi,
                            "sign_lower": sgn_lo, "sign_higher": sgn_hi,
                            "branch_sign_flip": bool(sgn_lo != sgn_hi)}
            experiment.cfg["parity_drive_freq"] = base["parity_drive_freq"]
    experiment.set_qubit_gain(base["qubit_gain"])

    json_path, _ = _stage_sidecar(experiment, "8_control_suite",
                                  scalars={"off_level": off_level},
                                  arrays=None, extra_meta={"variants": results}, out_dir=out_dir)
    return {"variants": results, "off_level": off_level, "sidecar": json_path}


# ---------------------------------------------------------------------------
# Stages 4, 5, 6 -- the telegraph itself and its two robustness checks.
#
# The three analysis primitives (projected_histogram_snr, bin_size_sweep,
# threshold_stability) already existed but nothing called them, so the evidence
# chain had a hole exactly where the telegraph gets characterised: stages 1-3
# proved the signal is parity-dependent and the pipeline works, stages 7-8 proved
# it responds to the environment and vanishes under controls, and nothing in
# between actually showed it was a two-level telegraph with an exponential dwell
# distribution.
# ---------------------------------------------------------------------------


def _plot_histogram(scores, h, out_path):
    fig, ax = plt.subplots(figsize=(7, 4))
    if h["hist"].size and h["bin_edges"].size:
        centers = 0.5 * (h["bin_edges"][:-1] + h["bin_edges"][1:])
        ax.plot(centers, h["hist"], drawstyle="steps-mid", lw=1.0)
    for c in np.atleast_1d(h["centers"]):
        if np.isfinite(c):
            ax.axvline(float(c), color="r", ls="--", lw=1)
    ax.set_xlabel("projected V")
    ax.set_ylabel("counts")
    ax.set_title(f"Telegraph histogram  sep_snr={h['separation_snr']:.2f}  "
                 f"dBIC={h['delta_bic']:.0f}  bimodal={h['is_bimodal']}")
    fig.tight_layout(); fig.savefig(out_path, dpi=200); plt.close(fig)


def _plot_trace_and_bits(scores, bits, t_us, out_path, max_pts=50_000):
    fig, axes = plt.subplots(2, 1, figsize=(10, 5), sharex=True)
    stride = max(1, int(np.ceil(scores.size / max_pts)))
    axes[0].plot(t_us[::stride] / 1e6, scores[::stride], lw=0.4)
    axes[0].set_ylabel("projected V")
    axes[1].step(t_us[::stride] / 1e6, bits[::stride], where="post", lw=0.5)
    axes[1].set_ylabel("parity state")
    axes[1].set_xlabel("time (s)")
    axes[0].set_title("Stage 4 telegraph")
    fig.tight_layout(); fig.savefig(out_path, dpi=200); plt.close(fig)


def run_telegraph(experiment, separator, window_us=1000.0, n_chunks=1,
                  progress=False, out_dir=None, classifier_method=None,
                  min_dwell_bins=2, k_sigma=5.0):
    """Stage 4: continuous acquisition -> projected trace -> bimodality test.

    Acquires one (optionally chunked) strobe record, projects it, and asks
    projected_histogram_snr whether the distribution is genuinely two-level.
    `is_bimodal` is deliberately conservative (delta_BIC > 0 AND
    separation_snr > 1.5 AND both weights in (0.1, 0.9)) because a 2-component
    GMM "finds" two peaks in almost anything.

    Also reports the switch rate, dwell statistics and any bursts, so the single
    reference trace everything else is compared against is fully characterised in
    one sidecar. No pass/fail -- the numbers go into the stage-9 report.
    """
    from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.utils import (
        chunked_acquire,
    )
    if int(n_chunks) > 1:
        data = chunked_acquire(experiment, n_chunks=int(n_chunks), progress=progress)
    else:
        data = experiment.acquire(progress=progress)

    cls = _classify(data["I"], data["Q"], separator, classifier_method)
    gaps = data.get("gap_indices")
    from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.analyze_ZeroSpanParity import (
        _debounce_bits_segmented,
    )
    bits = _debounce_bits_segmented(cls["binary_states"], gaps, min_dwell_bins)

    h = projected_histogram_snr(cls["scores"])
    rate = sliding_window_switch_rate(bits, data["t_us"], window_us, gap_indices=gaps)
    bursts = detect_bursts(rate["rate_Hz"], rate["window_t_us"], k_sigma=k_sigma,
                           window_us=rate["window_us"])
    dw = dwell_time_statistics(bits, data["t_us"], gap_indices=gaps)

    scalars = {
        "separation_snr": h["separation_snr"],
        "delta_bic": h["delta_bic"],
        "overlap": h["overlap"],
        "center_0": float(h["centers"][0]), "center_1": float(h["centers"][1]),
        "sigma_0": float(h["sigmas"][0]), "sigma_1": float(h["sigmas"][1]),
        "weight_0": float(h["weights"][0]), "weight_1": float(h["weights"][1]),
        "mean_rate_Hz": float(np.mean(rate["rate_Hz"])) if rate["rate_Hz"].size else 0.0,
        "median_rate_Hz": float(np.median(rate["rate_Hz"])) if rate["rate_Hz"].size else 0.0,
        "mean_dwell_0_us": dw["mean_0"], "mean_dwell_1_us": dw["mean_1"],
        "exp_fit_tau_0_us": dw["exp_fit_0"]["tau_us"],
        "exp_fit_tau_1_us": dw["exp_fit_1"]["tau_us"],
        "n_runs_0": dw["n_runs_0"], "n_runs_1": dw["n_runs_1"],
        "n_bursts": len(bursts),
        "n_samples": int(bits.size),
        # is_bimodal is a bool: keep it out of `scalars` (which float()s values)
        # and put it in the metadata instead.
    }
    arrays = {"I": data["I"], "Q": data["Q"], "t_us": data["t_us"],
              "scores": cls["scores"], "binary_states": bits,
              "window_t_us": rate["window_t_us"], "rate_Hz": rate["rate_Hz"],
              "dwell_0_us": dw["dwell_0_us"], "dwell_1_us": dw["dwell_1_us"],
              "gap_indices": gaps,
              # Per-chunk wall-clock stamps, when the record was chunked. t_us is
              # stitched as if the chunks were contiguous, so it UNDERSTATES real
              # elapsed time by the inter-chunk overhead. These stamps are the only
              # way to recover the true elapsed time (and hence an absolute
              # switch-rate-vs-wall-clock axis) after the fact.
              "chunk_wall_clock_starts": data.get("chunk_wall_clock_starts")}
    json_path, _ = _stage_sidecar(
        experiment, "4_telegraph", scalars=scalars, arrays=arrays,
        extra_meta={"is_bimodal": bool(h["is_bimodal"]),
                    "classifier_method": cls["method"],
                    "threshold": float(cls.get("threshold", 0.0)),
                    "window_us": rate["window_us"],
                    "min_dwell_bins": int(min_dwell_bins),
                    "n_chunks": int(n_chunks)},
        out_dir=out_dir)
    _plot_histogram(cls["scores"], h, json_path.replace(".json", ".png"))
    _plot_trace_and_bits(cls["scores"], bits, data["t_us"],
                         json_path.replace(".json", "_trace.png"))
    return {"histogram": h, "rate": rate, "dwell": dw, "bursts": bursts,
            "classification": cls, "data": data, "is_bimodal": bool(h["is_bimodal"]),
            "sidecar": json_path}


def _plot_bin_sweep(res, out_path):
    fig, axes = plt.subplots(2, 1, figsize=(7, 5), sharex=True)
    bins = np.asarray(res["bin_list_us"], dtype=float)
    axes[0].plot(bins, res["separation_snr_per_bin"], "o-")
    axes[0].set_ylabel("separation SNR")
    axes[1].plot(bins, res["exp_tau_per_bin"], "o-", label="exp fit tau")
    axes[1].plot(bins, res["mean_dwell_per_bin"], "s--", label="mean dwell")
    axes[1].set_ylabel("dwell (us)")
    axes[1].set_xlabel("analysis bin (us)")
    axes[1].legend(loc="best", fontsize=8)
    axes[0].set_xscale("log"); axes[1].set_xscale("log")
    axes[0].set_title(f"Stage 5 bin-size sweep  best={res['best_bin_us']:.0f} us")
    fig.tight_layout(); fig.savefig(out_path, dpi=200); plt.close(fig)


def run_bin_size_sweep(experiment, separator, bin_list_us=(100, 200, 500, 1000),
                       data=None, progress=False, out_dir=None,
                       classifier_method=None):
    """Stage 5: reprocess ONE raw trace at several analysis bin sizes.

    Pass `data` (e.g. the dict returned by run_telegraph) to reuse an existing
    record; otherwise a fresh trace is acquired. Reusing is preferable -- the point
    of this stage is that the SAME samples separate better or worse depending on
    the integration bin, which is only a clean statement within one record.

    Deliberately makes NO monotonic-then-degrade assertion: the optimum can occur
    well before the parity lifetime depending on SNR and switching rate. The shape
    is a qualitative signature for the stage-9 report to surface, not a test.
    """
    if data is None:
        data = experiment.acquire(progress=progress)
    method = classifier_method or DEFAULT_CLASSIFIER
    if separator is None and method in ("apriori", "apriori_axis"):
        method = "kmeans"
    res = bin_size_sweep(data["I"], data["Q"], data["t_us"], separator,
                         list(bin_list_us), gap_indices=data.get("gap_indices"),
                         method=method)
    scalars = {"best_bin_us": res["best_bin_us"]}
    for b, s, tau in zip(res["bin_list_us"], res["separation_snr_per_bin"],
                         res["exp_tau_per_bin"]):
        scalars[f"separation_snr_{int(b)}us"] = s
        scalars[f"exp_tau_{int(b)}us"] = tau
    json_path, _ = _stage_sidecar(
        experiment, "5_bin_size_sweep", scalars=scalars,
        arrays={"bin_list_us": np.asarray(res["bin_list_us"], dtype=float),
                "separation_snr_per_bin": np.asarray(res["separation_snr_per_bin"], dtype=float),
                "mean_dwell_per_bin": np.asarray(res["mean_dwell_per_bin"], dtype=float),
                "exp_tau_per_bin": np.asarray(res["exp_tau_per_bin"], dtype=float)},
        extra_meta={"classifier_method": method,
                    "bin_us": float(res["best_bin_us"])},
        out_dir=out_dir)
    _plot_bin_sweep(res, json_path.replace(".json", ".png"))
    return {**res, "sidecar": json_path}


def _plot_threshold_stability(res, out_path):
    fig, ax = plt.subplots(figsize=(7, 4))
    th = np.asarray(res["threshold_list"], dtype=float)
    ax.plot(th, res["tau0_per_threshold"], "o-", label="tau state 0")
    ax.plot(th, res["tau1_per_threshold"], "s-", label="tau state 1")
    ax.set_xlabel("threshold (projected V)")
    ax.set_ylabel("fitted tau (us)")
    ax.set_title(f"Stage 6 threshold stability  tau_cv={res['tau_cv']:.3f}")
    ax.legend(loc="best", fontsize=8)
    fig.tight_layout(); fig.savefig(out_path, dpi=200); plt.close(fig)


def run_threshold_stability(experiment, separator, data=None, threshold_list=None,
                            min_dwell_bins=2, progress=False, out_dir=None,
                            classifier_method=None):
    """Stage 6: is the fitted dwell time robust to where the threshold sits?

    Sweeps the classification threshold across the valley between the two levels
    and refits tau at each. A low `tau_cv` (coefficient of variation of tau across
    thresholds) means a real telegraph; a high one means the transitions are noise
    crossings that move with the threshold.

    The default grid is valley-centred, NOT percentile-based -- see
    analyze_ZeroSpanParity._default_threshold_grid for why percentiles invert this
    metric on exactly the well-separated data it is meant to reward.
    """
    if data is None:
        data = experiment.acquire(progress=progress)
    cls = _classify(data["I"], data["Q"], separator, classifier_method)
    res = threshold_stability(cls["scores"], data["t_us"],
                              threshold_list=threshold_list,
                              gap_indices=data.get("gap_indices"),
                              min_dwell_bins=min_dwell_bins)
    scalars = {"tau_cv": res["tau_cv"],
               "n_thresholds": len(res["threshold_list"])}
    json_path, _ = _stage_sidecar(
        experiment, "6_threshold_stability", scalars=scalars,
        arrays={"threshold_list": np.asarray(res["threshold_list"], dtype=float),
                "tau0_per_threshold": np.asarray(res["tau0_per_threshold"], dtype=float),
                "tau1_per_threshold": np.asarray(res["tau1_per_threshold"], dtype=float),
                "scores": cls["scores"]},
        extra_meta={"classifier_method": cls["method"],
                    "min_dwell_bins": int(min_dwell_bins)},
        out_dir=out_dir)
    _plot_threshold_stability(res, json_path.replace(".json", ".png"))
    return {**res, "sidecar": json_path}


_STAGE_ORDER = ["1_static_contrast", "2_contrast_vs_qubit_freq", "3_modulation_check",
                "4_telegraph", "5_bin_size_sweep", "6_threshold_stability",
                "7_environment", "8_control_suite"]


def build_evidence_report(run_dir, out_path):
    """Stage 9: collate per-stage sidecars into one markdown report. NO pass/fail.

    Scans run_dir for *.json sidecars, groups by stage prefix, embeds figures and
    scalar tables in canonical order. Flags stale analysis_version.
    """
    sidecars = []
    for fn in sorted(os.listdir(run_dir)):
        if fn.endswith(".json"):
            try:
                with open(os.path.join(run_dir, fn)) as fh:
                    meta = json.load(fh)
            except (ValueError, OSError):
                continue
            if "stage" in meta:
                meta["_file"] = fn
                sidecars.append(meta)

    def _order_key(m):
        for i, pref in enumerate(_STAGE_ORDER):
            if m["stage"].startswith(pref):
                return (i, m.get("timestamp", ""))
        return (len(_STAGE_ORDER), m.get("timestamp", ""))

    sidecars.sort(key=_order_key)
    lines = ["# Zero-Span Parity — Evidence Chain", "",
             f"_Collated from `{run_dir}` — no automated pass/fail; human judgment required._", ""]
    for m in sidecars:
        lines.append(f"## {m['stage']}")
        lines.append("")
        if m.get("analysis_version") != ANALYSIS_VERSION:
            lines.append(f"> ⚠ stale analysis_version {m.get('analysis_version')} "
                         f"(current {ANALYSIS_VERSION}) — consider re-analysis.")
            lines.append("")
        sc = m.get("scalars", {})
        if sc:
            lines.append("| metric | value |")
            lines.append("|---|---|")
            for k, v in sc.items():
                lines.append(f"| {k} | {v} |")
            lines.append("")
        png = os.path.join(run_dir, m["_file"].replace(".json", ".png"))
        if os.path.exists(png):
            lines.append(f"![{m['stage']}]({os.path.basename(png)})")
            lines.append("")
    with open(out_path, "w") as fh:
        fh.write("\n".join(lines))
    return out_path


if __name__ == "__main__":
    import tempfile
    # Headless test run: pick a non-interactive backend HERE, never at module or
    # function scope, so importing this module from a runner leaves the session's
    # interactive backend alone.
    import matplotlib
    matplotlib.use("Agg")

    class _StrobeFakeExp:
        """Fake ZeroSpanParity: acquire() returns a single IQ cloud shifted to
        level 5.0 when driven (gain>0), a cloud at 0.0 when off. Models the
        drive-on/off mean-response contrast used by the modulation and static-
        contrast stages — NOT parity telegraph (see _ParityFakeExp for that)."""
        def __init__(self, n, sp_us, out_dir):
            self.cfg = {"qubit_gain": 200, "reps_per_chunk": n, "reps": n,
                        "sample_period_us": sp_us, "read_pulse_freq": 100.0,
                        "parity_drive_freq": 4000.0, "device": "TEST", "mode": "strobe",
                        "pulse_gain": 300}
            self._sp = sp_us
            self._rng = np.random.default_rng(0)
            self.fname = os.path.join(out_dir, "fake.h5")

        @property
        def _n(self):
            """Sample count per acquire, from cfg -- like the real ZeroSpanParity.

            Must NOT be a fixed attribute: callers (modulated_strobe_acquire) change
            cfg['reps_per_chunk'] to set the block length, and a fake that ignores
            that cannot exercise the reps_per_block path at all.
            """
            return int(self.cfg["reps"])

        def set_qubit_gain(self, gain):
            self.cfg["qubit_gain"] = gain
            # Mirror ZeroSpanParity.set_qubit_gain: re-sync reps from reps_per_chunk
            # and rebuild, so a caller's reps_per_chunk override takes effect.
            if "reps_per_chunk" in self.cfg:
                self.cfg["reps"] = int(self.cfg["reps_per_chunk"])
        def acquire(self, progress=False):
            g = self.cfg["qubit_gain"]
            level = 5.0 if g > 0 else 0.0
            I = level + self._rng.normal(0, 0.8, self._n)
            Q = self._rng.normal(0, 0.8, self._n)
            t = np.arange(self._n) * self._sp
            return {"I": I, "Q": Q, "t_us": t, "mode": "strobe",
                    "sample_period_us": self._sp, "read_length_us": 5.0,
                    "wall_clock_start": "2026-01-01T00:00:00"}

    class _SpecFakeExp(_StrobeFakeExp):
        def acquire(self, progress=False):
            g = self.cfg["qubit_gain"]
            fq = self.cfg["parity_drive_freq"]
            # two "branches" at 3998 and 4002 -> larger response near them when driven
            resp = 0.0
            if g > 0:
                resp = 5.0 * (np.exp(-((fq - 3998.0) ** 2) / 0.5) + np.exp(-((fq - 4002.0) ** 2) / 0.5))
            I = resp + self._rng.normal(0, 0.5, self._n)
            Q = self._rng.normal(0, 0.5, self._n)
            t = np.arange(self._n) * self._sp
            return {"I": I, "Q": Q, "t_us": t, "mode": "strobe",
                    "sample_period_us": self._sp, "read_length_us": 5.0,
                    "wall_clock_start": "2026-01-01T00:00:00"}

    # --- Task 4: run_modulation_check ---
    sep = {"g_center": np.array([0.0, 0.0]), "e_center": np.array([5.0, 0.0])}
    with tempfile.TemporaryDirectory() as d:
        exp = _StrobeFakeExp(500, 20.0, d)
        res = run_modulation_check(exp, separator=sep, modulation_freq_hz=50.0, n_periods=4, out_dir=d)
        assert res["correlation"] > 0.8, res["correlation"]
        assert res["modulation_depth"] > 2.0, res["modulation_depth"]
        # sidecar written
        sidecars = [f for f in os.listdir(d) if f.startswith("3_modulation_check") and f.endswith(".json")]
        assert sidecars, "no modulation sidecar json written"
        with open(os.path.join(d, sidecars[0])) as fh:
            meta = json.load(fh)
        assert meta["stage"] == "3_modulation_check"
        assert meta["mode"] == "strobe"
    print("validate_ZeroSpanParity run_modulation_check: OK")

    # --- Task 6: run_static_contrast ---
    with tempfile.TemporaryDirectory() as d:
        exp = _StrobeFakeExp(200, 20.0, d)
        freq_list = np.linspace(95.0, 105.0, 11)
        res = run_static_contrast(exp, freq_list, qubit_gain_on=200, out_dir=d)
        assert res["contrast"].shape == (freq_list.size,), res["contrast"].shape
        assert np.all(np.isfinite(res["Z_on"])) and np.all(np.isfinite(res["Z_off"]))
        files = [f for f in os.listdir(d) if f.startswith("1_static_contrast")]
        assert any(f.endswith(".png") for f in files), "no contrast plot"
        assert any(f.endswith(".json") for f in files), "no contrast sidecar"
    print("validate_ZeroSpanParity run_static_contrast: OK")

    # --- Task 7: run_contrast_vs_qubit_freq ---
    with tempfile.TemporaryDirectory() as d:
        exp = _SpecFakeExp(200, 20.0, d)
        qf = np.linspace(3995.0, 4005.0, 51)
        res = run_contrast_vs_qubit_freq(exp, qf, out_dir=d)
        assert res["contrast"].shape == (qf.size,), res["contrast"].shape
        # the two branches should be the two strongest contrast points
        top2 = qf[np.argsort(res["contrast"])[-2:]]
        assert min(abs(top2 - 3998.0).min(), abs(top2 - 4002.0).min()) < 0.5, top2
    print("validate_ZeroSpanParity run_contrast_vs_qubit_freq: OK")

    # --- Task 11: CrossRunComparison ---
    cmp = CrossRunComparison(param_name="power_dB")
    cmp.add(-10, {"switch_rate": 100.0, "separation_snr": 5.0, "mean_dwell": 2000.0, "mean_signal_level": 4.0})
    cmp.add(-5, {"switch_rate": 200.0, "separation_snr": 4.0, "mean_dwell": 1000.0, "mean_signal_level": 4.1})
    tbl = cmp.table()
    assert tbl["power_dB"] == [-10, -5], tbl
    assert tbl["switch_rate"] == [100.0, 200.0], tbl
    with tempfile.TemporaryDirectory() as d:
        p = cmp.plot(os.path.join(d, "env.png"))
        assert os.path.exists(p)
    print("validate_ZeroSpanParity CrossRunComparison: OK")

    # --- Task 12: run_control_suite ---
    class _ParityFakeExp(_StrobeFakeExp):
        """Bimodal-telegraph fake: driving ON at a parity-doublet peak
        (3998/4002 MHz) yields a 50/50 mix of the g-cloud (0,0) and e-cloud
        (5,0) — the two separated states run_control_suite's separation_snr is
        meant to detect. Drive OFF or detuned off the peaks -> single g-cloud.
        This is what the drive-off (A) vs on-peak (D) control comparison needs;
        the plain _StrobeFakeExp only shifts a unimodal cloud and cannot
        exercise the ordering."""
        PEAKS = (3998.0, 4002.0)
        def acquire(self, progress=False):
            g = self.cfg["qubit_gain"]
            fq = self.cfg["parity_drive_freq"]
            on_peak = g > 0 and min(abs(fq - p) for p in self.PEAKS) < 0.5
            if on_peak:
                labels = self._rng.random(self._n) < 0.5
                I = np.where(labels, 5.0, 0.0) + self._rng.normal(0, 0.5, self._n)
                Q = self._rng.normal(0, 0.5, self._n)
            else:
                I = self._rng.normal(0, 0.5, self._n)
                Q = self._rng.normal(0, 0.5, self._n)
            t = np.arange(self._n) * self._sp
            return {"I": I, "Q": Q, "t_us": t, "mode": "strobe",
                    "sample_period_us": self._sp, "read_length_us": 5.0,
                    "wall_clock_start": "2026-01-01T00:00:00"}

    with tempfile.TemporaryDirectory() as d:
        exp = _ParityFakeExp(2000, 20.0, d)
        sep = {"g_center": np.array([0.0, 0.0]), "e_center": np.array([5.0, 0.0])}
        res = run_control_suite(exp, separator=sep,
                                variants=("A", "D"), detune_mhz=50.0,
                                parity_freqs={"lower": 3998.0, "higher": 4002.0},
                                out_dir=d)
        assert "A" in res["variants"] and "D" in res["variants"], res["variants"]
        # control A (drive off, unimodal) separation must be well below the
        # on-peak driven branch D (bimodal telegraph -> large separation).
        assert res["variants"]["A"]["separation_snr"] < res["variants"]["D"]["separation_snr_lower"], (
            res["variants"]["A"]["separation_snr"], res["variants"]["D"]["separation_snr_lower"])
        assert "branch_sign_flip" in res["variants"]["D"], res["variants"]["D"]
    print("validate_ZeroSpanParity run_control_suite: OK")

    # --- Task 13: build_evidence_report ---
    with tempfile.TemporaryDirectory() as d:
        for stage, sc in [("1_static_contrast", {"best_freq": 100.05, "contrast_snr": 8.0}),
                          ("3_modulation_check", {"correlation": 0.95, "modulation_depth": 4.0})]:
            with open(os.path.join(d, f"{stage}_2026_01_01_00_00_00.json"), "w") as fh:
                json.dump({"stage": stage, "timestamp": "t", "mode": "strobe",
                           "analysis_version": ANALYSIS_VERSION, "scalars": sc}, fh)
        report = build_evidence_report(d, os.path.join(d, "EVIDENCE.md"))
        assert os.path.exists(report)
        text = open(report).read()
        assert "1_static_contrast" in text and "3_modulation_check" in text
        assert "correlation" in text
    print("validate_ZeroSpanParity build_evidence_report: OK")

    # =====================================================================
    # Stages 4/5/6 (previously declared in _STAGE_ORDER but never implemented)
    # and the separator=None crash guard.
    # =====================================================================

    class _TelegraphFakeExp(_StrobeFakeExp):
        """Time-correlated two-level telegraph, i.e. what the real measurement
        looks like rather than an IID 50/50 mix.

        The state persists with a mean dwell of ~`tau_us`, and — crucially — both
        levels sit BELOW the g/e midpoint (0.8 and 1.4 on a g=0 / e=10 axis),
        because the zero-span drive produces a driven steady state, not a
        pi-pulsed |g>/|e> mixture. A midpoint-thresholding classifier sees one
        state here; the axis-plus-data-threshold classifier resolves both.
        """
        def __init__(self, n, sp_us, out_dir, tau_us=3000.0, noise=0.12, seed=5):
            super().__init__(n, sp_us, out_dir)
            self._rng = np.random.default_rng(seed)
            self._tau = tau_us
            self._noise = noise
            self._state = 0
        def acquire(self, progress=False):
            p = self._sp / self._tau
            bits = np.empty(self._n, dtype=int)
            for i in range(self._n):
                if self._rng.random() < p:
                    self._state ^= 1
                bits[i] = self._state
            lvl = np.where(bits == 1, 1.4, 0.8)
            I = lvl + self._rng.normal(0, self._noise, self._n)
            Q = self._rng.normal(0, self._noise, self._n)
            t = np.arange(self._n) * self._sp
            return {"I": I, "Q": Q, "t_us": t, "mode": "strobe",
                    "gap_indices": np.array([], dtype=int),
                    "sample_period_us": self._sp, "read_length_us": 30.0,
                    "wall_clock_start": "2026-01-01T00:00:00"}

    _sep_drv = {"g_center": np.array([0.0, 0.0]), "e_center": np.array([10.0, 0.0])}

    # --- Stage 4: run_telegraph ---
    with tempfile.TemporaryDirectory() as d:
        exp = _TelegraphFakeExp(40_000, 40.0, d, tau_us=3000.0)
        res4 = run_telegraph(exp, separator=_sep_drv, window_us=5000.0, out_dir=d)
        assert res4["is_bimodal"], (res4["histogram"]["delta_bic"],
                                    res4["histogram"]["separation_snr"],
                                    res4["histogram"]["weights"])
        assert res4["histogram"]["separation_snr"] > 2.0, res4["histogram"]["separation_snr"]
        # Dwell times must land near the injected 3 ms, both states populated.
        for _tau in (res4["dwell"]["exp_fit_0"]["tau_us"],
                     res4["dwell"]["exp_fit_1"]["tau_us"]):
            assert np.isfinite(_tau) and 1000.0 < _tau < 9000.0, _tau
        assert res4["dwell"]["n_runs_0"] > 3 and res4["dwell"]["n_runs_1"] > 3, res4["dwell"]
        files = os.listdir(d)
        assert any(f.startswith("4_telegraph") and f.endswith(".json") for f in files), files
        assert any(f.startswith("4_telegraph") and f.endswith(".png") for f in files), files
        assert any(f.startswith("4_telegraph") and f.endswith("_trace.png") for f in files), files
        assert any(f.startswith("4_telegraph") and f.endswith(".h5") for f in files), files
        with open(os.path.join(d, sorted(f for f in files if f.startswith("4_telegraph")
                                         and f.endswith(".json"))[0])) as fh:
            m4 = json.load(fh)
        assert m4["stage"] == "4_telegraph"
        assert m4["is_bimodal"] is True, m4
        assert m4["classifier_method"] == "apriori_axis", m4
        # A unimodal (drive-off) trace must NOT be called bimodal.
        exp_uni = _StrobeFakeExp(20_000, 40.0, d)
        exp_uni.set_qubit_gain(0)
        res4u = run_telegraph(exp_uni, separator=_sep_drv, window_us=5000.0, out_dir=d)
        assert not res4u["is_bimodal"], (res4u["histogram"]["delta_bic"],
                                         res4u["histogram"]["separation_snr"])
    print("validate_ZeroSpanParity run_telegraph (stage 4): OK")

    # --- Stage 5: run_bin_size_sweep, reusing the stage-4 record ---
    with tempfile.TemporaryDirectory() as d:
        exp = _TelegraphFakeExp(60_000, 20.0, d, tau_us=3000.0, noise=1.2, seed=9)
        data = exp.acquire()
        res5 = run_bin_size_sweep(exp, separator=_sep_drv,
                                  bin_list_us=(100, 200, 500, 1000),
                                  data=data, out_dir=d)
        assert np.isfinite(res5["best_bin_us"]), res5
        assert res5["best_bin_us"] in (100.0, 200.0, 500.0, 1000.0), res5["best_bin_us"]
        assert len(res5["separation_snr_per_bin"]) == 4, res5
        # Noise averages down with the bin, so a larger bin must not separate worse
        # than the smallest one here (no monotonic assertion beyond that).
        _snr = np.asarray(res5["separation_snr_per_bin"], dtype=float)
        assert np.nanmax(_snr) >= _snr[0], _snr
        files = os.listdir(d)
        assert any(f.startswith("5_bin_size_sweep") and f.endswith(".png") for f in files), files
    print("validate_ZeroSpanParity run_bin_size_sweep (stage 5): OK")

    # --- Stage 6: run_threshold_stability, clean vs noise ---
    with tempfile.TemporaryDirectory() as d:
        exp_clean = _TelegraphFakeExp(60_000, 40.0, d, tau_us=3000.0, noise=0.1, seed=3)
        res6 = run_threshold_stability(exp_clean, separator=_sep_drv, out_dir=d)
        assert np.isfinite(res6["tau_cv"]), res6
        # A real telegraph: tau must barely move as the threshold sweeps the valley.
        assert res6["tau_cv"] < 0.5, res6["tau_cv"]
        # Pure noise (drive off, unimodal) must look far less stable.
        exp_noise = _StrobeFakeExp(60_000, 40.0, d)
        exp_noise.set_qubit_gain(0)
        res6n = run_threshold_stability(exp_noise, separator=_sep_drv, out_dir=d)
        assert res6n["tau_cv"] > res6["tau_cv"], (res6n["tau_cv"], res6["tau_cv"])
        files = os.listdir(d)
        assert any(f.startswith("6_threshold_stability") and f.endswith(".png") for f in files), files
    print("validate_ZeroSpanParity run_threshold_stability (stage 6): OK")

    # --- separator=None must fall back to kmeans, not raise ------------------
    # Every stage used to hard-code method="apriori", which raises ValueError on a
    # None separator -- and the orchestrator passes None whenever the run is
    # configured for kmeans classification, so stages 3/7/8 crashed in that
    # configuration instead of clustering the trace.
    with tempfile.TemporaryDirectory() as d:
        exp = _TelegraphFakeExp(4_000, 40.0, d, tau_us=3000.0)
        cls_none = _classify(np.array([0.0, 1.0, 0.0, 1.0]),
                             np.array([0.0, 0.0, 0.0, 0.0]), None)
        assert cls_none["method"] == "kmeans", cls_none["method"]
        m = run_modulation_check(exp, separator=None, modulation_freq_hz=100.0,
                                 n_periods=3, out_dir=d)
        assert np.isfinite(m["correlation"]), m
        c = run_control_suite(exp, separator=None, variants=("A",), out_dir=d)
        assert "A" in c["variants"], c
        e = run_environment_sweep(exp, separator=None, param_name="probe_gain",
                                  param_values=[100, 200],
                                  set_param=lambda _e, v: _e.cfg.__setitem__("pulse_gain", v),
                                  window_us=5000.0, out_dir=d)
        assert len(e["table"]["probe_gain"]) == 2, e["table"]
    print("validate_ZeroSpanParity separator=None falls back to kmeans: OK")

    # --- build_evidence_report covers all 8 stages in canonical order ---------
    with tempfile.TemporaryDirectory() as d:
        for stage in _STAGE_ORDER:
            with open(os.path.join(d, f"{stage}_2026_01_01_00_00_00.json"), "w") as fh:
                json.dump({"stage": stage, "timestamp": "t", "mode": "strobe",
                           "analysis_version": ANALYSIS_VERSION,
                           "scalars": {"dummy": 1.0}}, fh)
        report = build_evidence_report(d, os.path.join(d, "EVIDENCE.md"))
        text = open(report).read()
        for stage in _STAGE_ORDER:
            assert stage in text, f"{stage} missing from the evidence report"
        # Canonical order, not alphabetical / filesystem order.
        positions = [text.index(s) for s in _STAGE_ORDER]
        assert positions == sorted(positions), positions
    print("validate_ZeroSpanParity evidence report covers stages 1-8: OK")
