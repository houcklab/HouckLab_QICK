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
BIG = 10_000_000


def main():
    soc, soccfg = makeProxy()

    probe = ActiveResetProbe(soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outerFolder,
                             suffix="ResetFlip_Phase", cfg=dict(BaseConfig))
    d = probe.calibrate_res_phase().get("data", {})
    if not d.get("supported") or not d.get("recommended"):
        print("[flip] no feedback discrimination.")
        return
    res_phase = float(d.get("best_res_phase", BaseConfig.get("res_phase", 0.0)))
    rec = d["recommended"]
    thr, gb = int(rec["threshold_raw"]), bool(rec["ground_below"])
    print(f"[flip] res_phase={res_phase:.1f} thr={thr} ground_below={gb}")

    probe.cfg["reset_max_iters"] = 1

    print("\nEach uses ONE reset iteration. reset |g> resid should stay ~0 for a real reset.")
    print(f"{'mode':34s} | reset |g> | reset |e>")
    print("-" * 62)

    r = probe._residual_at(res_phase, thr, gb, SHOTS)
    print(f"{'CONDITIONAL (calibrated thr)':34s} |  {r['reset_ground']:+.3f}  |  {r['reset_excited']:+.3f}")

    r = probe._residual_at(res_phase, BIG, False, SHOTS)
    print(f"{'ALWAYS-FLIP (thr=+1e7, tests pi)':34s} |  {r['reset_ground']:+.3f}  |  {r['reset_excited']:+.3f}")

    r = probe._residual_at(res_phase, -BIG, False, SHOTS)
    print(f"{'NEVER-FLIP (thr=-1e7, sanity)':34s} |  {r['reset_ground']:+.3f}  |  {r['reset_excited']:+.3f}")

    print("\n[flip] READ IT:")
    print("  * NEVER-FLIP should give |g>~0, |e>~1 (the reset does nothing = baseline). Sanity.")
    print("  * ALWAYS-FLIP flips every shot once: |g>-> ~1 (ground driven to excited), and")
    print("    |e>-> ~0 IFF the conditional pi actually inverts the qubit.")
    print("  * So: ALWAYS-FLIP grounds |e> (~0) but CONDITIONAL leaves it high -> the in-loop READ "
          "misreads |e> as ground and skips the flip (discrimination bug, not the pi).")
    print("       ALWAYS-FLIP ALSO leaves |e> high -> the reset pi itself does not invert "
          "(pi gain/freq/timing in the reset path).")


if __name__ == "__main__":
    main()
