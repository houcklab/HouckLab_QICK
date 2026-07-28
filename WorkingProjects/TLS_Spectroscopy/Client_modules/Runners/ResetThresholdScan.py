import time

import numpy as np

from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.socProxy import makeProxy
from WorkingProjects.TLS_Spectroscopy.Client_modules.Calib.initialize import BaseConfig
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mActiveResetProbe import (
    ReadProbeProgram, ResetCheckProgram,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import active_reset as ar

QUBIT = "q4"

ROUNDS = 4
REF_SHOTS = 4000
GATE_SHOTS = 600
REF_RELAX_US = 2000.0
GATE_RELAX_US = 25.0

ITERS_LIST = [1, 2, 3, 5, 8]
N_THRESHOLDS = 7
THRESHOLD_SPAN = (0.25, 0.95)

RESET_THERMALIZATION_US = 25.0
RESET_MEAS_SYNCDELAY_US = 4.0
RESET_READ_DELAY_US = 2.0

GATE_LIMIT = 0.2


def banner(text):
    print()
    print("=" * 100)
    print(text)
    print("=" * 100)


def ge_reference(soc, soccfg, cfg, shots):
    out = {}
    for label, gain in (("g", 0), ("e", int(cfg["qubit_pi_gain"]))):
        c = dict(cfg)
        c["probe_gain"] = int(gain)
        c["reps"] = c["shots"] = int(shots)
        c["relax_delay"] = REF_RELAX_US
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


def pick_oper(ref):
    lo = abs(np.median(ref["e"]["lower"]) - np.median(ref["g"]["lower"]))
    up = abs(np.median(ref["e"]["upper"]) - np.median(ref["g"]["upper"]))
    return ("lower", lo) if lo >= up else ("upper", up)


def make_projector(ref):
    Ig, Qg = ref["g"]["I"], ref["g"]["Q"]
    dx, dy = ref["e"]["I"] - Ig, ref["e"]["Q"] - Qg
    denom = dx * dx + dy * dy

    def project(Ir, Qr):
        return (((Ir - Ig) * dx + (Qr - Qg) * dy) / denom) if denom > 0 else float("nan")
    return project


def residual(soc, soccfg, cfg, project, prep_excited, threshold, ground_below,
             oper, iters):
    c = dict(cfg)
    c["reps"] = c["shots"] = int(GATE_SHOTS)
    c["prep_excited"] = bool(prep_excited)
    c["do_reset"] = True
    c["reset_threshold_raw"] = int(threshold)
    c["reset_ground_below"] = bool(ground_below)
    c["reset_oper"] = str(oper)
    c["reset_max_iters"] = int(iters)
    c["reset_thermalization_us"] = RESET_THERMALIZATION_US
    c["reset_meas_syncdelay_us"] = RESET_MEAS_SYNCDELAY_US
    c["reset_read_delay_us"] = RESET_READ_DELAY_US
    c["relax_delay"] = GATE_RELAX_US
    I, Q = ResetCheckProgram(soccfg, c).acquire(soc, load_pulses=True)
    return project(I, Q)


def main():
    soc, soccfg = makeProxy()
    cfg = dict(BaseConfig)
    cfg["qubit_gain"] = int(cfg["qubit_pi_gain"])
    cfg["reset_mode"] = "feedback"
    cfg["tproc_ch"] = ar.feedback_channel(soccfg, cfg["ro_chs"][0])

    banner("RESET THRESHOLD / ITERATION SCAN")
    print("  The reset loop is a two-state Markov chain.  Its fixed point is")
    print("      floor = P(e|g) / (P(e|g) + 1 - P(g|e))")
    print("  which depends ONLY on the readout error rates -- not on the pi pulse.")
    print("  A threshold chosen to maximise assignment fidelity balances P(e|g) against")
    print("  P(g|e).  That is the wrong trade for reset: P(e|g) sets the floor, while")
    print("  P(g|e) only slows convergence.  Pushing the threshold toward |e> should")
    print("  therefore LOWER the residual even though it LOWERS F.")
    print("  This scan measures that directly.")

    ref = ge_reference(soc, soccfg, cfg, REF_SHOTS)
    oper, sep = pick_oper(ref)
    g_shots, e_shots = ref["g"][oper], ref["e"][oper]
    fF = ar.fit_assignment_threshold(g_shots[::2], e_shots[::2])
    gb = bool(fF["ground_below"])
    g_med, e_med = float(np.median(g_shots)), float(np.median(e_shots))
    print(f"\n  quadrature '{oper}', |g> median {g_med:.0f}, |e> median {e_med:.0f}, "
          f"separation {sep:.0f}")
    print(f"  F-optimal threshold {fF['threshold_raw']} (ground_below={gb}): "
          f"F={fF['fidelity']:.3f}, P(e|g)={fF['p_e_given_g']:.3f}, "
          f"P(g|e)={fF['p_g_given_e']:.3f}")
    print(f"  -> reset floor at that threshold: "
          f"{ar.reset_floor(fF['p_e_given_g'], fF['p_g_given_e']):.3f}")

    fracs = np.linspace(THRESHOLD_SPAN[0], THRESHOLD_SPAN[1], N_THRESHOLDS)
    thresholds = sorted({int(round(g_med + f * (e_med - g_med))) for f in fracs}
                        | {int(fF["threshold_raw"])})
    print(f"\n  scanning {len(thresholds)} thresholds x {len(ITERS_LIST)} iteration "
          f"counts x {ROUNDS} interleaved rounds, {GATE_SHOTS} shots each")
    print(f"  thresholds: {thresholds}")

    rates = {}
    for thr in thresholds:
        peg, pge = ar._threshold_rates(g_shots[1::2], e_shots[1::2], thr, gb)
        rates[thr] = (peg, pge)

    cells = [(thr, it) for thr in thresholds for it in ITERS_LIST]
    acc = {c: {"g": [], "e": []} for c in cells}
    rng = np.random.default_rng(0)
    t0 = time.time()
    for r in range(ROUNDS):
        ref_r = ge_reference(soc, soccfg, cfg, 600)
        project = make_projector(ref_r)
        for idx in rng.permutation(len(cells)):
            thr, it = cells[idx]
            acc[(thr, it)]["g"].append(
                residual(soc, soccfg, cfg, project, False, thr, gb, oper, it))
            acc[(thr, it)]["e"].append(
                residual(soc, soccfg, cfg, project, True, thr, gb, oper, it))
        print(f"  round {r + 1}/{ROUNDS} done ({time.time() - t0:.0f} s)", flush=True)

    def stat(vals):
        v = np.asarray(vals, dtype=float)
        v = v[np.isfinite(v)]
        if v.size == 0:
            return np.nan, np.nan
        return float(np.mean(v)), float(np.std(v) / max(1.0, np.sqrt(v.size - 1)))

    banner("MEASURED RESIDUALS")
    print(f"  {'thr':>8s} {'P(e|g)':>7s} {'P(g|e)':>7s} {'floor':>6s} | " +
          " ".join(f"{'N=' + str(it):>15s}" for it in ITERS_LIST))
    grid = {}
    for thr in thresholds:
        peg, pge = rates[thr]
        row = f"  {thr:>8d} {peg:>7.3f} {pge:>7.3f} {ar.reset_floor(peg, pge):>6.3f} |"
        for it in ITERS_LIST:
            mg, sgm = stat(acc[(thr, it)]["g"])
            me, sem = stat(acc[(thr, it)]["e"])
            worst = max(abs(mg), abs(me))
            grid[(thr, it)] = {"g": mg, "g_err": sgm, "e": me, "e_err": sem,
                               "worst": worst}
            row += f" {me:>7.3f}+-{sem:<5.3f}"
        print(row + ("   <- F-optimal" if thr == int(fF["threshold_raw"]) else ""))
    print("\n  (values shown are the |e> residual; |g> residuals below)")
    print(f"  {'thr':>8s} |" + " ".join(f"{'N=' + str(it):>15s}" for it in ITERS_LIST))
    for thr in thresholds:
        row = f"  {thr:>8d} |"
        for it in ITERS_LIST:
            c = grid[(thr, it)]
            row += f" {c['g']:>7.3f}+-{c['g_err']:<5.3f}"
        print(row)

    banner("MODEL vs MEASUREMENT")

    def chi2(f, off):
        s = 0.0
        n = 0
        for (thr, it), c in grid.items():
            peg, pge = rates[thr]
            pe, pg = ar.predicted_residuals(peg, pge, f, it)
            if np.isfinite(c["e"]):
                s += ((c["e"] - off - pe) / max(c["e_err"], 1e-3)) ** 2
                n += 1
            if np.isfinite(c["g"]):
                s += ((c["g"] - off - pg) / max(c["g_err"], 1e-3)) ** 2
                n += 1
        return s, n

    fs = np.linspace(0.05, 1.0, 191)
    offs = np.linspace(-0.10, 0.25, 141)
    s_plain, n_pts = min((chi2(f, 0.0) for f in fs), key=lambda x: x[0])
    f_plain = float(fs[int(np.argmin([chi2(f, 0.0)[0] for f in fs]))])
    s_off, f_best, off_best = min((chi2(f, o)[0], float(f), float(o))
                                  for f in fs for o in offs)
    print(f"  the model has ONE free parameter, the pi efficiency f, and predicts both")
    print(f"  the |g> and the |e> residual at every cell.  Fitting all {n_pts} points:")
    print(f"\n    zero point fixed at 0 : chi2/dof = {s_plain / max(n_pts - 1, 1):6.2f}  "
          f"(f = {f_plain:.2f})")
    print(f"    zero point free       : chi2/dof = {s_off / max(n_pts - 2, 1):6.2f}  "
          f"(f = {f_best:.2f}, offset = {off_best:+.3f})")
    print(f"    delta-chi2 for that one extra parameter: {s_plain - s_off:.0f}")
    zero_point_error = (s_plain - s_off) > 25.0 and abs(off_best) > 0.02
    if zero_point_error:
        print(f"\n  -> the SHAPE of the model is right but its ZERO POINT is not.  Every")
        print(f"     residual measured here is high by {off_best:+.3f}, independently of")
        print(f"     threshold and of iteration count.  No reset mechanism can do that:")
        print(f"     it is an artefact of how the residual is referenced (the projector's")
        print(f"     0 and 1 come from ReadProbeProgram at {REF_RELAX_US:g} us relax, but")
        print(f"     are applied to ResetCheckProgram at {GATE_RELAX_US:g} us).")
        print(f"     Run Runners/ResetBaselineAudit.py to decompose it.")
        print(f"     The numbers below are quoted BOTH ways.")
    elif s_off / max(n_pts - 2, 1) < 3.0:
        print(f"\n  -> the Markov model describes the reset.  The floor is real.")
    else:
        print(f"\n  -> the model does NOT describe the data even with a free zero point.")
        print(f"     Something beyond readout errors + a finite-fidelity pi is at work.")
    print(f"\n  {'thr':>8s} {'N':>3s} {'meas |e>':>9s} {'model':>7s} "
          f"{'meas |g>':>9s} {'model':>7s}   (model includes offset {off_best:+.3f})")
    for thr in thresholds:
        for it in ITERS_LIST:
            peg, pge = rates[thr]
            pe, pg = ar.predicted_residuals(peg, pge, f_best, it)
            c = grid[(thr, it)]
            print(f"  {thr:>8d} {it:>3d} {c['e']:>9.3f} {pe + off_best:>7.3f} "
                  f"{c['g']:>9.3f} {pg + off_best:>7.3f}")

    banner("RECOMMENDATION")
    print(f"  {len(grid)} cells were measured.  Picking the single smallest is a")
    print(f"  max-of-noise selection, so the recommendation below comes from the FITTED")
    print(f"  model (which pools all {n_pts} points) evaluated on the measured blob")
    print(f"  statistics, not from the grid minimum.")
    cand = np.unique(np.concatenate((g_shots, e_shots)))
    cand = cand[(cand > min(thresholds) - 4000) & (cand < max(thresholds) + 4000)]
    best = None
    print(f"\n  {'N':>3s} {'best thr':>9s} {'P(e|g)':>7s} {'P(g|e)':>7s} {'F':>6s} "
          f"{'true worst':>11s} {'as measured':>12s}")
    for it in ITERS_LIST:
        row = None
        for t in cand[::max(1, len(cand) // 400)]:
            peg, pge = ar._threshold_rates(g_shots[1::2], e_shots[1::2], t, gb)
            pe, pg = ar.predicted_residuals(peg, pge, f_best, it)
            w = max(pe, pg)
            if np.isfinite(w) and (row is None or w < row[0]):
                row = (w, int(t), peg, pge)
        if row is None:
            continue
        w, t, peg, pge = row
        print(f"  {it:>3d} {t:>9d} {peg:>7.3f} {pge:>7.3f} "
              f"{1 - 0.5 * (peg + pge):>6.3f} {w:>11.3f} {w + off_best:>12.3f}")
        if best is None or w < best[0]:
            best = row + (it,)
    peg0, pge0 = rates[int(fF["threshold_raw"])]
    pe0, pg0 = ar.predicted_residuals(peg0, pge0, f_best, 3)
    base = grid.get((int(fF["threshold_raw"]), 3))
    print(f"\n  today's setting (F-optimal threshold {fF['threshold_raw']}, 3 iters):")
    print(f"     model true worst {max(pe0, pg0):.3f}, as measured "
          f"{max(pe0, pg0) + off_best:.3f}"
          + (f", observed {base['worst']:.3f}" if base else ""))
    if best is not None:
        w, t, peg, pge, it = best
        print(f"\n  -> set RESET_THRESHOLD_RAW = {t}")
        print(f"     set RESET_GROUND_BELOW  = {gb}")
        print(f"     set RESET_MAX_ITERS     = {it}")
        print(f"     (model true worst {w:.3f}, assignment F at that threshold "
              f"{1 - 0.5 * (peg + pge):.3f})")
    print(f"\n  cheapest N whose model worst-case clears the {GATE_LIMIT} gate WITH the")
    print(f"  zero-point offset still in place (i.e. what the gate will actually see):")
    got = False
    for it in ITERS_LIST:
        row = None
        for t in cand[::max(1, len(cand) // 400)]:
            peg, pge = ar._threshold_rates(g_shots[1::2], e_shots[1::2], t, gb)
            w = max(ar.predicted_residuals(peg, pge, f_best, it))
            if np.isfinite(w) and (row is None or w < row[0]):
                row = (w, int(t))
        if row is not None and row[0] + off_best <= GATE_LIMIT:
            print(f"     N = {it} at threshold {row[1]} -> {row[0] + off_best:.3f}")
            got = True
            break
    if not got:
        print(f"     none of the iteration counts tested.  Fix the zero point first")
        print(f"     (ResetBaselineAudit.py) -- without the offset, N = "
              f"{ITERS_LIST[0]} already clears it.")

    banner("scan complete -- paste the whole log back")


if __name__ == "__main__":
    main()
