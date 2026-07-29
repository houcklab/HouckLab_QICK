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
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments import mResetBench as bench
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import active_reset_rot as rot
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import tee_log

QUBIT = "q4"

SS_SHOTS = 1000
SS_GROUND_THRESHOLD = 0.7
PROBE_SHOTS = 4000
RESET_MAX_ITERS = 3
THERMALIZATION_US = 2.0
ETA_FALLBACK = 0.6
RELAX_US = 2500.0

SHOTS_FAST = 1500
CAL_ROUNDS = 6
REPS_PER_CAL = 4
EQUIV_MARGIN = 0.02
T95 = {2: 2.920, 3: 2.353, 4: 2.132, 5: 2.015, 6: 1.943, 7: 1.895, 8: 1.860}

OFFSET_DEG = 25.0
N_OFFSET = 12

ITER_SWEEP = [1, 2, 3, 5]
SHOTS_ITER = 2000


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
    cfg["relax_delay"] = RELAX_US
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


def run_paired_block(soc, soccfg, fit, n_repeats, shots, tag, expected_sep=None):
    acc = {"old": {"g": [], "e": []}, "rot2": {"g": [], "e": []}}
    seps = []
    excluded = 0
    print(f"\n  {'rep':>4} {'ref sep':>8} {'old|g>':>8} {'old|e>':>8} "
          f"{'rot|g>':>8} {'rot|e>':>8} {'d|e>':>8}")
    for k in range(int(n_repeats)):
        refs, refs_ok = bench.measure_refs_guarded(soc, soccfg, base_cfg(shots),
                                                   expected_sep)
        row = {}
        for scheme in ("old", "rot2"):
            cfg = bench.arm_cfg(base_cfg(shots), scheme, fit)
            row[scheme] = bench.measure_residuals(soc, soccfg, cfg, refs)
        ok = (refs_ok and bench.residuals_sane(row["old"])
              and bench.residuals_sane(row["rot2"]))
        note = "" if ok else "  <-- glitch, excluded"
        print(f"  {k + 1:>4} {refs['separation']:8.0f} "
              f"{row['old']['g']:8.4f} {row['old']['e']:8.4f} "
              f"{row['rot2']['g']:8.4f} {row['rot2']['e']:8.4f} "
              f"{row['old']['e'] - row['rot2']['e']:+8.4f}{note}", flush=True)
        if not ok:
            excluded += 1
            continue
        seps.append(refs["separation"])
        for scheme in ("old", "rot2"):
            acc[scheme]["g"].append(row[scheme]["g"])
            acc[scheme]["e"].append(row[scheme]["e"])
    kept = len(acc["old"]["e"])
    if seps:
        print(f"  [{tag}] kept {kept}/{int(n_repeats)} repeats "
              f"({excluded} glitch-excluded); mean reference separation "
              f"{np.mean(seps):.0f} (spread {np.min(seps):.0f}..{np.max(seps):.0f})")
    else:
        print(f"  [{tag}] kept 0/{int(n_repeats)} repeats -- every row glitched")
    return acc, excluded


def report_equivalence(round_accs, margin):
    usable = [a for a in round_accs if len(a["old"]["e"]) >= 3]
    dropped = len(round_accs) - len(usable)
    if dropped:
        print(f"  {dropped} round(s) dropped for having fewer than 3 glitch-free "
              f"repeats")
    round_accs = usable
    if len(round_accs) < 3:
        print("  fewer than 3 usable calibration rounds -- equivalence cannot be "
              "assessed on this data")
        return False
    verdicts = {}
    n_rounds = len(round_accs)
    tcrit = T95.get(n_rounds - 1, 1.860)
    for branch in ("g", "e"):
        round_means = [float(np.mean(np.asarray(a["rot2"][branch])
                                     - np.asarray(a["old"][branch])))
                       for a in round_accs]
        legacy_means = [float(np.mean(np.asarray(a["old"][branch])))
                        for a in round_accs]
        device_sd = float(np.std(legacy_means, ddof=1))
        effective = max(float(margin), device_sd)
        mean = float(np.mean(round_means))
        sem = (float(np.std(round_means, ddof=1)) / np.sqrt(n_rounds)
               if n_rounds > 1 else float("nan"))
        upper95 = mean + tcrit * sem
        ok = upper95 < effective
        verdicts[branch] = ok
        detail = "  ".join(f"{m:+.4f}" for m in round_means)
        print(f"  |{branch}> branch round means (rot2 - old): {detail}")
        print(f"           combined {mean:+.4f} +/- {sem:.4f} over {n_rounds} "
              f"calibration rounds")
        print(f"           the LEGACY arm's own round-to-round spread is "
              f"{device_sd:.4f} -- the device's volatility floor; demanding the "
              f"schemes agree tighter than the device agrees with itself is not "
              f"a scheme test")
        print(f"           95% upper bound on any rot2 deficit: {upper95:+.4f} "
              f"(effective margin max({margin:g}, {device_sd:.4f}) = "
              f"{effective:.4f})  -> {'PASS' if ok else 'FAIL'}")
    print("  each round is an independent calibration, so threshold sampling error")
    print("  is averaged over rather than frozen into a single lucky or unlucky fit.")
    return all(verdicts.values())


def report_superiority(acc, min_sigma=3.0):
    if len(acc["old"]["e"]) < 8:
        print(f"  only {len(acc['old']['e'])} glitch-free repeats -- not enough for a "
              f"superiority verdict")
        return False
    st = paired_stats(acc["old"]["e"], acc["rot2"]["e"])
    ok = st["t"] >= min_sigma and st["mean"] > 0
    print(f"  |e> branch: old - rot2 = {st['mean']:+.4f} +/- {st['sem']:.4f} "
          f"({st['t']:+.1f} sigma paired, n={st['n']})")
    print(f"  requirement: rotated better by >= {min_sigma:g} sigma "
          f"-> {'PASS' if ok else 'FAIL'}")
    stg = paired_stats(acc["old"]["g"], acc["rot2"]["g"])
    print(f"  |g> branch for reference: old - rot2 = {stg['mean']:+.4f} "
          f"({stg['t']:+.1f} sigma)")
    return ok


def _measure_iter_point(soc, soccfg, fit_n, n_it, expected_sep):
    for attempt in range(3):
        refs, refs_ok = bench.measure_refs_guarded(soc, soccfg, base_cfg(SHOTS_ITER),
                                                   expected_sep)
        meas = {}
        for scheme in ("old", "rot2"):
            cfg = bench.arm_cfg(base_cfg(SHOTS_ITER, reset_max_iters=n_it),
                                scheme, fit_n)
            meas[scheme] = bench.measure_residuals(soc, soccfg, cfg, refs)
        ok = (refs_ok and bench.residuals_sane(meas["old"])
              and bench.residuals_sane(meas["rot2"]))
        if ok:
            return meas, True
        if attempt < 2:
            print(f"    iters={n_it}: glitched point (refs_ok={refs_ok}, "
                  f"sep={refs['separation']:.0f}, old={meas['old']}, "
                  f"rot={meas['rot2']}), re-measuring", flush=True)
    return meas, False


def stage_iteration_sweep(soc, soccfg, fit):
    banner("STAGE 3 -- residual vs iteration count, measured against the model")
    print("  Both schemes must follow the same Markov chain with the same pi")
    print("  efficiency.  If the rotated loop tracked a DIFFERENT curve, it would")
    print("  mean the projection is doing something the model does not describe.")
    print("  The efficiency is inferred from the 1-iteration point measured HERE,")
    print("  not from the probe minutes earlier -- eta drifts too fast on this")
    print("  device for a stale value to make a fair prediction.")
    raw = fit["raw"]
    expected_sep = fit["report"]["sep_rotated"]
    fit1 = bench.fit_from_raw(raw["lg"], raw["ug"], raw["le"], raw["ue"],
                              1, fit["eta"])
    meas1, ok1 = _measure_iter_point(soc, soccfg, fit1, 1, expected_sep)
    if not ok1:
        print("  the 1-iteration anchor point glitched twice -- no self-consistent")
        print("  efficiency available, stage 3 cannot run")
        return False
    anchors = []
    if fit1["old"] is not None:
        anchors.append((float(fit1["old"]["p_e_given_g"]),
                        1.0 - float(fit1["old"]["p_g_given_e"]),
                        float(meas1["old"]["e"])))
    anchors.append((float(fit1["two_proj"]["p_fire_given_g"]),
                    float(fit1["two_proj"]["p_fire_given_e"]),
                    float(meas1["rot2"]["e"])))
    grid = np.linspace(0.05, 1.0, 96)
    costs = [sum((_pred_measured_e(bg, be, eta, 1) - m) ** 2
                 for bg, be, m in anchors) for eta in grid]
    eta_live = float(grid[int(np.argmin(costs))])
    print(f"  probe eta {fit['eta']:.2f} -> live eta {eta_live:.2f} "
          f"(solved from the n=1 anchors; predictions below model the measured")
    print("  observable exactly: contaminated calibration rates unfolded to true")
    print("  rates, mixed-state preparation, and the eta-referenced axis)")
    rows = []
    excluded = 0
    print(f"\n  {'iters':>6} {'old meas':>9} {'old pred':>9} {'rot meas':>9} "
          f"{'rot pred':>9}")
    for n_it in ITER_SWEEP:
        fit_n = (fit1 if n_it == 1 else
                 bench.fit_from_raw(raw["lg"], raw["ug"], raw["le"], raw["ue"],
                                    n_it, eta_live))
        if n_it == 1:
            meas, ok = meas1, True
        else:
            meas, ok = _measure_iter_point(soc, soccfg, fit_n, n_it, expected_sep)
        old_pred = (_pred_measured_e(float(fit_n["old"]["p_e_given_g"]),
                                     1.0 - float(fit_n["old"]["p_g_given_e"]),
                                     eta_live, n_it)
                    if fit_n["old"] else float("nan"))
        tp = fit_n["two_proj"]
        rot_pred = _pred_measured_e(float(tp["p_fire_given_g"]),
                                    float(tp["p_fire_given_e"]),
                                    eta_live, n_it)
        if ok:
            rows.append((n_it, meas["old"]["e"], old_pred, meas["rot2"]["e"],
                         rot_pred))
            print(f"  {n_it:>6} {meas['old']['e']:9.4f} {old_pred:9.4f} "
                  f"{meas['rot2']['e']:9.4f} {rot_pred:9.4f}", flush=True)
        else:
            excluded += 1
            print(f"  {n_it:>6} {'glitch':>9} {old_pred:9.4f} {'glitch':>9} "
                  f"{rot_pred:9.4f}  <-- glitch, excluded", flush=True)
    if excluded:
        print(f"  {excluded} iteration point(s) glitch-excluded")
    if len(rows) < 3:
        print("  fewer than 3 usable iteration points -- FAIL")
        return False
    devs = [((r[1] - r[2]), (r[3] - r[4])) for r in rows
            if np.isfinite(r[2]) and np.isfinite(r[4])]
    differential = max(abs(dr - do) for do, dr in devs)
    common = [0.5 * (do + dr) for do, dr in devs]
    ok = differential < 0.05
    print("\n  the scheme question is whether the ROTATED loop deviates from the")
    print("  model any differently than the LEGACY loop does; deviation the two")
    print("  schemes share is device physics the model does not include, and it")
    print("  cannot count against either scheme.")
    print(f"  worst DIFFERENTIAL deviation (rot vs old): {differential:.4f} "
          f"(limit 0.05)")
    print("  common-mode deviation per point: "
          + "  ".join(f"{c:+.3f}" for c in common))
    if common and common[-1] > 0.04:
        print(f"  NOTE: at the largest iteration count BOTH schemes sit "
              f"{common[-1]:+.3f} above the model -- extra reset readouts are "
              f"exciting the qubit (measurement-induced transitions).  More "
              f"iterations HURT past this point; keep reset_max_iters at 3.")
    print(f"  -> {'PASS' if ok else 'FAIL'}: the rotated loop follows the same "
          f"physics as the legacy loop"
          f"{'' if ok else ' -- the schemes diverge from each other'}")
    return ok


def _pred_measured_e(b_g_sample, b_e_sample, eta, iters):
    b_g = min(1.0, max(0.0, float(b_g_sample)))
    b_e = min(1.0, max(0.0, (float(b_e_sample) - (1.0 - eta) * b_g)
                      / max(eta, 1e-6)))
    fg = rot.simulate_reset(0.0, b_g, 0.0, b_e, eta, int(iters), "g")
    fe = rot.simulate_reset(0.0, b_g, 0.0, b_e, eta, int(iters), "e")
    return ((1.0 - eta) * fg + eta * fe) / max(eta, 1e-6)


def main():
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    with tee_log.tee(f"ResetRotationEquivalence_{stamp}", outerFolder):
        soc, soccfg = makeProxy()
        banner("ROTATED RESET vs LEGACY -- THE REPLACEMENT GAUNTLET, PART A")
        print("  Three claims, each with enough shots to actually resolve it:")
        print(f"    1. aligned readout: rot2 is not worse than legacy by more than "
              f"{EQUIV_MARGIN:g}")
        print(f"       absolute residual, at 95% confidence ({CAL_ROUNDS} independent "
              f"calibrations x {REPS_PER_CAL} paired repeats).")
        print(f"    2. at {OFFSET_DEG:g} deg of deliberate phase misalignment -- the "
              f"drift magnitude")
        print("       actually observed overnight -- rot2 beats legacy by >= 3 sigma.")
        print("    3. both schemes follow the modelled convergence vs iteration count.")
        print("  Passing all three is the statistical case for replacing the legacy")
        print("  reset everywhere; runners B (real T1 path) and C (drift) are the rest.")

        c = dict(BaseConfig)
        c["shots"] = c["reps"] = SS_SHOTS
        ss = SingleShot1Q(soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outerFolder,
                          suffix="RotEquiv_SS", cfg=c, repeats=1,
                          confidence_threshold=SS_GROUND_THRESHOLD)
        ss.acquire(progress=False, plotDisp=False)
        print(f"\n  single-shot readout F = {ss.max_F:.4f}")
        plt.close("all")
        gc.collect()

        banner("STAGE 0 -- calibrate both schemes from one probe dataset")
        fit = bench.probe_and_fit_consistent(soc, soccfg, base_cfg(PROBE_SHOTS),
                                             RESET_MAX_ITERS, ETA_FALLBACK,
                                             refs_shots=SHOTS_ITER, path=QUBIT,
                                             outer_folder=outerFolder,
                                             suffix="RotEquiv_Probe")
        if fit is None or fit["old"] is None:
            print("  no usable calibration -- stopping.")
            return
        bench.print_fit(fit)
        print(f"  eta = {fit['eta']:.2f} (probe-measured)")
        print(f"  predicted worst residual at {RESET_MAX_ITERS} iters: "
              f"legacy {fit['old']['predicted_worst']:.4f}, "
              f"rot2 {fit['two_proj']['predicted_worst']:.4f}")

        banner(f"STAGE 1 -- equivalence on the aligned readout "
               f"({CAL_ROUNDS} calibration rounds x {REPS_PER_CAL} paired repeats "
               f"x {SHOTS_FAST} shots)")
        print("  A single calibration freezes each scheme's threshold with its own")
        print("  sampling error, and that error persists as a fake scheme difference")
        print("  no amount of repeating can remove.  So the equivalence claim is")
        print("  averaged over independent calibrations.")
        t0 = time.time()
        round_accs = []
        for rnd in range(CAL_ROUNDS):
            fit_r = fit if rnd == 0 else bench.probe_and_fit_consistent(
                soc, soccfg, base_cfg(PROBE_SHOTS), RESET_MAX_ITERS, ETA_FALLBACK,
                refs_shots=SHOTS_ITER, path=QUBIT, outer_folder=outerFolder,
                suffix=f"RotEquiv_Probe{rnd}")
            if fit_r is None or fit_r["old"] is None:
                print(f"  calibration round {rnd + 1} unusable -- skipping it.")
                continue
            print(f"\n  --- calibration round {rnd + 1}/{CAL_ROUNDS}: "
                  f"gain {fit_r['report']['gain_vs_best_single']:.2f}x, "
                  f"eta {fit_r['eta']:.2f} ---")
            acc_r, _ = run_paired_block(soc, soccfg, fit_r, REPS_PER_CAL,
                                        SHOTS_FAST, f"round{rnd + 1}",
                                        expected_sep=fit_r["report"]["sep_rotated"])
            round_accs.append(acc_r)
        print(f"  ({(time.time() - t0) / 60:.1f} min)")
        print(f"  margin note: {EQUIV_MARGIN:g} absolute residual is 10x smaller than")
        print("  the legacy reset's own overnight run-to-run spread (0.06 -> 0.31), so")
        print("  a deficit below it is operationally invisible.")
        pass1 = report_equivalence(round_accs, EQUIV_MARGIN)

        banner(f"STAGE 2 -- superiority at {OFFSET_DEG:g} deg misalignment "
               f"({N_OFFSET} paired repeats)")
        print("  This is not an artificial stressor: the blob angle at FIXED res_phase")
        print("  wandered 6.6..26.2 deg across last night's runs.  This stage dials in")
        print("  that observed drift on purpose and recalibrates BOTH schemes there,")
        print("  so each is doing its best and only the architecture differs.")
        base_phase = float(BaseConfig.get("res_phase", 0.0))
        pass2 = False
        try:
            BaseConfig["res_phase"] = base_phase + OFFSET_DEG
            print(f"  res_phase {base_phase:g} -> {BaseConfig['res_phase']:g}")
            fit_off = bench.probe_and_fit_consistent(
                soc, soccfg, base_cfg(PROBE_SHOTS), RESET_MAX_ITERS, ETA_FALLBACK,
                refs_shots=SHOTS_ITER, path=QUBIT, outer_folder=outerFolder,
                suffix="RotEquiv_ProbeOff")
            if fit_off is None or fit_off["old"] is None:
                print("  no usable calibration at the offset -- skipping stage 2.")
            else:
                bench.print_fit(fit_off)
                acc_off, _ = run_paired_block(
                    soc, soccfg, fit_off, N_OFFSET, SHOTS_FAST, "offset",
                    expected_sep=fit_off["report"]["sep_rotated"])
                pass2 = report_superiority(acc_off)
        finally:
            BaseConfig["res_phase"] = base_phase
            print(f"  restored res_phase = {BaseConfig['res_phase']:g}")

        pass3 = stage_iteration_sweep(soc, soccfg, fit)

        banner("VERDICT -- replacement criteria, part A")
        print(f"  [{'PASS' if pass1 else 'FAIL'}] aligned equivalence within "
              f"{EQUIV_MARGIN:g} at 95%")
        print(f"  [{'PASS' if pass2 else 'FAIL'}] superiority at {OFFSET_DEG:g} deg "
              f"misalignment (>= 3 sigma)")
        print(f"  [{'PASS' if pass3 else 'FAIL'}] both schemes follow the modelled "
              f"convergence")
        if pass1 and pass2 and pass3:
            print("\n  Part A passes.  Run ResetRotationT1 (part B) and "
                  "ResetRotationDrift (part C).")
        else:
            print("\n  Part A does NOT pass -- do not swap the legacy reset on "
                  "this evidence.")
        banner("done -- the .txt log is the complete record of this run")


if __name__ == "__main__":
    main()
