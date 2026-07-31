import importlib
import os
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, *[".."] * 4))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from WorkingProjects.TLS_Spectroscopy.Client_modules.Tests import reset_sim


def main():
    reset_sim.install_stubs()
    A = importlib.import_module(
        "WorkingProjects.TLS_Spectroscopy.Client_modules.Runners."
        "RoundTripRamseyHoldSweep")
    rng = np.random.default_rng(31)
    out_dir = tempfile.mkdtemp(prefix="RoundTripRamseyHoldSweep_dryrun_")
    A.TLS._load_correction = lambda correction, folder: None
    p = dict(A.P)
    p.update({
        "hold_dense_min_us": 0.0,
        "hold_dense_max_us": 0.2,
        "hold_dense_step_us": 0.2,
        "hold_long_us": [1.0],
        "shots": 40,
        "rounds": 2,
        "park_cal_shots": 40,
        "t1_shots": 40,
        "t1_rounds": 2,
        "checkpoint_every": 2,
        "progress_every": 4,
    })

    class FakeParkSS:
        def __init__(self, **kw):
            n = int(kw["cfg"]["shots"])
            self.I_0 = rng.normal(-3.0, 0.3, n)
            self.Q_0 = rng.normal(0.0, 0.3, n)
            self.I_1 = rng.normal(3.0, 0.3, n)
            self.Q_1 = rng.normal(0.0, 0.3, n)
            self.calib_params = {
                "scale_factor": 1.0,
                "threshold": 0.0,
                "read_theta": 0.0,
                "ground_threshold": -1.0,
            }
            self.max_F = 0.98

        def acquire(self, **kw):
            return None

    class FakeChannel:
        def __init__(self, **kw):
            self.dc = float(kw["ff_gain"])
            self.hold = float(kw["flux_hold_us"])
            self.shots = int(kw["shots"])

        def acquire(self, **kw):
            magnitude = 0.85 * np.exp(-self.hold / 50.0)
            phase = 0.4 + self.hold * 0.2 + self.dc * 1e-5
            pg, pe = 0.04, 0.94
            pi = 0.5 + 0.45 * magnitude * np.cos(phase)
            pq = 0.5 + 0.45 * magnitude * np.sin(phase)
            probabilities = {"g": pg, "e": pe, "i": pi, "q": pq}
            self.raw = {}
            for arm in A.RAMSEY_ARMS:
                excited = rng.random(self.shots) < probabilities[arm]
                values = np.where(excited, 3.0, -3.0) + rng.normal(
                    0.0, 0.3, self.shots)
                empty = np.full(self.shots, np.nan)
                self.raw[arm] = {
                    "herald_i": empty,
                    "herald_q": empty.copy(),
                    "i": values,
                    "q": rng.normal(0.0, 0.3, self.shots),
                }
            self.metrics = {
                "P_g": pg,
                "P_e": pe,
                "P_i": pi,
                "P_q": pq,
                "reference_contrast": pe - pg,
                "local_reference_valid": 1.0,
                "assignment_P_g": 0.0,
                "assignment_P_e": 1.0,
                "assignment_contrast": 1.0,
                "population_g": pg,
                "population_e": pe,
                "ramsey_i": magnitude * np.cos(phase),
                "ramsey_q": magnitude * np.sin(phase),
                "coherence_magnitude": magnitude,
                "coherence_phase_rad": phase,
                "valid": 1.0,
                "keep_fraction_g": 1.0,
                "keep_fraction_e": 1.0,
                "keep_fraction_i": 1.0,
                "keep_fraction_q": 1.0,
            }
            return self.metrics

    def fake_t1(soc, soccfg, cfg, settings, folder, targets, calib, stage):
        n = len(targets)
        t1 = np.asarray([35.0 if target["role"] == "tls" else 120.0
                         for target in targets], dtype=float)
        return {
            "T1_3pt_us": t1,
            "T1_3pt_valid_mask": np.ones(n),
            "P0": np.full(n, 0.05),
            "P1": np.full(n, 0.95),
            "Ps": 0.05 + 0.90 * np.exp(-59.0 / t1),
            "ref_contrast_3pt": np.full(n, 0.90),
            "Ts_effective_ns": 59000.0,
            "elapsed_s": 0.01,
        }

    A.SingleShot1Q = FakeParkSS
    A.RoundTripRamsey = FakeChannel
    A.run_t1_check = fake_t1
    result = A.run(None, None, outer_folder=out_dir, settings=p)
    print(f"### OUTPUT_DIR {out_dir}")
    print(f"### H5 {result['h5']}")
    print("=== ROUND TRIP RAMSEY HOLD SWEEP DRY RUN COMPLETED ===")


if __name__ == "__main__":
    main()
