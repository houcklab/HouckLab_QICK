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
runner.RESET_MODE = "passive"
runner.P_TRANSMISSION["run"] = False
runner.P_TRANSMISSION_SWEEP["run"] = False
runner.P_QUBIT_SPEC["run"] = False
runner.P_QUBIT_SPEC_SWEEP["run"] = False
runner.P_SS_CAL["run"] = False
runner.P_RABI_CHEVRON_IQ["run"] = False
runner.P_RABI_CHEVRON_SS["run"] = False
runner.P_READOUT_OPT["run"] = False
runner.P_QUBIT_OPT.update({
    "run": True,
    "shots": 50,
    "num_pi": 1,
    "pulse_type": "X180",
    "freq_span_mhz": 1.0,
    "freq_points": 5,
    "gain_min": 11500,
    "gain_max": 15500,
    "gain_points": 5,
    "x90_validation_shots": 100,
    "x90_validation_rounds": 2,
})


if __name__ == "__main__":
    runner.main()
