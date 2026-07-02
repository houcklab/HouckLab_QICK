from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.utils import *
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mZeroSpanParity import ZeroSpanParity
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.analyze_ZeroSpanParity import analyze_parity_run
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.validate_ZeroSpanParity import (run_static_contrast, run_contrast_vs_qubit_freq, run_modulation_check, run_control_suite, run_environment_sweep, build_evidence_report)
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mSpecSliceFF import QubitSpecSliceFF
import numpy as np
import matplotlib.pyplot as plt
import os
from .context import Context
from .calibration import get_apriori_separator_from_singleshot


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
        data_paritySpec = QubitSpecSliceFF.acquire(Instance_paritySpec)
        QubitSpecSliceFF.display(
            Instance_paritySpec, data_paritySpec, plotDisp=False, figNum=2,
            min_sep=p["ZSP_ParitySpec_params"]["min_sep_MHz"],
            fit_window_mhz=p["ZSP_ParitySpec_params"]["fit_window_mhz"],
            prominent_ratio=p["ZSP_ParitySpec_params"]["prominent_ratio"])
        QubitSpecSliceFF.save_data(Instance_paritySpec, data_paritySpec)
        QubitSpecSliceFF.save_config(Instance_paritySpec)

        chosen = pick_parity_drive_freq(
            data_paritySpec, which=p["ZSP_ParityFreqs_Cached"]["which_to_park"])
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
    elif p["ZSP_AnalysisParams"]["classifier_method"] == "apriori":
        # Spec §5.3 rule 7: with RecalibrateSeparator=False and apriori
        # classification, all four cached fields must be np.ndarray of shape
        # (2,). Validate fail-fast (a copy-pasted list is coerced; wrong shapes
        # are rejected).
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
    zsp_cfg = {
        # Channel routing sourced from BaseConfig (Calib/initialize4Q.py)
        "res_ch":     cfg["res_ch"],
        "qubit_ch":   cfg["qubit_ch"],
        "ro_chs":     cfg["ro_chs"],
        "nqz":        cfg["nqz"],
        "qubit_nqz":  cfg["qubit_nqz"],
        "mixer_freq": cfg["mixer_freq"],
        # Frequencies (active qubit's tuned readout + picked parity peak)
        "read_pulse_freq":   ctx.resonator_frequency_center,
        "parity_drive_freq": parity_drive_freq_MHz,
        # Drive
        "qubit_gain": zsp_qubit_gain,
        "pulse_gain": zsp_pulse_gain,
        "res_phase":  p["ZSP_DriveParams"]["res_phase"],
        # Mode + trigger source
        "mode":      p["ZSP_RunMode"],
        "start_src": p["ZSP_StartSrc"],
        # Mode-specific params (read_length, adc_trig_offset, + mode extras)
        **zsp_mode_params,
    }

    # ---- Step 4: run acquisition --------------------------------------------
    zsp_exp = ZeroSpanParity(
        soc=ctx.soc, soccfg=ctx.soccfg, path="ZeroSpanParity",
        outerFolder=zsp_outerFolder, cfg=zsp_cfg)
    if p["ZSP_RunMode"] == "strobe" and p["ZSP_StrobeParams"]["n_chunks"] > 1:
        zsp_data = chunked_acquire(
            zsp_exp, n_chunks=p["ZSP_StrobeParams"]["n_chunks"], progress=True)
        # Stitched arrays replace exp.data so save_data writes the full record.
        zsp_exp.data = {"data": zsp_data}
    else:
        zsp_data = zsp_exp.acquire(progress=True)
    zsp_exp.save_data()
    zsp_exp.save_config()

    # ---- Step 5: offline analysis -------------------------------------------
    zsp_separator = (p["ZSP_Separator_Cached"]
                     if p["ZSP_AnalysisParams"]["classifier_method"] == "apriori"
                     else None)
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
        out_dir=os.path.dirname(zsp_exp.fname),
    )
    print(f"[ZeroSpanParity] complete. Raw data: {zsp_exp.fname}")

    # --- Validation harness execution ---
    _val_out_dir = zsp_exp.outerFolder if hasattr(zsp_exp, "outerFolder") else os.path.dirname(zsp_exp.fname)

    if p["Validate_StaticContrast"]:
        if p["ZSP_Separator_Cached"].get("g_center") is None:
            raise RuntimeError("Validate_StaticContrast needs a calibrated separator (set RecalibrateSeparator)")
        _f0 = zsp_cfg["read_pulse_freq"]
        _span = p["StaticContrast_params"]["freq_span_mhz"]
        _flist = np.linspace(_f0 - _span / 2, _f0 + _span / 2, p["StaticContrast_params"]["n_points"])
        zsp_exp.cfg["reps_per_chunk"] = p["StaticContrast_params"]["reps_per_point"]
        _sc = run_static_contrast(zsp_exp, _flist, qubit_gain_on=zsp_cfg["qubit_gain"], out_dir=_val_out_dir)
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
                                  n_periods=p["Modulation_params"]["n_periods"], out_dir=_val_out_dir)
        print(f"[stage 3] modulation corr={_m['correlation']:.2f} depth={_m['modulation_depth']:.2f} "
              f"snr={_m['snr']:.2f}  (gate: proceed only if recovered)")

    if p["Validate_ControlSuite"]:
        _pf = {"lower": p["ZSP_ParityFreqs_Cached"].get("lower_peak_MHz"),
               "higher": p["ZSP_ParityFreqs_Cached"].get("higher_peak_MHz")}
        _c = run_control_suite(zsp_exp, separator=zsp_separator, variants=tuple(p["Control_params"]["variants"]),
                               detune_mhz=p["Control_params"]["detune_mhz"], parity_freqs=_pf, out_dir=_val_out_dir)
        print(f"[stage 8] controls: {[(k, v.get('separation_snr', v.get('separation_snr_lower'))) for k, v in _c['variants'].items()]}")

    if p["Validate_EnvironmentSweep"]:
        def _set_power(_exp, _val):
            _exp.cfg["pulse_gain"] = _val  # NOTE: replace with attenuator/YOKO call for real power sweep
            _exp.prog = type(_exp.prog)(_exp.soccfg, _exp.cfg)
        _e = run_environment_sweep(zsp_exp, separator=zsp_separator,
                                   param_name=p["Environment_params"]["param_name"],
                                   param_values=p["Environment_params"]["values"],
                                   set_param=_set_power, out_dir=_val_out_dir)
        print(f"[stage 7] swept {p['Environment_params']['param_name']}: {_e['table']}")

    if p["Build_EvidenceReport"]:
        _rep = build_evidence_report(_val_out_dir, os.path.join(_val_out_dir, "EVIDENCE.md"))
        print(f"[stage 9] evidence report written: {_rep}")
