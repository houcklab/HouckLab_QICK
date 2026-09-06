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
runner.P_QUBIT_SPEC.update({
    "run": True,
    "shots": 1000,
    "freq_start_mhz": 4364.5,
    "freq_stop_mhz": 4367.5,
    "freq_points": 201,
    "spec_gain": 15000,
    "spec_length_us": 1.0,
    "relax_delay_us": 1000.0,
})
runner.P_QUBIT_SPEC_SWEEP["run"] = False
runner.P_SS_CAL["run"] = False
runner.P_RABI_CHEVRON_IQ["run"] = False
runner.P_RABI_CHEVRON_SS["run"] = False
runner.P_READOUT_OPT["run"] = False
runner.P_QUBIT_OPT["run"] = False


if __name__ == "__main__":
    runner.main()
