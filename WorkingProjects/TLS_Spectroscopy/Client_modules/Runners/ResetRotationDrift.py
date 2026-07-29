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

DURATION_MIN = 40.0
MIN_CYCLES = 8
MINI_SHOTS = 1500
ARM_SHOTS = 1200

ARM_ORDER = ("legacy_fixed", "legacy_retuned", "rot_fixed", "rot_tracked")


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


def wrap_delta_deg(angle, angle0):
    return float((float(angle) - float(angle0) + 180.0) % 360.0 - 180.0)


def slope_fit(x, y):
    coef, cov = np.polyfit(np.asarray(x, dtype=float), np.asarray(y, dtype=float),
                           1, cov=True)
    return float(coef[0]), float(cov[0][0])


def main():
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    with tee_log.tee(f"ResetRotationDrift_{stamp}", outerFolder):
        soc, soccfg = makeProxy()
        banner("ROTATED RESET vs LEGACY -- THE REPLACEMENT GAUNTLET, PART C: DRIFT")
        print("  The operational case for replacement.  The blob angle at FIXED res_phase")
        print("  wandered 6.6 to 26.2 deg across one night, costing up to 10 percent of")
        print("  separation.  The legacy scheme needs a separate phase calibration to fix")
        print("  that, and that calibration goes stale; the rotated scheme refits its angle")
        print("  from the same raw g/e data every probe, so it tracks drift by construction.")
        print(f"  Four arms, re-measured every cycle for {DURATION_MIN:g} min "
              f"(at least {MIN_CYCLES} cycles):")
        print("    legacy_fixed   -- legacy reset, calibrated once at the start")
        print("    legacy_retuned -- legacy threshold and quadrature refit every cycle from")
        print("                      fresh raw shots, the best the legacy architecture can")
        print("                      do without a phase calibration")
        print("    rot_fixed      -- rotated reset, calibrated once at the start")
        print("    rot_tracked    -- rotated reset refit every cycle, the intended")
        print("                      production mode")
        print(f"  Cost: 10 measurements per cycle (2 mini-calibration x {MINI_SHOTS} shots,")
        print(f"  4 arms x 2 preps x {ARM_SHOTS} shots), about 1.5 min per cycle;")
        print(f"  configured duration {DURATION_MIN:g} min.")

        c = dict(BaseConfig)
        c["shots"] = c["reps"] = SS_SHOTS
        ss = SingleShot1Q(soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outerFolder,
                          suffix="RotDrift_SS", cfg=c, repeats=1,
                          confidence_threshold=SS_GROUND_THRESHOLD)
        ss.acquire(progress=False, plotDisp=False)
        print(f"\n  single-shot readout F = {ss.max_F:.4f}")
        plt.close("all")
        gc.collect()

        banner("STAGE 0 -- one-time calibration: what the fixed arms hold on to all run")
        fit0 = bench.probe_and_fit(soc, soccfg, base_cfg(PROBE_SHOTS),
                                   RESET_MAX_ITERS, ETA_FALLBACK, path=QUBIT,
                                   outer_folder=outerFolder, suffix="RotDrift_Probe")
        if fit0 is None or fit0["old"] is None:
            print("  no usable calibration -- stopping.")
            return
        bench.print_fit(fit0)
        eta0 = float(fit0["eta"])
        angle0 = float(np.rad2deg(fit0["theta"]))
        print(f"  eta = {eta0:.2f} (probe-measured once, reused for every per-cycle refit)")
        print(f"  angle0 = {angle0:+.2f} deg -- all drift below is relative to this")

        banner(f"STAGE 1 -- four-arm drift watch ({DURATION_MIN:g} min, "
               f">= {MIN_CYCLES} cycles)")
        print("  Each cycle takes 2 mini-calibration measurements (g and e, no reset) and")
        print("  feeds those SAME raw shots to both the per-cycle refit and the population")
        print("  reference axis, so the mini-calibration doubles as the reference")
        print("  measurement and costs nothing extra.")
        print("  Angles are reported unwrapped about angle0, so a drift across +/-180 deg")
        print("  shows as a continuous column instead of a 360 deg jump.")
        print(f"\n  {'cyc':>4} {'min':>6} {'angle':>8} {'sep sgl':>8} {'sep rot':>8} "
              f"{'leg-fix':>8} {'leg-ret':>8} {'rot-fix':>8} {'rot-trk':>8}")
        t0 = time.time()
        cycles = 0
        fails = 0
        warned_retune = False
        rec = {"min": [], "angle": [], "delta": [], "sep_single": [], "sep_rot": []}
        res = {arm: {"g": [], "e": []} for arm in ARM_ORDER}
        while (time.time() - t0) < DURATION_MIN * 60.0 or cycles < MIN_CYCLES:
            lg, ug = bench.raw_final_shots(soc, soccfg, base_cfg(MINI_SHOTS),
                                           False, "none")
            le, ue = bench.raw_final_shots(soc, soccfg, base_cfg(MINI_SHOTS),
                                           True, "none")
            try:
                fit_t = bench.fit_from_raw(lg, ug, le, ue, RESET_MAX_ITERS, eta0)
            except RuntimeError as err:
                fails += 1
                print(f"  per-cycle refit failed ({err}) -- skipping this cycle",
                      flush=True)
                if fails > 20:
                    print("  too many refit failures -- ending the watch early")
                    break
                continue
            refs = rot.reference_axis(float(np.mean(lg)), float(np.mean(ug)),
                                      float(np.mean(le)), float(np.mean(ue)))
            fit_old_arm = fit_t
            if fit_t["old"] is None:
                if not warned_retune:
                    print("  a per-cycle legacy refit came back empty -- the retuned "
                          "legacy arm reuses the start-of-run fit on such cycles")
                    warned_retune = True
                fit_old_arm = fit0
            pairs = (("legacy_fixed", "old", fit0),
                     ("legacy_retuned", "old", fit_old_arm),
                     ("rot_fixed", "rot2", fit0),
                     ("rot_tracked", "rot2", fit_t))
            row = {}
            for arm, scheme, fit_a in pairs:
                cfg = bench.arm_cfg(base_cfg(ARM_SHOTS), scheme, fit_a)
                row[arm] = bench.measure_residuals(soc, soccfg, cfg, refs)
                res[arm]["g"].append(row[arm]["g"])
                res[arm]["e"].append(row[arm]["e"])
            elapsed_min = (time.time() - t0) / 60.0
            delta = wrap_delta_deg(np.rad2deg(fit_t["theta"]), angle0)
            angle = angle0 + delta
            rep_t = fit_t["report"]
            rec["min"].append(elapsed_min)
            rec["angle"].append(angle)
            rec["delta"].append(delta)
            rec["sep_single"].append(float(rep_t["sep_best_single"]))
            rec["sep_rot"].append(float(rep_t["sep_rotated"]))
            cycles += 1
            print(f"  {cycles:>4} {elapsed_min:6.1f} {angle:+8.2f} "
                  f"{rep_t['sep_best_single']:8.0f} {rep_t['sep_rotated']:8.0f} "
                  f"{row['legacy_fixed']['e']:8.4f} {row['legacy_retuned']['e']:8.4f} "
                  f"{row['rot_fixed']['e']:8.4f} {row['rot_tracked']['e']:8.4f}",
                  flush=True)

        banner("ANALYSIS -- what the run did, |e> branch primary")
        print(f"  {cycles} cycles in {(time.time() - t0) / 60.0:.1f} min "
              f"({fails} refit failures)")
        if cycles < 4:
            print("  fewer than 4 usable cycles -- nothing to fit, stopping without a "
                  "verdict.")
            return
        angles = np.asarray(rec["angle"], dtype=float)
        deltas = np.asarray(rec["delta"], dtype=float)
        gains = np.asarray(rec["sep_rot"], dtype=float) / np.asarray(rec["sep_single"],
                                                                     dtype=float)
        print(f"  angle span: {angles.min():+.2f} .. {angles.max():+.2f} deg "
              f"(span {angles.max() - angles.min():.2f} deg, max |deviation| from "
              f"angle0 {np.max(np.abs(deltas)):.2f} deg)")
        print(f"  rotated vs best-single separation gain: mean {np.mean(gains):.3f}x "
              f"(range {np.min(gains):.3f}x .. {np.max(gains):.3f}x)")
        for arm in ARM_ORDER:
            e = np.asarray(res[arm]["e"], dtype=float)
            g = np.asarray(res[arm]["g"], dtype=float)
            print(f"  arm {arm:<14} mean|e> {np.mean(e):7.4f}  worst|e> "
                  f"{np.max(e):7.4f}  mean|g> {np.mean(g):7.4f}  worst|g> "
                  f"{np.max(g):7.4f}")

        print("\n  criterion 1 -- tracked rotated vs the best retuned legacy:")
        print("  both arms recalibrate every cycle, so this compares the architectures")
        print("  with calibration freshness taken out of the question.")
        d = (np.asarray(res["legacy_retuned"]["e"], dtype=float)
             - np.asarray(res["rot_tracked"]["e"], dtype=float))
        mean_d = float(np.mean(d))
        sem_d = float(np.std(d, ddof=1) / np.sqrt(d.size))
        pass1 = mean_d > -0.01
        print(f"  paired d = legacy_retuned|e> - rot_tracked|e> = {mean_d:+.4f} "
              f"+/- {sem_d:.4f} over {d.size} cycles (needs > -0.01)")
        if mean_d > 0 and sem_d > 0:
            print(f"  rot_tracked is BETTER by {mean_d / sem_d:.1f} sigma (paired)")
        print(f"  -> {'PASS' if pass1 else 'FAIL'}")

        print("\n  criterion 2 -- staleness: residual growth per degree of angle drift:")
        print("  both fixed arms hold the start-of-run calibration while the angle")
        print("  wanders; a stale rotated calibration must degrade no faster than a")
        print("  stale legacy one.")
        x = np.abs(deltas)
        slope_leg, var_leg = slope_fit(x, res["legacy_fixed"]["e"])
        slope_rot, var_rot = slope_fit(x, res["rot_fixed"]["e"])
        allow = 2.0 * float(np.sqrt(var_rot + var_leg))
        pass2 = slope_rot <= slope_leg + allow
        print(f"  legacy_fixed slope {slope_leg:+.5f} +/- {np.sqrt(var_leg):.5f} "
              f"residual per deg")
        print(f"  rot_fixed    slope {slope_rot:+.5f} +/- {np.sqrt(var_rot):.5f} "
              f"residual per deg")
        print(f"  requirement: slope_rot <= slope_legacy + {allow:.5f}")
        print(f"  -> {'PASS' if pass2 else 'FAIL'}")

        print("\n  criterion 3 -- the drift protection actually realised:")
        worst_rt = float(np.max(res["rot_tracked"]["e"]))
        worst_lf = float(np.max(res["legacy_fixed"]["e"]))
        pass3 = worst_rt <= worst_lf
        print(f"  worst rot_tracked|e> {worst_rt:.4f} vs worst legacy_fixed|e> "
              f"{worst_lf:.4f}")
        print(f"  -> {'PASS' if pass3 else 'FAIL'}")

        banner("VERDICT -- replacement criteria, part C")
        print(f"  [{'PASS' if pass1 else 'FAIL'}] tracked rotated reset at least matches "
              f"the best retuned legacy (within 0.01)")
        print(f"  [{'PASS' if pass2 else 'FAIL'}] stale rotated calibration degrades no "
              f"faster with angle drift than stale legacy")
        print(f"  [{'PASS' if pass3 else 'FAIL'}] worst tracked-rotated residual never "
              f"exceeded worst stale-legacy residual")
        if pass1 and pass2 and pass3:
            print("\n  Part C passes.")
        else:
            print("\n  Part C does NOT pass -- send back this log before anything gets "
                  "replaced.")
        banner("done -- send back the .txt log")


if __name__ == "__main__":
    main()
