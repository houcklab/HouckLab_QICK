import importlib
import os
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, *[".."] * 4))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from WorkingProjects.TLS_Spectroscopy.Client_modules.Tests import reset_sim


def main():
    reset_sim.install_stubs()
    import numpy as np
    seed = int(os.environ.get("RESET_SIM_SEED", "7"))
    rot = importlib.import_module(
        "WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.active_reset_rot")
    T1mod = importlib.import_module(
        "WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mT1VsFlux")
    A = importlib.import_module(
        "WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.Step6TimingAudit")
    TLS = A.TLS
    truth = reset_sim.TruthState(seed=seed)
    reset_sim.install_t1(T1mod, rot, truth=truth)
    TLS.FFT1Program = T1mod.FFT1Program
    A.makeProxy = reset_sim.fake_proxy
    out_dir = tempfile.mkdtemp(prefix="TimingAudit_dryrun_")
    A.outerFolder = out_dir
    A.tee_log = types.SimpleNamespace(tee=lambda *a, **k: reset_sim.NullTee())
    TLS._load_correction = lambda cj, of: None

    lg, ug = truth.blob_shots(0.0, 8000)
    le, ue = truth.blob_shots(truth.eta, 8000)
    fit = rot.fit_raw_calibration(lg, ug, le, ue, 3, truth.eta)
    rec = dict(fit["old"])
    rec["oper"] = fit["oper"]
    rec["rot_reset"] = rot.reset_params_from_fit(fit, 3)
    rec["use"] = "rot"
    TLS.probe_reset_params = lambda *a, **k: dict(rec)

    rng = np.random.default_rng(seed)
    ss_flux_points = []
    park_ss_runs = []

    class FakeParkSS:
        def __init__(self, **kw):
            truth.advance()
            park_ss_runs.append(True)
            n = int(kw.get("cfg", {}).get("shots", 1000))
            self.I_0 = rng.normal(-3.0, 1.0, n)
            self.Q_0 = rng.normal(0.0, 1.0, n)
            self.I_1 = rng.normal(3.0, 1.0, n)
            self.Q_1 = rng.normal(0.0, 1.0, n)
            self.calib_params = {"scale_factor": 1.0, "threshold": 0.0,
                                 "read_theta": 0.0, "ground_threshold": -1.0}
            self.max_F = 0.98

        def acquire(self, **kw):
            return None

    class FakeFluxSS:
        def __init__(self, **kw):
            truth.advance()
            cfg = kw.get("cfg", {})
            dc = float(kw["ff_gain"])
            if "qubit_freq_mhz" in kw:
                raise AssertionError(kw["qubit_freq_mhz"])
            if not np.isclose(float(cfg["qubit_pi_freq"]),
                              float(A.BaseConfig["qubit_pi_freq"])):
                raise AssertionError(cfg["qubit_pi_freq"])
            if int(cfg["shots"]) != int(A.SS_SHOTS_PER_DC):
                raise AssertionError(cfg["shots"])
            if not np.isclose(float(kw["flux_hold_us"]),
                              float(A.P6["ss_flux_hold_us"])):
                raise AssertionError(kw["flux_hold_us"])
            ss_flux_points.append(dc)
            n = int(cfg.get("shots", 1000))
            self.I_0 = rng.normal(-3.0, 1.0, n)
            self.Q_0 = rng.normal(0.0, 1.0, n)
            exc = rng.random(n) < truth.eta
            self.I_1 = np.where(exc, 3.0, -3.0) + rng.normal(0, 1.0, n)
            self.Q_1 = rng.normal(0.0, 1.0, n)
            self.calib_params = {
                "scale_factor": 1.0, "threshold": 12345.0,
                "read_theta": 0.0, "ground_threshold": -1.0,
                "flux_ramp_ff_gain": dc,
                "flux_ramp_park_pi_freq_mhz": float(cfg["qubit_pi_freq"]),
                "flux_ramp_pi_gain": int(cfg["qubit_pi_gain"]),
                "flux_ramp_hold_us": float(kw["flux_hold_us"]),
            }
            self.max_F = 0.88
            self.data = {"confusion": [[0.95, 0.2], [0.05, 0.8]]}

        def acquire(self, **kw):
            return None

    A.SingleShot1Q = FakeParkSS
    A.SingleShotFluxRamp = FakeFluxSS
    A.P6 = dict(A.P6, shots=200)
    A.SS_SHOTS_PER_DC = 200
    A.PROGRESS_EVERY = 100
    TLS.INTERLEAVE_ROUNDS = 2
    A.main()
    print(f"### SS_FLUX_POINTS {len(ss_flux_points)}")
    print(f"### PARK_SS_RUNS {len(park_ss_runs)}")
    print(f"### OUTPUT_DIR {out_dir}")
    print("\n=== DRY RUN COMPLETED WITHOUT ERROR ===")


if __name__ == "__main__":
    main()
