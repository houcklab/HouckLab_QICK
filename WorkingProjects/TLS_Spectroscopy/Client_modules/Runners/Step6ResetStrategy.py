import gc
import time

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.socProxy import makeProxy
from WorkingProjects.TLS_Spectroscopy.Client_modules.Calib.initialize import BaseConfig, outerFolder
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mSingleShot1Q import SingleShot1Q
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mActiveResetProbe import (
    ActiveResetProbe)
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mT1VsFlux import T13PointVsFlux
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import active_reset, flux_fit as fx
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import tee_log

QUBIT = "q4"

WALL_CLOCK_MIN = 5.0
DC_POINTS = 8
SHOTS = 500
Ts_US = 115.0

DETUNE_FRACTIONS = [-0.20, -0.10, 0.0, 0.10, 0.20, 0.35]
DETUNE_DC_POINTS = 5
DETUNE_SHOTS = 500
DETUNE_REPEATS = 2

ROUNDS_AB = [10, 5, 2, 1]
ROUNDS_AB_PASSES = 4

SS_SHOTS = 1000
SS_GROUND_THRESHOLD = 0.7
PROBE_SHOTS = 2000

INTERLEAVE_ROUNDS = 10
RANDOMIZE_POINT_ORDER = True
THERMALIZATION_US = 2.0
FEEDBACK_RELAX_US = 25.0
PASSIVE_BACKSTOP_US = 2000.0
RESET_MAX_ITERS = 3
MIN_REF_CONTRAST = 0.05
MAX_PLOT_T1_MULTIPLE = 20.0

SWEEP_POINTS_PROD = 335
DC_MIN, DC_MAX, FREQ_STEP_MHZ = 0, 10000, 1
FLUX_FIT_PARAMS = [9.30070052036, 0.100677145556, 31881.294671,
                   7115.71137189, 0.822636051338, -4.13273417292e-05]


def banner(text):
    print()
    print("=" * 96)
    print(text)
    print("=" * 96)


def build_cfg(dc_vec, shots, rec, threshold_override=None):
    cfg = dict(BaseConfig)
    cfg.update({
        "shots": int(shots), "reps": int(shots),
        "interleave_rounds": INTERLEAVE_ROUNDS,
        "randomize_point_order": bool(RANDOMIZE_POINT_ORDER),
        "point_order_seed": None,
        "ff_gain_vec": dc_vec,
        "flux_fit_params": FLUX_FIT_PARAMS,
        "qubit_pulse_style": "arb",
        "reset_mode": "feedback" if rec is not None else "passive",
        "three_point_matched_refs": True,
    })
    if rec is not None:
        thr = int(rec["threshold_raw"] if threshold_override is None
                  else threshold_override)
        cfg.update({
            "reset_threshold_raw": thr,
            "reset_oper": str(rec["oper"]),
            "reset_ground_below": bool(rec["ground_below"]),
            "reset_max_iters": int(RESET_MAX_ITERS),
            "reset_thermalization_us": THERMALIZATION_US,
            "relax_delay": FEEDBACK_RELAX_US,
        })
    else:
        cfg["relax_delay"] = PASSIVE_BACKSTOP_US
    return cfg


def run_3pt(soc, soccfg, cfg, dc_vec, shots, calib_params, suffix):
    exp = T13PointVsFlux(
        soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outerFolder,
        suffix=suffix, cfg=dict(cfg), dc_vec=dc_vec,
        Ts_ns=int(round(Ts_US * 1e3)), shots=int(shots),
        calib_params=calib_params, park_voltage=0,
        reset_mode=cfg["reset_mode"],
        min_ref_contrast=MIN_REF_CONTRAST,
        max_plot_t1_multiple=MAX_PLOT_T1_MULTIPLE,
        run_park_T1_if_Ts_none=False, write_outputs=False)
    exp.acquire(progress=False)
    plt.close("all")
    gc.collect()
    return exp


def summarize(exp):
    d = exp.data
    return (np.asarray(d["T1_3pt_us"], dtype=float),
            np.asarray(d["P0"], dtype=float),
            np.asarray(d["P1"], dtype=float),
            np.asarray(d["Ps"], dtype=float))


def run():
    soc, soccfg = makeProxy()

    banner("STEP 6 RESET STRATEGY -- what to do for a 2-3 day scan")
    print("  Two questions, one run:")
    print("    1. how far does a 3-point T1 vs flux sweep get in "
          f"{WALL_CLOCK_MIN:g} minutes, and")
    print("       how much does the answer wander when nothing is changed?")
    print("    2. how much does the 3-point T1 move when the reset threshold is")
    print("       deliberately WRONG?  That is drift, compressed into two minutes.")
    print("       If T1 barely moves, the threshold can be left alone for days and")
    print("       there is no reason to re-probe mid-run.")

    c = dict(BaseConfig)
    c["shots"] = c["reps"] = SS_SHOTS
    ss = SingleShot1Q(soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outerFolder,
                      suffix="Step6Strategy_SS", cfg=c, repeats=1,
                      confidence_threshold=SS_GROUND_THRESHOLD)
    ss.acquire(progress=False, plotDisp=False)
    calib_params = ss.calib_params
    print(f"\n  single-shot readout F = {ss.max_F:.4f}")
    plt.close("all")
    gc.collect()

    banner("STAGE 1 -- reset probe, judged on the floor rather than on F")
    probe = ActiveResetProbe(soc=soc, soccfg=soccfg, path=QUBIT,
                             outerFolder=outerFolder, suffix="Step6Strategy_Probe",
                             cfg=dict(BaseConfig, shots=PROBE_SHOTS, reps=PROBE_SHOTS,
                                      qubit_gain=int(BaseConfig["qubit_pi_gain"]),
                                      reset_max_iters=RESET_MAX_ITERS,
                                      reset_thermalization_us=THERMALIZATION_US))
    pdata = probe.acquire().get("data", {})
    raw = getattr(probe, "raw_shots", None)
    rec = pdata.get("recommended")
    if rec is None or raw is None:
        print("  probe found no usable feedback discrimination; nothing to test.")
        return
    oper = rec["oper"]
    gb = bool(rec["ground_below"])
    g_raw = np.asarray(raw["ground"][oper], dtype=np.int64)
    e_raw = np.asarray(raw["excited"][oper], dtype=np.int64)
    sep = float(abs(np.median(e_raw) - np.median(g_raw)))
    errs = pdata.get("raw_assignment_errors", {})
    floor0 = active_reset.reset_floor(errs.get("p_e_given_g", np.nan),
                                      errs.get("p_g_given_e", np.nan))
    print(f"  threshold_raw={rec['threshold_raw']} oper={oper} ground_below={gb}")
    print(f"  blob separation {sep:.0f}, F={pdata.get('raw_assignment_fidelity', np.nan):.3f}, "
          f"reset floor {floor0:.3f}")

    dc_all = fx.build_freq_uniform_dc_vec(DC_MIN, DC_MAX, FREQ_STEP_MHZ * 1e6,
                                          FLUX_FIT_PARAMS)
    pick = np.unique(np.linspace(0, len(dc_all) - 1, DC_POINTS).astype(int))
    dc_vec = dc_all[pick]
    f_ghz = fx.estimate_fit_frequency_ghz_array(FLUX_FIT_PARAMS, dc_vec)

    banner(f"STAGE 2 -- 3-point T1 vs flux, repeated for {WALL_CLOCK_MIN:g} min")
    print(f"  {len(dc_vec)} DC points, {SHOTS} shots, Ts = {Ts_US:g} us, "
          f"flux-matched references")
    cfg = build_cfg(dc_vec, SHOTS, rec)
    deadline = time.time() + WALL_CLOCK_MIN * 60.0
    reps = []
    t0 = time.time()
    while time.time() < deadline:
        ts = time.time()
        exp = run_3pt(soc, soccfg, cfg, dc_vec, SHOTS, calib_params,
                      "Step6Strategy_3pt")
        dt = time.time() - ts
        reps.append(summarize(exp))
        print(f"  repeat {len(reps)}: {dt:.1f} s  "
              f"({dt / max(len(dc_vec), 1):.2f} s per DC point)", flush=True)
        if time.time() + dt > deadline:
            break
    total = time.time() - t0
    if not reps:
        print("  no repeat finished inside the budget; lower DC_POINTS or SHOTS.")
        return
    T1s = np.vstack([r[0] for r in reps])
    per_dc = total / max(len(reps) * len(dc_vec), 1)
    print(f"\n  {len(reps)} full sweeps in {total:.0f} s -> {per_dc:.2f} s per DC point")
    print(f"  a {len(dc_all)}-point production sweep would take "
          f"{per_dc * len(dc_all) / 60:.1f} min per pass")

    print(f"\n  {'dc':>8s} {'f (GHz)':>9s} {'T1 mean':>9s} {'spread':>8s} {'n':>3s}")
    for i, dc in enumerate(dc_vec):
        col = T1s[:, i]
        good = np.isfinite(col)
        m = np.nanmean(col) if good.any() else np.nan
        s = np.nanstd(col) if good.sum() > 1 else np.nan
        print(f"  {dc:>8.0f} {f_ghz[i]:>9.4f} {m:>9.1f} {s:>8.1f} {int(good.sum()):>3d}")
    if len(reps) > 1:
        rel = np.nanmean(np.nanstd(T1s, axis=0) / np.abs(np.nanmean(T1s, axis=0)))
        print(f"\n  repeat-to-repeat scatter: {100 * rel:.1f}% of T1, with the reset")
        print(f"  settings held completely fixed.  Anything the threshold does to T1 in")
        print(f"  stage 3 has to beat this to matter.")

    banner("STAGE 3 -- deliberately detune the reset threshold (drift, compressed)")
    print("  The 3-point estimator is pe = (Ps-P0)/(P1-P0) with flux-matched references,")
    print("  so a reset residual that is the SAME in all three points cancels exactly.")
    print("  The question is whether it stays the same as the threshold walks off.")
    pick2 = np.unique(np.linspace(0, len(dc_vec) - 1, DETUNE_DC_POINTS).astype(int))
    dc2 = dc_vec[pick2]
    base_thr = int(rec["threshold_raw"])
    rows = []
    print(f"\n  T1 is reported PER FLUX POINT.  Averaging over flux points is")
    print(f"  meaningless here -- T1 genuinely runs {np.nanmax(np.nanmean(T1s, axis=0)):.0f}"
          f" -> {np.nanmin(np.nanmean(T1s, axis=0)):.0f} us across this range, so a flux")
    print(f"  average would just measure the flux dependence.")
    print(f"\n  {'detune':>8s} {'threshold':>10s} {'P(e|g)':>7s} {'P(g|e)':>7s} "
          f"{'floor':>7s} | " + "  ".join(f"dc={int(d):>5d}" for d in dc2))
    for frac in DETUNE_FRACTIONS:
        thr = int(round(base_thr + frac * sep))
        peg, pge = active_reset._threshold_rates(g_raw, e_raw, thr, gb)
        fl = active_reset.reset_floor(peg, pge)
        c2 = build_cfg(dc2, DETUNE_SHOTS, rec, threshold_override=thr)
        t1s = []
        for _ in range(DETUNE_REPEATS):
            exp = run_3pt(soc, soccfg, c2, dc2, DETUNE_SHOTS, calib_params,
                          "Step6Strategy_detune")
            t1s.append(summarize(exp)[0])
        arr = np.vstack(t1s)
        good = np.isfinite(arr)
        per_dc = np.nanmean(arr, axis=0)
        rows.append({"frac": frac, "thr": thr, "peg": peg, "pge": pge, "floor": fl,
                     "valid": int(good.sum()), "per_dc": per_dc})
        cells = "  ".join(f"{v:>7.1f}" if np.isfinite(v) else "    nan"
                          for v in per_dc)
        print(f"  {frac:>+8.2f} {thr:>10d} {peg:>7.3f} {pge:>7.3f} {fl:>7.3f} | "
              f"{cells}  ({good.sum():>2d}/{arr.size:<2d})", flush=True)

    banner("STAGE 4 -- interleave_rounds A/B (the biggest wall-clock lever)")
    print("  _interleaved_populations visits every spec once PER ROUND and builds a fresh")
    print("  FFT1Program each visit, so a pass is 3 x n_dc x rounds programs, each")
    print("  carrying only shots/rounds shots.  Per-program host overhead is paid every")
    print("  time.  The triplet is contiguous (group_size=3) so P0/P1/Ps drift-cancel")
    print("  WITHIN a triplet regardless of rounds; rounds only guards drift ACROSS a")
    print("  pass, which a multi-pass run already averages over.  The question is whether")
    print("  the pass-to-pass T1 scatter actually degrades when rounds is cut.")
    ab = {}
    for r_ in ROUNDS_AB:
        c = build_cfg(dc_vec, SHOTS, rec)
        c["interleave_rounds"] = int(r_)
        t1s, times = [], []
        for _ in range(ROUNDS_AB_PASSES):
            ts = time.time()
            exp = run_3pt(soc, soccfg, c, dc_vec, SHOTS, calib_params,
                          "Step6Strategy_rounds")
            times.append(time.time() - ts)
            t1s.append(summarize(exp)[0])
        ab[r_] = {"t1": np.vstack(t1s), "t": float(np.median(times))}
        print(f"  rounds={r_:>2d}: {np.median(times):.2f} s per {len(dc_vec)}-point pass "
              f"({3 * len(dc_vec) * r_} programs)", flush=True)
    if ab:
        base_t = ab[ROUNDS_AB[0]]["t"]
        print(f"\n  {'rounds':>7s} {'s/pass':>8s} {'speedup':>8s} {'335-pt pass':>12s} "
              f"{'T1 scatter':>11s} {'vs rounds=%d' % ROUNDS_AB[0]:>13s}")
        base_sc = None
        for r_ in ROUNDS_AB:
            arr = ab[r_]["t1"]
            sc = np.nanmean(np.nanstd(arr, axis=0) / np.abs(np.nanmean(arr, axis=0)))
            if base_sc is None:
                base_sc = sc
            scaled = ab[r_]["t"] * SWEEP_POINTS_PROD / max(len(dc_vec), 1) / 60.0
            print(f"  {r_:>7d} {ab[r_]['t']:>8.2f} {base_t / ab[r_]['t']:>7.2f}x "
                  f"{scaled:>11.2f}m {100 * sc:>10.1f}% {sc / max(base_sc, 1e-9):>12.2f}x")
        rel = 1.0 / np.sqrt(2 * (ROUNDS_AB_PASSES - 1)) / np.sqrt(max(len(dc_vec), 1))
        print(f"\n  each scatter is a std from {ROUNDS_AB_PASSES} passes averaged over "
              f"{len(dc_vec)} DC points,")
        print(f"  so each carries a relative uncertainty of about {rel:.2f}.  Judge the")
        print(f"  ratios against that, not against a fixed cutoff.")
        scs = {}
        for r_ in ROUNDS_AB:
            arr = ab[r_]["t1"]
            scs[r_] = float(np.nanmean(np.nanstd(arr, axis=0)
                                       / np.abs(np.nanmean(arr, axis=0))))
        b = scs[ROUNDS_AB[0]]
        safe = []
        print(f"\n  {'rounds':>7s} {'speedup':>8s} {'scatter ratio':>14s} {'sigma':>7s}")
        for r_ in ROUNDS_AB:
            d = scs[r_] - b
            de = np.hypot(scs[r_] * rel, b * rel)
            sig = abs(d) / max(de, 1e-9)
            print(f"  {r_:>7d} {base_t / ab[r_]['t']:>7.2f}x {scs[r_] / b:>13.2f}x "
                  f"{sig:>7.1f}")
            if sig < 2.0:
                safe.append(r_)
        if safe:
            pick = min(safe, key=lambda r_: ab[r_]["t"])
            print(f"\n  -> rounds={pick} is {base_t / ab[pick]['t']:.2f}x faster with a "
                  f"scatter ratio of {scs[pick] / b:.2f}x")
            print(f"     ({abs(scs[pick] - b) / max(np.hypot(scs[pick] * rel, b * rel), 1e-9):.1f} "
                  f"sigma -- no evidence of harm).  Set INTERLEAVE_ROUNDS = {pick}.")
            worse = [r_ for r_ in ROUNDS_AB if r_ not in safe]
            if worse:
                print(f"     rounds={min(worse)} is faster still but its scatter is "
                      f"{scs[min(worse)] / b:.2f}x, which does not clear 2 sigma.")
        else:
            print(f"\n  -> no reduction clears 2 sigma; keep rounds={ROUNDS_AB[0]}.")

    banner("VERDICT -- how to run active reset for 2-3 days")
    base = next((r for r in rows if r["frac"] == 0.0), None)
    ref_scatter = np.nanstd(T1s, axis=0)[pick2]
    if base is not None and len(rows) > 1:
        print(f"  For each flux point: how far does T1 move when the threshold is wrong,")
        print(f"  measured in units of the scatter that flux point already shows at FIXED")
        print(f"  settings?  Anything under ~2 sigma is not a threshold effect.")
        print(f"\n  {'dc':>8s} {'T1 @ nominal':>13s} {'fixed-setting':>14s} "
              f"{'worst detuned':>14s} {'shift':>8s}")
        print(f"  {'':>8s} {'(us)':>13s} {'scatter (us)':>14s} {'excursion (us)':>14s} "
              f"{'(sigma)':>8s}")
        worst_sigma = []
        for i, dc in enumerate(dc2):
            b = base["per_dc"][i]
            others = [r["per_dc"][i] for r in rows if r is not base]
            others = [v for v in others if np.isfinite(v)]
            if not np.isfinite(b) or not others or ref_scatter[i] <= 0:
                continue
            dev = max(others, key=lambda v: abs(v - b))
            sig = abs(dev - b) / ref_scatter[i]
            worst_sigma.append(sig)
            print(f"  {dc:>8.0f} {b:>13.1f} {ref_scatter[i]:>14.1f} {dev:>14.1f} "
                  f"{sig:>8.1f}")
        if worst_sigma:
            med = float(np.median(worst_sigma))
            fl = np.array([r["floor"] for r in rows])
            print(f"\n  the reset floor spans {np.nanmin(fl):.3f} -> {np.nanmax(fl):.3f} "
                  f"({np.nanmax(fl) / max(np.nanmin(fl), 1e-9):.1f}x) across this sweep")
            print(f"  median worst-case T1 shift: {med:.1f} sigma")
            if med < 2.0:
                print(f"\n  -> T1 is INSENSITIVE to the reset threshold.  The residual")
                print(f"     really does cancel in the ratio.  For the long run:")
                print(f"       * probe ONCE at the start and leave the threshold alone")
                print(f"       * do NOT re-probe between points -- re-probing injects a")
                print(f"         step change BETWEEN the three points of a triplet, which")
                print(f"         is the one thing that does NOT cancel")
                print(f"       * re-probe only if a health check shows the threshold has")
                print(f"         walked outside the blobs entirely")
            else:
                print(f"\n  -> T1 DOES move with the threshold at some flux points.")
                print(f"     Re-probe periodically, but always finish a triplet before")
                print(f"     changing anything.")
    print(f"\n  On the gates that stop active reset from firing:")
    print(f"    probe_reset_params used to refuse whenever raw F < 0.80 and whenever the")
    print(f"    residual exceeded a flat 0.2.  Today F = "
          f"{pdata.get('raw_assignment_fidelity', np.nan):.3f} and the floor alone is "
          f"{floor0:.3f},")
    print(f"    so both were within ~0.03 of aborting.  Over 2-3 days they WOULD have")
    print(f"    aborted, silently dropping you to passive relax and roughly 7x the")
    print(f"    wall-clock.  Both are now judged against the floor instead:")
    print(f"      * refuse only if the floor itself exceeds "
          f"{active_reset.MAX_USABLE_FLOOR:.2f}")
    print(f"      * refuse only if the reset sits more than "
          f"{active_reset.MAX_RESIDUAL_ABOVE_FLOOR:.2f} above its own floor")
    print(f"    A high floor with the loop converging is fine for the 3-point estimator.")
    print(f"    A loop that will not converge is not, and that is what is now tested.")

    banner("done -- paste the whole log back")


def main():
    with tee_log.tee("Step6ResetStrategy", folder=outerFolder):
        run()


if __name__ == "__main__":
    main()
