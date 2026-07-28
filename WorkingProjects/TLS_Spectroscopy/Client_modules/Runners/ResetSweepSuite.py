import time

import numpy as np

from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.socProxy import makeProxy
from WorkingProjects.TLS_Spectroscopy.Client_modules.Calib.initialize import BaseConfig, outerFolder
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mActiveResetProbe import (
    ReadProbeProgram, ResetCheckProgram,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import active_reset as ar
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import tee_log
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.pulse_setup import (
    readout_drive_length_us,
)

QUBIT = "q4"

RUN_ITERS = True
RUN_READ_GAIN = True
RUN_READ_LENGTH = True
RUN_PI = True
RUN_READ_DELAY = True

ITERS_LIST = [1, 2, 3, 4, 6, 8, 12, 16]
READ_GAIN_FRACTIONS = [0.25, 0.4, 0.6, 0.8, 1.0, 1.3]
READ_LENGTH_US = [1.0, 2.0, 4.0, 8.0, 15.0]
PI_GAIN_FRACTIONS = [0.85, 0.925, 1.0, 1.075, 1.15]
PI_DETUNE_MHZ = [-1.5, -0.75, 0.0, 0.75, 1.5]
READ_DELAY_US = [0.5, 1.0, 2.0, 3.0, 5.0]

ROUNDS = 8
REF_SHOTS = 4000
GATE_SHOTS = 1000
TIMING_SHOTS_LO = 200
TIMING_REPEATS = 3
REF_RELAX_US = 2000.0
GATE_RELAX_US = 25.0

BASE_ITERS = 3
BASE_SYNCDELAY_US = 4.0
BASE_CLEAR_US = 2.0
BASE_READ_DELAY_US = 2.0

TS_US = 60.0
SWEEP_POINTS = 335
SHOTS_PER_POINT = 500
INTERLEAVE_ROUNDS = 10
REF_F_BASELINE = [0.89]


def banner(text):
    print()
    print("=" * 100)
    print(text)
    print("=" * 100)


def stat(v):
    v = np.asarray([x for x in v if np.isfinite(x)], dtype=float)
    if v.size == 0:
        return np.nan, np.nan
    return float(np.mean(v)), float(np.std(v) / max(1.0, np.sqrt(v.size - 1)))


def reference(soc, soccfg, cfg, shots, read_gain=None, read_length=None):
    out = {}
    for label, gain in (("g", 0), ("e", int(cfg["qubit_pi_gain"]))):
        c = dict(cfg)
        c["probe_gain"] = int(gain)
        c["reps"] = c["shots"] = int(shots)
        c["relax_delay"] = REF_RELAX_US
        if read_gain is not None:
            c["read_pulse_gain"] = int(read_gain)
        if read_length is not None:
            c["read_length"] = float(read_length)
            c.pop("read_pulse_length", None)
        prog = ReadProbeProgram(soccfg, c)
        prog.acquire(soc, load_pulses=True, progress=False)
        out[label] = {
            "lower": np.asarray([ar.to_signed32(v) for v in
                                 np.asarray(prog.di_buf[0]).ravel()], dtype=np.int64),
            "upper": np.asarray([ar.to_signed32(v) for v in
                                 np.asarray(prog.dq_buf[0]).ravel()], dtype=np.int64),
        }
    lo = abs(np.median(out["e"]["lower"]) - np.median(out["g"]["lower"]))
    up = abs(np.median(out["e"]["upper"]) - np.median(out["g"]["upper"]))
    oper = "lower" if lo >= up else "upper"
    disc = ar.fit_assignment_threshold(out["g"][oper][::2], out["e"][oper][::2])
    tuned = ar.fit_reset_threshold(out["g"][oper][1::2], out["e"][oper][1::2],
                                   iters=BASE_ITERS,
                                   pi_efficiency=ar.DEFAULT_PI_EFFICIENCY)
    return {"shots": out, "oper": oper, "sep": max(lo, up), "F": disc["fidelity"],
            "thr": int(disc["threshold_raw"]), "gb": bool(disc["ground_below"]),
            "peg": disc["p_e_given_g"], "pge": disc["p_g_given_e"],
            "tuned_thr": int(tuned["threshold_raw"]) if tuned else
            int(disc["threshold_raw"]),
            "floor": ar.reset_floor(disc["p_e_given_g"], disc["p_g_given_e"])}


def build(cfg, ref, prep, do_reset, iters, **kw):
    c = dict(cfg)
    c["prep_excited"] = bool(prep)
    c["do_reset"] = bool(do_reset)
    c["reset_threshold_raw"] = int(kw.pop("threshold", ref["tuned_thr"]))
    c["reset_ground_below"] = bool(ref["gb"])
    c["reset_oper"] = str(ref["oper"])
    c["reset_max_iters"] = int(iters)
    c["reset_meas_syncdelay_us"] = float(kw.pop("syncdelay_us", BASE_SYNCDELAY_US))
    c["reset_thermalization_us"] = float(kw.pop("clear_us", BASE_CLEAR_US))
    c["reset_read_delay_us"] = float(kw.pop("read_delay_us", BASE_READ_DELAY_US))
    c["relax_delay"] = GATE_RELAX_US
    for key, val in kw.items():
        if val is not None:
            c[key] = val
    return c


def run_pe(soc, soccfg, c, ref, shots=None, timed=False):
    c = dict(c)
    c["reps"] = c["shots"] = int(GATE_SHOTS if shots is None else shots)
    t0 = time.time()
    prog = ResetCheckProgram(soccfg, c)
    prog.acquire(soc, load_pulses=True)
    dt = time.time() - t0
    lo, up = prog.shots()
    if lo is None:
        return (np.nan, dt) if timed else np.nan
    v = (lo if ref["oper"] == "lower" else up)[:, -1].astype(float)
    thr, gb = ref["thr"], ref["gb"]
    pe = float(np.mean(v >= thr)) if gb else float(np.mean(v <= thr))
    return (pe, dt) if timed else pe


def timing(soc, soccfg, c, ref, repeats=TIMING_REPEATS):
    n = GATE_SHOTS - TIMING_SHOTS_LO
    if n <= 0:
        return np.nan, np.nan
    slopes, overheads = [], []
    for _ in range(int(repeats)):
        _, t_hi = run_pe(soc, soccfg, c, ref, shots=GATE_SHOTS, timed=True)
        _, t_lo = run_pe(soc, soccfg, c, ref, shots=TIMING_SHOTS_LO, timed=True)
        sl = (t_hi - t_lo) / n
        slopes.append(sl * 1e6)
        overheads.append(t_lo - TIMING_SHOTS_LO * sl)
    return float(max(np.median(slopes), 0.0)), float(max(np.median(overheads), 0.0))


def per_shot_us(soc, soccfg, c, ref, repeats=TIMING_REPEATS):
    return timing(soc, soccfg, c, ref, repeats)[0]


OVERHEAD_S = [0.0]


def sweep_time_min(us_shot, overhead_s=None, rounds=None):
    oh = OVERHEAD_S[0] if overhead_s is None else overhead_s
    r = int(INTERLEAVE_ROUNDS if rounds is None else rounds)
    per_program = oh + (SHOTS_PER_POINT / r) * us_shot * 1e-6
    return per_program * 3 * SWEEP_POINTS * r / 60.0


def contrast(F, r):
    return max((2.0 * float(F) - 1.0) * (1.0 - 2.0 * float(r)), 1e-6)


def effective_min(us_shot, F, r, overhead_s=None, rounds=None):
    ref_c = contrast(REF_F_BASELINE[0], 0.0)
    return sweep_time_min(us_shot, overhead_s, rounds) * (ref_c / contrast(F, r)) ** 2


def worst_residual(soc, soccfg, cfg, ref, iters, rounds=None, **kw):
    g, e = [], []
    for _ in range(int(rounds or ROUNDS)):
        g.append(run_pe(soc, soccfg, build(cfg, ref, False, True, iters, **kw), ref))
        e.append(run_pe(soc, soccfg, build(cfg, ref, True, True, iters, **kw), ref))
    gm, ge = stat(g)
    em, ee = stat(e)
    return gm, ge, em, ee, max(abs(gm), abs(em))


def run():
    soc, soccfg = makeProxy()
    cfg = dict(BaseConfig)
    cfg["qubit_gain"] = int(cfg["qubit_pi_gain"])
    cfg["reset_mode"] = "feedback"
    cfg["tproc_ch"] = ar.feedback_channel(soccfg, cfg["ro_chs"][0])
    nominal_gain = int(cfg["read_pulse_gain"])
    nominal_len = float(cfg["read_length"])
    pi_gain0 = int(cfg["qubit_pi_gain"])
    pi_freq0 = float(cfg.get("qubit_pi_freq", cfg["qubit_freq"]))

    banner("RESET SWEEP SUITE")
    print("  The objective is NOT the smallest residual.  In the 3-point estimator")
    print("  pe = (Ps-P0)/(P1-P0) with flux-matched references, a residual that is the")
    print("  same across the triplet CANCELS.  The reset exists to buy wall clock: it")
    print(f"  lets the inter-shot relax be {GATE_RELAX_US:g} us instead of ~2000 us.")
    print("  So the figure of merit is MICROSECONDS PER SHOT, subject to the loop")
    print("  actually converging to its floor.  Every stage below reports both.")
    print()
    print(f"  a {SWEEP_POINTS}-point 3-point sweep at {SHOTS_PER_POINT} shots/point is")
    print(f"  {SWEEP_POINTS * 3 * SHOTS_PER_POINT} shots per pass, so 1 us/shot saved is")
    print(f"  {SWEEP_POINTS * 3 * SHOTS_PER_POINT / 1e6 / 60:.2f} min/pass.")

    ref = reference(soc, soccfg, cfg, REF_SHOTS)
    us0, oh0 = timing(soc, soccfg, build(cfg, ref, True, True, BASE_ITERS), ref)
    OVERHEAD_S[0] = oh0
    print(f"\n  TIMING MODEL, measured: t(N shots) = overhead + N x t_shot")
    print(f"    per-program overhead {oh0 * 1e3:.0f} ms   (host + Pyro + compile)")
    print(f"    per-shot sequence    {us0:.1f} us")
    print(f"    at {SHOTS_PER_POINT} shots/point that is "
          f"{oh0 * 1e3 + us0 * SHOTS_PER_POINT * 1e-3:.0f} ms/program, "
          f"{sweep_time_min(us0):.1f} min per {SWEEP_POINTS}-point pass")
    frac = us0 * SHOTS_PER_POINT * 1e-6 / max(oh0 + us0 * SHOTS_PER_POINT * 1e-6, 1e-9)
    print(f"    the pulse sequence is {100 * frac:.0f}% of the wall clock")
    if frac < 0.4:
        print(f"    -> OVERHEAD DOMINATES.  Shaving microseconds off the reset can win at")
        print(f"       most {100 * frac:.0f}% of the runtime.  The bigger levers are fewer")
        print(f"       programs (more shots per program) or fewer points.")
    print(f"\n  readout: '{ref['oper']}', separation {ref['sep']:.0f}, F={ref['F']:.3f}")
    print(f"  P(e|g)={ref['peg']:.3f} P(g|e)={ref['pge']:.3f} -> floor {ref['floor']:.3f}")
    print(f"  F-optimal threshold {ref['thr']}, reset-tuned {ref['tuned_thr']}")
    drive = readout_drive_length_us(cfg)
    print(f"\n  per-iteration time budget from the config:")
    print(f"    readout drive          {drive:>7.2f} us  (read_length {nominal_len:g} + "
          f"adc_trig_offset + guard)")
    print(f"    read delay             {BASE_READ_DELAY_US:>7.2f} us")
    print(f"    meas syncdelay         {BASE_SYNCDELAY_US:>7.2f} us")
    print(f"    conditional pi + settle {0.05:>6.2f} us + pulse")
    print(f"    ------------------------------")
    print(f"    ~{drive + BASE_SYNCDELAY_US + 0.05:.2f} us per iteration, "
          f"x{BASE_ITERS} = {(drive + BASE_SYNCDELAY_US + 0.05) * BASE_ITERS:.1f} us")
    print(f"    + clear {BASE_CLEAR_US:g} + relax {GATE_RELAX_US:g} us per shot")

    pareto = []

    def record(tag, resid, us_shot, note="", floor=None, F=None, resid_g=None):
        pareto.append({"tag": tag, "resid": resid, "us": us_shot, "note": note,
                       "floor": ref["floor"] if floor is None else floor,
                       "F": ref["F"] if F is None else F,
                       "resid_g": resid if resid_g is None else resid_g})

    if RUN_ITERS:
        banner("STAGE 1 -- reset_max_iters 1..16")
        print("  Each in-loop readout was measured to destroy ~16% of the excited")
        print("  population, so more iterations is not automatically better.  This finds")
        print("  where it stops helping and whether it starts hurting.")
        print(f"\n  {'N':>3s} {'|g>':>16s} {'|e>':>16s} {'worst':>7s} {'floor':>7s} "
              f"{'us/shot':>9s} {'sweep(min)':>11s}")
        for it in ITERS_LIST:
            gm, ge, em, ee, w = worst_residual(soc, soccfg, cfg, ref, it)
            us, oh = timing(soc, soccfg, build(cfg, ref, True, True, it), ref)
            if it == BASE_ITERS and oh > 0:
                OVERHEAD_S[0] = oh
            record(f"iters={it}", w, us, resid_g=gm)
            print(f"  {it:>3d} {gm:>9.4f}+-{ge:<5.4f} {em:>9.4f}+-{ee:<5.4f} {w:>7.4f} "
                  f"{ref['floor']:>7.3f} {us:>9.1f} {sweep_time_min(us):>11.1f}",
                  flush=True)

    if RUN_READ_GAIN:
        banner("STAGE 2 -- readout drive gain DURING the reset loop only")
        print("  The reset only needs a binary decision; the final measurement needs a")
        print("  calibrated population.  They do not have to use the same readout power.")
        print("  A weaker reset tone should cause less measurement-induced decay but give")
        print("  worse in-loop discrimination, which RAISES the floor.  The threshold is")
        print("  re-calibrated at each gain, because the blobs move.")
        print(f"\n  {'gain':>7s} {'x nom':>6s} {'sep':>7s} {'F':>6s} {'floor':>7s} "
              f"{'thr':>8s} {'worst':>7s} {'us/shot':>9s}")
        for frac in READ_GAIN_FRACTIONS:
            g = int(round(nominal_gain * frac))
            if not 0 < g <= 32767:
                continue
            rg = reference(soc, soccfg, cfg, 2000, read_gain=g)
            gm2, _, _, _, w = worst_residual(
                soc, soccfg, cfg, ref, BASE_ITERS,
                threshold=rg["tuned_thr"], reset_read_pulse_gain=g)
            us = per_shot_us(soc, soccfg, build(
                cfg, ref, True, True, BASE_ITERS,
                threshold=rg["tuned_thr"], reset_read_pulse_gain=g), ref)
            record(f"read_gain={g}", w, us, f"floor {rg['floor']:.3f}", rg["floor"], ref["F"], gm2)
            print(f"  {g:>7d} {frac:>6.2f} {rg['sep']:>7.0f} {rg['F']:>6.3f} "
                  f"{rg['floor']:>7.3f} {rg['tuned_thr']:>8d} {w:>7.4f} {us:>9.1f}",
                  flush=True)

    if RUN_READ_LENGTH:
        banner("STAGE 3 -- read_length (global: reset AND measurement together)")
        print("  declare_readout fixes the ADC integration for the whole program, so this")
        print("  cannot be set differently for the reset and the measurement.  It is the")
        print("  single biggest wall-clock lever: the drive length follows it, and the")
        print("  loop pays it once per iteration.")
        print(f"  Currently {nominal_len:g} us -> drive {drive:.2f} us -> "
              f"{(drive + BASE_SYNCDELAY_US) * BASE_ITERS:.0f} us of reset per shot.")
        print(f"\n  {'read_len':>9s} {'drive':>7s} {'sep':>7s} {'F':>6s} {'floor':>7s} "
              f"{'worst':>7s} {'us/shot':>9s} {'sweep(min)':>11s}")
        for rl in READ_LENGTH_US:
            c = dict(cfg)
            c["read_length"] = float(rl)
            c.pop("read_pulse_length", None)
            try:
                rr = reference(soc, soccfg, c, 2000, read_length=rl)
                gm3, _, _, _, w = worst_residual(soc, soccfg, c, rr, BASE_ITERS,
                                                 threshold=rr["tuned_thr"])
                us = per_shot_us(soc, soccfg, build(c, rr, True, True, BASE_ITERS,
                                                    threshold=rr["tuned_thr"]), rr)
            except Exception as exc:
                print(f"  {rl:>9.1f}  failed: {str(exc)[:60]}")
                continue
            record(f"read_length={rl:g}", w, us,
                   f"F {rr['F']:.3f} floor {rr['floor']:.3f}", rr["floor"], rr["F"], gm3)
            print(f"  {rl:>9.1f} {readout_drive_length_us(c):>7.2f} {rr['sep']:>7.0f} "
                  f"{rr['F']:>6.3f} {rr['floor']:>7.3f} {w:>7.4f} {us:>9.1f} "
                  f"{sweep_time_min(us):>11.1f}", flush=True)

    if RUN_PI:
        banner("STAGE 4 -- the reset pi, gain x frequency, measured with force_flip")
        print("  force_flip fires the pi unconditionally, so ONE forced pi from |g> is a")
        print("  direct measurement of pi transfer, with no discrimination in the way.")
        print("  The reset pi can differ from the measurement pi (reset_pi_gain /")
        print("  reset_pi_freq), which matters because it fires right after a readout.")
        clean = stat([run_pe(soc, soccfg, build(cfg, ref, True, False, 1), ref)
                      for _ in range(ROUNDS)])
        print(f"\n  a clean pi (no readout in front) reaches P(exc) = "
              f"{clean[0]:.4f} +- {clean[1]:.4f}")
        print(f"\n  {'gain':>7s} " +
              " ".join(f"{d:+6.2f}MHz" for d in PI_DETUNE_MHZ))
        best = None
        for gf in PI_GAIN_FRACTIONS:
            g = int(round(pi_gain0 * gf))
            row = f"  {g:>7d} "
            for d in PI_DETUNE_MHZ:
                vals = [run_pe(soc, soccfg, build(
                    cfg, ref, False, True, 1, reset_force_flip=True,
                    reset_pi_gain=g, reset_pi_freq=pi_freq0 + d), ref)
                    for _ in range(max(3, ROUNDS // 2))]
                m, e = stat(vals)
                row += f" {m:>7.4f}  "
                if best is None or m > best[0]:
                    best = (m, g, d, e)
            print(row, flush=True)
        if best is not None:
            print(f"\n  best forced-pi transfer {best[0]:.4f} +- {best[3]:.4f} at "
                  f"gain {best[1]} ({best[1] / pi_gain0:.3f}x nominal), detune "
                  f"{best[2]:+.2f} MHz")
            print(f"  nominal reaches {clean[0]:.4f}; the reset pi is "
                  f"{'BETTER' if best[0] > clean[0] + 2 * clean[1] else 'no better'} "
                  f"when retuned for its position in the loop")

    if RUN_READ_DELAY:
        banner("STAGE 5 -- reset_read_delay_us (the stale-read guard)")
        print("  The tProc readout register is a latch: read() returns the PREVIOUS")
        print("  measurement unless it is given time to settle.  2.0 us was chosen to fix")
        print("  that.  Too small and the reset acts on stale data; too large and it eats")
        print("  into the syncdelay budget before the pi.")
        print(f"\n  {'delay':>7s} {'|g>':>16s} {'|e>':>16s} {'worst':>7s}")
        for rd in READ_DELAY_US:
            try:
                gm, ge, em, ee, w = worst_residual(soc, soccfg, cfg, ref, BASE_ITERS,
                                                   read_delay_us=rd)
            except ValueError as exc:
                print(f"  {rd:>7.2f}  rejected by the timing guard: {str(exc)[:55]}")
                continue
            print(f"  {rd:>7.2f} {gm:>9.4f}+-{ge:<5.4f} {em:>9.4f}+-{ee:<5.4f} "
                  f"{w:>7.4f}", flush=True)

    banner("SCORE -- effective wall clock, contrast-weighted")
    REF_F_BASELINE[0] = ref["F"]
    rows = [p for p in pareto if np.isfinite(p["resid"]) and p["us"] > 0]
    if rows:
        print("  A residual r does NOT come for free.  The measured population is")
        print("    P = P(e|g) + P_true * (1 - P(e|g) - P(g|e)) = a + b*P_true,  b = 2F-1")
        print("  and with a fraction r entering excited, the reference contrast is")
        print("    P1 - P0 = b * (1 - 2r)")
        print("  The residual cancels in the BIAS of pe = (Ps-P0)/(P1-P0), but the shots")
        print("  needed for a given T1 precision go as 1/contrast^2.  So the real cost is")
        print("    effective time  =  wall clock  /  [ (2F-1)(1-2r) ]^2")
        print("  r is taken as the GROUND-prepared residual, because in the production")
        print("  sequence the reset acts on a state the previous shot already left near")
        print("  ground.  r = 0.15 costs 2.0x the shots.  Time and residual trade off; they")
        print("  are not independent, and my earlier framing of 'a high floor is fine'")
        print("  was wrong.")
        for p in rows:
            p["above"] = p["resid"] - p["floor"]
            p["ok"] = p["above"] <= ar.MAX_RESIDUAL_ABOVE_FLOOR
            p["raw_min"] = sweep_time_min(p["us"])
            p["eff_min"] = effective_min(p["us"], p["F"], p["resid_g"])
            p["contrast"] = contrast(p["F"], p["resid_g"])
        print(f"\n  {'config':>22s} {'resid':>7s} {'above':>7s} {'F':>6s} "
              f"{'contrast':>9s} {'us/shot':>8s} {'raw min':>8s} {'eff min':>8s} {'':<3s}")
        for p in sorted(rows, key=lambda q: q["eff_min"]):
            print(f"  {p['tag']:>22s} {p['resid']:>7.4f} {p['above']:>+7.3f} "
                  f"{p['F']:>6.3f} {p['contrast']:>9.3f} {p['us']:>8.1f} "
                  f"{p['raw_min']:>8.2f} {p['eff_min']:>8.2f} "
                  f"{'ok ' if p['ok'] else 'NO ':<3s}")
        good = [p for p in rows if p["ok"]]
        base = next((p for p in rows if p["tag"] == f"iters={BASE_ITERS}"), None)
        if good:
            best = min(good, key=lambda p: p["eff_min"])
            print(f"\n  BEST BY EFFECTIVE TIME: {best['tag']}")
            print(f"    {best['us']:.1f} us/shot, residual {best['resid']:.4f}, "
                  f"contrast {best['contrast']:.3f}")
            print(f"    raw {best['raw_min']:.2f} min/pass, effective "
                  f"{best['eff_min']:.2f} min/pass")
            if base:
                print(f"    versus today ({base['tag']}): raw {base['raw_min']:.2f} -> "
                      f"{best['raw_min']:.2f} min, effective {base['eff_min']:.2f} -> "
                      f"{best['eff_min']:.2f} min "
                      f"({base['eff_min'] / max(best['eff_min'], 1e-9):.2f}x)")
        cheapest_raw = min(rows, key=lambda p: p["raw_min"])
        best_eff = min(rows, key=lambda p: p["eff_min"])
        if cheapest_raw["tag"] != best_eff["tag"]:
            print(f"\n  NOTE the fastest config ({cheapest_raw['tag']}, "
                  f"{cheapest_raw['raw_min']:.2f} min) is NOT the best one")
            print(f"  ({best_eff['tag']}, {best_eff['raw_min']:.2f} min raw but "
                  f"{best_eff['eff_min']:.2f} min effective).  Optimising raw wall clock")
            print(f"  alone would have picked the wrong configuration.")

    banner("THE BIGGER LEVER -- interleave_rounds")
    print(f"  This suite times ONE program per point.  Production does not:")
    print(f"  T13PointVsFlux -> _interleaved_populations visits every spec once PER ROUND")
    print(f"  and builds a fresh FFT1Program each visit (mT1VsFlux.py _run_point_counts),")
    print(f"  so a {SWEEP_POINTS}-point pass is 3 x {SWEEP_POINTS} x rounds programs,")
    print(f"  each carrying only shots/rounds shots.")
    oh = OVERHEAD_S[0]
    us = pareto[0]["us"] if pareto else 0.0
    base_us = next((p["us"] for p in pareto if p["tag"] == f"iters={BASE_ITERS}"), us)
    print(f"\n  with the measured overhead {oh * 1e3:.0f} ms and {base_us:.0f} us/shot:")
    print(f"    {'rounds':>7s} {'programs':>9s} {'ms/prog':>8s} {'min/pass':>9s} "
          f"{'speedup':>8s}")
    ref_min = None
    for r in (10, 5, 2, 1):
        shots = SHOTS_PER_POINT / r
        per = oh + shots * base_us * 1e-6
        tot = 3 * SWEEP_POINTS * r * per / 60.0
        if ref_min is None:
            ref_min = tot
        print(f"    {r:>7d} {3 * SWEEP_POINTS * r:>9d} {per * 1e3:>8.1f} {tot:>9.2f} "
              f"{ref_min / tot:>8.2f}x")
    print(f"\n  The triplet is already contiguous (group_size=3), so P0/P1/Ps drift-cancel")
    print(f"  WITHIN a triplet no matter what rounds is.  Rounds only guards against drift")
    print(f"  ACROSS a pass -- which a 2-3 day multi-pass run already averages over.")
    print(f"  This is worth more than every knob above combined, but it must be TESTED:")
    print(f"  run Step6ResetStrategy with INTERLEAVE_ROUNDS at 10, 5, 2, 1 and compare")
    print(f"  both the wall clock and the pass-to-pass T1 scatter before trusting it.")

    banner("done -- send me the .txt")


def main():
    with tee_log.tee("ResetSweepSuite", folder=outerFolder):
        run()


if __name__ == "__main__":
    main()
