import importlib
import os
import sys
import tempfile

import h5py
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, *[".."] * 4))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from WorkingProjects.TLS_Spectroscopy.Client_modules.Tests import reset_sim


def main():
    reset_sim.install_stubs()
    A = importlib.import_module(
        "WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSMemoryAudit")
    rng = np.random.default_rng(731)
    out_dir = tempfile.mkdtemp(prefix="TLSMemoryAudit_dryrun_")
    A.TLS._load_correction = lambda correction, folder: None
    p = dict(A.P)
    p.update({
        "interaction_min_us": 0.0,
        "interaction_max_us": 0.8,
        "interaction_step_us": 0.2,
        "storage_us": [0.0, 1.0, 10.0],
        "shots": 40,
        "park_cal_shots": 40,
        "smooth_points": 3,
        "checkpoint_every": 2,
        "progress_every": 20,
    })
    targets, _, _ = A.target_table(p)
    dc_roles = {round(float(target["dc_gain"]), 6): target["role"] for target in targets}

    class FakeParkSS:
        def __init__(self, **kw):
            n = int(kw["cfg"]["shots"])
            self.I_0 = rng.normal(-3.0, 0.25, n)
            self.Q_0 = rng.normal(0.0, 0.25, n)
            self.I_1 = rng.normal(3.0, 0.25, n)
            self.Q_1 = rng.normal(0.0, 0.25, n)
            self.calib_params = {
                "scale_factor": 1.0,
                "threshold": 0.0,
                "read_theta": 0.0,
                "ground_threshold": -1.0,
            }
            self.max_F = 0.99

        def acquire(self, **kw):
            return None

    class FakeMemory:
        def __init__(self, **kw):
            self.ff_gain = float(kw["ff_gain"])
            self.interaction = float(kw["interaction_us"])
            self.storage = float(kw["storage_us"])
            self.sequence = str(kw["sequence"])
            self.shots = int(kw["shots"])
            self.metrics = {}
            self.raw = {}

        def acquire(self, **kw):
            role = dc_roles[round(self.ff_gain, 6)]
            if self.sequence == "ground_double":
                probability = 0.04
            else:
                depletion = 0.55 * np.exp(-((self.interaction - 0.6) / 0.22) ** 2)
                single = 0.88 - (depletion if role == "tls" else 0.08 * depletion)
                if self.sequence == "single":
                    probability = single * np.exp(-self.storage / 180.0)
                else:
                    retrieval = (0.24 * np.exp(-self.storage / 30.0)
                                 if role == "tls" else 0.01)
                    probability = single * np.exp(-self.storage / 180.0) + retrieval
            probability = float(np.clip(probability, 0.0, 1.0))
            excited = rng.random(self.shots) < probability
            i = np.where(excited, 3.0, -3.0) + rng.normal(0.0, 0.25, self.shots)
            q = rng.normal(0.0, 0.25, self.shots)
            empty = np.full(self.shots, np.nan)
            measured = float(np.mean(excited))
            self.metrics = {
                "P_excited": measured,
                "population_corrected": measured,
                "keep_fraction": 1.0,
            }
            self.raw = {
                "herald_i": empty,
                "herald_q": empty.copy(),
                "i": i,
                "q": q,
            }
            return self.metrics

    A.SingleShot1Q = FakeParkSS
    A.TLSMemory = FakeMemory
    result = A.run(None, None, outer_folder=out_dir, settings=p)
    with h5py.File(result["h5"], "r") as handle:
        assert handle.attrs["schema"] == "tls_population_memory_audit_v1"
        assert bool(handle.attrs["retrieval_detected"])
        assert bool(handle.attrs["storage_stage_run"])
        assert int(handle["interaction_scan"].attrs["completed_points"]) == 45
        assert int(handle["storage_sweep"].attrs["completed_points"]) == 27
        assert handle["interaction_scan/I"].shape == (45, 40)
        assert handle["storage_sweep/I"].shape == (27, 40)
    table = pd.read_csv(result["csv"])
    assert len(table) == 72
    assert set(table["stage"]) == {"interaction_scan", "storage_sweep"}
    assert os.path.isfile(result["plot"])
    print(f"### OUTPUT_DIR {out_dir}")
    print(f"### H5 {result['h5']}")
    print("=== TLS MEMORY AUDIT DRY RUN COMPLETED ===")


if __name__ == "__main__":
    main()
