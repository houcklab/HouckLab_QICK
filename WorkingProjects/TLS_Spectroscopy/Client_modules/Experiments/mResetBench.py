import contextlib
import gc

import numpy as np
from qick import AveragerProgram
import matplotlib.pyplot as plt

from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import active_reset as ar
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import active_reset_rot as rot
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import ff_pulse
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.pulse_setup import (
    add_qubit_gaussian, set_readout_pulse)
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mActiveResetProbe import (
    ActiveResetProbe)


class BenchResetProgram(AveragerProgram):

    def initialize(self):
        cfg = self.cfg
        cfg.setdefault("reps", int(cfg.get("shots", 2000)))
        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"],
                         mixer_freq=cfg.get("mixer_freq", 0), ro_ch=cfg["ro_chs"][0])
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])
        ff_pulse.declare_static_park(self)
        for ro_ch in cfg["ro_chs"]:
            self.declare_readout(ch=ro_ch, freq=cfg["read_pulse_freq"],
                                 length=self.us2cycles(cfg["read_length"],
                                                       ro_ch=cfg["ro_chs"][0]),
                                 gen_ch=cfg["res_ch"])
        read_freq = self.freq2reg(cfg["read_pulse_freq"], gen_ch=cfg["res_ch"],
                                  ro_ch=cfg["ro_chs"][0])
        qubit_freq = self.freq2reg(cfg.get("qubit_pi_freq", cfg["qubit_freq"]),
                                   gen_ch=cfg["qubit_ch"])
        add_qubit_gaussian(self)
        self.set_pulse_registers(ch=cfg["qubit_ch"], style="arb", freq=qubit_freq,
                                 phase=0, gain=int(cfg["qubit_pi_gain"]),
                                 waveform="qubit")
        set_readout_pulse(self, read_freq)
        self.synci(200)

    def body(self):
        cfg = self.cfg
        ff_pulse.play_static_park(self, settle_us=cfg.get("ff_park_settle_us", 0.05))
        if cfg.get("prep_excited", True):
            self.pulse(ch=cfg["qubit_ch"])
            self.sync_all(self.us2cycles(0.01))
        scheme = str(cfg.get("reset_scheme", "none"))
        if scheme == "old":
            ar.active_reset_block(
                self, ro_ch=cfg["ro_chs"][0], threshold_raw=cfg["reset_threshold_raw"],
                oper=cfg.get("reset_oper", "lower"),
                ground_below=cfg.get("reset_ground_below", True),
                max_iters=int(cfg.get("reset_max_iters", 3)))
        elif scheme in ("rot2", "rot3", "rot3nl"):
            rot.active_reset_rot_block(
                self, ro_ch=cfg["ro_chs"][0],
                c_int=cfg["rot_c_int"], s_int=cfg["rot_s_int"],
                excite_threshold=cfg["rot_excite_threshold"],
                ground_threshold=cfg.get("rot_ground_threshold"),
                latch_sink=cfg.get("rot_latch_sink"),
                max_iters=int(cfg.get("reset_max_iters", 3)),
                three_zone=(scheme in ("rot3", "rot3nl")),
                use_latch=(scheme == "rot3"))
        self.measure(pulse_ch=cfg["res_ch"], adcs=cfg["ro_chs"],
                     adc_trig_offset=self.us2cycles(cfg["adc_trig_offset"]),
                     wait=True,
                     syncdelay=self.us2cycles(cfg.get("relax_delay", 2500.0)))

    def reads_per_rep(self):
        n = int(self.cfg.get("reset_max_iters", 3))
        return (n if str(self.cfg.get("reset_scheme", "none")) != "none" else 0) + 1

    def acquire(self, soc, load_pulses=True, progress=False, **kw):
        reads = self.reads_per_rep()
        super().acquire(soc, readouts_per_experiment=reads,
                        load_pulses=load_pulses, progress=progress)
        self.readouts_per_rep = reads
        return self.final_shots()

    def final_shots(self):
        reads = int(getattr(self, "readouts_per_rep", 1))
        out = []
        for buf in (self.di_buf, self.dq_buf):
            v = np.asarray([ar.to_signed32(x) for x in np.asarray(buf[0]).ravel()],
                           dtype=np.int64)
            n = v.size // reads
            out.append(v[:n * reads].reshape(n, reads)[:, -1])
        return out[0], out[1]


def raw_final_shots(soc, soccfg, cfg, prep_excited, scheme):
    c = dict(cfg)
    c["prep_excited"] = bool(prep_excited)
    c["reset_scheme"] = str(scheme)
    prog = BenchResetProgram(soccfg, c)
    i_final, q_final = prog.acquire(soc, load_pulses=True, progress=False)
    plt.close("all")
    gc.collect()
    return np.asarray(i_final, dtype=np.int64), np.asarray(q_final, dtype=np.int64)


def mean_final_iq(soc, soccfg, cfg, prep_excited, scheme):
    i_final, q_final = raw_final_shots(soc, soccfg, cfg, prep_excited, scheme)
    return float(np.mean(i_final)), float(np.mean(q_final))


def measure_refs(soc, soccfg, cfg):
    ig, qg = mean_final_iq(soc, soccfg, cfg, False, "none")
    ie, qe = mean_final_iq(soc, soccfg, cfg, True, "none")
    return rot.reference_axis(ig, qg, ie, qe)


def measure_residuals(soc, soccfg, cfg, refs):
    out = {}
    for prep in (False, True):
        ir, qr = mean_final_iq(soc, soccfg, cfg, prep,
                               cfg.get("reset_scheme", "none"))
        out["e" if prep else "g"] = rot.population_from_iq(ir, qr, refs)
    return out


def fit_legacy_from_raw(lg, ug, le, ue, iters, eta):
    sep_lower = abs(float(np.median(le)) - float(np.median(lg)))
    sep_upper = abs(float(np.median(ue)) - float(np.median(ug)))
    oper = "lower" if sep_lower >= sep_upper else "upper"
    g = lg if oper == "lower" else ug
    e = le if oper == "lower" else ue
    best = ar.fit_reset_threshold(g, e, iters=int(iters), pi_efficiency=float(eta))
    if best is not None:
        best = dict(best)
        best["oper"] = oper
    return best


def fit_from_raw(lg, ug, le, ue, iters, eta):
    lg = np.asarray(lg, dtype=np.int64)
    ug = np.asarray(ug, dtype=np.int64)
    le = np.asarray(le, dtype=np.int64)
    ue = np.asarray(ue, dtype=np.int64)
    n = min(lg.size, ug.size, le.size, ue.size)
    lg, ug, le, ue = lg[:n], ug[:n], le[:n], ue[:n]
    max_abs = float(np.max(np.abs(np.concatenate([lg, ug, le, ue]))))
    theta = rot.projection_angle(lg, ug, le, ue)
    shift, c_int, s_int = rot.fixed_point_coeffs(theta, max_abs)
    ok, worst = rot.check_headroom(shift, theta, max_abs)
    if not ok:
        raise RuntimeError(f"fixed-point headroom check failed ({worst:.3e})")
    plan = rot.asm_plan(c_int, s_int)
    sink = rot.latch_offset(shift, theta, max_abs,
                            excited_above=plan["excited_above"])
    rep = rot.separation_report(lg, ug, le, ue, c_int=c_int, s_int=s_int, theta=theta)
    eta = float(min(1.0, eta))
    two = rot.choose_thresholds(rep["proj_g"], rep["proj_e"], iters=int(iters),
                                pi_efficiency=eta, three_zone=False)
    three = rot.choose_thresholds(rep["proj_g"], rep["proj_e"], iters=int(iters),
                                  pi_efficiency=eta, three_zone=True)
    old = fit_legacy_from_raw(lg, ug, le, ue, iters, eta)
    return {"theta": theta, "shift": shift, "c_int": c_int, "s_int": s_int,
            "plan": plan, "latch_sink": sink, "max_abs": max_abs,
            "headroom_worst": worst, "report": rep,
            "two": rot.thresholds_to_acc(two, plan),
            "three": rot.thresholds_to_acc(three, plan),
            "two_proj": two, "three_proj": three, "old": old,
            "oper": (old or {}).get("oper",
                                    "lower" if rep["sep_lower"] >= rep["sep_upper"]
                                    else "upper"),
            "n": n, "eta": eta,
            "raw": {"lg": lg, "ug": ug, "le": le, "ue": ue}}


def probe_and_fit(soc, soccfg, cfg, iters, eta_fallback, path="q4", outer_folder="",
                  suffix="ResetBench_Probe"):
    probe = ActiveResetProbe(soc=soc, soccfg=soccfg, path=path,
                             outerFolder=outer_folder, suffix=suffix, cfg=dict(cfg))
    data = probe.acquire().get("data", {})
    plt.close("all")
    gc.collect()
    raw = getattr(probe, "raw_shots", None)
    if not raw or "ground" not in raw or "excited" not in raw:
        print("    probe exposed no raw_shots -- cannot fit the rotation.")
        return None
    eta = (data.get("reset_threshold_tuning") or {}).get("pi_efficiency")
    if eta is None or not np.isfinite(eta) or eta <= 0:
        eta = float(eta_fallback)
    fit = fit_from_raw(raw["ground"]["lower"], raw["ground"]["upper"],
                       raw["excited"]["lower"], raw["excited"]["upper"],
                       iters, eta)
    fit.update({"probe_floor": data.get("reset_floor"),
                "probe_errors": data.get("raw_assignment_errors", {}),
                "probe_raw_F": data.get("raw_assignment_fidelity"),
                "probe_recommended": data.get("recommended")})
    return fit


def print_fit(fit):
    rep = fit["report"]
    plan = fit["plan"]
    print(f"  theta = {np.rad2deg(fit['theta']):+7.2f} deg | 2^{fit['shift']} -> "
          f"C={fit['c_int']}, S={fit['s_int']} | headroom "
          f"{fit['headroom_worst']:.2e} / {rot.INT32_MAX:.2e}")
    print(f"  asm plan: acc = {plan['c_abs']}*I {plan['combine_op']} "
          f"{plan['s_abs']}*Q   (multiply immediates are non-negative by "
          f"construction; excited_above={plan['excited_above']}, "
          f"latch sink {fit['latch_sink']})")
    print(f"  separation:  lower {rep['sep_lower']:8.0f}   upper {rep['sep_upper']:8.0f}"
          f"   best single {rep['sep_best_single']:8.0f}   rotated "
          f"{rep['sep_rotated']:8.0f}   gain {rep['gain_vs_best_single']:.2f}x")


def arm_cfg(cfg, scheme, fit, legacy=None):
    out = dict(cfg)
    out["reset_scheme"] = str(scheme)
    if scheme == "none":
        return out
    if scheme == "old":
        rec = legacy if legacy is not None else fit["old"]
        if rec is None:
            raise RuntimeError("no legacy threshold fit available for the 'old' arm")
        out.update({"reset_threshold_raw": int(rec["threshold_raw"]),
                    "reset_oper": str(rec.get("oper", fit["oper"])),
                    "reset_ground_below": bool(rec["ground_below"])})
        return out
    thr = fit["three"] if scheme in ("rot3", "rot3nl") else fit["two"]
    out.update({"rot_c_int": fit["c_int"], "rot_s_int": fit["s_int"],
                "rot_excite_threshold": thr["excite_threshold"],
                "rot_ground_threshold": thr.get("ground_threshold"),
                "rot_latch_sink": fit["latch_sink"]})
    return out


def rot_reset_params(fit, max_iters):
    return {"c_int": int(fit["c_int"]), "s_int": int(fit["s_int"]),
            "excite_threshold": float(fit["two"]["excite_threshold"]),
            "max_iters": int(max_iters)}


def _dispatching_reset_block(original):
    def dispatch(prog, **kw):
        params = None
        try:
            params = prog.cfg.get("rot_reset")
        except Exception:
            params = None
        if not params:
            return original(prog, **kw)
        return rot.active_reset_rot_block(
            prog, ro_ch=kw.get("ro_ch", 0),
            c_int=params["c_int"], s_int=params["s_int"],
            excite_threshold=params["excite_threshold"],
            max_iters=int(params.get("max_iters", kw.get("max_iters", 3))),
            three_zone=False, use_latch=False)
    return dispatch


@contextlib.contextmanager
def patched_production_reset():
    original = ar.active_reset_block
    ar.active_reset_block = _dispatching_reset_block(original)
    try:
        yield
    finally:
        ar.active_reset_block = original
