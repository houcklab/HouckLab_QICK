import importlib
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, *[".."] * 4))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from WorkingProjects.TLS_Spectroscopy.Client_modules.Tests import reset_sim


def fake_probe_rec(truth, rot, iters):
    lg, ug = truth.blob_shots(0.0, 8000)
    le, ue = truth.blob_shots(truth.eta, 8000)
    fit = rot.fit_raw_calibration(lg, ug, le, ue, iters, truth.eta)
    rec = dict(fit["old"])
    rec["oper"] = fit["oper"]
    rec["rot_reset"] = rot.reset_params_from_fit(fit, iters)
    rec["use"] = "rot"
    return rec


def main():
    reset_sim.install_stubs()
    seed = int(os.environ.get("RESET_SIM_SEED", "7"))
    rot = importlib.import_module(
        "WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.active_reset_rot")
    T1mod = importlib.import_module(
        "WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mT1VsFlux")
    TLS = importlib.import_module(
        "WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSSpectroscopy")
    truth = reset_sim.TruthState(seed=seed)
    reset_sim.install_t1(T1mod, rot, truth=truth)
    TLS.FFT1Program = T1mod.FFT1Program
    TLS.makeProxy = reset_sim.fake_proxy
    TLS._load_correction = lambda cj, of: None
    TLS.outerFolder = tempfile.mkdtemp(prefix="RotProd_dryrun_")
    rec = fake_probe_rec(truth, rot, 3)
    TLS.probe_reset_params = (
        lambda *a, **k: {**rec, "rot_reset": dict(rec["rot_reset"])})
    TLS.P6_3PT_T1 = dict(TLS.P6_3PT_T1)
    TLS.P6_3PT_T1.update({"run": True, "shots": 600, "dc_min": 0, "dc_max": 9000,
                          "dc_step": 4000, "freq_step_mhz": None,
                          "Ts_us": 60.0})
    TLS.PROBE_RESET = True
    TLS.INTERLEAVE_ROUNDS = 2
    calib = {"scale_factor": 1, "threshold": 0.0, "read_theta": 0.0,
             "ground_threshold": -1.0}

    seen_cfgs = []
    orig_init = T1mod.FFT1Program.__init__

    def spy_init(self, soccfg, cfg):
        seen_cfgs.append(dict(cfg))
        orig_init(self, soccfg, cfg)

    T1mod.FFT1Program.__init__ = spy_init

    print("### SCENARIO 1: USE_ROTATED_RESET=True -- the rotated reset must reach "
          "the production program")
    TLS.USE_ROTATED_RESET = True
    TLS.run_step6_3pt_t1(TLS.outerFolder, None, None, calib, None)
    rot_engaged = [c for c in seen_cfgs if c.get("rot_reset")]
    print(f"### production programs built: {len(seen_cfgs)}, with rot_reset: "
          f"{len(rot_engaged)}")
    assert seen_cfgs and len(rot_engaged) == len(seen_cfgs)
    assert all(c.get("reset_threshold_raw") is not None for c in seen_cfgs)
    print("### every program carried BOTH parameter sets (rotated active, legacy "
          "fallback present)")

    seen_cfgs.clear()
    print("\n### SCENARIO 2: USE_ROTATED_RESET=False -- one flag back to legacy")
    TLS.USE_ROTATED_RESET = False
    TLS.run_step6_3pt_t1(TLS.outerFolder, None, None, calib, None)
    rot_engaged = [c for c in seen_cfgs if c.get("rot_reset")]
    print(f"### production programs built: {len(seen_cfgs)}, with rot_reset: "
          f"{len(rot_engaged)}")
    assert seen_cfgs and len(rot_engaged) == 0
    print("### the identical run reverted to the legacy reset with no other change")

    print("\n=== DRY RUN COMPLETED WITHOUT ERROR ===")


if __name__ == "__main__":
    main()
