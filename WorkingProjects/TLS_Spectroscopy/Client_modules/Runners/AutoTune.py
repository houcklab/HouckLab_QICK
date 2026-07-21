"""
AUTO TUNE -- run once.  Maintains the calibration GRAPH to a fixed point and, on
success, writes the result into Calib/initialize.py's BaseConfig.

    python WorkingProjects/TLS_Spectroscopy/Client_modules/Runners/AutoTune.py

The graph (dependencies in brackets) mirrors the QUA gate_calibration_flux_tunable
bring-up, with the manual "read the number, paste it, re-run" loop automated:

    resonator      []                        -> read_pulse_freq, kappa
    spec           [resonator]               -> qubit_freq        (power-extrapolated)
    rough_pi       [spec, resonator]         -> pi gain           (harmonic-checked)
    chi            [rough_pi]                -> chi, and the ANALYTIC optimal readout freq
    readout_power  [chi, rough_pi]           -> read_pulse_gain   (two-blob outlier gate)
    t1             [rough_pi]                -> T1
    readout_len    [readout_power, t1]       -> read_length       (capped at T1/2)
    single_shot    [readout_len]             -> fidelity, rotation angle
    fine_pi_freq   [single_shot, rough_pi]   -> qubit_pi_freq     (pi-train minimum)
    fine_pi_amp    [fine_pi_freq]            -> qubit_pi_gain     (vertex + cross-M)

Recalibrating a node whose value MOVED by more than its own uncertainty marks its
dependents stale, so e.g. a readout change forces the spec and Rabi that were measured
through the old readout to be re-measured.  Iterates until nothing is stale, keeping the
best-so-far state so a round that makes things worse is never committed.

Nothing uses a pi/2 pulse or any free evolution, so a short T2* cannot block the tune.

WRITES on success only: read_pulse_freq, read_pulse_gain, read_length, res_phase,
qubit_freq, qubit_pi_freq, qubit_pi_gain -- and only those a node actually MEASURED.
A timestamped initialize.py backup and an entry in Calib/pi_calibration_history.json are
made either way.  Ctrl-C is safe: partial data is saved and nothing is written.
"""

import matplotlib.pyplot as plt  # noqa: F401

from WorkingProjects.TLS_Spectroscopy.Client_modules.Calib.initialize import BaseConfig, outerFolder
from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.socProxy import makeProxy
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mAutoTuner import AutoTuner
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import config_updater

QUBIT = "q4"
LIVE_PLOTS = False
APPLY_CONFIG = True          # False -> measure and report only, never touch initialize.py
WRITE_READOUT = True         # gates ALL readout keys (freq, gain, length, phase)
WRITE_QUBIT = True           # gates qubit_freq / qubit_pi_freq / qubit_pi_gain

# Per-node overrides; defaults live in mAutoTuner.DEFAULTS.
P_TUNER = {
    # "max_rounds": 4,
    # "resonator":     {"span_mhz": 4.0, "expected_fwhm_mhz": 0.3},
    # "spec":          {"span_mhz": 20.0, "power_ratios": (1.0, 0.35, 0.12)},
    # "readout_power": {"ratios": (0.25, 0.4, 0.6, 0.85, 1.2, 1.7, 2.4, 3.4),
    #                   "outlier_max": 0.02},
    # "readout_len":   {"lengths_us": (1.0, 2.0, 4.0, 8.0, 14.0, 20.0, 30.0)},
    # "single_shot":   {"shots": 4000, "min_sep_sigma": 2.0},
    # "fine_pi_amp":   {"M_list": (4, 10, 20), "tol_frac": 0.004},
}

READOUT_KEYS = ("read_pulse_freq", "read_pulse_gain", "read_length", "res_phase")
QUBIT_KEYS = ("qubit_freq", "qubit_pi_freq", "qubit_pi_gain")


def main():
    soc, soccfg = makeProxy()
    cfg = dict(BaseConfig)
    exp = AutoTuner(soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outerFolder,
                    suffix="Auto_Tune", cfg=cfg, params=P_TUNER)
    try:
        out = exp.acquire(plotDisp=LIVE_PLOTS)
    finally:
        try:
            exp.save_data()
        except Exception as e:
            print("[auto-tune] save_data failed: %s" % e)
    data = out["data"]
    tuned = dict(data["tuned"])

    config_updater.append_history({
        "time": data["time"], "qubit": QUBIT, "success": bool(data["success"]),
        "failure": data.get("failure"),
        "old": {k: BaseConfig.get(k) for k in tuned},
        "new": tuned,
        "t1_us": data["working"].get("t1_us"),
        "chi_mhz": data["working"].get("chi_mhz"),
        "kappa_mhz": data["working"].get("kappa_mhz"),
        "ss_fidelity": data["working"].get("ss_fidelity"),
        "ss_sep_sigma": data["working"].get("ss_sep_sigma"),
        "report": data.get("report", []),
    })

    if not data["success"]:
        print("\n[auto-tune] not successful -- BaseConfig untouched.\n"
              "            Summary plot: %s" % exp.iname)
        return
    if not WRITE_READOUT:
        for k in READOUT_KEYS:
            tuned.pop(k, None)
    if not WRITE_QUBIT:
        for k in QUBIT_KEYS:
            tuned.pop(k, None)
    if not tuned:
        print("\n[auto-tune] nothing eligible to write (both write flags off).")
        return
    if not APPLY_CONFIG:
        print("\n[auto-tune] APPLY_CONFIG=False -- measured but NOT written:")
        for k in sorted(tuned):
            print("   %-18s %-14s (was %s)" % (k, tuned[k], BaseConfig.get(k)))
        return
    changed = config_updater.update_baseconfig(tuned)
    config_updater.prune_backups(keep=10)
    print("\n[auto-tune] BaseConfig updated (%s):" % config_updater.config_path())
    for k in sorted(changed):
        o, n = changed[k]
        print("   %-18s %-14s -> %s" % (k, o, n))
    print("[auto-tune] backup + history written; done.")


if __name__ == "__main__":
    main()
