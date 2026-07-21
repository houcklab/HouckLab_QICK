"""
AUTO PI TUNE -- run this file once; it tunes the pi pulse end-to-end and (on success)
writes the new values into Calib/initialize.py's BaseConfig automatically.

Pipeline (default mode 'pi_only' -- see Experiments/mAutoPiTuner.py for the physics):
  resonator scan -> qubit spec (2-pass) -> rough Rabi -> single shot ->
  fine pi (even-M pi-train minimisation) -> single shot -> verify

NOTHING in this path uses a pi/2 pulse or any free evolution, so a short T2* cannot
block the tune.  A train of M same-phase pi pulses is CPMG-like: it refocuses detuning
and low-frequency dephasing, so its limit is T1 / driven coherence rather than T2*.
For even M the population after the train is sin^2(M*d/2) in the per-pulse angle error
d, so sweeping the gain and MINIMISING the residual finds the true pi, with the minimum
narrowing as 1/M.  Single-shot histograms bracket the calibration and give the absolute
judge of pi quality: the excess of P(g|e) over P(e|g) is the ground-state weight the pi
failed to transfer, which no averaged/normalised measurement can see (those define |e>
as 'whatever the current pi produces').

Set P_TUNER['pipeline'] = {'mode': 'full'} to restore the RamseyXY fine-frequency and
sx-based error-amplification stages (needs T2* >> the pulse length to be meaningful).

What gets written on success (and ONLY on success -- a failed run changes nothing):
  read_pulse_freq, qubit_freq, qubit_pi_freq, qubit_pi_gain, qubit_pi2_gain
  (+ a timestamped initialize.py backup and an appended Calib/pi_calibration_history.json)

qubit_pi2_gain is written as round(pi/2) -- a linear estimate, NOT independently
fine-tuned (the verify stage reports how good it is).

Typical runtime with defaults: ~8-15 min (dominated by relax_delay).  Ctrl-C aborts
safely at any point; nothing is written.
"""

import matplotlib.pyplot as plt  # noqa: F401  (keeps the plotting backend warm)

from WorkingProjects.TLS_Spectroscopy.Client_modules.Calib.initialize import BaseConfig, outerFolder
from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.socProxy import makeProxy
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mAutoPiTuner import AutoPiTuner
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import config_updater

QUBIT = "q4"
LIVE_PLOTS = False           # the tuner always saves its summary PNG regardless
APPLY_CONFIG = True          # False -> measure + report only, never touch initialize.py
UPDATE_READ_FREQ = True      # include read_pulse_freq in the write (resonator stage)

# Per-stage overrides (defaults live in mAutoPiTuner.DEFAULT_PARAMS; uncomment to use).
P_TUNER = {
    # "pipeline":  {"mode": "pi_only"},   # or "full" (adds Ramsey + sx error-amp)
    # "fine_pi":   {"passes": ((4, 0.12, 13), (12, 0.05, 13), (32, 0.018, 13)),
    #               "shots": 400, "tol_rad": 0.010},
    # "single_shot": {"shots": 3000, "min_sep_sigma": 2.0},
    # "resonator": {"run": True, "span_mhz": 3.0, "shots": 300},
    # "spec":      {"run": True, "span_mhz": 12.0, "shots": 500, "spec_gain": None},
    # "rabi":      {"gain_max": 30000, "points": 61, "shots": 400},
    # "ramsey":    {"f_virt_mhz": 1.0, "tau_max_us": 4.0, "shots": 500,
    #               "sign": None},   # +1/-1 to skip the hardware sign probe
    # "fine_amp":  {"n_max": 14, "shots": 700, "tol_rad": 0.010},
    # "verify":    {"shots": 1000, "snr_min": 4.0},
}


def main():
    soc, soccfg = makeProxy()
    cfg = dict(BaseConfig)
    sign_hint = config_updater.last_ramsey_sign()
    if sign_hint is not None:
        print("[auto-pi] reusing hardware-measured Ramsey sign %+d from history" % sign_hint)

    exp = AutoPiTuner(soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outerFolder,
                      suffix="Auto_Pi_Tune", cfg=cfg, params=P_TUNER,
                      ramsey_sign_hint=sign_hint)
    out = exp.acquire(plotDisp=LIVE_PLOTS)
    exp.save_data()
    data = out["data"]
    tuned = data["tuned"]

    # append the run to the calibration history regardless of outcome (the measured
    # Ramsey sign is hardware truth we want to keep even from a failed run)
    old = {k: BaseConfig.get(k) for k in tuned}
    config_updater.append_history({
        "time": data["time"], "qubit": QUBIT, "success": bool(data["success"]),
        "failure": data.get("failure"), "old": old, "new": tuned,
        "ramsey_sign": data.get("ramsey_sign", 0) or None,
        "report": data.get("report", []),
    })

    if not data["success"]:
        print("\n[auto-pi] tune FAILED -- BaseConfig untouched. See the report above "
              "and the summary PNG:\n         %s" % exp.iname)
        return

    updates = dict(tuned)
    if not UPDATE_READ_FREQ:
        updates.pop("read_pulse_freq", None)
    if not APPLY_CONFIG:
        print("\n[auto-pi] APPLY_CONFIG=False -- measured values (NOT written):")
        for k, v in updates.items():
            print("   %-18s %-12s (was %s)" % (k, v, old.get(k)))
        return

    changed = config_updater.update_baseconfig(updates)
    print("\n[auto-pi] BaseConfig updated (%s):" % config_updater.config_path())
    for k, (o, n) in changed.items():
        print("   %-18s %-12s -> %s" % (k, o, n))
    print("[auto-pi] backup + history written; done.")


if __name__ == "__main__":
    main()
