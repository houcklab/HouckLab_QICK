import time

import numpy as np
from qick import AveragerProgram

from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.socProxy import makeProxy
from WorkingProjects.TLS_Spectroscopy.Client_modules.Calib.initialize import BaseConfig
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mActiveResetProbe import (
    ReadProbeProgram, ResetCheckProgram,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import active_reset as ar
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import ff_pulse
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.pulse_setup import (
    set_readout_pulse, readout_drive_length_us,
)

QUBIT = "q4"

RINGDOWN_TAIL_US = 10.0
RINGDOWN_REPS = 200

SYNCDELAY_SWEEP_US = [3.5, 4.0, 5.0, 7.0, 10.0, 15.0, 25.0]
CLEAR_SWEEP_US = [0.0, 0.5, 2.0, 5.0, 10.0, 25.0, 50.0]

ROUNDS = 4
REF_SHOTS = 3000
GATE_SHOTS = 800
REF_RELAX_US = 2000.0
GATE_RELAX_US = 25.0

NEVER_FIRE_THRESHOLD = 1 << 22
RESET_ITERS = 3
BASE_SYNCDELAY_US = 4.0
BASE_CLEAR_US = 2.0
RESET_READ_DELAY_US = 2.0


def banner(text):
    print()
    print("=" * 100)
    print(text)
    print("=" * 100)


class RingdownProgram(AveragerProgram):

    def initialize(self):
        cfg = self.cfg
        cfg.setdefault("reps", RINGDOWN_REPS)
        ro = cfg["ro_chs"][0]
        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"],
                         mixer_freq=cfg.get("mixer_freq", 0), ro_ch=ro)
        ff_pulse.declare_static_park(self)
        self.declare_readout(ch=ro, freq=cfg["read_pulse_freq"],
                             length=self.us2cycles(cfg["capture_us"], ro_ch=ro),
                             gen_ch=cfg["res_ch"])
        set_readout_pulse(self, self.freq2reg(cfg["read_pulse_freq"],
                                              gen_ch=cfg["res_ch"], ro_ch=ro))
        self.synci(200)

    def body(self):
        cfg = self.cfg
        ff_pulse.play_static_park(self, settle_us=cfg.get("ff_park_settle_us", 0.05))
        self.trigger(adcs=cfg["ro_chs"],
                     adc_trig_offset=self.us2cycles(cfg["adc_trig_offset"]))
        self.pulse(ch=cfg["res_ch"])
        self.wait_all()
        self.sync_all(self.us2cycles(cfg.get("relax_delay", 200.0)))


def measure_ringdown(soc, soccfg, cfg, capture_us=None):
    c = dict(cfg)
    drive_us = float(readout_drive_length_us(cfg))
    want = float(drive_us + RINGDOWN_TAIL_US if capture_us is None else capture_us)
    c["reps"] = RINGDOWN_REPS
    c["relax_delay"] = 200.0
    ro = c["ro_chs"][0]
    out = None
    for attempt in (want, drive_us + 4.0, drive_us + 2.0, drive_us + 1.0):
        c["capture_us"] = float(attempt)
        try:
            prog = RingdownProgram(soccfg, c)
            out = prog.acquire_decimated(soc, load_pulses=True, progress=False)
            if attempt < want:
                print(f"  decimated buffer would not hold {want:.1f} us; captured "
                      f"{attempt:.1f} us instead.")
            break
        except Exception as exc:
            last = exc
    if out is None:
        print(f"  could not capture a decimated trace ({last}).")
        print(f"  Skipping the direct kappa measurement; stage 2 still measures the")
        print(f"  delay the pi actually needs, which is the number that matters.")
        return None
    arr = np.asarray(out[0], dtype=float)
    I, Q = (arr[:, 0], arr[:, 1]) if arr.ndim == 2 and arr.shape[1] == 2 else (arr[0], arr[1])
    mag = np.hypot(I, Q)
    try:
        f_fabric = float(soccfg['readouts'][ro]['f_fabric'])
    except Exception:
        f_fabric = None
    if f_fabric and f_fabric > 0:
        dt_us = 1.0 / f_fabric
    else:
        dt_us = float(c["capture_us"]) / max(mag.size, 1)
    t = np.arange(mag.size) * dt_us
    drive_us = float(readout_drive_length_us(cfg))
    peak = int(np.argmax(mag))
    start = min(peak + max(2, int(round(0.05 / max(dt_us, 1e-9)))), mag.size - 5)
    tt, mm = t[start:], mag[start:]
    tail_us = float(tt[-1] - tt[0]) if tt.size > 1 else 0.0
    base = float(np.median(mm[-max(3, mm.size // 5):]))
    y = mm - base
    good = y > 0.05 * max(y.max(), 1e-9)
    tau = np.nan
    if good.sum() >= 4:
        sl = np.polyfit(tt[good], np.log(y[good]), 1)[0]
        tau = -1.0 / sl if sl < 0 else np.nan
    return {"t": t, "mag": mag, "dt_us": dt_us, "drive_us": drive_us,
            "tau_us": tau, "peak_us": t[peak], "tail_us": tail_us,
            "fit_pts": int(good.sum())}


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
            "lower": np.asarray([ar.to_signed32(v) for v in
                                 np.asarray(prog.di_buf[0]).ravel()], dtype=np.int64),
            "upper": np.asarray([ar.to_signed32(v) for v in
                                 np.asarray(prog.dq_buf[0]).ravel()], dtype=np.int64),
        }
    return out


def gate(soc, soccfg, cfg, prep, do_reset, thr, gb, oper, iters,
         syncdelay_us, clear_us, force_flip=False):
    c = dict(cfg)
    c["reps"] = c["shots"] = int(GATE_SHOTS)
    c["prep_excited"] = bool(prep)
    c["do_reset"] = bool(do_reset)
    c["reset_threshold_raw"] = int(thr)
    c["reset_ground_below"] = bool(gb)
    c["reset_oper"] = str(oper)
    c["reset_max_iters"] = int(iters)
    c["reset_force_flip"] = bool(force_flip)
    c["reset_meas_syncdelay_us"] = float(syncdelay_us)
    c["reset_thermalization_us"] = float(clear_us)
    c["reset_read_delay_us"] = RESET_READ_DELAY_US
    c["relax_delay"] = GATE_RELAX_US
    return ResetCheckProgram(soccfg, c).acquire(soc, load_pulses=True)


def projector(ag, ae):
    dx, dy = ae[0] - ag[0], ae[1] - ag[1]
    den = dx * dx + dy * dy

    def p(I, Q):
        return (((I - ag[0]) * dx + (Q - ag[1]) * dy) / den) if den > 0 else float("nan")
    return p


def stat(v):
    v = np.asarray([x for x in v if np.isfinite(x)], dtype=float)
    if v.size == 0:
        return np.nan, np.nan
    return float(np.mean(v)), float(np.std(v) / max(1.0, np.sqrt(v.size - 1)))


def main():
    soc, soccfg = makeProxy()
    cfg = dict(BaseConfig)
    cfg["qubit_gain"] = int(cfg["qubit_pi_gain"])
    cfg["reset_mode"] = "feedback"
    cfg["tproc_ch"] = ar.feedback_channel(soccfg, cfg["ro_chs"][0])

    banner("RESET DELAY AUDIT -- which delay guards what, measured not assumed")
    print("  active_reset_block has THREE delays and they are not interchangeable.")
    print("  Reading the source (Helpers/active_reset.py), per iteration it emits:")
    print()
    print("      measure(...)                       <- readout tone, resonator fills")
    print("      waiti(adc_end + reset_read_delay_us)")
    print("      read(...)                          <- tProc latches the result")
    print("      sync_all(reset_meas_syncdelay_us)  <- (A) readout -> conditional pi")
    print("      condj / pulse(qubit_ch)            <- the pi fires HERE")
    print("      sync_all(reset_settle_us)")
    print("  ...and ONCE after the loop:")
    print("      sync_all(reset_thermalization_us)  <- (B) last pi -> your experiment")
    print()
    print("  So resonator photons threaten the PI, and the delay that protects the pi")
    print("  is (A) reset_meas_syncdelay_us -- NOT reset_thermalization_us.  Photons")
    print("  left in the resonator ac-Stark shift the qubit; the pi is only ~0.6 MHz")
    print("  wide, so a shifted qubit means a failed flip.")
    print("  reset_thermalization_us is (B): the gap between the last conditional pi")
    print("  and whatever your experiment does next.  Different job, different value.")
    print()
    print("  Cost is asymmetric and this decides the trade:")
    print(f"    (A) is paid ONCE PER ITERATION  -> x{RESET_ITERS} per shot")
    print(f"    (B) is paid ONCE PER SHOT")
    print()
    print("  This script measures the ring-down directly, then sweeps (A) and (B)")
    print("  independently so neither hides inside the other.")

    banner("STAGE 1 -- resonator ring-down, measured directly from the ADC trace")
    rd = measure_ringdown(soc, soccfg, cfg)
    if rd is not None:
        print(f"  decimated sample spacing {rd['dt_us'] * 1e3:.1f} ns, "
              f"drive length {rd['drive_us']:.2f} us, peak at {rd['peak_us']:.2f} us, "
              f"tail {rd['tail_us']:.2f} us")
        if np.isfinite(rd["tau_us"]) and rd["tail_us"] >= 2.0 * rd["tau_us"]:
            tau = rd["tau_us"]
            print(f"  ring-down time constant tau = {tau * 1e3:.0f} ns "
                  f"(kappa/2pi = {1e3 / (2 * np.pi * tau):.1f} kHz)")
            print(f"\n  photons remaining after a delay of:")
            for n in (1, 2, 3, 5, 7, 10):
                print(f"    {n * tau:>7.2f} us ({n:>2d} tau): {np.exp(-n):.2e}")
            print(f"\n  -> ring-down alone needs about {5 * tau:.2f} us "
                  f"(5 tau, 0.7% left).")
            print(f"     reset_meas_syncdelay_us is currently {BASE_SYNCDELAY_US:g} us, "
                  f"which is {BASE_SYNCDELAY_US / tau:.1f} tau.")
            if BASE_SYNCDELAY_US < 5 * tau:
                print(f"     THAT IS NOT ENOUGH -- the conditional pi is firing into a")
                print(f"     resonator that still has photons in it.")
            else:
                print(f"     That is already sufficient; ring-down is not your problem.")
        elif np.isfinite(rd["tau_us"]):
            print(f"  fitted tau = {rd['tau_us'] * 1e3:.0f} ns but the captured tail is "
                  f"only {rd['tail_us']:.2f} us = {rd['tail_us'] / rd['tau_us']:.1f} tau.")
            print(f"  That is too short to trust.  Raise RINGDOWN_TAIL_US (currently "
                  f"{RINGDOWN_TAIL_US:g} us) if the buffer allows.")
        else:
            print(f"  could not fit an exponential to the tail ({rd['fit_pts']} usable "
                  f"points over {rd['tail_us']:.2f} us); see the trace dump.")
        step = max(1, rd["mag"].size // 40)
        print(f"\n  trace (every {step} samples):")
        for i in range(0, rd["mag"].size, step):
            bar = "#" * int(40 * rd["mag"][i] / max(rd["mag"].max(), 1e-9))
            print(f"    {rd['t'][i]:>6.2f} us {rd['mag'][i]:>10.0f} {bar}")

    ref = ge_reference(soc, soccfg, cfg, REF_SHOTS)
    lo = abs(np.median(ref["e"]["lower"]) - np.median(ref["g"]["lower"]))
    up = abs(np.median(ref["e"]["upper"]) - np.median(ref["g"]["upper"]))
    oper = "lower" if lo >= up else "upper"
    disc = ar.fit_assignment_threshold(ref["g"][oper][::2], ref["e"][oper][::2])
    thr, gb = int(disc["threshold_raw"]), bool(disc["ground_below"])
    print(f"\n  readout: quadrature '{oper}', separation {max(lo, up):.0f}, "
          f"F={disc['fidelity']:.3f}, threshold {thr}")

    acc = {}

    def rec(k, v):
        acc.setdefault(k, []).append(v)

    banner("STAGE 2 -- (A) readout -> pi delay, scored by whether the PI STILL WORKS")
    print("  force_flip makes the conditional pi fire unconditionally, so one forced pi")
    print("  from |g> lands the qubit in |e> if and only if the pi is healthy.  It is")
    print("  compared against a pi with NO readout in front of it (prep |e>, no reset),")
    print("  which is the same pulse under clean conditions.  Ratio 1.0 = photons are")
    print("  not hurting the pi.  Ratio < 1.0 = they are, and the delay is too short.")
    t0 = time.time()
    for r in range(ROUNDS):
        ag = gate(soc, soccfg, cfg, False, False, thr, gb, oper, 1,
                  BASE_SYNCDELAY_US, BASE_CLEAR_US)
        ae = gate(soc, soccfg, cfg, True, False, thr, gb, oper, 1,
                  BASE_SYNCDELAY_US, BASE_CLEAR_US)
        proj = projector(ag, ae)
        for sd in SYNCDELAY_SWEEP_US:
            try:
                v = gate(soc, soccfg, cfg, False, True, thr, gb, oper, 1,
                         sd, BASE_CLEAR_US, force_flip=True)
                rec(("sync", sd), proj(*v))
            except ValueError as exc:
                rec(("sync", sd), np.nan)
                if r == 0:
                    print(f"    syncdelay {sd:g} us rejected by the timing guard: "
                          f"{str(exc)[:70]}")
        print(f"  round {r + 1}/{ROUNDS} ({time.time() - t0:.0f} s)", flush=True)
    print(f"\n  {'syncdelay':>10s} {'pi reaches':>18s} {'cost/shot':>11s}")
    best_sd, best_v = None, -np.inf
    for sd in SYNCDELAY_SWEEP_US:
        m, e = stat(acc[("sync", sd)])
        print(f"  {sd:>10.1f} {m:>11.4f}+-{e:<6.4f} {RESET_ITERS * sd:>9.1f} us")
        if np.isfinite(m) and m > best_v:
            best_v, best_sd = m, sd
    ok = [(sd, *stat(acc[("sync", sd)])) for sd in SYNCDELAY_SWEEP_US
          if np.isfinite(stat(acc[("sync", sd)])[0])]
    if len(ok) >= 3:
        lo_sd, hi_sd = ok[0], ok[-1]
        d = hi_sd[1] - lo_sd[1]
        de = np.hypot(lo_sd[2], hi_sd[2])
        print(f"\n  change from {lo_sd[0]:g} us to {hi_sd[0]:g} us: {d:+.4f} +- {de:.4f} "
              f"({abs(d) / max(de, 1e-9):.1f} sigma)")
        knee = next((sd for sd, m, e in ok if m >= 0.98 * best_v), best_sd)
        print(f"  the pi stops improving at reset_meas_syncdelay_us = {knee:g} us")
        print(f"  -> that is the ring-down requirement, measured on the thing that")
        print(f"     actually cares.  Cost {RESET_ITERS * knee:.1f} us per shot at "
              f"{RESET_ITERS} iterations.")
    else:
        knee = BASE_SYNCDELAY_US
        print("  too few valid points to locate a knee.")

    banner("STAGE 3 -- (B) post-loop delay, swept INDEPENDENTLY")
    print(f"  Held at the stage-2 choice reset_meas_syncdelay_us = {knee:g} us, so this")
    print("  sweep cannot absorb a ring-down effect that belongs to (A).")
    print("  The pi is disabled (threshold far beyond the blobs), so anything that")
    print("  moves here is the readout acting on the qubit, not the reset logic.")
    for r in range(ROUNDS):
        ag = gate(soc, soccfg, cfg, False, False, thr, gb, oper, 1, knee, BASE_CLEAR_US)
        ae = gate(soc, soccfg, cfg, True, False, thr, gb, oper, 1, knee, BASE_CLEAR_US)
        proj = projector(ag, ae)
        for cu in CLEAR_SWEEP_US:
            v = gate(soc, soccfg, cfg, False, True, NEVER_FIRE_THRESHOLD, True, oper,
                     RESET_ITERS, knee, cu)
            rec(("clear_g", cu), proj(*v))
            v = gate(soc, soccfg, cfg, False, True, thr, gb, oper, RESET_ITERS, knee, cu)
            rec(("clear_real", cu), proj(*v))
        print(f"  round {r + 1}/{ROUNDS}", flush=True)
    print(f"\n  {'clear':>8s} {'pi disabled':>18s} {'real reset':>18s} {'cost/shot':>10s}")
    for cu in CLEAR_SWEEP_US:
        a, ae_ = stat(acc[("clear_g", cu)])
        b, be = stat(acc[("clear_real", cu)])
        print(f"  {cu:>8.1f} {a:>11.4f}+-{ae_:<6.4f} {b:>11.4f}+-{be:<6.4f} "
              f"{cu:>8.1f} us")
    a0, e0 = stat(acc[("clear_real", CLEAR_SWEEP_US[0])])
    a1, e1 = stat(acc[("clear_real", CLEAR_SWEEP_US[-1])])
    d, de = a0 - a1, np.hypot(e0, e1)
    print(f"\n  real reset, {CLEAR_SWEEP_US[0]:g} us vs {CLEAR_SWEEP_US[-1]:g} us: "
          f"{d:+.4f} +- {de:.4f} ({abs(d) / max(de, 1e-9):.1f} sigma)")

    banner("VERDICT")
    if rd is not None and np.isfinite(rd.get("tau_us", np.nan)):
        print(f"  measured ring-down tau = {rd['tau_us'] * 1e3:.0f} ns")
    print(f"  (A) reset_meas_syncdelay_us -> {knee:g} us   "
          f"[guards the pi from photons; costs {RESET_ITERS}x per shot]")
    vals = [(cu, stat(acc[("clear_real", cu)])[0], stat(acc[("clear_real", cu)])[1])
            for cu in CLEAR_SWEEP_US]
    vals = [v for v in vals if np.isfinite(v[1])]
    if vals:
        best = min(vals, key=lambda v: v[1])
        cheap = next((v for v in vals if v[1] <= best[1] + np.hypot(v[2], best[2])), best)
        print(f"  (B) reset_thermalization_us -> {cheap[0]:g} us   "
              f"[cheapest value statistically indistinguishable from the best, "
              f"{best[0]:g} us]")
        if abs(d) <= 2 * de:
            print(f"      the whole sweep is flat to within {2 * de:.3f}; (B) is not")
            print(f"      doing real work here and the cheap value is the right one.")
    print(f"\n  Set these in Helpers/active_reset.py defaults and in the runners only")
    print(f"  after seeing these numbers -- not before.")

    banner("done -- paste the whole log back")


if __name__ == "__main__":
    main()
