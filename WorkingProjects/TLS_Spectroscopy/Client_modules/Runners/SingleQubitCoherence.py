import gc

import numpy as np
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt

from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.socProxy import makeProxy
from WorkingProjects.TLS_Spectroscopy.Client_modules.Calib.initialize import BaseConfig, outerFolder
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mSingleShot1Q import SingleShot1Q
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mCoherence import T1
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.active_reset import probe_reset_params

QUBIT = "q4"
CHIP_NAME_FOR_CONFIG = "FTTv02_SiOxJJ"
LIVE_PLOTS = True

FF_HOLD_GAIN = 0
READOUT_AFTER_PARK = True

RESET_MODE = "feedback"
PROBE_RESET = True
RESET_THRESHOLD_RAW = 7087
RESET_OPER = "lower"
RESET_GROUND_BELOW = True
RESET_MAX_ITERS = 3
THERMALIZATION_US = 25.0
PASSIVE_RESET_US = 1000.0

P_SS_CAL = {
    "run": True,
    "shots": 1000,
    "number_pi_pulses": 1,
    "ground_threshold": 0.7,
}

P_T1 = {
    "run": True,
    "shots": 1000,
    "t_min_us": 1.0,
    "t_max_us": 300.0,
    "t_points": 61,
}

P_T1_FLUX_RAMP = {
    "run": False,
    "shots": 1000,
    "excursion_gain": 8000,
    "t_min_us": 1.0,
    "t_max_us": 300.0,
    "t_points": 61,
}


def _base_cfg(p, extra=None):
    cfg = dict(BaseConfig)
    cfg["shots"] = int(p["shots"])
    cfg["reps"] = int(p["shots"])
    cfg["ff_gain"] = int(FF_HOLD_GAIN)
    cfg["ff_hold_gain"] = int(FF_HOLD_GAIN)
    cfg["readout_after_park"] = bool(READOUT_AFTER_PARK)
    cfg["reset_mode"] = RESET_MODE
    if RESET_MODE == "feedback":
        if RESET_THRESHOLD_RAW is None:
            raise RuntimeError("RESET_MODE='feedback' needs a reset threshold, but the "
                               "start-of-run probe did not set one.")
        cfg["reset_threshold_raw"] = int(RESET_THRESHOLD_RAW)
        cfg["reset_oper"] = str(RESET_OPER)
        cfg["reset_ground_below"] = bool(RESET_GROUND_BELOW)
        cfg["reset_max_iters"] = int(RESET_MAX_ITERS)
        cfg["reset_thermalization_us"] = THERMALIZATION_US
    if extra:
        cfg.update(extra)
    cfg["relax_delay"] = (THERMALIZATION_US if str(cfg.get("reset_mode")) == "feedback"
                          else PASSIVE_RESET_US)
    return cfg


def _log_t_vec(p):
    return np.logspace(np.log10(max(float(p["t_min_us"]), 0.016)),
                       np.log10(float(p["t_max_us"])), int(p["t_points"]))


def run_ss_cal(outer_folder, soc, soccfg):
    p = P_SS_CAL
    cfg = _base_cfg(p, extra={"reset_mode": "passive"})
    cfg["qubit_gain"] = int(cfg["qubit_pi_gain"])
    print(f"[SS] single-shot readout calibration ({p['shots']} shots, "
          f"{p['number_pi_pulses']}x pi prep)")
    ss = SingleShot1Q(soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outer_folder,
                      suffix="SS_Cal", cfg=cfg, repeats=int(p["number_pi_pulses"]),
                      confidence_threshold=float(p["ground_threshold"]))
    ss.acquire(progress=True, plotDisp=LIVE_PLOTS)
    print(f"[SS] fidelity F = {ss.max_F:.4f}; calib_params = {ss.calib_params}")
    plt.close("all"); gc.collect()
    return ss.calib_params


def run_t1(outer_folder, soc, soccfg, calib_params):
    p = P_T1
    cfg = _base_cfg(p)
    exp = T1(soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outer_folder, suffix="T1",
             cfg=cfg, calib_params=calib_params, t_vec_us=_log_t_vec(p), ff_gain=0.0,
             reset_mode=RESET_MODE, live_plot=LIVE_PLOTS)
    exp.acquire(progress=True, plotDisp=LIVE_PLOTS)
    plt.close("all"); gc.collect()
    return exp


def run_t1_flux_ramp(outer_folder, soc, soccfg, calib_params):
    p = P_T1_FLUX_RAMP
    cfg = _base_cfg(p)
    exp = T1(soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outer_folder,
             suffix="T1_Flux_Ramp", cfg=cfg, calib_params=calib_params,
             t_vec_us=_log_t_vec(p), ff_gain=float(p["excursion_gain"]),
             reset_mode=RESET_MODE, live_plot=LIVE_PLOTS)
    exp.acquire(progress=True, plotDisp=LIVE_PLOTS)
    plt.close("all"); gc.collect()
    return exp


def main():
    soc, soccfg = makeProxy()
    outer_folder = outerFolder

    global RESET_MODE, RESET_THRESHOLD_RAW, RESET_OPER, RESET_GROUND_BELOW
    if RESET_MODE == "feedback" and PROBE_RESET:
        rec = probe_reset_params(soc, soccfg, BaseConfig, path=QUBIT,
                                 outer_folder=outer_folder)
        if rec is None:
            RESET_MODE = "passive"
            print(f"[reset] no feedback discrimination this session -> passive reset "
                  f"({PASSIVE_RESET_US:.0f}us). Verify it exceeds ~5x T1.")
        else:
            RESET_THRESHOLD_RAW = int(rec["threshold_raw"])
            RESET_OPER = str(rec["oper"])
            RESET_GROUND_BELOW = bool(rec["ground_below"])
    elif RESET_MODE == "feedback":
        print(f"[reset] PROBE_RESET=False -> reusing threshold_raw={RESET_THRESHOLD_RAW} "
              f"({RESET_OPER}) without re-probing")

    print("=" * 70)
    print(f"single-qubit coherence | {QUBIT} | chip {CHIP_NAME_FOR_CONFIG} | "
          f"{'PARK' if FF_HOLD_GAIN == 0 else f'held ff_gain={FF_HOLD_GAIN}'}")
    for name, on in [("SS_Cal", P_SS_CAL["run"]),
                     ("T1", P_T1["run"]),
                     ("T1_Flux_Ramp", P_T1_FLUX_RAMP["run"])]:
        print(f"  {'[x]' if on else '[ ]'} {name}")
    print("=" * 70)

    calib_params = None
    if P_SS_CAL["run"]:
        calib_params = run_ss_cal(outer_folder, soc, soccfg)
    if P_T1["run"]:
        if calib_params is None:
            print("[SS] T1 needs a single-shot calibration; running SS_Cal first.")
            calib_params = run_ss_cal(outer_folder, soc, soccfg)
        run_t1(outer_folder, soc, soccfg, calib_params)
    if P_T1_FLUX_RAMP["run"]:
        if calib_params is None:
            print("[SS] T1_Flux_Ramp needs a single-shot calibration; running SS_Cal first.")
            calib_params = run_ss_cal(outer_folder, soc, soccfg)
        run_t1_flux_ramp(outer_folder, soc, soccfg, calib_params)

    print("\nsingle-qubit coherence complete.")


if __name__ == "__main__":
    main()
