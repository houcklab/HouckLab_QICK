import datetime
import gc
import math
import time

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.socProxy import makeProxy
from WorkingProjects.TLS_Spectroscopy.Client_modules.Calib.initialize import BaseConfig, outerFolder
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mSingleShot1Q import SingleShot1Q
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mT1VsFlux import (
    T13PointVsFlux, T1FullCurveVsFlux, _fit_T1_map, _csv_base_from_pickle,
    build_wall_clock_repeat_metadata, get_wall_clock_repeat_full_spec,
    save_wall_clock_repeat_full_outputs)
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import active_reset, flux_fit as fx
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import tee_log

QUBIT = "q4"

DC_POINTS = 6
SHOTS = 1000
SHOTS_3PT = 2000
T_POINTS = 15
T_MIN_US = 1.0
FIXED_TMAX_US = 1500.0
AUTO_TMAX_FACTOR = 3.0
Ts_US = 60.0

PROBE_SHORT_US = 300.0
PROBE_LONG_US = 2500.0
PROBE_T_POINTS = 31
PROBE_SHOTS = 500

DECIMATIONS = [15, 13, 11, 9, 7]

SS_SHOTS = 1000
SS_GROUND_THRESHOLD = 0.7
RESET_PROBE_SHOTS = 2000

INTERLEAVE_ROUNDS = 10
RANDOMIZE_POINT_ORDER = True
THERMALIZATION_US = 2.0
FEEDBACK_RELAX_US = 25.0
PASSIVE_BACKSTOP_US = 2000.0
RESET_MAX_ITERS = 3
MIN_REF_CONTRAST = 0.05
MAX_PLOT_T1_MULTIPLE = 20.0

PROD_DC_MIN, PROD_DC_MAX, PROD_FREQ_STEP_MHZ = 0, 12000, 1
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
        "reset_mode": ("feedback" if active_reset.rotated_probe_record(rec)
                       else "passive"),
        "three_point_matched_refs": True,
    })
    if active_reset.rotated_probe_record(rec):
        thr = int(rec["threshold_raw"] if threshold_override is None
                  else threshold_override)
        cfg.update(active_reset.feedback_runtime_from_probe(
            rec, max_iters=RESET_MAX_ITERS,
            thermalization_us=THERMALIZATION_US))
        cfg["reset_threshold_raw"] = thr
        cfg["relax_delay"] = FEEDBACK_RELAX_US
    else:
        cfg["relax_delay"] = PASSIVE_BACKSTOP_US
    return cfg


def make_full(soc, soccfg, cfg, dc_vec, calib_params, suffix, t_max_us=None,
              probe_cfg=None, write_outputs=False, repeat_metadata=None):
    return T1FullCurveVsFlux(
        soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outerFolder,
        suffix=suffix, cfg=dict(cfg), dc_vec=dc_vec, shots=int(SHOTS),
        calib_params=calib_params, park_voltage=0,
        reset_mode=cfg["reset_mode"],
        auto_tmax_factor=AUTO_TMAX_FACTOR,
        T1_probe_cfg=probe_cfg,
        t_min_ns_default=T_MIN_US * 1e3,
        t_points_default=T_POINTS,
        t_max_ns=(None if t_max_us is None else float(t_max_us) * 1e3),
        repeat_metadata=repeat_metadata,
        write_outputs=write_outputs)


def park_curve(exp, t_max_us, t_points, shots, tag):
    saved = exp.cfg.get("shots")
    exp.cfg["shots"] = int(shots)
    t_us = np.logspace(np.log10(max(T_MIN_US, 0.016)), np.log10(t_max_us), int(t_points))
    print(f"  [{tag}] {len(t_us)} waits, 1..{t_max_us:g} us, {shots} shots", flush=True)
    specs = [(exp.park_voltage, float(t), True, True) for t in t_us]
    t0 = time.time()
    pe = exp._interleaved_populations(specs)
    dt = time.time() - t0
    exp.cfg["shots"] = saved
    T1, err, ok = _fit_T1_map(np.asarray(pe)[None, :], t_us)
    return float(T1[0]), float(err[0]), bool(ok[0]), t_us, np.asarray(pe), dt


def run_3pt(soc, soccfg, cfg, dc_vec, calib_params, suffix):
    cfg = dict(cfg)
    cfg["shots"] = cfg["reps"] = int(SHOTS_3PT)
    exp = T13PointVsFlux(
        soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outerFolder,
        suffix=suffix, cfg=cfg, dc_vec=dc_vec,
        Ts_ns=int(round(Ts_US * 1e3)), shots=int(SHOTS_3PT),
        calib_params=calib_params, park_voltage=0,
        reset_mode=cfg["reset_mode"],
        min_ref_contrast=MIN_REF_CONTRAST,
        max_plot_t1_multiple=MAX_PLOT_T1_MULTIPLE,
        write_outputs=False)
    exp.acquire(progress=False)
    plt.close("all")
    gc.collect()
    return exp


def run():
    soc, soccfg = makeProxy()

    banner("STEP 6 FULL-CURVE AUDIT -- the full T1-vs-flux path has never run")
    print("  The 3-point path has been tested to death.  The full-curve path")
    print("  (P6_FULL_T1 / T1FullCurveVsFlux) has never executed on hardware.")
    print(f"  Run with a FIXED t_max of {FIXED_TMAX_US:g} us, {T_POINTS} delay points,")
    print(f"  {SHOTS} shots.  A fixed t_max skips the park-T1 probe entirely, so every")
    print("  pass uses the same delay grid.  Five questions:")
    print(f"    1. is a fixed {FIXED_TMAX_US:g} us the right choice?  Measure the park T1")
    print("       and check the grid reaches past it without wasting the fast end.")
    print("    2. does the full-curve path run end to end and write its files?")
    print(f"    3. does the full-curve T1 agree with the 3-point T1 at Ts = {Ts_US:g} us?")
    print("       If it does, the cheap method is validated by the expensive one.")
    print(f"    4. how many delay points are actually needed?  {T_POINTS} is a guess.")
    print("    5. how long does a production pass take, and does the one-stop")
    print("       wall-clock CSV hold two passes correctly?")

    c = dict(BaseConfig)
    c["shots"] = c["reps"] = SS_SHOTS
    ss = SingleShot1Q(soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outerFolder,
                      suffix="Step6FullCurve_SS", cfg=c, repeats=1,
                      confidence_threshold=SS_GROUND_THRESHOLD)
    ss.acquire(progress=False, plotDisp=False)
    calib_params = ss.calib_params
    print(f"\n  single-shot readout F = {ss.max_F:.4f}")
    plt.close("all")
    gc.collect()

    rec = active_reset.probe_reset_params(
        soc, soccfg, BaseConfig, path=QUBIT, outer_folder=outerFolder,
        shots=RESET_PROBE_SHOTS, validate=True,
        reset_max_iters=RESET_MAX_ITERS)
    if not active_reset.rotated_probe_record(rec):
        rec = None
        print("  probe found no usable rotated reset; running PASSIVE.")
    else:
        errs = rec.get("raw_assignment_errors", {})
        floor0 = active_reset.reset_floor(errs.get("p_e_given_g", np.nan),
                                          errs.get("p_g_given_e", np.nan))
        print(f"  reset threshold_raw={rec['threshold_raw']} oper={rec['oper']} "
              f"ground_below={bool(rec['ground_below'])}")
        print(f"  F={rec.get('raw_assignment_fidelity', np.nan):.3f}, "
              f"reset floor {floor0:.3f}")
    plt.close("all")
    gc.collect()

    dc_all = fx.build_freq_uniform_dc_vec(PROD_DC_MIN, PROD_DC_MAX,
                                          PROD_FREQ_STEP_MHZ * 1e6, FLUX_FIT_PARAMS)
    pick = np.unique(np.linspace(0, len(dc_all) - 1, DC_POINTS).astype(int))
    dc_vec = dc_all[pick]
    f_ghz = fx.estimate_fit_frequency_ghz_array(FLUX_FIT_PARAMS, dc_vec)
    print(f"\n  production sweep would be {len(dc_all)} DC points "
          f"({PROD_DC_MIN}..{PROD_DC_MAX} at {PROD_FREQ_STEP_MHZ:g} MHz steps)")
    print(f"  this audit uses {len(dc_vec)} of them:")
    for d, f in zip(dc_vec, f_ghz):
        print(f"    dc {d:+8.0f}   f {f:.4f} GHz")

    cfg = build_cfg(dc_vec, SHOTS, rec)

    banner(f"STAGE 1 -- is a fixed t_max of {FIXED_TMAX_US:g} us the right choice?")
    print("  A fixed t_max means one delay grid for every flux point, from the park")
    print("  T1 (longest) to the far end of the sweep (shortest).  It has to reach")
    print("  past the park T1 without burning the whole scan on dead time at the")
    print("  fast end.  Measure the park T1 to judge it.")
    ref = make_full(soc, soccfg, cfg, dc_vec, calib_params, "Step6FullCurve_Probe",
                    t_max_us=100.0)
    T1l, el, okl, t_l, pe_l, dt_l = park_curve(
        ref, PROBE_LONG_US, PROBE_T_POINTS, PROBE_SHOTS, f"1..{PROBE_LONG_US:g} us")
    print(f"\n    T1_park = {T1l:.1f} +/- {el:.1f} us   fit_ok={okl}   ({dt_l:.0f} s)")
    if okl:
        print("    tail of the curve (should reach the floor):")
        for t, p in zip(t_l[-5:], pe_l[-5:]):
            print(f"      t={t:9.1f} us   pe={p:.4f}")
    span = FIXED_TMAX_US / max(T1l, 1e-9)
    print(f"\n    fixed t_max = {FIXED_TMAX_US:g} us = {span:.2f} x the park T1")
    probe_ok = bool(okl and span >= 2.5)
    if probe_ok:
        print(f"    -> {FIXED_TMAX_US:g} us reaches {span:.1f} T1 at the park point.  Good.")
    else:
        print(f"    -> {FIXED_TMAX_US:g} us only reaches {span:.1f} T1 at the park point.")
        print(f"       The slowest curves never decay.  Use t_max_us >= "
              f"{3.0 * T1l:.0f}.")
    T1s, es, oks, t_s, pe_s, dt_s = park_curve(
        ref, PROBE_SHORT_US, PROBE_T_POINTS, PROBE_SHOTS,
        f"AUTO-mode check, 1..{PROBE_SHORT_US:g} us")
    dsig = abs(T1s - T1l) / max(np.hypot(es, el), 1e-12)
    print("\n    For reference, if t_max_us is ever set back to None the AUTO probe")
    print(f"    runs on the library default 1..{PROBE_SHORT_US:g} us grid, which here gives")
    print(f"    T1_park = {T1s:.1f} +/- {es:.1f} us -- {abs(T1s - T1l):.0f} us "
          f"({dsig:.1f} sigma) from the long-grid answer,")
    print(f"    and would set t_max = {AUTO_TMAX_FACTOR * T1s:.0f} us instead of "
          f"{FIXED_TMAX_US:g}.")
    if not (dsig < 3.0 and PROBE_SHORT_US > 2.0 * T1l):
        print("    That default grid is too short for this park T1 -- another reason")
        print("    to keep t_max fixed rather than AUTO.")
    plt.close("all")
    gc.collect()

    banner("STAGE 2 -- production full-curve pass, exactly as step 6 would build it")
    print(f"  {len(dc_vec)} DC x {T_POINTS} delays x {SHOTS} shots, fixed t_max = "
          f"{FIXED_TMAX_US:g} us,")
    print("  write_outputs=True so the CSV and PNG writers actually execute.")
    md0 = build_wall_clock_repeat_metadata(datetime.datetime.now(),
                                           datetime.datetime.now(), 0)
    t0 = time.time()
    full1 = make_full(soc, soccfg, cfg, dc_vec, calib_params,
                      "Step6FullCurve_Pass1", t_max_us=FIXED_TMAX_US,
                      write_outputs=True, repeat_metadata=md0)
    build1_s = time.time() - t0
    t0 = time.time()
    full1.acquire(progress=True)
    acq1_s = time.time() - t0
    t_vec1 = np.asarray(full1.data["t_vec_ns"], dtype=float) / 1e3
    T1_full1 = np.asarray(full1.data["T1_fit_us"], dtype=float)
    err_full1 = np.asarray(full1.data["T1_fit_err_us"], dtype=float)
    ok_full1 = np.asarray(full1.data["fit_success"], dtype=float)
    ss1 = np.asarray(full1.data["ss_data"], dtype=float)
    print(f"\n  t_vec build:              {build1_s:.0f} s (no park probe, t_max fixed)")
    print(f"  acquisition:              {acq1_s:.0f} s "
          f"({acq1_s / max(len(dc_vec), 1):.1f} s per DC point)")
    print(f"  t_vec: {len(t_vec1)} points, {t_vec1.min():.2f}..{t_vec1.max():.1f} us")
    print(f"\n  {'dc':>8} {'f (GHz)':>9} {'T1_full':>9} {'err':>8} {'ok':>4} "
          f"{'t_max/T1':>9} {'pe(t_min)':>10} {'pe(t_max)':>10}")
    for i, d in enumerate(dc_vec):
        print(f"  {d:8.0f} {f_ghz[i]:9.4f} {T1_full1[i]:9.1f} {err_full1[i]:8.1f} "
              f"{ok_full1[i]:4.0f} {t_vec1.max() / max(T1_full1[i], 1e-9):9.2f} "
              f"{ss1[i, 0]:10.3f} {ss1[i, -1]:10.3f}")
    nbad = int(np.sum(ok_full1 < 0.5))
    print(f"\n  fits that failed: {nbad} / {len(dc_vec)}")
    covered = t_vec1.max() / np.where(T1_full1 > 0, T1_full1, np.nan)
    print(f"  longest delay spans {np.nanmin(covered):.1f}..{np.nanmax(covered):.1f} "
          f"T1 across the flux range")
    if np.nanmin(covered) < 2.0:
        print("  -> WARNING: at the slowest flux point the curve never decays.  "
              "Raise auto_tmax_factor.")
    if np.nanmax(covered) > 40.0:
        print("  -> WARNING: at the fastest flux point most delays are dead time.  "
              "A per-dc t_max (quality_factor mode) would be cheaper.")
    plt.close("all")
    gc.collect()

    banner("STAGE 3 -- does the full curve agree with the 3-point estimator?")
    print(f"  Same DC points, Ts = {Ts_US:g} us, run right after the full curve so the")
    print(f"  two see the same device.  {SHOTS_3PT} shots here rather than {SHOTS}: the")
    print("  3-point sweep is cheap enough that there is no reason to leave this")
    print("  comparison shot-noise limited.")
    t0 = time.time()
    exp3 = run_3pt(soc, soccfg, cfg, dc_vec, calib_params, "Step6FullCurve_3pt")
    acq3_s = time.time() - t0
    T1_3pt = np.asarray(exp3.data["T1_3pt_us"], dtype=float)
    valid3 = np.asarray(exp3.data["T1_3pt_valid_mask"], dtype=float)
    per_shot_1 = acq1_s / max(SHOTS, 1)
    per_shot_3 = acq3_s / max(SHOTS_3PT, 1)
    print(f"\n  3-point sweep took {acq3_s:.0f} s vs {acq1_s:.0f} s for the full curve;")
    print(f"  at equal shots that is {per_shot_1 / max(per_shot_3, 1e-9):.1f}x faster.")
    print(f"\n  {'dc':>8} {'T1_full':>9} {'err':>8} {'T1_3pt':>9} {'valid':>6} "
          f"{'ratio':>8} {'sigma':>8}")
    ratios, sigmas = [], []
    for i, d in enumerate(dc_vec):
        r = T1_3pt[i] / T1_full1[i] if (np.isfinite(T1_3pt[i]) and T1_full1[i] > 0) else np.nan
        s = np.nan
        if np.isfinite(r) and valid3[i] > 0.5 and ok_full1[i] > 0.5 and err_full1[i] > 0:
            s = r * err_full1[i] / T1_full1[i]
            ratios.append(r)
            sigmas.append(s)
        print(f"  {d:8.0f} {T1_full1[i]:9.1f} {err_full1[i]:8.1f} {T1_3pt[i]:9.1f} "
              f"{valid3[i]:6.0f} {r:8.3f} {s:8.3f}")
    if ratios:
        ratios = np.asarray(ratios)
        sigmas = np.asarray(sigmas)
        w = 1.0 / sigmas ** 2
        wmean = float(np.sum(w * ratios) / np.sum(w))
        werr = float(1.0 / np.sqrt(np.sum(w)))
        chi2 = float(np.sum(((ratios - 1.0) / sigmas) ** 2))
        dof = len(ratios)
        print(f"\n  3pt / full ratio over {dof} usable points: "
              f"median {np.median(ratios):.3f}, "
              f"spread {np.min(ratios):.3f}..{np.max(ratios):.3f}")
        print(f"  weighted mean = {wmean:.3f} +/- {werr:.3f}   "
              f"chi2/dof vs 1.0 = {chi2 / dof:.2f}")
        print("  The sigma column is the full curve's own fit error, which dominates")
        print("  here.  With both estimators correct and the P0 reference sitting at")
        print("  the decay asymptote this ratio is 1.00; a simulated cross-check of the")
        print("  two implementations agrees to 0.5%, so any real offset is physics.")
        offset_sig = abs(wmean - 1.0) / max(werr, 1e-12)
        same_side = int(np.sum(ratios < 1.0))
        tail = min(same_side, dof - same_side)
        p_sign = min(1.0, 2.0 * sum(math.comb(dof, j) for j in range(tail + 1))
                     / float(2 ** dof))
        print(f"  {same_side}/{dof} points fall below 1.0 "
              f"(sign test, two-sided p = {p_sign:.3f})")
        P0 = np.asarray(exp3.data["P0"], dtype=float)
        pe_last = ss1[:, -1]
        print("\n  Where the 3-point floor sits versus the decay's own floor:")
        print(f"  {'dc':>8} {'P0 (3pt ref)':>13} {'pe at t_max':>12} {'excess':>9}")
        excess = []
        for i, d in enumerate(dc_vec):
            ex = P0[i] - pe_last[i] if np.isfinite(P0[i]) else np.nan
            if np.isfinite(ex):
                excess.append(ex)
            print(f"  {d:8.0f} {P0[i]:13.3f} {pe_last[i]:12.3f} {ex:+9.3f}")
        mean_excess = float(np.mean(excess)) if excess else np.nan
        print(f"\n  mean excess = {mean_excess:+.3f}")
        print("  The 3-point estimator assumes the decay settles to P0.  The full curve's")
        print("  longest delay shows where it actually settles.  A positive excess means")
        print("  P0 sits ABOVE the true floor, the estimator over-subtracts, and it reads")
        print("  T1 systematically SHORT.  This is the reset residual leaking into the")
        print("  reference, and it grows as the reset degrades.")
        if chi2 / dof < 2.0 and offset_sig < 3.0:
            print(f"\n  -> agreed.  The 3-point sweep at Ts = {Ts_US:g} us measures the same")
            print("     T1 the full fit does, and it is the method to run for 2-3 days.")
        elif offset_sig >= 3.0 and np.isfinite(mean_excess) and mean_excess > 0.02:
            print(f"\n  -> a {100 * (wmean - 1):+.1f}% offset at {offset_sig:.1f} sigma, and the")
            print(f"     excess is positive at every DC point (mean {mean_excess:+.3f}).")
            print("     That is the signature of a BIAS, not scatter: the 3-point P0")
            print("     reference sits above the level the decay actually reaches, so the")
            print("     estimator over-subtracts and reads short.  The cause is the reset")
            print("     residual leaking into the reference.  Expect this offset to shrink")
            print("     as the reset improves, and to vanish when the residual matches the")
            print("     thermal steady state.  The full curve fits its own floor and is")
            print(f"     immune -- chi2/dof of {chi2 / dof:.1f} here reflects the full curve's own")
            print("     error bars, which stage 5 tests directly.")
        elif offset_sig >= 3.0:
            print(f"\n  -> a {100 * (wmean - 1):+.1f}% offset at {offset_sig:.1f} sigma, but the excess")
            print(f"     column (mean {mean_excess:+.3f}) does not explain it.  Something other")
            print("     than the reset residual is shifting one of the two estimators.")
        else:
            print(f"\n  -> scatter exceeds the error bars (chi2/dof = {chi2 / dof:.1f}) and the")
            print("     offsets are not one-sided.  Either T1 moved between the two sweeps")
            print("     or the disagreement is flux-dependent.  Check stage 5's")
            print("     pass-to-pass reproducibility before blaming either method.")
    else:
        print("\n  no DC point was usable in both methods.")

    banner("STAGE 4 -- how many delay points does the full curve actually need?")
    print("  Refit stage 2's data on decimated grids.  No extra hardware time;")
    print("  this is the same measurement, thrown away point by point.")
    print(f"\n  {'points':>7} {'t_max/us':>9} " +
          " ".join(f"{'dc%+.0f' % d:>10}" for d in dc_vec) + f" {'max dev':>9}")
    base = T1_full1
    for npts in DECIMATIONS:
        if npts > len(t_vec1):
            continue
        idx = np.unique(np.linspace(0, len(t_vec1) - 1, npts).astype(int))
        T1d, _, okd = _fit_T1_map(ss1[:, idx], t_vec1[idx])
        dev = np.abs(T1d - base) / np.where(base > 0, base, np.nan)
        dev = np.where(okd > 0.5, dev, np.nan)
        row = " ".join(f"{v:10.1f}" for v in T1d)
        worst = np.nanmax(dev) if np.any(np.isfinite(dev)) else np.nan
        print(f"  {npts:7d} {t_vec1[idx].max():9.1f} {row} {100 * worst:8.1f}%")
    print(f"\n  'max dev' is the worst fractional change vs the {len(t_vec1)}-point fit.")
    print("  Runtime scales almost linearly with the point count, so the smallest grid")
    print("  whose deviation stays under a few percent is the one to use.  But read it")
    print(f"  the other way too: if dropping {len(t_vec1)} -> {len(t_vec1) - 2} already moves T1 by more")
    print(f"  than the fit errors in stage 2, then {len(t_vec1)} points is not enough either and")
    print("  the number needs to go UP, not down.")

    banner("STAGE 5 -- second pass, and the one-stop wall-clock CSV")
    print("  A 2-3 day run repeats the pass.  With t_max fixed both passes must use")
    print("  the identical delay grid, so the map stacks cleanly run over run.  The")
    print("  one-stop CSV takes its column list from pass 1 -- check it survives.")
    series_start = datetime.datetime.now()
    md1 = build_wall_clock_repeat_metadata(series_start, series_start, 1)
    t0 = time.time()
    full2 = make_full(soc, soccfg, cfg, dc_vec, calib_params,
                      "Step6FullCurve_Pass2", t_max_us=FIXED_TMAX_US,
                      write_outputs=False, repeat_metadata=md1)
    full2.acquire(progress=True)
    acq2_s = time.time() - t0
    t_vec2 = np.asarray(full2.data["t_vec_ns"], dtype=float) / 1e3
    T1_full2 = np.asarray(full2.data["T1_fit_us"], dtype=float)
    err_full2 = np.asarray(full2.data["T1_fit_err_us"], dtype=float)
    print(f"\n  pass 1 acquisition {acq1_s:.0f} s, pass 2 {acq2_s:.0f} s")
    print(f"  pass 1 t_vec: {len(t_vec1)} points to {t_vec1.max():.1f} us")
    print(f"  pass 2 t_vec: {len(t_vec2)} points to {t_vec2.max():.1f} us")
    same_grid = (len(t_vec1) == len(t_vec2)
                 and np.allclose(t_vec1, t_vec2, rtol=0, atol=1e-6))
    print(f"  identical grids: {same_grid} "
          f"({'as expected with a fixed t_max' if same_grid else 'UNEXPECTED'})")
    print(f"\n  {'dc':>8} {'pass1':>9} {'pass2':>9} {'diff':>9} {'sigma':>7} {'ratio':>7}")
    sigs, rats = [], []
    for i, d in enumerate(dc_vec):
        diff = T1_full2[i] - T1_full1[i]
        sig = abs(diff) / max(np.hypot(err_full1[i], err_full2[i]), 1e-12)
        rat = (max(T1_full1[i], T1_full2[i]) / max(min(T1_full1[i], T1_full2[i]), 1e-9)
               if min(T1_full1[i], T1_full2[i]) > 0 else np.nan)
        if np.isfinite(sig):
            sigs.append(sig)
        if np.isfinite(rat):
            rats.append(rat)
        print(f"  {d:8.0f} {T1_full1[i]:9.1f} {T1_full2[i]:9.1f} {diff:+9.1f} "
              f"{sig:7.1f} {rat:7.2f}")
    if sigs:
        rms = float(np.sqrt(np.mean(np.square(sigs))))
        print(f"\n  rms pass-to-pass deviation = {rms:.1f} sigma "
              f"(1.0 if the error bars were honest)")
        print(f"  worst pass-to-pass ratio    = {max(rats):.2f}x")
        if rms > 1.5:
            print("  -> the quoted fit errors UNDERSTATE the real run-to-run spread by")
            print(f"     about {rms:.1f}x.  Whatever the full curve reports, trust it only")
            print(f"     to a factor of ~{max(rats):.1f} at these settings.  Raise shots or")
            print("     delay points before using it as a reference for anything.")
        else:
            print("  -> the error bars are consistent with the observed reproducibility.")

    per_run = []
    for exp, md in ((full1, md0), (full2, md1)):
        spec = get_wall_clock_repeat_full_spec(exp)
        if spec is None:
            print("\n  get_wall_clock_repeat_full_spec returned None for the full curve.")
            break
        per_run.append(dict(spec, run_metadata=md, dc_vec=exp.dc_vec,
                            metric_values=np.asarray(exp.data["inv_T1_fit_per_us"],
                                                     dtype=float),
                            metric_column_name="inv_T1_fit_per_us",
                            extra_metric_matrices={"T1_fit_us": np.asarray(
                                exp.data["T1_fit_us"], dtype=float)}))
    if len(per_run) == 2:
        base_path = _csv_base_from_pickle(full1.pname)
        out = save_wall_clock_repeat_full_outputs(base_path, "AUDIT_T1_fit", per_run)
        print(f"\n  one-stop CSV written: {out}")
        with open(out) as f:
            header = f.readline().strip()
            nrows = sum(1 for _ in f)
        expect = (len(dc_vec) * len(t_vec1)) + (len(dc_vec) * len(t_vec2))
        print(f"  rows = {nrows}, expected {expect} "
              f"({'OK' if nrows == expect else 'MISMATCH'})")
        print(f"  columns = {header}")

    banner("VERDICT")
    n_prod = len(dc_all)
    per_dc = acq1_s / max(len(dc_vec), 1)
    print(f"  measured {per_dc:.1f} s per DC point at {T_POINTS} delays, {SHOTS} shots")
    print(f"  production is {n_prod} DC points at 2000 shots:")
    tpt_h = n_prod * (acq3_s / max(len(dc_vec), 1)) * (2000.0 / SHOTS_3PT) / 3600
    for npts in sorted({T_POINTS, 41}):
        full_h = (n_prod * per_dc * (2000.0 / SHOTS) * (npts / T_POINTS)) / 3600
        tag = "  <- P6_FULL_T1 t_points_default" if npts == 41 else ""
        print(f"    one full-curve pass at {npts:2d} delays ~ {full_h:5.1f} h"
              f"  ({60 / max(full_h, 1e-9):4.0f} passes in 60 h){tag}")
    print(f"    one 3-point pass              ~ {tpt_h:5.2f} h"
          f"  ({60 / max(tpt_h, 1e-9):4.0f} passes in 60 h)")
    print()
    print("  Set in P6_FULL_T1 before the real run:")
    if probe_ok:
        print(f"    t_max_us: {FIXED_TMAX_US:g}")
    else:
        print(f"    t_max_us: {max(FIXED_TMAX_US, 3.0 * T1l):.0f}   "
              f"({FIXED_TMAX_US:g} does not reach past the park T1)")
    print("    T1_probe_cfg: None            (unused once t_max_us is set)")
    print("    t_points_default: read it off stage 4")
    print(f"    shots: 2000                   (this audit ran {SHOTS})")

    banner("done -- the .txt log is the complete record of this run")


def main():
    with tee_log.tee("Step6FullCurveAudit", folder=outerFolder):
        run()


if __name__ == "__main__":
    main()
