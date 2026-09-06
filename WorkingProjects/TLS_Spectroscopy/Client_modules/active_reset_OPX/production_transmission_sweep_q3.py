from pathlib import Path
import sys


_root = Path(__file__).resolve()
for parent in _root.parents:
    if (parent / "WorkingProjects").is_dir():
        if str(parent) not in sys.path:
            sys.path.insert(0, str(parent))
        break
else:
    raise RuntimeError("Could not locate the HouckLab_QICK repository root")


from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
    GateCalibration as runner,
)


runner.P_TRANSMISSION["run"] = False
runner.P_TRANSMISSION_SWEEP["run"] = True
runner.P_TRANSMISSION_SWEEP["shots"] = 100
runner.P_TRANSMISSION_SWEEP["freq_start_mhz"] = None
runner.P_TRANSMISSION_SWEEP["freq_stop_mhz"] = None
runner.P_TRANSMISSION_SWEEP["freq_points"] = 41
runner.P_TRANSMISSION_SWEEP["gain_min"] = 500
runner.P_TRANSMISSION_SWEEP["gain_max"] = 1500
runner.P_TRANSMISSION_SWEEP["gain_points"] = 3
runner.P_TRANSMISSION_SWEEP["spec_len_us"] = 10.0
runner.P_QUBIT_SPEC["run"] = False
runner.P_QUBIT_SPEC_SWEEP["run"] = False
runner.P_SS_CAL["run"] = False
runner.P_RABI_CHEVRON_IQ["run"] = False
runner.P_RABI_CHEVRON_SS["run"] = False
runner.P_READOUT_OPT["run"] = False
runner.P_QUBIT_OPT["run"] = False


if __name__ == "__main__":
    runner.main()
