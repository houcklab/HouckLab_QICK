import matplotlib.pyplot as plt

from WorkingProjects.TLS_Spectroscopy.Client_modules.Calib.initialize import BaseConfig, outerFolder
from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.socProxy import makeProxy
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mAutoTuner import AutoTuner
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import config_updater

QUBIT = "q4"
LIVE_PLOTS = False
APPLY_CONFIG = True
WRITE_READOUT = True
WRITE_QUBIT = True

P_TUNER = {
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

    qubit_ok, readout_ok = data.get("qubit_ok", False), data.get("readout_ok", False)
    if not (qubit_ok or readout_ok):
        print("\n[auto-tune] nothing converged -- BaseConfig untouched.\n"
              "            Summary plot: %s" % exp.iname)
        return
    if not qubit_ok:
        for k in QUBIT_KEYS:
            tuned.pop(k, None)
        print("\n[auto-tune] qubit calibration did not converge -- its keys are NOT written.")
    if not readout_ok:
        print("\n[auto-tune] readout is below the separation floor; its keys are the best "
              "FOUND\n            (write them with WRITE_READOUT, or set it False to keep "
              "the current readout).")
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
