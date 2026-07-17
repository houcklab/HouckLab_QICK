"""
TLS spectroscopy pipeline -- QICK port of Houck-Lab-Qua/.../Flux_Tunable/TLSSpectroscopy.py,
kept STRUCTURALLY IDENTICAL to the QUA original: same steps in the same order
(1 -> 2 -> 3a -> 3b -> 4 -> 5 -> 6), same top-level constants, same param-dict
knobs, same artifact threading, same printouts.

Unit translation (the only difference from QUA -- the flux actuator changed):
  - flux axis  : OPX DC volts  ->  fast-flux DAC gain units (ff_ch = gen 3);
                 keys keep their QUA names (dc_min/dc_max/dc_step, BASELINE/
                 TARGET_DC_OFFSET) but hold DAC-gain values.
  - frequencies: OPX IF Hz (LO-relative)  ->  absolute MHz (freq_min/max/step).
  - times      : ns keys -> _us keys with microsecond values.
  - spec_amp   : OPX volts -> DAC gain units.

Run from the HouckLab_QICK repo root on the measurement PC:
    python -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSSpectroscopy
"""

import gc

import numpy as np
import matplotlib.pyplot as plt

from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.socProxy import makeProxy
from WorkingProjects.TLS_Spectroscopy.Client_modules.Calib.initialize import BaseConfig, outerFolder
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mTransmissionVsFFGain import TransmissionVsFFGain
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mQubitLongTimeSpecVsFlux import QubitLongTimeSpecVsFlux
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mQubitFluxStepResponse import QubitFluxStepResponse
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mSingleShot1Q import SingleShot1Q
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mT1VsFlux import (
    T13PointVsFlux, T1FullCurveVsFlux, run_wall_clock_repeat,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import flux_fit as fx
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import flux_predistortion as fpd


LIVE_PLOTS = True

CHIP_NAME_FOR_CONFIG = "FTTv02_SiOxJJ"
QUBIT = "q4"


SET_YOKO = False
YOKO_VISA = "USB0::0x0B21::0x0039::91S929899::0::INSTR"
YOKO_VOLTAGE = 0.0


# Flux -> qubit-frequency fit, [EJmax(GHz), Ec(GHz), period, offset, d, tilt] with
# the flux axis in ff_gain DAC units.  None until measured: run step 2, then paste
# the printed FLUX_FIT_PARAMS here (same workflow as QUA, where step 2 printed the
# paste-ready values for this spot).
FLUX_FIT_PARAMS = None

BASELINE_DC_OFFSET = 0        # ff DAC units (park level; QUA: OPX volts)
TARGET_DC_OFFSET = 8000       # ff DAC units (step-3 distortion-probe target)
FLUX_TAIL_COMPENSATION_GAIN = 0.75

SAVE_RESONATOR_LOOKUP = True
USE_RESONATOR_LOOKUP = False
RESONATOR_LOOKUP_CSV = None


P1_RESONATOR = {
    "run": False,
    "shots": 200,
    "freq_min": 7245.0,       # MHz absolute (QUA: IF relative to r_LO)
    "freq_max": 7252.0,
    "freq_step": 0.05,
    "dc_min": 0,              # ff DAC units (QUA: volts)
    "dc_max": 12000,
    "dc_step": 300,
    "lookup_smooth_points": None,
}

P2_QUBIT_SPEC_FULL = {
    "run": False,
    "advanced_fit": True,
    "shots": 100,
    "spec_amp": 7000,         # DAC units (QUA: OPX volts)
    "spec_len_us": 0.5,       # us (QUA: spec_len in ns)
    "freq_min": 2250.0,       # MHz absolute
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
    "freq_step": 2.0,
    "auto_center_frequency_window": True,
    "auto_freq_absolute_min_mhz": 2250.0,
    "auto_freq_absolute_max_mhz": 2570.0,
    "t_min_us": 1.0,
    "t_max_us": 200.0,
    "t_step_us": 4.0,
    "baseline_rearm_us": 100.0,
    "piecewise_min_multiplier": 0.5,
    "piecewise_max_multiplier": 1.5,
    "live_plot": True,
}

P4_LONG_TIME = {
    "run": False,
    "advanced_fit": False,
    "shots": 100,
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
}

# P6_FULL_T1 = {
#     "run": False,
#     "shots": 300,
#     "dc_min": 0,
#     "dc_max": 12000,
#     "dc_step": 60,
#     "freq_step_mhz": 2,
#     "wall_clock_duration_min": 2880,
#     "auto_tmax_factor": 3.0,
#     "t_max_us": None,
#     "t_min_us_default": 1.0,
#     "t_points_default": 21,
#     "reset_mode": "active",
#     "T1_probe_cfg": {
#         "shots_T1": 300,
#         "t_min_us": 1.0,
#         "t_max_us": 300.0,
#         "t_points": 21,
#         "num_pulses": 1,
#     },
# }

P6_3PT_T1 = {
    "run": False,
    "shots": 2000,
    "dc_min": 0,
    "dc_max": 12000,
    "dc_step": 60,
    "freq_step_mhz": 1,
    "wall_clock_duration_min": None,
    "Ts_us": 100.0,           # (QUA: Ts_ns = 100 us)
    "auto_Ts_factor": 0.5,
    "run_park_T1_if_Ts_none": True,
    "min_ref_contrast": 0.05,
    "max_plot_t1_multiple": 20.0,
    "reset_mode": "active",   # QICK analog: herald + post-selection
    "T1_probe_cfg": {
        "shots_T1": 1000,
        "t_min_us": 1.0,
        "t_max_us": 300.0,
        "t_points": 71,
        "num_pulses": 1,
    },
}

STEP3B_GAIN_SWEEP = None      # e.g. [0.5, 0.75, 1.0] -> gain sweep in step 3b


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
    """BaseConfig + a P-dict's spec knobs (QUA _spec_meta_dict analog)."""
    cfg = dict(BaseConfig)
    cfg["reps"] = int(p["shots"])
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


def _wall_clock_minutes(duration_min):
    if duration_min is None:
        return None
    duration_min = float(duration_min)
    return duration_min if duration_min > 0 else None


def _resolve_resonator_lookup(latest_lookup_csv):
    if not USE_RESONATOR_LOOKUP:
        return None
    lookup_csv = RESONATOR_LOOKUP_CSV or latest_lookup_csv
    if lookup_csv is None:
        raise RuntimeError(
            "USE_RESONATOR_LOOKUP=True but no lookup CSV is available. Run step 1 "
            "(resonator spec) in this same session, or set RESONATOR_LOOKUP_CSV to a "
            "saved *_resonator_lookup.csv path."
        )
    return lookup_csv


def _dc_vec(p):
    return np.arange(p["dc_min"], p["dc_max"], p["dc_step"])


def _freq_vec_mhz(p):
    return np.arange(p["freq_min"], p["freq_max"], p["freq_step"])


def _auto_freq_window(p, dc_baseline, dc_target):
    """QUA auto_center_frequency_window: center the spec window on the expected
    baseline->target frequency band from the flux fit, clipped to absolute limits."""
    if not (p.get("auto_center_frequency_window", True) and FLUX_FIT_PARAMS is not None):
        return p["auto_freq_absolute_min_mhz"], p["auto_freq_absolute_max_mhz"]
    f = fx.estimate_fit_frequency_ghz_array(
        FLUX_FIT_PARAMS, np.array([float(dc_baseline), float(dc_target)])) * 1e3  # MHz
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
    cfg["relax_delay"] = 50           # no qubit excitation; cavity ring-down only
    cfg["trans_freq_start"] = p["freq_min"]
    cfg["trans_freq_stop"] = p["freq_max"]
    cfg["TransNumPoints"] = len(f_vec)
    cfg["ff_gain_vec"] = dc_vec
    cfg["ff_settle_us"] = 20.0
    exp = TransmissionVsFFGain(
        soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outer_folder,
        suffix="Resonator_Spec_vs_Flux", cfg=cfg,
        save_resonator_lookup=SAVE_RESONATOR_LOOKUP,
        resonator_lookup_smooth_points=p.get("lookup_smooth_points", None),
    )
    data = exp.acquire(plotDisp=LIVE_PLOTS)
    exp.save_data(data)
    exp.save_config()
    lookup_csv = data['data'].get('resonator_lookup_csv')
    print("[1] Done. Cosine fit -> resonator_fit_parameters (update the meta dict if the resonator moved).")
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
        "qubit_freq_expts": len(_freq_vec_mhz(p)),
        "ff_gain_vec": dc_vec,
        "long_time_us": 2.0,          # settle-then-probe; no long-time window here
        "average_window_us": 0.0, "average_step_us": 0.016,
        "fit_flux": bool(p.get("advanced_fit", True)),
        "resonator_lookup_csv": resonator_lookup_csv,
    })
    exp = QubitLongTimeSpecVsFlux(
        soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outer_folder,
        suffix="Qubit_Spec_vs_Flux_Full_Range", cfg=cfg, step_tag="2",
    )
    data = exp.acquire(plotDisp=bool(p.get("live_plot", True)) and LIVE_PLOTS)
    exp.save_data(data)
    exp.save_config()
    print(f"[2] Done. raw_sweep CSV (fit offline): {data['data'].get('raw_sweep_csv')}")
    return data['data'].get('flux_fit_params')


def _step3_common_cfg(p):
    fmin, fmax = _auto_freq_window(p, BASELINE_DC_OFFSET, TARGET_DC_OFFSET)
    n = max(int(round((fmax - fmin) / p["freq_step"])) + 1, 5)
    cfg = _spec_cfg(p, extra={
        "qubit_freq_start": fmin, "qubit_freq_stop": fmax, "qubit_freq_expts": n,
        "t_vec_us": np.arange(p["t_min_us"], p["t_max_us"], p["t_step_us"]),
        "ff_gain": TARGET_DC_OFFSET,
        "baseline_dc_offset": BASELINE_DC_OFFSET,
        "dc_offset": TARGET_DC_OFFSET,
        "baseline_rearm_us": p.get("baseline_rearm_us", 0.0),
    })
    return cfg


def run_step3a_step_response_fit(outer_folder, soc, soccfg):
    p = P3_STEP_RESPONSE
    if FLUX_FIT_PARAMS is None:
        raise RuntimeError("Step 3a needs FLUX_FIT_PARAMS: run step 2 and paste the "
                           "printed values at the top of this file.")
    print(f"[3a] Step-response FIT: baseline={BASELINE_DC_OFFSET:+.0f} DAC -> "
          f"target={TARGET_DC_OFFSET:+.0f} DAC (measure + fit the distortion, no correction applied)")
    exp = QubitFluxStepResponse(
        soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outer_folder,
        suffix="Qubit_Flux_Step_Response", cfg=_step3_common_cfg(p),
        flux_fit_params=FLUX_FIT_PARAMS, run_fit=True, qubit_name=QUBIT,
        piecewise_min_multiplier=p["piecewise_min_multiplier"],
        piecewise_max_multiplier=p["piecewise_max_multiplier"],
        correction_gain=1.0,          # undamped fit; gain applied at load time
    )
    data = exp.acquire(plotDisp=bool(p.get("live_plot", True)) and LIVE_PLOTS)
    exp.save_data(data)
    exp.save_config()
    correction_json = data['data'].get('rise_decay_bump_dc_compensation_json')
    if correction_json is None:
        raise RuntimeError("Step-response fit did not save a rise-decay-bump compensation JSON.")
    print(f"[3a] Saved correction JSON: {correction_json}")
    return correction_json


def run_step3b_step_response_correct(outer_folder, soc, soccfg, correction_json=None):
    p = P3_STEP_RESPONSE
    if correction_json is None:
        correction_json = fpd.find_latest_compensation_json(
            outer_folder, QUBIT,
            dc_offset=TARGET_DC_OFFSET, baseline_dc_offset=BASELINE_DC_OFFSET)
        if correction_json is None:
            raise RuntimeError("No correction JSON found; run step 3a (fit) first.")

    def _run_correct(compensation, live_plot):
        cfg = _step3_common_cfg(p)
        cfg["flux_tail_compensation"] = compensation
        exp = QubitFluxStepResponse(
            soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outer_folder,
            suffix="Qubit_Flux_Step_Response", cfg=cfg,
            flux_fit_params=FLUX_FIT_PARAMS, run_fit=False, qubit_name=QUBIT)
        data = exp.acquire(plotDisp=live_plot and LIVE_PLOTS)
        exp.save_data(data)
        exp.save_config()
        return exp, data

    if STEP3B_GAIN_SWEEP is not None:
        print(f"[3b] Step-response CORRECT (gain sweep {STEP3B_GAIN_SWEEP}): applying {correction_json}")
        print("[3b] Live plotting disabled during the gain sweep (multi-run Tk figures crash on Windows).")
        base = fpd.load_compensation_json(correction_json)
        rows = []
        last_exp = None
        for gain in STEP3B_GAIN_SWEEP:
            comp = fpd.scale_compensation_gain(base, float(gain))
            print(f"    gain = {gain}")
            last_exp, data = _run_correct(comp, live_plot=False)
            rows.append([float(gain), float(data['data'].get('residual_flatness_MHz', np.nan))])
        summary_csv = last_exp.iname[:-4] + "_gain_sweep_summary.csv"
        np.savetxt(summary_csv, np.array(rows), delimiter=",",
                   header="flux_tail_compensation_gain,residual_flatness_MHz", comments="")
        print("[3b] Done. Pick the best gain from the *_gain_sweep_summary.csv, then set "
              "FLUX_TAIL_COMPENSATION_GAIN to it for steps 4 & 6.")
        print(f"     {summary_csv}")
    else:
        compensation = _load_correction(correction_json, outer_folder)
        print(f"[3b] Step-response CORRECT (gain {FLUX_TAIL_COMPENSATION_GAIN}): applying {correction_json}")
        _run_correct(compensation, live_plot=bool(p.get("live_plot", True)))
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
        "qubit_freq_expts": len(_freq_vec_mhz(p)),
        "ff_gain_vec": dc_vec,
        "long_time_us": p["long_time_us"],
        "average_window_us": p.get("average_window_us", 0.0),
        "average_step_us": p.get("average_step_us", 0.016),
        "inter_target_wait_us": p.get("inter_target_wait_us", 100.0),
        "fit_flux": bool(p.get("advanced_fit", False)),
        "resonator_lookup_csv": resonator_lookup_csv,
    })
    exp = QubitLongTimeSpecVsFlux(
        soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outer_folder,
        suffix="Qubit_Long_Time_Frequency_vs_Flux", cfg=cfg, step_tag="4",
        flux_tail_compensation=flux_tail_compensation,
    )
    data = exp.acquire(plotDisp=bool(p.get("live_plot", False)) and LIVE_PLOTS)
    exp.save_data(data)
    exp.save_config()
    print(f"[4] Done. raw_sweep CSV (fit offline): {data['data'].get('raw_sweep_csv')}")


def run_step5_single_shot_cal(outer_folder, soc, soccfg):
    cfg = dict(BaseConfig)
    print("[5] Single-shot readout calibration ...")
    cfg["shots"] = int(P5_SS_CAL["ss_shots"])
    cfg["qubit_pulse_style"] = "arb"
    cfg["qubit_gain"] = BaseConfig["qubit_pi_gain"]
    ss = SingleShot1Q(soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outer_folder,
                      suffix="SS_Cal", cfg=cfg, save=True, plot=True, min_F=0.0)
    ss.acquire(plotDisp=LIVE_PLOTS)
    min_F = float(P5_SS_CAL.get("min_F", 0.6))
    if ss.max_F < min_F:
        raise RuntimeError(f"SS cal fidelity {ss.max_F:.3f} < {min_F}; aborting before the T1 step.")
    print(f"[5] SS cal complete (F={ss.max_F:.3f}).")
    return ss.calib_params


def run_step6_3pt_t1(outer_folder, soc, soccfg, calib_params, correction_json):
    plt.close("all")
    gc.collect()
    p = P6_3PT_T1
    freq_step_mhz = p.get("freq_step_mhz", None)
    if freq_step_mhz is not None and FLUX_FIT_PARAMS is not None:
        dc_vec = _build_freq_uniform_dc_vec(p)
    else:
        dc_vec = _dc_vec(p)
    flux_tail_compensation = _load_correction(correction_json, outer_folder)
    wall_clock_min = _wall_clock_minutes(p.get("wall_clock_duration_min", None))
    print(f"[6] 3-point T1 vs flux (distortion-corrected): {len(dc_vec)} DC points, "
          f"{'single pass' if wall_clock_min is None else f'wall-clock {wall_clock_min:.0f} min'}")

    base = dict(BaseConfig)
    base.update({
        "shots": int(p["shots"]),
        "ff_gain_vec": dc_vec,
        "Ts_us": p.get("Ts_us", None),
        "auto_Ts_factor": float(p.get("auto_Ts_factor", 0.5)),
        "run_park_T1_if_Ts_none": bool(p.get("run_park_T1_if_Ts_none", True)),
        "min_ref_contrast": float(p.get("min_ref_contrast", 0.05)),
        "max_plot_t1_multiple": p.get("max_plot_t1_multiple", 20.0),
        "reset_mode": p.get("reset_mode", "active"),
        "T1_probe_cfg": p.get("T1_probe_cfg", None),
        "flux_tail_compensation": flux_tail_compensation,
        "flux_fit_params": FLUX_FIT_PARAMS,
        "relax_delay": 5000,
        "qubit_pulse_style": "arb",
    })

    def factory():
        return T13PointVsFlux(
            soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outer_folder,
            suffix="TLS_3pt_T1_vs_Flux_distortion_corrected", cfg=dict(base),
            calib_params=calib_params)

    if wall_clock_min is not None:
        csv_path = outer_folder + f"/{QUBIT}/TLS_3pt_T1_wall_clock.csv"
        csv_path = run_wall_clock_repeat(factory, "inv_T1_3pt_per_us", dc_vec, csv_path,
                                         duration_min=wall_clock_min)
    else:
        exp = factory()
        exp.acquire(plotDisp=LIVE_PLOTS)
        csv_path = exp.data['data'].get('summary_csv')
    print(f"[6] Done. One-stop 3-point CSV: {csv_path}")


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
        # ("6_full_t1_vs_flux", P6_FULL_T1["run"]),
        ("6_3pt_t1_vs_flux", P6_3PT_T1["run"]),
    ]
    for name, on in steps_enabled:
        print(f"  {'[x]' if on else '[ ]'} {name}")
    print("=" * 70)

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
    # if P6_FULL_T1["run"]:
    #     if calib_params is None:
    #         print("[6] Step 5 was skipped; running single-shot calibration for the T1.")
    #         calib_params = run_step5_single_shot_cal(outer_folder, soc, soccfg)
    #     run_step6_full_t1_vs_flux(outer_folder, soc, soccfg, calib_params, correction_json)
    if P6_3PT_T1["run"]:
        if calib_params is None:
            print("[6] Step 5 was skipped; running single-shot calibration for the T1.")
            calib_params = run_step5_single_shot_cal(outer_folder, soc, soccfg)
        run_step6_3pt_t1(outer_folder, soc, soccfg, calib_params, correction_json)

    print("\nTLS spectroscopy pipeline complete.")


if __name__ == "__main__":
    main()
