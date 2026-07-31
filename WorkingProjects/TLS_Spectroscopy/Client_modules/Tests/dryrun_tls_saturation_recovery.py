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
        "WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSSaturationRecovery")
    rng = np.random.default_rng(731)
    out_dir = tempfile.mkdtemp(prefix="TLSSaturationRecovery_dryrun_")
    A.TLS._load_correction = lambda correction, folder: None
    p = dict(A.P)
    p.update({
        "pump_gains": [1000, 4000, 7000],
        "dose_repeats": 4,
        "confirmation_repeats": 5,
        "recovery_us": [3.0, 30.0],
        "recovery_repeats": 3,
        "shots": 80,
        "park_cal_shots": 80,
        "reset_probe_shots": 80,
        "min_excess_z": 2.0,
        "confirmation_min_excess_z": 2.0,
        "checkpoint_every": 2,
        "progress_every": 1000,
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

    class FakeSaturation:
        def __init__(self, **kw):
            self.ff_gain = float(kw["ff_gain"])
            self.pump_gain = int(kw["pump_gain"])
            self.recovery = float(kw["recovery_us"])
            self.arm = str(kw["arm"])
            self.shots = int(kw["shots"])
            self.metrics = {}
            self.raw = {}

        def acquire(self, **kw):
            role = dc_roles[round(self.ff_gain, 6)]
            dose = {1000: 0.03, 4000: 0.08, 7000: 0.18}[self.pump_gain]
            effect = dose * np.exp(-self.recovery / 80.0) if role == "tls" else 0.005
            probability = 0.62 + (effect if self.arm == "pump" else 0.0)
            measured = float(np.clip(probability + rng.normal(0.0, 0.004), 0.0, 1.0))
            excited = rng.random(self.shots) < measured
            i = np.where(excited, 3.0, -3.0) + rng.normal(0.0, 0.25, self.shots)
            q = rng.normal(0.0, 0.25, self.shots)
            reset_i = rng.normal(-3.0, 0.25, (self.shots, 3))
            reset_q = rng.normal(0.0, 0.25, (self.shots, 3))
            self.metrics = {
                "P_excited": measured,
                "population_corrected": measured,
                "reset_last_P_excited": 0.02,
            }
            self.raw = {"reset_i": reset_i, "reset_q": reset_q, "i": i, "q": q}
            return self.metrics

    reset_record = {
        "use": "rot",
        "threshold_raw": 100,
        "oper": "lower",
        "ground_below": True,
        "rot_reset": {"c_int": 1, "s_int": 0, "excite_threshold": 100,
                      "max_iters": 3},
    }
    A.SingleShot1Q = FakeParkSS
    A.TLSSaturationProbe = FakeSaturation
    A.run_reset_calibration = lambda *a, **kw: (reset_record, 0.01)
    result = A.run(None, None, outer_folder=out_dir, settings=p)
    with h5py.File(result["h5"], "r") as handle:
        assert handle.attrs["schema"] == "tls_saturation_recovery_v1"
        assert bool(handle.attrs["dose_detected"])
        assert bool(handle.attrs["confirmation_stage_run"])
        assert bool(handle.attrs["dose_confirmed"])
        assert bool(handle.attrs["recovery_stage_run"])
        assert int(handle["dose_scan"].attrs["completed_points"]) == 72
        assert int(handle["confirmation"].attrs["completed_points"]) == 30
        assert int(handle["recovery_sweep"].attrs["completed_points"]) == 36
        assert handle["dose_scan/I"].shape == (72, 80)
        assert handle["dose_scan/reset_I"].shape == (72, 80, 3)
    table = pd.read_csv(result["csv"])
    assert len(table) == 138
    assert set(table["stage"]) == {"dose_scan", "confirmation", "recovery_sweep"}
    assert os.path.isfile(result["plot"])
    print(f"### OUTPUT_DIR {out_dir}")
    print(f"### H5 {result['h5']}")
    print("=== TLS SATURATION RECOVERY DRY RUN COMPLETED ===")


if __name__ == "__main__":
    main()
