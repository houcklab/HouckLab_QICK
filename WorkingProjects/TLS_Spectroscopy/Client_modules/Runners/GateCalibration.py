import gc
import time

import numpy as np
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt

from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.socProxy import makeProxy
from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.Experiment import ExperimentClass
from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.local_settings import (
    apply_local_overrides,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.Calib.initialize import BaseConfig, outerFolder
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mTransmission import Transmission
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mTransmissionVsFFGain import (
    TransmissionVsFFGain, FFTransProgram)
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mSingleShot1Q import SingleShot1Q
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mRabiChevronIQ import RabiChevronIQ
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mRabiChevronSS import RabiChevronSS
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mQubitSpec import QubitSpec, QubitSpecGainSweep
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mOptimize1Q import ReadoutOptimize, QubitPulseOptimize
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.progress import progress_counter
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.production import (
    ProductionResetSession,
    normalize_reset_mode,
    prepare_reset_session,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.qua_order import (
    acquire_passive_readout_grid,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mCoherence import (
    needs_standalone_ss_calibration,
)

QUBIT = "q3"
CHIP_NAME_FOR_CONFIG = "FTT02_AlOxJJ"
LIVE_PLOTS = True

FF_HOLD_GAIN = 0
READOUT_AFTER_PARK = True

RESET_MODE = "active"

_RESET_SESSION = ProductionResetSession.passive()

P_TRANSMISSION = {
    "run": False,
    "shots": 1000,
    "freq_start_mhz": 6929.0,
    "freq_stop_mhz": 6935.0,
    "freq_points": 201,
    "spec_amp": 1000,
    "spec_len_us": 10,
}

P_TRANSMISSION_SWEEP = {
    "run": False,
    "shots": 500,
    "freq_start_mhz": None,
    "freq_stop_mhz": None,
    "freq_points": 101,
    "gain_min": 1000,
    "gain_max": 10000,
    "gain_points": 10,
    "spec_len_us": None,
}

P_QUBIT_SPEC = {
    "run": False,
    "shots": 100,
    "freq_start_mhz": 4300,
    "freq_stop_mhz": 4400,
    "freq_points": 101,
    "spec_gain": 10000,
    "spec_length_us": 1.0,
    "relax_delay_us": 100.0,
}

P_QUBIT_SPEC_SWEEP = {
    "run": False,
    "shots": 1000,
    "freq_start_mhz": 2520,
    "freq_stop_mhz": 2540,
    "freq_points": 201,
    "gain_min": 200,
    "gain_max": 10000,
    "gain_points": 12,
    "spec_length_us": 10.0,
    "relax_delay_us": 100.0,
}

P_SS_CAL = {
    "run": True,
    "shots": 1000,
    "number_pi_pulses": 1,
    "ground_threshold": 0.7,
    "relax_delay_us": 1000.0,
}

P_RABI_CHEVRON_IQ = {
    "run": False,
    "shots": 50,
    "num_pi": 1,
    "pulse_type": "X180",
    "a_min": 1000,
    "a_max": 30000,
    "a_points": 21,
    "sigma_us": 0.2,
    "freq_span_mhz": 2.0,
    "freq_points": 21,
    "relax_delay_us": 500.0,
}

P_RABI_CHEVRON_SS = {
    "run": False,
    "shots": 1000,
    "num_pi": 1,
    "pulse_type": "X180",
    "a_min": 10000,
    "a_max": 20000,
    "a_points": 21,
    "freq_span_mhz": 3.0,
    "freq_points": 21,
}

P_READOUT_OPT = {
    "run": False,
    "shots": 500,
    "num_pi": 1,
    "pulse_type": "X180",
    "freq_span_mhz": 2.0,
    "freq_points": 11,
    "gain_min": 200,
    "gain_max": 3000,
    "gain_points": 11,
}

P_QUBIT_OPT = {
    "run": False,
    "shots": 500,
    "num_pi": 1,
    "pulse_type": "X180",
    "freq_span_mhz": 2.0,
    "freq_points": 11,
    "gain_min": 9000,
    "gain_max": 15000,
    "gain_points": 11,
    "x90_validation_shots": 500,
    "x90_validation_rounds": 5,
}

LOCAL_OVERRIDE_KEYS = (
    "QUBIT",
    "CHIP_NAME_FOR_CONFIG",
    "LIVE_PLOTS",
    "FF_HOLD_GAIN",
    "READOUT_AFTER_PARK",
    "RESET_MODE",
    "P_TRANSMISSION",
    "P_TRANSMISSION_SWEEP",
    "P_QUBIT_SPEC",
    "P_QUBIT_SPEC_SWEEP",
    "P_SS_CAL",
    "P_RABI_CHEVRON_IQ",
    "P_RABI_CHEVRON_SS",
    "P_READOUT_OPT",
    "P_QUBIT_OPT",
)

apply_local_overrides(globals(), __file__, LOCAL_OVERRIDE_KEYS)


def _base_cfg(p, extra=None, active=True):
    cfg = dict(BaseConfig)
    cfg["shots"] = int(p["shots"])
    cfg["reps"] = int(p["shots"])
    cfg["relax_delay"] = float(p.get("relax_delay_us", 1000.0))
    cfg["ff_gain"] = int(FF_HOLD_GAIN)
    cfg["ff_hold_gain"] = int(FF_HOLD_GAIN)
    cfg["readout_after_park"] = bool(READOUT_AFTER_PARK)
    cfg["baseline_rearm_us"] = float(p.get("baseline_rearm_us", 0.5))
    if extra:
        cfg.update(extra)
    session = _RESET_SESSION if active else ProductionResetSession.passive()
    return session.apply(cfg)


def _apply_spec_probe(cfg, p):
    if p.get("spec_amp") is not None:
        cfg["read_pulse_gain"] = int(p["spec_amp"])
    if p.get("spec_len_us") is not None:
        cfg["read_length"] = float(p["spec_len_us"])
    return cfg


def run_transmission(outer_folder, soc, soccfg):
    p = P_TRANSMISSION
    f0 = float(BaseConfig["read_pulse_freq"])
    start = p["freq_start_mhz"] if p["freq_start_mhz"] is not None else f0 - 2.0
    stop = p["freq_stop_mhz"] if p["freq_stop_mhz"] is not None else f0 + 2.0
    f_vec = np.linspace(float(start), float(stop), int(p["freq_points"]))
    cfg = _base_cfg(p, active=False)
    cfg["relax_delay"] = 50
    _apply_spec_probe(cfg, p)
    print(f"[transmission] {p['freq_points']} freqs {start:.3f}-{stop:.3f} MHz at ff_gain={FF_HOLD_GAIN}")
    exp = Transmission(soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outer_folder,
                       suffix="GateCal_Transmission", cfg=cfg, f_vec=f_vec)
    exp.acquire(progress=True, plotDisp=LIVE_PLOTS)
    plt.close("all"); gc.collect()
    return exp


def run_transmission_sweep(outer_folder, soc, soccfg):
    p = P_TRANSMISSION_SWEEP
    f0 = float(BaseConfig["read_pulse_freq"])
    start = p["freq_start_mhz"] if p["freq_start_mhz"] is not None else f0 - 2.0
    stop = p["freq_stop_mhz"] if p["freq_stop_mhz"] is not None else f0 + 2.0
    freqs = np.linspace(float(start), float(stop), int(p["freq_points"]))
    gains = np.linspace(p["gain_min"], p["gain_max"], int(p["gain_points"]))
    cfg = _base_cfg(p, extra={"ff_gain": int(FF_HOLD_GAIN),
                              "ff_settle_us": 20.0}, active=False)
    cfg["relax_delay"] = 50
    _apply_spec_probe(cfg, p)
    exp = ExperimentClass(path=QUBIT, outerFolder=outer_folder, suffix="GateCal_TransSweep", cfg=cfg)
    mag = np.full((len(gains), len(freqs)), np.nan)
    total = len(gains) * len(freqs)
    print(f"[transmission sweep] {len(gains)} readout gains x {len(freqs)} freqs at "
          f"park ff_park_gain={cfg.get('ff_park_gain', 0)} ({total} points -- slow)")
    start_time = time.time()
    telemetry = None
    if bool(cfg.get("qua_shot_order", False)):
        i_values, q_values, telemetry = acquire_passive_readout_grid(
            soc,
            soccfg,
            cfg,
            frequencies_mhz=freqs,
            values=gains,
            kind="readout_gain",
            progress=lambda done, count: progress_counter(
                done - 1, count, start_time=start_time, label="transmission sweep"
            ),
        )
        signal = np.mean(i_values + 1j * q_values, axis=2)
        mag[:, :] = (20.0 * np.log10(np.abs(signal) + 1e-12)).T
    else:
        step = 0
        for i, g in enumerate(gains):
            cfg["read_pulse_gain"] = int(g)
            for j, f in enumerate(freqs):
                cfg["read_pulse_freq"] = float(f)
                res = FFTransProgram(soccfg, cfg).acquire(
                    soc, load_pulses=True, progress=False
                )
                I, Q = np.array(res[0]).mean(), np.array(res[1]).mean()
                mag[i, j] = 20.0 * np.log10(np.hypot(I, Q) + 1e-12)
                progress_counter(
                    step, total, start_time=start_time, label="transmission sweep"
                )
                step += 1
    fig = plt.figure(figsize=(7, 4.5))
    plt.pcolormesh(freqs, gains, mag, shading="nearest")
    plt.xlabel("Readout frequency [MHz]"); plt.ylabel("Readout gain [DAC]")
    plt.colorbar(label="|S21| [dB]")
    plt.title(
        f"{QUBIT} transmission vs readout power "
        f"(park {cfg.get('ff_park_gain', 0)} DAC)"
    )
    plt.savefig(exp.iname, bbox_inches="tight")
    print(f"[transmission sweep] saved {exp.iname}")
    exp.data = {
        "frequencies_mhz": freqs,
        "readout_gains": gains,
        "magnitude_db": mag,
        "config": dict(cfg),
    }
    if telemetry is not None:
        exp.data["acquisition_order"] = telemetry["order"]
        exp.data["qua_order_telemetry"] = telemetry
    exp.pickle_data()
    if LIVE_PLOTS:
        plt.show(block=False); plt.pause(0.1)
    plt.close(fig); gc.collect()
    print("[transmission sweep] pick the readout gain with the cleanest dip -> read_pulse_gain.")


def run_qubit_spec(outer_folder, soc, soccfg):
    p = P_QUBIT_SPEC
    q0 = float(BaseConfig["qubit_pi_freq"])
    start = p["freq_start_mhz"] if p["freq_start_mhz"] is not None else q0 - 50.0
    stop = p["freq_stop_mhz"] if p["freq_stop_mhz"] is not None else q0 + 50.0
    cfg = _base_cfg(p, extra={
        "qubit_pulse_style": "const",
        "qubit_gain": int(p["spec_gain"]),
        "qubit_length": float(p["spec_length_us"]),
        "qubit_freq_start": float(start),
        "qubit_freq_stop": float(stop),
        "qubit_freq_expts": int(p["freq_points"]),
        "qua_passive_pre_point_delay_us": 0.0,
    }, active=False)
    print(f"[qubit spec] two-tone: {p['freq_points']} freqs {start:.1f}-{stop:.1f} MHz, "
          f"spec gain {p['spec_gain']} DAC")
    exp = QubitSpec(soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outer_folder,
                    suffix="GateCal_Qubit_Spec", cfg=cfg, live_plot=LIVE_PLOTS)
    exp.acquire(progress=True, plotDisp=LIVE_PLOTS)
    plt.close("all"); gc.collect()
    return exp


def run_qubit_spec_sweep(outer_folder, soc, soccfg):
    p = P_QUBIT_SPEC_SWEEP
    q0 = float(BaseConfig["qubit_pi_freq"])
    start = p["freq_start_mhz"] if p["freq_start_mhz"] is not None else q0 - 50.0
    stop = p["freq_stop_mhz"] if p["freq_stop_mhz"] is not None else q0 + 50.0
    gain_points = int(p["gain_points"])
    gains = np.linspace(
        float(p["gain_min"]),
        float(p["gain_max"]),
        gain_points,
    )
    cfg = _base_cfg(p, extra={
        "qubit_pulse_style": "const",
        "qubit_length": float(p["spec_length_us"]),
        "qubit_freq_start": float(start),
        "qubit_freq_stop": float(stop),
        "qubit_freq_expts": int(p["freq_points"]),
        "qua_passive_pre_point_delay_us": 0.0,
    }, active=False)
    print(f"[qubit spec sweep] {p['gain_points']} spec gains {gains[0]}..{gains[-1]} DAC "
          f"x {p['freq_points']} freqs {start:.1f}-{stop:.1f} MHz")
    exp = QubitSpecGainSweep(soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outer_folder,
                             suffix="GateCal_Qubit_Spec_Gain", cfg=cfg, gains=gains,
                             live_plot=LIVE_PLOTS)
    exp.acquire(progress=True, plotDisp=LIVE_PLOTS)
    plt.close("all"); gc.collect()
    return exp


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
    return ss.calib_params


def run_rabi_chevron_iq(outer_folder, soc, soccfg):
    p = P_RABI_CHEVRON_IQ
    cfg = _base_cfg(p, extra={
        "amp_start": p["a_min"], "amp_stop": p["a_max"], "amp_expts": p["a_points"],
        "freq_span": p["freq_span_mhz"], "freq_points": p["freq_points"],
        "qubit_pulse_style": "arb",
        "sigma": p["sigma_us"],
        "relax_delay": p.get("relax_delay_us", 1000.0),
        "qua_passive_pre_point_delay_us": p.get("relax_delay_us", 1000.0),
    }, active=False)
    exp = RabiChevronIQ(soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outer_folder,
                        suffix="Rabi_Chevron_IQ", cfg=cfg,
                        num_pi_pulses=p["num_pi"], pulse_type=p["pulse_type"],
                        live_plot=LIVE_PLOTS)
    exp.acquire(progress=True, plotDisp=LIVE_PLOTS)
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
    exp.acquire(progress=True, plotDisp=LIVE_PLOTS)
    plt.close("all"); gc.collect()
    return exp


def run_readout_opt(outer_folder, soc, soccfg):
    p = P_READOUT_OPT
    f0 = float(BaseConfig["read_pulse_freq"])
    freqs = np.linspace(f0 - p["freq_span_mhz"] / 2.0, f0 + p["freq_span_mhz"] / 2.0,
                        int(p["freq_points"]))
    gains = np.round(np.linspace(p["gain_min"], p["gain_max"],
                                 int(p["gain_points"]))).astype(int)
    cfg = _base_cfg(p, active=False)
    print(f"[readout opt] scanning read freq {freqs[0]:.3f}..{freqs[-1]:.3f} MHz x gain "
          f"{gains[0]}..{gains[-1]} with {p['pulse_type']} state preparation at "
          f"ff_gain={FF_HOLD_GAIN} (passive)")
    exp = ReadoutOptimize(soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outer_folder,
                          suffix="GateCal_Readout_Optimize", cfg=cfg,
                          freqs_mhz=freqs, gains=gains, shots=int(p["shots"]),
                          num_pi=int(p["num_pi"]),
                          pulse_type=p["pulse_type"], live_plot=LIVE_PLOTS)
    exp.acquire(progress=True, plotDisp=LIVE_PLOTS)
    plt.close("all"); gc.collect()
    return exp


def run_qubit_opt(outer_folder, soc, soccfg):
    p = P_QUBIT_OPT
    cfg = _base_cfg(p, active=False)
    f0 = float(cfg["qubit_pi_freq"])
    freqs = np.linspace(f0 - p["freq_span_mhz"] / 2.0, f0 + p["freq_span_mhz"] / 2.0,
                        int(p["freq_points"]))
    gains = np.round(np.linspace(p["gain_min"], p["gain_max"],
                                 int(p["gain_points"]))).astype(int)
    cfg["x90_validation_shots"] = int(p.get("x90_validation_shots", p["shots"]))
    cfg["x90_validation_rounds"] = int(p.get("x90_validation_rounds", 5))
    print(f"[qubit opt] scanning qubit freq {freqs[0]:.3f}..{freqs[-1]:.3f} MHz x gain "
          f"{gains[0]}..{gains[-1]}, {p['pulse_type']} with "
          f"{p['num_pi']} logical pi rotations (passive)")
    exp = QubitPulseOptimize(soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outer_folder,
                             suffix="GateCal_Qubit_Optimize", cfg=cfg,
                             freqs_mhz=freqs, gains=gains, shots=int(p["shots"]),
                             num_pi=int(p["num_pi"]),
                             pulse_type=p["pulse_type"], live_plot=LIVE_PLOTS)
    exp.acquire(progress=True, plotDisp=LIVE_PLOTS)
    plt.close("all"); gc.collect()
    return exp


def main():
    soc, soccfg = makeProxy()
    outer_folder = outerFolder

    global _RESET_SESSION
    active_measurement = bool(P_RABI_CHEVRON_SS["run"])
    if active_measurement and normalize_reset_mode(RESET_MODE) == "opx_unbounded":
        _RESET_SESSION = prepare_reset_session(
            RESET_MODE,
            outer_folder=outer_folder,
            qubit=QUBIT,
            base_cfg=BaseConfig,
            soc=soc,
            soccfg=soccfg,
            purpose="GateCalibration",
        )
        print(f"[reset] automatic calibration saved: {_RESET_SESSION.calibration_output}")
    else:
        _RESET_SESSION = ProductionResetSession.passive()

    print("=" * 70)
    flux_note = ("PARK (ff_gain=0)" if FF_HOLD_GAIN == 0 else
                 f"HELD flux ff_gain={FF_HOLD_GAIN} DAC, read {'at park' if READOUT_AFTER_PARK else 'AT held flux'}")
    print(f"gate calibration | {QUBIT} | chip {CHIP_NAME_FOR_CONFIG} | at {flux_note}")
    if FF_HOLD_GAIN != 0:
        print(f"  NOTE: qubit_pi_freq={BaseConfig['qubit_pi_freq']} MHz must be the qubit freq AT ff_gain={FF_HOLD_GAIN}")
    for name, on in [("Transmission", P_TRANSMISSION["run"]),
                     ("Transmission_Sweep", P_TRANSMISSION_SWEEP["run"]),
                     ("Qubit_Spec", P_QUBIT_SPEC["run"]),
                     ("Qubit_Spec_Sweep", P_QUBIT_SPEC_SWEEP["run"]),
                     ("SS_Cal", P_SS_CAL["run"]),
                     ("Rabi_Chevron_IQ", P_RABI_CHEVRON_IQ["run"]),
                     ("Rabi_Chevron_SS", P_RABI_CHEVRON_SS["run"]),
                     ("Readout_Optimize", P_READOUT_OPT["run"]),
                     ("Qubit_Optimize", P_QUBIT_OPT["run"])]:
        print(f"  {'[x]' if on else '[ ]'} {name}")
    print("=" * 70)

    if P_TRANSMISSION["run"]:
        run_transmission(outer_folder, soc, soccfg)
    if P_TRANSMISSION_SWEEP["run"]:
        run_transmission_sweep(outer_folder, soc, soccfg)
    if P_QUBIT_SPEC["run"]:
        run_qubit_spec(outer_folder, soc, soccfg)
    if P_QUBIT_SPEC_SWEEP["run"]:
        run_qubit_spec_sweep(outer_folder, soc, soccfg)

    calib_params = None
    if P_SS_CAL["run"]:
        calib_params = run_ss_cal(outer_folder, soc, soccfg)
    if P_RABI_CHEVRON_IQ["run"]:
        run_rabi_chevron_iq(outer_folder, soc, soccfg)
    if P_RABI_CHEVRON_SS["run"]:
        if calib_params is None and needs_standalone_ss_calibration(
                _RESET_SESSION.runtime_mode):
            print("[SS] Chevron_SS needs a single-shot calibration; running SS_Cal first.")
            calib_params = run_ss_cal(outer_folder, soc, soccfg)
        run_rabi_chevron_ss(outer_folder, soc, soccfg, calib_params)
    if P_READOUT_OPT["run"]:
        run_readout_opt(outer_folder, soc, soccfg)
    if P_QUBIT_OPT["run"]:
        run_qubit_opt(outer_folder, soc, soccfg)

    print("\ngate calibration complete.")


if __name__ == "__main__":
    main()
