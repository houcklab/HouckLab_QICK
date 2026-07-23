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
SHARED_TIMING_KEYS = ("relax_delay",)


def _select_updates(data, write_readout=True, write_qubit=True):
    """Return evidence-eligible values and the flag-filtered write selection."""
    eligible = dict(data.get("eligible_tuned", {}))
    selected = dict(eligible)
    if not data.get("qubit_ok", False) or not write_qubit:
        for key in QUBIT_KEYS:
            selected.pop(key, None)
    if not data.get("readout_ok", False) or not write_readout:
        for key in READOUT_KEYS:
            selected.pop(key, None)
    if not ((data.get("qubit_ok", False) and write_qubit)
            or (data.get("readout_ok", False) and write_readout)):
        for key in SHARED_TIMING_KEYS:
            selected.pop(key, None)
    return eligible, selected


def _history_entry(data, eligible, selected, applied, write_error=None):
    """History distinguishes measured, eligible, attempted, and actually applied keys."""
    pi2_would_be_stale = bool(
        "qubit_pi_gain" in selected
        and "qubit_pi2_gain" in BaseConfig
        and int(selected["qubit_pi_gain"]) != int(BaseConfig.get("qubit_pi_gain", -1)))
    return {
        "time": data["time"], "qubit": QUBIT, "success": bool(data["success"]),
        "failure": data.get("failure"), "write_error": write_error,
        "applied": bool(applied),
        "measured": dict(data.get("tuned", {})),
        "eligible": dict(eligible), "attempted": dict(selected),
        "old": {k: BaseConfig.get(k) for k in selected},
        "new": dict(selected) if applied else {},
        "t1_us": data["working"].get("t1_us"),
        "t1_verified": data["working"].get("t1_verified"),
        "chi_mhz": data["working"].get("chi_mhz"),
        "kappa_mhz": data["working"].get("kappa_mhz"),
        "ss_fidelity": data["working"].get("ss_fidelity"),
        "ss_fidelity_se": data["working"].get("ss_fidelity_se"),
        "ss_fidelity_lcb": data["working"].get("ss_fidelity_lcb"),
        "ss_sep_sigma": data["working"].get("ss_sep_sigma"),
        "verified": data["working"].get("verified"),
        "fixed_point": data["working"].get("fixed_point"),
        "qubit_ok": data.get("qubit_ok"), "readout_ok": data.get("readout_ok"),
        "pi_verified": data["working"].get("pi_verified"),
        "pi_fidelity_verified": data["working"].get("pi_fidelity_verified"),
        "pi_fidelity_binding": data["working"].get("pi_fidelity_binding"),
        "pulse_fingerprint": data["working"].get("pulse_fingerprint"),
        # A calibrated X180 does not prove that half its DAC code is an X90 when the
        # microwave chain is nonlinear.  Preserve the old value, but make its invalidity
        # explicit and auditable whenever this runner applies a changed pi gain.
        "qubit_pi2_stale": bool(applied and pi2_would_be_stale),
        "qubit_pi2_would_be_stale": pi2_would_be_stale,
        "qubit_pi2_gain_unchanged": BaseConfig.get("qubit_pi2_gain"),
        "freq_verified": data["working"].get("freq_verified"),
        "readout_verified": data["working"].get("readout_verified"),
        "ss_verify_sigma": data["working"].get("ss_verify_sigma"),
        "report": data.get("report", []),
    }


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
    # AutoTuner performs the evidence gating per key group.  ``tuned`` is retained in
    # the saved data for diagnostics; only ``eligible_tuned`` may reach BaseConfig.
    eligible, tuned = _select_updates(data, WRITE_READOUT, WRITE_QUBIT)

    qubit_ok, readout_ok = data.get("qubit_ok", False), data.get("readout_ok", False)
    if not (qubit_ok or readout_ok):
        config_updater.append_history(_history_entry(data, eligible, {}, False))
        print("\n[auto-tune] nothing converged -- BaseConfig untouched.\n"
              "            Summary plot: %s" % exp.iname)
        return
    if not qubit_ok:
        print("\n[auto-tune] qubit calibration did not converge -- its keys are NOT written.")
    if not readout_ok:
        print("\n[auto-tune] readout did not pass its fresh verification; readout keys are "
              "NOT written.  They remain in the saved diagnostic data.")
    if not tuned:
        config_updater.append_history(_history_entry(data, eligible, {}, False))
        print("\n[auto-tune] nothing eligible to write after verification and write flags.")
        return
    if not APPLY_CONFIG:
        config_updater.append_history(_history_entry(data, eligible, tuned, False))
        print("\n[auto-tune] APPLY_CONFIG=False -- measured but NOT written:")
        for k in sorted(tuned):
            print("   %-18s %-14s (was %s)" % (k, tuned[k], BaseConfig.get(k)))
        return
    try:
        changed = config_updater.update_baseconfig(tuned)
    except Exception as exc:
        config_updater.append_history(
            _history_entry(data, eligible, tuned, False, write_error=str(exc)))
        raise
    config_updater.append_history(_history_entry(data, eligible, tuned, True))
    config_updater.prune_backups(keep=10)
    print("\n[auto-tune] BaseConfig updated (%s):" % config_updater.config_path())
    for k in sorted(changed):
        o, n = changed[k]
        print("   %-18s %-14s -> %s" % (k, o, n))
    if ("qubit_pi_gain" in tuned and "qubit_pi2_gain" in BaseConfig
            and int(tuned["qubit_pi_gain"]) != int(BaseConfig["qubit_pi_gain"])):
        print("[auto-tune] WARNING: qubit_pi2_gain was not measured and is now STALE. "
              "It was deliberately left unchanged; run GateCalibration with X90 before "
              "using an X90 pulse (half the X180 DAC code is not treated as evidence).")
    print("[auto-tune] backup + history written; done.")


if __name__ == "__main__":
    main()
