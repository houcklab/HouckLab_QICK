import os
import sys

_d = os.path.dirname(os.path.abspath(__file__))
while _d != os.path.dirname(_d):
    if os.path.isdir(os.path.join(_d, "WorkingProjects")):
        if _d not in sys.path:
            sys.path.insert(0, _d)
        break
    _d = os.path.dirname(_d)

from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.socProxy import makeProxy
from WorkingProjects.TLS_Spectroscopy.Client_modules.Calib.initialize import outerFolder
from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.GateCalibration import run_rabi_chevron_iq

N_RUNS = 3


def main():
    soc, soccfg = makeProxy()
    for k in range(N_RUNS):
        print(f"\n===== Rabi chevron {k + 1}/{N_RUNS} =====")
        run_rabi_chevron_iq(outerFolder, soc, soccfg)


if __name__ == "__main__":
    main()
