import time

import numpy as np

from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.socProxy import makeProxy
from WorkingProjects.TLS_Spectroscopy.Client_modules.Calib.initialize import BaseConfig
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mActiveResetProbe import (
    ReadProbeProgram, ResetCheckProgram,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import active_reset as ar

QUBIT = "q4"

MONITOR_MINUTES = 6.0
PHASE_CAL_AT_START = True
PHASE_CAL_AT_END = True
PHASE_SWEEP_DEG = list(range(0, 180, 15))
PHASE_SHOTS = 400

REF_SHOTS = 600
GATE_SHOTS = 800
REF_RELAX_US = 2000.0
GATE_RELAX_US = 25.0

RESET_MAX_ITERS = 3
RESET_PI_EFFICIENCY = 0.8
RESET_THERMALIZATION_US = 2.0
RESET_MEAS_SYNCDELAY_US = 4.0
RESET_READ_DELAY_US = 2.0

GATE_LIMIT = 0.2


def banner(text):
    print()
    print("=" * 96)
    print(text)
    print("=" * 96)


def fit_threshold(ground, excited):
    return ar.fit_reset_threshold(ground, excited, iters=RESET_MAX_ITERS,
                                  pi_efficiency=RESET_PI_EFFICIENCY)


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
            "lower": np.asarray(prog.di_buf[0], dtype=np.int64).ravel(),
            "upper": np.asarray(prog.dq_buf[0], dtype=np.int64).ravel(),
        }
    return out


def purity_of(ref):
    sep_lo = abs(np.median(ref["e"]["lower"]) - np.median(ref["g"]["lower"]))
    sep_up = abs(np.median(ref["e"]["upper"]) - np.median(ref["g"]["upper"]))
    oper = "lower" if sep_lo >= sep_up else "upper"
    return oper, max(sep_lo, sep_up) / (sep_lo + sep_up + 1e-9), max(sep_lo, sep_up)


def calibrate_phase(soc, soccfg, cfg, tag):
    print(f"  [{tag}] phase sweep ...")
    best = None
    for ph in PHASE_SWEEP_DEG:
        c = dict(cfg)
        c["res_phase"] = float(ph)
        ref = ge_reference(soc, soccfg, c, PHASE_SHOTS)
        oper, pur, sep = purity_of(ref)
        if best is None or (pur, sep) > (best[1], best[2]):
            best = (float(ph), pur, sep, oper)
    print(f"  [{tag}] best res_phase = {best[0]:.1f} deg  purity {best[1]:.2f}  "
          f"sep {best[2]:.0f}  oper '{best[3]}'")
    return best


def make_projector(ref):
    Ig, Qg = ref["g"]["I"], ref["g"]["Q"]
    dx, dy = ref["e"]["I"] - Ig, ref["e"]["Q"] - Qg
    denom = dx * dx + dy * dy

    def project(Ir, Qr):
        return (((Ir - Ig) * dx + (Qr - Qg) * dy) / denom) if denom > 0 else float("nan")
    return project


def residual(soc, soccfg, cfg, project, prep_excited, threshold, ground_below, oper):
    c = dict(cfg)
    c["reps"] = c["shots"] = int(GATE_SHOTS)
    c["prep_excited"] = bool(prep_excited)
    c["do_reset"] = True
    c["reset_threshold_raw"] = int(threshold)
    c["reset_ground_below"] = bool(ground_below)
    c["reset_oper"] = str(oper)
    c["reset_max_iters"] = RESET_MAX_ITERS
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

    banner("RESET STABILITY MONITOR")
    print(f"  watching for {MONITOR_MINUTES:g} min.  Each cycle re-measures the |g>/|e>")
    print(f"  blobs, re-derives the threshold, and runs the gate TWICE:")
    print(f"    fresh  = threshold re-derived this cycle")
    print(f"    stale  = threshold frozen from cycle 0")
    print(f"  If 'stale' degrades while 'fresh' holds, the threshold is going stale and")
    print(f"  re-probing more often fixes it.  If BOTH degrade, the reset/readout itself")
    print(f"  is drifting and no amount of re-probing will help.")

    if PHASE_CAL_AT_START:
        ph0 = calibrate_phase(soc, soccfg, cfg, "start")
        cfg["res_phase"] = ph0[0]
    else:
        ph0 = None

    rows = []
    frozen = None
    t0 = time.time()
    deadline = t0 + MONITOR_MINUTES * 60.0
    print(f"\n  {'t(s)':>6s} {'g_raw':>8s} {'e_raw':>8s} {'sep':>7s} {'thr':>7s} "
          f"{'F':>6s} {'P(e|g)':>7s} {'P(g|e)':>7s} | {'fresh_g':>7s} {'fresh_e':>7s} "
          f"| {'stale_g':>7s} {'stale_e':>7s} | gate")
    while time.time() < deadline:
        t = time.time() - t0
        ref = ge_reference(soc, soccfg, cfg, REF_SHOTS)
        oper, pur, sep = purity_of(ref)
        disc = fit_threshold(ref["g"][oper][::2], ref["e"][oper][::2])
        project = make_projector(ref)
        if frozen is None:
            frozen = dict(disc)
            frozen["oper"] = oper
        fg = residual(soc, soccfg, cfg, project, False,
                      disc["threshold_raw"], disc["ground_below"], oper)
        fe = residual(soc, soccfg, cfg, project, True,
                      disc["threshold_raw"], disc["ground_below"], oper)
        sg = residual(soc, soccfg, cfg, project, False,
                      frozen["threshold_raw"], frozen["ground_below"], frozen["oper"])
        se = residual(soc, soccfg, cfg, project, True,
                      frozen["threshold_raw"], frozen["ground_below"], frozen["oper"])
        gate = "PASS" if max(abs(fg), abs(fe)) <= GATE_LIMIT else "fail"
        rows.append({"t": t, "g_raw": float(np.median(ref["g"][oper])),
                     "e_raw": float(np.median(ref["e"][oper])), "sep": sep,
                     "thr": disc["threshold_raw"], "F": disc["fidelity"],
                     "peg": disc["p_e_given_g"], "pge": disc["p_g_given_e"],
                     "purity": pur, "oper": oper,
                     "fresh_g": fg, "fresh_e": fe, "stale_g": sg, "stale_e": se})
        print(f"  {t:>6.0f} {rows[-1]['g_raw']:>8.0f} {rows[-1]['e_raw']:>8.0f} "
              f"{sep:>7.0f} {disc['threshold_raw']:>7d} {disc['fidelity']:>6.3f} "
              f"{disc['p_e_given_g']:>7.3f} {disc['p_g_given_e']:>7.3f} | "
              f"{fg:>7.3f} {fe:>7.3f} | {sg:>7.3f} {se:>7.3f} | {gate}", flush=True)

    if PHASE_CAL_AT_END:
        ph1 = calibrate_phase(soc, soccfg, cfg, "end")
    else:
        ph1 = None

    banner("VERDICT")
    if len(rows) < 3:
        print("  too few cycles to judge; raise MONITOR_MINUTES")
        return
    t = np.array([r["t"] for r in rows])
    fe = np.array([r["fresh_e"] for r in rows])
    se = np.array([r["stale_e"] for r in rows])
    thr = np.array([r["thr"] for r in rows], dtype=float)
    sep = np.array([r["sep"] for r in rows], dtype=float)
    F = np.array([r["F"] for r in rows])
    graw = np.array([r["g_raw"] for r in rows])

    def trend(y):
        good = np.isfinite(y)
        if good.sum() < 3:
            return np.nan, np.nan, np.nan
        tt, yy = t[good], y[good]
        slope, _ = np.polyfit(tt, yy, 1)
        resid = yy - np.polyval(np.polyfit(tt, yy, 1), tt)
        dof = max(1, yy.size - 2)
        var_t = float(np.sum((tt - tt.mean()) ** 2))
        slope_err = float(np.sqrt(np.sum(resid ** 2) / dof / var_t)) if var_t > 0 else np.nan
        return slope * 60.0, float(np.nanstd(y)), slope_err * 60.0

    print(f"  cycles: {len(rows)} over {t[-1]:.0f} s  "
          f"({t[-1] / max(len(rows) - 1, 1):.1f} s per cycle)")
    floor = np.array([ar.reset_floor(r["peg"], r["pge"]) for r in rows])
    print(f"\n  {'quantity':>22s} {'mean':>10s} {'std':>10s} {'drift/min':>12s} "
          f"{'sigma':>8s}")
    for name, y in (("reset |e> (fresh thr)", fe), ("reset |e> (stale thr)", se),
                    ("reset floor (model)", floor),
                    ("threshold_raw", thr), ("blob separation", sep),
                    ("ground raw median", graw), ("assignment F", F)):
        d, s, de = trend(y)
        sig = abs(d) / de if np.isfinite(de) and de > 0 else np.nan
        print(f"  {name:>22s} {np.nanmean(y):>10.3f} {s:>10.3f} "
              f"{d:>8.3f}+-{de:<7.3f} {sig:>8.1f}")

    d_fresh, s_fresh, e_fresh = trend(fe)
    d_stale, s_stale, e_stale = trend(se)
    n_fail = sum(1 for r in rows if max(abs(r["fresh_g"]), abs(r["fresh_e"])) > GATE_LIMIT)
    print(f"\n  gate failures (fresh threshold): {n_fail}/{len(rows)}")
    print(f"  spread of reset |e>: fresh {s_fresh:.3f}, stale {s_stale:.3f}")
    print(f"  model floor from the measured readout errors: {np.nanmean(floor):.3f} "
          f"-- the residual CANNOT go below this at any iteration count")
    print(f"  headroom above the floor: {np.nanmean(fe) - np.nanmean(floor):+.3f} "
          f"(this part is the pi; the floor is the readout)")
    drifting = np.isfinite(e_fresh) and e_fresh > 0 and abs(d_fresh) > 3.0 * e_fresh
    stale_worse = (np.isfinite(e_stale) and np.isfinite(e_fresh)
                   and (d_stale - d_fresh) > 3.0 * np.hypot(e_stale, e_fresh))
    margin = (GATE_LIMIT - np.nanmean(fe)) / max(s_fresh, 1e-9)
    if stale_worse:
        print("  --> STALE THRESHOLD is the problem: the frozen threshold degrades")
        print("      significantly faster than a freshly derived one.  Re-probe more often.")
    elif drifting:
        print(f"  --> REAL DRIFT: the slope {d_fresh:+.3f}/min is "
              f"{abs(d_fresh) / e_fresh:.1f} sigma from zero.")
    else:
        print(f"  --> NO significant drift (slope {d_fresh:+.3f}+-{e_fresh:.3f}/min).")
        print(f"      What you are seeing is shot-to-shot SCATTER about a mean that sits")
        print(f"      {margin:+.1f} sigma from the {GATE_LIMIT} gate, so the gate is close")
        print(f"      to a coin flip.  Re-probing will not help; lower the mean.")
    if np.nanmean(floor) > 0.5 * GATE_LIMIT:
        print(f"      The floor alone is {np.nanmean(floor):.3f}.  More iterations cannot")
        print(f"      fix that -- move the threshold toward |e> (run ResetThresholdScan)")
        print(f"      or improve the readout SNR.")
    if ph0 is not None and ph1 is not None:
        dphi = (ph1[0] - ph0[0] + 180.0) % 360.0 - 180.0
        print(f"\n  res_phase: start {ph0[0]:.1f} deg (purity {ph0[1]:.2f}) -> "
              f"end {ph1[0]:.1f} deg (purity {ph1[1]:.2f}), change {dphi:+.1f} deg")
        if abs(dphi) > 15.0:
            print("      the optimal readout phase MOVED during the window -- that alone")
            print("      invalidates a threshold frozen at the start.")

    banner("monitor complete -- paste the whole log back")


if __name__ == "__main__":
    main()
