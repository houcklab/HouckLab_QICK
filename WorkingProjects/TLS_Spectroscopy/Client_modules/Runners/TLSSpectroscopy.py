import os
import sys
from datetime import datetime

_d = os.path.dirname(os.path.abspath(__file__))
while _d != os.path.dirname(_d):
    if os.path.isdir(os.path.join(_d, "WorkingProjects")):
        if _d not in sys.path:
            sys.path.insert(0, _d)
        break
    _d = os.path.dirname(_d)
else:
    raise RuntimeError("Could not find the HouckLab_QICK repo root (no WorkingProjects/ above this file).")

import numpy as np

from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.socProxy import makeProxy
from WorkingProjects.TLS_Spectroscopy.Client_modules.Calib.initialize import BaseConfig, outerFolder
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.active_reset import probe_reset_params
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.reset_phase import calibrate_res_phase
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mTransmissionVsFFGain import TransmissionVsFFGain
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mQubitLongTimeSpecVsFlux import QubitLongTimeSpecVsFlux
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mQubitFluxStepResponse import QubitFluxStepResponse
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mSingleShot1Q import SingleShot1Q
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mT1VsFlux import (
    T1FullCurveVsFlux,
    T1FullCurveVsFluxFromFit,
    T13PointVsFlux,
    build_wall_clock_repeat_metadata,
    get_wall_clock_repeat_spec,
    get_wall_clock_repeat_full_spec,
    save_wall_clock_repeat_full_outputs,
    _csv_base_from_pickle,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import flux_fit as fx
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import flux_predistortion as fpd


LIVE_PLOTS = True
import matplotlib
matplotlib.use("TkAgg" if LIVE_PLOTS else "Agg", force=True)
import matplotlib.pyplot as plt
import gc

CHIP_NAME_FOR_CONFIG = "FTTv02_SiOxJJ"
QUBIT = "q4"


SET_YOKO = False
YOKO_VISA = "USB0::0x0B21::0x0039::91S929899::0::INSTR"
YOKO_VOLTAGE = 0.0


FLUX_FIT_PARAMS = None

BASELINE_DC_OFFSET = 0
TARGET_DC_OFFSET = 8000
FLUX_TAIL_COMPENSATION_GAIN = 0.75

SAVE_RESONATOR_LOOKUP = True
USE_RESONATOR_LOOKUP = False
RESONATOR_LOOKUP_CSV = None

RESONATOR_FIT_PARAMS = None

INTERLEAVE_ROUNDS = 10

PROBE_RESET = True
CAL_RES_PHASE = False
RESET_THRESHOLD_RAW = 7087
RESET_OPER = "lower"
RESET_GROUND_BELOW = True


P1_RESONATOR = {
    "run": False,
    "shots": 200,
    "freq_min": 7245.0,
    "freq_max": 7252.0,
    "freq_step": 0.05,
    "dc_min": 0,
    "dc_max": 12000,
    "dc_step": 300,
    "lookup_smooth_points": None,
    "live_plot": True,
    "spec_amp": None,
    "spec_len_us": None,
}

P2_QUBIT_SPEC_FULL = {
    "run": False,
    "advanced_fit": True,
    "shots": 100,
    "relax_delay_us": 100.0,
    "spec_amp": 7000,
    "spec_len_us": 0.5,
    "freq_min": 2250.0,
    "freq_max": 2570.0,
    "freq_step": 2.0,
    "dc_min": 0,
    "dc_max": 12000,
    "dc_step": 300,
    "live_plot": True,
}

P3_STEP_RESPONSE = {
    "run_fit": False,
    "run_correct": False,
    "shots": 200,
    "spec_amp": 2000,
    "spec_len_us": 0.5,
    "freq_step": 0.5,
    "auto_center_frequency_window": True,
    "auto_freq_absolute_min_mhz": 2250.0,
    "auto_freq_absolute_max_mhz": 2570.0,
    "t_min_us": 1.0,
    "t_max_us": 500.0,
    "t_step_us": 4.0,
    "baseline_rearm_us": 100.0,
    "piecewise_min_multiplier": 0.5,
    "piecewise_max_multiplier": 1.5,
    "readout_after_park": False,
    "live_plot": True,
}

P4_LONG_TIME = {
    "run": False,
    "fit_trace": True,
    "advanced_fit": False,
    "shots": 100,
    "relax_delay_us": 700.0,
    "spec_amp": 7000,
    "spec_len_us": 0.5,
    "freq_min": 2250.0,
    "freq_max": 2570.0,
    "freq_step": 2.0,
    "dc_min": 0,
    "dc_max": 12000,
    "dc_step": 300,
    "long_time_us": 5.0,
    "average_window_us": 0.0,
    "average_step_us": 0.016,
    "inter_target_wait_us": 100.0,
    "live_plot": False,
}

P5_SS_CAL = {
    "run": False,
    "ss_shots": 1000,
    "min_F": 0.60,
    "reset_mode": "feedback",
    "reset_probe_shots": 2000,
    "reset_max_iters": 3,
    "reset_thermalization_us": 25.0,
}


P6_3PT_T1 = {
    "run": False,
    "shots": 2000,
    "dc_min": 0,
    "dc_max": 12000,
    "dc_step": 60,
    "freq_step_mhz": 1,
    "wall_clock_duration_min": None,
    "Ts_us": 100.0,
    "auto_Ts_factor": 0.5,
    "run_park_T1_if_Ts_none": True,
    "min_ref_contrast": 0.05,
    "max_plot_t1_multiple": 20.0,
    "reset_mode": "feedback",
    "reset_threshold_raw": 7087,
    "reset_oper": "lower",
    "reset_ground_below": True,
    "reset_max_iters": 3,
    "T1_probe_cfg": {
        "shots_T1": 1000,
        "t_min_us": 1.0,
        "t_max_us": 300.0,
        "t_points": 71,
        "num_pulses": 1,
    },
}

STEP3B_GAIN_SWEEP = None


def _set_yoko_if_requested():
    if not SET_YOKO:
        print("\nSET_YOKO is False: leaving the YOKO bias untouched.\n")
        return
    import time
    import pyvisa as visa
    from WorkingProjects.TLS_Spectroscopy.Client_modules.PythonDrivers.YOKOGS200 import YOKOGS200
    yoko = YOKOGS200(YOKO_VISA, rm=visa.ResourceManager())
    yoko.SetMode('voltage')
    print(f"\nRamping YOKO to {round(YOKO_VOLTAGE, 5)} V ...")
    yoko.SetVoltage(YOKO_VOLTAGE)
    while abs(yoko.GetVoltage() - YOKO_VOLTAGE) > 1e-4:
        time.sleep(0.1)
    print("YOKO parked.\n")


def _spec_cfg(p, extra=None):
    cfg = dict(BaseConfig)
    cfg["reps"] = int(p["shots"])
    cfg["interleave_rounds"] = p.get("interleave_rounds", INTERLEAVE_ROUNDS)
    cfg["relax_delay"] = float(p.get("relax_delay_us", 100.0))
    if RESONATOR_FIT_PARAMS is not None and not USE_RESONATOR_LOOKUP:
        cfg["resonator_fit_parameters"] = list(RESONATOR_FIT_PARAMS)
    if "spec_amp" in p:
        cfg["qubit_gain"] = int(p["spec_amp"])
        cfg["qubit_pulse_style"] = "const"
    if "spec_len_us" in p:
        cfg["qubit_length"] = float(p["spec_len_us"])
    if extra:
        cfg.update(extra)
    return cfg


def _load_correction(correction_json, outer_folder):
    if correction_json is None:
        correction_json = fpd.find_latest_compensation_json(
            outer_folder, QUBIT, baseline_dc_offset=BASELINE_DC_OFFSET)
    if correction_json is None:
        raise ValueError(
            "No flux-tail compensation JSON available. Run step 3 (calibration) "
            "first, or set the correction path explicitly."
        )
    compensation = fpd.load_compensation_json(correction_json)
    if FLUX_TAIL_COMPENSATION_GAIN != 1.0:
        compensation = fpd.scale_compensation_gain(compensation, FLUX_TAIL_COMPENSATION_GAIN)
    print(f"    Applying flux-tail compensation: {correction_json}")
    print(f"      segments = {len(compensation['segment_edges_ns'])}, gain = {FLUX_TAIL_COMPENSATION_GAIN}")
    return compensation


def _wall_clock_seconds(duration_min):
    if duration_min is None:
        return None
    duration_min = float(duration_min)
    return 60.0 * duration_min if duration_min > 0 else None


def _resolve_resonator_lookup(latest_lookup_csv):
    lookup_csv = RESONATOR_LOOKUP_CSV or latest_lookup_csv
    if USE_RESONATOR_LOOKUP:
        if lookup_csv is None:
            raise RuntimeError(
                "USE_RESONATOR_LOOKUP=True but no lookup CSV is available. Run step 1 "
                "(resonator spec) in this same session, or set RESONATOR_LOOKUP_CSV to a "
                "saved *_resonator_lookup.csv path."
            )
        return lookup_csv
    if RESONATOR_FIT_PARAMS is not None:
        return None
    return lookup_csv


def _dc_vec(p):
    return np.arange(p["dc_min"], p["dc_max"], p["dc_step"])


def _freq_vec_mhz(p):
    v = np.arange(p["freq_min"], p["freq_max"], p["freq_step"])
    if v.size == 0:
        raise ValueError(f"empty frequency vector: need freq_min < freq_max with freq_step > 0 "
                         f"(got freq_min={p['freq_min']}, freq_max={p['freq_max']}, "
                         f"freq_step={p['freq_step']})")
    return v


def _auto_freq_window(p, dc_baseline, dc_target):
    if not (p.get("auto_center_frequency_window", True) and FLUX_FIT_PARAMS is not None):
        return p["auto_freq_absolute_min_mhz"], p["auto_freq_absolute_max_mhz"]
    f = fx.estimate_fit_frequency_ghz_array(
        FLUX_FIT_PARAMS, np.array([float(dc_baseline), float(dc_target)])) * 1e3
    margin = max(40.0, 0.5 * abs(f[1] - f[0]))
    lo = max(min(f) - margin, p["auto_freq_absolute_min_mhz"])
    hi = min(max(f) + margin, p["auto_freq_absolute_max_mhz"])
    return lo, hi


def _build_freq_uniform_dc_vec(p):
    dc_vec = fx.build_freq_uniform_dc_vec(p["dc_min"], p["dc_max"],
                                          float(p["freq_step_mhz"]) * 1e6, FLUX_FIT_PARAMS)
    f_edges = fx.estimate_fit_frequency_ghz_array(
        FLUX_FIT_PARAMS, np.array([float(dc_vec.min()), float(dc_vec.max())]))
    print(f"[6] freq-uniform DC scan from flux fit: {len(dc_vec)} points at "
          f"{p['freq_step_mhz']:g} MHz steps "
          f"(DC {dc_vec.min():+.0f}..{dc_vec.max():+.0f} DAC, "
          f"f {min(f_edges):.3f}..{max(f_edges):.3f} GHz)")
    return dc_vec


def run_step1_resonator_spec(outer_folder, soc, soccfg):
    p = P1_RESONATOR
    f_vec = _freq_vec_mhz(p)
    dc_vec = _dc_vec(p)
    print(f"[1] Resonator spectroscopy vs flux: {len(f_vec)} IF x {len(dc_vec)} DC points")
    cfg = dict(BaseConfig)
    cfg["reps"] = int(p["shots"])
    cfg["interleave_rounds"] = p.get("interleave_rounds", INTERLEAVE_ROUNDS)
    cfg["relax_delay"] = 50
    cfg["trans_freq_start"] = p["freq_min"]
    cfg["trans_freq_stop"] = p["freq_max"]
    cfg["TransNumPoints"] = len(f_vec)
    cfg["trans_freq_vec"] = f_vec
    cfg["ff_gain_vec"] = dc_vec
    cfg["ff_settle_us"] = 20.0
    if p.get("spec_amp") is not None:
        cfg["read_pulse_gain"] = int(p["spec_amp"])
    if p.get("spec_len_us") is not None:
        cfg["read_length"] = float(p["spec_len_us"])
    exp = TransmissionVsFFGain(
        soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outer_folder,
        suffix="Resonator_Spec_vs_Flux", cfg=cfg,
        save_resonator_lookup=SAVE_RESONATOR_LOOKUP,
        resonator_lookup_smooth_points=p.get("lookup_smooth_points", None),
    )
    data = exp.acquire(progress=True, plotDisp=bool(p.get("live_plot", True)) and LIVE_PLOTS)
    lookup_csv = data['data'].get('resonator_lookup_csv')
    print("[1] Done. To make steps 2-4 track the readout freq with flux (QUA-style), paste the printed")
    print("    'dispersive fit parameters' 7-tuple into RESONATOR_FIT_PARAMS at the top of this file")
    print("    (keep USE_RESONATOR_LOOKUP=False).  Leave it None for a flat readout IF.")
    if lookup_csv:
        print(f"[1] Measured-dip lookup table saved: {lookup_csv}")
    return lookup_csv


def run_step2_qubit_spec_full_range(outer_folder, soc, soccfg, resonator_lookup_csv=None):
    p = P2_QUBIT_SPEC_FULL
    dc_vec = _dc_vec(p)
    print(f"[2] Qubit spec vs flux (full range, FIT OFF): "
          f"{p['freq_min'] / 1e3:.3f}-{p['freq_max'] / 1e3:.3f} GHz x {len(dc_vec)} DC points")
    cfg = _spec_cfg(p, extra={
        "qubit_freq_start": p["freq_min"], "qubit_freq_stop": p["freq_max"],
        "qubit_freq_step": p["freq_step"],
        "qubit_freq_expts": len(_freq_vec_mhz(p)),
    })
    exp = QubitLongTimeSpecVsFlux(
        soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outer_folder,
        suffix="Qubit_Spec_vs_Flux_Full_Range", cfg=cfg, step_tag="2",
        dc_vec=dc_vec,
        long_time_ns=2000.0, average_window_ns=0.0,
        readout_after_park=False,
        park_voltage=BASELINE_DC_OFFSET,
        fit_trace=False, advanced_fit=bool(p.get("advanced_fit", True)),
        live_plot=bool(p.get("live_plot", True)) and LIVE_PLOTS,
        resonator_lookup_csv=resonator_lookup_csv,
    )
    data = exp.acquire(progress=True)
    print(f"[2] Done. raw_sweep CSV (fit offline): {data['data'].get('raw_sweep_csv')}")
    return data['data'].get('flux_fit_params')


def _step3_common_cfg(p):
    fmin, fmax = _auto_freq_window(p, BASELINE_DC_OFFSET, TARGET_DC_OFFSET)
    n = max(int(round((fmax - fmin) / p["freq_step"])) + 1, 5)
    cfg = _spec_cfg(p, extra={
        "qubit_freq_start": fmin, "qubit_freq_stop": fmax, "qubit_freq_expts": n,
        "readout_after_park": p.get("readout_after_park", False),
    })
    return cfg


def _gain_suffix(gain):
    sign = "p" if float(gain) >= 0 else "m"
    milli = int(round(abs(float(gain)) * 1000))
    return f"gain_{sign}{milli:04d}"


def _gain_sweep_row(gain, dc_offset, exp, flux_tail_compensation):
    frequency_ghz = np.asarray(exp.data.get("extracted_qubit_frequency_ghz", []), dtype=float)
    time_ns = np.asarray(exp.data.get("t_vec", []), dtype=float)
    finite = np.isfinite(frequency_ghz)
    row = {
        "gain": float(gain),
        "dc_offset_V": float(dc_offset),
        "source_json": flux_tail_compensation.get("source", ""),
        "summary_png": exp.data.get("summary_image", ""),
        "step_response_png": exp.data.get("step_response_image", ""),
        "frequency_drift_zoom_png": exp.data.get("frequency_drift_zoom_image", ""),
        "frequency_drift_csv": exp.data.get("frequency_drift_csv", ""),
        "raw_sweep_csv": exp.data.get("raw_sweep_csv", exp.data.get("raw_sweep_csv_path", "")),
        "n_finite_frequency_points": int(np.count_nonzero(finite)),
        "multiplier_min": float(np.nanmin(flux_tail_compensation["multipliers"])),
        "multiplier_max": float(np.nanmax(flux_tail_compensation["multipliers"])),
        "multiplier_clipped": bool(flux_tail_compensation.get("gain_sweep_multiplier_clipped", False)),
    }
    if np.count_nonzero(finite) > 0:
        first = float(frequency_ghz[finite][0])
        drift_mhz = 1e3 * (frequency_ghz[finite] - first)
        finite_time_us = time_ns[finite] / 1e3 if time_ns.size == frequency_ghz.size else np.arange(drift_mhz.size)
        row.update(
            {
                "first_frequency_GHz": first,
                "median_frequency_GHz": float(np.nanmedian(frequency_ghz[finite])),
                "final_minus_first_MHz": float(drift_mhz[-1]),
                "min_minus_first_MHz": float(np.nanmin(drift_mhz)),
                "max_minus_first_MHz": float(np.nanmax(drift_mhz)),
                "peak_to_peak_MHz": float(np.nanmax(drift_mhz) - np.nanmin(drift_mhz)),
                "max_abs_minus_first_MHz": float(np.nanmax(np.abs(drift_mhz))),
                "rms_minus_first_MHz": float(np.sqrt(np.nanmean(drift_mhz**2))),
                "mean_abs_minus_first_MHz": float(np.nanmean(np.abs(drift_mhz))),
                "duration_us": float(finite_time_us[-1] - finite_time_us[0]) if finite_time_us.size > 1 else 0.0,
            }
        )
    else:
        row.update(
            {
                "first_frequency_GHz": np.nan,
                "median_frequency_GHz": np.nan,
                "final_minus_first_MHz": np.nan,
                "min_minus_first_MHz": np.nan,
                "max_minus_first_MHz": np.nan,
                "peak_to_peak_MHz": np.nan,
                "max_abs_minus_first_MHz": np.nan,
                "rms_minus_first_MHz": np.nan,
                "mean_abs_minus_first_MHz": np.nan,
                "duration_us": np.nan,
            }
        )

    voltage_response = np.asarray(exp.data.get("measured_voltage_step_response", []), dtype=float)
    finite_v = np.isfinite(voltage_response)
    if np.count_nonzero(finite_v) > 0:
        row.update(
            {
                "voltage_response_min": float(np.nanmin(voltage_response[finite_v])),
                "voltage_response_max": float(np.nanmax(voltage_response[finite_v])),
                "voltage_response_peak_to_peak": float(
                    np.nanmax(voltage_response[finite_v]) - np.nanmin(voltage_response[finite_v])
                ),
                "voltage_response_final_minus_one": float(voltage_response[finite_v][-1] - 1.0),
            }
        )
    else:
        row.update(
            {
                "voltage_response_min": np.nan,
                "voltage_response_max": np.nan,
                "voltage_response_peak_to_peak": np.nan,
                "voltage_response_final_minus_one": np.nan,
            }
        )
    return row


def _write_gain_sweep_summary_csv(experiments, rows):
    import csv
    from pathlib import Path
    if not rows:
        return None
    first_path = Path(experiments[0].iname)
    stem = first_path.stem
    marker = "_gain_"
    if marker in stem:
        stem = stem.split(marker)[0]
    csv_path = first_path.with_name(stem + "_gain_sweep_summary.csv")
    fieldnames = list(rows[0].keys())
    with open(csv_path, "w", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Saved gain sweep summary CSV: {csv_path}")
    return str(csv_path)


def _run_step3_experiment(p, soc, soccfg, outer_folder, suffix, flux_tail_compensation,
                          fit_rise_decay_bump_dc_correction, live_plot):
    run_kind = "calibration" if fit_rise_decay_bump_dc_correction else "validation"
    print(f"Running flux-step {run_kind} target dc_offset={TARGET_DC_OFFSET:+.6f} DAC")
    t_vec_ns = np.arange(p["t_min_us"], p["t_max_us"], p["t_step_us"]) * 1e3
    exp = QubitFluxStepResponse(
        soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outer_folder,
        suffix=suffix, cfg=_step3_common_cfg(p),
        element=QUBIT, t_vec=t_vec_ns,
        dc_offset=TARGET_DC_OFFSET, baseline_dc_offset=BASELINE_DC_OFFSET,
        shots=int(p["shots"]),
        flux_fit_params=FLUX_FIT_PARAMS, flux_lookup_mode="fit",
        piecewise_response_domain=p.get("piecewise_response_domain", "voltage"),
        live_plot=live_plot,
        fit_rise_decay_bump_dc_correction=fit_rise_decay_bump_dc_correction,
        piecewise_min_multiplier=p.get("piecewise_min_multiplier", 0.5),
        piecewise_max_multiplier=p.get("piecewise_max_multiplier", 1.5),
        baseline_rearm_time_ns=float(p.get("baseline_rearm_us", 500.0)) * 1e3,
        flux_tail_compensation=flux_tail_compensation,
    )
    exp.acquire(progress=True)
    exp.save_data()
    exp.save_config()
    if fit_rise_decay_bump_dc_correction and not exp.data.get("rise_decay_bump_dc_compensation_json"):
        fit_info = exp.data.get("rise_decay_bump_dc_correction_fit", {})
        raise RuntimeError(
            "This calibration run was expected to save a rise-decay-bump DC compensation JSON, "
            "but none was produced. The next validation run would otherwise fall back to an "
            f"old JSON. Fit info: success={fit_info.get('success')}, "
            f"error={fit_info.get('error')!r}. Check the just-saved raw sweep and trace plots."
        )
    plt.close("all")
    gc.collect()
    print(f"Flux step response for {QUBIT} at dc_offset={TARGET_DC_OFFSET:+.6f} DAC complete")
    return exp


def run_step3a_step_response_fit(outer_folder, soc, soccfg):
    p = P3_STEP_RESPONSE
    if FLUX_FIT_PARAMS is None:
        raise RuntimeError("Step 3a needs FLUX_FIT_PARAMS: run step 2 and paste the "
                           "printed values at the top of this file.")
    print(f"[3a] Step-response FIT: baseline={BASELINE_DC_OFFSET:+.4f} DAC -> "
          f"target={TARGET_DC_OFFSET:+.4f} DAC (measure + fit the distortion, no correction applied)")
    exp = _run_step3_experiment(
        p, soc, soccfg, outer_folder, suffix="Qubit_Flux_Step_Response",
        flux_tail_compensation=None, fit_rise_decay_bump_dc_correction=True,
        live_plot=bool(p.get("live_plot", True)) and LIVE_PLOTS,
    )
    correction_json = exp.data.get("rise_decay_bump_dc_compensation_json")
    if correction_json is None:
        raise RuntimeError("Step-response fit did not save a rise-decay-bump compensation JSON.")
    print(f"[3a] Saved correction JSON: {correction_json}")
    return correction_json


def run_step3b_step_response_correct(outer_folder, soc, soccfg, correction_json=None):
    p = P3_STEP_RESPONSE
    if correction_json is None:
        correction_json = QubitFluxStepResponse.find_latest_rise_decay_bump_dc_compensation_json(
            outer_folder, QUBIT,
            dc_offset=TARGET_DC_OFFSET, baseline_dc_offset=BASELINE_DC_OFFSET,
        )
        if correction_json is None:
            raise RuntimeError("No correction JSON found; run step 3a (fit) first.")
    base_comp = QubitFluxStepResponse.load_piecewise_dc_compensation_json(correction_json)

    if STEP3B_GAIN_SWEEP is not None:
        print(f"[3b] Step-response CORRECT (gain sweep {STEP3B_GAIN_SWEEP}): applying {correction_json}")
        print("[3b] Live plotting disabled during the gain sweep (multi-run Tk figures crash on Windows).")
        gain_sweep_values = ([float(STEP3B_GAIN_SWEEP)] if np.isscalar(STEP3B_GAIN_SWEEP)
                             else [float(gain) for gain in STEP3B_GAIN_SWEEP])
        for gain in gain_sweep_values:
            if not np.isfinite(gain) or gain < 0.0:
                raise ValueError("flux_tail_compensation_gain_sweep values must be finite and non-negative.")
        print(
            "Running flux-tail gain sweep with gains: "
            + ", ".join(f"{gain:.3f}" for gain in gain_sweep_values)
        )
        experiments = []
        gain_sweep_rows = []
        for gain in gain_sweep_values:
            run_flux_tail_compensation = fpd.scale_compensation_gain(
                base_comp, gain,
                min_multiplier=p.get("piecewise_min_multiplier", 0.5),
                max_multiplier=p.get("piecewise_max_multiplier", 1.5),
            )
            suffix = f"Qubit_Flux_Step_Response_{_gain_suffix(gain)}"
            print(
                f"Gain-sweep validation: dc_offset={TARGET_DC_OFFSET:+.6f} DAC, "
                f"correction_gain={gain:.3f}"
            )
            exp = _run_step3_experiment(
                p, soc, soccfg, outer_folder, suffix=suffix,
                flux_tail_compensation=run_flux_tail_compensation,
                fit_rise_decay_bump_dc_correction=False, live_plot=False,
            )
            experiments.append(exp)
            gain_sweep_rows.append(_gain_sweep_row(gain, TARGET_DC_OFFSET, exp, run_flux_tail_compensation))
        summary_csv = _write_gain_sweep_summary_csv(experiments, gain_sweep_rows)
        if summary_csv is not None:
            experiments[-1].data["gain_sweep_summary_csv"] = summary_csv
        print("[3b] Done. Pick the best gain from the *_gain_sweep_summary.csv, then set "
              "FLUX_TAIL_COMPENSATION_GAIN to it for steps 4 & 6.")
    else:
        print(f"[3b] Step-response CORRECT (gain {FLUX_TAIL_COMPENSATION_GAIN}): applying {correction_json}")
        compensation = fpd.scale_compensation_gain(
            base_comp, FLUX_TAIL_COMPENSATION_GAIN,
            min_multiplier=p.get("piecewise_min_multiplier", 0.5),
            max_multiplier=p.get("piecewise_max_multiplier", 1.5),
        )
        print(f"Applying fixed flux-tail compensation gain: {float(FLUX_TAIL_COMPENSATION_GAIN):.3f}")
        _run_step3_experiment(
            p, soc, soccfg, outer_folder, suffix="Qubit_Flux_Step_Response",
            flux_tail_compensation=compensation,
            fit_rise_decay_bump_dc_correction=False,
            live_plot=bool(p.get("live_plot", True)) and LIVE_PLOTS,
        )
        print("[3b] Done (the post-correction trace should be flat).")
    return correction_json


def run_step4_long_time_spec(outer_folder, soc, soccfg, correction_json,
                             resonator_lookup_csv=None):
    p = P4_LONG_TIME
    dc_vec = QubitLongTimeSpecVsFlux.build_inclusive_sweep(p["dc_min"], p["dc_max"], p["dc_step"])
    flux_tail_compensation = _load_correction(correction_json, outer_folder)
    print(f"[4] Long-time qubit spec vs flux (large ramp, FIT OFF, distortion-corrected): "
          f"{len(dc_vec)} DC points")
    cfg = _spec_cfg(p, extra={
        "qubit_freq_start": p["freq_min"], "qubit_freq_stop": p["freq_max"],
        "qubit_freq_step": p["freq_step"],
        "qubit_freq_expts": len(_freq_vec_mhz(p)),
    })
    exp = QubitLongTimeSpecVsFlux(
        soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outer_folder,
        suffix="Qubit_Long_Time_Frequency_vs_Flux", cfg=cfg, step_tag="4",
        dc_vec=dc_vec,
        long_time_ns=p["long_time_us"] * 1e3,
        average_window_ns=p.get("average_window_us", 0.0) * 1e3,
        average_step_ns=p.get("average_step_us", 0.016) * 1e3,
        park_voltage=BASELINE_DC_OFFSET,
        inter_target_wait_ns=p.get("inter_target_wait_us", 100.0) * 1e3,
        flux_tail_compensation=flux_tail_compensation,
        fit_trace=bool(p.get("fit_trace", True)), advanced_fit=bool(p.get("advanced_fit", False)),
        live_plot=bool(p.get("live_plot", False)) and LIVE_PLOTS,
        resonator_lookup_csv=resonator_lookup_csv,
    )
    data = exp.acquire(progress=True)
    print(f"[4] Done. raw_sweep CSV (fit offline): {data['data'].get('raw_sweep_csv')}")


def run_step5_single_shot_cal(outer_folder, soc, soccfg):
    cfg = dict(BaseConfig)
    print("[5] Single-shot readout calibration ...")
    cfg["shots"] = int(P5_SS_CAL["ss_shots"])
    cfg["qubit_pulse_style"] = "arb"
    cfg["qubit_gain"] = BaseConfig["qubit_pi_gain"]
    cfg["reset_mode"] = str(P5_SS_CAL.get("reset_mode", "passive"))
    if cfg["reset_mode"] == "feedback" and PROBE_RESET:
        rec = probe_reset_params(
            soc, soccfg, cfg, path=QUBIT, outer_folder=outer_folder,
            shots=int(P5_SS_CAL.get("reset_probe_shots", 2000)), validate=True)
        if rec is None:
            print("[5] active-reset validation failed -- using the configured passive "
                  f"{cfg['relax_delay']} us fallback.")
            cfg["reset_mode"] = "passive"
        else:
            cfg.update({
                "reset_threshold_raw": int(rec["threshold_raw"]),
                "reset_oper": str(rec.get("oper", "lower")),
                "reset_ground_below": bool(rec.get("ground_below", True)),
                "reset_max_iters": int(P5_SS_CAL.get("reset_max_iters", 3)),
                "reset_thermalization_us": float(
                    P5_SS_CAL.get("reset_thermalization_us", 25.0)),
                "active_reset_post_measure_delay_us": 0.05,
            })
    elif cfg["reset_mode"] == "feedback":
        print(f"[5] PROBE_RESET=False -> reusing threshold_raw={RESET_THRESHOLD_RAW} "
              f"({RESET_OPER}) without re-probing")
        cfg.update({
            "reset_threshold_raw": int(RESET_THRESHOLD_RAW),
            "reset_oper": str(RESET_OPER),
            "reset_ground_below": bool(RESET_GROUND_BELOW),
            "reset_max_iters": int(P5_SS_CAL.get("reset_max_iters", 3)),
            "reset_thermalization_us": float(
                P5_SS_CAL.get("reset_thermalization_us", 25.0)),
            "active_reset_post_measure_delay_us": 0.05,
        })
    ss = SingleShot1Q(soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outer_folder,
                      suffix="SS_Cal", cfg=cfg, save=True, plot=True, min_F=0.0)
    ss.acquire(progress=True, plotDisp=LIVE_PLOTS)
    min_F = float(P5_SS_CAL.get("min_F", 0.6))
    if ss.max_F < min_F:
        raise RuntimeError(f"SS cal fidelity {ss.max_F:.3f} < {min_F}; aborting before the T1 step.")
    print(f"[5] SS cal complete (F={ss.max_F:.3f}).")
    return ss.calib_params


def _run_one_stop_t1(factory, wall_clock_s):
    series_start = datetime.now()
    per_run_full_data = []
    base_path = None
    csv_path = None
    run_index = 0
    while True:
        run_start = datetime.now()
        repeat_metadata = build_wall_clock_repeat_metadata(run_start, series_start, run_index)
        if wall_clock_s is not None:
            print(f"  [6] wall-clock run {run_index + 1} "
                  f"(elapsed {repeat_metadata['wall_clock_elapsed_minutes_from_first_run']:.1f} min)")
        exp = factory(repeat_metadata)
        exp.acquire(progress=True)
        if base_path is None:
            base_path = _csv_base_from_pickle(exp.pname)
        spec = get_wall_clock_repeat_spec(exp)
        full_spec = get_wall_clock_repeat_full_spec(exp) or {}
        per_run_full_data.append({
            "run_metadata": repeat_metadata,
            "dc_vec": np.asarray(exp.dc_vec, dtype=float),
            "metric_column_name": spec["metric_column_name"],
            "metric_values": np.asarray(spec["metric_values"], dtype=float),
            "extra_metric_matrices": {
                key: np.asarray(values, dtype=float)
                for key, values in dict(spec.get("extra_metric_matrices", {})).items()
            },
            "axes": full_spec.get("axes", {}),
            "scalar_columns": full_spec.get("scalar_columns", {}),
            "array_columns": full_spec.get("array_columns", {}),
        })
        csv_path = save_wall_clock_repeat_full_outputs(base_path, spec["file_tag"], per_run_full_data)
        print(f"  [6] one-stop CSV updated after run {run_index + 1}: {csv_path}")
        run_index += 1
        if wall_clock_s is None or (datetime.now() - series_start).total_seconds() >= wall_clock_s:
            break
    return csv_path


def _t1_base_cfg(p, flux_tail_compensation, dc_vec):
    base = dict(BaseConfig)
    base.update({
        "shots": int(p["shots"]),
        "interleave_rounds": p.get("interleave_rounds", INTERLEAVE_ROUNDS),
        "ff_gain_vec": dc_vec,
        "flux_tail_compensation": flux_tail_compensation,
        "flux_fit_params": FLUX_FIT_PARAMS,
        "relax_delay": 2000,
        "qubit_pulse_style": "arb",
    })
    if p.get("reset_mode") == "feedback":
        if p.get("reset_threshold_raw") is None:
            raise RuntimeError("reset_mode='feedback' needs a reset threshold, but the "
                               "start-of-step-6 probe did not set one.")
        base.update({
            "reset_threshold_raw": int(p["reset_threshold_raw"]),
            "reset_oper": p.get("reset_oper", "lower"),
            "reset_ground_below": bool(p.get("reset_ground_below", True)),
            "reset_max_iters": int(p.get("reset_max_iters", 3)),
        })
    return base


def run_step6_3pt_t1(outer_folder, soc, soccfg, calib_params, correction_json):
    plt.close("all")
    gc.collect()
    p = dict(P6_3PT_T1)
    if p.get("reset_mode") == "feedback" and PROBE_RESET:
        rec = probe_reset_params(soc, soccfg, BaseConfig, path=QUBIT,
                                 outer_folder=outer_folder,
                                 shots=int(p.get("reset_probe_shots", 2000)))
        if rec is None:
            print("[6] no feedback discrimination this session -- using passive relax.")
            p["reset_mode"] = "passive"
        else:
            p["reset_threshold_raw"] = int(rec["threshold_raw"])
            p["reset_oper"] = str(rec["oper"])
            p["reset_ground_below"] = bool(rec["ground_below"])
    elif p.get("reset_mode") == "feedback":
        print(f"[6] PROBE_RESET=False -> reusing threshold_raw={RESET_THRESHOLD_RAW} "
              f"({RESET_OPER}) without re-probing")
        p["reset_threshold_raw"] = int(RESET_THRESHOLD_RAW)
        p["reset_oper"] = str(RESET_OPER)
        p["reset_ground_below"] = bool(RESET_GROUND_BELOW)
    freq_step_mhz = p.get("freq_step_mhz", None)
    if freq_step_mhz is not None:
        if FLUX_FIT_PARAMS is None:
            raise RuntimeError("Step 6 freq_step_mhz needs FLUX_FIT_PARAMS: run step 2 "
                               "and paste the printed values at the top of this file.")
        dc_vec = _build_freq_uniform_dc_vec(p)
    else:
        dc_vec = _dc_vec(p)
    flux_tail_compensation = _load_correction(correction_json, outer_folder)
    wall_clock_s = _wall_clock_seconds(p.get("wall_clock_duration_min", None))
    print(f"[6] 3-point T1 vs flux (distortion-corrected): {len(dc_vec)} DC points, "
          f"{'single pass' if wall_clock_s is None else f'wall-clock {wall_clock_s / 60:.0f} min'}")
    base = _t1_base_cfg(p, flux_tail_compensation, dc_vec)

    def factory(repeat_metadata):
        return T13PointVsFlux(
            soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outer_folder,
            suffix="TLS_3pt_T1_vs_Flux_distortion_corrected", cfg=dict(base),
            dc_vec=dc_vec, Ts_ns=(None if p.get("Ts_us") is None
                                  else int(round(p["Ts_us"] * 1e3))),
            shots=int(p["shots"]), calib_params=calib_params,
            park_voltage=BASELINE_DC_OFFSET,
            min_ref_contrast=float(p.get("min_ref_contrast", 0.05)),
            max_plot_t1_multiple=p.get("max_plot_t1_multiple", 20.0),
            auto_Ts_factor=float(p.get("auto_Ts_factor", 0.5)),
            T1_probe_cfg=p.get("T1_probe_cfg", None),
            run_park_T1_if_Ts_none=bool(p.get("run_park_T1_if_Ts_none", True)),
            reset_mode=p.get("reset_mode", "passive"),
            flux_tail_compensation=flux_tail_compensation,
            repeat_metadata=repeat_metadata,
            write_outputs=False,
        )

    csv_path = _run_one_stop_t1(factory, wall_clock_s)
    print(f"[6] Done. One-stop 3-point CSV: {csv_path}")


def run_step6_full_t1_vs_flux(outer_folder, soc, soccfg, calib_params, correction_json):
    plt.close("all")
    gc.collect()
    p = P6_FULL_T1
    freq_step_mhz = p.get("freq_step_mhz", None)
    if freq_step_mhz is not None:
        if FLUX_FIT_PARAMS is None:
            raise RuntimeError("Step 6 freq_step_mhz needs FLUX_FIT_PARAMS: run step 2 "
                               "and paste the printed values at the top of this file.")
        dc_vec = _build_freq_uniform_dc_vec(p)
    else:
        dc_vec = _dc_vec(p)
    flux_tail_compensation = _load_correction(correction_json, outer_folder)
    wall_clock_s = _wall_clock_seconds(p.get("wall_clock_duration_min", None))
    print(f"[6] Full T1 vs flux (distortion-corrected): {len(dc_vec)} DC points, "
          f"{'single pass' if wall_clock_s is None else f'wall-clock {wall_clock_s / 60:.0f} min'}")
    base = _t1_base_cfg(p, flux_tail_compensation, dc_vec)

    q_factor = p.get("quality_factor", None)
    notebook_fit = fx.flux_fit_params_to_notebook(FLUX_FIT_PARAMS) if q_factor is not None else None
    if q_factor is not None:
        tilt = float(FLUX_FIT_PARAMS[5]) if len(FLUX_FIT_PARAMS) > 5 else 0.0
        if abs(tilt) > 1e-9:
            print(f"[6] WARNING: FLUX_FIT_PARAMS tilt={tilt:+.4g} GHz/V is ignored by the per-dc Q t_max "
                  f"model (it uses the tilt-free transmon form).")
        print(f"[6] per-dc t_max from supplied Q = {q_factor:g}: "
              f"t_max(dc) = {float(p.get('auto_tmax_factor', 3.0)):g} x Q/(2*pi*f(dc)) using the flux fit")

    def factory(repeat_metadata):
        common = dict(soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outer_folder,
                      suffix="TLS_Full_T1_vs_Flux_distortion_corrected", cfg=dict(base),
                      dc_vec=dc_vec, shots=int(p["shots"]), calib_params=calib_params,
                      park_voltage=BASELINE_DC_OFFSET,
                      auto_tmax_factor=float(p.get("auto_tmax_factor", 3.0)),
                      T1_probe_cfg=p.get("T1_probe_cfg", None),
                      t_min_ns_default=float(p.get("t_min_us_default", 1.0)) * 1e3,
                      t_points_default=int(p.get("t_points_default", 41)),
                      reset_mode=p.get("reset_mode", "passive"),
                      flux_tail_compensation=flux_tail_compensation,
                      repeat_metadata=repeat_metadata,
                      write_outputs=False)
        if q_factor is not None:
            return T1FullCurveVsFluxFromFit(notebook_fit_params=notebook_fit,
                                            quality_factor=q_factor, **common)
        t_max_us = p.get("t_max_us", None)
        return T1FullCurveVsFlux(t_max_ns=(None if t_max_us is None else t_max_us * 1e3),
                                 **common)

    csv_path = _run_one_stop_t1(factory, wall_clock_s)
    print(f"[6] Done. One-stop CSV: {csv_path}")


def main():
    _set_yoko_if_requested()
    soc, soccfg = makeProxy()
    outer_folder = outerFolder

    print("=" * 70)
    print(f"TLS spectroscopy pipeline | {QUBIT} | chip {CHIP_NAME_FOR_CONFIG}")
    print(f"park/baseline = {BASELINE_DC_OFFSET:+.0f} DAC | distortion-probe target = {TARGET_DC_OFFSET:+.0f} DAC")
    print(f"qubit-spec readout-IF source = {'measured-dip lookup' if USE_RESONATOR_LOOKUP else 'cosine fit'}")
    steps_enabled = [
        ("1_resonator_spec_vs_flux", P1_RESONATOR["run"]),
        ("2_qubit_spec_vs_flux_full_range", P2_QUBIT_SPEC_FULL["run"]),
        ("3a_step_response_fit", P3_STEP_RESPONSE["run_fit"]),
        ("3b_step_response_correct", P3_STEP_RESPONSE["run_correct"]),
        ("4_long_time_spec_vs_flux", P4_LONG_TIME["run"]),
        ("5_single_shot_cal", P5_SS_CAL["run"]),
        ("6_3pt_t1_vs_flux", P6_3PT_T1["run"]),
    ]
    for name, on in steps_enabled:
        print(f"  {'[x]' if on else '[ ]'} {name}")
    print("=" * 70)

    if CAL_RES_PHASE:
        calibrate_res_phase(soc, soccfg, BaseConfig, QUBIT, outer_folder, apply_config=True)

    correction_json = None
    calib_params = None
    latest_resonator_lookup_csv = None

    if P1_RESONATOR["run"]:
        latest_resonator_lookup_csv = run_step1_resonator_spec(outer_folder, soc, soccfg)
    if P2_QUBIT_SPEC_FULL["run"]:
        run_step2_qubit_spec_full_range(
            outer_folder, soc, soccfg, _resolve_resonator_lookup(latest_resonator_lookup_csv))
    if P3_STEP_RESPONSE["run_fit"]:
        correction_json = run_step3a_step_response_fit(outer_folder, soc, soccfg)
    if P3_STEP_RESPONSE["run_correct"]:
        correction_json = run_step3b_step_response_correct(outer_folder, soc, soccfg, correction_json)
    if P4_LONG_TIME["run"]:
        run_step4_long_time_spec(
            outer_folder, soc, soccfg, correction_json,
            _resolve_resonator_lookup(latest_resonator_lookup_csv))
    if P5_SS_CAL["run"]:
        calib_params = run_step5_single_shot_cal(outer_folder, soc, soccfg)
    if P6_3PT_T1["run"]:
        if calib_params is None:
            print("[6] Step 5 was skipped; running single-shot calibration for the T1.")
            calib_params = run_step5_single_shot_cal(outer_folder, soc, soccfg)
        run_step6_3pt_t1(outer_folder, soc, soccfg, calib_params, correction_json)

    print("\nTLS spectroscopy pipeline complete.")


if __name__ == "__main__":
    main()
