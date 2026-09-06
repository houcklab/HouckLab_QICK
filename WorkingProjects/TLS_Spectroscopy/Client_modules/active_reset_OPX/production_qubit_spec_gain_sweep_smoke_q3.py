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


runner.LIVE_PLOTS = False
runner.RESET_MODE = "active"
runner.P_TRANSMISSION["run"] = False
runner.P_TRANSMISSION_SWEEP["run"] = False
runner.P_QUBIT_SPEC["run"] = False
runner.P_QUBIT_SPEC_SWEEP.update({
    "run": True,
    "shots": 50,
    "freq_start_mhz": 4364.0,
    "freq_stop_mhz": 4368.0,
    "freq_points": 9,
    "gain_min": 3000,
    "gain_max": 7000,
    "gain_points": 3,
    "spec_length_us": 1.0,
})
runner.P_SS_CAL["run"] = False
runner.P_RABI_CHEVRON_IQ["run"] = False
runner.P_RABI_CHEVRON_SS["run"] = False
runner.P_READOUT_OPT["run"] = False
runner.P_QUBIT_OPT["run"] = False


if __name__ == "__main__":
    runner.main()
