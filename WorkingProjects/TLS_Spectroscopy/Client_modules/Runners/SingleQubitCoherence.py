import gc

import numpy as np
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt

from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.socProxy import makeProxy
from WorkingProjects.TLS_Spectroscopy.Client_modules.Calib.initialize import BaseConfig, outerFolder
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mSingleShot1Q import (
    SingleShot1Q, SingleShotFluxRamp)
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mCoherence import (
    T1,
    needs_standalone_ss_calibration,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import ff_pulse
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.production import (
    ProductionResetSession,
    normalize_reset_mode,
    prepare_reset_session,
)

QUBIT = "q3"
CHIP_NAME_FOR_CONFIG = "FTTv02_AlOxJJ"
LIVE_PLOTS = True

FF_HOLD_GAIN = 0
READOUT_AFTER_PARK = True

RESET_MODE = "active"

_RESET_SESSION = ProductionResetSession.passive()

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


def _base_cfg(p, extra=None, active=True):
    cfg = dict(BaseConfig)
    cfg["shots"] = int(p["shots"])
    cfg["reps"] = int(p["shots"])
    cfg["ff_gain"] = int(FF_HOLD_GAIN)
    cfg["ff_hold_gain"] = int(FF_HOLD_GAIN)
    cfg["readout_after_park"] = bool(READOUT_AFTER_PARK)
    cfg["relax_delay"] = 1000.0
    if extra:
        cfg.update(extra)
    session = _RESET_SESSION if active else ProductionResetSession.passive()
    return session.apply(cfg)


def _log_t_vec(p):
    return np.logspace(np.log10(max(float(p["t_min_us"]), 0.016)),
                       np.log10(float(p["t_max_us"])), int(p["t_points"]))


def run_ss_cal(outer_folder, soc, soccfg):
    p = P_SS_CAL
    cfg = _base_cfg(p, active=False)
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
    cfg = _base_cfg(p, active=False)
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
             reset_mode=cfg["reset_mode"], live_plot=LIVE_PLOTS)
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
             reset_mode=cfg["reset_mode"], live_plot=LIVE_PLOTS)
    exp.acquire(progress=True, plotDisp=LIVE_PLOTS)
    plt.close("all"); gc.collect()
    return exp


def main():
    soc, soccfg = makeProxy()
    outer_folder = outerFolder

    global _RESET_SESSION
    active_measurement = bool(P_T1["run"] or P_T1_FLUX_RAMP["run"])
    if active_measurement and normalize_reset_mode(RESET_MODE) == "opx_unbounded":
        _RESET_SESSION = prepare_reset_session(
            RESET_MODE,
            outer_folder=outer_folder,
            qubit=QUBIT,
            base_cfg=BaseConfig,
            soc=soc,
            soccfg=soccfg,
            purpose="SingleQubitCoherence",
        )
        print(f"[reset] automatic calibration saved: {_RESET_SESSION.calibration_output}")
    else:
        _RESET_SESSION = ProductionResetSession.passive()

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
        if calib_params is None and needs_standalone_ss_calibration(
                _RESET_SESSION.runtime_mode):
            print("[SS] T1 needs a single-shot calibration; running SS_Cal first.")
            calib_params = run_ss_cal(outer_folder, soc, soccfg)
        run_t1(outer_folder, soc, soccfg, calib_params)
    if P_T1_FLUX_RAMP["run"]:
        if calib_params is None and needs_standalone_ss_calibration(
                _RESET_SESSION.runtime_mode):
            print("[SS] T1_Flux_Ramp needs a park single-shot calibration; "
                  "running SS_Cal first.")
            calib_params = run_ss_cal(outer_folder, soc, soccfg)
        run_t1_flux_ramp(outer_folder, soc, soccfg, calib_params)

    print("\nsingle-qubit coherence complete.")


if __name__ == "__main__":
    main()
