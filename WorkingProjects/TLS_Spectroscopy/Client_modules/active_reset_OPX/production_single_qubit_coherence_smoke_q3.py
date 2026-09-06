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
runner.RESET_MODE = "active"
runner.P_SS_CAL["run"] = False
runner.P_SS_FLUX_RAMP["run"] = False
runner.P_T1.update({
    "run": True,
    "shots": 200,
    "t_min_us": 1.0,
    "t_max_us": 500.0,
    "t_points": 5,
})
runner.P_T1_FLUX_RAMP.update({
    "run": True,
    "shots": 200,
    "excursion_gain": -20000,
    "flux_tail_compensation": None,
    "t_min_us": 1.0,
    "t_max_us": 500.0,
    "t_points": 5,
})


if __name__ == "__main__":
    runner.main()
