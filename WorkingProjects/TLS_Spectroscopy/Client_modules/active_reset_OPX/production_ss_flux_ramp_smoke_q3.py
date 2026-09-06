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
    SingleQubitCoherence as runner,
)


runner.LIVE_PLOTS = False
runner.RESET_MODE = "passive"
runner.P_SS_CAL["run"] = False
runner.P_SS_FLUX_RAMP.update({
    "run": True,
    "shots": 500,
    "number_pi_pulses": 1,
    "ground_threshold": 0.7,
    "excursion_gain": -20000,
    "qubit_pi_gain": None,
    "flux_hold_us": 1.0,
    "flux_tail_compensation": None,
})
runner.P_T1["run"] = False
runner.P_T1_FLUX_RAMP["run"] = False


if __name__ == "__main__":
    runner.main()
