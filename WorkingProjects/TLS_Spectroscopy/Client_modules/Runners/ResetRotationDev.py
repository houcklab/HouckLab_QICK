"""Development bench for the in-tProc rotated / three-zone active reset.

The current reset (Helpers/active_reset.py) is untouched and remains the
production path.  This develops its replacement (Helpers/active_reset_rot.py),
which computes  proj = cos(t)*I + sin(t)*Q  in fixed point on the tProc instead
of thresholding one raw quadrature.

Stated honestly up front: on a well-aligned readout the two schemes are predicted
to perform IDENTICALLY.  The rotated one wins only when the blobs are NOT aligned
to a quadrature -- the state this setup was in earlier today (separation 9992 vs
9968) and the state it drifts back toward.  This is a robustness change, not a
peak-performance change, and stage 4 is what actually tests that claim.

  0  does tProc v1 arithmetic do what we think?  This is the one thing that
     cannot be checked off-hardware, and everything else depends on it.
  1  fit theta from raw 2-D shots; predict the gain over the best quadrature.
  2  run the new block; measure residuals from |g> and |e>.
  3  head-to-head vs the current reset, interleaved so drift cannot fake a winner.
  4  mis-set res_phase on purpose and watch the two schemes diverge.
"""
import datetime
import gc
import time

import numpy as np
from qick import AveragerProgram
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.socProxy import makeProxy
from WorkingProjects.TLS_Spectroscopy.Client_modules.Calib.initialize import BaseConfig, outerFolder
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mSingleShot1Q import SingleShot1Q
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mActiveResetProbe import (
    ActiveResetProbe)
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import active_reset as ar
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import active_reset_rot as rot
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import ff_pulse
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import tee_log
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.pulse_setup import (
    add_qubit_gaussian, set_readout_pulse)

QUBIT = "q4"

SHOTS = 4000
SS_SHOTS = 1000
SS_GROUND_THRESHOLD = 0.7
RESET_MAX_ITERS = 3
THERMALIZATION_US = 2.0
PI_EFFICIENCY_GUESS = 0.58
RELAX_US = 2500.0

AB_REPEATS = 4
PHASE_OFFSETS_DEG = [0.0, 20.0, 45.0, 70.0]

RUN_STAGE_0 = True
RUN_STAGE_1 = True
RUN_STAGE_2 = True
RUN_STAGE_3 = True
RUN_STAGE_4 = True

ARITH_BASE_ADDR = 200
ARITH_REGS = {"a": 1, "b": 2, "acc": 3, "flag": 4}
ARITH_CASES = [
    (1, 1, 1, 1),
    (12345, -6789, 4096, 4096),
    (-18944, 791, 4096, -4096),
    (20000, 20000, 4096, 4096),
    (-20000, -20000, 4096, 4096),
    (32767, -32768, 8192, 8192),
    (0, 20000, 0, 4096),
]


def banner(text):
    print()
    print("=" * 96)
    print(text)
    print("=" * 96)


def base_cfg(**extra):
    cfg = dict(BaseConfig)
    cfg["shots"] = cfg["reps"] = int(SHOTS)
    cfg["reset_max_iters"] = int(RESET_MAX_ITERS)
    cfg["reset_thermalization_us"] = THERMALIZATION_US
    cfg["relax_delay"] = RELAX_US
    cfg.update(extra)
    return cfg


class ArithProgram(AveragerProgram):
    """Deterministic ALU check: regwi known values, apply the projection, memwi it.

    Uses constants rather than live ADC values so the expected answer is known
    exactly and the edge cases (large immediates, negative operands, the latch
    sink) are covered on purpose rather than by luck.
    """

    def initialize(self):
        cfg = self.cfg
        cfg.setdefault("reps", 1)
        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"],
                         mixer_freq=cfg.get("mixer_freq", 0), ro_ch=cfg["ro_chs"][0])
        for ro_ch in cfg["ro_chs"]:
            self.declare_readout(ch=ro_ch, freq=cfg["read_pulse_freq"],
                                 length=self.us2cycles(cfg["read_length"],
                                                       ro_ch=cfg["ro_chs"][0]),
                                 gen_ch=cfg["res_ch"])
        set_readout_pulse(self, self.freq2reg(cfg["read_pulse_freq"],
                                              gen_ch=cfg["res_ch"],
                                              ro_ch=cfg["ro_chs"][0]))
        self.synci(200)

    def body(self):
        cfg = self.cfg
        page = self.ch_page(cfg["res_ch"])
        r = ARITH_REGS
        for k, (a, b, c_int, s_int) in enumerate(ARITH_CASES):
            addr = ARITH_BASE_ADDR + 4 * k
            self.regwi(page, r["a"], int(a))
            self.regwi(page, r["b"], int(b))
            self.mathi(page, r["a"], r["a"], '*', int(c_int))
            self.mathi(page, r["b"], r["b"], '*', int(s_int))
            self.math(page, r["acc"], r["a"], '+', r["b"])
            self.memwi(page, r["a"], addr)
            self.memwi(page, r["b"], addr + 1)
            self.memwi(page, r["acc"], addr + 2)
            self.regwi(page, r["flag"], 0)
            self.regwi(page, r["a"], 0)
            self.condj(page, r["acc"], '<', r["a"], f"ARITH_NEG_{k}")
            self.regwi(page, r["flag"], 1)
            self.label(f"ARITH_NEG_{k}")
            self.memwi(page, r["flag"], addr + 3)
        self.measure(pulse_ch=cfg["res_ch"], adcs=cfg["ro_chs"],
                     adc_trig_offset=self.us2cycles(cfg["adc_trig_offset"]),
                     wait=True, syncdelay=self.us2cycles(1.0))


class RotResetProgram(AveragerProgram):
    """Prepare |g> or |e>, optionally reset with one of the two schemes, read out."""

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
        elif scheme in ("rot2", "rot3"):
            rot.active_reset_rot_block(
                self, ro_ch=cfg["ro_chs"][0],
                c_int=cfg["rot_c_int"], s_int=cfg["rot_s_int"],
                excite_threshold=cfg["rot_excite_threshold"],
                ground_threshold=cfg.get("rot_ground_threshold"),
                latch_sink=cfg.get("rot_latch_sink"),
                max_iters=int(cfg.get("reset_max_iters", 3)),
                three_zone=(scheme == "rot3"), use_latch=(scheme == "rot3"))
        self.measure(pulse_ch=cfg["res_ch"], adcs=cfg["ro_chs"],
                     adc_trig_offset=self.us2cycles(cfg["adc_trig_offset"]),
                     wait=True,
                     syncdelay=self.us2cycles(cfg.get("relax_delay", RELAX_US)))

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


def read_dmem(soc, addr):
    for getter in (lambda: soc.tproc.single_read(addr),
                   lambda: soc.tproc.read_dmem(addr, 1)[0],
                   lambda: soc.read_dmem(addr, 1)[0]):
        try:
            return ar.to_signed32(getter())
        except Exception:
            continue
    raise RuntimeError("could not read tProc data memory via the soc proxy")


def wrap32(x):
    return int(np.int32(np.int64(x) & 0xFFFFFFFF))


def stage0(soc, soccfg):
    banner("STAGE 0 -- does tProc v1 actually do the arithmetic?")
    print("  Everything downstream assumes  mathi(reg,'*',C)  with C ~ 2^12 and")
    print("  math(reg,'+',reg).  Elsewhere in this repo mathi '*' is only ever used")
    print("  with -1 or +2, so a wide multiply is genuinely unverified here.  This")
    print("  stage writes known constants into registers, applies exactly the")
    print("  projection the reset will use, and reads every intermediate back out")
    print("  of tProc memory.  If any row disagrees, the design is dead and nothing")
    print("  below it means anything.")
    prog = ArithProgram(soccfg, base_cfg(reps=1, shots=1))
    prog.acquire(soc, load_pulses=True, progress=False)
    print(f"\n  {'a':>8} {'b':>8} {'C':>6} {'S':>7} | {'C*a want':>12} {'got':>12} "
          f"{'S*b want':>12} {'got':>12} {'sum want':>12} {'got':>12} {'neg':>4}")
    bad = 0
    for k, (a, b, c_int, s_int) in enumerate(ARITH_CASES):
        addr = ARITH_BASE_ADDR + 4 * k
        got_a, got_b = read_dmem(soc, addr), read_dmem(soc, addr + 1)
        got_acc, got_flag = read_dmem(soc, addr + 2), read_dmem(soc, addr + 3)
        want_a, want_b = wrap32(a * c_int), wrap32(b * s_int)
        want_acc = wrap32(want_a + want_b)
        want_flag = 0 if want_acc < 0 else 1
        ok = (got_a == want_a and got_b == want_b and got_acc == want_acc
              and got_flag == want_flag)
        bad += not ok
        print(f"  {a:8d} {b:8d} {c_int:6d} {s_int:7d} | {want_a:12d} {got_a:12d} "
              f"{want_b:12d} {got_b:12d} {want_acc:12d} {got_acc:12d} "
              f"{got_flag:4d}  {'' if ok else '<-- MISMATCH'}")
    if bad:
        print(f"\n  {bad}/{len(ARITH_CASES)} cases WRONG.  tProc v1 on this firmware does")
        print("  not compute what the rotated reset needs.  Stop here -- the remaining")
        print("  stages would be measuring nonsense.")
        return False
    print(f"\n  all {len(ARITH_CASES)} cases exact, including the condj sign test.")
    print("  The fixed-point projection and the latch comparison are implementable.")
    return True


def fit_rotation(soc, soccfg, tag, verbose=True):
    probe = ActiveResetProbe(soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outerFolder,
                             suffix=f"RotDev_{tag}", cfg=base_cfg())
    data = probe.acquire().get("data", {})
    plt.close("all")
    gc.collect()
    raw = getattr(probe, "raw_shots", None)
    if not raw or "ground" not in raw or "excited" not in raw:
        print("    probe exposed no raw_shots attribute -- cannot fit the rotation.")
        return None
    lg = np.asarray(raw["ground"]["lower"], dtype=np.int64)
    ug = np.asarray(raw["ground"]["upper"], dtype=np.int64)
    le = np.asarray(raw["excited"]["lower"], dtype=np.int64)
    ue = np.asarray(raw["excited"]["upper"], dtype=np.int64)
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
    eta = data.get("pi_efficiency")
    if eta is None or not np.isfinite(eta) or eta <= 0:
        eta = PI_EFFICIENCY_GUESS
    eta = float(min(1.0, eta))
    two = rot.choose_thresholds(rep["proj_g"], rep["proj_e"], iters=RESET_MAX_ITERS,
                                pi_efficiency=eta, three_zone=False)
    three = rot.choose_thresholds(rep["proj_g"], rep["proj_e"], iters=RESET_MAX_ITERS,
                                  pi_efficiency=eta, three_zone=True)
    old = ar.fit_reset_threshold(
        lg if rep["sep_lower"] >= rep["sep_upper"] else ug,
        le if rep["sep_lower"] >= rep["sep_upper"] else ue,
        iters=RESET_MAX_ITERS, pi_efficiency=eta)
    out = {"theta": theta, "shift": shift, "c_int": c_int, "s_int": s_int,
           "plan": plan, "latch_sink": sink, "max_abs": max_abs, "report": rep,
           "two": rot.thresholds_to_acc(two, plan),
           "three": rot.thresholds_to_acc(three, plan),
           "two_proj": two, "three_proj": three, "old": old,
           "oper": "lower" if rep["sep_lower"] >= rep["sep_upper"] else "upper",
           "n": n,
           "probe_floor": data.get("reset_floor"),
           "probe_errors": data.get("raw_assignment_errors", {}),
           "probe_raw_F": data.get("raw_assignment_fidelity"),
           "probe_recommended": data.get("recommended"), "eta": eta}
    if verbose:
        print(f"  theta = {np.rad2deg(theta):+7.2f} deg | 2^{shift} -> C={c_int}, S={s_int}"
              f" | headroom {worst:.2e} / {rot.INT32_MAX:.2e}")
        print(f"  asm plan: acc = {plan['c_abs']}*I {plan['combine_op']} "
              f"{plan['s_abs']}*Q   (multiply immediates are non-negative by "
              f"construction; excited_above={plan['excited_above']}, latch sink {sink})")
        print(f"  separation:  lower {rep['sep_lower']:8.0f}   upper {rep['sep_upper']:8.0f}"
              f"   best single {rep['sep_best_single']:8.0f}   rotated {rep['sep_rotated']:8.0f}"
              f"   gain {rep['gain_vs_best_single']:.2f}x")
    return out


def measure_residual(soc, soccfg, cfg, calib_params, label):
    prepared = {}
    for prep in (False, True):
        c = dict(cfg)
        c["prep_excited"] = bool(prep)
        prog = RotResetProgram(soccfg, c)
        i_final, q_final = prog.acquire(soc, load_pulses=True, progress=False)
        from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mSingleShot1Q import (
            discriminate_shots)
        assign = np.asarray(discriminate_shots(i_final, q_final, calib_params))
        prepared["e" if prep else "g"] = float(np.mean(assign == 1))
        plt.close("all")
        gc.collect()
    return prepared


def stage2(soc, soccfg, fit, calib_params, rec):
    banner("STAGE 2 -- run the new block end to end")
    if fit is None:
        print("  no rotation fit -- skipping.")
        return None
    results = {}
    arms = [("old", {}), ("rot2", {}), ("rot3", {})]
    for scheme, _ in arms:
        cfg = base_cfg(reset_scheme=scheme)
        if scheme == "old":
            if rec is None:
                print("  current reset has no recommendation this session -- skipping 'old'.")
                continue
            cfg.update({"reset_threshold_raw": int(rec["threshold_raw"]),
                        "reset_oper": str(fit["oper"]),
                        "reset_ground_below": bool(rec["ground_below"])})
        else:
            thr = fit["three"] if scheme == "rot3" else fit["two"]
            cfg.update({"rot_c_int": fit["c_int"], "rot_s_int": fit["s_int"],
                        "rot_excite_threshold": thr["excite_threshold"],
                        "rot_ground_threshold": thr.get("ground_threshold"),
                        "rot_latch_sink": fit["latch_sink"]})
        t0 = time.time()
        res = measure_residual(soc, soccfg, cfg, calib_params, scheme)
        results[scheme] = res
        print(f"  {scheme:5s}: residual from |g> {res['g']:.4f}   from |e> {res['e']:.4f}"
              f"   worst {max(res.values()):.4f}   ({time.time() - t0:.0f} s)")
    return results


def stage3(soc, soccfg, fit, calib_params, rec):
    banner("STAGE 3 -- head to head, interleaved")
    print(f"  {AB_REPEATS} interleaved repeats.  Running the arms back to back in a fixed")
    print("  order would let slow drift masquerade as a winner, which is exactly how")
    print("  the earlier interleave_rounds A/B produced three different verdicts.")
    if fit is None or rec is None:
        print("  missing a fit or a recommendation -- skipping.")
        return None
    arms = ["old", "rot2", "rot3"]
    acc = {a: {"g": [], "e": []} for a in arms}
    for rep in range(int(AB_REPEATS)):
        for scheme in arms:
            cfg = base_cfg(reset_scheme=scheme)
            if scheme == "old":
                cfg.update({"reset_threshold_raw": int(rec["threshold_raw"]),
                            "reset_oper": str(fit["oper"]),
                            "reset_ground_below": bool(rec["ground_below"])})
            else:
                thr = fit["three"] if scheme == "rot3" else fit["two"]
                cfg.update({"rot_c_int": fit["c_int"], "rot_s_int": fit["s_int"],
                            "rot_excite_threshold": thr["excite_threshold"],
                            "rot_ground_threshold": thr.get("ground_threshold"),
                            "rot_latch_sink": fit["latch_sink"]})
            res = measure_residual(soc, soccfg, cfg, calib_params, scheme)
            acc[scheme]["g"].append(res["g"])
            acc[scheme]["e"].append(res["e"])
        print(f"    repeat {rep + 1}/{AB_REPEATS} done")
    print(f"\n  {'arm':>6} {'from|g>':>18} {'from|e>':>18} {'worst':>8}")
    summary = {}
    for scheme in arms:
        g = np.asarray(acc[scheme]["g"])
        e = np.asarray(acc[scheme]["e"])
        summary[scheme] = {"g": g, "e": e}
        print(f"  {scheme:>6} {g.mean():8.4f} +/- {g.std(ddof=1) / np.sqrt(g.size):.4f}"
              f"   {e.mean():8.4f} +/- {e.std(ddof=1) / np.sqrt(e.size):.4f}"
              f" {max(g.mean(), e.mean()):8.4f}")
    for a, b in (("old", "rot2"), ("rot2", "rot3"), ("old", "rot3")):
        if a not in summary or b not in summary:
            continue
        d = summary[a]["e"] - summary[b]["e"]
        sig = d.mean() / (d.std(ddof=1) / np.sqrt(d.size)) if d.std(ddof=1) > 0 else np.nan
        print(f"  {a} - {b} on the |e> branch: {d.mean():+.4f} ({sig:+.1f} sigma paired)")
    return summary


def stage4(soc, soccfg, calib_params):
    banner("STAGE 4 -- the actual claim: immunity to readout phase")
    print("  Offset res_phase on purpose and refit both schemes at each offset.  The")
    print("  rotated reset should be flat; the single-quadrature reset should degrade")
    print("  and be worst near 45 deg, where the separation splits evenly across the")
    print("  two accumulator halves.  This is the failure mode seen this morning.")
    base_phase = float(BaseConfig.get("res_phase", 0.0))
    print(f"  base res_phase = {base_phase:g} deg")
    rows = []
    for d in PHASE_OFFSETS_DEG:
        BaseConfig["res_phase"] = base_phase + float(d)
        print(f"\n  --- res_phase offset {d:+.0f} deg (absolute {BaseConfig['res_phase']:g}) ---")
        try:
            fit = fit_rotation(soc, soccfg, f"Phase{int(d)}")
        except Exception as exc:
            print(f"    fit failed: {type(exc).__name__}: {exc}")
            continue
        if fit is None:
            print("    probe returned no raw shots -- skipping.")
            continue
        old_pred = fit["old"]["predicted_worst"] if fit["old"] else np.nan
        rows.append({"offset": d, "gain": fit["report"]["gain_vs_best_single"],
                     "sep_single": fit["report"]["sep_best_single"],
                     "sep_rot": fit["report"]["sep_rotated"],
                     "old_pred": old_pred,
                     "new_pred": fit["three_proj"]["predicted_worst"],
                     "probe_floor": fit.get("probe_floor"),
                     "probe_F": fit.get("probe_raw_F")})
    BaseConfig["res_phase"] = base_phase
    print(f"\n  restored res_phase = {BaseConfig['res_phase']:g} deg")
    if rows:
        print(f"\n  {'offset':>7} {'sep single':>11} {'sep rot':>9} {'gain':>6} "
              f"{'raw F':>7} {'floor':>7} {'OLD pred':>9} {'NEW pred':>9} {'improve':>8}")
        for r in rows:
            imp = r["old_pred"] / r["new_pred"] if r["new_pred"] > 0 else np.nan
            pf = r.get("probe_F")
            fl = r.get("probe_floor")
            print(f"  {r['offset']:+6.0f}d {r['sep_single']:11.0f} {r['sep_rot']:9.0f} "
                  f"{r['gain']:5.2f}x {(pf if pf is not None else np.nan):7.3f} "
                  f"{(fl if fl is not None else np.nan):7.3f} "
                  f"{r['old_pred']:9.4f} {r['new_pred']:9.4f} {imp:7.2f}x")
        print("\n  'raw F' and 'floor' are the CURRENT scheme measured by the probe at")
        print("  each phase -- independent of any model.  If they dip where sep single")
        print("  dips, the degradation is real and not an artefact of the fit.")
        new = np.asarray([r["new_pred"] for r in rows])
        old = np.asarray([r["old_pred"] for r in rows])
        print(f"\n  rotated spread across phase: {np.nanmax(new) - np.nanmin(new):.4f} "
              f"(should be ~0)")
        print(f"  single spread across phase:  {np.nanmax(old) - np.nanmin(old):.4f} "
              f"(should be large)")
        if np.nanmax(new) - np.nanmin(new) < 0.5 * (np.nanmax(old) - np.nanmin(old)):
            print("  -> the rotated reset is measurably less sensitive to readout phase.")
        else:
            print("  -> NO measurable immunity.  Either the phase offsets did not move the")
            print("     blobs as expected, or the fit is picking up something else.  Check")
            print("     the separation columns before believing either scheme.")
    return rows


def main():
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    with tee_log.tee(f"ResetRotationDev_{stamp}", outerFolder):
        soc, soccfg = makeProxy()
        banner("ROTATED / THREE-ZONE ACTIVE RESET -- DEVELOPMENT BENCH")
        print(__doc__.strip())

        if RUN_STAGE_0 and not stage0(soc, soccfg):
            return

        c = dict(BaseConfig)
        c["shots"] = c["reps"] = SS_SHOTS
        ss = SingleShot1Q(soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outerFolder,
                          suffix="RotDev_SS", cfg=c, repeats=1,
                          confidence_threshold=SS_GROUND_THRESHOLD)
        ss.acquire(progress=False, plotDisp=False)
        calib_params = ss.calib_params
        print(f"\n  single-shot readout F = {ss.max_F:.4f}")
        plt.close("all")
        gc.collect()

        fit, rec = None, None
        if RUN_STAGE_1:
            banner("STAGE 1 -- fit the rotation from raw 2-D shots")
            print("  The existing probe already records both accumulator halves per shot")
            print("  for prepared |g> and |e>.  That is exactly what the rotation needs,")
            print("  so this is a different analysis of data we already take.")
            fit = fit_rotation(soc, soccfg, "Fit")
            if fit is not None:
                rec = fit["old"]
                two, three = fit["two_proj"], fit["three_proj"]
                print(f"\n  predicted worst residual, {RESET_MAX_ITERS} iters, "
                      f"eta={fit['eta']:.2f} (measured by the probe, not assumed):")
                if fit["old"]:
                    print(f"    current (1 quadrature)  {fit['old']['predicted_worst']:.4f}"
                          f"   threshold {fit['old']['threshold_raw']} on '{fit['oper']}'")
                print(f"    rotated 2-zone          {two['predicted_worst']:.4f}")
                print(f"    rotated 3-zone          {three['predicted_worst']:.4f}"
                      f"   latch P(g)={three['p_latch_given_g']:.3f} "
                      f"P(e)={three['p_latch_given_e']:.3f}")
                if fit["report"]["gain_vs_best_single"] < 1.05:
                    print("\n  -> blobs already aligned to a quadrature: the rotation buys")
                    print("     nothing TODAY.  Expected on a freshly phased readout, and")
                    print("     not a failure -- stage 4 is where the difference appears.")
                print("\n  The worst case is set by the |e> branch, which the latch cannot")
                print("  help, so expect the 3-zone gain to be a few percent.  A large")
                print("  measured gain is a reason to distrust the measurement.")

        if RUN_STAGE_2:
            stage2(soc, soccfg, fit, calib_params, rec)
        if RUN_STAGE_3:
            stage3(soc, soccfg, fit, calib_params, rec)
        if RUN_STAGE_4:
            stage4(soc, soccfg, calib_params)

        banner("done -- send back the .txt log")


if __name__ == "__main__":
    main()
