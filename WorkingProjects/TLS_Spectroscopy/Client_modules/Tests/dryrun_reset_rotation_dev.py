"""Run Runners/ResetRotationDev.py end to end against a simulated instrument.

Every bug that has cost a hardware run on this script so far lived in the
plumbing, not the reset: a raw_shots lookup on the wrong object, a KeyError on
a dict that never had that key, a pi_efficiency read from the wrong nesting
level, and host-scale thresholds applied to raw accumulator buffers.  All four
are catchable without a board.  This stubs qick, the proxy, the single-shot
calibration, the probe and the programs, then executes main() so they are.

The simulated instrument is physically consistent: it applies the SAME reset
chain the analysis models, so the measured residuals that come back out should
match what rot.simulate_reset predicts for the configured thresholds.  That
closes the loop -- it tests the measurement, not just the absence of crashes.

Run directly, or via test_reset_rotation_dev_dryrun.py.
"""
import sys
import types

import numpy as np

IG, QG = -794.0, -3606.0
IE, QE = -22182.0, 2512.0
SIGMA = 7000.0
ETA = 0.74
SHOTS = 4000

_rng = np.random.default_rng(7)


def _install_stubs():
    class _P:
        def __init__(self, *a, **k):
            pass

        def __getattr__(self, n):
            return lambda *a, **k: None

    q = types.ModuleType("qick")
    for n in ("AveragerProgram", "RAveragerProgram", "QickProgram",
              "NDAveragerProgram", "QickConfig", "QickSoc", "AbsQickProgram"):
        setattr(q, n, _P)
    q.__path__ = []
    sys.modules["qick"] = q
    for sub in ("qick.qick_asm", "qick.averager_program", "qick.helpers", "qick.asm_v1"):
        m = types.ModuleType(sub)
        m.__getattr__ = lambda n: _P
        sys.modules[sub] = m
    for name in ("Pyro4", "pyro4"):
        m = types.ModuleType(name)
        m.Proxy = _P
        m.locateNS = lambda **k: None
        m.config = types.SimpleNamespace(SERIALIZER="pickle", PICKLE_PROTOCOL_VERSION=4)
        m.util = types.SimpleNamespace(SerializerBase=_P)
        sys.modules[name] = m
    sys.modules["pyvisa"] = types.ModuleType("pyvisa")
    sys.modules["pyvisa"].ResourceManager = _P
    import matplotlib
    matplotlib.use("Agg")


def _blob_shots(pop, n=SHOTS):
    exc = _rng.random(n) < pop
    return (np.where(exc, IE, IG) + _rng.normal(0, SIGMA, n),
            np.where(exc, QE, QG) + _rng.normal(0, SIGMA, n))


def _rates_single(threshold_raw, ground_below, oper):
    """P(fire the pi | g) and P(fire | e) for the CURRENT single-quadrature scheme."""
    lo_g, up_g = _blob_shots(0.0)
    lo_e, up_e = _blob_shots(1.0)
    g = lo_g if oper == "lower" else up_g
    e = lo_e if oper == "lower" else up_e
    fire = (lambda v: v >= threshold_raw) if ground_below else (lambda v: v < threshold_raw)
    return float(np.mean(fire(g))), float(np.mean(fire(e)))


def _rates_rot(cfg, rot):
    """P(fire) and P(latch) for the rotated scheme, from the configured thresholds."""
    plan = rot.asm_plan(cfg["rot_c_int"], cfg["rot_s_int"])
    lo_g, up_g = _blob_shots(0.0)
    lo_e, up_e = _blob_shots(1.0)
    acc_g = rot.project_acc(lo_g, up_g, plan)
    acc_e = rot.project_acc(lo_e, up_e, plan)
    thr_e = cfg["rot_excite_threshold"]
    thr_g = cfg.get("rot_ground_threshold")
    if plan["excited_above"]:
        b_g, b_e = np.mean(acc_g >= thr_e), np.mean(acc_e >= thr_e)
        a_g, a_e = ((np.mean(acc_g < thr_g), np.mean(acc_e < thr_g))
                    if thr_g is not None else (0.0, 0.0))
    else:
        b_g, b_e = np.mean(acc_g <= thr_e), np.mean(acc_e <= thr_e)
        a_g, a_e = ((np.mean(acc_g > thr_g), np.mean(acc_e > thr_g))
                    if thr_g is not None else (0.0, 0.0))
    return float(a_g), float(b_g), float(a_e), float(b_e)


def install(monkey_target):
    """Patch the runner module in place with a simulated instrument."""
    R = monkey_target
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import active_reset_rot as rot

    R.makeProxy = lambda: (types.SimpleNamespace(tproc=types.SimpleNamespace()),
                           {"readouts": [{"tproc_ch": 0}], "gens": []})

    class FakeSS:
        def __init__(self, **kw):
            self.calib_params = {"threshold": 2.635, "scale_factor": 1,
                                 "read_theta": 2.937, "ground_threshold": -0.06}
            self.max_F = 0.917

        def acquire(self, **kw):
            return None

    R.SingleShot1Q = FakeSS

    class FakeProbe:
        def __init__(self, **kw):
            self.cfg = kw.get("cfg", {})
            lo_g, up_g = _blob_shots(0.0)
            lo_e, up_e = _blob_shots(ETA)
            self.raw_shots = {
                "ground": {"lower": lo_g.astype(np.int64), "upper": up_g.astype(np.int64)},
                "excited": {"lower": lo_e.astype(np.int64), "upper": up_e.astype(np.int64)}}

        def acquire(self, **kw):
            return {"data": {
                "recommended": {"oper": "lower", "threshold_raw": -12947,
                                "ground_below": False},
                "raw_assignment_fidelity": 0.868,
                "raw_assignment_errors": {"p_e_given_g": 0.082, "p_g_given_e": 0.182},
                "reset_floor": 0.060,
                "reset_threshold_tuning": {"pi_efficiency": ETA},
            }}

    R.ActiveResetProbe = FakeProbe

    def fake_read_dmem(soc, addr):
        k, field = divmod(addr - R.ARITH_BASE_ADDR, 4)
        a, b, c_int, s_int = R.ARITH_CASES[k]
        wa, wb = R.wrap32(a * c_int), R.wrap32(b * s_int)
        return [wa, wb, R.wrap32(wa + wb), 0 if R.wrap32(wa + wb) < 0 else 1][field]

    R.read_dmem = fake_read_dmem
    R.ArithProgram = lambda soccfg, cfg: types.SimpleNamespace(
        acquire=lambda *a, **k: None)

    class FakeRotProgram:
        def __init__(self, soccfg, cfg):
            self.cfg = cfg

        def acquire(self, soc, load_pulses=True, progress=False, **kw):
            cfg = self.cfg
            scheme = str(cfg.get("reset_scheme", "none"))
            start_pop = ETA if cfg.get("prep_excited", True) else 0.0
            if scheme == "none":
                pop = start_pop
            elif scheme == "old":
                b_g, b_e = _rates_single(cfg["reset_threshold_raw"],
                                         cfg.get("reset_ground_below", True),
                                         cfg.get("reset_oper", "lower"))
                pop = _mix(rot, 0.0, b_g, 0.0, b_e, start_pop, cfg)
            else:
                a_g, b_g, a_e, b_e = _rates_rot(cfg, rot)
                pop = _mix(rot, a_g, b_g, a_e, b_e, start_pop, cfg)
            return _blob_shots(pop)

    def _mix(rot, a_g, b_g, a_e, b_e, start_pop, cfg):
        iters = int(cfg.get("reset_max_iters", 3))
        from_g = rot.simulate_reset(a_g, b_g, a_e, b_e, ETA, iters, "g")
        from_e = rot.simulate_reset(a_g, b_g, a_e, b_e, ETA, iters, "e")
        return (1.0 - start_pop) * from_g + start_pop * from_e

    R.RotResetProgram = FakeRotProgram
    R.AB_REPEATS = 2
    R.PHASE_OFFSETS_DEG = [0.0, 45.0]

    class _NullTee:
        def __enter__(self):
            return "dryrun"

        def __exit__(self, *a):
            return False

    R.tee_log = types.SimpleNamespace(tee=lambda *a, **k: _NullTee())
    return R


def main():
    _install_stubs()
    sys.path.insert(0, "/Users/rummanrahman/Documents/Princeton/Research/HouckLab_QICK")
    import importlib
    R = importlib.import_module(
        "WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.ResetRotationDev")
    install(R)
    R.main()
    print("\n=== DRY RUN COMPLETED WITHOUT ERROR ===")


if __name__ == "__main__":
    main()
