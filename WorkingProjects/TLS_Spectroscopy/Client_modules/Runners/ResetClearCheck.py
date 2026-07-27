import os
import sys

_d = os.path.dirname(os.path.abspath(__file__))
while _d != os.path.dirname(_d):
    if os.path.isdir(os.path.join(_d, "WorkingProjects")):
        if _d not in sys.path:
            sys.path.insert(0, _d)
        break
    _d = os.path.dirname(_d)

import matplotlib
matplotlib.use("Agg", force=True)

from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.socProxy import makeProxy
from WorkingProjects.TLS_Spectroscopy.Client_modules.Calib.initialize import BaseConfig, outerFolder
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mActiveResetProbe import ActiveResetProbe

QUBIT = "q4"
SHOTS = 2000


def main():
    soc, soccfg = makeProxy()

    probe = ActiveResetProbe(soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outerFolder,
                             suffix="ResetClear_Phase", cfg=dict(BaseConfig))
    d = probe.calibrate_res_phase().get("data", {})
    if not d.get("supported") or not d.get("recommended"):
        print("[clear] no feedback discrimination.")
        return
    res_phase = float(d.get("best_res_phase", BaseConfig.get("res_phase", 0.0)))
    rec = d["recommended"]
    thr, gb = int(rec["threshold_raw"]), bool(rec["ground_below"])
    print(f"[clear] res_phase={res_phase:.1f} thr={thr} ground_below={gb}\n")

    configs = [
        ("msync=0.2 it=3", 0.2, 3, 0.05),
        ("msync=1.0 it=3", 1.0, 3, 0.05),
        ("msync=2.0 it=3", 2.0, 3, 0.05),
        ("msync=4.0 it=3", 4.0, 3, 0.05),
        ("msync=6.0 it=3", 6.0, 3, 0.05),
        ("msync=4.0 it=6", 4.0, 6, 0.05),
    ]

    print("prepared-|e> residual after reset (want <~0.1; the gate needs <0.2). "
          "prepared-|g> should stay ~0.")
    print(f"{'config':18s} | reset |g> resid | reset |e> resid | works")
    print("-" * 66)
    for name, msync, iters, settle in configs:
        probe.cfg["reset_meas_syncdelay_us"] = float(msync)
        probe.cfg["reset_settle_us"] = float(settle)
        probe.cfg["reset_max_iters"] = int(iters)
        r = probe._residual_at(res_phase, thr, gb, SHOTS)
        print(f"{name:18s} |     {r['reset_ground']:+.3f}      |     "
              f"{r['reset_excited']:+.3f}      | {bool(r['works'])}")

    print("\n[clear] If |e> residual drops as msync grows -> the conditional pi was firing into an "
          "un-cleared cavity; set reset_meas_syncdelay_us to the smallest value that grounds |e>. "
          "If it stays high at every msync -> it is discrimination/pi-calibration limited, not cavity.")


if __name__ == "__main__":
    main()
