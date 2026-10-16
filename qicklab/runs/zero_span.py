"""Zero-span parity run: optional doublet/separator recalibration, validation stages 1-3
(feeding the probe and drive frequencies forward), acquisition, analysis, stages 8/7/9."""

import os

import numpy as np

from qicklab.analysis.spectroscopy import (
    MIN_PARTNER_SNR,
    fit_lorentzian_near_peak,
    pick_parity_drive_freq,
)
from qicklab.analysis.zero_span import SEPARATOR_METHODS, analyze_parity_run
from qicklab.core.acquisition import chunked_acquire
from qicklab.core.experiment import finish
from qicklab.experiments.qubit_spec import QubitSpecSliceFF
from qicklab.experiments.zero_span_parity import ZeroSpanParity
from qicklab.runs.single_shot import get_apriori_separator_from_singleshot
from qicklab.runs.zero_span_validation import (
    build_evidence_report,
    run_contrast_vs_qubit_freq,
    run_control_suite,
    run_environment_sweep,
    run_modulation_check,
    run_static_contrast,
)

# Stage-3 default gate: the block-means t statistic of the on/off level difference (see
# modulation_block_t). Each block is one half-period (reps_per_block samples, much longer than
# the parity correlation time), so its mean is ~independent; with n_periods = 10 the null is
# ~Student t with ~18 dof, P(|t| >= 5) ~ 1e-4. The per-sample snr / |correlation| scale with
# the single-shot separation, not with the record length, so they are recipe-only heuristics.
MODULATION_MIN_BLOCK_T = 5.0


def nearest_contrast_peak(
    s2,
    f0,
    max_shift_mhz,
    min_snr=MIN_PARTNER_SNR,
    n_se=2.0,
    which=None,
    expected_sep=None,
    sep_tol=None,
):
    """Stage-2 refinement of the parked line.

    Branch assignment. When which ("lower" / "higher") and the cached doublet splitting
    expected_sep are given and stage 2 found exactly two grid peaks whose separation is
    within sep_tol of expected_sep (default max(0.25 * expected_sep, 2 grid steps)), the
    parked line is the lower / higher of the two (info["doublet"] = "matched",
    info["assignment"] = "doublet_order"): the CW-readout shift is common to both lines, so
    the order holds for any common shift inside the span and the capture check against f0
    is not applied. Otherwise (info["doublet"] "mismatch" when expected_sep is known, else
    "unknown") the grid peak nearest f0 is used (info["assignment"] = "nearest"); that is
    the parked line, not its partner, only for a common shift below half the splitting.

    The assigned grid peak must have contrast_snr_per_point >= min_snr. Its centre is then
    refined below the grid step by a Lorentzian fit to s2["contrast"] within
    +/- max_shift_mhz of that grid peak (fit_lorentzian_near_peak: >= 6 points, R^2 and
    width gates). The fitted centre is adopted when it differs from f0 by more than n_se
    times its fit standard error (and, for a nearest assignment, lies within max_shift_mhz
    of f0); a shift consistent with zero leaves the line at f0.

    Returns (freq, snr, info): freq is the fitted centre when adopted, else None; snr is the
    assigned grid peak's contrast_snr_per_point (None when there is no peak); info holds
    grid_freq, fit_center, fit_se, doublet, assignment, stage2_sep (the two grid peaks'
    separation, else None), nearest_grid_freq and reason ("adopted", "no_peak", "low_snr",
    "fit_failed", "outside_capture" or "consistent_with_f0").
    """
    info = {
        "grid_freq": None,
        "fit_center": None,
        "fit_se": None,
        "reason": "no_peak",
        "doublet": "unknown",
        "assignment": None,
        "stage2_sep": None,
        "nearest_grid_freq": None,
    }
    freqs = np.asarray(s2["peaks"].get("peak_freqs", []), dtype=float).ravel()
    inds = np.asarray(s2["peaks"].get("peak_inds", []), dtype=int).ravel()
    known_sep = expected_sep is not None and np.isfinite(expected_sep) and expected_sep > 0
    if known_sep and which in ("lower", "higher"):
        info["doublet"] = "mismatch"
    if freqs.size == 0:
        return None, None, info
    if inds.size == freqs.size:  # find_two_tone_peaks sorts by frequency; make sure
        order = np.argsort(freqs)
        freqs, inds = freqs[order], inds[order]
    j = int(np.argmin(np.abs(freqs - f0)))
    info["nearest_grid_freq"] = float(freqs[j])
    if freqs.size == 2:
        info["stage2_sep"] = float(freqs[1] - freqs[0])
    if info["doublet"] == "mismatch" and freqs.size == 2:
        if sep_tol is None:
            q = np.asarray(s2.get("qfreqs", []), dtype=float).ravel()
            step = float(np.median(np.abs(np.diff(q)))) if q.size > 1 else 0.0
            sep_tol = max(0.25 * float(expected_sep), 2.0 * step)
        if abs(info["stage2_sep"] - float(expected_sep)) <= sep_tol:
            info["doublet"] = "matched"
    if info["doublet"] == "matched":
        j = 0 if which == "lower" else 1
        info["assignment"] = "doublet_order"
    else:
        info["assignment"] = "nearest"
    info["grid_freq"] = float(freqs[j])
    snr_pp = np.asarray(s2.get("contrast_snr_per_point", []), dtype=float).ravel()
    snr = float(snr_pp[inds[j]]) if inds.size > j and inds[j] < snr_pp.size else float("nan")
    if not (np.isfinite(snr) and snr >= min_snr):
        info["reason"] = "low_snr"
        return None, snr, info
    fit = fit_lorentzian_near_peak(
        np.asarray(s2.get("qfreqs", []), dtype=float),
        np.asarray(s2.get("contrast", []), dtype=float),
        freqs[j],
        max_shift_mhz,
    )
    if fit is None:
        info["reason"] = "fit_failed"
        return None, snr, info
    center = float(fit["center"])
    var = float(fit["pcov"][2, 2])
    se = float(np.sqrt(var)) if np.isfinite(var) and var >= 0 else float("nan")
    if not np.isfinite(se):
        info["reason"] = "fit_failed"
        return None, snr, info
    info.update(fit_center=center, fit_se=se)
    if info["assignment"] == "nearest" and abs(center - f0) > max_shift_mhz:
        info["reason"] = "outside_capture"
        return None, snr, info
    if abs(center - f0) <= n_se * se:
        info["reason"] = "consistent_with_f0"
        return None, snr, info
    info["reason"] = "adopted"
    return center, snr, info


def modulation_block_t(scores, reference, gap_indices):
    """Block-means t statistic of a stage-3 modulated record.

    The record is cut at gap_indices (the block starts after the first) into its on/off
    blocks; each block's mean score is one sample. Returns the Welch t of mean(on-block
    means) - mean(off-block means) (signed: positive = the drive moves the score toward e)
    with the block counts. NaN with fewer than 2 blocks of either kind.
    """
    scores = np.asarray(scores, dtype=float).ravel()
    ref = np.asarray(reference, dtype=float).ravel()
    n = min(scores.size, ref.size)
    cuts = [int(g) for g in gap_indices if 0 < int(g) < n]
    on, off = [], []
    for blk_s, blk_r in zip(np.split(scores[:n], cuts), np.split(ref[:n], cuts)):
        if blk_s.size:
            (on if blk_r[0] > 0.5 else off).append(float(np.mean(blk_s)))
    out = {"block_t": float("nan"), "n_on_blocks": len(on), "n_off_blocks": len(off)}
    if len(on) < 2 or len(off) < 2:
        return out
    diff = np.mean(on) - np.mean(off)
    se = np.sqrt(np.var(on, ddof=1) / len(on) + np.var(off, ddof=1) / len(off))
    if se > 0:
        out["block_t"] = float(diff / se)
    elif diff != 0:
        out["block_t"] = float(np.copysign(np.inf, diff))
    return out


def modulation_gate(m, params):
    """Stage-3 gate on a run_modulation_check result (plus m["block_t"]).

    Recipe thresholds params["min_block_t"] (on |block_t|), ["min_abs_correlation"],
    ["min_snr"] (per-sample heuristics): when the recipe sets any, exactly those are tested
    and enforced (the run raises before the main record). Otherwise the default is
    |block_t| >= MODULATION_MIN_BLOCK_T, flag only. A NaN statistic fails.
    """
    recipe = {
        k: float(params[k])
        for k in ("min_block_t", "min_abs_correlation", "min_snr")
        if params.get(k) is not None
    }
    enforced = bool(recipe)
    thresholds = recipe if enforced else {"min_block_t": MODULATION_MIN_BLOCK_T}
    values = {
        "min_block_t": abs(float(m.get("block_t", float("nan")))),
        "min_abs_correlation": abs(float(m["correlation"])),
        "min_snr": float(m["snr"]),
    }
    passed = all(bool(values[k] >= t) for k, t in thresholds.items())
    return {"passed": passed, "enforced": enforced, "thresholds": thresholds}


def run_zero_span_parity(ctx, p):
    zsp_outerFolder = ctx.outerFolder + "ZeroSpanParity/"
    os.makedirs(zsp_outerFolder, exist_ok=True)

    # stages 3/8/7 score the record on the separator projection (classify_parity_trace with
    # a separator method): kmeans has none, so fail fast before any acquisition
    _sep_stages = [
        f
        for f in ("Validate_ModulationCheck", "Validate_ControlSuite", "Validate_EnvironmentSweep")
        if p.get(f)
    ]
    if p["ZSP_AnalysisParams"]["classifier_method"] not in SEPARATOR_METHODS and _sep_stages:
        raise RuntimeError(
            f"[ZeroSpanParity] {', '.join(_sep_stages)} project the record on the g -> e "
            f"separator, but classifier_method="
            f"{p['ZSP_AnalysisParams']['classifier_method']!r} has none. Use "
            f"'apriori_gmm' or 'apriori_midpoint', or disable those flags."
        )

    if p["ZSP_RecalibrateParityFreqs"]:
        spec_cfg = ctx.working_config()
        spec_cfg["reps"] = p["ZSP_ParitySpec_params"]["reps"]
        spec_cfg["rounds"] = p["ZSP_ParitySpec_params"]["rounds"]
        spec_cfg["relax_delay"] = p["ZSP_ParitySpec_params"]["relax_delay"]
        spec_cfg["Gauss"] = p["ZSP_ParitySpec_params"]["Gauss"]
        spec_cfg["sigma"] = p["ZSP_ParitySpec_params"]["sigma"]
        spec_cfg["qubit_gain"] = p["ZSP_ParitySpec_params"]["gain"]
        spec_cfg["qubit_length"] = p["ZSP_ParitySpec_params"]["qubit_length"]
        spec_cfg["qubit_pulse_style"] = "const"
        spec_cfg["SpecSpan"] = p["ZSP_ParitySpec_params"]["SpecSpan"]
        spec_cfg["SpecNumPoints"] = p["ZSP_ParitySpec_params"]["SpecNumPoints"]
        spec_cfg["step"] = 2 * spec_cfg["SpecSpan"] / spec_cfg["SpecNumPoints"]
        spec_cfg["start"] = ctx.qubit_frequency_center - spec_cfg["SpecSpan"]
        spec_cfg["expts"] = spec_cfg["SpecNumPoints"]
        spec_cfg.setdefault("current_voltage", ctx.start_voltage)

        Instance_paritySpec = QubitSpecSliceFF(
            path="ZeroSpanParity_Spec",
            cfg=spec_cfg,
            soc=ctx.soc,
            soccfg=ctx.soccfg,
            outerFolder=zsp_outerFolder,
        )
        data_paritySpec = Instance_paritySpec.acquire()
        finish(
            QubitSpecSliceFF,
            Instance_paritySpec,
            data_paritySpec,
            reraise=True,
            plotDisp=False,
            figNum=2,
            min_sep=p["ZSP_ParitySpec_params"]["min_sep_MHz"],
            fit_window_mhz=p["ZSP_ParitySpec_params"]["fit_window_mhz"],
            prominent_ratio=p["ZSP_ParitySpec_params"]["prominent_ratio"],
        )

        chosen = pick_parity_drive_freq(
            data_paritySpec,
            which=p["ZSP_ParityFreqs_Cached"]["which_to_park"],
            min_sep_mhz=p["ZSP_ParitySpec_params"]["min_sep_MHz"],
            min_partner_snr=p["ZSP_ParitySpec_params"].get("min_partner_snr", MIN_PARTNER_SNR),
        )
        p["ZSP_ParityFreqs_Cached"]["lower_peak_MHz"] = chosen["lower"]
        p["ZSP_ParityFreqs_Cached"]["higher_peak_MHz"] = chosen["higher"]
        parity_drive_freq_MHz = chosen["picked"]
        # provenance for the saved cfg: which selection path produced the parked line
        parity_freq_source = chosen["source"]
        parity_peak_sep_MHz = chosen["peak_sep_MHz"]
        parity_partner_snr = chosen["partner_snr"]
        print(
            f"[ZeroSpanParity] parity doublet: lower={chosen['lower']:.6f} "
            f"higher={chosen['higher']:.6f} MHz; parking at "
            f"{p['ZSP_ParityFreqs_Cached']['which_to_park']} "
            f"({parity_drive_freq_MHz:.6f} MHz)"
        )
    else:
        which = p["ZSP_ParityFreqs_Cached"]["which_to_park"]
        parity_drive_freq_MHz = (
            p["ZSP_ParityFreqs_Cached"]["lower_peak_MHz"]
            if which == "lower"
            else p["ZSP_ParityFreqs_Cached"]["higher_peak_MHz"]
        )
        if parity_drive_freq_MHz is None:
            raise RuntimeError(
                "[ZeroSpanParity] No cached parity freq and "
                "ZSP_RecalibrateParityFreqs=False. Populate ZSP_ParityFreqs_Cached "
                "or set ZSP_RecalibrateParityFreqs=True."
            )
        parity_freq_source = "cached"
        parity_partner_snr = None
        _lo = p["ZSP_ParityFreqs_Cached"].get("lower_peak_MHz")
        _hi = p["ZSP_ParityFreqs_Cached"].get("higher_peak_MHz")
        parity_peak_sep_MHz = (
            abs(float(_hi) - float(_lo)) if _lo is not None and _hi is not None else None
        )

    if p["ZSP_RecalibrateSeparator"]:
        sep = get_apriori_separator_from_singleshot(ctx)
        p["ZSP_Separator_Cached"]["g_center"] = sep["g_center"]
        p["ZSP_Separator_Cached"]["e_center"] = sep["e_center"]
        p["ZSP_Separator_Cached"]["normal"] = sep["normal"]
        p["ZSP_Separator_Cached"]["midpoint"] = sep["midpoint"]
    elif p["ZSP_AnalysisParams"]["classifier_method"] in SEPARATOR_METHODS:
        # rule 7 (docs/experiments/zero_span_parity.md): cached fields must be shape (2,)
        for _k in ("g_center", "e_center", "normal", "midpoint"):
            _v = p["ZSP_Separator_Cached"][_k]
            if _v is None:
                raise RuntimeError(
                    f"[ZeroSpanParity §5.3 rule 7] ZSP_Separator_Cached['{_k}'] "
                    f"is None and classifier_method="
                    f"{p['ZSP_AnalysisParams']['classifier_method']!r}. Populate "
                    f"ZSP_Separator_Cached, set ZSP_RecalibrateSeparator=True, or "
                    f"use classifier_method='kmeans'."
                )
            _arr = np.asarray(_v, dtype=float)
            if _arr.shape != (2,):
                raise RuntimeError(
                    f"[ZeroSpanParity §5.3 rule 7] ZSP_Separator_Cached['{_k}'] "
                    f"has shape {_arr.shape}, expected (2,) — an (I, Q) "
                    f"coordinate."
                )
            p["ZSP_Separator_Cached"][_k] = _arr  # normalize to ndarray

    zsp_mode_params = (
        p["ZSP_StrobeParams"] if p["ZSP_RunMode"] == "strobe" else p["ZSP_DecimatedParams"]
    )
    zsp_qubit_gain = (
        p["ZSP_DriveParams"]["qubit_gain"]
        if p["ZSP_DriveParams"]["qubit_gain"] is not None
        else ctx.qubit_gain
    )
    zsp_pulse_gain = (
        p["ZSP_DriveParams"]["pulse_gain"]
        if p["ZSP_DriveParams"]["pulse_gain"] is not None
        else ctx.cavity_gain
    )
    cfg = ctx.working_config()
    zsp_cfg = {
        "res_ch": cfg["res_ch"],
        "qubit_ch": cfg["qubit_ch"],
        "ro_chs": cfg["ro_chs"],
        "nqz": cfg["nqz"],
        "qubit_nqz": cfg["qubit_nqz"],
        "mixer_freq": cfg["mixer_freq"],
        "read_pulse_freq": ctx.resonator_frequency_center,
        "parity_drive_freq": parity_drive_freq_MHz,
        "parity_freq_source": parity_freq_source,
        "parity_peak_sep_MHz": parity_peak_sep_MHz,
        "parity_partner_snr": parity_partner_snr,
        "qubit_gain": zsp_qubit_gain,
        "pulse_gain": zsp_pulse_gain,
        "res_phase": p["ZSP_DriveParams"]["res_phase"],
        "mode": p["ZSP_RunMode"],
        "start_src": p["ZSP_StartSrc"],
        **zsp_mode_params,
    }

    # the validation harness is strobe-only (set_qubit_gain raises in decimated mode): fail fast
    _validate_flags = (
        "Validate_StaticContrast",
        "Validate_ContrastVsQubitFreq",
        "Validate_ModulationCheck",
        "Validate_ControlSuite",
        "Validate_EnvironmentSweep",
    )
    if p["ZSP_RunMode"] != "strobe" and any(p.get(f) for f in _validate_flags):
        raise RuntimeError(
            f"[ZeroSpanParity] the validation harness (Validate_*) is strobe-only "
            f"but ZSP_RunMode={p['ZSP_RunMode']!r}. Set ZSP_RunMode='strobe' or "
            f"disable the Validate_* flags."
        )

    zsp_separator = (
        p["ZSP_Separator_Cached"]
        if p["ZSP_AnalysisParams"]["classifier_method"] in SEPARATOR_METHODS
        else None
    )

    # Stages 1-3 run BEFORE the main record, on their own instance, and feed it: stage 1
    # picks the probe, stage 2 refines the parked line under that CW readout, stage 3 is the
    # pipeline-sanity gate (docs/experiments/zero_span_parity.md#run-order-and-feedback).
    _val_out_dir = None
    if any(
        p.get(f)
        for f in (
            "Validate_StaticContrast",
            "Validate_ContrastVsQubitFreq",
            "Validate_ModulationCheck",
        )
    ):
        _pre = ZeroSpanParity(
            soc=ctx.soc,
            soccfg=ctx.soccfg,
            path="ZeroSpanParity",
            outerFolder=zsp_outerFolder,
            cfg=dict(zsp_cfg),
        )
        # the folder the main record's .h5 lands in (same path, same date)
        _val_out_dir = os.path.dirname(_pre.fname)

        if p.get("Validate_StaticContrast"):
            _f0 = zsp_cfg["read_pulse_freq"]
            _span = p["StaticContrast_params"]["freq_span_mhz"]
            _flist = np.linspace(
                _f0 - _span / 2, _f0 + _span / 2, p["StaticContrast_params"]["n_points"]
            )
            # set_qubit_gain rebuilds the strobe program from cfg["reps"]: set both keys for
            # stage 1 only, then restore them so stages 2-3 keep the run's reps_per_chunk
            _saved_reps = {k: _pre.cfg[k] for k in ("reps_per_chunk", "reps")}
            _pre.cfg["reps_per_chunk"] = p["StaticContrast_params"]["reps_per_point"]
            _pre.cfg["reps"] = p["StaticContrast_params"]["reps_per_point"]
            _sc = run_static_contrast(
                _pre, _flist, qubit_gain_on=zsp_cfg["qubit_gain"], out_dir=_val_out_dir
            )
            _pre.cfg.update(_saved_reps)
            print(
                f"[stage 1] best read_pulse_freq = {_sc['best_freq']:.4f} MHz  (contrast SNR "
                f"{_sc['contrast_snr']:.1f} at best, max {_sc['contrast_snr_max']:.1f} vs "
                f"{_sc['contrast_snr_threshold']:.1f} threshold: "
                f"significant={_sc['contrast_significant']})"
            )
            zsp_cfg["read_pulse_freq_nominal"] = _f0
            _best = float(_sc["best_freq"])
            # the SNR AT best_freq against the look-elsewhere threshold (NaN fails)
            _adopt = bool(
                np.isfinite(_best) and _sc["contrast_snr"] > _sc["contrast_snr_threshold"]
            )
            _moves = _adopt and _best != _f0
            _uses_sep = p["ZSP_AnalysisParams"]["classifier_method"] in SEPARATOR_METHODS
            if not _adopt:
                zsp_cfg["read_pulse_freq_source"] = "resonator_center"
                print(
                    "[stage 1] FLAG: contrast at best_freq not significant; keeping "
                    f"read_pulse_freq at the resonator centre ({_f0:.4f} MHz)"
                )
            elif _moves and _uses_sep and not p["ZSP_RecalibrateSeparator"]:
                # the cached g -> e axis was calibrated at the nominal probe: not valid at _best
                zsp_cfg["read_pulse_freq_source"] = "resonator_center_cached_separator"
                print(
                    f"[stage 1] FLAG: best_freq {_best:.4f} MHz not adopted: the cached "
                    "separator is only valid at the probe it was calibrated at. Set "
                    "ZSP_RecalibrateSeparator=True to re-derive it there."
                )
            else:
                if _moves and _uses_sep:
                    # re-derive the projection axis at the new probe (the I/Q frame and the
                    # g -> e difference vector both rotate with probe detuning)
                    sep = get_apriori_separator_from_singleshot(ctx, pulse_freq=_best)
                    for _k in ("g_center", "e_center", "normal", "midpoint"):
                        p["ZSP_Separator_Cached"][_k] = sep[_k]
                    zsp_cfg["separator_probe_freq"] = _best
                zsp_cfg["read_pulse_freq"] = _best
                zsp_cfg["read_pulse_freq_source"] = "stage1_static_contrast"
            _pre.cfg["read_pulse_freq"] = zsp_cfg["read_pulse_freq"]

        if p.get("Validate_ContrastVsQubitFreq"):
            _q0 = zsp_cfg["parity_drive_freq"]
            _qspan = p["ContrastVsQubit_params"]["qfreq_span_mhz"]
            _qlist = np.linspace(
                _q0 - _qspan / 2, _q0 + _qspan / 2, p["ContrastVsQubit_params"]["n_points"]
            )
            _s2 = run_contrast_vs_qubit_freq(_pre, _qlist, out_dir=_val_out_dir)
            print(f"[stage 2] parity peak sep = {_s2['peaks'].get('peak_sep')}")
            # the parked branch is the lower / higher of a stage-2 doublet matching the cached
            # splitting (any common shift inside the span); otherwise the nearest line, which
            # is the parked one (not its partner) only for a common shift below half the
            # splitting. Fit window / nearest capture: half the splitting, else min_sep_MHz
            _sep = zsp_cfg.get("parity_peak_sep_MHz")
            _max_shift = (
                float(_sep) / 2
                if _sep is not None and np.isfinite(_sep) and _sep > 0
                else p["ZSP_ParitySpec_params"]["min_sep_MHz"]
            )
            _peak, _peak_snr, _pinfo = nearest_contrast_peak(
                _s2,
                _q0,
                max_shift_mhz=_max_shift,
                min_snr=p["ContrastVsQubit_params"].get("min_peak_snr", MIN_PARTNER_SNR),
                which=p["ZSP_ParityFreqs_Cached"]["which_to_park"],
                expected_sep=_sep,
                sep_tol=p["ContrastVsQubit_params"].get("doublet_sep_tol_MHz"),
            )
            zsp_cfg["parity_drive_freq_unrefined"] = _q0
            zsp_cfg["parity_stage2_doublet"] = _pinfo["doublet"]
            zsp_cfg["parity_stage2_peak_sep_MHz"] = _pinfo["stage2_sep"]
            if _pinfo["doublet"] == "mismatch":
                print(
                    f"[stage 2] FLAG: stage-2 lines {list(np.round(_s2['peaks'].get('peak_freqs', []), 6))} "
                    f"do not match the cached doublet (splitting {float(_sep):.4f} MHz): branch "
                    f"assigned by the line nearest {_q0:.6f} MHz, which is the partner for a "
                    f"common shift > {float(_sep) / 2:.4f} MHz. Re-run the spectroscopy under the "
                    "CW readout."
                )
            elif (
                _pinfo["assignment"] == "doublet_order"
                and _pinfo["grid_freq"] != _pinfo["nearest_grid_freq"]
            ):
                print(
                    f"[stage 2] {p['ZSP_ParityFreqs_Cached']['which_to_park']} line assigned by "
                    f"doublet order ({_pinfo['grid_freq']:.6f} MHz); the line nearest "
                    f"{_q0:.6f} MHz is its partner (common shift > half the splitting)"
                )
            zsp_cfg["parity_drive_freq_stage2_snr"] = _peak_snr
            zsp_cfg["parity_drive_freq_refined"] = _peak is not None
            if _pinfo["fit_center"] is not None:
                zsp_cfg["parity_drive_freq_stage2_fit_center"] = _pinfo["fit_center"]
                zsp_cfg["parity_drive_freq_stage2_fit_se"] = _pinfo["fit_se"]
            if _peak is not None:
                zsp_cfg["parity_drive_freq"] = _peak
                print(
                    f"[stage 2] parity_drive_freq refined {_q0:.6f} -> {_peak:.6f} MHz "
                    f"(Lorentzian centre +/- {_pinfo['fit_se']:.6f} MHz)"
                )
            else:
                print(
                    f"[stage 2] FLAG: parity_drive_freq not refined ({_pinfo['reason']}; "
                    f"capture +/- {_max_shift:.4f} MHz of {_q0:.6f} MHz, nearest grid peak "
                    f"{_pinfo['grid_freq']}, fit centre {_pinfo['fit_center']}, min SNR "
                    f"{p['ContrastVsQubit_params'].get('min_peak_snr', MIN_PARTNER_SNR)})"
                )
            _pre.cfg["parity_drive_freq"] = zsp_cfg["parity_drive_freq"]

        if p.get("Validate_ModulationCheck"):
            _m = run_modulation_check(
                _pre,
                separator=zsp_separator,
                modulation_freq_hz=p["Modulation_params"]["modulation_freq_hz"],
                n_periods=p["Modulation_params"]["n_periods"],
                out_dir=_val_out_dir,
            )
            _bt = modulation_block_t(
                _m["classification"]["scores"],
                _m["acq"]["modulation_reference"],
                _m["acq"]["gap_indices"],
            )
            _m["block_t"] = _bt["block_t"]
            _gate = modulation_gate(_m, p["Modulation_params"])
            print(
                f"[stage 3] modulation corr={_m['correlation']:.2f} depth={_m['modulation_depth']:.2f} "
                f"snr={_m['snr']:.2f} block_t={_bt['block_t']:.2f} ({_bt['n_on_blocks']} on / "
                f"{_bt['n_off_blocks']} off blocks)  (gate {_gate['thresholds']}: "
                f"passed={_gate['passed']})"
            )
            zsp_cfg["modulation_correlation"] = float(_m["correlation"])
            zsp_cfg["modulation_snr"] = float(_m["snr"])
            zsp_cfg["modulation_block_t"] = _bt["block_t"]
            zsp_cfg["modulation_gate_passed"] = _gate["passed"]
            if not _gate["passed"]:
                if _gate["enforced"]:
                    raise RuntimeError(
                        f"[ZeroSpanParity stage 3] modulation not recovered "
                        f"(corr={_m['correlation']:.3f}, snr={_m['snr']:.3f}, "
                        f"block_t={_bt['block_t']:.3f}; recipe thresholds "
                        f"{_gate['thresholds']}): main record not taken"
                    )
                print("[stage 3] FLAG: modulation not recovered; do not trust the telegraph")

    # a fresh instance: the main program comes only from the chosen cfg
    zsp_exp = ZeroSpanParity(
        soc=ctx.soc,
        soccfg=ctx.soccfg,
        path="ZeroSpanParity",
        outerFolder=zsp_outerFolder,
        cfg=dict(zsp_cfg),
    )
    if p["ZSP_RunMode"] == "strobe" and p["ZSP_StrobeParams"]["n_chunks"] > 1:
        # sets zsp_exp.data to the stitched record, which save_data() below persists
        chunked_acquire(zsp_exp, n_chunks=p["ZSP_StrobeParams"]["n_chunks"], progress=True)
    else:
        zsp_exp.acquire(progress=True)
    zsp_exp.save_data()
    zsp_exp.save_config()

    # one run dir (beside the raw .h5) for analysis outputs and every validation sidecar
    _run_dir = os.path.dirname(zsp_exp.fname)

    analyze_parity_run(
        h5_path=zsp_exp.fname,
        separator=zsp_separator,
        window_us=p["ZSP_AnalysisParams"]["window_us"],
        k_sigma=p["ZSP_AnalysisParams"]["k_sigma"],
        classifier_method=p["ZSP_AnalysisParams"]["classifier_method"],
        step_us=p["ZSP_AnalysisParams"]["step_us"],
        min_burst_duration_us=p["ZSP_AnalysisParams"]["min_burst_duration_us"],
        analysis_bin_us=p["ZSP_AnalysisParams"]["analysis_bin_us"],
        save_plots=p["ZSP_AnalysisParams"]["save_plots"],
        out_dir=_run_dir,
    )
    print(f"[ZeroSpanParity] complete. Raw data: {zsp_exp.fname}")

    # stages 1-3 already wrote into the run's folder (it differs only across midnight)
    if _val_out_dir is None:
        _val_out_dir = _run_dir

    if p["Validate_ControlSuite"]:
        _pf = {
            "lower": p["ZSP_ParityFreqs_Cached"].get("lower_peak_MHz"),
            "higher": p["ZSP_ParityFreqs_Cached"].get("higher_peak_MHz"),
        }
        if zsp_cfg.get("parity_drive_freq_refined"):
            # control D drives the record's lines: the stage-2 (CW-readout Stark) shift of the
            # parked line applied to both cached pulsed-spectroscopy lines
            _shift = zsp_cfg["parity_drive_freq"] - zsp_cfg["parity_drive_freq_unrefined"]
            _pf = {k: (None if v is None else float(v) + _shift) for k, v in _pf.items()}
            print(f"[stage 8] control D lines shifted by the stage-2 refinement {_shift:+.6f} MHz")
        _c = run_control_suite(
            zsp_exp,
            separator=zsp_separator,
            variants=tuple(p["Control_params"]["variants"]),
            detune_mhz=p["Control_params"]["detune_mhz"],
            parity_freqs=_pf,
            out_dir=_val_out_dir,
        )
        print(
            f"[stage 8] controls: {[(k, v.get('separation_snr', v.get('separation_snr_lower'))) for k, v in _c['variants'].items()]}"
        )

    if p["Validate_EnvironmentSweep"]:

        def _set_power(_exp, _val):
            _exp.cfg["pulse_gain"] = (
                _val  # placeholder power knob: docs/experiments/zero_span_parity.md
            )
            _exp.prog = type(_exp.prog)(_exp.soccfg, _exp.cfg)

        _e = run_environment_sweep(
            zsp_exp,
            separator=zsp_separator,
            param_name=p["Environment_params"]["param_name"],
            param_values=p["Environment_params"]["values"],
            set_param=_set_power,
            out_dir=_val_out_dir,
        )
        print(f"[stage 7] swept {p['Environment_params']['param_name']}: {_e['table']}")

    if p["Build_EvidenceReport"]:
        _rep = build_evidence_report(_val_out_dir, os.path.join(_val_out_dir, "EVIDENCE.md"))
        print(f"[stage 9] evidence report written: {_rep}")
