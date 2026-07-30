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
    A.SingleShot1Q = reset_sim.make_fake_ss()
    A.outerFolder = tempfile.mkdtemp(prefix="TimingAudit_dryrun_")
    A.tee_log = __import__("types").SimpleNamespace(
        tee=lambda *a, **k: reset_sim.NullTee())
    TLS._load_correction = lambda cj, of: None

    lg, ug = truth.blob_shots(0.0, 8000)
    le, ue = truth.blob_shots(truth.eta, 8000)
    fit = rot.fit_raw_calibration(lg, ug, le, ue, 3, truth.eta)
    rec = dict(fit["old"])
    rec["oper"] = fit["oper"]
    rec["rot_reset"] = rot.reset_params_from_fit(fit, 3)
    rec["use"] = "rot"
    TLS.probe_reset_params = lambda *a, **k: dict(rec)

    class FakeTransmission:
        def __init__(self, **kw):
            self.cfg = kw.get("cfg", {})

        def acquire(self, **kw):
            truth.advance()
            return None

    A.Transmission = FakeTransmission
    A.SAMPLE_DC_COUNTS = [2, 4]
    A.TIMING_REPS = 1
    A.P6 = dict(A.P6, shots=300)
    A.main()
    print("\n=== DRY RUN COMPLETED WITHOUT ERROR ===")


if __name__ == "__main__":
    main()
