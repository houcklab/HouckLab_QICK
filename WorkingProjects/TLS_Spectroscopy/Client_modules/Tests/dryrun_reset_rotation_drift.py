import importlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, *[".."] * 4))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from WorkingProjects.TLS_Spectroscopy.Client_modules.Tests import reset_sim


def main():
    reset_sim.install_stubs()
    rot = importlib.import_module(
        "WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.active_reset_rot")
    bench = importlib.import_module(
        "WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mResetBench")
    R = importlib.import_module(
        "WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.ResetRotationDrift")
    seed = int(os.environ.get("RESET_SIM_SEED", "7"))
    truth = reset_sim.TruthState(seed=seed)
    truth.drift_deg_amp = 30.0
    truth.drift_period_ticks = 120.0
    truth.sep_wobble = 0.03
    reset_sim.install_bench(bench, rot, truth=truth)
    reset_sim.install_runner_common(R)
    print(f"simulated instrument: seed {seed}, angle drift amplitude "
          f"{truth.drift_deg_amp:g} deg, period {truth.drift_period_ticks:g} ticks, "
          f"separation wobble {truth.sep_wobble:g}")
    R.DURATION_MIN = 0.0
    R.MIN_CYCLES = 24
    R.MINI_SHOTS = 4000
    R.ARM_SHOTS = 4000
    R.main()
    print("\n=== DRY RUN COMPLETED WITHOUT ERROR ===")


if __name__ == "__main__":
    main()
