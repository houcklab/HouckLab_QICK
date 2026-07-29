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
        "WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.ResetRotationEquivalence")
    truth = reset_sim.install_bench(bench, rot)
    reset_sim.install_runner_common(R)
    truth.base_res_phase = float(R.BaseConfig.get("res_phase", 0.0))
    truth.res_phase_getter = lambda: R.BaseConfig.get("res_phase", 0.0)
    R.CAL_ROUNDS = 6
    R.REPS_PER_CAL = 4
    R.N_OFFSET = 8
    R.OFFSET_DEG = 40.0
    R.SHOTS_FAST = 16000
    R.PROBE_SHOTS = 16000
    R.ITER_SWEEP = [1, 3, 5]
    R.main()
    print("\n=== DRY RUN COMPLETED WITHOUT ERROR ===")


if __name__ == "__main__":
    main()
