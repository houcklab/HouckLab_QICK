import importlib
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, *[".."] * 4))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from WorkingProjects.TLS_Spectroscopy.Client_modules.Tests import reset_sim


def main():
    reset_sim.install_stubs()
    seed = int(os.environ.get("RESET_SIM_SEED", "7"))
    print(f"[dryrun] RESET_SIM_SEED = {seed}")
    rot = importlib.import_module(
        "WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.active_reset_rot")
    bench = importlib.import_module(
        "WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mResetBench")
    t1 = importlib.import_module(
        "WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mT1VsFlux")
    R = importlib.import_module(
        "WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.ResetRotationT1")
    truth = reset_sim.TruthState(seed=seed)
    reset_sim.install_bench(bench, rot, truth=truth)
    reset_sim.install_t1(t1, rot, truth=truth)
    reset_sim.install_runner_common(R)
    truth.base_res_phase = float(R.BaseConfig.get("res_phase", 0.0))
    truth.res_phase_getter = lambda: R.BaseConfig.get("res_phase", 0.0)
    R.outerFolder = tempfile.mkdtemp(prefix="RotT1_dryrun_")
    R.N_PASS_PAIRS = 2
    R.SHOTS_3PT = 600
    R.PROBE_SHOTS = 8000
    R.POINT_ORDER_SEED = 1000 + seed
    R.main()
    print("\n=== DRY RUN COMPLETED WITHOUT ERROR ===")


if __name__ == "__main__":
    main()
