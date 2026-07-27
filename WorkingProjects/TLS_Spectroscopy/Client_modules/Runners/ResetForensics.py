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
    add_qubit_gaussian, set_readout_pulse, readout_drive_length_us,
)

QUBIT = "q4"

RUN_STAGE_0_ENV = True
RUN_STAGE_1_REFERENCE = True
RUN_STAGE_2_FRESHNESS = True
RUN_STAGE_3_DECISIONS = True
RUN_STAGE_4_PI_CONTEXT = False
RUN_STAGE_5_END_TO_END = True
RUN_STAGE_6_READOUT_LEAKAGE = False

READOUT_GAIN_SWEEP = [1000, 2000, 3000, 4000, 5000, 7000, 10000]
READOUT_LENGTH_SWEEP_US = [2.0, 4.0, 6.0, 10.0, 16.5]

RES_PHASE = 15.0
REFERENCE_SHOTS = 2000
DIAG_RELAX_US = 1500.0

TRACE_BASE_ADDR = 200
TRACE_REPS = 20
TRACE_ACQUIRES = 12
READ_DELAY_SWEEP_US = [None, 0.1, 0.2, 0.3, 0.4, 0.5, 0.7, 1.0, 1.5, 2.0, 3.0]

END_TO_END_SHOTS = 2000
END_TO_END_ITERS = [1, 2, 3, 4]

PI_CONTEXT_SHOTS = 600
PI_CONTEXT_DELAYS_US = [0.2, 1.0, 2.0, 4.0, 8.0, 16.0]
PI_FREQ_OFFSETS_MHZ = [-3.0, -2.0, -1.0, -0.5, 0.0, 0.5, 1.0, 2.0, 3.0]
PI_GAIN_SCALES = [0.7, 0.85, 0.95, 1.0, 1.05, 1.15, 1.3]
PI_CONTEXT_DELAY_US = 4.0


def banner(text):
    print()
    print("=" * 78)
    print(text)
    print("=" * 78)


class PiContextProgram(AveragerProgram):

    def initialize(self):
        cfg = self.cfg
        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"],
                         mixer_freq=cfg.get("mixer_freq", 0), ro_ch=cfg["ro_chs"][0])
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])
        ff_pulse.declare_static_park(self)
        for ro_ch in cfg["ro_chs"]:
            self.declare_readout(ch=ro_ch, freq=cfg["read_pulse_freq"],
                                 length=self.us2cycles(cfg["read_length"], ro_ch=cfg["ro_chs"][0]),
                                 gen_ch=cfg["res_ch"])
        self.read_freq = self.freq2reg(cfg["read_pulse_freq"], gen_ch=cfg["res_ch"],
                                       ro_ch=cfg["ro_chs"][0])
        add_qubit_gaussian(self)
        self.prep_freq = self.freq2reg(cfg.get("qubit_pi_freq", cfg["qubit_freq"]),
                                       gen_ch=cfg["qubit_ch"])
        self.probe_freq = self.freq2reg(float(cfg["ctx_pi_freq"]), gen_ch=cfg["qubit_ch"])
        set_readout_pulse(self, self.read_freq)
        self.synci(200)

    def _qubit_pulse(self, freq, gain):
        self.set_pulse_registers(ch=self.cfg["qubit_ch"], style="arb", freq=freq,
                                 phase=self.deg2reg(0, gen_ch=self.cfg["qubit_ch"]),
                                 gain=int(gain), waveform="qubit")
        self.pulse(ch=self.cfg["qubit_ch"])
        self.sync_all(self.us2cycles(0.01))

    def body(self):
        cfg = self.cfg
        ff_pulse.play_static_park(self, settle_us=cfg.get("ff_park_settle_us", 0.05))
        if int(cfg["ctx_prep_gain"]) != 0:
            self._qubit_pulse(self.prep_freq, cfg["ctx_prep_gain"])
        delay_us = float(cfg["ctx_delay_us"])
        probe_len = cfg.get("ctx_ro_length_us", None)
        drive_us = (readout_drive_length_us(cfg) if probe_len is None else float(probe_len))
        if bool(cfg["ctx_do_readout"]):
            set_readout_pulse(self, self.read_freq, gain=cfg.get("ctx_ro_gain", None),
                              length_us=probe_len)
            self.measure(pulse_ch=cfg["res_ch"], adcs=cfg["ro_chs"],
                         adc_trig_offset=self.us2cycles(cfg["adc_trig_offset"]),
                         wait=True, syncdelay=None)
            self.sync_all(self.us2cycles(delay_us))
            set_readout_pulse(self, self.read_freq)
        else:
            self.sync_all(self.us2cycles(delay_us + drive_us))
        if int(cfg["ctx_pi_gain"]) != 0:
            self._qubit_pulse(self.probe_freq, cfg["ctx_pi_gain"])
        self.measure(pulse_ch=cfg["res_ch"], adcs=cfg["ro_chs"],
                     adc_trig_offset=self.us2cycles(cfg["adc_trig_offset"]),
                     wait=True, syncdelay=self.us2cycles(cfg["relax_delay"]))

    def acquire(self, soc, load_pulses=True, progress=False, **kw):
        reads = (1 if self.cfg["ctx_do_readout"] else 0) + 1
        avg_di, avg_dq = super().acquire(soc, readouts_per_experiment=reads,
                                         load_pulses=load_pulses, progress=progress)
        return float(np.asarray(avg_di)[0][-1]), float(np.asarray(avg_dq)[0][-1])


def read_trace(soc, base_addr, n_words):
    getters = (lambda a: soc.tproc.single_read(a),
               lambda a: soc.tproc.read_dmem(a, 1)[0],
               lambda a: soc.read_dmem(a, 1)[0])
    out = []
    for k in range(int(n_words)):
        addr = int(base_addr) + k
        for getter in getters:
            try:
                out.append(ar.to_signed32(getter(addr)))
                break
            except Exception:
                continue
        else:
            raise RuntimeError(
                "cannot read tProc data memory through the Pyro proxy; tell me the "
                "error so I can adapt the trace read-back to this board's API")
    return out


def raw_reads(prog, reps, reads):
    lower = np.asarray(prog.di_buf[0], dtype=np.int64).reshape(int(reps), int(reads))
    upper = np.asarray(prog.dq_buf[0], dtype=np.int64).reshape(int(reps), int(reads))
    return lower, upper


def ge_reference(soc, soccfg, cfg, shots):
    out = {}
    for label, gain in (("g", 0), ("e", int(cfg["qubit_pi_gain"]))):
        c = dict(cfg)
        c["probe_gain"] = int(gain)
        c["reps"] = c["shots"] = int(shots)
        prog = ReadProbeProgram(soccfg, c)
        avgi, avgq = prog.acquire(soc, load_pulses=True, progress=False)
        lower = np.asarray(prog.di_buf[0], dtype=np.int64).ravel()
        upper = np.asarray(prog.dq_buf[0], dtype=np.int64).ravel()
        out[label] = {"I": float(np.asarray(avgi).ravel()[0]),
                      "Q": float(np.asarray(avgq).ravel()[0]),
                      "lower": lower, "upper": upper,
                      "lower_med": float(np.median(lower)),
                      "upper_med": float(np.median(upper))}
    return out


def make_projector(ref):
    Ig, Qg = ref["g"]["I"], ref["g"]["Q"]
    dx, dy = ref["e"]["I"] - Ig, ref["e"]["Q"] - Qg
    denom = dx * dx + dy * dy

    def project(Ir, Qr):
        return (((Ir - Ig) * dx + (Qr - Qg) * dy) / denom) if denom > 0 else float("nan")
    return project


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


def stage0(soc, soccfg, cfg):
    banner("STAGE 0 -- environment, register map, compiled reset assembly")
    ro_ch = cfg["ro_chs"][0]
    tproc_ch = ar.feedback_channel(soccfg, ro_ch)
    dmem = int(soccfg['tprocs'][0]['dmem_size'])
    print(f"  readout {ro_ch}: tproc input ch = {tproc_ch}   (needs >= 0 for feedback)")
    print(f"  tProc dmem size = {dmem} words; trace base = {TRACE_BASE_ADDR}, "
          f"words = {ar.trace_word_count(cfg['reset_max_iters'])}")
    need = TRACE_BASE_ADDR + ar.trace_word_count(cfg["reset_max_iters"])
    if need > dmem:
        raise RuntimeError(f"trace needs dmem word {need} but dmem is {dmem} words")

    c = dict(cfg)
    c["reps"] = c["shots"] = 2
    c["prep_excited"] = True
    c["do_reset"] = True
    c.setdefault("reset_threshold_raw", -1)
    c.setdefault("reset_ground_below", True)
    c["reset_trace_base_addr"] = int(TRACE_BASE_ADDR)
    c["reset_read_delay_us"] = 0.1
    prog = ResetCheckProgram(soccfg, c)
    page = prog.ch_page(cfg["qubit_ch"])
    reserved = ar.reserved_registers(prog, page)
    free = sorted(set(range(1, 32)) - reserved)
    print(f"  qubit_ch={cfg['qubit_ch']} -> tProc page {page}")
    print(f"    res_ch  regs: "
          f"{ {n: prog.sreg(cfg['res_ch'], n) for n in ('freq', 'phase', 'gain', 'mode', 't')} }")
    print(f"    qubit   regs: "
          f"{ {n: prog.sreg(cfg['qubit_ch'], n) for n in ('freq', 'phase', 'gain', 'mode', 't')} }")
    print(f"    reserved on page {page}: {sorted(reserved)}")
    print(f"    free scratch on page {page}: {free}")
    print(f"    reset uses reg_val=1, reg_thr=2, reg_flag=6 -> "
          f"{'DISJOINT (ok)' if {1, 2, 6}.isdisjoint(reserved) else 'COLLISION (BUG)'}")

    asm = prog.asm().splitlines()
    lo = next((i for i, l in enumerate(asm) if "active-reset threshold" in l), None)
    if lo is not None:
        print("\n  compiled reset block (assembly as the tProc will run it):")
        for line in asm[lo:lo + 46]:
            print("    " + line)
    return prog


def stage1(soc, soccfg, cfg):
    banner("STAGE 1 -- raw |g>/|e> reference and threshold")
    ref = ge_reference(soc, soccfg, cfg, REFERENCE_SHOTS)
    sep_lower = abs(ref["e"]["lower_med"] - ref["g"]["lower_med"])
    sep_upper = abs(ref["e"]["upper_med"] - ref["g"]["upper_med"])
    oper = "lower" if sep_lower >= sep_upper else "upper"
    key = oper
    disc = fit_threshold(ref["g"][key][::2], ref["e"][key][::2])
    print(f"  res_phase = {cfg['res_phase']:.1f} deg")
    print(f"  ground  {key}: median {ref['g'][key + '_med']:>12.0f}  "
          f"std {np.std(ref['g'][key]):>10.0f}")
    print(f"  excited {key}: median {ref['e'][key + '_med']:>12.0f}  "
          f"std {np.std(ref['e'][key]):>10.0f}")
    print(f"  separation lower={sep_lower:.0f} upper={sep_upper:.0f} -> discriminate on '{oper}'")
    print(f"  threshold_raw = {disc['threshold_raw']}  ground_below = {disc['ground_below']}  "
          f"F = {disc['fidelity']:.3f}  P(e|g)={disc['p_e_given_g']:.3f} "
          f"P(g|e)={disc['p_g_given_e']:.3f}")
    return ref, oper, disc


def trace_run(soc, soccfg, cfg, read_delay_us, prep_excited, force_flip, n_acquires):
    max_iters = int(cfg["reset_max_iters"])
    reads = max_iters + 1
    oper = str(cfg.get("reset_oper", "lower"))
    rows = []
    for _ in range(int(n_acquires)):
        c = dict(cfg)
        c["reps"] = c["shots"] = int(TRACE_REPS)
        c["prep_excited"] = bool(prep_excited)
        c["do_reset"] = True
        c["reset_force_flip"] = bool(force_flip)
        c["reset_trace_base_addr"] = int(TRACE_BASE_ADDR)
        c["reset_read_delay_us"] = read_delay_us
        prog = ResetCheckProgram(soccfg, c)
        prog.acquire(soc, load_pulses=True, progress=False)
        lower, upper = raw_reads(prog, TRACE_REPS, reads)
        host = upper if oper == "upper" else lower
        words = read_trace(soc, TRACE_BASE_ADDR, ar.trace_word_count(max_iters))
        rows.append({
            "threshold_reg": words[0],
            "tproc_val": [words[1 + 2 * i] for i in range(max_iters)],
            "tproc_flip": [words[2 + 2 * i] for i in range(max_iters)],
            "host_last": host[-1].tolist(),
            "host_prev_final": int(host[-2][-1]) if TRACE_REPS > 1 else None,
        })
    return rows


def alignment_matrix(rows, max_iters):
    labels = ["prev_final"] + [f"read{k}" for k in range(max_iters + 1)]
    counts = [[0] * len(labels) for _ in range(max_iters)]
    unmatched = [0] * max_iters
    total = [0] * max_iters
    for r in rows:
        candidates = [r["host_prev_final"]] + list(r["host_last"])
        for i in range(max_iters):
            got = r["tproc_val"][i]
            total[i] += 1
            hit = False
            for j, cand in enumerate(candidates):
                if cand is not None and got == cand:
                    counts[i][j] += 1
                    hit = True
            if not hit:
                unmatched[i] += 1
    return labels, counts, unmatched, total


def print_alignment(labels, counts, unmatched, total):
    header = "      iter | " + " ".join(f"{l:>10s}" for l in labels) + " |  no match"
    print(header)
    for i, row in enumerate(counts):
        cells = " ".join(f"{c:>10d}" for c in row)
        print(f"      {i:>4d} | {cells} | {unmatched[i]:>9d}   (of {total[i]})")


def fresh_fraction(counts, total, max_iters):
    ok = 0
    n = 0
    for i in range(max_iters):
        ok += counts[i][1 + i]
        n += total[i]
    return ok / max(n, 1)


def stage2(soc, soccfg, cfg, disc):
    banner("STAGE 2 -- IS THE IN-LOOP read() FRESH?  (forced flip, prepared |g>)")
    print("  sequence per shot: [measure -> read -> UNCONDITIONAL pi] x 3 -> measure")
    print("  the true state alternates g,e,g,(e) so consecutive readouts differ hugely;")
    print("  the tProc's traced read value must match THIS iteration's host readout.")
    max_iters = int(cfg["reset_max_iters"])
    c = dict(cfg)
    c["reset_threshold_raw"] = int(disc["threshold_raw"])
    c["reset_ground_below"] = bool(disc["ground_below"])
    print("  the table counts EXACT integer matches between the tProc's traced read")
    print("  value and each candidate host readout.  A correct read puts iteration i")
    print("  on the 'read<i>' diagonal; a one-measurement-stale read sits one to the left.")
    verdicts = {}
    for delay in READ_DELAY_SWEEP_US:
        rows = trace_run(soc, soccfg, c, delay, prep_excited=False, force_flip=True,
                         n_acquires=TRACE_ACQUIRES)
        labels, counts, unmatched, total = alignment_matrix(rows, max_iters)
        verdicts[delay] = fresh_fraction(counts, total, max_iters)
        tag = "   <-- exactly what the production code does" if delay is None else ""
        print(f"\n  read_delay_us = {str(delay):>5s}{tag}")
        print_alignment(labels, counts, unmatched, total)
        print(f"    on-diagonal (correct) fraction: {100.0 * verdicts[delay]:5.1f}%")
        for r in rows[:3]:
            print(f"      host {r['host_last']}  prev_final {r['host_prev_final']}  "
                  f"tproc {r['tproc_val']}  thr_reg {r['threshold_reg']}")
    good = [d for d, f in verdicts.items() if f >= 0.98]
    print("\n  --> read matches this iteration's readout at read_delay_us in: "
          f"{[str(d) for d in good] if good else 'NONE'}")
    if verdicts.get(None, 0.0) < 0.98:
        print("  --> the production code path does NOT read this iteration's value.")
    return verdicts


def reset_residual(soc, soccfg, cfg, project, read_delay_us, max_iters, shots,
                   prep_excited, do_reset):
    c = dict(cfg)
    c["reps"] = c["shots"] = int(shots)
    c["prep_excited"] = bool(prep_excited)
    c["do_reset"] = bool(do_reset)
    c["reset_max_iters"] = int(max_iters)
    c["reset_read_delay_us"] = read_delay_us
    c["reset_force_flip"] = False
    c.pop("reset_trace_base_addr", None)
    I, Q = ResetCheckProgram(soccfg, c).acquire(soc, load_pulses=True)
    return project(I, Q)


def stage5(soc, soccfg, cfg, ref, disc, read_delay_us):
    banner("STAGE 5 -- END-TO-END RESET RESIDUAL (the gate that keeps failing)")
    project = make_projector(ref)
    c = dict(cfg)
    c["reset_threshold_raw"] = int(disc["threshold_raw"])
    c["reset_ground_below"] = bool(disc["ground_below"])
    baseline = reset_residual(soc, soccfg, c, project, None, 1, END_TO_END_SHOTS,
                              True, False)
    print(f"  no-reset baseline (prepared |e>, must be ~1.0): {baseline:+.3f}")
    print("  gate requires reset |g> < 0.2 AND reset |e> < 0.2\n")
    delays = []
    for d in (None, read_delay_us):
        if d not in delays:
            delays.append(d)
    print(f"  {'read_delay':>10s} {'iters':>5s} | {'reset |g>':>9s} {'reset |e>':>9s} "
          f"| verdict")
    for delay in delays:
        for iters in END_TO_END_ITERS:
            rg = reset_residual(soc, soccfg, c, project, delay, iters,
                                END_TO_END_SHOTS, False, True)
            re = reset_residual(soc, soccfg, c, project, delay, iters,
                                END_TO_END_SHOTS, True, True)
            ok = abs(rg) <= 0.2 and abs(re) <= 0.2
            print(f"  {str(delay):>10s} {iters:>5d} | {rg:>9.3f} {re:>9.3f} | "
                  f"{'PASS' if ok else 'fail'}")


def stage3(soc, soccfg, cfg, disc, read_delay_us):
    banner(f"STAGE 3 -- DECISION TRUTH TABLE at read_delay_us={read_delay_us}")
    max_iters = int(cfg["reset_max_iters"])
    c = dict(cfg)
    c["reset_threshold_raw"] = int(disc["threshold_raw"])
    c["reset_ground_below"] = bool(disc["ground_below"])
    thr = int(disc["threshold_raw"])
    ground_below = bool(disc["ground_below"])
    for prep in (False, True):
        rows = trace_run(soc, soccfg, c, read_delay_us, prep_excited=prep,
                         force_flip=False, n_acquires=TRACE_ACQUIRES)
        wrong = 0
        total = 0
        print(f"\n  prepared |{'e' if prep else 'g'}>  (threshold {thr}, "
              f"ground_below={ground_below})")
        for r in rows[:4]:
            print(f"    host {r['host_last']}  tproc_val {r['tproc_val']}  "
                  f"flip {r['tproc_flip']}  thr_reg {r['threshold_reg']}")
        for r in rows:
            for i in range(max_iters):
                v = r["tproc_val"][i]
                expect = (v >= thr) if ground_below else (v <= thr)
                total += 1
                if bool(r["tproc_flip"][i]) != bool(expect):
                    wrong += 1
        print(f"    condj agreed with a signed host-side comparison on "
              f"{total - wrong}/{total} decisions")
        if wrong:
            print("    --> the tProc comparison does NOT match a signed compare "
                  "(sign-extension / operand-order bug)")


def pi_context_point(soc, soccfg, cfg, project, prep_gain, do_readout, delay_us,
                     pi_gain, pi_freq, ro_gain=None, ro_length_us=None, shots=None,
                     want_probe_shots=False):
    c = dict(cfg)
    c["reps"] = c["shots"] = int(PI_CONTEXT_SHOTS if shots is None else shots)
    c["ctx_prep_gain"] = int(prep_gain)
    c["ctx_do_readout"] = bool(do_readout)
    c["ctx_delay_us"] = float(delay_us)
    c["ctx_pi_gain"] = int(pi_gain)
    c["ctx_pi_freq"] = float(pi_freq)
    c["ctx_ro_gain"] = None if ro_gain is None else int(ro_gain)
    c["ctx_ro_length_us"] = None if ro_length_us is None else float(ro_length_us)
    prog = PiContextProgram(soccfg, c)
    I, Q = prog.acquire(soc, load_pulses=True, progress=False)
    resid = project(I, Q)
    if not want_probe_shots:
        return resid
    lower, upper = raw_reads(prog, c["reps"], 2)
    return resid, lower[:, 0], upper[:, 0]


def stage6(soc, soccfg, cfg, ref):
    banner("STAGE 6 -- DOES THE READOUT DRIVE POPULATION OUT OF {g,e}?")
    project = make_projector(ref)
    pi_gain = int(cfg["qubit_pi_gain"])
    pi_freq = float(cfg.get("qubit_pi_freq", cfg["qubit_freq"]))
    nominal_gain = int(cfg["read_pulse_gain"])
    nominal_len = readout_drive_length_us(cfg)
    delay = PI_CONTEXT_DELAY_US
    print(f"  prep -> probe readout (gain G, length L) -> {delay}us -> pi -> score readout")
    print(f"  pi_eff(e->g) must be ~1 for the reset to work; it is the whole remaining gap.")
    print(f"  nominal: gain={nominal_gain}, drive length={nominal_len:.1f} us\n")

    def row(tag, ro_gain, ro_len):
        g0, g0_lo, g0_up = pi_context_point(soc, soccfg, cfg, project, 0, True, delay, 0,
                                            pi_freq, ro_gain=ro_gain, ro_length_us=ro_len,
                                            want_probe_shots=True)
        e0, e0_lo, e0_up = pi_context_point(soc, soccfg, cfg, project, pi_gain, True,
                                            delay, 0, pi_freq, ro_gain=ro_gain,
                                            ro_length_us=ro_len, want_probe_shots=True)
        g1 = pi_context_point(soc, soccfg, cfg, project, 0, True, delay, pi_gain,
                              pi_freq, ro_gain=ro_gain, ro_length_us=ro_len)
        e1 = pi_context_point(soc, soccfg, cfg, project, pi_gain, True, delay, pi_gain,
                              pi_freq, ro_gain=ro_gain, ro_length_us=ro_len)
        eff_ge = (g1 - g0) / (1.0 - 2.0 * g0) if abs(1.0 - 2.0 * g0) > 1e-6 else float("nan")
        eff_eg = (e1 - e0) / (1.0 - 2.0 * e0) if abs(1.0 - 2.0 * e0) > 1e-6 else float("nan")
        sep_lo = abs(np.median(e0_lo) - np.median(g0_lo))
        sep_up = abs(np.median(e0_up) - np.median(g0_up))
        if sep_lo >= sep_up:
            disc = fit_threshold(g0_lo[::2], e0_lo[::2])
        else:
            disc = fit_threshold(g0_up[::2], e0_up[::2])
        print(f"  {tag:>16s} | {g0:6.3f} {e0:6.3f} | {g1:6.3f} {e1:6.3f} | "
              f"{eff_ge:6.3f} {eff_eg:6.3f} | probe F={disc['fidelity']:.3f} "
              f"P(g|e)={disc['p_g_given_e']:.3f}")

    print(f"  {'probe readout':>16s} | {'g,nopi':>6s} {'e,nopi':>6s} | {'g,+pi':>6s} "
          f"{'e,+pi':>6s} | {'ge_eff':>6s} {'eg_eff':>6s} | discrimination")
    for g in READOUT_GAIN_SWEEP:
        row(f"gain {g}", g, None)
    for L in READOUT_LENGTH_SWEEP_US:
        row(f"len {L:g}us", None, L)


def stage4(soc, soccfg, cfg, ref):
    banner("STAGE 4 -- WHY IS THE RESET PI WEAK?  (readout-induced mixing and pi quality)")
    project = make_projector(ref)
    pi_gain = int(cfg["qubit_pi_gain"])
    pi_freq = float(cfg.get("qubit_pi_freq", cfg["qubit_freq"]))
    print("  residual 0 = |g>, 1 = |e> (projected onto the g->e axis)\n")

    print("  4a/4b  state after: prep -> 10us readout -> delay -> optional pi")
    print(f"  {'delay':>7s} | {'g,no pi':>8s} {'e,no pi':>8s} | {'g,+pi':>8s} {'e,+pi':>8s} "
          f"| {'pi eff':>7s}")
    for d in PI_CONTEXT_DELAYS_US:
        g0 = pi_context_point(soc, soccfg, cfg, project, 0, True, d, 0, pi_freq)
        e0 = pi_context_point(soc, soccfg, cfg, project, pi_gain, True, d, 0, pi_freq)
        g1 = pi_context_point(soc, soccfg, cfg, project, 0, True, d, pi_gain, pi_freq)
        e1 = pi_context_point(soc, soccfg, cfg, project, pi_gain, True, d, pi_gain, pi_freq)
        eff = (g1 - g0) / max(1.0 - g0, 1e-9)
        print(f"  {d:7.2f} | {g0:8.3f} {e0:8.3f} | {g1:8.3f} {e1:8.3f} | {eff:7.3f}")

    print("\n  4c  control: same elapsed time, NO readout before the pi")
    for d in PI_CONTEXT_DELAYS_US:
        g1 = pi_context_point(soc, soccfg, cfg, project, 0, False, d, pi_gain, pi_freq)
        print(f"  {d:7.2f} | g -> pi -> measure = {g1:8.3f}")

    print(f"\n  4d  pi frequency scan {PI_CONTEXT_DELAY_US}us after a readout "
          f"(Stark shift shows as a shifted peak)")
    for df in PI_FREQ_OFFSETS_MHZ:
        after = pi_context_point(soc, soccfg, cfg, project, 0, True,
                                 PI_CONTEXT_DELAY_US, pi_gain, pi_freq + df)
        clean = pi_context_point(soc, soccfg, cfg, project, 0, False,
                                 PI_CONTEXT_DELAY_US, pi_gain, pi_freq + df)
        print(f"  {df:+6.2f} MHz | after readout {after:7.3f} | no readout {clean:7.3f}")

    print(f"\n  4e  pi gain scan {PI_CONTEXT_DELAY_US}us after a readout")
    for s in PI_GAIN_SCALES:
        g = int(round(pi_gain * s))
        after = pi_context_point(soc, soccfg, cfg, project, 0, True,
                                 PI_CONTEXT_DELAY_US, g, pi_freq)
        clean = pi_context_point(soc, soccfg, cfg, project, 0, False,
                                 PI_CONTEXT_DELAY_US, g, pi_freq)
        print(f"  x{s:4.2f} ({g:5d}) | after readout {after:7.3f} | no readout {clean:7.3f}")


def main():
    soc, soccfg = makeProxy()
    cfg = dict(BaseConfig)
    if RES_PHASE is not None:
        cfg["res_phase"] = float(RES_PHASE)
    cfg["relax_delay"] = float(DIAG_RELAX_US)
    cfg["qubit_gain"] = int(cfg["qubit_pi_gain"])
    cfg["reset_max_iters"] = 3
    cfg["reset_oper"] = "lower"
    cfg["reset_meas_syncdelay_us"] = 4.0
    cfg["reset_settle_us"] = 0.05
    cfg["reset_thermalization_us"] = 25.0
    cfg["tproc_ch"] = ar.feedback_channel(soccfg, cfg["ro_chs"][0])

    if RUN_STAGE_0_ENV:
        stage0(soc, soccfg, cfg)

    ref = disc = None
    if RUN_STAGE_1_REFERENCE or RUN_STAGE_2_FRESHNESS or RUN_STAGE_3_DECISIONS \
            or RUN_STAGE_4_PI_CONTEXT:
        ref, oper, disc = stage1(soc, soccfg, cfg)
        cfg["reset_oper"] = oper

    best_delay = None
    if RUN_STAGE_2_FRESHNESS:
        verdicts = stage2(soc, soccfg, cfg, disc)
        candidates = [d for d in READ_DELAY_SWEEP_US
                      if d is not None and verdicts.get(d, 0.0) >= 0.98]
        if candidates:
            best_delay = candidates[-1]
            print(f"\n  smallest delay with a fully fresh read: {candidates[0]}")
        else:
            best_delay = max(d for d in READ_DELAY_SWEEP_US if d is not None)
            print("\n  no delay gave a fully fresh read; falling back to the largest swept")
        print(f"  chosen read_delay_us for the rest of the run: {best_delay}")

    if RUN_STAGE_3_DECISIONS:
        stage3(soc, soccfg, cfg, disc, best_delay)

    if RUN_STAGE_4_PI_CONTEXT:
        stage4(soc, soccfg, cfg, ref)

    if RUN_STAGE_5_END_TO_END:
        stage5(soc, soccfg, cfg, ref, disc, best_delay)

    if RUN_STAGE_6_READOUT_LEAKAGE:
        stage6(soc, soccfg, cfg, ref)

    banner("forensics complete -- paste the whole log back")


if __name__ == "__main__":
    main()
