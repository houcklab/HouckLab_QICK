import time

import numpy as np
from qick import AveragerProgram

from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.socProxy import makeProxy
from WorkingProjects.TLS_Spectroscopy.Client_modules.Calib.initialize import BaseConfig, outerFolder
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mActiveResetProbe import (
    ReadProbeProgram, ResetCheckProgram,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import active_reset as ar
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import ff_pulse
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import tee_log
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.pulse_setup import (
    set_readout_pulse, readout_drive_length_us,
)

QUBIT = "q4"

RINGDOWN_TAIL_US = 60.0
RINGDOWN_SOFT_AVGS = 200
RINGDOWN_BUF_FRACTION = 0.95

SYNCDELAY_MIN_US = 3.5
SYNCDELAY_SWEEP_US = [3.5, 5.0, 8.0, 12.0, 18.0, 25.0, 40.0]
CLEAR_SWEEP_US = [0.0, 0.5, 2.0, 5.0, 10.0, 25.0, 50.0]

ROUNDS = 20
REF_SHOTS = 4000
GATE_SHOTS = 1000
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
        cfg["reps"] = 1
        ro = cfg["ro_chs"][0]
        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"],
                         mixer_freq=cfg.get("mixer_freq", 0), ro_ch=ro)
        ff_pulse.declare_static_park(self)
        self.declare_readout(ch=ro, freq=cfg["read_pulse_freq"],
                             length=self.us2cycles(cfg["capture_us"], ro_ch=ro),
                             gen_ch=cfg["res_ch"])
        set_readout_pulse(self, self.freq2reg(cfg["read_pulse_freq"],
                                              gen_ch=cfg["res_ch"], ro_ch=ro),
                          length_us=float(cfg["ringdown_drive_us"]))
        self.synci(200)

    def body(self):
        cfg = self.cfg
        ff_pulse.play_static_park(self, settle_us=cfg.get("ff_park_settle_us", 0.05))
        self.trigger(adcs=cfg["ro_chs"],
                     adc_trig_offset=self.us2cycles(cfg["ringdown_trig_offset_us"]))
        self.pulse(ch=cfg["res_ch"])
        self.wait_all()
        self.sync_all(self.us2cycles(cfg.get("relax_delay", 200.0)))


def decimated_budget_us(soccfg, ro):
    maxlen = None
    for key in ("buf_maxlen", "avg_buf_maxlen", "maxlen"):
        try:
            maxlen = int(soccfg['readouts'][ro][key])
            break
        except Exception:
            continue
    if not maxlen:
        maxlen = 1024
    try:
        return float(soccfg.cycles2us(maxlen, ro_ch=ro)), maxlen
    except Exception:
        pass
    try:
        return maxlen / float(soccfg['readouts'][ro]['f_fabric']), maxlen
    except Exception:
        return 2.5, maxlen


def measure_ringdown(soc, soccfg, cfg):
    ro = cfg["ro_chs"][0]
    budget_us, maxlen = decimated_budget_us(soccfg, ro)
    win = float(budget_us) * RINGDOWN_BUF_FRACTION
    drive = float(readout_drive_length_us(cfg))
    span = drive + RINGDOWN_TAIL_US
    offsets = np.arange(0.0, span, win * 0.9)
    print(f"  the decimated buffer holds {maxlen} samples = {budget_us:.2f} us, but the")
    print(f"  readout drive alone is {drive:.2f} us, so no single capture can see the")
    print(f"  decay.  Stepping the ADC trigger across {span:.0f} us in {len(offsets)} "
          f"windows of")
    print(f"  {win:.2f} us and stitching them.  The drive is the REAL readout pulse, so")
    print(f"  the resonator is filled exactly as it is during a reset iteration.")
    ts, mags = [], []
    dt_us = None
    for off in offsets:
        c = dict(cfg)
        c["capture_us"] = win
        c["ringdown_drive_us"] = drive
        c["ringdown_trig_offset_us"] = float(off)
        c["reps"] = 1
        c["soft_avgs"] = int(RINGDOWN_SOFT_AVGS)
        c["relax_delay"] = 50.0
        try:
            prog = RingdownProgram(soccfg, c)
            out = prog.acquire_decimated(soc, load_pulses=True, progress=False)
        except Exception as exc:
            print(f"  capture at offset {off:.2f} us failed ({exc}); stopping the sweep.")
            break
        arr = np.asarray(out[0], dtype=float)
        if arr.ndim == 2 and arr.shape[1] == 2:
            I, Q = arr[:, 0], arr[:, 1]
        else:
            I, Q = arr[0], arr[1]
        mag = np.hypot(I, Q)
        if dt_us is None:
            try:
                dt_us = 1.0 / float(soccfg['readouts'][ro]['f_fabric'])
            except Exception:
                dt_us = win / max(mag.size, 1)
        ts.append(np.arange(mag.size) * dt_us + off)
        mags.append(mag)
    if not ts:
        print("  no window captured; skipping the direct kappa measurement.")
        return None
    t = np.concatenate(ts)
    mag = np.concatenate(mags)
    order = np.argsort(t)
    t, mag = t[order], mag[order]
    fit_from = drive * 1.02
    sel = t >= fit_from
    if sel.sum() < 10:
        return {"t": t, "mag": mag, "dt_us": dt_us, "drive_us": drive,
                "tau_us": np.nan, "peak_us": float(t[int(np.argmax(mag))]),
                "tail_us": float(t[-1] - fit_from), "fit_pts": 0}
    tt, mm = t[sel], mag[sel]
    base = float(np.median(mm[-max(5, mm.size // 6):]))
    y = mm - base
    good = y > 0.05 * max(y.max(), 1e-9)
    tau = np.nan
    if good.sum() >= 6:
        sl = np.polyfit(tt[good], np.log(y[good]), 1)[0]
        tau = -1.0 / sl if sl < 0 else np.nan
    return {"t": t, "mag": mag, "dt_us": dt_us, "drive_us": drive, "tau_us": tau,
            "peak_us": float(t[int(np.argmax(mag))]),
            "tail_us": float(t[-1] - fit_from), "fit_pts": int(good.sum())}


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


def gate_pe(soc, soccfg, cfg, prep, do_reset, thr, gb, oper, iters,
            syncdelay_us, clear_us, ref_thr, ref_gb, force_flip=False):
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
    prog = ResetCheckProgram(soccfg, c)
    prog.acquire(soc, load_pulses=True)
    lo, up = prog.shots()
    if lo is None:
        return float("nan")
    v = (lo if oper == "lower" else up)[:, -1].astype(float)
    return float(np.mean(v >= ref_thr)) if ref_gb else float(np.mean(v <= ref_thr))


def stat(v):
    v = np.asarray([x for x in v if np.isfinite(x)], dtype=float)
    if v.size == 0:
        return np.nan, np.nan
    return float(np.mean(v)), float(np.std(v) / max(1.0, np.sqrt(v.size - 1)))


def run():
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
        top = float(np.max(rd["mag"]))
        med = float(np.median(rd["mag"]))
        if top < 5.0 * max(med, 1e-9) or top < 50.0:
            print(f"\n  NO SIGNAL: the stitched trace peaks at {top:.0f} against a median")
            print(f"  of {med:.0f}.  The ADC never saw the readout tone, so any tau fitted")
            print(f"  from it is meaningless.  Ignore stage 1; stage 2 still measures the")
            print(f"  delay the pi actually needs, which is the number that matters.")
            rd["tau_us"] = float("nan")
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
        step = max(1, rd["mag"].size // 60)
        print(f"\n  stitched trace (every {step} samples, drive ends at "
              f"{rd['drive_us']:.2f} us):")
        top = max(rd["mag"].max(), 1e-9)
        for i in range(0, rd["mag"].size, step):
            bar = "#" * int(48 * rd["mag"][i] / top)
            mark = " <- drive ends" if abs(rd["t"][i] - rd["drive_us"]) < step * rd["dt_us"] else ""
            print(f"    {rd['t'][i]:>7.2f} us {rd['mag'][i]:>10.0f} {bar}{mark}")

    ref = ge_reference(soc, soccfg, cfg, REF_SHOTS)
    lo = abs(np.median(ref["e"]["lower"]) - np.median(ref["g"]["lower"]))
    up = abs(np.median(ref["e"]["upper"]) - np.median(ref["g"]["upper"]))
    oper = "lower" if lo >= up else "upper"
    disc = ar.fit_assignment_threshold(ref["g"][oper][::2], ref["e"][oper][::2])
    thr, gb = int(disc["threshold_raw"]), bool(disc["ground_below"])
    ref_g, ref_e = ref["g"][oper], ref["e"][oper]
    print(f"\n  readout: quadrature '{oper}', separation {max(lo, up):.0f}, "
          f"F={disc['fidelity']:.3f}, threshold {thr}")

    tau_meas = rd["tau_us"] if (rd is not None and np.isfinite(rd.get("tau_us", np.nan))
                                and rd["tail_us"] >= 2.0 * rd["tau_us"]) else None
    if tau_meas is not None:
        lo_sd = float(SYNCDELAY_MIN_US)
        hi_sd = float(max(12.0, 8.0 * tau_meas))
        sweep = sorted({round(float(v), 2)
                        for v in np.geomspace(lo_sd, hi_sd, 7)})
        print(f"\n  the (A) sweep is built from the measured tau: {sweep} us")
        print(f"  that spans {lo_sd / tau_meas:.1f}..{hi_sd / tau_meas:.1f} tau.  The low")
        print(f"  end is floored at {lo_sd:g} us because reset_read_delay_us "
              f"({RESET_READ_DELAY_US:g} us)")
        print(f"  plus the {ar.MIN_READ_TO_PULSE_GAP_US:g} us guard has to fit before "
              f"the pi.")
        if lo_sd >= 5.0 * tau_meas:
            print(f"  NOTE even the shortest delay the timing guard allows is already")
            print(f"  {lo_sd / tau_meas:.1f} tau, so ring-down cannot be hurting the pi.")
            print(f"  The sweep below is a confirmation, not a search.")
    else:
        sweep = list(SYNCDELAY_SWEEP_US)
        print(f"\n  no trustworthy tau, so the (A) sweep uses the default grid: "
              f"{sweep} us")

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
        clean = gate_pe(soc, soccfg, cfg, True, False, thr, gb, oper, 1,
                        BASE_SYNCDELAY_US, BASE_CLEAR_US, thr, gb)
        rec(("clean_pi",), clean)
        for sd in sweep:
            try:
                v = gate_pe(soc, soccfg, cfg, False, True, thr, gb, oper, 1,
                            sd, BASE_CLEAR_US, thr, gb, force_flip=True)
                rec(("sync", sd), v / clean if clean > 0.05 else np.nan)
                rec(("sync_raw", sd), v)
            except ValueError as exc:
                rec(("sync", sd), np.nan)
                rec(("sync_raw", sd), np.nan)
                if r == 0:
                    print(f"    syncdelay {sd:g} us rejected by the timing guard: "
                          f"{str(exc)[:70]}")
        if r == 0 or (r + 1) % 5 == 0:
            print(f"  round {r + 1}/{ROUNDS} ({time.time() - t0:.0f} s)", flush=True)
    cm, ce = stat(acc[("clean_pi",)])
    print(f"\n  a clean pi (no readout in front of it) reaches P(excited) = "
          f"{cm:.4f} +- {ce:.4f}")
    print(f"  shot-noise floor at {GATE_SHOTS} shots x {ROUNDS} rounds: "
          f"{np.sqrt(0.25 / (GATE_SHOTS * ROUNDS)):.4f}")
    print(f"\n  {'syncdelay':>10s} {'P(exc)':>9s} {'/clean pi':>18s} {'cost/shot':>11s}")
    best_sd, best_v = None, -np.inf
    for sd in sweep:
        m, e = stat(acc[("sync", sd)])
        rm, _ = stat(acc[("sync_raw", sd)])
        print(f"  {sd:>10.1f} {rm:>9.4f} {m:>11.4f}+-{e:<6.4f} "
              f"{RESET_ITERS * sd:>9.1f} us")
        if np.isfinite(m) and m > best_v:
            best_v, best_sd = m, sd
    ok = [(sd, *stat(acc[("sync", sd)])) for sd in sweep
          if np.isfinite(stat(acc[("sync", sd)])[0])]
    knee = BASE_SYNCDELAY_US
    if len(ok) >= 3:
        y = np.array([m for _, m, _ in ok])
        e = np.array([max(err, 1e-6) for _, _, err in ok])
        w = 1.0 / e ** 2
        mu = float((w * y).sum() / w.sum())
        chi = float((((y - mu) / e) ** 2).sum())
        dof = len(y) - 1
        print(f"\n  is there ANY dependence on the delay?")
        print(f"    weighted mean {mu:.4f}, chi2 against a flat line = {chi:.1f} "
              f"for {dof} dof")
        if chi < dof + 2.0 * np.sqrt(2.0 * dof):
            print(f"    -> NO.  The sweep is flat: the pi does not care about this delay")
            print(f"       over {ok[0][0]:g}..{ok[-1][0]:g} us, so ring-down is already")
            print(f"       cleared by the time the pi fires.  Take the CHEAPEST value.")
            knee = ok[0][0]
        else:
            best_v = max(m for _, m, _ in ok)
            knee = next((sd for sd, m, _ in ok if m >= 0.98 * best_v), best_sd)
            print(f"    -> YES.  The pi stops improving at "
                  f"reset_meas_syncdelay_us = {knee:g} us.")
            print(f"       That is the ring-down requirement, measured on the thing")
            print(f"       that actually cares.")
        print(f"  cost of {knee:g} us: {RESET_ITERS * knee:.1f} us per shot at "
              f"{RESET_ITERS} iterations")
    else:
        print("  too few valid points to judge; keeping the current value.")

    banner("STAGE 3 -- (B) post-loop delay, swept INDEPENDENTLY")
    print(f"  Held at the stage-2 choice reset_meas_syncdelay_us = {knee:g} us, so this")
    print("  sweep cannot absorb a ring-down effect that belongs to (A).")
    print("  The pi is disabled (threshold far beyond the blobs), so anything that")
    print("  moves here is the readout acting on the qubit, not the reset logic.")
    for r in range(ROUNDS):
        for cu in CLEAR_SWEEP_US:
            rec(("clear_g", cu), gate_pe(
                soc, soccfg, cfg, False, True, NEVER_FIRE_THRESHOLD, True, oper,
                RESET_ITERS, knee, cu, thr, gb))
            rec(("clear_real", cu), gate_pe(
                soc, soccfg, cfg, False, True, thr, gb, oper, RESET_ITERS, knee, cu,
                thr, gb))
        if r == 0 or (r + 1) % 5 == 0:
            print(f"  round {r + 1}/{ROUNDS}", flush=True)
    print(f"\n  {'clear':>8s} {'pi disabled':>18s} {'real reset':>18s} {'cost/shot':>10s}")
    for cu in CLEAR_SWEEP_US:
        a, ae_ = stat(acc[("clear_g", cu)])
        b, be = stat(acc[("clear_real", cu)])
        print(f"  {cu:>8.1f} {a:>11.4f}+-{ae_:<6.4f} {b:>11.4f}+-{be:<6.4f} "
              f"{cu:>8.1f} us")
    gvals = np.array([stat(acc[("clear_g", cu)])[0] for cu in CLEAR_SWEEP_US])
    peg0, pge0 = ar._threshold_rates(ref_g, ref_e, 0, True)
    floor0 = ar.reset_floor(peg0, pge0)
    print(f"\n  SANITY: the 'pi disabled' column is only meaningful if the huge threshold")
    print(f"  ({NEVER_FIRE_THRESHOLD}) really did disable the pi.  The failure mode is regwi")
    print(f"  truncating that immediate.  If it truncated toward 0 the effective threshold")
    print(f"  would sit between the blobs and prep |g> would be driven to that threshold's")
    print(f"  floor, {floor0:.3f}.  Measured: {np.nanmin(gvals):.3f}..{np.nanmax(gvals):.3f}.")
    if np.nanmax(gvals) > 0.6 * floor0 + 0.15:
        print(f"  *** prep |g> was driven upward -- the pi WAS firing.  Stage 3 is invalid. ***")
    else:
        print(f"  -> far below {floor0:.3f}, so the pi never fired.  Stage 3 is valid.")

    yy = np.array([stat(acc[("clear_real", cu)])[0] for cu in CLEAR_SWEEP_US])
    ee = np.array([max(stat(acc[("clear_real", cu)])[1], 1e-6) for cu in CLEAR_SWEEP_US])
    fin = np.isfinite(yy)
    if fin.sum() >= 3:
        w = 1.0 / ee[fin] ** 2
        mu = float((w * yy[fin]).sum() / w.sum())
        chi = float((((yy[fin] - mu) / ee[fin]) ** 2).sum())
        dof = int(fin.sum()) - 1
        print(f"\n  weighted mean {mu:.4f}, chi2 against a flat line = {chi:.1f} "
              f"for {dof} dof")
        clear_flat = chi < dof + 2.0 * np.sqrt(2.0 * dof)
        if clear_flat:
            print(f"  -> FLAT.  reset_thermalization_us is not doing measurable work.")
        else:
            print(f"  -> NOT flat; the post-loop delay matters.  Pick the knee below.")
    else:
        clear_flat = True
        print("\n  too few valid points to judge.")

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
        cheap = (vals[0] if clear_flat else
                 next((v for v in vals if v[1] <= best[1] + np.hypot(v[2], best[2])),
                      best))
        print(f"  (B) reset_thermalization_us -> {cheap[0]:g} us   "
              f"[costs 1x per shot]")
        if clear_flat:
            print(f"      the sweep is statistically flat, so the cheapest value wins;")
            print(f"      {best[0]:g} us looked best but not significantly so.")
        else:
            print(f"      cheapest value indistinguishable from the best ({best[0]:g} us)")
    print(f"\n  Set these in Helpers/active_reset.py defaults and in the runners only")
    print(f"  after seeing these numbers -- not before.")

    banner("done -- paste the whole log back")


def main():
    with tee_log.tee("ResetDelayAudit", folder=outerFolder):
        run()


if __name__ == "__main__":
    main()
