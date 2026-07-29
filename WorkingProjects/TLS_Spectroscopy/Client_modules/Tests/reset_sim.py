import sys
import types

import numpy as np


def install_stubs():
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
    for sub in ("qick.qick_asm", "qick.averager_program", "qick.helpers",
                "qick.asm_v1"):
        m = types.ModuleType(sub)
        m.__getattr__ = lambda n: _P
        sys.modules[sub] = m
    for name in ("Pyro4", "pyro4"):
        m = types.ModuleType(name)
        m.Proxy = _P
        m.locateNS = lambda **k: None
        m.config = types.SimpleNamespace(SERIALIZER="pickle",
                                         PICKLE_PROTOCOL_VERSION=4)
        m.util = types.SimpleNamespace(SerializerBase=_P)
        sys.modules[name] = m
    sys.modules["pyvisa"] = types.ModuleType("pyvisa")
    sys.modules["pyvisa"].ResourceManager = _P
    import matplotlib
    matplotlib.use("Agg")


class TruthState:
    def __init__(self, seed=7):
        self.rng = np.random.default_rng(seed)
        self.ig, self.qg = -794.0, -3606.0
        self.sep0 = 21000.0
        self.theta0_deg = 173.0
        self.sigma = 7000.0
        self.eta = 0.74
        self.thermal_pop = 0.15
        self.drift_deg_amp = 0.0
        self.drift_period_ticks = 40.0
        self.sep_wobble = 0.0
        self.tick = 0
        self.base_res_phase = None
        self.res_phase_getter = None

    def advance(self):
        self.tick += 1

    def current_angle_deg(self):
        ang = self.theta0_deg
        if self.drift_deg_amp:
            ang += self.drift_deg_amp * np.sin(
                2.0 * np.pi * self.tick / self.drift_period_ticks)
        if self.res_phase_getter is not None and self.base_res_phase is not None:
            ang += float(self.res_phase_getter()) - float(self.base_res_phase)
        return ang

    def current_sep(self):
        sep = self.sep0
        if self.sep_wobble:
            sep *= 1.0 + self.sep_wobble * np.sin(
                2.0 * np.pi * self.tick / (self.drift_period_ticks * 1.7))
        return sep

    def excited_center(self):
        th = np.deg2rad(self.current_angle_deg())
        sep = self.current_sep()
        return self.ig + sep * np.cos(th), self.qg + sep * np.sin(th)

    def blob_shots(self, pop, n=4000):
        ie, qe = self.excited_center()
        exc = self.rng.random(n) < float(pop)
        i = np.where(exc, ie, self.ig) + self.rng.normal(0, self.sigma, n)
        q = np.where(exc, qe, self.qg) + self.rng.normal(0, self.sigma, n)
        return i.astype(np.int64), q.astype(np.int64)


TRUTH = TruthState()


def _fire_rates_legacy(truth, threshold_raw, ground_below, oper, n=4000):
    lg, ug = truth.blob_shots(0.0, n)
    le, ue = truth.blob_shots(1.0, n)
    g = lg if oper == "lower" else ug
    e = le if oper == "lower" else ue
    if ground_below:
        return float(np.mean(g >= threshold_raw)), float(np.mean(e >= threshold_raw))
    return float(np.mean(g < threshold_raw)), float(np.mean(e < threshold_raw))


def _fire_rates_rot(truth, rot_mod, cfg, n=4000):
    plan = rot_mod.asm_plan(cfg["rot_c_int"], cfg["rot_s_int"])
    lg, ug = truth.blob_shots(0.0, n)
    le, ue = truth.blob_shots(1.0, n)
    acc_g = rot_mod.project_acc(lg, ug, plan)
    acc_e = rot_mod.project_acc(le, ue, plan)
    thr_e = cfg["rot_excite_threshold"]
    thr_g = cfg.get("rot_ground_threshold")
    if plan["excited_above"]:
        b = (float(np.mean(acc_g >= thr_e)), float(np.mean(acc_e >= thr_e)))
        a = ((float(np.mean(acc_g < thr_g)), float(np.mean(acc_e < thr_g)))
             if thr_g is not None else (0.0, 0.0))
    else:
        b = (float(np.mean(acc_g <= thr_e)), float(np.mean(acc_e <= thr_e)))
        a = ((float(np.mean(acc_g > thr_g)), float(np.mean(acc_e > thr_g)))
             if thr_g is not None else (0.0, 0.0))
    return a[0], b[0], a[1], b[1]


def reset_output_pop(truth, rot_mod, cfg, start_pop):
    scheme = str(cfg.get("reset_scheme", "none"))
    iters = int(cfg.get("reset_max_iters", 3))
    n_rate = int(cfg.get("shots", 4000))
    if scheme == "none":
        return float(start_pop)
    if scheme == "old":
        b_g, b_e = _fire_rates_legacy(truth, cfg["reset_threshold_raw"],
                                      cfg.get("reset_ground_below", True),
                                      cfg.get("reset_oper", "lower"), n=n_rate)
        a_g = a_e = 0.0
    else:
        use_latch = scheme == "rot3"
        a_g, b_g, a_e, b_e = _fire_rates_rot(truth, rot_mod, cfg, n=n_rate)
        if not use_latch:
            a_g = a_e = 0.0
    from_g = rot_mod.simulate_reset(a_g, b_g, a_e, b_e, truth.eta, iters, "g")
    from_e = rot_mod.simulate_reset(a_g, b_g, a_e, b_e, truth.eta, iters, "e")
    return float((1.0 - start_pop) * from_g + start_pop * from_e)


def install_bench(bench_mod, rot_mod, truth=None):
    truth = truth if truth is not None else TRUTH

    class FakeBenchProgram:
        def __init__(self, soccfg, cfg):
            self.cfg = cfg

        def acquire(self, soc, load_pulses=True, progress=False, **kw):
            truth.advance()
            start = truth.eta if self.cfg.get("prep_excited", True) else 0.0
            pop = reset_output_pop(truth, rot_mod, self.cfg, start)
            return truth.blob_shots(pop, int(self.cfg.get("shots", 2000)))

    class FakeProbe:
        def __init__(self, **kw):
            self.cfg = kw.get("cfg", {})
            truth.advance()
            lg, ug = truth.blob_shots(0.0)
            le, ue = truth.blob_shots(truth.eta)
            self.raw_shots = {"ground": {"lower": lg, "upper": ug},
                              "excited": {"lower": le, "upper": ue}}

        def acquire(self, **kw):
            lg = self.raw_shots["ground"]["lower"]
            le = self.raw_shots["excited"]["lower"]
            thr = float(np.median(np.concatenate([lg, le])))
            return {"data": {
                "recommended": {"oper": "lower",
                                "threshold_raw": int(thr),
                                "ground_below": False},
                "raw_assignment_fidelity": 0.868,
                "raw_assignment_errors": {"p_e_given_g": 0.082,
                                          "p_g_given_e": 0.182},
                "reset_floor": 0.060,
                "reset_threshold_tuning": {"pi_efficiency": truth.eta}}}

    bench_mod.BenchResetProgram = FakeBenchProgram
    bench_mod.ActiveResetProbe = FakeProbe
    return truth


def fake_proxy():
    return (types.SimpleNamespace(tproc=types.SimpleNamespace()),
            {"readouts": [{"tproc_ch": 0}], "gens": []})


def make_fake_ss(calib=None):
    class FakeSS:
        def __init__(self, **kw):
            self.calib_params = calib or {"threshold": 0.0, "scale_factor": 1,
                                          "read_theta": 0.0,
                                          "ground_threshold": -1.0}
            self.max_F = 0.917

        def acquire(self, **kw):
            return None
    return FakeSS


class NullTee:
    def __enter__(self):
        return "dryrun"

    def __exit__(self, *a):
        return False


def install_runner_common(runner_mod):
    runner_mod.makeProxy = fake_proxy
    if hasattr(runner_mod, "SingleShot1Q"):
        runner_mod.SingleShot1Q = make_fake_ss()
    if hasattr(runner_mod, "tee_log"):
        runner_mod.tee_log = types.SimpleNamespace(tee=lambda *a, **k: NullTee())


def install_dev_arith(runner_mod):
    def fake_read_dmem(soc, addr):
        k, field = divmod(addr - runner_mod.ARITH_BASE_ADDR, 4)
        a, b, c_int, s_int = runner_mod.ARITH_CASES[k]
        wa = runner_mod.wrap32(a * c_int)
        wb = runner_mod.wrap32(b * s_int)
        acc = runner_mod.wrap32(wa + wb)
        return [wa, wb, acc, 0 if acc < 0 else 1][field]

    runner_mod.read_dmem = fake_read_dmem
    runner_mod.ArithProgram = lambda soccfg, cfg: types.SimpleNamespace(
        acquire=lambda *a, **k: None)


def install_t1(t1_mod, rot_mod, truth=None, t1_true_us=150.0):
    truth = truth if truth is not None else TRUTH
    rng = np.random.default_rng(11)

    class FakeFFT1Program:
        def __init__(self, soccfg, cfg):
            self.cfg = cfg

        def acquire(self, soc, load_pulses=True, **kw):
            truth.advance()
            cfg = self.cfg
            n = int(cfg["shots"])
            hold = float(cfg.get("ff_hold", 0.0))
            if cfg.get("rot_reset"):
                c = dict(cfg)
                c.update({"reset_scheme": "rot2",
                          "rot_c_int": cfg["rot_reset"]["c_int"],
                          "rot_s_int": cfg["rot_reset"]["s_int"],
                          "rot_excite_threshold": cfg["rot_reset"]["excite_threshold"],
                          "reset_max_iters": cfg["rot_reset"].get("max_iters", 3)})
                r = reset_output_pop(truth, rot_mod, c, truth.thermal_pop)
            elif str(cfg.get("reset_mode", "passive")) == "feedback":
                c = dict(cfg)
                c["reset_scheme"] = "old"
                r = reset_output_pop(truth, rot_mod, c, truth.thermal_pop)
            else:
                r = truth.thermal_pop
            if cfg.get("do_pi", True):
                p = truth.eta * (1.0 - r) + (1.0 - truth.eta) * r
            else:
                p = r
            p = 0.03 + p * float(np.exp(-hold / t1_true_us))
            p = min(0.97, max(0.01, p))
            exc = rng.random(n) < p
            i1 = np.where(exc, 3.0, -3.0) + rng.normal(0, 1.0, n)
            i0 = np.full(n, -3.0) + rng.normal(0, 1.0, n)
            z = np.zeros(n)
            return i0, z, i1, z

    t1_mod.FFT1Program = FakeFFT1Program
    t1_mod.acquire_with_retry = lambda prog, soc, **kw: prog.acquire(soc, **kw)
    return truth
