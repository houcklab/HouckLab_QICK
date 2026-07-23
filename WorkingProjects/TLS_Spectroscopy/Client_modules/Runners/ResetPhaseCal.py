import os
import sys

_d = os.path.dirname(os.path.abspath(__file__))
while _d != os.path.dirname(_d):
    if os.path.isdir(os.path.join(_d, "WorkingProjects")):
        if _d not in sys.path:
            sys.path.insert(0, _d)
        break
    _d = os.path.dirname(_d)
else:
    raise RuntimeError("Could not find the HouckLab_QICK repo root (no WorkingProjects/ above this file).")

from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.socProxy import makeProxy
from WorkingProjects.TLS_Spectroscopy.Client_modules.Calib.initialize import BaseConfig, outerFolder
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mActiveResetProbe import ActiveResetProbe

QUBIT = "q4"

SWEEP_SHOTS = 800
CHECK_SHOTS = 3000
PHASE_STEP_DEG = 15.0


def main():
    soc, soccfg = makeProxy()
    cfg = dict(BaseConfig)
    cfg["shots"] = cfg["reps"] = int(SWEEP_SHOTS)
    cfg["relax_delay"] = 500.0
    exp = ActiveResetProbe(soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outerFolder,
                           suffix="Reset_Phase_Cal", cfg=cfg)
    import numpy as np
    exp.calibrate_res_phase(phases=np.arange(0.0, 180.0, PHASE_STEP_DEG),
                            sweep_shots=SWEEP_SHOTS, check_shots=CHECK_SHOTS)
    print("\nDone.  Paste the BEST res_phase into Calib/initialize.py BaseConfig['res_phase'],")
    print("then re-run -- the active-reset probe should read CLEAN with a stable sign.")


if __name__ == "__main__":
    main()
