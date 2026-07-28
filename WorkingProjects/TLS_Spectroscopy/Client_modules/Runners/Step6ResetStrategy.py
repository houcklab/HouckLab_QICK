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

QUBIT = "q4"

WALL_CLOCK_MIN = 5.0
DC_POINTS = 8
SHOTS = 500
Ts_US = 60.0

DETUNE_FRACTIONS = [-0.20, -0.10, 0.0, 0.10, 0.20, 0.35]
DETUNE_DC_POINTS = 5
DETUNE_SHOTS = 500
DETUNE_REPEATS = 2

SS_SHOTS = 1000
SS_GROUND_THRESHOLD = 0.7
PROBE_SHOTS = 2000

INTERLEAVE_ROUNDS = 10
RANDOMIZE_POINT_ORDER = True
THERMALIZATION_US = 25.0
FEEDBACK_RELAX_US = 25.0
PASSIVE_BACKSTOP_US = 2000.0
RESET_MAX_ITERS = 3
MIN_REF_CONTRAST = 0.05
MAX_PLOT_T1_MULTIPLE = 20.0

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


def main():
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
    print(f"\n  {'detune':>8s} {'threshold':>10s} {'P(e|g)':>7s} {'P(g|e)':>7s} "
          f"{'floor':>7s} {'T1 mean':>9s} {'spread':>8s} {'valid':>6s}")
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
        m = np.nanmean(arr) if good.any() else np.nan
        s = np.nanstd(np.nanmean(arr, axis=0)) if good.any() else np.nan
        rows.append({"frac": frac, "thr": thr, "peg": peg, "pge": pge, "floor": fl,
                     "T1": m, "spread": s, "valid": int(good.sum()),
                     "per_dc": np.nanmean(arr, axis=0)})
        print(f"  {frac:>+8.2f} {thr:>10d} {peg:>7.3f} {pge:>7.3f} {fl:>7.3f} "
              f"{m:>9.1f} {s:>8.1f} {good.sum():>4d}/{arr.size:<3d}", flush=True)

    banner("VERDICT -- how to run active reset for 2-3 days")
    ok = [r for r in rows if np.isfinite(r["T1"])]
    if len(ok) >= 3:
        t1 = np.array([r["T1"] for r in ok])
        fl = np.array([r["floor"] for r in ok])
        base = next((r for r in ok if r["frac"] == 0.0), ok[len(ok) // 2])
        swing = (np.nanmax(t1) - np.nanmin(t1)) / max(abs(base["T1"]), 1e-9)
        floor_swing = np.nanmax(fl) / max(np.nanmin(fl), 1e-9)
        ref_scatter = (np.nanmean(np.nanstd(T1s, axis=0) / np.abs(np.nanmean(T1s, axis=0)))
                       if len(reps) > 1 else np.nan)
        print(f"  across the detuning range the reset floor changed by "
              f"{floor_swing:.1f}x ({np.nanmin(fl):.3f} -> {np.nanmax(fl):.3f})")
        print(f"  while the 3-point T1 moved by {100 * swing:.1f}%")
        if np.isfinite(ref_scatter):
            print(f"  against a repeat-to-repeat scatter of {100 * ref_scatter:.1f}% at "
                  f"fixed settings")
        if np.isfinite(ref_scatter) and swing <= 2.0 * ref_scatter:
            print(f"\n  -> T1 is INSENSITIVE to the reset threshold: the residual really")
            print(f"     does cancel in the ratio.  For the long run that means:")
            print(f"       * probe ONCE at the start and leave the threshold alone")
            print(f"       * do NOT re-probe between points -- re-probing injects step")
            print(f"         changes in the residual BETWEEN the three points of a")
            print(f"         triplet, which is the one thing that does NOT cancel")
            print(f"       * re-probe only if a periodic health check shows the threshold")
            print(f"         has walked outside the blobs entirely")
        else:
            print(f"\n  -> T1 DOES move with the threshold by more than the noise.")
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


if __name__ == "__main__":
    main()
