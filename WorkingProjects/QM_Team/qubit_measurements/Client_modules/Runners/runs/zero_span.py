from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.utils import *
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mZeroSpanParity import ZeroSpanParity
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.analyze_ZeroSpanParity import analyze_parity_run
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.validate_ZeroSpanParity import (run_static_contrast, run_contrast_vs_qubit_freq, run_modulation_check, run_telegraph, run_bin_size_sweep, run_threshold_stability, run_control_suite, run_environment_sweep, build_evidence_report)
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mSpecSliceFF import QubitSpecSliceFF
import numpy as np
import matplotlib.pyplot as plt
import os
from .context import Context
from .calibration import get_apriori_separator_from_singleshot


def _load_saved_telegraph(zsp_outerFolder, run_dir):
    """Load the most recent saved stage-4 record, so stages 5/6 can reuse it.

    run_telegraph's sidecar .h5 carries the full I/Q/t_us/gap_indices (spec §4.7 --
    every stage reprocessable offline without re-acquiring), which is exactly what
    the bin-size and threshold sweeps need: they only reprocess samples.

    Searches the current run folder first, then older dated sibling folders.
    (ExperimentClass names folders by DATE, not datetime, so several runs on the
    same day share one folder.) Returns a data dict, or None if nothing is found.
    """
    import glob
    import h5py

    candidates = sorted(glob.glob(os.path.join(run_dir, "4_telegraph*.h5")),
                        key=os.path.getmtime, reverse=True)
    if not candidates:
        candidates = sorted(
            glob.glob(os.path.join(zsp_outerFolder, "ZeroSpanParity", "*",
                                   "4_telegraph*.h5")),
            key=os.path.getmtime, reverse=True)
    for path in candidates:
        try:
            with h5py.File(path, "r") as f:
                if not all(k in f for k in ("I", "Q", "t_us")):
                    continue
                data = {
                    "I": np.array(f["I"]), "Q": np.array(f["Q"]),
                    "t_us": np.array(f["t_us"]),
                    "gap_indices": ([int(g) for g in np.array(f["gap_indices"])]
                                    if "gap_indices" in f else []),
                }
                sp = f.attrs.get("sample_period_us")
        except (OSError, KeyError, ValueError):
            continue
        if sp is not None:
            data["sample_period_us"] = float(sp)
        dur_s = (float(data["t_us"][-1] - data["t_us"][0]) * 1e-6
                 if data["t_us"].size > 1 else 0.0)
        print(f"[stages 5/6] reusing the saved stage-4 record "
              f"{os.path.basename(path)} ({data['I'].size} samples, {dur_s:.3f} s, "
              f"{len(data['gap_indices'])} chunk gaps) -- no new acquisition. "
              f"Delete/rename it, or set Validate_Telegraph=True, to take a new one.")
        return data
    return None


def run_zero_span_parity(ctx, p):
    zsp_outerFolder = ctx.outerFolder + "ZeroSpanParity/"
    os.makedirs(zsp_outerFolder, exist_ok=True)

    # ---- Step 1: optional parity-doublet frequency pre-calibration ----------
    if p["ZSP_RecalibrateParityFreqs"]:
        cfg = ctx.working_config()
        spec_cfg = cfg.copy()
        spec_cfg["reps"]              = p["ZSP_ParitySpec_params"]["reps"]
        spec_cfg["rounds"]            = p["ZSP_ParitySpec_params"]["rounds"]
        spec_cfg["relax_delay"]       = p["ZSP_ParitySpec_params"]["relax_delay"]
        spec_cfg["Gauss"]             = p["ZSP_ParitySpec_params"]["Gauss"]
        spec_cfg["sigma"]             = p["ZSP_ParitySpec_params"]["sigma"]
        spec_cfg["qubit_gain"]        = p["ZSP_ParitySpec_params"]["gain"]
        spec_cfg["qubit_length"]      = p["ZSP_ParitySpec_params"]["qubit_length"]
        spec_cfg["qubit_pulse_style"] = "const"
        spec_cfg["SpecSpan"]          = p["ZSP_ParitySpec_params"]["SpecSpan"]
        spec_cfg["SpecNumPoints"]     = p["ZSP_ParitySpec_params"]["SpecNumPoints"]
        spec_cfg["step"]  = 2 * spec_cfg["SpecSpan"] / spec_cfg["SpecNumPoints"]
        spec_cfg["start"] = ctx.qubit_frequency_center - spec_cfg["SpecSpan"]
        spec_cfg["expts"] = spec_cfg["SpecNumPoints"]
        spec_cfg.setdefault("current_voltage", ctx.start_voltage)

        Instance_paritySpec = QubitSpecSliceFF(
            path="ZeroSpanParity_Spec", cfg=spec_cfg,
            soc=ctx.soc, soccfg=ctx.soccfg, outerFolder=zsp_outerFolder)
        data_paritySpec = Instance_paritySpec.acquire()
        Instance_paritySpec.display(
            data_paritySpec, plotDisp=False, figNum=2,
            min_sep=p["ZSP_ParitySpec_params"]["min_sep_MHz"],
            fit_window_mhz=p["ZSP_ParitySpec_params"]["fit_window_mhz"],
            prominent_ratio=p["ZSP_ParitySpec_params"]["prominent_ratio"])
        Instance_paritySpec.save_data(data_paritySpec)
        Instance_paritySpec.save_config()

        # Reuse the SAME min_sep the spec fit above used, so "resolved doublet"
        # means one thing across the fit and the peak pick.
        chosen = pick_parity_drive_freq(
            data_paritySpec, which=p["ZSP_ParityFreqs_Cached"]["which_to_park"],
            min_sep_mhz=p["ZSP_ParitySpec_params"]["min_sep_MHz"])
        p["ZSP_ParityFreqs_Cached"]["lower_peak_MHz"]  = chosen["lower"]
        p["ZSP_ParityFreqs_Cached"]["higher_peak_MHz"] = chosen["higher"]
        parity_drive_freq_MHz = chosen["picked"]
        print(f"[ZeroSpanParity] parity doublet: lower={chosen['lower']:.6f} "
              f"higher={chosen['higher']:.6f} MHz; parking at "
              f"{p['ZSP_ParityFreqs_Cached']['which_to_park']} "
              f"({parity_drive_freq_MHz:.6f} MHz)")
    else:
        which = p["ZSP_ParityFreqs_Cached"]["which_to_park"]
        parity_drive_freq_MHz = (p["ZSP_ParityFreqs_Cached"]["lower_peak_MHz"]
                                 if which == "lower"
                                 else p["ZSP_ParityFreqs_Cached"]["higher_peak_MHz"])
        if parity_drive_freq_MHz is None:
            raise RuntimeError(
                "[ZeroSpanParity] No cached parity freq and "
                "ZSP_RecalibrateParityFreqs=False. Populate ZSP_ParityFreqs_Cached "
                "or set ZSP_RecalibrateParityFreqs=True.")

    # ---- Step 2: optional g/e separator pre-calibration ---------------------
    if p["ZSP_RecalibrateSeparator"]:
        sep = get_apriori_separator_from_singleshot(ctx)
        p["ZSP_Separator_Cached"]["g_center"] = sep["g_center"]
        p["ZSP_Separator_Cached"]["e_center"] = sep["e_center"]
        p["ZSP_Separator_Cached"]["normal"]   = sep["normal"]
        p["ZSP_Separator_Cached"]["midpoint"] = sep["midpoint"]
    elif p["ZSP_AnalysisParams"]["classifier_method"] in ("apriori", "apriori_axis"):
        # Spec §5.3 rule 7: with RecalibrateSeparator=False and a separator-based
        # classifier, all four cached fields must be np.ndarray of shape (2,).
        # Validate fail-fast (a copy-pasted list is coerced; wrong shapes are
        # rejected). "apriori_axis" needs the separator just as much as "apriori"
        # does -- it takes the projection AXIS from it and only the threshold from
        # the data -- so it must be covered by this guard too.
        for _k in ("g_center", "e_center", "normal", "midpoint"):
            _v = p["ZSP_Separator_Cached"][_k]
            if _v is None:
                raise RuntimeError(
                    f"[ZeroSpanParity §5.3 rule 7] ZSP_Separator_Cached['{_k}'] "
                    f"is None and classifier_method='apriori'. Populate "
                    f"ZSP_Separator_Cached, set ZSP_RecalibrateSeparator=True, or "
                    f"use classifier_method='kmeans'.")
            _arr = np.asarray(_v, dtype=float)
            if _arr.shape != (2,):
                raise RuntimeError(
                    f"[ZeroSpanParity §5.3 rule 7] ZSP_Separator_Cached['{_k}'] "
                    f"has shape {_arr.shape}, expected (2,) — an (I, Q) "
                    f"coordinate.")
            p["ZSP_Separator_Cached"][_k] = _arr  # normalize to ndarray

    # ---- Step 3: build the ZeroSpanParity cfg -------------------------------
    zsp_mode_params = (p["ZSP_StrobeParams"] if p["ZSP_RunMode"] == "strobe"
                       else p["ZSP_DecimatedParams"])
    zsp_qubit_gain = (p["ZSP_DriveParams"]["qubit_gain"]
                      if p["ZSP_DriveParams"]["qubit_gain"] is not None
                      else ctx.qubit_gain)
    zsp_pulse_gain = (p["ZSP_DriveParams"]["pulse_gain"]
                      if p["ZSP_DriveParams"]["pulse_gain"] is not None
                      else ctx.cavity_gain)
    cfg = ctx.working_config()
    # Readout frequency: prefer a cavity frequency actually FOUND this session (the
    # run_transmission_* carry-over writes it into ctx.config["pulse_freq"]) over
    # the value typed into Qubit_Parameters, which may predate the last fit.
    zsp_read_freq = float(cfg.get("pulse_freq") or ctx.resonator_frequency_center)
    # res_phase: default to the session's calibrated phase rather than a constant.
    # The apriori separator is measured in whatever rotated frame res_phase sets, so
    # if the two disagree the strobe IQ is rotated relative to the separator axis
    # and the projection is wrong. None -> inherit ctx.config.
    zsp_res_phase = p["ZSP_DriveParams"]["res_phase"]
    if zsp_res_phase is None:
        zsp_res_phase = cfg.get("res_phase", 0)
    zsp_cfg = {
        # Channel routing sourced from BaseConfig (Calib/initialize4Q.py)
        "res_ch":     cfg["res_ch"],
        "qubit_ch":   cfg["qubit_ch"],
        "ro_chs":     cfg["ro_chs"],
        "nqz":        cfg["nqz"],
        "qubit_nqz":  cfg["qubit_nqz"],
        "mixer_freq": cfg["mixer_freq"],
        # Frequencies (active qubit's tuned readout + picked parity peak)
        "read_pulse_freq":   zsp_read_freq,
        "parity_drive_freq": parity_drive_freq_MHz,
        # Drive
        "qubit_gain": zsp_qubit_gain,
        "pulse_gain": zsp_pulse_gain,
        "res_phase":  zsp_res_phase,
        # Mode + trigger source
        "mode":      p["ZSP_RunMode"],
        "start_src": p["ZSP_StartSrc"],
        # Mode-specific params (read_length, adc_trig_offset, + mode extras)
        **zsp_mode_params,
    }
    print(f"[ZeroSpanParity] read_pulse_freq={zsp_read_freq:.6f} MHz "
          f"(source: {'session transmission fit' if cfg.get('pulse_freq') else 'Qubit_Parameters'}), "
          f"res_phase={zsp_res_phase}, parity_drive_freq={parity_drive_freq_MHz:.6f} MHz")

    # The validation harness (Validate_* stages below) is strobe-only: every
    # run_* helper calls experiment.set_qubit_gain(), which raises in decimated
    # mode. Fail fast here — before the (potentially long) acquisition — rather
    # than crashing partway through the validation tail.
    _validate_flags = ("Validate_StaticContrast", "Validate_ContrastVsQubitFreq",
                       "Validate_ModulationCheck", "Validate_Telegraph",
                       "Validate_BinSizeSweep", "Validate_ThresholdStability",
                       "Validate_ControlSuite", "Validate_EnvironmentSweep")
    if p["ZSP_RunMode"] != "strobe" and any(p.get(f) for f in _validate_flags):
        raise RuntimeError(
            f"[ZeroSpanParity] the validation harness (Validate_*) is strobe-only "
            f"but ZSP_RunMode={p['ZSP_RunMode']!r}. Set ZSP_RunMode='strobe' or "
            f"disable the Validate_* flags.")

    # ---- Step 4: run acquisition --------------------------------------------
    zsp_exp = ZeroSpanParity(
        soc=ctx.soc, soccfg=ctx.soccfg, path="ZeroSpanParity",
        outerFolder=zsp_outerFolder, cfg=zsp_cfg)
    if p["ZSP_RunMode"] == "strobe" and p["ZSP_StrobeParams"]["n_chunks"] > 1:
        # chunked_acquire sets zsp_exp.data = {"data": stitched} itself, so the
        # bare save_data() below persists the full stitched record.
        zsp_data = chunked_acquire(
            zsp_exp, n_chunks=p["ZSP_StrobeParams"]["n_chunks"], progress=True)
    else:
        zsp_data = zsp_exp.acquire(progress=True)
    zsp_exp.save_data()
    zsp_exp.save_config()

    # Single run directory (the dated subfolder already holding the raw .h5) for
    # BOTH the analysis outputs and every validation-stage sidecar, so
    # build_evidence_report collates them from one place.
    _run_dir = os.path.dirname(zsp_exp.fname)

    # ---- Step 5: offline analysis -------------------------------------------
    # A separator is needed by every axis-projecting classifier, not just the
    # legacy midpoint-thresholding "apriori" one. Only "kmeans" works without it.
    _classifier = p["ZSP_AnalysisParams"]["classifier_method"]
    zsp_separator = None if _classifier == "kmeans" else p["ZSP_Separator_Cached"]
    analyze_parity_run(
        h5_path=zsp_exp.fname,
        separator=zsp_separator,
        window_us=p["ZSP_AnalysisParams"]["window_us"],
        k_sigma=p["ZSP_AnalysisParams"]["k_sigma"],
        classifier_method=_classifier,
        step_us=p["ZSP_AnalysisParams"]["step_us"],
        min_burst_duration_us=p["ZSP_AnalysisParams"]["min_burst_duration_us"],
        analysis_bin_us=p["ZSP_AnalysisParams"]["analysis_bin_us"],
        save_plots=p["ZSP_AnalysisParams"]["save_plots"],
        merge_short_segments=p["ZSP_AnalysisParams"].get("merge_short_segments", True),
        min_dwell_bins=p["ZSP_AnalysisParams"].get("min_dwell_bins", 2),
        # Threshold-free PSD rate. Always computed; these only tune it. Both keys
        # are optional in the runner's ZSP_AnalysisParams — psd_nperseg=None lets
        # segmented_welch_psd choose, psd_bin_list_us=None skips the (repeated,
        # therefore slower) bin-size invariance check.
        psd_nperseg=p["ZSP_AnalysisParams"].get("psd_nperseg"),
        psd_bin_list_us=p["ZSP_AnalysisParams"].get("psd_bin_list_us"),
        out_dir=_run_dir,
    )
    print(f"[ZeroSpanParity] complete. Raw data: {zsp_exp.fname}")

    # --- Validation harness execution ---
    _val_out_dir = _run_dir
    _min_dwell_bins = p["ZSP_AnalysisParams"].get("min_dwell_bins", 2)

    if p["Validate_StaticContrast"]:
        # Stage 1 measures |Z_on - Z_off| vs read_pulse_freq; it does NOT use a
        # g/e separator (that guard belonged to the classify-based stages, which
        # already have their separator validated in Step 2).
        _f0 = zsp_cfg["read_pulse_freq"]
        _span = p["StaticContrast_params"]["freq_span_mhz"]
        _flist = np.linspace(_f0 - _span / 2, _f0 + _span / 2, p["StaticContrast_params"]["n_points"])
        # run_static_contrast's set_qubit_gain rebuilds the strobe program from
        # cfg["reps"], so update both keys — otherwise reps_per_point only lands
        # in the sidecar metadata and the acquisition keeps the original count.
        # Snapshot and restore them: stage 1 uses a short per-point count, and
        # leaving that in place silently shortened every later stage's trace.
        _saved_reps = (zsp_exp.cfg.get("reps_per_chunk"), zsp_exp.cfg.get("reps"))
        try:
            zsp_exp.cfg["reps_per_chunk"] = p["StaticContrast_params"]["reps_per_point"]
            zsp_exp.cfg["reps"] = p["StaticContrast_params"]["reps_per_point"]
            _sc = run_static_contrast(zsp_exp, _flist, qubit_gain_on=zsp_cfg["qubit_gain"], out_dir=_val_out_dir)
        finally:
            zsp_exp.cfg["reps_per_chunk"], zsp_exp.cfg["reps"] = _saved_reps
            # Rebuild so the program in hand matches the restored reps, not the
            # per-point count stage 1 was running with.
            zsp_exp.set_qubit_gain(zsp_cfg["qubit_gain"])
        print(f"[stage 1] best read_pulse_freq = {_sc['best_freq']:.4f} MHz  (contrast SNR {_sc['contrast_snr']:.1f})")

    if p["Validate_ContrastVsQubitFreq"]:
        _q0 = zsp_cfg["parity_drive_freq"]
        _qspan = p["ContrastVsQubit_params"]["qfreq_span_mhz"]
        _qlist = np.linspace(_q0 - _qspan / 2, _q0 + _qspan / 2, p["ContrastVsQubit_params"]["n_points"])
        _s2 = run_contrast_vs_qubit_freq(zsp_exp, _qlist, out_dir=_val_out_dir)
        print(f"[stage 2] parity peak sep = {_s2['peaks'].get('peak_sep')}")

    if p["Validate_ModulationCheck"]:
        _m = run_modulation_check(zsp_exp, separator=zsp_separator,
                                  modulation_freq_hz=p["Modulation_params"]["modulation_freq_hz"],
                                  n_periods=p["Modulation_params"]["n_periods"],
                                  classifier_method=_classifier, out_dir=_val_out_dir)
        # Judge on block_tstat + the frequency match, NOT on the per-sample snr:
        # the injected schedule is constant within a block, so a per-sample figure
        # understates it by sqrt(reps_per_block). See verify_modulation's docstring.
        print(f"[stage 3] modulation GATE "
              f"({_m['n_blocks_on']} on / {_m['n_blocks_off']} off blocks of "
              f"{_m['reps_per_block']} samples)")
        print(f"          block separation AUC = {_m['block_separation_auc']:.3f}  "
              f"(1.0 = every driven block above every undriven one)"
              f"{'  [fully separated]' if _m['blocks_fully_separated'] else ''}")
        print(f"          block_tstat={_m['block_tstat']:.1f}  "
              f"block_snr={_m['block_snr']:.2f}  "
              f"depth={_m['modulation_depth']:.3f} "
              f"(per-sample snr={_m['snr']:.2f} -- not the figure of merit)")
        print(f"          freq recovered={_m['recovered_freq_hz']:.4f} Hz vs "
              f"injected={_m['injected_freq_hz']:.4f} Hz "
              f"(from {_m.get('recovered_freq_source', '?')})")
        print(f"          corr={_m['correlation']:+.2f} at lag={_m['lag_samples']} "
              f"samples")
        _freq_ok = (np.isfinite(_m["recovered_freq_hz"])
                    and abs(_m["recovered_freq_hz"] - _m["injected_freq_hz"])
                    <= 0.1 * max(abs(_m["injected_freq_hz"]), 1e-9))
        # AUC is the primary: it asks whether the drive on/off state is recoverable
        # block by block, which is exactly what the gate is for, and it does not
        # care how variable the driven level is.
        _pass = (_m["block_separation_auc"] >= 0.95
                 and _m["correlation"] > 0 and _freq_ok)
        print(f"          => {'PASS' if _pass else 'FAIL'} "
              f"(need AUC>=0.95, corr>0, freq within 10%)")
        if not _pass:
            print("          Do NOT trust anything downstream until this passes: "
                  "it means the projection axis, demod or timing is wrong.")

    # Stages 4/5/6 characterise the telegraph itself. Stage 4 acquires the
    # reference record; 5 and 6 reprocess THAT record so the bin-size and
    # threshold comparisons are made on identical samples rather than on
    # separately-acquired traces that also differ by drift.
    _telegraph_data = None
    if p.get("Validate_Telegraph"):
        _t4 = run_telegraph(zsp_exp, separator=zsp_separator,
                            window_us=p["ZSP_AnalysisParams"]["window_us"],
                            n_chunks=p["Telegraph_params"]["n_chunks"],
                            classifier_method=_classifier,
                            min_dwell_bins=_min_dwell_bins,
                            k_sigma=p["ZSP_AnalysisParams"]["k_sigma"],
                            progress=True, out_dir=_val_out_dir)
        _telegraph_data = _t4["data"]
        _h4 = _t4["histogram"]
        print(f"[stage 4] bimodal={_t4['is_bimodal']}  sep_snr={_h4['separation_snr']:.2f}  "
              f"dBIC={_h4['delta_bic']:.0f}  weights={np.round(_h4['weights'], 3)}  "
              f"tau0={_t4['dwell']['exp_fit_0']['tau_us']:.0f} us  "
              f"tau1={_t4['dwell']['exp_fit_1']['tau_us']:.0f} us")

    # Stages 5 and 6 do NOT need Validate_Telegraph set every time. If stage 4 did
    # not just run, reuse the most recent saved stage-4 record from disk, so you can
    # iterate on bin lists and thresholds for free. Falling through to a fresh
    # single-chunk acquire() would be much worse than it looks: it is reps_per_chunk
    # samples (one chunk, no n_chunks), and stages 5 and 6 would each grab a
    # DIFFERENT one -- so the bin-size and threshold comparisons would describe
    # different records, which defeats their purpose.
    if _telegraph_data is None and (p.get("Validate_BinSizeSweep")
                                    or p.get("Validate_ThresholdStability")):
        _telegraph_data = _load_saved_telegraph(zsp_outerFolder, _run_dir)
        if _telegraph_data is None:
            _n_ch = p["Telegraph_params"]["n_chunks"]
            print(f"[stages 5/6] no saved stage-4 record found -- acquiring a fresh "
                  f"{_n_ch}-chunk trace to analyse (enable Validate_Telegraph to get "
                  f"the stage-4 bimodality report from the same data).")
            _telegraph_data = (chunked_acquire(zsp_exp, n_chunks=_n_ch, progress=True)
                               if _n_ch > 1 else zsp_exp.acquire(progress=True))

    if p.get("Validate_BinSizeSweep"):
        _t5 = run_bin_size_sweep(zsp_exp, separator=zsp_separator,
                                 bin_list_us=p["BinSize_params"]["bin_list_us"],
                                 data=_telegraph_data, classifier_method=_classifier,
                                 progress=True, out_dir=_val_out_dir)
        print(f"[stage 5] best analysis bin = {_t5['best_bin_us']:.0f} us; "
              f"sep_snr per bin = {np.round(_t5['separation_snr_per_bin'], 2)}")

    if p.get("Validate_ThresholdStability"):
        _t6 = run_threshold_stability(zsp_exp, separator=zsp_separator,
                                      data=_telegraph_data,
                                      threshold_list=p["Threshold_params"]["threshold_list"],
                                      min_dwell_bins=_min_dwell_bins,
                                      classifier_method=_classifier,
                                      progress=True, out_dir=_val_out_dir)
        print(f"[stage 6] tau_cv = {_t6['tau_cv']:.3f} across "
              f"{len(_t6['threshold_list'])} thresholds (low = robust telegraph)")

    if p["Validate_ControlSuite"]:
        _pf = {"lower": p["ZSP_ParityFreqs_Cached"].get("lower_peak_MHz"),
               "higher": p["ZSP_ParityFreqs_Cached"].get("higher_peak_MHz")}
        _c = run_control_suite(zsp_exp, separator=zsp_separator, variants=tuple(p["Control_params"]["variants"]),
                               detune_mhz=p["Control_params"]["detune_mhz"], parity_freqs=_pf,
                               classifier_method=_classifier, out_dir=_val_out_dir)
        print(f"[stage 8] controls: {[(k, v.get('separation_snr', v.get('separation_snr_lower'))) for k, v in _c['variants'].items()]}")

    if p["Validate_EnvironmentSweep"]:
        def _set_power(_exp, _val):
            # NOTE: this only changes the RFSoC readout DAC gain. For a genuine
            # readout-POWER sweep, drive the Vaunix attenuator here instead
            # (PythonDrivers/control_atten.py) -- DAC gain and attenuation are not
            # interchangeable once the amplifier chain compresses.
            _exp.cfg["pulse_gain"] = _val
            _exp.prog = type(_exp.prog)(_exp.soccfg, _exp.cfg)
        _e = run_environment_sweep(zsp_exp, separator=zsp_separator,
                                   param_name=p["Environment_params"]["param_name"],
                                   param_values=p["Environment_params"]["values"],
                                   set_param=_set_power,
                                   window_us=p["ZSP_AnalysisParams"]["window_us"],
                                   classifier_method=_classifier, out_dir=_val_out_dir)
        print(f"[stage 7] swept {p['Environment_params']['param_name']}: {_e['table']}")

    if p["Build_EvidenceReport"]:
        _rep = build_evidence_report(_val_out_dir, os.path.join(_val_out_dir, "EVIDENCE.md"))
        print(f"[stage 9] evidence report written: {_rep}")
