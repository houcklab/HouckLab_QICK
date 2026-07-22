import gc
import os

import numpy as np
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt

from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.socProxy import makeProxy
from WorkingProjects.TLS_Spectroscopy.Client_modules.Calib.initialize import BaseConfig, outerFolder
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mTransmissionVsFFGain import (
    TransmissionVsFFGain, FFTransProgram)
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mQubitLongTimeSpecVsFlux import QubitLongTimeSpecVsFlux
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mSingleShot1Q import SingleShot1Q
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mRabiChevronIQ import RabiChevronIQ
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mRabiChevronSS import RabiChevronSS
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mRabiLinecutSS import RabiLinecutSS
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mActiveResetProbe import ActiveResetProbe
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mActiveResetValidation import ActiveResetValidation

QUBIT = "q4"
CHIP_NAME_FOR_CONFIG = "FTTv02_SiOxJJ"
LIVE_PLOTS = True

FF_HOLD_GAIN = 0
READOUT_AFTER_PARK = True

RESET_MODE = "passive"
RESET_THRESHOLD_RAW = 2153
RESET_OPER = "upper"
RESET_GROUND_BELOW = True
RESET_MAX_ITERS = 3
RUN_ACTIVE_RESET_PROBE = False
RUN_ACTIVE_RESET_VALIDATION = False

P_TRANSMISSION = {
    "run": True,
    "shots": 1000,
    "freq_center_mhz": None,
    "freq_span_mhz": 4.0,
    "freq_points": 201,
}
P_TRANSMISSION_SWEEP = {
    "run": False,
    "shots": 500,
    "freq_center_mhz": None,
    "freq_span_mhz": 4.0,
    "freq_points": 101,
    "gain_min": 1000,
    "gain_max": 10000,
    "gain_points": 10,
}
P_QUBIT_SPEC = {
    "run": True,
    "shots": 1000,
    "spec_amp": 7000,
    "spec_len_us": 2.0,
    "freq_min_mhz": 2300.0,
    "freq_max_mhz": 2700.0,
    "freq_step_mhz": 1.0,
}

P_SS_CAL = {
    "run": True,
    "shots": 1000,
    "number_pi_pulses": 1,
    "ground_threshold": 0.6,
    "relax_delay_us": 2000.0,
}

P_RABI_CHEVRON_IQ = {
    "run": True,
    "shots": 100,
    "num_pi": 1,
    "pulse_type": "X180",
    "a_min": 500,
    "a_max": 30000,
    "a_points": 41,
    "freq_span_mhz": 20.0,
    "freq_points": 21,
    "relax_delay_us": 500.0,
}

P_RABI_CHEVRON_SS = {
    "run": False,
    "shots": 200,
    "num_pi": 5,
    "pulse_type": "X180",
    "a_min": 10000,
    "a_max": 15000,
    "a_points": 21,
    "freq_span_mhz": 1.0,
    "freq_points": 21,
    "relax_delay_us": 2000.0,
}

P_RABI_LINECUT_SS = {
    "run": False,
    "shots": 1000,
    "num_pi": 1,
    "pulse_type": "X180",
    "a_span": 6000,
    "a_points": 51,
    "relax_delay_us": 2000.0,
}


def _base_cfg(p, extra=None):
    """BaseConfig + shots + passive relax + flux-hold point + optional sweep knobs."""
    cfg = dict(BaseConfig)
    cfg["shots"] = int(p["shots"])
    cfg["reps"] = int(p["shots"])
    cfg["relax_delay"] = float(p.get("relax_delay_us", 2000.0))
    cfg["ff_gain"] = int(FF_HOLD_GAIN)
    cfg["ff_hold_gain"] = int(FF_HOLD_GAIN)
    cfg["readout_after_park"] = bool(READOUT_AFTER_PARK)
    cfg["baseline_rearm_us"] = float(p.get("baseline_rearm_us", 0.5))
    cfg["reset_mode"] = RESET_MODE
    if RESET_MODE == "feedback":
        if RESET_THRESHOLD_RAW is None:
            raise RuntimeError("RESET_MODE='feedback' needs RESET_THRESHOLD_RAW from "
                               "mActiveResetProbe.py (set RUN_ACTIVE_RESET_PROBE=True first).")
        cfg["reset_threshold_raw"] = int(RESET_THRESHOLD_RAW)
        cfg["reset_oper"] = str(RESET_OPER)
        cfg["reset_ground_below"] = bool(RESET_GROUND_BELOW)
        cfg["reset_max_iters"] = int(RESET_MAX_ITERS)
    if extra:
        cfg.update(extra)
    return cfg


def run_transmission(outer_folder, soc, soccfg):
    """QUA Transmission analog: 1D readout-freq sweep at the cal flux -> resonator dip.
    Reuses the step-1 FF transmission at a single ff_gain."""
    p = P_TRANSMISSION
    center = (p["freq_center_mhz"] if p["freq_center_mhz"] is not None
              else float(BaseConfig["read_pulse_freq"]))
    cfg = _base_cfg(p, extra={
        "trans_freq_start": center - p["freq_span_mhz"] / 2.0,
        "trans_freq_stop": center + p["freq_span_mhz"] / 2.0,
        "TransNumPoints": int(p["freq_points"]),
        "ff_gain_vec": [int(FF_HOLD_GAIN)], "ff_settle_us": 20.0,
    })
    cfg["relax_delay"] = 50
    print(f"[transmission] {p['freq_points']} freqs around {center:.3f} MHz at ff_gain={FF_HOLD_GAIN}")
    exp = TransmissionVsFFGain(soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outer_folder,
                               suffix="GateCal_Transmission", cfg=cfg, save_resonator_lookup=False)
    exp.acquire(plotDisp=LIVE_PLOTS)
    plt.close("all"); gc.collect()
    print("[transmission] read the dip -> set BaseConfig['read_pulse_freq'].")
    return exp


def run_transmission_sweep(outer_folder, soc, soccfg):
    """QUA Transmission_Sweep analog: readout-gain x freq map at the cal flux (pick
    read_pulse_gain).  Loops the step-1 FF transmission program over readout gain."""
    p = P_TRANSMISSION_SWEEP
    center = (p["freq_center_mhz"] if p["freq_center_mhz"] is not None
              else float(BaseConfig["read_pulse_freq"]))
    freqs = np.linspace(center - p["freq_span_mhz"] / 2.0, center + p["freq_span_mhz"] / 2.0,
                        int(p["freq_points"]))
    gains = np.linspace(p["gain_min"], p["gain_max"], int(p["gain_points"]))
    cfg = _base_cfg(p, extra={"ff_gain": int(FF_HOLD_GAIN), "ff_settle_us": 20.0})
    cfg["relax_delay"] = 50
    mag = np.full((len(gains), len(freqs)), np.nan)
    print(f"[transmission sweep] {len(gains)} readout gains x {len(freqs)} freqs at "
          f"ff_gain={FF_HOLD_GAIN} ({len(gains) * len(freqs)} points -- slow)")
    for i, g in enumerate(gains):
        cfg["read_pulse_gain"] = int(g)
        for j, f in enumerate(freqs):
            cfg["read_pulse_freq"] = float(f)
            res = FFTransProgram(soccfg, cfg).acquire(soc, load_pulses=True, progress=False)
            I, Q = np.array(res[0]).mean(), np.array(res[1]).mean()
            mag[i, j] = 20.0 * np.log10(np.hypot(I, Q) + 1e-12)
    fig = plt.figure(figsize=(7, 4.5))
    plt.pcolormesh(freqs, gains, mag, shading="nearest")
    plt.xlabel("Readout frequency [MHz]"); plt.ylabel("Readout gain [DAC]")
    plt.colorbar(label="|S21| [dB]")
    plt.title(f"{QUBIT} transmission vs readout power (ff_gain={FF_HOLD_GAIN})")
    try:
        os.makedirs(os.path.join(outer_folder, QUBIT), exist_ok=True)
        ipath = os.path.join(outer_folder, QUBIT, f"{QUBIT}_GateCal_TransSweep.png")
        plt.savefig(ipath, bbox_inches="tight")
        print(f"[transmission sweep] saved {ipath}")
    except Exception as e:
        print(f"[transmission sweep] could not save PNG: {e}")
    if LIVE_PLOTS:
        plt.show(block=False); plt.pause(0.1)
    plt.close(fig); gc.collect()
    print("[transmission sweep] pick the readout gain with the cleanest dip -> read_pulse_gain.")


def run_qubit_spec(outer_folder, soc, soccfg):
    """QUA Qubit_Spec analog: 1D qubit-drive-freq sweep at the cal flux -> qubit dip.
    Reuses the step-2 FF spec at a single flux (advanced fit off)."""
    p = P_QUBIT_SPEC
    n = max(int(round((p["freq_max_mhz"] - p["freq_min_mhz"]) / p["freq_step_mhz"])) + 1, 5)
    cfg = _base_cfg(p, extra={
        "qubit_freq_start": p["freq_min_mhz"], "qubit_freq_stop": p["freq_max_mhz"],
        "qubit_freq_step": p["freq_step_mhz"], "qubit_freq_expts": n,
        "qubit_gain": int(p["spec_amp"]), "qubit_length": float(p["spec_len_us"]),
        "qubit_pulse_style": "const", "interleave_rounds": 1,
    })
    cfg["relax_delay"] = float(p.get("relax_delay_us", 100.0))
    print(f"[qubit spec] {p['freq_min_mhz']:.0f}-{p['freq_max_mhz']:.0f} MHz "
          f"({n} pts) @ gain {p['spec_amp']} at ff_gain={FF_HOLD_GAIN}")
    exp = QubitLongTimeSpecVsFlux(
        soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outer_folder,
        suffix="GateCal_Qubit_Spec", cfg=cfg, step_tag="GC", dc_vec=[int(FF_HOLD_GAIN)],
        long_time_ns=2000.0, average_window_ns=0.0,
        readout_after_park=bool(READOUT_AFTER_PARK), park_voltage=int(FF_HOLD_GAIN),
        fit_trace=False, advanced_fit=False, live_plot=LIVE_PLOTS, resonator_lookup_csv=None)
    exp.acquire(plotDisp=LIVE_PLOTS)
    plt.close("all"); gc.collect()
    print("[qubit spec] read the qubit dip -> set BaseConfig['qubit_pi_freq'] (and qubit_freq).")
    return exp


def run_ss_cal(outer_folder, soc, soccfg):
    p = P_SS_CAL
    cfg = _base_cfg(p)
    print(f"[SS] single-shot readout calibration ({p['shots']} shots, "
          f"{p['number_pi_pulses']}x pi prep)")
    ss = SingleShot1Q(soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outer_folder,
                      suffix="SS_Cal", cfg=cfg, repeats=int(p["number_pi_pulses"]),
                      confidence_threshold=float(p["ground_threshold"]))
    ss.acquire(plotDisp=LIVE_PLOTS)
    print(f"[SS] fidelity F = {ss.max_F:.4f}; calib_params = {ss.calib_params}")
    return ss.calib_params


def run_rabi_chevron_iq(outer_folder, soc, soccfg):
    p = P_RABI_CHEVRON_IQ
    cfg = _base_cfg(p, extra={
        "amp_start": p["a_min"], "amp_stop": p["a_max"], "amp_expts": p["a_points"],
        "freq_span": p["freq_span_mhz"], "freq_points": p["freq_points"],
        "reset_mode": "passive",
    })
    exp = RabiChevronIQ(soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outer_folder,
                        suffix="Rabi_Chevron_IQ", cfg=cfg,
                        num_pi_pulses=p["num_pi"], pulse_type=p["pulse_type"],
                        live_plot=LIVE_PLOTS)
    exp.acquire(plotDisp=LIVE_PLOTS)
    plt.close("all"); gc.collect()
    return exp


def run_rabi_chevron_ss(outer_folder, soc, soccfg, calib_params):
    p = P_RABI_CHEVRON_SS
    cfg = _base_cfg(p, extra={
        "amp_start": p["a_min"], "amp_stop": p["a_max"], "amp_expts": p["a_points"],
        "freq_span": p["freq_span_mhz"], "freq_points": p["freq_points"],
    })
    exp = RabiChevronSS(soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outer_folder,
                        suffix="Rabi_Chevron_SS", cfg=cfg, calib_params=calib_params,
                        num_pi_pulses=p["num_pi"], pulse_type=p["pulse_type"],
                        live_plot=LIVE_PLOTS)
    exp.acquire(plotDisp=LIVE_PLOTS)
    plt.close("all"); gc.collect()
    return exp


def run_rabi_linecut_ss(outer_folder, soc, soccfg, calib_params):
    p = P_RABI_LINECUT_SS
    num_pi = p["num_pi"]
    if isinstance(num_pi, (list, tuple)):
        stacked, last = [], None
        for npi in num_pi:
            cfg = _base_cfg(p, extra={"a_span": p["a_span"], "a_points": p["a_points"]})
            exp = RabiLinecutSS(soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outer_folder,
                                suffix=f"Rabi_Linecut_SS_npi{npi}", cfg=cfg,
                                calib_params=calib_params, num_pi_pulses=int(npi),
                                pulse_type=p["pulse_type"], live_plot=False)
            exp.acquire()
            stacked.append(exp.data["ss_data"]); last = exp
        fig = plt.figure(figsize=(7, 4.5))
        plt.pcolor(last.data["gain_vec"], np.asarray(num_pi, dtype=float),
                   np.asarray(stacked), shading="auto")
        plt.xlabel("Qubit pulse gain [DAC]"); plt.ylabel("# pi pulses")
        plt.colorbar(label="Excited population")
        plt.title(f"{QUBIT} error-amplification pi sweep")
        plt.savefig(last.iname[:-4] + "_pi_sweep.png", bbox_inches="tight")
        plt.close(fig)
        print(f"[Linecut] error-amp sweep saved for num_pi = {list(num_pi)}")
        return last
    else:
        cfg = _base_cfg(p, extra={"a_span": p["a_span"], "a_points": p["a_points"]})
        exp = RabiLinecutSS(soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outer_folder,
                            suffix="Rabi_Linecut_SS", cfg=cfg, calib_params=calib_params,
                            num_pi_pulses=int(num_pi), pulse_type=p["pulse_type"],
                            live_plot=LIVE_PLOTS)
        exp.acquire(plotDisp=LIVE_PLOTS)
        plt.close("all"); gc.collect()
        print(f"[Linecut] paste pi gain {exp.data['pi_gain']:.0f} into "
              f"BaseConfig['qubit_pi_gain'] (or qubit_pi2_gain for X90).")
        return exp


def run_active_reset_probe(outer_folder, soc, soccfg):
    """Capability + threshold probe for TRUE tProc active reset (run before RESET_MODE='feedback')."""
    cfg = _base_cfg(P_SS_CAL)
    probe = ActiveResetProbe(soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outer_folder,
                             suffix="Active_Reset_Probe", cfg=cfg)
    probe.acquire()
    return probe


def run_active_reset_validation(outer_folder, soc, soccfg):
    """Validate the FULL active-reset feedback LOOP (not just the read): prep |e> -> reset ->
    measure the residual excited fraction vs |g>/|e> refs.  Runs regardless of RESET_MODE (it
    drives the reset itself, forcing the probe values in), and is self-contained on the readout
    buffer -- so it's the correct thing to run BEFORE trusting reset_mode='feedback' anywhere."""
    if RESET_THRESHOLD_RAW is None:
        raise RuntimeError("Active-reset validation needs RESET_THRESHOLD_RAW from "
                           "mActiveResetProbe.py (set RUN_ACTIVE_RESET_PROBE=True first).")
    cfg = _base_cfg(P_SS_CAL, extra={
        "reset_threshold_raw": int(RESET_THRESHOLD_RAW),
        "reset_oper": str(RESET_OPER),
        "reset_ground_below": bool(RESET_GROUND_BELOW),
        "reset_max_iters": int(RESET_MAX_ITERS),
    })
    val = ActiveResetValidation(soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outer_folder,
                                suffix="Active_Reset_Validation", cfg=cfg)
    val.acquire()
    return val


def main():
    soc, soccfg = makeProxy()
    outer_folder = outerFolder

    if RUN_ACTIVE_RESET_PROBE:
        print("=" * 70)
        print("Active-reset probe only (RUN_ACTIVE_RESET_PROBE=True)")
        print("=" * 70)
        run_active_reset_probe(outer_folder, soc, soccfg)
        print("\nProbe done.  If supported, paste RESET_THRESHOLD_RAW / RESET_OPER / "
              "RESET_GROUND_BELOW above, then RUN_ACTIVE_RESET_VALIDATION=True to validate the loop.")
        return

    if RUN_ACTIVE_RESET_VALIDATION:
        print("=" * 70)
        print("Active-reset VALIDATION only (RUN_ACTIVE_RESET_VALIDATION=True)")
        print("=" * 70)
        run_active_reset_validation(outer_folder, soc, soccfg)
        print("\nValidation done.  Read the VERDICT line above -- it only says WORKS when the "
              "no-reset\nbaseline is ~1.0 AND the residual stays low at EVERY iteration count.  A "
              "single low\npoint, or a baseline that isn't ~1.0, means the readout/pi need "
              "calibrating (SS_Cal +\nRabi) -- not that the reset works.  Only enable "
              "RESET_MODE='feedback' after a clean WORKS.")
        return

    print("=" * 70)
    flux_note = ("PARK (ff_gain=0)" if FF_HOLD_GAIN == 0 else
                 f"HELD flux ff_gain={FF_HOLD_GAIN} DAC, read {'at park' if READOUT_AFTER_PARK else 'AT held flux'}")
    print(f"pi-pulse calibration | {QUBIT} | chip {CHIP_NAME_FOR_CONFIG} | at {flux_note}")
    if FF_HOLD_GAIN != 0:
        print(f"  NOTE: qubit_pi_freq={BaseConfig['qubit_pi_freq']} MHz must be the qubit freq AT ff_gain={FF_HOLD_GAIN}")
    for name, on in [("Transmission", P_TRANSMISSION["run"]),
                     ("Transmission_Sweep", P_TRANSMISSION_SWEEP["run"]),
                     ("Qubit_Spec", P_QUBIT_SPEC["run"]),
                     ("SS_Cal", P_SS_CAL["run"]),
                     ("Rabi_Chevron_IQ", P_RABI_CHEVRON_IQ["run"]),
                     ("Rabi_Chevron_SS", P_RABI_CHEVRON_SS["run"]),
                     ("Rabi_Linecut_SS", P_RABI_LINECUT_SS["run"])]:
        print(f"  {'[x]' if on else '[ ]'} {name}")
    print("=" * 70)

    if P_TRANSMISSION["run"]:
        run_transmission(outer_folder, soc, soccfg)
    if P_TRANSMISSION_SWEEP["run"]:
        run_transmission_sweep(outer_folder, soc, soccfg)
    if P_QUBIT_SPEC["run"]:
        run_qubit_spec(outer_folder, soc, soccfg)

    calib_params = None
    if P_SS_CAL["run"]:
        calib_params = run_ss_cal(outer_folder, soc, soccfg)
    if P_RABI_CHEVRON_IQ["run"]:
        run_rabi_chevron_iq(outer_folder, soc, soccfg)
    if P_RABI_CHEVRON_SS["run"]:
        if calib_params is None:
            print("[SS] Chevron_SS needs a single-shot calibration; running SS_Cal first.")
            calib_params = run_ss_cal(outer_folder, soc, soccfg)
        run_rabi_chevron_ss(outer_folder, soc, soccfg, calib_params)
    if P_RABI_LINECUT_SS["run"]:
        if calib_params is None:
            print("[SS] Linecut_SS needs a single-shot calibration; running SS_Cal first.")
            calib_params = run_ss_cal(outer_folder, soc, soccfg)
        run_rabi_linecut_ss(outer_folder, soc, soccfg, calib_params)

    print("\npi-pulse calibration complete.")


if __name__ == "__main__":
    main()
