"""Zero-span parity validation harness (spec 2026-06-01).

Composes ZeroSpanParity acquisition + analyze_ZeroSpanParity primitives into the
9-stage contrast/SNR validation chain. Strobe-only. Collate-only report.
"""

import datetime
import json
import os
from contextlib import contextmanager

import h5py
import numpy as np

from qicklab.analysis.dwell import dwell_time_statistics
from qicklab.analysis.spectroscopy import find_two_tone_peaks
from qicklab.analysis.zero_span import classify_parity_trace, sliding_window_switch_rate
from qicklab.analysis.zero_span_checks import (
    batch_means_se,
    branch_response_test,
    complex_response_stats,
    contrast_from_sweeps,
    level_shift_null,
    projected_histogram_snr,
    verify_modulation,
)
from qicklab.core.acquisition import modulated_strobe_acquire


@contextmanager
def _preserve_cfg(experiment, *keys):
    """Snapshot the named cfg keys and unconditionally restore them on exit.

    Stages that sweep read_pulse_freq / parity_drive_freq / qubit_gain mutate
    experiment.cfg in a loop; without this an exception mid-sweep would leave
    the experiment parked at a swept value. A key absent at entry is removed again
    (not set to None). set_qubit_gain is called explicitly by callers to rebuild the
    program after restoring the gain.
    """
    saved = {k: experiment.cfg[k] for k in keys if k in experiment.cfg}
    try:
        yield
    finally:
        experiment.cfg.update(saved)
        for k in keys:
            if k not in saved:
                experiment.cfg.pop(k, None)


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
        "gap_indices_present": bool((arrays or {}).get("gap_indices")),
        "analysis_version": ANALYSIS_VERSION,
    }
    meta.update(extra_meta or {})
    meta["scalars"] = {
        k: (None if v is None else (float(v) if np.isscalar(v) and not isinstance(v, str) else v))
        for k, v in scalars.items()
    }
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
                else:
                    f.create_dataset(k, data=np.asarray(v))
            for mk, mv in meta.items():
                if mk == "scalars":
                    continue
                f.attrs[mk] = "" if mv is None else mv
    return json_path, h5_path


def _plot_modulation(scores, t_us, reference, vm, out_path):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(t_us / 1e6, scores, lw=0.5, label="V(t) recovered")
    span = np.nanmax(scores) - np.nanmin(scores) if scores.size else 1.0
    ax.plot(
        t_us / 1e6, np.nanmin(scores) + reference * span, "r-", alpha=0.5, label="injected on/off"
    )
    ax.set_xlabel("time (s)")
    ax.set_ylabel("projected V")
    ax.set_title(
        f"Modulation check  corr={vm['correlation']:.2f}  depth={vm['modulation_depth']:.2f}  snr={vm['snr']:.2f}"
    )
    ax.legend(loc="best", fontsize=8)
    fig.tight_layout()
    fig.savefig(out_path, dpi=200)
    plt.close(fig)


def run_modulation_check(
    experiment, separator, modulation_freq_hz=25.0, n_periods=10, progress=False, out_dir=None
):
    """Stage 3: artificial square-wave modulation sanity gate.

    One block = one half-period (explicit factor of 2). Builds an alternating
    [G_on, 0] schedule, acquires, projects, and verifies recovery. Both frequencies are
    in stitched sample time, which omits the dead time between block programs
    (docs/experiments/zero_span_parity.md#stage-3-modulation-timing). The drive gain
    G_on is restored (program rebuilt) afterwards; modulated_strobe_acquire leaves the
    last gain of the schedule, 0.
    """
    sp_us = float(experiment.cfg["sample_period_us"])
    g_on = experiment.cfg["qubit_gain"]
    reps_per_block = int(round(1.0 / (2.0 * modulation_freq_hz * sp_us * 1e-6)))
    reps_per_block = max(1, reps_per_block)
    actual_freq = 1.0 / (2.0 * reps_per_block * sp_us * 1e-6)
    schedule = [g_on, 0] * int(n_periods)
    try:
        acq = modulated_strobe_acquire(experiment, schedule, reps_per_block, progress=progress)
    finally:
        experiment.set_qubit_gain(g_on)
    # scores only (the threshold is unused): the separator projection
    cls = classify_parity_trace(acq["I"], acq["Q"], separator=separator, method="apriori_midpoint")
    vm = verify_modulation(
        cls["scores"], acq["t_us"], acq["modulation_reference"], gap_indices=acq["gap_indices"]
    )
    # injected_freq_hz stays the value measured from the reference transitions; nominal kept apart
    vm["nominal_modulation_freq_hz"] = actual_freq
    arrays = {
        "I": acq["I"],
        "Q": acq["Q"],
        "t_us": acq["t_us"],
        "scores": cls["scores"],
        "modulation_reference": acq["modulation_reference"],
        "gap_indices": acq["gap_indices"],
    }
    json_path, _ = _stage_sidecar(
        experiment,
        "3_modulation_check",
        scalars=vm,
        arrays=arrays,
        extra_meta={
            "reps_per_block": reps_per_block,
            "n_periods": n_periods,
            "modulation_freq_hz": actual_freq,
        },
        out_dir=out_dir,
    )
    _plot_modulation(
        cls["scores"],
        acq["t_us"],
        acq["modulation_reference"],
        vm,
        json_path.replace(".json", ".png"),
    )
    return {**vm, "acq": acq, "classification": cls, "sidecar": json_path}


def _complex_response_stats(experiment, n_blocks=20, progress=False):
    """One acquire(): (z_mean, se_I, se_Q, cov_IQ, n_batches), batch means over n_blocks
    contiguous blocks of the time-ordered record (complex_response_stats)."""
    data = experiment.acquire(progress=progress)
    return complex_response_stats(data["I"], data["Q"], n_blocks=n_blocks)


def _mean_complex_response(experiment, progress=False):
    return _complex_response_stats(experiment, progress=progress)[0]


def _plot_contrast(c, out_path, xlabel="read_pulse_freq (MHz)"):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(c["freqs"], np.abs(c["Z_on"]), label="|Z_on|")
    ax.plot(c["freqs"], np.abs(c["Z_off"]), label="|Z_off|")
    se = np.asarray(c.get("contrast_se", np.zeros(0)), dtype=float)
    if se.size == np.size(c["contrast"]) and np.isfinite(se).any():
        ax.errorbar(
            c["freqs"], c["contrast"], yerr=se, fmt="k-", capsize=2, label="|Z_on - Z_off| +- se"
        )
    else:
        ax.plot(c["freqs"], c["contrast"], "k-", label="|Z_on - Z_off|")
    if np.isfinite(c["best_freq"]):
        ax.axvline(c["best_freq"], color="r", ls="--", label=f"best={c['best_freq']:.3f}")
    ax.set_xlabel(xlabel)
    ax.set_ylabel("response")
    # Stage 2 (contrast vs qubit freq) has no meaningful contrast SNR; only
    # annotate it when a finite value was actually computed (stage 1).
    snr = c.get("contrast_snr")
    if snr is not None and np.isfinite(snr):
        if c.get("contrast_snr_method") == "standard_error":
            ax.set_title(
                f"Contrast  snr={snr:.2f} at best  (max {c['contrast_snr_max']:.2f}, "
                f"alpha={c['alpha']:g} threshold {c['contrast_snr_threshold']:.2f})"
            )
        else:
            ax.set_title(f"Contrast  peak/MAD={snr:.2f}")
    else:
        ax.set_title("Contrast")
    ax.legend(loc="best", fontsize=8)
    fig.tight_layout()
    fig.savefig(out_path, dpi=200)
    plt.close(fig)


def run_static_contrast(
    experiment, freq_list, qubit_gain_on, progress=False, out_dir=None, n_blocks=20
):
    """Stage 1: sweep read_pulse_freq, drive ON vs OFF, max |Z_on - Z_off|.

    Z = <I + iQ> averaged per point. NOT calibrated S21. Each point's standard error is from
    batch means over n_blocks contiguous blocks of its record (complex_response_stats);
    contrast_snr = |Z_on - Z_off| / se of the difference, at best_freq.
    Returns contrast_from_sweeps result; best_freq is the recommended read_pulse_freq.
    """
    freq_list = np.asarray(freq_list, dtype=float).ravel()
    Z_on = np.empty(freq_list.size, dtype=complex)
    Z_off = np.empty(freq_list.size, dtype=complex)
    se_on = np.full(freq_list.size, np.nan, dtype=complex)
    se_off = np.full(freq_list.size, np.nan, dtype=complex)
    cov_on = np.full(freq_list.size, np.nan)
    cov_off = np.full(freq_list.size, np.nan)
    n_batches = []
    base_gain = experiment.cfg["qubit_gain"]
    with _preserve_cfg(experiment, "read_pulse_freq", "qubit_gain"):
        for i, fr in enumerate(freq_list):
            experiment.cfg["read_pulse_freq"] = float(fr)
            experiment.set_qubit_gain(qubit_gain_on)
            Z_on[i], sI, sQ, cov_on[i], nb_on = _complex_response_stats(
                experiment, n_blocks=n_blocks, progress=progress
            )
            se_on[i] = complex(sI, sQ)
            experiment.set_qubit_gain(0)
            Z_off[i], sI, sQ, cov_off[i], nb_off = _complex_response_stats(
                experiment, n_blocks=n_blocks, progress=progress
            )
            se_off[i] = complex(sI, sQ)
            n_batches += [nb_on, nb_off]
    experiment.set_qubit_gain(base_gain)
    min_batches = min(n_batches) if n_batches else 0
    c = contrast_from_sweeps(
        freq_list,
        Z_on,
        Z_off,
        se_on=se_on,
        se_off=se_off,
        cov_on=cov_on,
        cov_off=cov_off,
        dof=(min_batches - 1) if min_batches >= 2 else np.nan,
    )
    c.update({"se_on": se_on, "se_off": se_off, "n_batches_min": min_batches})
    arrays = {
        "freqs": c["freqs"],
        "Z_on_real": c["Z_on"].real,
        "Z_on_imag": c["Z_on"].imag,
        "Z_off_real": c["Z_off"].real,
        "Z_off_imag": c["Z_off"].imag,
        "contrast": c["contrast"],
        "Z_on_se_real": se_on.real,
        "Z_on_se_imag": se_on.imag,
        "Z_off_se_real": se_off.real,
        "Z_off_se_imag": se_off.imag,
        "Z_on_cov_IQ": cov_on,
        "Z_off_cov_IQ": cov_off,
        "contrast_se": c["contrast_se"],
        "contrast_snr_per_point": c["contrast_snr_per_point"],
    }
    scalars = {
        "best_freq": c["best_freq"],
        "max_contrast": c["max_contrast"],
        "contrast_snr": c["contrast_snr"],
        "contrast_snr_method": c["contrast_snr_method"],
        "contrast_snr_max": c["contrast_snr_max"],
        "contrast_snr_threshold": c["contrast_snr_threshold"],
        "contrast_significant": c["contrast_significant"],
        "alpha": c["alpha"],
        "contrast_peak_to_mad": c["contrast_peak_to_mad"],
        "n_blocks": n_blocks,
        "n_batches_min": min_batches,
    }
    json_path, _ = _stage_sidecar(
        experiment, "1_static_contrast", scalars=scalars, arrays=arrays, out_dir=out_dir
    )
    _plot_contrast(c, json_path.replace(".json", ".png"))
    return {**c, "sidecar": json_path}


def run_contrast_vs_qubit_freq(experiment, qfreq_list, progress=False, out_dir=None, n_blocks=20):
    """Stage 2: contrast(f_q) = |<Z>_drive_on - <Z>_drive_off| vs qubit drive freq.

    No telegraph exists at each driven steady state, so DO NOT use histogram
    bimodality here -- use complex-response difference against a drive-off baseline.
    Run this at the resonator probe point already optimized by stage 1.
    Each z_on and the one z_off get batch-means standard errors (complex_response_stats);
    contrast_snr_per_point includes z_off's error, which is shared by every point (a
    correlated offset, not independent noise).
    """
    qfreq_list = np.asarray(qfreq_list, dtype=float).ravel()
    base_gain = experiment.cfg["qubit_gain"]
    with _preserve_cfg(experiment, "parity_drive_freq", "qubit_gain"):
        # drive-off baseline at current probe point
        experiment.set_qubit_gain(0)
        z_off, sI, sQ, cov_off, nb_off = _complex_response_stats(
            experiment, n_blocks=n_blocks, progress=progress
        )
        z_off_se = complex(sI, sQ)
        contrast = np.empty(qfreq_list.size, dtype=float)
        z_on = np.empty(qfreq_list.size, dtype=complex)
        z_on_se = np.full(qfreq_list.size, np.nan, dtype=complex)
        z_on_cov = np.full(qfreq_list.size, np.nan)
        n_batches = [nb_off]
        for i, fq in enumerate(qfreq_list):
            experiment.cfg["parity_drive_freq"] = float(fq)
            experiment.set_qubit_gain(base_gain)
            z_on[i], sI, sQ, z_on_cov[i], nb = _complex_response_stats(
                experiment, n_blocks=n_blocks, progress=progress
            )
            z_on_se[i] = complex(sI, sQ)
            n_batches.append(nb)
            contrast[i] = abs(z_on[i] - z_off)
    experiment.set_qubit_gain(base_gain)
    peaks = find_two_tone_peaks(qfreq_list, contrast)
    min_batches = min(n_batches)
    c = contrast_from_sweeps(
        qfreq_list,
        z_on,
        np.full(qfreq_list.size, z_off),
        se_on=z_on_se,
        se_off=z_off_se,
        cov_on=z_on_cov,
        cov_off=cov_off,
        dof=(min_batches - 1) if min_batches >= 2 else np.nan,
    )
    arrays = {
        "qfreqs": qfreq_list,
        "contrast": contrast,
        "z_on_real": z_on.real,
        "z_on_imag": z_on.imag,
        "z_on_se_real": z_on_se.real,
        "z_on_se_imag": z_on_se.imag,
        "z_on_cov_IQ": z_on_cov,
        "contrast_se": c["contrast_se"],
        "contrast_snr_per_point": c["contrast_snr_per_point"],
    }
    scalars = {
        "z_off_real": z_off.real,
        "z_off_imag": z_off.imag,
        "z_off_se_real": z_off_se.real,
        "z_off_se_imag": z_off_se.imag,
        "z_off_cov_IQ": cov_off,
        "peak_sep": peaks.get("peak_sep"),
        "n_blocks": n_blocks,
        "n_batches_min": min_batches,
    }
    json_path, _ = _stage_sidecar(
        experiment, "2_contrast_vs_qubit_freq", scalars=scalars, arrays=arrays, out_dir=out_dir
    )
    _plot_contrast(
        {
            "freqs": qfreq_list,
            "Z_on": z_on,
            "Z_off": np.full(qfreq_list.size, z_off),
            "contrast": contrast,
            "contrast_se": c["contrast_se"],
            "best_freq": float(qfreq_list[int(np.argmax(contrast))]) if contrast.size else np.nan,
            "contrast_snr": np.nan,
        },
        json_path.replace(".json", ".png"),
        xlabel="parity_drive_freq (MHz)",
    )
    return {
        "qfreqs": qfreq_list,
        "contrast": contrast,
        "z_on": z_on,
        "z_off": z_off,
        "z_on_se": z_on_se,
        "z_off_se": z_off_se,
        "contrast_se": c["contrast_se"],
        "contrast_snr_per_point": c["contrast_snr_per_point"],
        "peaks": peaks,
        "sidecar": json_path,
    }


class CrossRunComparison:
    """Collect (swept_param, {metric: value}) across runs; emit table + plot.

    Used by stage 7 (run_environment_sweep) to record multiple metrics per
    environment setting, because readout power changes both measurement SNR and
    real parity dynamics. (Stages 5/6 are declared in _STAGE_ORDER but not yet
    implemented here; stage 8 builds its own results dict.)
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
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        tbl = self.table()
        metrics = [k for k in self.METRICS if k in tbl]
        fig, axes = plt.subplots(
            len(metrics), 1, figsize=(8, 2.4 * max(1, len(metrics))), sharex=True
        )
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


def _trace_metrics(experiment, separator, window_us=1000.0, progress=False):
    """Acquire one strobe trace, classify, return the 4 stage-7 metrics.

    Bits come from the data-derived GMM threshold (classify_parity_trace "apriori_gmm");
    switch_rate and mean_dwell are NaN when the projected histogram is not bimodal.
    """
    data = experiment.acquire(progress=progress)
    cls = classify_parity_trace(data["I"], data["Q"], separator=separator, method="apriori_gmm")
    h = cls["histogram_fit"]
    bits = cls["binary_states"]
    if bits is None:
        switch_rate, mean_dwell = float("nan"), float("nan")
    else:
        rate = sliding_window_switch_rate(bits, data["t_us"], window_us)
        dw = dwell_time_statistics(bits, data["t_us"], merge_short_segments=True, min_dwell_bins=2)
        switch_rate = float(np.mean(rate["rate_Hz"])) if rate["rate_Hz"].size else 0.0
        mean_dwell = 0.5 * (dw["mean_0"] + dw["mean_1"])
    return {
        "switch_rate": switch_rate,
        "separation_snr": h["separation_snr"],
        "mean_dwell": mean_dwell,
        "mean_signal_level": float(np.mean(np.abs(data["I"] + 1j * data["Q"]))),
    }


def run_environment_sweep(
    experiment,
    separator,
    param_name,
    param_values,
    set_param,
    window_us=1000.0,
    progress=False,
    out_dir=None,
):
    """Stage 7: vary an environment knob (power/detuning/drive-off), record 4 metrics each.

    set_param(experiment, value) applies the swept parameter (caller-provided so this
    stays decoupled from YOKO/attenuator/cfg specifics). Temperature is logged manually.
    """
    cmp = CrossRunComparison(param_name)
    for v in param_values:
        set_param(experiment, v)
        cmp.add(v, _trace_metrics(experiment, separator, window_us=window_us, progress=progress))
    tbl = cmp.table()
    json_path, _ = _stage_sidecar(
        experiment,
        f"7_environment_{param_name}",
        scalars={"n_points": len(param_values)},
        arrays=None,
        extra_meta={"table": tbl},
        out_dir=out_dir,
    )
    cmp.plot(json_path.replace(".json", ".png"))
    return {"table": tbl, "comparison": cmp, "sidecar": json_path}


def _control_record(experiment, separator, n_blocks=1, progress=False):
    """Acquire n_blocks strobe records with the current program, stitch and classify them.

    Each block is one acquire() (reps_per_chunk samples); block k's
    t_us is offset to follow block k-1 by one sample spacing, so the stitched time omits
    the dead time between acquisitions. Returns the projected scores, t_us, the mean level
    and the histogram separation SNR.
    """
    I_parts, Q_parts, t_parts = [], [], []
    offset = 0.0
    for _ in range(max(1, int(n_blocks))):
        data = experiment.acquire(progress=progress)
        t_c = np.asarray(data["t_us"], dtype=float).ravel()
        I_parts.append(np.asarray(data["I"]).ravel())
        Q_parts.append(np.asarray(data["Q"]).ravel())
        t_parts.append(t_c - (t_c[0] if t_c.size else 0.0) + offset)
        if t_c.size:
            step = float(t_c[1] - t_c[0]) if t_c.size > 1 else 0.0
            offset = t_parts[-1][-1] + step
    I = np.concatenate(I_parts)
    Q = np.concatenate(Q_parts)
    # scores only (levels and their shifts; the threshold is unused): the separator projection
    cls = classify_parity_trace(I, Q, separator=separator, method="apriori_midpoint")
    h = projected_histogram_snr(cls["scores"])
    return {
        "scores": cls["scores"],
        "t_us": np.concatenate(t_parts),
        "mean_level": float(np.mean(cls["scores"])),
        "separation_snr": h["separation_snr"],
    }


def _control_blocks(cfg, min_record_us):
    """Acquisitions per control record so that the stitched record spans >= min_record_us."""
    reps = cfg.get("reps_per_chunk", cfg.get("reps"))
    sp_us = cfg.get("sample_period_us")
    if not reps or not sp_us or not min_record_us:
        return 1
    return max(1, int(np.ceil(float(min_record_us) / (int(reps) * float(sp_us)) - 1e-9)))


def run_control_suite(
    experiment,
    separator,
    variants=("A", "B", "C", "D"),
    detune_mhz=50.0,
    parity_freqs=None,
    progress=False,
    out_dir=None,
    k_sigma=3.0,
    se_batch_us=10000.0,
    min_batches=4,
    pe_drive=0.5,
    min_record_us=200000.0,
):
    """Stage 8: A=drive off, B=drive detuned, C=probe off-res, D=drive each branch in turn.

    Every variant rebuilds the program (set_qubit_gain) after its cfg change, and the base
    point is restored and rebuilt at the end, also when an acquisition raises. Each record is
    ceil(min_record_us / (reps_per_chunk * sample_period_us)) acquisitions of the current
    program, stitched. Levels are the mean projected score; each shift from the drive-off
    reference has a batch-means standard error (batches of se_batch_us, much longer than
    the parity dwell) and is tested against a Student-t critical value with the tail
    probability of a normal k_sigma (Welch dof).
    A, B: null_ok = |z| < t_crit. C: mean level and separation SNR only (the probe move
    shifts both clouds, so the drive-off reference does not apply).
    D: lower, higher and their midpoint; both_branches_respond, branch_ratio and
    complementarity (zero_span_checks.branch_response_test), midpoint_null_ok as for A/B.
    null_ok / both_branches_respond are None (insufficient_batches True) when a record holds
    fewer than min_batches batches. A variant whose frequencies are unset (None) is skipped
    with a reason. See docs/experiments/zero_span_parity.md#stage-8-instrument-controls.
    """
    cfg = experiment.cfg
    base = {
        "qubit_gain": cfg.get("qubit_gain"),
        "parity_drive_freq": cfg.get("parity_drive_freq"),
        "read_pulse_freq": cfg.get("read_pulse_freq"),
    }
    pf = parity_freqs or {}
    stat_kw = {"batch_us": se_batch_us, "k_sigma": k_sigma, "min_batches": min_batches}
    n_blocks = _control_blocks(cfg, min_record_us)
    e_minus_g = float(
        np.sum(
            (np.asarray(separator["e_center"], float) - np.asarray(separator["g_center"], float))
            ** 2
        )
    )
    results = {}

    def record():
        return _control_record(experiment, separator, n_blocks=n_blocks, progress=progress)

    try:
        with _preserve_cfg(experiment, "qubit_gain", "parity_drive_freq", "read_pulse_freq"):
            # drive-off reference for every shift
            experiment.set_qubit_gain(0)
            off = record()
            experiment.set_qubit_gain(base["qubit_gain"])

            if "A" in variants:
                experiment.set_qubit_gain(0)
                rec = record()
                results["A"] = {
                    "label": "drive_off",
                    "mean_level": rec["mean_level"],
                    "separation_snr": rec["separation_snr"],
                    **level_shift_null(rec, off, **stat_kw),
                }
                experiment.set_qubit_gain(base["qubit_gain"])
            if "B" in variants:
                if base["parity_drive_freq"] is None:
                    results["B"] = {"label": "drive_detuned", "skipped": "parity_drive_freq unset"}
                else:
                    experiment.cfg["parity_drive_freq"] = base["parity_drive_freq"] + detune_mhz
                    experiment.set_qubit_gain(base["qubit_gain"])
                    rec = record()
                    results["B"] = {
                        "label": "drive_detuned",
                        "mean_level": rec["mean_level"],
                        "separation_snr": rec["separation_snr"],
                        **level_shift_null(rec, off, **stat_kw),
                    }
                    experiment.cfg["parity_drive_freq"] = base["parity_drive_freq"]
            if "C" in variants:
                if base["read_pulse_freq"] is None:
                    results["C"] = {
                        "label": "probe_off_resonance",
                        "skipped": "read_pulse_freq unset",
                    }
                else:
                    experiment.cfg["read_pulse_freq"] = base["read_pulse_freq"] + detune_mhz
                    experiment.set_qubit_gain(base["qubit_gain"])
                    rec = record()
                    results["C"] = {
                        "label": "probe_off_resonance",
                        "mean_level": rec["mean_level"],
                        "separation_snr": rec["separation_snr"],
                    }
                    experiment.cfg["read_pulse_freq"] = base["read_pulse_freq"]
            if "D" in variants:
                f_lo, f_hi = pf.get("lower"), pf.get("higher")
                if f_lo is None or f_hi is None:
                    results["D"] = {
                        "label": "both_branches",
                        "skipped": "parity_freqs lower/higher unset",
                    }
                else:
                    f_lo, f_hi = float(f_lo), float(f_hi)
                    f_mid = 0.5 * (f_lo + f_hi)
                    recs = {}
                    for name, fq in (("lower", f_lo), ("higher", f_hi), ("midpoint", f_mid)):
                        experiment.cfg["parity_drive_freq"] = fq
                        experiment.set_qubit_gain(base["qubit_gain"])
                        recs[name] = record()
                    br = branch_response_test(
                        recs["lower"],
                        recs["higher"],
                        off,
                        e_minus_g=e_minus_g,
                        pe_drive=pe_drive,
                        **stat_kw,
                    )
                    mid = level_shift_null(recs["midpoint"], off, **stat_kw)
                    results["D"] = {
                        "label": "both_branches",
                        "parity_drive_freq_lower": f_lo,
                        "parity_drive_freq_higher": f_hi,
                        "parity_drive_freq_midpoint": f_mid,
                        "mean_level_lower": recs["lower"]["mean_level"],
                        "mean_level_higher": recs["higher"]["mean_level"],
                        "mean_level_midpoint": recs["midpoint"]["mean_level"],
                        "separation_snr_lower": recs["lower"]["separation_snr"],
                        "separation_snr_higher": recs["higher"]["separation_snr"],
                        **br,
                        "delta_midpoint": mid["delta"],
                        "delta_midpoint_se": mid["delta_se"],
                        "delta_midpoint_z": mid["delta_z"],
                        "delta_midpoint_dof": mid["delta_dof"],
                        "t_crit_midpoint": mid["t_crit"],
                        "midpoint_null_ok": mid["null_ok"],
                    }
                    experiment.cfg["parity_drive_freq"] = base["parity_drive_freq"]
    finally:
        # after _preserve_cfg has restored cfg: rebuild the base program, also when an
        # acquire raised mid-suite (the program would otherwise stay at a control point)
        experiment.set_qubit_gain(base["qubit_gain"])

    off_level, off_se, n_b = batch_means_se(off["scores"], off["t_us"], se_batch_us, min_batches)
    record_us = float(off["t_us"][-1] - off["t_us"][0]) if off["t_us"].size > 1 else 0.0
    json_path, _ = _stage_sidecar(
        experiment,
        "8_control_suite",
        scalars={"off_level": off_level, "off_level_se": off_se, "n_batches_off": n_b},
        arrays=None,
        extra_meta={
            "variants": results,
            "k_sigma": k_sigma,
            "se_batch_us": se_batch_us,
            "min_batches": min_batches,
            "pe_drive": pe_drive,
            "e_minus_g": e_minus_g,
            "min_record_us": min_record_us,
            "blocks_per_record": n_blocks,
            "record_us": record_us,
        },
        out_dir=out_dir,
    )
    return {
        "variants": results,
        "off_level": off_level,
        "off_level_se": off_se,
        "sidecar": json_path,
    }


_STAGE_ORDER = [
    "1_static_contrast",
    "2_contrast_vs_qubit_freq",
    "3_modulation_check",
    "4_telegraph",
    "5_bin_size_sweep",
    "6_threshold_stability",
    "7_environment",
    "8_control_suite",
]


def build_evidence_report(run_dir, out_path):
    """Stage 9: collate per-stage sidecars into one markdown report. NO pass/fail.

    Scans run_dir for *.json sidecars, groups by stage prefix, embeds figures and
    scalar tables in canonical order (plus the per-variant table of stage 8). Flags stale
    analysis_version.
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
    lines = [
        "# Zero-Span Parity — Evidence Chain",
        "",
        f"_Collated from `{run_dir}` — no automated pass/fail; human judgment required._",
        "",
    ]
    for m in sidecars:
        lines.append(f"## {m['stage']}")
        lines.append("")
        if m.get("analysis_version") != ANALYSIS_VERSION:
            lines.append(
                f"> ⚠ stale analysis_version {m.get('analysis_version')} "
                f"(current {ANALYSIS_VERSION}) — consider re-analysis."
            )
            lines.append("")
        sc = m.get("scalars", {})
        if sc:
            lines.append("| metric | value |")
            lines.append("|---|---|")
            for k, v in sc.items():
                lines.append(f"| {k} | {v} |")
            lines.append("")
        # stage 8 keeps its per-variant outcomes (null_ok, both_branches_respond,
        # branch_ratio +- se, complementarity +- se, ...) in "variants", not in scalars
        variants = m.get("variants")
        if isinstance(variants, dict) and variants:
            lines.append("| variant | metric | value |")
            lines.append("|---|---|---|")
            for name, res in variants.items():
                if not isinstance(res, dict):
                    continue
                for k, v in res.items():
                    if not isinstance(v, (dict, list)):
                        lines.append(f"| {name} | {k} | {v} |")
            lines.append("")
        png = os.path.join(run_dir, m["_file"].replace(".json", ".png"))
        if os.path.exists(png):
            lines.append(f"![{m['stage']}]({os.path.basename(png)})")
            lines.append("")
    with open(out_path, "w") as fh:
        fh.write("\n".join(lines))
    return out_path
