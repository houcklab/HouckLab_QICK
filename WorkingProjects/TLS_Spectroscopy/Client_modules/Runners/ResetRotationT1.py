import datetime
import gc
import time

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.socProxy import makeProxy
from WorkingProjects.TLS_Spectroscopy.Client_modules.Calib.initialize import BaseConfig, outerFolder
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mSingleShot1Q import SingleShot1Q
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mT1VsFlux import T13PointVsFlux
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments import mResetBench as bench
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import tee_log

QUBIT = "q4"

SS_SHOTS = 1000
SS_GROUND_THRESHOLD = 0.7
PROBE_SHOTS = 4000
RESET_MAX_ITERS = 3
THERMALIZATION_US = 2.0
ETA_FALLBACK = 0.6
FEEDBACK_RELAX_US = 25.0

INTERLEAVE_ROUNDS = 10
POINT_ORDER_SEED = None
DC_VEC = [0, 4000, 8000]
TS_US = 60.0
SHOTS_3PT = 2000
N_PASS_PAIRS = 4
MIN_REF_CONTRAST = 0.05
MAX_PLOT_T1_MULTIPLE = 20.0
FLUX_FIT_PARAMS = [9.30070052036, 0.100677145556, 31881.294671,
                   7115.71137189, 0.822636051338, -4.13273417292e-05]

SECONDS_PER_PASS = 40.0
P0_DIFF_LIMIT = 0.05
SHIFT_FRACTION = 0.25

HARVEST_KEYS = ("T1_3pt_us", "T1_3pt_valid_mask", "P0", "P1", "Ps",
                "ref_contrast_3pt")


def banner(text):
    print()
    print("=" * 96)
    print(text)
    print("=" * 96)


def base_cfg(shots, **extra):
    cfg = dict(BaseConfig)
    cfg["shots"] = cfg["reps"] = int(shots)
    cfg["reset_max_iters"] = int(RESET_MAX_ITERS)
    cfg["reset_thermalization_us"] = THERMALIZATION_US
    cfg.update(extra)
    return cfg


def paired_stats(a, b):
    d = np.asarray(a, dtype=float) - np.asarray(b, dtype=float)
    n = d.size
    mean = float(np.mean(d))
    sd = float(np.std(d, ddof=1)) if n > 1 else float("nan")
    sem = sd / np.sqrt(n) if n > 1 else float("nan")
    t = mean / sem if sem > 0 else float("nan")
    return {"mean": mean, "sd": sd, "sem": sem, "t": t, "n": n}


def legacy_arm_cfg(fit):
    cfg = dict(BaseConfig)
    cfg.update({
        "shots": int(SHOTS_3PT), "reps": int(SHOTS_3PT),
        "interleave_rounds": INTERLEAVE_ROUNDS,
        "randomize_point_order": True,
        "point_order_seed": POINT_ORDER_SEED,
        "ff_gain_vec": np.asarray(DC_VEC, dtype=float),
        "flux_fit_params": FLUX_FIT_PARAMS,
        "qubit_pulse_style": "arb",
        "three_point_matched_refs": True,
        "reset_mode": "feedback",
        "reset_threshold_raw": int(fit["old"]["threshold_raw"]),
        "reset_oper": str(fit["oper"]),
        "reset_ground_below": bool(fit["old"]["ground_below"]),
        "reset_max_iters": int(RESET_MAX_ITERS),
        "reset_thermalization_us": THERMALIZATION_US,
        "relax_delay": FEEDBACK_RELAX_US,
    })
    return cfg


def rot_arm_cfg(fit):
    cfg = legacy_arm_cfg(fit)
    cfg["rot_reset"] = bench.rot_reset_params(fit, RESET_MAX_ITERS)
    return cfg


def run_pass(soc, soccfg, cfg, calib_params, arm, pair):
    exp = T13PointVsFlux(
        soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outerFolder,
        suffix=f"RotT1_{arm}_pass{pair + 1}", cfg=dict(cfg),
        dc_vec=np.asarray(DC_VEC, dtype=float), Ts_ns=int(round(TS_US * 1e3)),
        shots=int(SHOTS_3PT), calib_params=calib_params, park_voltage=0,
        reset_mode="feedback", min_ref_contrast=MIN_REF_CONTRAST,
        max_plot_t1_multiple=MAX_PLOT_T1_MULTIPLE,
        run_park_T1_if_Ts_none=False, write_outputs=False)
    exp.acquire(progress=False)
    out = {k: np.asarray(exp.data[k], dtype=float) for k in HARVEST_KEYS}
    plt.close("all")
    gc.collect()
    return out


def print_pass_rows(pair, arm, out):
    for j, dc in enumerate(DC_VEC):
        print(f"  pass {pair + 1}/{int(N_PASS_PAIRS)} {arm:>6} dc {dc:>6.0f}"
              f"  T1 {out['T1_3pt_us'][j]:7.1f} us"
              f"  valid {int(out['T1_3pt_valid_mask'][j])}"
              f"  P0 {out['P0'][j]:.3f}  P1 {out['P1'][j]:.3f}"
              f"  Ps {out['Ps'][j]:.3f}"
              f"  contrast {out['ref_contrast_3pt'][j]:.3f}", flush=True)


def abort_on_register_pressure(arm, pair, exc):
    banner("REGISTER PRESSURE FAILURE -- the two programs do not coexist")
    print(f"  Building or acquiring the production T13PointVsFlux ({arm} arm, pass "
          f"{pair + 1}) raised ValueError.")
    print("  A register collision or scratch conflict occurred inside the production "
          "program:")
    print(f"    {exc}")
    print("  This is exactly the failure mode this runner exists to catch: the reset")
    print("  block's scratch registers or read timing clash with FFT1Program's own")
    print("  pulse registers.  Nothing was measured; do NOT trust any partial numbers")
    print("  above.")
    banner("VERDICT -- replacement criteria, part B")
    print("  [FAIL] the pass pairs could not complete inside the production program")
    print("\n  Part B does NOT pass -- send back this log before anything gets "
          "replaced.")
    banner("done -- send back the .txt log")


def analyze_and_judge(acc):
    banner("ANALYSIS -- per-flux-point T1, legacy vs rotated, inside the production "
           "path")
    T1 = {arm: np.vstack(acc[arm]["T1_3pt_us"]) for arm in ("legacy", "rot")}
    valid = {arm: np.vstack(acc[arm]["T1_3pt_valid_mask"]) for arm in ("legacy", "rot")}
    P0 = {arm: np.vstack(acc[arm]["P0"]) for arm in ("legacy", "rot")}
    n_pairs = T1["legacy"].shape[0]
    print(f"  {n_pairs} interleaved pass pairs; the paired differences cancel any slow")
    print("  drift that is common to both arms, which is why the arms alternate every")
    print("  pass instead of running in two blocks.")
    ok_shift = True
    worst = {"ratio": -np.inf, "diff": np.nan, "limit": np.nan, "dc": np.nan}
    worst_p0 = -np.inf
    for j, dc in enumerate(DC_VEC):
        tl = T1["legacy"][:, j]
        tr = T1["rot"][:, j]
        ml = float(np.mean(tl))
        mr = float(np.mean(tr))
        sl = float(np.std(tl, ddof=1)) if n_pairs > 1 else float("nan")
        sr = float(np.std(tr, ddof=1)) if n_pairs > 1 else float("nan")
        st = paired_stats(tl, tr)
        combined_sem = float(np.hypot(sl, sr)) / np.sqrt(n_pairs)
        pooled = float(np.mean(np.concatenate([tl, tr])))
        limit = max(2.0 * combined_sem, SHIFT_FRACTION * pooled)
        ok_dc = abs(st["mean"]) <= limit
        ok_shift = ok_shift and ok_dc
        ratio = abs(st["mean"]) / limit if limit > 0 else np.inf
        if ratio > worst["ratio"]:
            worst = {"ratio": ratio, "diff": st["mean"], "limit": limit, "dc": dc}
        dp0 = float(np.mean(np.abs(P0["legacy"][:, j] - P0["rot"][:, j])))
        worst_p0 = max(worst_p0, dp0)
        print(f"  dc {dc:+7.0f}: legacy T1 = {ml:6.1f} +/- {sl:5.1f} us | "
              f"rot T1 = {mr:6.1f} +/- {sr:5.1f} us")
        print(f"            paired diff (legacy - rot) {st['mean']:+7.1f} +/- "
              f"{st['sem']:5.1f} us (t {st['t']:+5.1f}, n {st['n']}) | "
              f"allowed {limit:6.1f} us -> {'ok' if ok_dc else 'SYSTEMATIC SHIFT'}")
        print(f"            mean |P0_legacy - P0_rot| = {dp0:.4f} "
              f"(same-reset-floor limit {P0_DIFF_LIMIT:g})")
    n_valid = int(np.sum(valid["legacy"] > 0.5) + np.sum(valid["rot"] > 0.5))
    n_total = int(valid["legacy"].size + valid["rot"].size)
    pass1 = n_valid == n_total
    pass2 = ok_shift
    pass3 = worst_p0 < P0_DIFF_LIMIT
    pass4 = True
    banner("VERDICT -- replacement criteria, part B")
    print(f"  [{'PASS' if pass1 else 'FAIL'}] every 3-point fit valid in both arms: "
          f"{n_valid}/{n_total} valid estimates")
    print(f"  [{'PASS' if pass2 else 'FAIL'}] no systematic T1 shift: worst |paired "
          f"mean diff| {abs(worst['diff']):.1f} us vs its {worst['limit']:.1f} us "
          f"allowance (dc {worst['dc']:+.0f}; allowance = max(2 x combined sem, "
          f"{SHIFT_FRACTION:g} x pooled mean T1))")
    print(f"  [{'PASS' if pass3 else 'FAIL'}] same reset floor: worst mean "
          f"|P0_legacy - P0_rot| = {worst_p0:.4f} (limit {P0_DIFF_LIMIT:g})")
    print(f"  [{'PASS' if pass4 else 'FAIL'}] the rotated block built and ran inside "
          f"the untouched production FFT1Program on all {n_pairs} passes -- no "
          f"register or scratch conflict was ever raised")
    if pass1 and pass2 and pass3 and pass4:
        print("\n  Part B passes.  The rotated reset is production-compatible AND "
              "physics-equivalent;")
        print("  run ResetRotationDrift (part C) to finish the gauntlet.")
    else:
        print("\n  Part B does NOT pass -- send back this log before anything gets "
              "replaced.")
    banner("done -- send back the .txt log")


def main():
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    with tee_log.tee(f"ResetRotationT1_{stamp}", outerFolder):
        soc, soccfg = makeProxy()
        banner("ROTATED RESET vs LEGACY -- THE REPLACEMENT GAUNTLET, PART B "
               "(REAL PRODUCTION T1 PATH)")
        print("  Purpose: prove the rotated reset works inside the REAL production T1")
        print("  path -- T13PointVsFlux building FFT1Program -- with ZERO changes to")
        print("  production code, via bench.patched_production_reset() dispatching on")
        print("  cfg['rot_reset'].  This is the test that catches register conflicts")
        print("  and timing interactions the dev bench cannot see, and it is the")
        print("  end-to-end physics deliverable: T1 measured with the rotated reset")
        print("  must agree with T1 measured with the legacy reset.")
        n_passes = 2 * int(N_PASS_PAIRS)
        est_min = (n_passes * SECONDS_PER_PASS + 120.0) / 60.0
        print(f"  time estimate: {n_passes} 3-point passes x ~{SECONDS_PER_PASS:.0f} s "
              f"each, plus single-shot calibration")
        print(f"  and the reset probe up front -- roughly {est_min:.0f} min total.")

        c = dict(BaseConfig)
        c["shots"] = c["reps"] = SS_SHOTS
        ss = SingleShot1Q(soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outerFolder,
                          suffix="RotT1_SS", cfg=c, repeats=1,
                          confidence_threshold=SS_GROUND_THRESHOLD)
        ss.acquire(progress=False, plotDisp=False)
        calib_params = ss.calib_params
        print(f"\n  single-shot readout F = {ss.max_F:.4f}")
        plt.close("all")
        gc.collect()

        banner("STAGE 0 -- calibrate BOTH schemes from one probe dataset")
        fit = bench.probe_and_fit(soc, soccfg, base_cfg(PROBE_SHOTS),
                                  RESET_MAX_ITERS, ETA_FALLBACK, path=QUBIT,
                                  outer_folder=outerFolder, suffix="RotT1_Probe")
        if fit is None:
            print("  no usable calibration at all -- stopping before wasting the T1 "
                  "passes.")
            return
        if fit["old"] is None:
            print("  the probe data gave no legacy threshold fit, so there is no "
                  "legacy arm to")
            print("  compare against -- stopping.")
            return
        bench.print_fit(fit)
        print(f"  eta = {fit['eta']:.2f} (probe-measured)")
        print(f"  legacy arm: threshold_raw={int(fit['old']['threshold_raw'])} "
              f"oper={fit['oper']} ground_below={bool(fit['old']['ground_below'])}")
        rr = bench.rot_reset_params(fit, RESET_MAX_ITERS)
        print(f"  rot arm:    c_int={rr['c_int']} s_int={rr['s_int']} "
              f"excite_threshold={rr['excite_threshold']:.0f} "
              f"max_iters={rr['max_iters']}")

        leg_cfg = legacy_arm_cfg(fit)
        rot_cfg = rot_arm_cfg(fit)
        print("\n  NOTE: the rot arm cfg KEEPS every legacy reset key "
              "(reset_threshold_raw,")
        print("  reset_oper, reset_ground_below) so the production code path is "
              "byte-identical;")
        print("  cfg['rot_reset'] is ALSO set, and the patched dispatcher overrides "
              "the legacy")
        print("  keys at emit time and plays the ROTATED block instead.  Remove "
              "'rot_reset' and")
        print("  the very same cfg runs the untouched legacy reset.")

        banner(f"STAGE 1 -- {int(N_PASS_PAIRS)} interleaved pass pairs through the "
               f"PRODUCTION T13PointVsFlux")
        print(f"  each pass: {len(DC_VEC)} flux points {DC_VEC}, Ts = {TS_US:g} us, "
              f"{int(SHOTS_3PT)} shots,")
        print(f"  {INTERLEAVE_ROUNDS} interleave rounds, matched references, feedback "
              f"reset, relax {FEEDBACK_RELAX_US:g} us.")
        acc = {arm: {k: [] for k in HARVEST_KEYS} for arm in ("legacy", "rot")}
        t0 = time.time()
        with bench.patched_production_reset():
            print("  ar.active_reset_block is now the dispatching wrapper; every other")
            print("  line of the production experiment is exactly what a real T1 "
                  "sweep runs.")
            for pair in range(int(N_PASS_PAIRS)):
                for arm, cfg_arm in (("legacy", leg_cfg), ("rot", rot_cfg)):
                    try:
                        out = run_pass(soc, soccfg, cfg_arm, calib_params, arm, pair)
                    except ValueError as exc:
                        abort_on_register_pressure(arm, pair, exc)
                        return
                    for k in HARVEST_KEYS:
                        acc[arm][k].append(out[k])
                    print_pass_rows(pair, arm, out)
        print(f"  ({(time.time() - t0) / 60:.1f} min for all passes)")
        analyze_and_judge(acc)


if __name__ == "__main__":
    main()
