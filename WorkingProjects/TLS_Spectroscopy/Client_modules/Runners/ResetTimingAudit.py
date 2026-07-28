import numpy as np

from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.socProxy import makeProxy
from WorkingProjects.TLS_Spectroscopy.Client_modules.Calib.initialize import BaseConfig
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mActiveResetProbe import (
    ReadProbeProgram, ResetCheckProgram,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mT1VsFlux import FFT1Program
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import active_reset as ar

QUBIT = "q4"

RUN_PHASE_CAL = True
PHASE_SWEEP_DEG = list(range(0, 180, 15))
PHASE_SHOTS = 500
MIN_PURITY = 0.85

RES_PHASE = None
REFERENCE_SHOTS = 2000

ROUNDS = 5
SHOTS_PER_ROUND = 400
PI_SHOTS_PER_ROUND = 300

REF_RELAX_US = 3000.0
SAFE_RELAX_US = 2000.0
SAFE_THERMALIZATION_US = 25.0
SAFE_MEAS_SYNCDELAY_US = 4.0
SAFE_READ_DELAY_US = 2.0
SAFE_MAX_ITERS = 3
SAFE_HERALD_DELAY_US = 8.0

SWEEPS = {
    "reset_thermalization_us": [0.0, 2.0, 5.0, 10.0, 15.0, 25.0],
    "reset_meas_syncdelay_us": [2.0, 3.0, 4.0, 6.0, 8.0],
    "reset_read_delay_us": [0.1, 0.3, 1.0, 2.0, 4.0],
    "reset_max_iters": [1, 2, 3, 4],
}
RELAX_SWEEP_US = [5.0, 10.0, 25.0, 50.0, 100.0, 500.0, 2000.0]

GATE_LIMIT = 0.2
BASELINE_MIN = 0.90


def banner(text):
    print()
    print("=" * 78)
    print(text)
    print("=" * 78)


def fit_threshold(ground, excited):
    values = np.unique(np.concatenate((ground, excited)))
    best = None
    for ground_below in (True, False):
        for threshold in values:
            if ground_below:
                p_e_g = float(np.mean(ground >= threshold))
                p_g_e = float(np.mean(excited < threshold))
            else:
                p_e_g = float(np.mean(ground <= threshold))
                p_g_e = float(np.mean(excited > threshold))
            f = 1.0 - 0.5 * (p_e_g + p_g_e)
            if best is None or f > best["fidelity"]:
                best = {"threshold_raw": int(threshold), "ground_below": bool(ground_below),
                        "fidelity": f, "p_e_given_g": p_e_g, "p_g_given_e": p_g_e}
    return best


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


def calibrate_phase(soc, soccfg, cfg):
    banner("PHASE CAL -- put |g>/|e> on one raw quadrature before measuring anything")
    best = None
    for ph in PHASE_SWEEP_DEG:
        c = dict(cfg)
        c["res_phase"] = float(ph)
        ref = ge_reference(soc, soccfg, c, PHASE_SHOTS)
        oper, pur, sep = purity_of(ref)
        print(f"    res_phase={ph:6.1f} deg  oper={oper:>5s}  purity={pur:.2f}  sep={sep:.0f}")
        if best is None or (pur, sep) > (best[1], best[2]):
            best = (ph, pur, sep, oper)
    print(f"\n  BEST res_phase = {best[0]:.1f} deg (purity {best[1]:.2f}, oper '{best[3]}')")
    return float(best[0])


def make_projector(ref):
    Ig, Qg = ref["g"]["I"], ref["g"]["Q"]
    dx, dy = ref["e"]["I"] - Ig, ref["e"]["Q"] - Qg
    denom = dx * dx + dy * dy

    def project(Ir, Qr):
        return (((Ir - Ig) * dx + (Qr - Qg) * dy) / denom) if denom > 0 else float("nan")
    return project


def base_reset_cfg(cfg):
    c = dict(cfg)
    c["reset_thermalization_us"] = SAFE_THERMALIZATION_US
    c["reset_meas_syncdelay_us"] = SAFE_MEAS_SYNCDELAY_US
    c["reset_read_delay_us"] = SAFE_READ_DELAY_US
    c["reset_max_iters"] = SAFE_MAX_ITERS
    c["relax_delay"] = SAFE_RELAX_US
    return c


def measure_gate(soc, soccfg, cfg, project, prep_excited, reps, over):
    c = base_reset_cfg(cfg)
    c["reps"] = c["shots"] = int(reps)
    c["prep_excited"] = bool(prep_excited)
    c["do_reset"] = True
    c.update(over)
    I, Q = ResetCheckProgram(soccfg, c).acquire(soc, load_pulses=True)
    return project(I, Q)


def measure_plateau(soc, soccfg, cfg, project, do_pi, reps, over):
    c = base_reset_cfg(cfg)
    c["reps"] = c["shots"] = int(reps)
    c["do_ff"] = False
    c["do_pi"] = bool(do_pi)
    c["ff_gain"] = 0.0
    c["ff_hold"] = 0.0
    c["herald_delay"] = SAFE_HERALD_DELAY_US
    c.update(over)
    prog = FFT1Program(soccfg, c)
    _i0, _q0, i1, q1 = prog.acquire(soc, load_pulses=True)
    return project(float(np.mean(i1)), float(np.mean(q1)))


def build_jobs():
    jobs = []
    for key, values in SWEEPS.items():
        for v in values:
            for prep in (False, True):
                jobs.append({"kind": "gate", "key": key, "value": v, "prep": prep,
                             "label": f"{key}={v}", "series": f"gate:{key}"})
    for v in RELAX_SWEEP_US:
        for do_pi in (False, True):
            jobs.append({"kind": "plateau", "key": "relax_delay", "value": v, "do_pi": do_pi,
                         "label": f"relax_delay={v}", "series": "plateau:relax_delay"})
    return jobs


def run_jobs(soc, soccfg, cfg, project, jobs):
    rng = np.random.default_rng()
    acc = {}
    skipped = set()
    for r in range(ROUNDS):
        order = rng.permutation(len(jobs))
        print(f"  round {r + 1}/{ROUNDS} ...", flush=True)
        for j in order:
            job = jobs[j]
            tag = (job["label"], job.get("prep"), job.get("do_pi"))
            if tag in skipped:
                continue
            try:
                if job["kind"] == "gate":
                    val = measure_gate(soc, soccfg, cfg, project, job["prep"],
                                       SHOTS_PER_ROUND, {job["key"]: job["value"]})
                else:
                    val = measure_plateau(soc, soccfg, cfg, project, job["do_pi"],
                                          PI_SHOTS_PER_ROUND, {job["key"]: job["value"]})
            except ValueError as exc:
                skipped.add(tag)
                print(f"    {job['label']}: not schedulable -- {str(exc)[:60]}")
                continue
            acc.setdefault(tag, []).append(val)
    return acc


def report_gate(acc, key, values):
    banner(f"{key}  (reset residual; interleaved over {ROUNDS} randomized rounds)")
    print(f"  {key:>26s} | {'reset |g>':>16s} | {'reset |e>':>16s} | {'worst':>7s}")
    rows = []
    for v in values:
        g = acc.get((f"{key}={v}", False, None), [])
        e = acc.get((f"{key}={v}", True, None), [])
        if not g or not e:
            print(f"  {str(v):>26s} | {'(not measured)':>16s}")
            continue
        gm, gs = float(np.mean(g)), float(np.std(g))
        em, es = float(np.mean(e)), float(np.std(e))
        worst = max(abs(gm), abs(em))
        rows.append((v, gm, gs, em, es, worst, max(gs, es)))
        print(f"  {str(v):>26s} | {gm:>8.3f} +/-{gs:5.3f} | {em:>8.3f} +/-{es:5.3f} | "
              f"{worst:>7.3f}")
    if not rows:
        return
    best = min(r[5] for r in rows)
    spread = float(np.median([r[6] for r in rows]))
    band = best + 2.0 * spread
    ok = [r for r in rows if r[5] <= min(band, GATE_LIMIT)]
    print(f"\n  best worst-residual = {best:.3f}; typical round-to-round sigma = {spread:.3f}")
    print(f"  values statistically indistinguishable from best (<= {band:.3f}): "
          f"{[str(r[0]) for r in ok] if ok else 'none'}")
    if ok:
        print(f"  --> SMALLEST value not distinguishable from the best: {min(r[0] for r in ok)}")
    if best > GATE_LIMIT:
        print(f"  --> WARNING: even the best value fails the {GATE_LIMIT} gate")


def report_plateau(acc):
    banner(f"relax_delay / FEEDBACK_RELAX_US  (production ordering: reset BEFORE the pi)")
    print("  the reset runs first, so a short inter-shot idle is only a problem if the")
    print("  reset cannot absorb it.  pi contrast must stay flat as relax_delay drops.\n")
    print(f"  {'relax_delay':>14s} | {'no pi':>16s} | {'with pi':>16s} | {'contrast':>8s}")
    rows = []
    for v in RELAX_SWEEP_US:
        p0 = acc.get((f"relax_delay={v}", None, False), [])
        p1 = acc.get((f"relax_delay={v}", None, True), [])
        if not p0 or not p1:
            continue
        m0, s0 = float(np.mean(p0)), float(np.std(p0))
        m1, s1 = float(np.mean(p1)), float(np.std(p1))
        rows.append((v, m0, m1, m1 - m0, max(s0, s1)))
        print(f"  {v:>12.1f}us | {m0:>8.3f} +/-{s0:5.3f} | {m1:>8.3f} +/-{s1:5.3f} | "
              f"{m1 - m0:>8.3f}")
    if not rows:
        return
    best = max(r[3] for r in rows)
    spread = float(np.median([r[4] for r in rows]))
    ok = [r for r in rows if r[3] >= best - 2.0 * spread]
    print(f"\n  best contrast = {best:.3f}; typical sigma = {spread:.3f}")
    print(f"  --> SMALLEST relax_delay with full contrast: {min(r[0] for r in ok)}us")


def main():
    soc, soccfg = makeProxy()
    cfg = dict(BaseConfig)
    if RES_PHASE is not None:
        cfg["res_phase"] = float(RES_PHASE)
    cfg["qubit_gain"] = int(cfg["qubit_pi_gain"])
    cfg["reset_mode"] = "feedback"
    cfg["tproc_ch"] = ar.feedback_channel(soccfg, cfg["ro_chs"][0])
    cfg["flux_settle_time"] = cfg.get("flux_settle_time", 100)

    if RUN_PHASE_CAL:
        cfg["res_phase"] = calibrate_phase(soc, soccfg, cfg)

    banner("SETUP -- reference blobs, discrimination, projector, sanity checks")
    ref = ge_reference(soc, soccfg, cfg, REFERENCE_SHOTS)
    oper, purity, _ = purity_of(ref)
    disc = fit_threshold(ref["g"][oper][::2], ref["e"][oper][::2])
    cfg["reset_oper"] = oper
    cfg["reset_threshold_raw"] = int(disc["threshold_raw"])
    cfg["reset_ground_below"] = bool(disc["ground_below"])
    project = make_projector(ref)
    print(f"  res_phase = {cfg['res_phase']:.1f} deg   oper '{oper}'   purity = {purity:.2f}")
    print(f"  threshold_raw = {disc['threshold_raw']}  ground_below = {disc['ground_below']}")
    print(f"  F = {disc['fidelity']:.3f}  P(e|g) = {disc['p_e_given_g']:.3f}  "
          f"P(g|e) = {disc['p_g_given_e']:.3f}")

    baseline = measure_gate(soc, soccfg, cfg, project, True, REFERENCE_SHOTS,
                            {"do_reset": False})
    print(f"  no-reset baseline (prepared |e>, must be ~1.0): {baseline:+.3f}"
          f"   [inter-shot relax {SAFE_RELAX_US:.0f}us]")
    ok = True
    if purity < MIN_PURITY:
        print(f"  ABORT-WORTHY: purity {purity:.2f} < {MIN_PURITY}; discrimination is split "
              f"across quadratures.")
        ok = False
    if baseline < BASELINE_MIN:
        print(f"  ABORT-WORTHY: baseline {baseline:.3f} < {BASELINE_MIN}.  The prep pi is "
              f"acting on a partly-excited")
        print(f"                qubit -- raise SAFE_RELAX_US above ~6x T1 before trusting "
              f"any number below.")
        ok = False
    if not ok:
        print("\n  Setup is not clean.  Fix the above and re-run; results would not be "
              "trustworthy.")
        return

    jobs = build_jobs()
    banner(f"MEASURING -- {len(jobs)} conditions x {ROUNDS} interleaved randomized rounds")
    print(f"  every condition is revisited once per round in a fresh random order, so")
    print(f"  drift shows up as round-to-round sigma instead of masquerading as signal.")
    acc = run_jobs(soc, soccfg, cfg, project, jobs)

    for key, values in SWEEPS.items():
        report_gate(acc, key, values)
    report_plateau(acc)

    banner("audit complete -- paste the whole log back")


if __name__ == "__main__":
    main()
