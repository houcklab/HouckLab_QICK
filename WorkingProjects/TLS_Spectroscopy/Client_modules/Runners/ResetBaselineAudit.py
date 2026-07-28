import time

import numpy as np

from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.socProxy import makeProxy
from WorkingProjects.TLS_Spectroscopy.Client_modules.Calib.initialize import BaseConfig
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mActiveResetProbe import (
    ReadProbeProgram, ResetCheckProgram,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import active_reset as ar

QUBIT = "q4"

ROUNDS = 5
REF_SHOTS = 4000
GATE_SHOTS = 800
REF_RELAX_US = 2000.0
GATE_RELAX_US = 25.0

NEVER_FIRE_THRESHOLD = 1 << 22
NEVER_FIRE_GROUND_BELOW = True
ALWAYS_FIRE = True

ITERS_LIST = [1, 2, 3, 5, 8]
THERMALIZATION_SWEEP_US = [0.5, 2.0, 5.0, 10.0, 25.0, 50.0]
RELAX_SWEEP_US = [25.0, 50.0, 100.0, 250.0, 1000.0, 2000.0]

RESET_THERMALIZATION_US = 2.0
RESET_MEAS_SYNCDELAY_US = 4.0
RESET_READ_DELAY_US = 2.0
RESET_ITERS = 3


def banner(text):
    print()
    print("=" * 100)
    print(text)
    print("=" * 100)


def read_probe_ge(soc, soccfg, cfg, shots, relax_us):
    out = {}
    for label, gain in (("g", 0), ("e", int(cfg["qubit_pi_gain"]))):
        c = dict(cfg)
        c["probe_gain"] = int(gain)
        c["reps"] = c["shots"] = int(shots)
        c["relax_delay"] = float(relax_us)
        prog = ReadProbeProgram(soccfg, c)
        avgi, avgq = prog.acquire(soc, load_pulses=True, progress=False)
        out[label] = {
            "I": float(np.asarray(avgi).ravel()[0]),
            "Q": float(np.asarray(avgq).ravel()[0]),
            "lower": np.asarray([ar.to_signed32(v) for v in
                                 np.asarray(prog.di_buf[0]).ravel()], dtype=np.int64),
            "upper": np.asarray([ar.to_signed32(v) for v in
                                 np.asarray(prog.dq_buf[0]).ravel()], dtype=np.int64),
        }
    return out


def gate_iq(soc, soccfg, cfg, prep_excited, do_reset, threshold, ground_below, oper,
            iters, thermalization_us=None, relax_us=None, force_flip=False,
            shots=None):
    c = dict(cfg)
    c["reps"] = c["shots"] = int(GATE_SHOTS if shots is None else shots)
    c["prep_excited"] = bool(prep_excited)
    c["do_reset"] = bool(do_reset)
    c["reset_threshold_raw"] = int(threshold)
    c["reset_ground_below"] = bool(ground_below)
    c["reset_oper"] = str(oper)
    c["reset_max_iters"] = int(iters)
    c["reset_force_flip"] = bool(force_flip)
    c["reset_thermalization_us"] = float(
        RESET_THERMALIZATION_US if thermalization_us is None else thermalization_us)
    c["reset_meas_syncdelay_us"] = RESET_MEAS_SYNCDELAY_US
    c["reset_read_delay_us"] = RESET_READ_DELAY_US
    c["relax_delay"] = float(GATE_RELAX_US if relax_us is None else relax_us)
    prog = ResetCheckProgram(soccfg, c)
    I, Q = prog.acquire(soc, load_pulses=True)
    return I, Q, prog


def projector(Ig, Qg, Ie, Qe):
    dx, dy = Ie - Ig, Qe - Qg
    denom = dx * dx + dy * dy

    def project(Ir, Qr):
        return (((Ir - Ig) * dx + (Qr - Qg) * dy) / denom) if denom > 0 else float("nan")
    return project


def stat(vals):
    v = np.asarray(vals, dtype=float)
    v = v[np.isfinite(v)]
    if v.size == 0:
        return np.nan, np.nan
    return float(np.mean(v)), float(np.std(v) / max(1.0, np.sqrt(v.size - 1)))


def show(label, m, e, width=52):
    print(f"  {label:<{width}s} {m:>+8.4f} +- {e:<7.4f}")


def main():
    soc, soccfg = makeProxy()
    cfg = dict(BaseConfig)
    cfg["qubit_gain"] = int(cfg["qubit_pi_gain"])
    cfg["reset_mode"] = "feedback"
    cfg["tproc_ch"] = ar.feedback_channel(soccfg, cfg["ro_chs"][0])

    banner("RESET BASELINE AUDIT")
    print("  The threshold scan showed the Markov model fits only after adding ~+0.065 to")
    print("  every residual (chi2/dof 7.3 -> 1.8, delta-chi2 = 432 for one parameter).")
    print("  That excess is flat in threshold over the useful range, but it is NOT flat in")
    print("  iteration count: +0.036 at N=1 rising to +0.069 at N=8 (3.8 sigma apart).  So")
    print("  roughly half of it is there after a single readout and the rest accumulates")
    print("  and saturates.  No mechanism proposed so far survives scrutiny, so this script")
    print("  measures the pieces instead of arguing about them:")
    print("     (A) reference-vs-gate program mismatch, do_reset=False")
    print("     (B) readout back-action, with a threshold so extreme the pi NEVER fires")
    print("     (C) resonator ring-down, sweeping reset_thermalization_us")
    print("     (D) inter-shot relaxation, sweeping relax_delay")
    print("     (E) pi efficiency measured directly with force_flip")
    print("     (G) THE DECISIVE ONE: the single-shot histogram of the final readout,")
    print("         which separates a real excited population from a displaced blob.")
    print("         acquire() used to average this away; it does not any more.")

    ref = read_probe_ge(soc, soccfg, cfg, REF_SHOTS, REF_RELAX_US)
    lo = abs(np.median(ref["e"]["lower"]) - np.median(ref["g"]["lower"]))
    up = abs(np.median(ref["e"]["upper"]) - np.median(ref["g"]["upper"]))
    oper = "lower" if lo >= up else "upper"
    sep = max(lo, up)
    disc = ar.fit_assignment_threshold(ref["g"][oper][::2], ref["e"][oper][::2])
    gb = bool(disc["ground_below"])
    thr_F = int(disc["threshold_raw"])
    g_med = float(np.median(ref["g"][oper]))
    e_med = float(np.median(ref["e"][oper]))
    thr_hi = int(round(g_med + 0.72 * (e_med - g_med)))
    old = projector(ref["g"]["I"], ref["g"]["Q"], ref["e"]["I"], ref["e"]["Q"])
    print(f"\n  quadrature '{oper}', |g> {g_med:.0f}, |e> {e_med:.0f}, separation {sep:.0f}")
    print(f"  F-optimal threshold {thr_F} (ground_below={gb}), F={disc['fidelity']:.3f}, "
          f"P(e|g)={disc['p_e_given_g']:.3f}, P(g|e)={disc['p_g_given_e']:.3f}")
    print(f"  high threshold for comparison: {thr_hi}")
    print(f"  never-fire threshold: {NEVER_FIRE_THRESHOLD} with ground_below=True "
          f"({NEVER_FIRE_THRESHOLD / max(sep, 1):.0f}x the blob separation, so the")
    print(f"    condj comparison 'reg_val < threshold -> skip the pi' is always true")
    print(f"    regardless of the real ground_below={gb})")

    acc = {}
    shot_hist = {}

    def record(key, value):
        acc.setdefault(key, []).append(value)

    t0 = time.time()
    for r in range(ROUNDS):
        anchors = {}
        for prep in (False, True):
            I, Q, _ = gate_iq(soc, soccfg, cfg, prep, False, thr_F, gb, oper, 1)
            anchors[prep] = (I, Q)
            record(("insitu_anchor_old", prep), old(I, Q))
        ins = projector(anchors[False][0], anchors[False][1],
                        anchors[True][0], anchors[True][1])

        for N in ITERS_LIST:
            for prep in (False, True):
                I, Q, _ = gate_iq(soc, soccfg, cfg, prep, True, NEVER_FIRE_THRESHOLD,
                               NEVER_FIRE_GROUND_BELOW, oper, N)
                record(("neverfire_old", N, prep), old(I, Q))
                record(("neverfire_ins", N, prep), ins(I, Q))

        for th in THERMALIZATION_SWEEP_US:
            I, Q, _ = gate_iq(soc, soccfg, cfg, False, True, NEVER_FIRE_THRESHOLD,
                           NEVER_FIRE_GROUND_BELOW, oper, RESET_ITERS,
                           thermalization_us=th)
            record(("therm_old", th), old(I, Q))
            record(("therm_ins", th), ins(I, Q))

        for rl in RELAX_SWEEP_US:
            n = 300 if rl > 250.0 else GATE_SHOTS
            I, Q, _ = gate_iq(soc, soccfg, cfg, False, False, thr_F, gb, oper, 1,
                           relax_us=rl, shots=n)
            record(("relax_old", rl), old(I, Q))
            I, Q, _ = gate_iq(soc, soccfg, cfg, True, False, thr_F, gb, oper, 1,
                           relax_us=rl, shots=n)
            record(("relax_old_e", rl), old(I, Q))

        if ALWAYS_FIRE:
            for N in (1, 2, 3):
                I, Q, _ = gate_iq(soc, soccfg, cfg, False, True, thr_F, gb, oper, N,
                               force_flip=True)
                record(("forceflip_ins", N), ins(I, Q))
                record(("forceflip_old", N), old(I, Q))

        for thr in (thr_F, thr_hi):
            for prep in (False, True):
                I, Q, prog = gate_iq(soc, soccfg, cfg, prep, True, thr, gb, oper,
                                     RESET_ITERS)
                record(("real_old", thr, prep), old(I, Q))
                record(("real_ins", thr, prep), ins(I, Q))
                if r == 0 and not prep:
                    lo_s, up_s = prog.shots()
                    if lo_s is not None:
                        shot_hist[thr] = (lo_s if oper == "lower" else up_s)[:, -1]
        for tag, kw in (("noreset", dict(do_reset=False, iters=1)),
                        ("neverfire", dict(do_reset=True, iters=RESET_ITERS,
                                           threshold=NEVER_FIRE_THRESHOLD,
                                           ground_below=NEVER_FIRE_GROUND_BELOW))):
            if r != 0:
                continue
            I, Q, prog = gate_iq(soc, soccfg, cfg, False,
                                 kw.get("do_reset"),
                                 kw.get("threshold", thr_F),
                                 kw.get("ground_below", gb), oper, kw["iters"])
            lo_s, up_s = prog.shots()
            if lo_s is not None:
                shot_hist[tag] = (lo_s if oper == "lower" else up_s)[:, -1]

        print(f"  round {r + 1}/{ROUNDS} done ({time.time() - t0:.0f} s)", flush=True)

    banner("(A) ZERO POINT -- where ResetCheckProgram lands in the OLD projection")
    print("  These are do_reset=False.  With a perfect zero point they would read exactly")
    print("  0.000 and 1.000.  Any deviation is reference-vs-gate mismatch: no reset ran")
    print("  and no extra readout happened, only the program and the relax delay differ.")
    print("  Section (D) below splits this into the program part and the 25 us inter-shot")
    print("  relaxation part.")
    ag = stat(acc[("insitu_anchor_old", False)])
    ae = stat(acc[("insitu_anchor_old", True)])
    show("prep |g>, no reset  (should be 0.000)", *ag)
    show("prep |e>, no reset  (should be 1.000)", *ae)
    mismatch = ag[0]
    span = ae[0] - ag[0]
    print(f"\n  -> zero-point error  = {mismatch:+.4f}")
    print(f"  -> span error        = {span:.4f} (1.000 would mean the prepared |e> in the")
    print(f"                          gate is as excited as the reference |e>)")

    banner("(B) READOUT BACK-ACTION -- reset loop runs but the pi can NEVER fire")
    print("  Threshold is set 1e3x beyond the blobs, so condj always skips.  The only")
    print("  difference from (A) is N extra readout tones.  In the IN-SITU projection the")
    print("  no-reset points are 0 and 1 by construction, so anything nonzero here is the")
    print("  readout tones acting on the qubit.")
    print(f"\n  {'N':>3s} {'|g> in-situ':>20s} {'|e> in-situ':>20s} {'|g> old proj':>20s}")
    for N in ITERS_LIST:
        gi = stat(acc[("neverfire_ins", N, False)])
        ei = stat(acc[("neverfire_ins", N, True)])
        go = stat(acc[("neverfire_old", N, False)])
        print(f"  {N:>3d} {gi[0]:>+11.4f}+-{gi[1]:<7.4f} {ei[0]:>+11.4f}+-{ei[1]:<7.4f} "
              f"{go[0]:>+11.4f}+-{go[1]:<7.4f}")
    e1 = stat(acc[("neverfire_ins", 1, True)])[0]
    e8 = stat(acc[("neverfire_ins", 8, True)])[0]
    print(f"\n  SANITY: the |e> column must stay near 1.0 -- if the pi were firing it would")
    print(f"  collapse.  N=1 {e1:+.3f}, N=8 {e8:+.3f}.")
    if e8 < 0.5:
        print("  *** it collapsed: the never-fire threshold did NOT disable the pi. ***")
        print("  *** everything in section (B) is invalid; tell me and I will fix it. ***")
    else:
        print(f"  The |e> decay from N=1 to N=8 is the qubit relaxing during the loop plus")
        print(f"  any measurement-induced decay.")

    banner("(C) RESONATOR RING-DOWN -- sweep reset_thermalization_us, pi never fires")
    print("  prep |g>, 3 never-firing iterations, varying the clearing delay before the")
    print("  final readout.  If leftover photons are the zero-point error, this falls.")
    print(f"\n  {'clear (us)':>11s} {'in-situ':>20s} {'old proj':>20s}")
    for th in THERMALIZATION_SWEEP_US:
        a = stat(acc[("therm_ins", th)])
        b = stat(acc[("therm_old", th)])
        print(f"  {th:>11.1f} {a[0]:>+11.4f}+-{a[1]:<7.4f} {b[0]:>+11.4f}+-{b[1]:<7.4f}")
    lo_t = stat(acc[("therm_ins", THERMALIZATION_SWEEP_US[0])])
    hi_t = stat(acc[("therm_ins", THERMALIZATION_SWEEP_US[-1])])
    d = lo_t[0] - hi_t[0]
    de = np.hypot(lo_t[1], hi_t[1])
    print(f"\n  change from {THERMALIZATION_SWEEP_US[0]:g} us to "
          f"{THERMALIZATION_SWEEP_US[-1]:g} us: {d:+.4f} +- {de:.4f} "
          f"({abs(d) / max(de, 1e-9):.1f} sigma)")

    banner("(D) INTER-SHOT RELAXATION -- sweep relax_delay, no reset at all")
    print("  The reference uses 2000 us; the gate uses 25 us.  With T1 ~ 316 us a 25 us")
    print("  gap leaves 92% of the previous shot's state in place.  If that is the zero")
    print("  point error, the |g> row converges to 0 as relax grows.")
    print(f"\n  {'relax (us)':>11s} {'prep |g>, old proj':>22s} {'prep |e>, old proj':>22s}")
    for rl in RELAX_SWEEP_US:
        a = stat(acc[("relax_old", rl)])
        b = stat(acc[("relax_old_e", rl)])
        print(f"  {rl:>11.1f} {a[0]:>+13.4f}+-{a[1]:<7.4f} {b[0]:>+13.4f}+-{b[1]:<7.4f}")

    if ALWAYS_FIRE:
        banner("(E) PI EFFICIENCY, measured directly with force_flip")
        print("  prep |g>, reset loop with the conditional branch removed so the pi ALWAYS")
        print("  fires.  After 1 forced pi the in-situ residual IS the pi transfer")
        print("  efficiency.  The threshold-scan fit inferred f = 0.91 indirectly.")
        for N in (1, 2, 3):
            a = stat(acc[("forceflip_ins", N)])
            show(f"{N} forced pi from |g>", *a)
        f1 = stat(acc[("forceflip_ins", 1)])
        print(f"\n  -> measured pi efficiency f = {f1[0]:.3f} +- {f1[1]:.3f}")

    banner("(F) THE REAL RESET, both zero points")
    print(f"  {'thr':>8s} {'prep':>5s} {'old proj':>20s} {'in-situ':>20s} {'model':>8s}")
    peg_F, pge_F = ar._threshold_rates(ref["g"][oper][1::2], ref["e"][oper][1::2],
                                       thr_F, gb)
    peg_H, pge_H = ar._threshold_rates(ref["g"][oper][1::2], ref["e"][oper][1::2],
                                       thr_hi, gb)
    f_meas = (stat(acc[("forceflip_ins", 1)])[0] if ALWAYS_FIRE else 0.91)
    f_meas = float(min(1.0, max(0.05, f_meas)))
    for thr, (peg, pge) in ((thr_F, (peg_F, pge_F)), (thr_hi, (peg_H, pge_H))):
        pe, pg = ar.predicted_residuals(peg, pge, f_meas, RESET_ITERS)
        for prep, model in ((False, pg), (True, pe)):
            a = stat(acc[("real_old", thr, prep)])
            b = stat(acc[("real_ins", thr, prep)])
            print(f"  {thr:>8d} {('|e>' if prep else '|g>'):>5s} "
                  f"{a[0]:>+11.4f}+-{a[1]:<7.4f} {b[0]:>+11.4f}+-{b[1]:<7.4f} "
                  f"{model:>8.4f}")
    print(f"\n  (model uses the directly measured pi efficiency f = {f_meas:.3f} and the")
    print(f"   P(e|g)/P(g|e) measured on the held-out raw shots at each threshold:")
    print(f"   thr {thr_F}: {peg_F:.3f}/{pge_F:.3f}   thr {thr_hi}: {peg_H:.3f}/{pge_H:.3f})")

    banner("(G) POPULATION OR DISPLACEMENT?  the single-shot histogram")
    print("  This is the decisive one, and the data was always there -- acquire() used to")
    print("  average it away.  A residual of +0.065 has exactly two explanations, and they")
    print("  are identical in the mean and obvious in the histogram:")
    print("    POPULATION  -- 6.5% of shots really sit in the |e> blob.  The |g> blob stays")
    print("                   put and keeps its width; a second bump appears at |e>.")
    print("    DISPLACEMENT-- no shot is excited; the whole |g> blob slid toward |e> by")
    print("                   6.5% of the separation.  Centroid moves, width does not,")
    print("                   no bump.  In that case the residual is an artefact.")
    g_ref = ref["g"][oper].astype(float)
    e_ref = ref["e"][oper].astype(float)
    g_mu, g_sd = float(np.mean(g_ref)), float(np.std(g_ref))
    e_mu, e_sd = float(np.mean(e_ref)), float(np.std(e_ref))
    print(f"\n  reference blobs: |g> {g_mu:.0f} +- {g_sd:.0f}   |e> {e_mu:.0f} +- {e_sd:.0f}")
    span = e_mu - g_mu
    edges = np.linspace(min(g_mu, e_mu) - 4 * max(g_sd, e_sd),
                        max(g_mu, e_mu) + 4 * max(g_sd, e_sd), 60)

    def decompose(v):
        obs, _ = np.histogram(v, bins=edges)
        obs = obs / max(obs.sum(), 1)
        best = None
        for p in np.linspace(0.0, 0.6, 121):
            for s in np.linspace(-0.15, 0.35, 101) * span:
                mg, _ = np.histogram(g_ref + s, bins=edges)
                me, _ = np.histogram(e_ref + s, bins=edges)
                mod = (1 - p) * mg / max(mg.sum(), 1) + p * me / max(me.sum(), 1)
                d = float(np.sum((obs - mod) ** 2))
                if best is None or d < best[0]:
                    best = (d, p, s / span)
        return best[1], best[2]

    print(f"\n  Decomposing each histogram as (1-p)*|g>_ref + p*|e>_ref, both allowed to")
    print(f"  slide by a common shift s.  p is REAL excited population; s is pure")
    print(f"  displacement.  The projected residual reports p + s together and cannot")
    print(f"  tell them apart.")
    print(f"\n  {'case':>18s} {'shots':>6s} {'residual':>9s} {'p (real)':>9s} "
          f"{'s (shift)':>10s} {'width/ref':>10s}")
    for key in ("noreset", "neverfire", thr_F, thr_hi):
        v = shot_hist.get(key)
        if v is None:
            continue
        v = np.asarray(v, dtype=float)
        name = key if isinstance(key, str) else f"reset thr {key}"
        p, s = decompose(v)
        print(f"  {name:>18s} {v.size:>6d} "
              f"{(float(np.mean(v)) - g_mu) / max(span, 1):>9.3f} {p:>9.3f} "
              f"{s:>10.3f} {float(np.std(v)) / max(g_sd, 1):>10.3f}")
    print(f"\n  If p carries the residual and s ~ 0, the excited population is REAL and")
    print(f"  the reset genuinely leaves it behind -- the Markov model needs a term the")
    print(f"  calibrated P(e|g)/P(g|e) do not capture.")
    print(f"  If s carries it and p ~ 0 with width/ref ~ 1.0, no shot is excited: the")
    print(f"  blob merely slid and the residual is an ARTEFACT of the zero point.")
    print(f"  Compare 'noreset' against the reset rows -- the difference is what the")
    print(f"  reset loop itself adds, free of any reference-program mismatch.")

    banner("DECOMPOSITION OF THE +0.065")
    nf3 = stat(acc[("neverfire_ins", RESET_ITERS, False)])
    print(f"  (A) reference-vs-gate program mismatch        {mismatch:>+8.4f}")
    print(f"  (B) readout back-action, {RESET_ITERS} never-firing reads  {nf3[0]:>+8.4f}")
    print(f"  (C) ring-down, {THERMALIZATION_SWEEP_US[0]:g} us vs "
          f"{THERMALIZATION_SWEEP_US[-1]:g} us           {d:>+8.4f}")
    print(f"      ------------------------------------------------")
    print(f"      (A)+(B) as measured in the old projection    "
          f"{mismatch + nf3[0]:>+8.4f}")
    print(f"      offset needed by the threshold-scan fit         +0.0650")

    banner("audit complete -- paste the whole log back")


if __name__ == "__main__":
    main()
