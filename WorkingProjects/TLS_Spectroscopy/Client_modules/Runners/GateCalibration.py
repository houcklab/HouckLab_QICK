"""
Single-qubit pi/pi-2 pulse calibration -- QICK port of Houck-Lab-Qua
LabCode/Control/Flux_Tunable/gate_calibration_flux_tunable.py.

Ports the experiments actually used in the QUA workflow (omitted per user: Frequency
Calibration, DRAG, the two Timed Rabis, Chi measurement).  Kept here:
  * SS_Cal          -- single-shot readout discrimination (reused: Experiments/mSingleShot1Q)
  * Rabi_Chevron_IQ -- 2D amp x detuning, averaged IQ -> rough pi gain + freq
  * Rabi_Chevron_SS -- 2D amp x detuning, single-shot + 5x error amp -> refined
  * Rabi_Linecut_SS -- 1D amp at fixed freq, single-shot, cosine^2 fit -> precise pi gain

Transmission / qubit spectroscopy (QUA's Transmission, Qubit_Spec) are already covered by
the TLS pipeline steps 1-2 (run those first to place the resonator + qubit-drive freq into
BaseConfig); this runner focuses on the pi tune-up.

Calibration is done at PARK (ff_gain = 0, native flux point) -- the QUA analog of YOKO=0.
Amplitudes are ABSOLUTE qubit-drive DAC gains (no QUA pi_amp normalization).

RESET: the single-shot Rabis use a PASSIVE relax_delay instead of the QUA active feedback
reset (tProc v1 cannot do mid-circuit feedback) -- same substitution as the TLS T1.  Set
relax_delay_us ~ 5x T1.

Result: read Rabi_Linecut_SS's printed "pi gain" and paste it into
Calib/initialize.py BaseConfig['qubit_pi_gain'] (or qubit_pi2_gain for X90), and the
Rabi_Chevron drive detuning into BaseConfig['qubit_pi_freq'].
"""

import gc

import numpy as np
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt

from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.socProxy import makeProxy
from WorkingProjects.TLS_Spectroscopy.Client_modules.Calib.initialize import BaseConfig, outerFolder
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mSingleShot1Q import SingleShot1Q
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mRabiChevronIQ import RabiChevronIQ
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mRabiChevronSS import RabiChevronSS
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mRabiLinecutSS import RabiLinecutSS

QUBIT = "q4"
CHIP_NAME_FOR_CONFIG = "FTTv02_SiOxJJ"
LIVE_PLOTS = True

# Flux point to tune the pi at.  The sweet spot can be at any DC offset, so set this to the
# fast-flux DAC gain of your operating point.  0 = park/native (the QUA YOKO=0 analog).
# Non-zero -> the Rabi ramps park->hold there during the drive (and the readout if
# READOUT_AFTER_PARK=False), then ramps back -- the same flux delivery as TLS step 3.
#   *** When FF_HOLD_GAIN != 0, set BaseConfig['qubit_pi_freq'] to the qubit frequency AT
#       this flux (measure it with a qubit spec there / TLS step 2 first). ***
FF_HOLD_GAIN = 0
# Readout location.  True: ramp back to park and read there (uses the park single-shot cal
# -- simplest, recommended).  False: read AT the held flux (then read_pulse_freq must be the
# resonator freq at FF_HOLD_GAIN AND the single-shot cal must be taken at that flux too).
READOUT_AFTER_PARK = True

# ----------------------------------------------------------------------------------------
# Per-experiment params (QUA experiment_dict analog).  Amplitudes are DAC gain (absolute).
# ----------------------------------------------------------------------------------------
P_SS_CAL = {
    "run": True,
    "shots": 1000,
    "number_pi_pulses": 1,      # excited-blob prep: X180 x this many (QUA parity knob)
    "ground_threshold": 0.6,    # SS-cal confidence_threshold -> calib_params['ground_threshold']
    "relax_delay_us": 2000.0,   # passive reset (~5x T1)
}

P_RABI_CHEVRON_IQ = {
    "run": True,
    "shots": 100,
    "num_pi": 1,
    "pulse_type": "X180",       # 'X180' or 'X90'
    "a_min": 500,               # DAC gain
    "a_max": 30000,             # DAC gain
    "a_points": 41,
    "freq_span_mhz": 20.0,      # drive detuning span around qubit_pi_freq
    "freq_points": 21,
    "relax_delay_us": 500.0,
}

P_RABI_CHEVRON_SS = {
    "run": False,               # needs SS_Cal; run after IQ narrows the window
    "shots": 200,
    "num_pi": 5,                # error amplification
    "pulse_type": "X180",
    "a_min": 10000,             # DAC gain (narrow around the IQ pi estimate)
    "a_max": 15000,
    "a_points": 21,
    "freq_span_mhz": 1.0,
    "freq_points": 21,
    "relax_delay_us": 2000.0,
}

P_RABI_LINECUT_SS = {
    "run": False,               # needs SS_Cal; the final precise pi-gain fit
    "shots": 1000,
    "num_pi": 1,                # scalar, or a list e.g. [1, 3, 5, 7] for an error-amp sweep
    "pulse_type": "X180",
    "a_span": 6000,             # DAC gain, full span centered on the current pi gain
    "a_points": 51,
    "relax_delay_us": 2000.0,
}


def _base_cfg(p, extra=None):
    """BaseConfig + shots + passive relax + flux-hold point + optional sweep knobs."""
    cfg = dict(BaseConfig)
    cfg["shots"] = int(p["shots"])
    cfg["reps"] = int(p["shots"])
    cfg["relax_delay"] = float(p.get("relax_delay_us", 2000.0))
    cfg["ff_gain"] = int(FF_HOLD_GAIN)                  # the flux point being calibrated at
    cfg["ff_hold_gain"] = int(FF_HOLD_GAIN)             # 0 -> Rabi plays no flux pulse (park)
    cfg["readout_after_park"] = bool(READOUT_AFTER_PARK)
    cfg["baseline_rearm_us"] = float(p.get("baseline_rearm_us", 0.5))
    if extra:
        cfg.update(extra)
    return cfg


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
    # QUA behavior: a list of num_pi values -> run each, stack the population curves.
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


def main():
    soc, soccfg = makeProxy()
    outer_folder = outerFolder

    print("=" * 70)
    flux_note = ("PARK (ff_gain=0)" if FF_HOLD_GAIN == 0 else
                 f"HELD flux ff_gain={FF_HOLD_GAIN} DAC, read {'at park' if READOUT_AFTER_PARK else 'AT held flux'}")
    print(f"pi-pulse calibration | {QUBIT} | chip {CHIP_NAME_FOR_CONFIG} | at {flux_note}")
    if FF_HOLD_GAIN != 0:
        print(f"  NOTE: qubit_pi_freq={BaseConfig['qubit_pi_freq']} MHz must be the qubit freq AT ff_gain={FF_HOLD_GAIN}")
    for name, on in [("SS_Cal", P_SS_CAL["run"]),
                     ("Rabi_Chevron_IQ", P_RABI_CHEVRON_IQ["run"]),
                     ("Rabi_Chevron_SS", P_RABI_CHEVRON_SS["run"]),
                     ("Rabi_Linecut_SS", P_RABI_LINECUT_SS["run"])]:
        print(f"  {'[x]' if on else '[ ]'} {name}")
    print("=" * 70)

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
