"""
Hardware-in-the-loop verification of the Modified Ramsey pulse sequence timing.

Runs against a live RFSoC (Pyro4 QICK server) but needs NO cold device: every
check below is about the *emitted tProc schedule*, not about qubit physics.

    python WorkingProjects/QM_Team/qubit_measurements/Client_modules/Experiments/verify_ModifiedRamsey_timing.py [--ns-host 192.168.0.103] [--acquire]

Phase 1 (compile-only, always runs):
  1. Real clock domains from soccfg.
  2. Compile ModifiedRamseyProgram and walk the emitted assembly.
  3. Sum the synci/sync ledger inside LOOP_J  ==  modified_ramsey_timing().
  4. Reconstruct pulse start/centre times -> assert realized centre-to-centre
     tau equals the requested 1/(2*df).   <-- the bug that was fixed
  5. Register-collision check against the REAL page/register allocation.
  6. condj/label placement: both reset branches must cost identical time.
  7. Guard checks: unreachable df raises; cmp_offset bounds; flattop raises.

Phase 2 (--acquire, drives the tProc):
  8. Short run at ZERO DAC gain (electrically inert) to check buffer shape,
     reads-per-rep striding, and measured-vs-scheduled rep cadence.
"""
import argparse
import os
import sys

import numpy as np

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), *[".."] * 5))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mModifiedRamsey import (  # noqa: E402
    ModifiedRamseyProgram,
)
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Runners.runs.charge_parity import (  # noqa: E402
    modified_ramsey_timing,
)

PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"\n         {detail}" if detail else ""))
    return ok


def base_cfg(soccfg, **over):
    """The cfg ModifiedRamseyProgram actually receives from run_modified_ramsey,
    reconstructed from BaseConfig + build_context + mr_cfg (CSTQ03, qubit 6)."""
    cfg = {
        "res_ch": 0, "qubit_ch": 1, "ro_chs": [0],
        "nqz": 2, "qubit_nqz": 1,
        "res_phase": 0,
        "adc_trig_offset": 1,          # us   (initialize4Q.py:30)
        "readout_length": 15,          # us   (context.py:152)
        "length": 16,                  # us   (context.py:160)
        "pulse_gain": 800,             # cavity_gain, qubit 6
        "pulse_freq": 7285.11,         # MHz
        "sigma": 0.1,                  # us   (Qubit_Parameters['6'])
        "flattop_length": None,
        "pi_gain": 4600, "pi2_gain": 2375,
        "f_ge": 3055.2, "df": 0.5,
        "use_pi_pulse": False, "flip_final_pi2": False, "symmetric_ramsey": False,
        "use_active_reset": False,
        "mr_relax_delay": 0.0,
        "reps": 1000, "rounds": 1,
    }
    cfg.update(over)
    return cfg


def walk(prog, r_wait_cycles):
    """Replay the compiled ASM and return the per-rep schedule.

    Returns (ledger_cycles, events) where events are (tproc_time, kind, detail)
    for every pulse `set` and ADC `seti` inside the LOOP_J body. tProc time is
    measured from the top of the rep.
    """
    plist = prog.prog_list
    start = next(i for i, x in enumerate(plist) if x.get("label") == "LOOP_J")
    end = next(i for i, x in enumerate(plist) if x["name"] == "loopnz")

    t = 0
    events = []
    for inst in plist[start:end]:
        n, a = inst["name"], inst["args"]
        if n == "synci":
            t += a[0]
        elif n == "sync":
            t += r_wait_cycles          # the only register ever synced on
        elif n == "set":
            # set(ch, page, ..., r_t) -- pulse time lives in register r_t, whose
            # value was written by the immediately preceding safe_regwi.
            events.append((t, "set", inst))
        elif n == "seti":
            events.append((t, "seti", inst))
    return t, events


def pulse_times(prog, r_wait_cycles):
    """Absolute tProc start time of each generator pulse in one rep, by
    replaying regwi->t and the sync ledger together."""
    plist = prog.prog_list
    start = next(i for i, x in enumerate(plist) if x.get("label") == "LOOP_J")
    end = next(i for i, x in enumerate(plist) if x["name"] == "loopnz")

    regs = {}          # (page, reg) -> value
    t_ref = 0
    out = []           # (tproc_ch, absolute_start_cycles)
    for inst in plist[start:end]:
        n, a = inst["name"], inst["args"]
        if n == "regwi":
            regs[(a[0], a[1])] = a[2]
        elif n == "synci":
            t_ref += a[0]
        elif n == "sync":
            t_ref += r_wait_cycles
        elif n == "set":
            tproc_ch, page, r_t = a[0], a[1], a[7]
            out.append((tproc_ch, t_ref + regs.get((page, r_t), 0)))
    return out


def phase1(soccfg):
    ok_all = True
    f_time = float(soccfg["tprocs"][0]["f_time"])
    qf = float(soccfg["gens"][1]["f_fabric"])
    rf = float(soccfg["gens"][0]["f_fabric"])
    fo = float(soccfg["readouts"][0]["f_output"])

    print("\n=== 1. Real clock domains ===")
    print(f"  tProc f_time      = {f_time:.4f} MHz")
    print(f"  gen0 (res)  f_fab = {rf:.4f} MHz")
    print(f"  gen1 (qub)  f_fab = {qf:.4f} MHz")
    print(f"  ro0        f_out  = {fo:.4f} MHz")
    print(f"  avg_maxlen        = {soccfg['readouts'][0].get('avg_maxlen')}")
    print(f"  buf_maxlen        = {soccfg['readouts'][0].get('buf_maxlen')}")

    for label, over in [
        ("standard, no reset", {}),
        ("symmetric drive", {"symmetric_ramsey": True}),
        ("echo (null control)", {"use_pi_pulse": True}),
        ("active reset x1", {"use_active_reset": True, "reset_cycles": 1,
                             "readout_threshold": 0.0,
                             "reset_readout_relax_delay": 5.0}),
        ("active reset x2", {"use_active_reset": True, "reset_cycles": 2,
                             "readout_threshold": 0.0,
                             "reset_readout_relax_delay": 5.0}),
    ]:
        print(f"\n=== variant: {label} ===")
        cfg = base_cfg(soccfg, **over)
        prog = ModifiedRamseyProgram(soccfg, cfg)
        model = modified_ramsey_timing(soccfg, dict(cfg))

        # --- 3. synci ledger vs the timing model -------------------------
        ledger, _ = walk(prog, prog.wait_cycles)
        ok_all &= check(
            f"[{label}] emitted synci ledger == modified_ramsey_timing()",
            ledger == model["scheduled_rep_period_tproc_cycles"],
            f"emitted {ledger} cyc ({ledger/f_time:.4f} us)   "
            f"model {model['scheduled_rep_period_tproc_cycles']} cyc "
            f"({model['scheduled_rep_period_us']:.4f} us)",
        )

        # --- 4. realized centre-to-centre tau ----------------------------
        qubit_tproc_ch = soccfg["gens"][1]["tproc_ch"]
        starts = [t for ch, t in pulse_times(prog, prog.wait_cycles)
                  if ch == qubit_tproc_ch]
        n_reset_pi = prog.reset_cycles
        ramsey_starts = starts[n_reset_pi:]          # drop the reset pi pulses
        env = prog.pulse_us * f_time                 # envelope, tProc cycles
        c2c = (ramsey_starts[-1] + env / 2) - (ramsey_starts[0] + env / 2)
        c2c_us = c2c / f_time
        want = 1.0 / (2.0 * cfg["df"])
        ok_all &= check(
            f"[{label}] realized pi/2 centre-to-centre == 1/(2*df)",
            abs(c2c_us - want) < 2.0 / f_time,
            f"realized {c2c_us:.6f} us vs requested {want:.6f} us "
            f"(err {(c2c_us-want)*1e3:+.2f} ns; program reports "
            f"effective_tau_us={prog.effective_tau_us:.6f}); "
            f"parity phase = {2*c2c_us*cfg['df']:.5f} pi",
        )
        ok_all &= check(
            f"[{label}] program.effective_tau_us matches the walked schedule",
            abs(prog.effective_tau_us - c2c_us) < 2.0 / f_time,
        )
        ok_all &= check(
            f"[{label}] timing model effective_tau_us agrees with program",
            abs(model["effective_tau_us"] - prog.effective_tau_us) < 1e-9,
            f"model {model['effective_tau_us']:.9f} vs prog {prog.effective_tau_us:.9f}",
        )

        # --- 5. register collisions, against the REAL allocation ---------
        used = {v for k, v in prog._gen_regmap.items() if k[0] != "0"}
        page_regs = {r for (ch, name), (p, r) in prog._gen_regmap.items()
                     if p == prog.q_rp and name != "0"}
        mine = {prog.r_wait, prog.r_read, prog.r_thresh}
        reserved_p0 = {13, 14, 15, 16, 17, 18, 19, 20, 21} if prog.q_rp == 0 else set()
        ok_all &= check(
            f"[{label}] r_wait/r_read/r_thresh free on page {prog.q_rp}",
            not (mine & page_regs) and not (mine & reserved_p0),
            f"mine={sorted(mine)}  pulse_regs_on_page={sorted(page_regs)}  "
            f"framework_reserved={sorted(reserved_p0)}",
        )
        del used

        # --- 6. conditional-pi branches cost the same --------------------
        if prog.reset_cycles:
            pl = prog.prog_list
            for i in range(prog.reset_cycles):
                lbl = f"RESET_DONE_{i}"
                j = next(k for k, x in enumerate(pl) if x.get("label") == lbl)
                ok_all &= check(
                    f"[{label}] {lbl} lands on the shared synci (equal-time branches)",
                    pl[j]["name"] == "synci",
                    f"label sits on '{pl[j]['name']}' args={pl[j]['args']}",
                )

        # --- tone coverage on the real clocks ----------------------------
        ok_all &= check(
            f"[{label}] resonator tone covers adc_trig_offset + window",
            model["tone_coverage_margin_us"] >= 0,
            f"margin {model['tone_coverage_margin_us']*1e3:+.2f} ns, "
            f"quantization extension {model['tone_quantization_extension_cycles']} gen cyc",
        )

        if over.get("use_active_reset"):
            ro_norm = prog.readout_window_cycles[0]
            ok_all &= check(
                f"[{label}] cmp_offset covers full accumulator range and fits 2^30",
                prog.cmp_offset == int(ro_norm) << 15 and prog.cmp_offset < (1 << 30),
                f"ro_norm={ro_norm} cyc, cmp_offset={prog.cmp_offset} "
                f"(2^24 was {1<<24} -> old margin {(1<<24)/(int(ro_norm)<<15):.3f}x)",
            )

    # --- 7. guards -------------------------------------------------------
    print("\n=== 7. Guards ===")
    pulse_us = ModifiedRamseyProgram(soccfg, base_cfg(soccfg)).pulse_us
    df_bad = 1.0 / (2.0 * pulse_us) * 1.05      # tau just under one envelope
    try:
        ModifiedRamseyProgram(soccfg, base_cfg(soccfg, df=df_bad))
        ok_all &= check(f"unreachable df={df_bad:.3f} MHz raises", False)
    except ValueError as e:
        ok_all &= check(f"unreachable df={df_bad:.3f} MHz raises", True, str(e)[:200])

    try:
        ModifiedRamseyProgram(soccfg, base_cfg(soccfg, flattop_length=1))
        ok_all &= check("flattop_length set raises", False)
    except ValueError as e:
        ok_all &= check("flattop_length set raises", True, str(e)[:120])

    print(f"\n  usable df range at sigma=0.1 us: df < {1.0/(2*pulse_us):.4f} MHz "
          f"(no pi), < {1.0/(4*pulse_us):.4f} MHz (echo)")
    return ok_all


def phase2(soc, soccfg, reps=4000):
    """Drive the tProc at ZERO DAC gain: electrically inert, timing identical."""
    print(f"\n=== 8. Live cadence check ({reps} reps, DAC gain = 0) ===")
    cfg = base_cfg(soccfg, reps=reps, pulse_gain=0, pi_gain=0, pi2_gain=0)
    prog = ModifiedRamseyProgram(soccfg, cfg)
    model = modified_ramsey_timing(soccfg, dict(cfg))

    shots_i, shots_q = prog.acquire(soc, load_pulses=True, progress=False)
    shots_i = np.asarray(shots_i).ravel()

    ok = check("returned shot count == cfg['reps']", shots_i.size == reps,
               f"got {shots_i.size}")

    nreads = prog.reset_cycles + 1
    ok &= check("raw buffer length == reps * (reset_cycles+1)",
                prog.di_buf[0].size == reps * nreads,
                f"{prog.di_buf[0].size} vs {reps*nreads}")

    last_elapsed_s, last_shots, _, _ = prog.stats[-1]
    measured = last_elapsed_s * 1e6 / last_shots
    sched = model["scheduled_rep_period_us"]
    frac = (measured - sched) / sched
    ok &= check("measured rep period within 3% of scheduled",
                abs(frac) < 0.03,
                f"scheduled {sched:.4f} us, measured {measured:.4f} us "
                f"({frac*100:+.2f}%); {last_shots} shots in {last_elapsed_s:.4f} s")
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ns-host", default="192.168.0.103")
    ap.add_argument("--ns-port", type=int, default=8888)
    ap.add_argument("--proxy-name", default="myqick")
    ap.add_argument("--acquire", action="store_true",
                    help="also run the tProc (zero DAC gain) for the cadence check")
    ap.add_argument("--reps", type=int, default=4000)
    args = ap.parse_args()

    import Pyro4
    from qick import QickConfig
    Pyro4.config.SERIALIZER = "pickle"
    Pyro4.config.PICKLE_PROTOCOL_VERSION = 4
    ns = Pyro4.locateNS(host=args.ns_host, port=args.ns_port)
    soc = Pyro4.Proxy(ns.lookup(args.proxy_name))
    soccfg = QickConfig(soc.get_cfg())
    print(f"connected to {args.proxy_name} @ {args.ns_host}:{args.ns_port}")

    phase1(soccfg)
    if args.acquire:
        phase2(soc, soccfg, reps=args.reps)

    print(f"\n================ {len(PASS)} passed, {len(FAIL)} failed ================")
    for f in FAIL:
        print(f"  FAILED: {f}")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
