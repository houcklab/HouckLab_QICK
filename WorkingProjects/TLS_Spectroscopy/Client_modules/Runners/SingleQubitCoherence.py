import gc
from datetime import datetime
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt

from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.socProxy import makeProxy
from WorkingProjects.TLS_Spectroscopy.Client_modules.Calib.initialize import BaseConfig, outerFolder
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mSingleShot1Q import (
    SingleShot1Q, SingleShotFluxRamp)
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mCoherence import T1
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import active_reset, ff_pulse
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.active_reset import probe_reset_params
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.reset_phase import calibrate_res_phase
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.benchmark_settings import (
    q3_benchmark_settings,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.calibration import (
    acquire_calibration,
    save_calibration,
    save_raw_calibration,
    validate_confident_calibration,
)

QUBIT = "q3"
CHIP_NAME_FOR_CONFIG = "FTTv02_AlOxJJ"
LIVE_PLOTS = True

FF_HOLD_GAIN = 0
READOUT_AFTER_PARK = True

RESET_MODE = "opx_unbounded"
PROBE_RESET = True
ROT_RESET_PARAMS = None
OPX_RESET_CALIBRATION = None
OPX_CALIBRATION_SHOTS = 2000
OPX_MIN_CONFIDENT_STATE_FRACTION = 0.2
OPX_HOST_WATCHDOG_S = 2.0
CAL_RES_PHASE = False
RESET_THRESHOLD_RAW = None
RESET_OPER = "lower"
RESET_GROUND_BELOW = False
RESET_MAX_ITERS = 3
RANDOMIZE_POINT_ORDER = True
POINT_ORDER_SEED = None
THERMALIZATION_US = 2.0
FEEDBACK_RELAX_US = 25.0
PASSIVE_RESET_US = 1000.0
CALIBRATE_DRIFT_PI = True
DRIFT_PI_PROFILE = None

P_SS_CAL = {
    "run": False,
    "shots": 1000,
    "number_pi_pulses": 1,
    "ground_threshold": 0.7,
}

P_SS_FLUX_RAMP = {
    "run": False,
    "shots": 1000,
    "number_pi_pulses": 1,
    "ground_threshold": 0.7,
    "excursion_gain": 8000,
    "qubit_pi_gain": None,
    "flux_hold_us": 1.0,
    "flux_tail_compensation": None,
}

P_T1 = {
    "run": False,
    "shots": 1000,
    "t_min_us": 1.0,
    "t_max_us": 1000.0,
    "t_points": 71,
}

P_T1_FLUX_RAMP = {
    "run": True,
    "shots": 1000,
    "excursion_gain": -20000,
    "flux_tail_compensation": None,
    "t_min_us": 1.0,
    "t_max_us": 1000.0,
    "t_points": 71,
}


def _base_cfg(p, extra=None):
    cfg = dict(BaseConfig)
    cfg["shots"] = int(p["shots"])
    cfg["reps"] = int(p["shots"])
    cfg["ff_gain"] = int(FF_HOLD_GAIN)
    cfg["ff_hold_gain"] = int(FF_HOLD_GAIN)
    cfg["readout_after_park"] = bool(READOUT_AFTER_PARK)
    cfg["randomize_point_order"] = bool(RANDOMIZE_POINT_ORDER)
    cfg["point_order_seed"] = POINT_ORDER_SEED
    cfg["reset_mode"] = RESET_MODE
    if extra:
        cfg.update(extra)
    if active_reset.uses_opx_unbounded(cfg):
        if OPX_RESET_CALIBRATION is None:
            raise RuntimeError("opx_unbounded reset needs a same-session calibration")
        cfg["opx_reset_calibration"] = dict(OPX_RESET_CALIBRATION)
        cfg.update(q3_benchmark_settings().opx_overrides())
        cfg["opx_unbounded_watchdog_s"] = float(OPX_HOST_WATCHDOG_S)
        cfg["opx_inter_shot_delay_us"] = float(FEEDBACK_RELAX_US)
    elif active_reset.uses_feedback(cfg):
        if not ROT_RESET_PARAMS:
            raise RuntimeError("feedback reset needs a validated rotated reset profile")
        if RESET_THRESHOLD_RAW is None:
            raise RuntimeError(f"RESET_MODE={RESET_MODE!r} needs a reset threshold, but "
                               "the start-of-run probe did not set one.")
        cfg["reset_threshold_raw"] = int(RESET_THRESHOLD_RAW)
        cfg["reset_oper"] = str(RESET_OPER)
        cfg["reset_ground_below"] = bool(RESET_GROUND_BELOW)
        cfg["rot_reset"] = dict(ROT_RESET_PARAMS)
        cfg["reset_max_iters"] = int(RESET_MAX_ITERS)
        cfg["reset_thermalization_us"] = THERMALIZATION_US
        if DRIFT_PI_PROFILE:
            active_reset.apply_drift_pi(cfg, {"drift_pi": DRIFT_PI_PROFILE})
    cfg["relax_delay"] = (FEEDBACK_RELAX_US if active_reset.uses_feedback(cfg)
                          else PASSIVE_RESET_US)
    return cfg


def _log_t_vec(p):
    return np.logspace(np.log10(max(float(p["t_min_us"]), 0.016)),
                       np.log10(float(p["t_max_us"])), int(p["t_points"]))


def _calibrate_opx_reset(outer_folder, soc, soccfg):
    cfg = dict(BaseConfig)
    cfg.update(q3_benchmark_settings().opx_overrides())
    cfg["relax_delay"] = float(PASSIVE_RESET_US)
    cfg["opx_inter_shot_delay_us"] = float(FEEDBACK_RELAX_US)
    cfg["opx_unbounded_watchdog_s"] = float(OPX_HOST_WATCHDOG_S)
    now = datetime.now()
    output = (
        Path(outer_folder)
        / QUBIT
        / f"{QUBIT}_{now:%Y_%m_%d}"
        / f"{QUBIT}_{now:%H_%M_%S}_active_reset_OPX_production_calibration"
    )
    output.mkdir(parents=True, exist_ok=False)
    bundle, raw = acquire_calibration(
        soc,
        soccfg,
        cfg,
        shots=int(OPX_CALIBRATION_SHOTS),
        **q3_benchmark_settings().calibration_options(),
        metadata={
            "qubit": QUBIT,
            "created": now.isoformat(),
            "purpose": "SingleQubitCoherence opx_unbounded",
        },
    )
    save_calibration(output / "calibration.json", bundle)
    save_raw_calibration(output / "calibration_raw.npz", raw)
    validate_confident_calibration(
        bundle,
        min_confident_fraction=OPX_MIN_CONFIDENT_STATE_FRACTION,
    )
    print(f"[reset] OPX calibration saved: {output}")
    return bundle.to_dict()


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


def run_ss_flux_ramp(outer_folder, soc, soccfg):
    p = P_SS_FLUX_RAMP
    cfg = _base_cfg(p, extra={"reset_mode": "passive"})
    if p.get("qubit_pi_gain") is not None:
        cfg["ss_flux_pi_gain"] = int(p["qubit_pi_gain"])
    comp = p.get("flux_tail_compensation")
    if comp is not None:
        cfg["flux_tail_compensation"] = comp
    print(f"[SS flux ramp] park pi {float(cfg['qubit_pi_freq']):.6f} MHz at gain "
          f"{int(cfg.get('ss_flux_pi_gain', cfg['qubit_pi_gain']))}, then "
          f"ff_gain={p['excursion_gain']}, ramp "
          f"{cfg.get('ff_ramp_length', ff_pulse.STATE_SAFE_RAMP_US):g} us, hold "
          f"{float(p['flux_hold_us']):g} us, predistortion "
          f"{'ON' if comp is not None else 'OFF'}")
    ss = SingleShotFluxRamp(
        soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outer_folder,
        suffix="SS_Cal_Flux_Ramp", cfg=cfg,
        repeats=int(p["number_pi_pulses"]),
        confidence_threshold=float(p["ground_threshold"]),
        ff_gain=float(p["excursion_gain"]),
        flux_hold_us=float(p["flux_hold_us"]))
    ss.acquire(progress=True, plotDisp=LIVE_PLOTS)
    print(f"[SS flux ramp] fidelity F = {ss.max_F:.4f}; "
          f"calib_params = {ss.calib_params}")
    plt.close("all"); gc.collect()
    return ss.calib_params


def run_t1(outer_folder, soc, soccfg, calib_params):
    p = P_T1
    cfg = _base_cfg(p)
    exp = T1(soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outer_folder, suffix="T1",
             cfg=cfg, calib_params=calib_params, t_vec_us=_log_t_vec(p),
             ff_gain=float(cfg.get("ff_park_gain", 0) or 0),
             reset_mode=RESET_MODE, live_plot=LIVE_PLOTS)
    exp.acquire(progress=True, plotDisp=LIVE_PLOTS)
    plt.close("all"); gc.collect()
    return exp


def run_t1_flux_ramp(outer_folder, soc, soccfg, calib_params):
    p = P_T1_FLUX_RAMP
    cfg = _base_cfg(p)
    comp = p.get("flux_tail_compensation", None)
    if comp is not None:
        cfg["flux_tail_compensation"] = comp
    print(f"[T1 flux ramp] ff_gain={p['excursion_gain']}, ramp "
          f"{cfg.get('ff_ramp_length', ff_pulse.STATE_SAFE_RAMP_US):g} us, settle "
          f"{ff_pulse.flux_settle_us(cfg):g} us, "
          f"predistortion {'ON' if comp is not None else 'OFF'}")
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
    global ROT_RESET_PARAMS, DRIFT_PI_PROFILE, OPX_RESET_CALIBRATION
    opx_requested = active_reset.uses_opx_unbounded(RESET_MODE)
    feedback_requested = active_reset.uses_feedback(RESET_MODE) and not opx_requested
    DRIFT_PI_PROFILE = None
    if opx_requested:
        if not PROBE_RESET and OPX_RESET_CALIBRATION is None:
            raise RuntimeError(
                "RESET_MODE='opx_unbounded' needs PROBE_RESET=True or an explicit "
                "OPX_RESET_CALIBRATION"
            )
        if PROBE_RESET:
            OPX_RESET_CALIBRATION = _calibrate_opx_reset(
                outer_folder, soc, soccfg
            )
    if CAL_RES_PHASE:
        print("[reset] NOTE: res_phase calibration only matters for the LEGACY "
              "single-quadrature reset; the rotated reset (the default) measures "
              "its own projection angle every probe and does not need it.")
        best = calibrate_res_phase(soc, soccfg, BaseConfig, QUBIT, outer_folder,
                                   apply_config=False)
        if best is not None:
            BaseConfig["res_phase"] = float(best)
            print(f"[res-phase] applied res_phase={best:.1f} deg for this session "
                  f"(aligns |g>/|e> on one raw quadrature; initialize.py unchanged)")
    if feedback_requested and PROBE_RESET:
        rec = active_reset.load_reset_profile(
            BaseConfig, path=QUBIT, outer_folder=outer_folder)
        if rec is None:
            rec = probe_reset_params(soc, soccfg, BaseConfig, path=QUBIT,
                                     outer_folder=outer_folder,
                                     reset_max_iters=int(RESET_MAX_ITERS))
            active_reset.save_reset_profile(
                rec, BaseConfig, path=QUBIT, outer_folder=outer_folder)
        if rec is None:
            RESET_MODE = "passive"
            ROT_RESET_PARAMS = None
            print(f"[reset] no feedback discrimination this session -> passive reset "
                  f"({PASSIVE_RESET_US:.0f}us). Verify it exceeds ~5x T1.")
        elif active_reset.rotated_probe_record(rec):
            RESET_THRESHOLD_RAW = int(rec["threshold_raw"])
            RESET_OPER = str(rec["oper"])
            RESET_GROUND_BELOW = bool(rec["ground_below"])
            ROT_RESET_PARAMS = dict(rec["rot_reset"])
            if rec.get("degraded"):
                print("[reset] ROTATED reset selected BEST-EFFORT: functional "
                      "but above the validated bar this probe.")
            else:
                print("[reset] ROTATED reset selected (probe-validated).")
            DRIFT_PI_PROFILE = rec.get("drift_pi")
            if DRIFT_PI_PROFILE is not None and not active_reset.drift_pi_matches(
                    DRIFT_PI_PROFILE, BaseConfig, FEEDBACK_RELAX_US,
                    RESET_MAX_ITERS, THERMALIZATION_US):
                print("[reset] the cached drift-pi calibration was taken at different "
                      "reset timing or relax; re-calibrating")
                DRIFT_PI_PROFILE = None
                rec.pop("drift_pi", None)
            if DRIFT_PI_PROFILE is None and CALIBRATE_DRIFT_PI:
                DRIFT_PI_PROFILE = active_reset.calibrate_drift_pi(
                    soc, soccfg, BaseConfig, rec,
                    max_iters=int(RESET_MAX_ITERS),
                    thermalization_us=THERMALIZATION_US,
                    passive_relax_us=PASSIVE_RESET_US,
                    feedback_relax_us=FEEDBACK_RELAX_US)
                if DRIFT_PI_PROFILE is not None:
                    active_reset.save_reset_profile(
                        rec, BaseConfig, path=QUBIT, outer_folder=outer_folder)
        else:
            RESET_MODE = "passive"
            ROT_RESET_PARAMS = None
            print(f"[reset] rotated reset did not validate -> passive reset "
                  f"({PASSIVE_RESET_US:.0f}us).")
    elif feedback_requested:
        if ROT_RESET_PARAMS and RESET_THRESHOLD_RAW is not None:
            print("[reset] PROBE_RESET=False -> using the configured rotated reset "
                  "profile without re-probing")
        else:
            RESET_MODE = "passive"
            print(f"[reset] no configured rotated reset profile -> passive reset "
                  f"({PASSIVE_RESET_US:.0f}us).")

    print("=" * 70)
    print(f"single-qubit coherence | {QUBIT} | chip {CHIP_NAME_FOR_CONFIG} | "
          f"{'PARK' if FF_HOLD_GAIN == 0 else f'held ff_gain={FF_HOLD_GAIN}'}")
    for name, on in [("SS_Cal", P_SS_CAL["run"]),
                     ("SS_Cal_Flux_Ramp", P_SS_FLUX_RAMP["run"]),
                     ("T1", P_T1["run"]),
                     ("T1_Flux_Ramp", P_T1_FLUX_RAMP["run"])]:
        print(f"  {'[x]' if on else '[ ]'} {name}")
    print("=" * 70)

    calib_params = None
    if P_SS_CAL["run"]:
        calib_params = run_ss_cal(outer_folder, soc, soccfg)
    if P_SS_FLUX_RAMP["run"]:
        run_ss_flux_ramp(outer_folder, soc, soccfg)
    if P_T1["run"]:
        if calib_params is None:
            print("[SS] T1 needs a single-shot calibration; running SS_Cal first.")
            calib_params = run_ss_cal(outer_folder, soc, soccfg)
        run_t1(outer_folder, soc, soccfg, calib_params)
    if P_T1_FLUX_RAMP["run"]:
        if calib_params is None:
            print("[SS] T1_Flux_Ramp needs a park single-shot calibration; "
                  "running SS_Cal first.")
            calib_params = run_ss_cal(outer_folder, soc, soccfg)
        run_t1_flux_ramp(outer_folder, soc, soccfg, calib_params)

    print("\nsingle-qubit coherence complete.")


if __name__ == "__main__":
    main()
