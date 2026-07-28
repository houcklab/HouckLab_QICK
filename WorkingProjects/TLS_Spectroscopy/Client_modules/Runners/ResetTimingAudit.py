import numpy as np

from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.socProxy import makeProxy
from WorkingProjects.TLS_Spectroscopy.Client_modules.Calib.initialize import BaseConfig
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mActiveResetProbe import (
    ReadProbeProgram, ResetCheckProgram,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mT1VsFlux import FFT1Program
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import active_reset as ar

QUBIT = "q4"

RES_PHASE = None
REFERENCE_SHOTS = 2000
GATE_SHOTS = 2000
PI_SHOTS = 1500

REF_RELAX_US = 3000.0
SAFE_RELAX_US = 500.0
SAFE_THERMALIZATION_US = 25.0
SAFE_MEAS_SYNCDELAY_US = 4.0
SAFE_READ_DELAY_US = 2.0
SAFE_MAX_ITERS = 3
SAFE_HERALD_DELAY_US = 8.0

THERMALIZATION_SWEEP_US = [0.0, 1.0, 2.0, 3.0, 5.0, 8.0, 15.0, 25.0]
RELAX_SWEEP_US = [2.0, 5.0, 10.0, 25.0, 50.0, 100.0, 500.0]
MEAS_SYNCDELAY_SWEEP_US = [1.0, 2.0, 3.0, 4.0, 6.0, 8.0]
READ_DELAY_SWEEP_US = [0.05, 0.1, 0.3, 1.0, 2.0, 4.0]
MAX_ITERS_SWEEP = [1, 2, 3, 4, 5]
HERALD_DELAY_SWEEP_US = [1.0, 2.0, 3.0, 4.0, 6.0, 8.0, 12.0]

GATE_LIMIT = 0.2
TOLERANCE = 0.02

RUN_A_THERMALIZATION = True
RUN_B_INTERSHOT_RELAX = True
RUN_C_MEAS_SYNCDELAY = True
RUN_D_READ_DELAY = True
RUN_E_MAX_ITERS = True
RUN_F_HERALD_DELAY = True


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


def make_projector(ref):
    Ig, Qg = ref["g"]["I"], ref["g"]["Q"]
    dx, dy = ref["e"]["I"] - Ig, ref["e"]["Q"] - Qg
    denom = dx * dx + dy * dy

    def project(Ir, Qr):
        return (((Ir - Ig) * dx + (Qr - Qg) * dy) / denom) if denom > 0 else float("nan")
    return project


def gate_residual(soc, soccfg, cfg, project, prep_excited, **over):
    c = dict(cfg)
    c["reps"] = c["shots"] = int(GATE_SHOTS)
    c["prep_excited"] = bool(prep_excited)
    c["do_reset"] = True
    c["reset_thermalization_us"] = SAFE_THERMALIZATION_US
    c["reset_meas_syncdelay_us"] = SAFE_MEAS_SYNCDELAY_US
    c["reset_read_delay_us"] = SAFE_READ_DELAY_US
    c["reset_max_iters"] = SAFE_MAX_ITERS
    c["relax_delay"] = SAFE_RELAX_US
    c.update(over)
    I, Q = ResetCheckProgram(soccfg, c).acquire(soc, load_pulses=True)
    return project(I, Q)


def sweep_gate(soc, soccfg, cfg, project, title, key, values, unit=""):
    banner(title)
    print(f"  everything else held at the validated point: therm={SAFE_THERMALIZATION_US}us, "
          f"msync={SAFE_MEAS_SYNCDELAY_US}us,")
    print(f"  read_delay={SAFE_READ_DELAY_US}us, iters={SAFE_MAX_ITERS}, "
          f"inter-shot relax={SAFE_RELAX_US}us")
    print(f"\n  {key:>22s} | {'reset |g>':>9s} {'reset |e>':>9s} | {'worst':>7s} | verdict")
    rows = []
    for v in values:
        try:
            rg = gate_residual(soc, soccfg, cfg, project, False, **{key: v})
            re = gate_residual(soc, soccfg, cfg, project, True, **{key: v})
        except ValueError as exc:
            print(f"  {str(v) + unit:>22s} | {'not schedulable':>29s} | {str(exc)[:60]}")
            continue
        worst = max(abs(rg), abs(re))
        rows.append((v, rg, re, worst))
        print(f"  {str(v) + unit:>22s} | {rg:>9.3f} {re:>9.3f} | {worst:>7.3f} | "
              f"{'PASS' if worst <= GATE_LIMIT else 'fail'}")
    if not rows:
        print("\n  --> no value in this sweep could be scheduled")
        return rows
    best = min(r[3] for r in rows)
    ok = [r for r in rows if r[3] <= min(best + TOLERANCE, GATE_LIMIT)]
    if ok:
        cheapest = ok[0] if not isinstance(values[0], (int, float)) else min(ok, key=lambda r: r[0])
        print(f"\n  best worst-residual = {best:.3f}; within +{TOLERANCE:.2f} of best: "
              f"{[str(r[0]) for r in ok]}")
        print(f"  --> SMALLEST SAFE {key} = {cheapest[0]}{unit}")
    else:
        print(f"\n  --> nothing passed the {GATE_LIMIT} gate; keep the current value")
    return rows


def pi_contrast(soc, soccfg, cfg, project, herald_delay_us, do_pi):
    c = dict(cfg)
    c["reps"] = c["shots"] = int(PI_SHOTS)
    c["do_ff"] = False
    c["do_pi"] = bool(do_pi)
    c["ff_gain"] = 0.0
    c["ff_hold"] = 0.0
    c["herald_delay"] = float(herald_delay_us)
    c["relax_delay"] = SAFE_RELAX_US
    c["reset_thermalization_us"] = SAFE_THERMALIZATION_US
    c["reset_meas_syncdelay_us"] = SAFE_MEAS_SYNCDELAY_US
    c["reset_read_delay_us"] = SAFE_READ_DELAY_US
    c["reset_max_iters"] = SAFE_MAX_ITERS
    prog = FFT1Program(soccfg, c)
    _i0, _q0, i1, q1 = prog.acquire(soc, load_pulses=True)
    return project(float(np.mean(i1)), float(np.mean(q1)))


def sweep_herald_delay(soc, soccfg, cfg, project):
    banner("TEST F -- prep-pi efficiency vs herald_delay (gap from herald readout to pi)")
    print("  runs the REAL FFT1Program at zero flux hold; the plateau is the pi contrast.")
    print("  pi_eff = (with_pi - no_pi) / (1 - 2*no_pi); it must saturate near 1.\n")
    print(f"  {'herald_delay':>14s} | {'no pi':>7s} {'with pi':>7s} | {'pi_eff':>7s} | verdict")
    rows = []
    for d in HERALD_DELAY_SWEEP_US:
        p0 = pi_contrast(soc, soccfg, cfg, project, d, False)
        p1 = pi_contrast(soc, soccfg, cfg, project, d, True)
        denom = 1.0 - 2.0 * p0
        eff = (p1 - p0) / denom if abs(denom) > 1e-6 else float("nan")
        rows.append((d, p0, p1, eff))
        print(f"  {d:>12.1f}us | {p0:>7.3f} {p1:>7.3f} | {eff:>7.3f} | "
              f"{'saturated' if eff > 0.95 else 'LOW'}")
    good = [r for r in rows if r[3] > 0.95]
    if good:
        print(f"\n  --> pi saturates from herald_delay = {good[0][0]}us upward")
        print(f"  --> RECOMMENDED herald_delay = {max(good[0][0] * 2, good[0][0] + 2):.1f}us "
              f"(2x margin over the knee)")
    else:
        print("\n  --> pi never saturated; the prep pulse itself needs attention")
    return rows


def main():
    soc, soccfg = makeProxy()
    cfg = dict(BaseConfig)
    if RES_PHASE is not None:
        cfg["res_phase"] = float(RES_PHASE)
    cfg["qubit_gain"] = int(cfg["qubit_pi_gain"])
    cfg["reset_mode"] = "feedback"
    cfg["reset_oper"] = "lower"
    cfg["tproc_ch"] = ar.feedback_channel(soccfg, cfg["ro_chs"][0])
    cfg["flux_settle_time"] = cfg.get("flux_settle_time", 100)

    banner("SETUP -- reference blobs, discrimination, projector")
    ref = ge_reference(soc, soccfg, cfg, REFERENCE_SHOTS)
    sep_lo = abs(np.median(ref["e"]["lower"]) - np.median(ref["g"]["lower"]))
    sep_up = abs(np.median(ref["e"]["upper"]) - np.median(ref["g"]["upper"]))
    oper = "lower" if sep_lo >= sep_up else "upper"
    purity = max(sep_lo, sep_up) / (sep_lo + sep_up + 1e-9)
    disc = fit_threshold(ref["g"][oper][::2], ref["e"][oper][::2])
    cfg["reset_oper"] = oper
    cfg["reset_threshold_raw"] = int(disc["threshold_raw"])
    cfg["reset_ground_below"] = bool(disc["ground_below"])
    project = make_projector(ref)
    print(f"  res_phase = {cfg['res_phase']:.1f} deg   discriminating on '{oper}'  "
          f"purity = {purity:.2f}")
    print(f"  threshold_raw = {disc['threshold_raw']}  ground_below = {disc['ground_below']}")
    print(f"  F = {disc['fidelity']:.3f}  P(e|g) = {disc['p_e_given_g']:.3f}  "
          f"P(g|e) = {disc['p_g_given_e']:.3f}")
    if purity < 0.80:
        print("  WARNING: |g>/|e> are not concentrated on one quadrature at this res_phase.")
        print("           Every number below is still self-consistent, but re-run the")
        print("           res-phase calibration before adopting the recommendations.")
    baseline = gate_residual(soc, soccfg, cfg, project, True, do_reset=False)
    print(f"  no-reset baseline (prepared |e>, must be ~1.0): {baseline:+.3f}")

    if RUN_A_THERMALIZATION:
        sweep_gate(soc, soccfg, cfg, project,
                   "TEST A -- reset_thermalization_us (resonator ring-down after the reset)",
                   "reset_thermalization_us", THERMALIZATION_SWEEP_US, "us")
    if RUN_B_INTERSHOT_RELAX:
        sweep_gate(soc, soccfg, cfg, project,
                   "TEST B -- relax_delay (inter-shot idle; FEEDBACK_RELAX_US)",
                   "relax_delay", RELAX_SWEEP_US, "us")
    if RUN_C_MEAS_SYNCDELAY:
        sweep_gate(soc, soccfg, cfg, project,
                   "TEST C -- reset_meas_syncdelay_us (readout -> conditional pi gap)",
                   "reset_meas_syncdelay_us", MEAS_SYNCDELAY_SWEEP_US, "us")
    if RUN_D_READ_DELAY:
        sweep_gate(soc, soccfg, cfg, project,
                   "TEST D -- reset_read_delay_us (accumulator settle before read)",
                   "reset_read_delay_us", READ_DELAY_SWEEP_US, "us")
    if RUN_E_MAX_ITERS:
        sweep_gate(soc, soccfg, cfg, project,
                   "TEST E -- reset_max_iters (measure/flip rounds)",
                   "reset_max_iters", MAX_ITERS_SWEEP, "")
    if RUN_F_HERALD_DELAY:
        sweep_herald_delay(soc, soccfg, cfg, project)

    banner("audit complete -- paste the whole log back")


if __name__ == "__main__":
    main()
