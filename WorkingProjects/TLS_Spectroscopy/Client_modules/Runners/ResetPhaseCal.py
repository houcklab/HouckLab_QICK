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
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.reset_phase import calibrate_res_phase

QUBIT = "q4"

APPLY_CONFIG = True
SWEEP_SHOTS = 800
CHECK_SHOTS = 3000
PHASE_STEP_DEG = 15.0


def main():
    soc, soccfg = makeProxy()
    best = calibrate_res_phase(soc, soccfg, BaseConfig, QUBIT, outerFolder,
                               apply_config=APPLY_CONFIG, sweep_shots=SWEEP_SHOTS,
                               check_shots=CHECK_SHOTS, phase_step_deg=PHASE_STEP_DEG)
    if best is None:
        return
    if APPLY_CONFIG:
        print("\nDone -- res_phase written to Calib/initialize.py (timestamped backup kept). "
              "The active-reset probe should now read CLEAN with a stable sign.")
    else:
        print(f"\nMeasure-only (APPLY_CONFIG=False). Set BaseConfig['res_phase'] = {best:.1f} "
              "in Calib/initialize.py to apply.")


if __name__ == "__main__":
    main()
