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
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.rfdc_cal import (
    freeze_readout_cal, cal_freeze_status)

RO_CH = 0
N_RUNS = 3


def main():
    soc, soccfg = makeProxy()
    print("cal status before:")
    cal_freeze_status(soc, RO_CH)
    freeze_readout_cal(soc, RO_CH, freeze=True)
    try:
        for k in range(N_RUNS):
            print(f"\n===== frozen Rabi chevron {k + 1}/{N_RUNS} =====")
            run_rabi_chevron_iq(outerFolder, soc, soccfg)
    finally:
        freeze_readout_cal(soc, RO_CH, freeze=False)
        print("\ncal thawed (restored to normal).")


if __name__ == "__main__":
    main()
