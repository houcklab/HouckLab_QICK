import importlib
import os
import sys
import tempfile
import types

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, *[".."] * 4))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from WorkingProjects.TLS_Spectroscopy.Client_modules.Tests import reset_sim


def main():
    reset_sim.install_stubs()
    A = importlib.import_module(
        "WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.RoundTripRamseyAudit")
    rng = np.random.default_rng(19)
    out_dir = tempfile.mkdtemp(prefix="RoundTripRamsey_dryrun_")
    A.outerFolder = out_dir
    A.makeProxy = reset_sim.fake_proxy
    A.tee_log = types.SimpleNamespace(tee=lambda *a, **k: reset_sim.NullTee())
    A.SPAN_MHZ = 20.0
    A.PARK_CAL_SHOTS = 40
    A.PROGRESS_EVERY = 10
    A.P = dict(A.P, shots=40, channel_shots=40, channel_rounds=2)
    A.TLS._load_correction = lambda cj, of: None

    def resolve(p, *args):
        result = dict(p)
        result.update({
            "reset_threshold_raw": 11177,
            "reset_oper": "upper",
            "reset_ground_below": True,
            "rot_reset": {"c_int": -106, "s_int": 2045,
                          "excite_threshold": -24327213.35, "max_iters": 3},
        })
        return result

    A.TLS._resolve_step6_reset = resolve

    class FakeParkSS:
        def __init__(self, **kw):
            n = int(kw["cfg"]["shots"])
            self.I_0 = rng.normal(-3.0, 0.7, n)
            self.Q_0 = rng.normal(0.0, 0.7, n)
            self.I_1 = rng.normal(3.0, 0.7, n)
            self.Q_1 = rng.normal(0.0, 0.7, n)
            self.calib_params = {"scale_factor": 1.0, "threshold": 0.0,
                                 "read_theta": 0.0, "ground_threshold": -1.0}
            self.max_F = 0.96

        def acquire(self, **kw):
            return None

    class FakeChannel:
        def __init__(self, **kw):
            self.cfg = kw["cfg"]
            self.dc = float(kw["ff_gain"])
            self.shots = int(kw["shots"])

        def acquire(self, **kw):
            phase = self.dc / 1800.0
            magnitude = 0.82 - 0.18 * np.exp(-((self.dc - 400.0) / 180.0) ** 2)
            pg, pe = 0.10, 0.82
            mid, half = 0.5 * (pg + pe), 0.5 * (pe - pg)
            pi = mid + half * magnitude * np.cos(phase)
            pq = mid + half * magnitude * np.sin(phase)
            probs = {"g": pg, "e": pe, "i": pi, "q": pq}
            self.raw = {}
            for arm in A.RAMSEY_ARMS:
                exc = rng.random(self.shots) < probs[arm]
                values = np.where(exc, 3.0, -3.0) + rng.normal(0.0, 0.4, self.shots)
                self.raw[arm] = {
                    "herald_i": rng.normal(-3.0, 0.4, self.shots),
                    "herald_q": rng.normal(0.0, 0.4, self.shots),
                    "i": values,
                    "q": rng.normal(0.0, 0.4, self.shots),
                }
            self.metrics = {
                "P_g": pg, "P_e": pe, "P_i": pi, "P_q": pq,
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
                "coherence_phase_rad": np.arctan2(np.sin(phase), np.cos(phase)),
                "valid": 1.0,
                "keep_fraction_g": 1.0, "keep_fraction_e": 1.0,
                "keep_fraction_i": 1.0, "keep_fraction_q": 1.0,
            }
            return self.metrics

    def fake_t1(soc, soccfg, p, base, dc, calib_params):
        t1 = 120.0 - 70.0 * np.exp(-((float(dc) - 400.0) / 180.0) ** 2)
        return {
            "T1_3pt_us": t1,
            "T1_3pt_valid_mask": 1.0,
            "P0": 0.10,
            "P1": 0.82,
            "Ps": 0.10 + 0.72 * np.exp(-59.0 / t1),
            "ref_contrast_3pt": 0.72,
            "Ts_effective_ns": 59000.0,
        }, 0.001

    A.SingleShot1Q = FakeParkSS
    A.RoundTripRamsey = FakeChannel
    A.run_t1_point = fake_t1
    A.main()
    print(f"### OUTPUT_DIR {out_dir}")
    print("=== ROUND TRIP RAMSEY DRY RUN COMPLETED ===")


if __name__ == "__main__":
    main()
