import numpy as np

from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.socProxy import makeProxy
from WorkingProjects.TLS_Spectroscopy.Client_modules.Calib.initialize import BaseConfig
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mT1VsFlux import FFT1Program

QUBIT = "q4"

SHOTS = 500
ROUNDS = 3
RELAX_US = 2000.0
HERALD_DELAY_US = 8.0

REF_GAIN = 0
BASE_HOLD_US = 1.0
BASE_SETTLE_NS = 20000.0
BASE_RAMP_US = 0.02
BASE_FF_GAIN = 8000

GAIN_SWEEP = [0, 500, 1000, 2000, 4000, 6000, 8000]
HOLD_SWEEP_US = [1.0, 10.0, 100.0, 1000.0]
SETTLE_SWEEP_NS = [100.0, 1000.0, 5000.0, 20000.0, 50000.0]
RAMP_SWEEP_US = [0.02, 0.1, 0.5, 2.0]


def banner(text):
    print()
    print("=" * 78)
    print(text)
    print("=" * 78)


def point(soc, soccfg, cfg, do_pi, ff_gain, hold_us, settle_ns, ramp_us):
    c = dict(cfg)
    c["reps"] = c["shots"] = int(SHOTS)
    c["reset_mode"] = "passive"
    c["relax_delay"] = RELAX_US
    c["herald_delay"] = HERALD_DELAY_US
    c["do_pi"] = bool(do_pi)
    c["do_ff"] = True
    c["ff_gain"] = float(ff_gain)
    c["ff_hold"] = float(hold_us)
    c["flux_settle_time"] = float(settle_ns)
    c["ff_ramp_length"] = float(ramp_us)
    prog = FFT1Program(soccfg, c)
    _i0, _q0, i1, q1 = prog.acquire(soc, load_pulses=True)
    return complex(float(np.mean(i1)), float(np.mean(q1)))


def build_conditions():
    conds = []
    for g in GAIN_SWEEP:
        conds.append(("ff_gain", g, dict(ff_gain=g, hold_us=BASE_HOLD_US,
                                         settle_ns=BASE_SETTLE_NS, ramp_us=BASE_RAMP_US)))
    for h in HOLD_SWEEP_US:
        conds.append(("hold_us", h, dict(ff_gain=BASE_FF_GAIN, hold_us=h,
                                         settle_ns=BASE_SETTLE_NS, ramp_us=BASE_RAMP_US)))
    for s in SETTLE_SWEEP_NS:
        conds.append(("settle_ns", s, dict(ff_gain=BASE_FF_GAIN, hold_us=BASE_HOLD_US,
                                           settle_ns=s, ramp_us=BASE_RAMP_US)))
    for r in RAMP_SWEEP_US:
        conds.append(("ramp_us", r, dict(ff_gain=BASE_FF_GAIN, hold_us=BASE_HOLD_US,
                                         settle_ns=BASE_SETTLE_NS, ramp_us=r)))
    return conds


def main():
    soc, soccfg = makeProxy()
    cfg = dict(BaseConfig)
    cfg["qubit_gain"] = int(cfg["qubit_pi_gain"])
    cfg["ff_park_gain"] = int(cfg.get("ff_park_gain", 0) or 0)

    banner("REFERENCE -- |g> and |e> centroids with NO flux excursion (ff_gain = park)")
    ref = {}
    for do_pi in (False, True):
        vals = [point(soc, soccfg, cfg, do_pi, REF_GAIN, BASE_HOLD_US,
                      BASE_SETTLE_NS, BASE_RAMP_US) for _ in range(ROUNDS)]
        ref["e" if do_pi else "g"] = complex(np.mean(vals))
    axis = ref["e"] - ref["g"]
    ref_sep = abs(axis)
    ref_angle = np.degrees(np.angle(axis))
    print(f"  |g> centroid  {ref['g'].real:+9.3f} {ref['g'].imag:+9.3f}j")
    print(f"  |e> centroid  {ref['e'].real:+9.3f} {ref['e'].imag:+9.3f}j")
    print(f"  separation = {ref_sep:.3f}   g->e axis angle = {ref_angle:+.1f} deg")
    if ref_sep < 1e-9:
        print("  ABORT: no |g>/|e> separation even without flux.  Fix the pi or readout first.")
        return

    def project(c):
        return float(((c - ref["g"]) * np.conj(axis)).real / (ref_sep ** 2))

    conds = build_conditions()
    banner(f"MEASURING -- {len(conds)} conditions x {ROUNDS} randomized rounds "
           f"(passive reset, {RELAX_US:.0f}us relax)")
    print("  each condition measures BOTH prep-|g> and prep-|e> through the SAME flux")
    print("  sequence, so the readout is characterised in situ instead of assumed.")
    rng = np.random.default_rng()
    acc = {}
    for r in range(ROUNDS):
        print(f"  round {r + 1}/{ROUNDS} ...", flush=True)
        for idx in rng.permutation(len(conds)):
            key, val, kw = conds[idx]
            for do_pi in (False, True):
                c = point(soc, soccfg, cfg, do_pi, **kw)
                acc.setdefault((key, val, do_pi), []).append(c)

    for key, values in (("ff_gain", GAIN_SWEEP), ("hold_us", HOLD_SWEEP_US),
                        ("settle_ns", SETTLE_SWEEP_NS), ("ramp_us", RAMP_SWEEP_US)):
        banner(f"{key} sweep")
        print(f"  reference (no flux): separation {ref_sep:.3f}, axis {ref_angle:+.1f} deg\n")
        print(f"  {key:>12s} | {'sep':>8s} {'sep/ref':>8s} | {'axis':>8s} {'d_axis':>8s} | "
              f"{'proj g':>7s} {'proj e':>7s} | diagnosis")
        for v in values:
            g = acc.get((key, v, False), [])
            e = acc.get((key, v, True), [])
            if not g or not e:
                continue
            cg, ce = complex(np.mean(g)), complex(np.mean(e))
            ax = ce - cg
            sep, ang = abs(ax), np.degrees(np.angle(ax))
            dang = (ang - ref_angle + 180.0) % 360.0 - 180.0
            pg, pe = project(cg), project(ce)
            if sep < 0.35 * ref_sep:
                diag = "BLOBS MERGED -> population lost"
            elif abs(dang) > 25.0:
                diag = "AXIS ROTATED -> park threshold invalid"
            elif pe < 0.5:
                diag = "separated but shifted off the park axis"
            else:
                diag = "healthy"
            print(f"  {str(v):>12s} | {sep:>8.3f} {sep / ref_sep:>8.2f} | {ang:>+8.1f} "
                  f"{dang:>+8.1f} | {pg:>7.3f} {pe:>7.3f} | {diag}")

    banner("HOW TO READ THIS")
    print("  sep/ref ~ 1 and |d_axis| small  -> readout still works; any drop in 'proj e'")
    print("                                     is real population loss at the flux point.")
    print("  sep/ref << 1                    -> the excited state is genuinely gone (or the")
    print("                                     qubit moved out of the readout's range).")
    print("  sep/ref ~ 1 but d_axis large    -> the resonator moved; the park-calibrated")
    print("                                     threshold is measuring the wrong axis and")
    print("                                     every T1 point built on it is meaningless.")


if __name__ == "__main__":
    main()
