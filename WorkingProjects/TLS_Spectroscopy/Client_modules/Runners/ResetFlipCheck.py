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
BIG = 1_000_000


def main():
    soc, soccfg = makeProxy()

    probe = ActiveResetProbe(soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outerFolder,
                             suffix="ResetFlip_Phase", cfg=dict(BaseConfig))
    d = probe.calibrate_res_phase().get("data", {})
    if not d.get("supported") or not d.get("recommended"):
        print("[flip] no feedback discrimination.")
        return
    res_phase = float(d.get("best_res_phase", BaseConfig.get("res_phase", 0.0)))
    print(f"[flip] res_phase={res_phase:.1f}")

    probe.cfg["reset_max_iters"] = 1

    print("\nALWAYS-FLIP (pi forced every shot) at increasing cavity-clear delay before the pi.")
    print("If the reset pi works once photons clear: |g> -> ~1 (driven to excited), |e> -> ~0.")
    print(f"{'mode':30s} | reset |g> | reset |e>")
    print("-" * 58)

    probe.cfg["reset_meas_syncdelay_us"] = 0.2
    r = probe._residual_at(res_phase, -BIG, False, SHOTS)
    print(f"{'NEVER-FLIP (sanity)':30s} |  {r['reset_ground']:+.3f}  |  {r['reset_excited']:+.3f}")

    for msync in (0.2, 1.0, 2.0, 4.0, 8.0):
        probe.cfg["reset_meas_syncdelay_us"] = float(msync)
        r = probe._residual_at(res_phase, BIG, False, SHOTS)
        print(f"{'ALWAYS-FLIP msync=' + format(msync, '.1f') + 'us':30s} |  "
              f"{r['reset_ground']:+.3f}  |  {r['reset_excited']:+.3f}")

    print("\n[flip] READ IT:")
    print("  * |g> rises toward 1 and |e> falls toward 0 as msync grows -> the reset pi is being "
          "detuned by leftover readout photons; fix = fire the conditional pi after the cavity "
          "clears (raise reset_meas_syncdelay_us to the smallest value that flips).")
    print("  * stays flat (|g>~0, |e> high) at every msync -> the reset pi is broken for another "
          "reason (pi gain/freq/waveform in the reset path), not photons.")


if __name__ == "__main__":
    main()
