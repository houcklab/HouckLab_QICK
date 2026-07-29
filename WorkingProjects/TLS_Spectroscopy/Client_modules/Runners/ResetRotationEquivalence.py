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


def run_paired_block(soc, soccfg, fit, n_repeats, shots, tag):
    acc = {"old": {"g": [], "e": []}, "rot2": {"g": [], "e": []}}
    seps = []
    print(f"\n  {'rep':>4} {'ref sep':>8} {'old|g>':>8} {'old|e>':>8} "
          f"{'rot|g>':>8} {'rot|e>':>8} {'d|e>':>8}")
    for k in range(int(n_repeats)):
        refs = bench.measure_refs(soc, soccfg, base_cfg(shots))
        seps.append(refs["separation"])
        row = {}
        for scheme in ("old", "rot2"):
            cfg = bench.arm_cfg(base_cfg(shots), scheme, fit)
            row[scheme] = bench.measure_residuals(soc, soccfg, cfg, refs)
            acc[scheme]["g"].append(row[scheme]["g"])
            acc[scheme]["e"].append(row[scheme]["e"])
        print(f"  {k + 1:>4} {refs['separation']:8.0f} "
              f"{row['old']['g']:8.4f} {row['old']['e']:8.4f} "
              f"{row['rot2']['g']:8.4f} {row['rot2']['e']:8.4f} "
              f"{row['old']['e'] - row['rot2']['e']:+8.4f}", flush=True)
    print(f"  [{tag}] mean reference separation {np.mean(seps):.0f} "
          f"(spread {np.min(seps):.0f}..{np.max(seps):.0f})")
    return acc


def report_equivalence(round_accs, margin):
    verdicts = {}
    n_rounds = len(round_accs)
    tcrit = T95.get(n_rounds - 1, 1.860)
    for branch in ("g", "e"):
        round_means = [float(np.mean(np.asarray(a["rot2"][branch])
                                     - np.asarray(a["old"][branch])))
                       for a in round_accs]
        mean = float(np.mean(round_means))
        sem = (float(np.std(round_means, ddof=1)) / np.sqrt(n_rounds)
               if n_rounds > 1 else float("nan"))
        upper95 = mean + tcrit * sem
        ok = upper95 < margin
        verdicts[branch] = ok
        detail = "  ".join(f"{m:+.4f}" for m in round_means)
        print(f"  |{branch}> branch round means (rot2 - old): {detail}")
        print(f"           combined {mean:+.4f} +/- {sem:.4f} over {n_rounds} "
              f"calibration rounds")
        print(f"           95% upper bound on any rot2 deficit: {upper95:+.4f} "
              f"(margin {margin:g})  -> {'PASS' if ok else 'FAIL'}")
    print("  each round is an independent calibration, so threshold sampling error")
    print("  is averaged over rather than frozen into a single lucky or unlucky fit.")
    return all(verdicts.values())


def report_superiority(acc, min_sigma=3.0):
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


def stage_iteration_sweep(soc, soccfg, fit):
    banner("STAGE 3 -- residual vs iteration count, measured against the model")
    print("  Both schemes must follow the same Markov chain with the same pi")
    print("  efficiency.  If the rotated loop tracked a DIFFERENT curve, it would")
    print("  mean the projection is doing something the model does not describe.")
    raw = fit["raw"]
    rows = []
    print(f"\n  {'iters':>6} {'old meas':>9} {'old pred':>9} {'rot meas':>9} "
          f"{'rot pred':>9}")
    for n_it in ITER_SWEEP:
        fit_n = bench.fit_from_raw(raw["lg"], raw["ug"], raw["le"], raw["ue"],
                                   n_it, fit["eta"])
        refs = bench.measure_refs(soc, soccfg, base_cfg(SHOTS_ITER))
        meas = {}
        for scheme in ("old", "rot2"):
            cfg = bench.arm_cfg(base_cfg(SHOTS_ITER, reset_max_iters=n_it),
                                scheme, fit_n)
            meas[scheme] = bench.measure_residuals(soc, soccfg, cfg, refs)["e"]
        old_pred = fit_n["old"]["predicted_worst"] if fit_n["old"] else float("nan")
        tp = fit_n["two_proj"]
        rot_pred = rot.simulate_reset(0.0, tp["p_fire_given_g"], 0.0,
                                      tp["p_fire_given_e"], fit["eta"], n_it, "e")
        rows.append((n_it, meas["old"], old_pred, meas["rot2"], rot_pred))
        print(f"  {n_it:>6} {meas['old']:9.4f} {old_pred:9.4f} "
              f"{meas['rot2']:9.4f} {rot_pred:9.4f}", flush=True)
    dev_old = max(abs(r[1] - r[2]) for r in rows if np.isfinite(r[2]))
    dev_rot = max(abs(r[3] - r[4]) for r in rows if np.isfinite(r[4]))
    ok = dev_old < 0.08 and dev_rot < 0.08
    print(f"\n  worst model deviation: old {dev_old:.4f}, rot {dev_rot:.4f} "
          f"(limit 0.08, dominated by eta drift between probe and sweep)")
    print(f"  -> {'PASS' if ok else 'FAIL'}: both schemes "
          f"{'track' if ok else 'DO NOT track'} the predicted convergence")
    monotone_rot = all(b <= a + 0.03 for (_, _, _, a, _), (_, _, _, b, _)
                       in zip(rows, rows[1:]))
    print(f"  rotated residual is non-increasing in iters: "
          f"{'yes' if monotone_rot else 'NO -- investigate'}")
    return ok


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
        fit = bench.probe_and_fit(soc, soccfg, base_cfg(PROBE_SHOTS),
                                  RESET_MAX_ITERS, ETA_FALLBACK, path=QUBIT,
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
            fit_r = fit if rnd == 0 else bench.probe_and_fit(
                soc, soccfg, base_cfg(PROBE_SHOTS), RESET_MAX_ITERS, ETA_FALLBACK,
                path=QUBIT, outer_folder=outerFolder,
                suffix=f"RotEquiv_Probe{rnd}")
            if fit_r is None or fit_r["old"] is None:
                print(f"  calibration round {rnd + 1} unusable -- skipping it.")
                continue
            print(f"\n  --- calibration round {rnd + 1}/{CAL_ROUNDS}: "
                  f"gain {fit_r['report']['gain_vs_best_single']:.2f}x, "
                  f"eta {fit_r['eta']:.2f} ---")
            round_accs.append(run_paired_block(soc, soccfg, fit_r, REPS_PER_CAL,
                                               SHOTS_FAST, f"round{rnd + 1}"))
        print(f"  ({(time.time() - t0) / 60:.1f} min)")
        print(f"  margin note: {EQUIV_MARGIN:g} absolute residual is 10x smaller than")
        print("  the legacy reset's own overnight run-to-run spread (0.06 -> 0.31), so")
        print("  a deficit below it is operationally invisible.")
        pass1 = len(round_accs) >= 3 and report_equivalence(round_accs, EQUIV_MARGIN)

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
            fit_off = bench.probe_and_fit(soc, soccfg, base_cfg(PROBE_SHOTS),
                                          RESET_MAX_ITERS, ETA_FALLBACK,
                                          path=QUBIT, outer_folder=outerFolder,
                                          suffix="RotEquiv_ProbeOff")
            if fit_off is None or fit_off["old"] is None:
                print("  no usable calibration at the offset -- skipping stage 2.")
            else:
                bench.print_fit(fit_off)
                acc_off = run_paired_block(soc, soccfg, fit_off, N_OFFSET,
                                           SHOTS_FAST, "offset")
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
            print("\n  Part A does NOT pass -- send back this log before anything "
                  "gets replaced.")
        banner("done -- send back the .txt log")


if __name__ == "__main__":
    main()
