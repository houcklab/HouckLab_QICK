"""Verification harness for the ModifiedRamsey fix set.

The Modified Ramsey path carries a set of fixes written from post-hoc data
forensics (TATQ01/BFE, 2026-06-05/06) and desk analysis, none of which had been
re-confirmed after the BFG board moved to qick 0.2.367 and a new bitstream. This
module is the standing regression suite for them. Re-run it after any qick
upgrade, bitstream reload, or channel remap.

Fixes under test
----------------
F1  resonator tone covers adc_trig_offset + readout_length, including the
    cross-clock ceil extension            (mModifiedRamsey.initialize)
F2  normalization/threshold keyed on cfg["ro_chs"][0], not a hardcoded ro_ch=0
F3  mr_relax_delay is separate from the spectroscopy relax_delay
F4  acquire() rejects readouts_per_experiment mismatches AND thresholds
F5  config validation (positives, non-negative delays, non-empty ro_chs)
F6  sign-safe tProc compare: regwi(thresh + cmp_offset) + mathi(r_read +=
    cmp_offset) before condj
F7  modified_ramsey_timing() models the scheduled rep period exactly
F8  buffer de-interleave: the final Ramsey read is the last read of each rep
F9  raw_shot_buffers() sources per-shot data from prog.acc_buf
F10 a STALLING instruction separates the reset readout from the `read` that
    feeds the condj, with a real settle margin measured in tProc cycles
    (mModifiedRamsey/mActiveResetVerify.active_reset_to_g)
F11 the two active_reset_to_g() implementations emit identical reset asm
F12 the r_read capture diagnostic is exact, and inert when disabled

Why F10 exists: measure(wait=True) emits waiti (which stalls) while syncdelay
emits synci (which only advances the tProc time reference). Before the fix the
`read` therefore executed 0.2 tProc cycles BEFORE the ADC integration window
closed, and the tProc input is a last-value latch with no handshake -- so it
returned the PREVIOUS readout's accumulated I. On 2026-07-28 that made the
corrective pi fire on ~50% of shots, uncorrelated with the qubit state
(prep|e> + reset ON gave P(|g>)=0.497 where force_pi gave 0.847), and the whole
suite still passed. F10 is the check whose absence allowed that.

Why F9 exists: from qick ~0.2.29x on, AveragerProgram._process_accumulated calls
_average_buf first, so prog.di_buf is averaged over reps AND divided by the
readout length -- one point per read, not one per shot. The raw per-shot stream
lives in prog.acc_buf, shaped (reps, reads_per_shot, 2), int64, un-normalized.

Tiers
-----
A (offline)  needs only a QickConfig. Runs from a committed soccfg snapshot, or
             from the synthetic fallback below if no snapshot exists yet.
             Entry point: run_offline_suite(). This is what __main__ runs.
B (board)    needs a live soc; no qubit signal required. Entry point:
             run_board_suite(ctx), wired into the runners as
             runs.verify.run_verify_modified_ramsey.
C (deferred) needs a calibrated single shot; no code here, see the checklist in
             _TIER_C_CHECKLIST below.

Usage
-----
    python -m WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.verify_ModifiedRamsey

from the repo root, with the qsim environment.
"""

import os
import json
import time
import datetime

import numpy as np
from qick import QickConfig

from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mModifiedRamsey import (
    ModifiedRamseyProgram,
    ModifiedRamsey,
    MIN_RESET_READ_SETTLE_US as MR_MIN_SETTLE_US,
)
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mActiveResetVerify import (
    ActiveResetVerifyProgram,
    RESET_CAPTURE_BASE_ADDR,
    decode_capture_words,
    MIN_RESET_READ_SETTLE_US as ARV_MIN_SETTLE_US,
)
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Helpers.shot_buffers import (
    raw_shot_buffers,
)


_TIER_C_CHECKLIST = """
Tier C (needs a calibrated single shot; also needs the YOKO for step 3):

1. RunSingleShot -> get_apriori_separator_from_singleshot ->
   calibrate_active_reset_readout (runs/calibration.py). The res_phase rotation
   MUST put g/e separation along I, or the F6 feedback compare is meaningless:
   the tProc thresholds the raw in-phase value only.
2. RunActiveResetVerify (runs/singleshot.py) over prep g/e x reset off/on, plus
   one reset_force_pi=True run. Pass criteria -- and note the ceiling, because
   the obvious criterion ("reset ON should match the prep|g> reset-OFF thermal
   baseline") is NOT achievable at reset_cycles=1 and reading a correct fix as a
   failure is the expensive mistake here:
     - one round of feedback pays the readout error TWICE, once in the
       conditioning decision and once in the verification read, so with the
       2026-07-28 Q3 primitives (A = P(g|prep g, OFF) = 0.872,
       B = P(g|prep e, OFF) = 0.152, C = P(g|prep e, force-pi) = 0.847,
       D = P(g|prep g, force-pi) = 0.132):
           prep|e> ON = P(reads e)*C + P(reads g)*B = 0.848*0.847 + 0.152*0.152
                      = 0.74
           prep|g> ON = P(reads g)*A + P(reads e)*D = 0.872*0.872 + 0.128*0.132
                      = 0.78
       A CORRECT fix therefore lands at 0.72-0.80, NOT at 0.85-0.87. Even
       reset_cycles=2 only reaches ~0.78. Do not compare against the force-pi
       control (0.847): force-pi makes no decision, so it never pays the error
       twice.
     - the two reset-ON conditions within ~0.06 of each other
     - the gap to the 0.872 baseline is the conditioning readout's own error and
       is irreducible at reset_cycles=1
     - flat vs verification-readout index (a working reset is QND)
     - NO ground-state damage. The pre-fix bug pumped 60-90% of |g> shots to
       |e>, concentrated in the below-zero half of the g blob. Include one
       deliberate g_I ~= 0 sweep: pre-fix that case lost exactly half its
       ground shots, so it is the sharpest regression test for F6.
3. RunModifiedRamsey end to end. Additionally needs the YOKO charge line: with
   use_apriori_separator=True the routine calls
   get_apriori_separator_from_singleshot before the loop, and steps the voltage
   via ramp_to when the two-tone doublet search fails.
"""


# ---------------------------------------------------------------------------
# soccfg snapshots
# ---------------------------------------------------------------------------

SNAPSHOT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "soccfg_snapshots")
DEFAULT_SNAPSHOT = os.path.join(SNAPSHOT_DIR, "bfg_zcu216.json")

_FS_DAC = 9830.4
_FS_ADC = 2457.6
_REFCLK = 245.76
_F_TIME = 430.08


def _synthetic_gen(ch):
    return {
        "type": "axis_signal_gen_v6",
        "tproc_ch": ch + 1,
        "fs": _FS_DAC, "fs_mult": 40, "fs_div": 1, "fdds_div": 1,
        "f_fabric": _FS_DAC / 16,
        "b_dds": 32, "b_phase": 32, "b_gain": 16,
        "interpolation": 1, "samps_per_clk": 16,
        "maxlen": 65536, "maxv": 32767, "maxv_scale": 0.9,
        "has_dds": True, "has_mixer": False, "complex_env": False,
        "switch_ch": ch, "dac": str(ch),
    }


def _synthetic_ro(ch):
    return {
        "type": "axis_readout_v2",
        "fs": _FS_ADC, "fs_mult": 10, "fs_div": 1, "fdds_div": 1,
        "f_output": _FS_ADC / 8, "f_fabric": _FS_ADC / 8,
        "b_dds": 32, "b_phase": 32,
        "trigger_port": 0, "trigger_bit": 14 + ch, "trigger_type": "dport",
        "buf_maxlen": 1024, "avg_maxlen": 16384, "iq_offset": 0,
        "has_weights": False, "has_edge_counter": False, "has_outsel": True,
        "adc": str(ch), "avgbuf_fullpath": "avg%d" % ch,
    }


# Synthetic bootstrap config. NOT the BFG board -- it exists so the offline tier
# is runnable before anyone connects, and so the checks below can be exercised
# against clock ratios of our choosing. Three distinct clocks (tProc 430.08,
# gen fabric 614.4, readout output 307.2 MHz) so cross-domain rounding is real.
# check_board_env() replaces it with the live dump on the first board run.
SYNTHETIC_SOCCFG = {
    "board": "SYNTHETIC-ZCU216",
    "sw_version": "0.2.367",
    "refclk_freq": _REFCLK,
    "gens": [_synthetic_gen(i) for i in range(7)],
    "readouts": [_synthetic_ro(i) for i in range(2)],
    "iqs": [],
    "tprocs": [{
        "type": "axis_tproc64x32_x8",
        "f_time": _F_TIME, "f_fabric": _F_TIME,
        "pmem_size": 16384, "dmem_size": 4096,
        "output_pins": [], "trig_output": 0,
    }],
    "ddrbufs": [],
    "mrbufs": [],
}


def snapshot_soccfg(soccfg, path=DEFAULT_SNAPSHOT):
    """Write a live soccfg to JSON so the offline tier can run against it."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(soccfg.dump_cfg())
    return path


def load_soccfg(path=None):
    """Load a snapshot, falling back to the synthetic bootstrap config.

    Returns (QickConfig, source_label).
    """
    path = path or DEFAULT_SNAPSHOT
    if os.path.exists(path):
        with open(path) as f:
            return QickConfig(json.load(f)), path
    return QickConfig(dict(SYNTHETIC_SOCCFG)), "synthetic (no snapshot at %s)" % path


# ---------------------------------------------------------------------------
# cfg fixtures
# ---------------------------------------------------------------------------

def base_cfg(**overrides):
    """A minimal ModifiedRamsey cfg that builds. Override per check."""
    cfg = {
        "res_ch": 0, "qubit_ch": 1, "ro_chs": [0],
        "nqz": 2, "qubit_nqz": 1,
        "reps": 100, "rounds": 1,
        "readout_length": 15.0, "adc_trig_offset": 0.5,
        "pulse_freq": 7000.0, "pulse_gain": 1500, "res_phase": 0,
        "f_ge": 2758.3, "df": 0.5, "sigma": 0.1,
        "pi_gain": 4000, "pi2_gain": 2000,
        "mr_relax_delay": 0.0,
        # Only consulted by the two-tone search in the runner; present here so
        # the F3 negative control can move it and prove the schedule ignores it.
        "relax_delay": 1500,
    }
    cfg.update(overrides)
    return cfg


def reset_cfg(**overrides):
    """cfg with active reset enabled.

    readout_threshold/pi_gain are dummies: reset_cycles > 0 hard-raises without
    them (mModifiedRamsey.initialize), but the *schedule* is branch-independent
    -- the shared synci after the RESET_DONE label reserves the corrective pi's
    duration whether or not the condj skipped it -- so timing and asm checks are
    unaffected by the threshold value. On hardware the pi will fire on roughly
    half the shots; harmless for a timing measurement, meaningless as physics.
    """
    cfg = base_cfg(use_active_reset=True, reset_cycles=1,
                   readout_threshold=0.0, reset_readout_relax_delay=5.0,
                   post_reset_wait=0.0)
    cfg.update(overrides)
    return cfg


def device_cfg(ctx, **overrides):
    """A real ModifiedRamsey cfg for THIS device, for the tier-B stages.

    base_cfg() above is a synthetic fixture -- its channels, frequencies and
    gains are invented, so building tier-B programs from it would pulse the
    wrong DAC at the wrong frequency and measure noise. Start from the runner's
    live config (channels, resonator freq/gain, res_phase, readout_length,
    adc_trig_offset, length) and add only the ModifiedRamsey-specific keys.
    """
    cfg = ctx.working_config()
    cfg.update({
        "f_ge": ctx.qubit_frequency_center,
        "df": 0.5,                       # only sets tau = 1/(2*df) here
        "pi_gain": ctx.qubit_gain,
        "pi2_gain": ctx.pi2_gain,
        "sigma": ctx.qubit_sigma,
        "flattop_length": ctx.qubit_flattop,
        "mr_relax_delay": 0.0,
        "rounds": 1,                     # never inherit rounds: it multiplies
        "Qubit_number": ctx.Qubit_Readout,
    })
    cfg.update(overrides)
    return cfg


def with_reset(cfg, reset_cycles):
    """Enable active reset on a device cfg, with dummy feedback parameters.

    reset_cycles > 0 hard-raises without readout_threshold/pi_gain, but the
    schedule is branch-independent (the shared synci after the RESET_DONE label
    reserves the corrective pi either way), so timing and buffer shape are
    unaffected by the threshold value. On an uncalibrated qubit the corrective
    pi fires on roughly half the shots: harmless here, meaningless as physics.
    """
    cfg = dict(cfg)
    cfg.update({
        "use_active_reset": True,
        "reset_cycles": reset_cycles,
        "readout_threshold": cfg.get("readout_threshold", 0.0) or 0.0,
        "reset_readout_relax_delay": cfg.get("reset_readout_relax_delay", 5.0),
        "post_reset_wait": cfg.get("post_reset_wait", 0.0),
    })
    return cfg


def _timing_fn():
    """Import modified_ramsey_timing lazily.

    Importing runs.charge_parity pulls in runs/__init__ -> context.py (pyvisa)
    and calibration.py (sklearn). Both are installed in qsim, but keep the cost
    off the import path of this module so the rest of the offline tier still
    runs if they ever go missing.
    """
    from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Runners.runs.charge_parity import (
        modified_ramsey_timing,
    )
    return modified_ramsey_timing


# ---------------------------------------------------------------------------
# result plumbing
# ---------------------------------------------------------------------------

class CheckResult:
    def __init__(self, name, fixes=""):
        self.name = name
        self.fixes = fixes
        self.failures = []
        self.notes = {}
        self.error = None

    def expect(self, cond, msg):
        if not cond:
            self.failures.append(msg)
        return bool(cond)

    def expect_raises(self, exc_types, fn, msg):
        try:
            fn()
        except exc_types:
            return True
        except Exception as e:
            self.failures.append(f"{msg} (raised {type(e).__name__}: {e})")
            return False
        self.failures.append(f"{msg} (did not raise)")
        return False

    def expect_no_raise(self, fn, msg):
        try:
            fn()
            return True
        except Exception as e:
            self.failures.append(f"{msg} (raised {type(e).__name__}: {e})")
            return False

    @property
    def passed(self):
        return self.error is None and not self.failures

    def to_dict(self):
        return {"name": self.name, "fixes": self.fixes, "passed": self.passed,
                "failures": self.failures, "error": self.error, "notes": self.notes}


def _run(check_fn, *args, **kwargs):
    """Run a check function, converting an unexpected exception into a failure."""
    name = check_fn.__name__
    try:
        return check_fn(*args, **kwargs)
    except Exception as e:
        import traceback
        r = CheckResult(name)
        r.error = f"{type(e).__name__}: {e}"
        r.notes["traceback"] = traceback.format_exc().splitlines()[-6:]
        return r


# ---------------------------------------------------------------------------
# asm helpers (tProc v1)
# ---------------------------------------------------------------------------

def _loop_body(prog):
    """Return the prog_list slice for one repetition of the body loop.

    AveragerProgram.make_program wraps body() in
        label LOOP_J ... mathi(rcount+1) ... memwi ... loopnz(LOOP_J)
    The label is attached to the instruction that follows it.
    """
    plist = prog.prog_list
    start = next(i for i, x in enumerate(plist) if x.get("label") == "LOOP_J")
    end = next(i for i, x in enumerate(plist)
               if x["name"] == "loopnz" and x["args"][-1] == "LOOP_J")
    return plist[start:end], plist


def _resolve_reg(plist, upto, page, reg):
    """Value of a register set by the last regwi before index `upto`."""
    val = None
    for inst in plist[:upto]:
        if inst["name"] == "regwi" and inst["args"][0] == page and inst["args"][1] == reg:
            val = inst["args"][2]
    return val


def rep_period_cycles_from_asm(prog):
    """Scheduled tProc cycles per repetition, summed from the compiled program.

    Independent ground truth for modified_ramsey_timing(). Every time-advancing
    instruction in a tProc v1 body is either synci (immediate delay, emitted by
    sync_all) or sync (delay by register, emitted by sync()); waiti blocks but
    does not advance the reference. sync_all() emits nothing at all when the
    accumulated delay is <= 0 (asm_v1.py:964-965).
    """
    body, plist = _loop_body(prog)
    offset = plist.index(body[0])
    total = 0
    for i, inst in enumerate(body):
        if inst["name"] == "synci":
            total += inst["args"][0]
        elif inst["name"] == "sync":
            page, reg = inst["args"][0], inst["args"][1]
            val = _resolve_reg(plist, offset + i, page, reg)
            if val is None:
                raise RuntimeError(f"could not resolve sync register p{page} r{reg}")
            total += val
    return total


def read_settle_margins(prog):
    """Settle margin, in tProc cycles, for every 'read' in the loop body.

    margin = (absolute time of the last STALLING instruction before the read)
             - (absolute time at which the ADC integration window closes)

    Absolute time = the tProc time reference accumulated by synci/sync, plus the
    instruction's own time argument -- which is exactly what the hardware
    compares against its time counter (t_inst = t_cnt_sync + imm, and the timed
    controller releases the control core only once t_inst <= t_cnt). waiti stalls
    and does NOT advance the reference; synci advances it and does NOT stall.

    Returns one dict per read, in program order.
    """
    body, plist = _loop_body(prog)
    offset = plist.index(body[0])
    f_time = float(prog.soccfg["tprocs"][0]["f_time"])
    ro_ch = prog.cfg["ro_chs"][0]
    rocfg = prog.soccfg["readouts"][ro_ch]
    ro_len_tproc = (prog.readout_window_cycles[ro_ch]
                    * f_time / float(rocfg["f_output"]))
    trig_port = int(rocfg["trigger_port"])
    trig_bits = 1 << int(rocfg["trigger_bit"])

    t_ref = 0
    adc_close = None
    stall = None
    out = []
    for i, inst in enumerate(body):
        name = inst["name"]
        args = inst["args"]
        if name == "synci":
            t_ref += args[0]
        elif name == "sync":
            val = _resolve_reg(plist, offset + i, args[0], args[1])
            if val is None:
                raise RuntimeError(f"could not resolve sync register p{args[0]} "
                                   f"r{args[1]}")
            t_ref += val
        elif name == "seti":
            # trigger() emits regwi(0, r_out, bits) then
            # seti(outport, 0, r_out, t_start) then seti(outport, 0, 0, t_end).
            # Pick the one whose out-word carries THIS readout's trigger bit.
            outport, page, reg, t = args[0], args[1], args[2], args[3]
            if outport != trig_port:
                continue
            val = _resolve_reg(plist, offset + i, page, reg)
            if val is not None and (int(val) & trig_bits):
                adc_close = t_ref + t + ro_len_tproc
        elif name == "waiti":
            stall = t_ref + args[1]
        elif name == "read":
            out.append({
                "index": i,
                "adc_close_cycles": adc_close,
                "stall_cycles": stall,
                "margin_cycles": (None if (adc_close is None or stall is None)
                                  else stall - adc_close),
                "margin_us": (None if (adc_close is None or stall is None)
                              else (stall - adc_close) / f_time),
                "has_waiti_before_read": stall is not None,
            })
    return out


def read_settle_timings(prog):
    """read_settle_margins() with the body INDEX dropped.

    The index is a position, not a timing quantity: anything that inserts
    instructions before a read (e.g. the reset-capture diagnostic) shifts it
    without touching the schedule. Compare this when asking "did the margin
    change", or the comparison reports a difference that does not exist.
    """
    return [(m["adc_close_cycles"], m["stall_cycles"], m["margin_cycles"])
            for m in read_settle_margins(prog)]


def reset_asm_signature(prog):
    """Canonical, label-agnostic signature of one program's reset block.

    The block runs from the first body instruction through the instruction
    carrying the LAST done-label (which is the synci that sync_all() emits after
    the corrective pi, so the branch-reconvergence delay is included). Label
    strings are normalized away: the two programs use RESET_DONE_n and
    VRESET_DONE_n for the same jump target.
    """
    body, _ = _loop_body(prog)
    labelled = [i for i, x in enumerate(body)
                if isinstance(x.get("label"), str) and "RESET_DONE_" in x["label"]]
    if len(labelled) != prog.reset_cycles:
        raise RuntimeError(
            f"found {len(labelled)} *RESET_DONE_* labels, expected "
            f"{prog.reset_cycles}; cannot delimit the reset block")
    sig = []
    for x in body[:labelled[-1] + 1]:
        args = tuple("<label>" if isinstance(a, str) and "RESET_DONE_" in a else a
                     for a in x["args"])
        sig.append((x["name"], args))
    return sig


# ---------------------------------------------------------------------------
# Tier A checks
# ---------------------------------------------------------------------------

class _LegacyProg:
    """Pre-0.2.29x stand-in: di_buf/dq_buf already hold the raw per-shot stream."""
    def __init__(self, di, dq):
        self.di_buf = di
        self.dq_buf = dq


def check_shot_buffers(soccfg):
    """F9/F8 -- de-interleave against a real-shaped acc_buf.

    Deliberately does NOT inject a synthetic di_buf: that is what the first
    draft of this harness did, and it passes while the real acquisition path
    raises, because on qick 0.2.367 di_buf is the rep-averaged array.
    """
    r = CheckResult("shot_buffers", "F9, F8")
    reps = 37
    for reset_cycles in (0, 1, 2):
        cfg = (reset_cfg(reps=reps, reset_cycles=reset_cycles)
               if reset_cycles else base_cfg(reps=reps))
        prog = ModifiedRamseyProgram(soccfg, dict(cfg))
        nreads = reset_cycles + 1
        prog.reads_per_rep = nreads

        # Raw accumulator fingerprint: I = rep*1000 + read, Q negative (the sign
        # case the F6 compare cares about, and a check that nothing takes abs).
        acc = np.zeros((reps, nreads, 2), dtype=np.int64)
        for rep in range(reps):
            for read in range(nreads):
                acc[rep, read, 0] = rep * 1000 + read
                acc[rep, read, 1] = -(rep * 1000 + read)
        prog.acc_buf = [acc]

        di, dq = raw_shot_buffers(prog)
        r.expect(di[0].shape == (reps * nreads,),
                 f"reset_cycles={reset_cycles}: flattened di length "
                 f"{di[0].shape} != {(reps * nreads,)}")
        # rep-major / read-minor, matching the [ii::reads_per_rep] strides
        r.expect(np.array_equal(di[0][:nreads], acc[0, :, 0]),
                 f"reset_cycles={reset_cycles}: flatten order is not rep-major")
        r.expect(di[0].max() == acc[:, :, 0].max(),
                 f"reset_cycles={reset_cycles}: raw_shot_buffers altered the "
                 "values (it must hand back RAW accumulator units -- acc_buf is "
                 "not length-normalized, unlike di_buf)")

        norm = soccfg.us2cycles(cfg["readout_length"], ro_ch=cfg["ro_chs"][0])
        shots_i, shots_q = prog.collect_shots()
        expected_i = (np.arange(reps) * 1000 + (nreads - 1)) / norm
        r.expect(shots_i.shape == (1, reps),
                 f"reset_cycles={reset_cycles}: shots_i shape {shots_i.shape}")
        r.expect(np.allclose(shots_i.ravel(), expected_i),
                 f"reset_cycles={reset_cycles}: collect_shots did not select the "
                 "FINAL read of each rep")
        r.expect(np.allclose(shots_q.ravel(), -expected_i),
                 f"reset_cycles={reset_cycles}: shots_q mismatch")

    # legacy fallback branch
    legacy = _LegacyProg([np.arange(10.0)], [np.arange(10.0)])
    di, dq = raw_shot_buffers(legacy)
    r.expect(di is legacy.di_buf and dq is legacy.dq_buf,
             "legacy (no acc_buf) fallback did not return di_buf/dq_buf untouched")
    return r


def check_tone_coverage(soccfg):
    """F1 -- the resonator tone must cover adc_trig_offset + the ADC window."""
    r = CheckResult("tone_coverage", "F1")
    f_time = float(soccfg["tprocs"][0]["f_time"])
    extensions = set()
    max_adc_end = 0.0

    for res_ch in (0, 2):
        for ro_ch in (0, 1):
            for ro_len in (1.0, 2.0, 2.37, 3.0, 5.0, 15.0):
                for offset in (0.0, 0.25, 0.5):
                    cfg = base_cfg(res_ch=res_ch, ro_chs=[ro_ch],
                                   readout_length=ro_len, adc_trig_offset=offset)
                    # pass the dict the program will mutate: initialize()
                    # setdefaults cfg["length"], and the check reads it back.
                    prog = ModifiedRamseyProgram(soccfg, cfg)
                    f_fabric = float(soccfg["gens"][res_ch]["f_fabric"])
                    f_output = float(soccfg["readouts"][ro_ch]["f_output"])

                    adc_end = (prog.adc_trig_offset_cycles
                               + prog.readout_window_cycles[ro_ch] * f_time / f_output)
                    tone_end = prog.readout_tone_cycles * f_time / f_fabric
                    max_adc_end = max(max_adc_end, adc_end)

                    tag = f"res_ch={res_ch} ro_ch={ro_ch} ro_len={ro_len} off={offset}"
                    r.expect(tone_end >= adc_end - 1e-9,
                             f"{tag}: tone ends {adc_end - tone_end:.6f} tProc "
                             "cycles BEFORE the ADC window closes")

                    # minimality is a property of required_tone_cycles, not of
                    # readout_tone_cycles = max(requested, required): a user who
                    # asks for a longer tone legitimately gets slop.
                    required = int(np.ceil(adc_end * f_fabric / f_time - 1e-12))
                    r.expect((required - 1) * f_time / f_fabric < adc_end,
                             f"{tag}: required_tone_cycles is not minimal")
                    requested = soccfg.us2cycles(cfg["length"], gen_ch=res_ch)
                    r.expect(prog.readout_tone_cycles == max(requested, required),
                             f"{tag}: tone cycles {prog.readout_tone_cycles} != "
                             f"max(requested {requested}, required {required})")
                    extensions.add(prog.readout_tone_extension_cycles)

                    # ActiveResetVerify must quantize identically -- it is the
                    # harness that validates the reset ModifiedRamsey relies on.
                    arv = ActiveResetVerifyProgram(soccfg, dict(cfg))
                    r.expect(arv.readout_tone_cycles == prog.readout_tone_cycles,
                             f"{tag}: ARV tone {arv.readout_tone_cycles} != MR "
                             f"tone {prog.readout_tone_cycles}")

    r.expect(0 in extensions and 1 in extensions,
             f"grid only exercised extension values {sorted(extensions)}; it must "
             "cover both 0 and 1 or the cross-clock ceil branch is untested")
    r.notes["extensions_seen"] = sorted(int(e) for e in extensions)

    # short tone must be rejected, not silently truncated
    short = base_cfg(readout_length=5.0, adc_trig_offset=0.5, length=5.0)
    r.expect_raises(ValueError, lambda: ModifiedRamseyProgram(soccfg, dict(short)),
                    "cfg['length'] shorter than offset+window was accepted")

    # the epsilon in the ceil is absolute (1e-12) and the operand is O(1e4)
    r.notes["max_adc_end_tproc_cycles"] = round(max_adc_end, 3)
    if max_adc_end > 1e3:
        r.notes["epsilon_warning"] = (
            "adc_end_tproc reaches %.0f, where the absolute 1e-12 epsilon in the "
            "ceil (mModifiedRamsey:186, charge_parity:75) is at the edge of double "
            "resolution; a relative epsilon would be safer" % max_adc_end)
    return r


def check_ro_ch_normalization(soccfg):
    """F2 -- normalization must follow ro_chs[0], not channel 0.

    Both readouts on the BFG board are the same IP with the same f_output, so
    comparing ro_chs=[0] against ro_chs=[1] on the real snapshot CANNOT fail --
    reverting the fix changes nothing. Mutate the snapshot so the two channels
    actually differ, then the check has teeth.
    """
    r = CheckResult("ro_ch_normalization", "F2")
    cfg_dict = json.loads(json.dumps(soccfg._cfg))  # deep copy
    ratio = 1.5
    cfg_dict["readouts"][1]["f_output"] *= ratio
    cfg_dict["readouts"][1]["f_fabric"] *= ratio
    mutated = QickConfig(cfg_dict)

    thresholds = {}
    norms = {}
    for ro_ch in (0, 1):
        cfg = reset_cfg(ro_chs=[ro_ch], readout_threshold=1.0)
        prog = ModifiedRamseyProgram(mutated, dict(cfg))
        window = prog.readout_window_cycles[ro_ch]
        norms[ro_ch] = window
        body, plist = _loop_body(prog)
        thresholds[ro_ch] = _resolve_reg(plist, len(plist), prog.q_rp, prog.r_thresh)

        # collect_shots must divide by the SAME window
        prog.reads_per_rep = prog.reset_cycles + 1
        nreads = prog.reads_per_rep
        acc = np.zeros((cfg["reps"], nreads, 2), dtype=np.int64)
        acc[:, -1, 0] = window  # one normalized unit
        prog.acc_buf = [acc]
        shots_i, _ = prog.collect_shots()
        r.expect(np.allclose(shots_i, 1.0),
                 f"ro_ch={ro_ch}: collect_shots normalized by the wrong window "
                 f"(got {shots_i.ravel()[0]}, expected 1.0)")

    r.expect(norms[1] != norms[0],
             "mutated snapshot did not actually change the window length; the "
             "check would be vacuous")
    # cmp_offset is itself sized from the ro_chs[0] window (int(ro_norm) << 15),
    # so derive the expectation from norms[1] rather than hardcoding a constant.
    # This keeps the check's teeth: if the fix were reverted so BOTH the
    # threshold and the offset were keyed on channel 0, each term would be built
    # from norms[0] and the total would still miss this norms[1]-derived value.
    expected_offset = int(norms[1]) << 15
    expected = round(norms[1] * 1.0) + expected_offset
    r.expect(thresholds[1] == expected,
             f"raw threshold for ro_chs=[1] is {thresholds[1]}, expected "
             f"{expected} (window {norms[1]} + cmp_offset {expected_offset}) -- "
             "the threshold rescale is not keyed on ro_chs[0]")
    r.notes["windows"] = {str(k): int(v) for k, v in norms.items()}
    return r


def check_config_validation(soccfg):
    """F5/F4 -- bad configs must be rejected, loudly and early."""
    r = CheckResult("config_validation", "F5, F4")
    bad = [
        ("df <= 0", base_cfg(df=0.0), ValueError),
        ("df negative", base_cfg(df=-0.5), ValueError),
        ("sigma <= 0", base_cfg(sigma=0.0), ValueError),
        ("readout_length <= 0", base_cfg(readout_length=0.0), ValueError),
        ("adc_trig_offset < 0", base_cfg(adc_trig_offset=-0.1), ValueError),
        ("mr_relax_delay < 0", base_cfg(mr_relax_delay=-1.0), ValueError),
        ("empty ro_chs", base_cfg(ro_chs=[]), (ValueError, IndexError, KeyError)),
        ("reset_cycles < 0", reset_cfg(reset_cycles=-1), ValueError),
        ("reset_readout_relax_delay < 0", reset_cfg(reset_readout_relax_delay=-1.0), ValueError),
        ("post_reset_wait < 0", reset_cfg(post_reset_wait=-1.0), ValueError),
    ]
    for label, cfg, exc in bad:
        r.expect_raises(exc, lambda c=cfg: ModifiedRamseyProgram(soccfg, dict(c)),
                        f"accepted invalid cfg: {label}")

    missing_thresh = reset_cfg()
    del missing_thresh["readout_threshold"]
    r.expect_raises(KeyError,
                    lambda: ModifiedRamseyProgram(soccfg, dict(missing_thresh)),
                    "use_active_reset without readout_threshold was accepted")
    missing_pi = reset_cfg()
    del missing_pi["pi_gain"]
    r.expect_raises(KeyError, lambda: ModifiedRamseyProgram(soccfg, dict(missing_pi)),
                    "use_active_reset without pi_gain was accepted")

    # threshold large enough to collide with the sign-safe offset
    prog0 = ModifiedRamseyProgram(soccfg, reset_cfg())
    window = prog0.readout_window_cycles[0]
    huge = reset_cfg(readout_threshold=float(prog0.cmp_offset) / window * 1.1)
    r.expect_raises(ValueError, lambda: ModifiedRamseyProgram(soccfg, dict(huge)),
                    "readout_threshold exceeding cmp_offset was accepted")

    # --- acquire() guards (F4). Both must raise before soc is touched. ---
    prog = ModifiedRamseyProgram(soccfg, reset_cfg(reset_cycles=2))
    r.expect_raises(ValueError,
                    lambda: prog.acquire(None, readouts_per_experiment=1),
                    "acquire() accepted a readouts_per_experiment mismatch")
    prog2 = ModifiedRamseyProgram(soccfg, base_cfg())
    r.expect_raises(ValueError, lambda: prog2.acquire(None, threshold=1.0),
                    "acquire() accepted threshold=... -- qick would replace the "
                    "data with heaviside decisions and zero Q, while collect_shots "
                    "returns raw acc_buf regardless")

    # --- timing model must accept every cfg the program accepts (F12) ---
    timing = _timing_fn()
    no_length = base_cfg()
    no_length.pop("length", None)
    r.expect_no_raise(lambda: timing(soccfg, dict(no_length)),
                      "modified_ramsey_timing rejects a cfg without 'length' that "
                      "ModifiedRamseyProgram accepts (initialize() setdefaults it); "
                      "both runner call sites compute timing BEFORE building the "
                      "program, so this is reachable")
    return r


def check_reset_asm(soccfg):
    """F6 -- sign-safe compare: offset both operands before the condj."""
    r = CheckResult("reset_asm", "F6")

    for reset_cycles in (1, 2):
        cfg = reset_cfg(reset_cycles=reset_cycles, readout_threshold=1.0)
        prog = ModifiedRamseyProgram(soccfg, dict(cfg))
        body, plist = _loop_body(prog)
        offset = prog.cmp_offset

        reads = [i for i, x in enumerate(body) if x["name"] == "read"]
        maths = [i for i, x in enumerate(body)
                 if x["name"] == "mathi" and x["args"][4] == offset]
        condjs = [i for i, x in enumerate(body) if x["name"] == "condj"]
        r.expect(len(reads) == reset_cycles,
                 f"reset_cycles={reset_cycles}: {len(reads)} read instructions")
        r.expect(len(maths) == reset_cycles,
                 f"reset_cycles={reset_cycles}: {len(maths)} mathi with immediate "
                 f"{offset} (expected {reset_cycles}); note mathi is also used for "
                 "the rep counter (imm 1) and inside safe_regwi, hence the filter")
        r.expect(len(condjs) == reset_cycles,
                 f"reset_cycles={reset_cycles}: {len(condjs)} condj instructions")
        for k in range(min(len(reads), len(maths), len(condjs))):
            r.expect(reads[k] < maths[k] < condjs[k],
                     f"reset_cycles={reset_cycles} cycle {k}: instruction order is "
                     f"read@{reads[k]} mathi@{maths[k]} condj@{condjs[k]}; the "
                     "offset must be applied between the read and the compare")
            m = body[maths[k]]
            r.expect(m["args"][1] == prog.r_read and m["args"][2] == prog.r_read
                     and m["args"][3] == "+",
                     f"cycle {k}: mathi does not add the offset to r_read in place")

        window = prog.readout_window_cycles[cfg["ro_chs"][0]]
        raw_threshold = int(round(cfg["readout_threshold"] * window))
        got = _resolve_reg(plist, len(plist), prog.q_rp, prog.r_thresh)
        r.expect(got == raw_threshold + offset,
                 f"r_thresh loaded with {got}, expected raw_threshold "
                 f"{raw_threshold} + cmp_offset {offset}")

        # both operands strictly positive across the reachable raw-I range
        r.expect(raw_threshold + offset > 0 and offset - (1 << 20) > 0,
                 "cmp_offset does not keep both compare operands positive")

    arv_cfg = reset_cfg(reset_cycles=1, readout_threshold=1.0)
    arv = ActiveResetVerifyProgram(soccfg, dict(arv_cfg))
    mr = ModifiedRamseyProgram(soccfg, dict(arv_cfg))
    r.expect(arv.cmp_offset == mr.cmp_offset,
             f"ActiveResetVerify cmp_offset {arv.cmp_offset} != ModifiedRamsey "
             f"{mr.cmp_offset}; ARV would validate a different compare than the "
             "one ModifiedRamsey runs")

    forced = ActiveResetVerifyProgram(soccfg, dict(reset_cfg(
        reset_cycles=1, readout_threshold=1.0, reset_force_pi=True)))
    fbody, _ = _loop_body(forced)
    r.expect(not [x for x in fbody if x["name"] == "condj"],
             "reset_force_pi=True still emits a condj")
    r.expect([x for x in fbody
              if x["name"] == "mathi" and x["args"][4] == forced.cmp_offset],
             "reset_force_pi=True dropped the sign-safe mathi")
    return r


# Hard floor on the settle margin, in us. Well above the avg_buf -> tProc
# propagation (two clock-domain crossings, tens to ~150 ns) and above the 200
# tProc cycles (0.47 us) the canonical qick active-reset demo waits.
MIN_READ_SETTLE_US = 0.1


def check_reset_read_settle(soccfg):
    """F10 -- a STALLING instruction must separate the readout from the 'read'.

    This is the check whose absence let a decorrelated condj pass a full
    regression suite. It measures the margin quantitatively rather than looking
    for the presence of an instruction: the PRE-FIX code already emitted a waiti
    (measure(wait=True) does), but its target was 0.2 tProc cycles BEFORE the ADC
    integration window closed, because wait_all() truncates the fractional
    readout-end timestamp with int(). Assertion (a) below therefore passes on the
    broken code and (b) does not.
    """
    r = CheckResult("reset_read_settle", "F10")
    f_time = float(soccfg["tprocs"][0]["f_time"])

    for name, cls in (("ModifiedRamsey", ModifiedRamseyProgram),
                      ("ActiveResetVerify", ActiveResetVerifyProgram)):
        for reset_cycles in (1, 2):
            cfg = reset_cfg(reset_cycles=reset_cycles, readout_threshold=1.0)
            prog = cls(soccfg, dict(cfg))
            margins = read_settle_margins(prog)
            tag = f"{name} reset_cycles={reset_cycles}"
            if not r.expect(len(margins) == reset_cycles,
                            f"{tag}: found {len(margins)} reads, expected "
                            f"{reset_cycles}"):
                continue
            for k, m in enumerate(margins):
                # (a) weak: something stalls at all before the read
                r.expect(m["has_waiti_before_read"],
                         f"{tag} read {k}: NO stalling instruction (waiti) "
                         "between the readout trigger and the read")
                if m["margin_cycles"] is None:
                    r.expect(False, f"{tag} read {k}: could not locate the ADC "
                                    "trigger for this read")
                    continue
                # (b) strong: the stall target must clear the ADC window close
                r.expect(m["margin_us"] >= MIN_READ_SETTLE_US,
                         f"{tag} read {k}: settle margin is {m['margin_us']:.4f} "
                         f"us ({m['margin_cycles']:.1f} tProc cycles) between the "
                         f"close of the ADC integration window and the 'read'; at "
                         f"least {MIN_READ_SETTLE_US} us is required. syncdelay "
                         "emits synci, which advances the tProc time reference but "
                         "does NOT stall execution; only waiti stalls. Restore the "
                         "self.wait_all(self.reset_read_extra_wait_cycles) between "
                         "measure() and read() in active_reset_to_g().")
                # (c) the configured guarantee is actually delivered. sync_all's
                # int() truncation can shave at most one cycle off the target.
                r.expect(m["margin_cycles"] + 1 >= prog.reset_read_settle_cycles,
                         f"{tag} read {k}: margin {m['margin_cycles']:.1f} cycles "
                         f"is below the configured reset_read_settle "
                         f"({prog.reset_read_settle_cycles} cycles)")
                r.notes[f"{name}_rc{reset_cycles}_read{k}"] = {
                    "adc_close_cycles": round(m["adc_close_cycles"], 2),
                    "stall_cycles": round(m["stall_cycles"], 2),
                    "margin_cycles": round(m["margin_cycles"], 2),
                    "margin_us": round(m["margin_us"], 5)}

    # The guarantee must survive a runner that shortens reset_readout_relax_delay
    # to zero -- that is the config in which wait_all(0) alone would degenerate to
    # a no-op, so the shortfall waiti has to appear.
    for name, cls in (("ModifiedRamsey", ModifiedRamseyProgram),
                      ("ActiveResetVerify", ActiveResetVerifyProgram)):
        zero = reset_cfg(reset_cycles=1, readout_threshold=1.0,
                         reset_readout_relax_delay=0.0)
        m = read_settle_margins(cls(soccfg, dict(zero)))[0]
        r.expect(m["margin_cycles"] is not None
                 and m["margin_us"] >= MIN_READ_SETTLE_US,
                 f"{name}: with reset_readout_relax_delay=0 the settle margin "
                 f"collapses to {m['margin_us']} us; the reset_read_settle floor "
                 "is not being emitted independently of the syncdelay")
        r.notes[f"{name}_relax0_margin_us"] = (None if m["margin_us"] is None
                                               else round(m["margin_us"], 5))

        # positive control: the knob must MOVE the margin, or the check is not
        # measuring what it claims to measure.
        base = m["margin_cycles"]
        bumped = read_settle_margins(cls(soccfg, dict(
            zero, reset_read_settle=2.0)))[0]["margin_cycles"]
        want = soccfg.us2cycles(2.0) - soccfg.us2cycles(0.5)
        r.expect(bumped - base >= want - 1,
                 f"{name}: raising cfg['reset_read_settle'] 0.5 -> 2.0 us moved "
                 f"the margin by {bumped - base:.1f} cycles, expected >= {want}; "
                 "the knob is not emitting a stalling instruction")

    # The scheduled rep period must NOT depend on the settle knob: the shortfall
    # is emitted as waiti, never as synci, so runs.charge_parity's
    # modified_ramsey_timing() needs no change for any value of it.
    #
    # The SAME matrix also has to assert the margin floor. Without that, the
    # worst case in this grid -- reset_read_settle=0.0 with
    # reset_readout_relax_delay=0.0 -- collapses the real margin to 0.8 tProc
    # cycles (1.9 ns), i.e. functionally the pre-fix bug, while every check here
    # still passed: the rep-period comparison below is insensitive to it, and the
    # per-cfg cases above only exercise the 0.5 us default. The floor in
    # mModifiedRamsey/mActiveResetVerify (MIN_RESET_READ_SETTLE_US) is what
    # actually prevents it; this is the check that would catch its removal.
    floor_us = min(MR_MIN_SETTLE_US, ARV_MIN_SETTLE_US)
    for settle in (0.0, 0.5, 2.0):
        for relax in (0.0, 5.0):
            cfg = reset_cfg(reset_cycles=2, reset_read_settle=settle,
                            reset_readout_relax_delay=relax)
            ref = reset_cfg(reset_cycles=2, reset_readout_relax_delay=relax)
            r.expect(rep_period_cycles_from_asm(ModifiedRamseyProgram(soccfg, dict(cfg)))
                     == rep_period_cycles_from_asm(ModifiedRamseyProgram(soccfg, dict(ref))),
                     f"reset_read_settle={settle} (relax={relax}) changed the "
                     "scheduled rep period; it must only emit waiti, which does "
                     "not advance the tProc time reference")
            for name, cls in (("ModifiedRamsey", ModifiedRamseyProgram),
                              ("ActiveResetVerify", ActiveResetVerifyProgram)):
                for m in read_settle_margins(cls(soccfg, dict(cfg))):
                    r.expect(m["margin_us"] >= floor_us - 1e-6,
                             f"{name} settle={settle} relax={relax} "
                             f"read{m.get('read_index', '?')}: real settle margin "
                             f"is {m['margin_us']:.5f} us, below the "
                             f"{floor_us} us floor. A cfg that disarms the stall "
                             "must be clamped in initialize(), not accepted.")

    r.expect(MR_MIN_SETTLE_US == ARV_MIN_SETTLE_US,
             f"MIN_RESET_READ_SETTLE_US is {MR_MIN_SETTLE_US} in mModifiedRamsey "
             f"but {ARV_MIN_SETTLE_US} in mActiveResetVerify; ActiveResetVerify "
             "would validate a different settle than the Ramsey runs")
    r.notes["settle_floor_us"] = floor_us

    r.expect_raises(ValueError,
                    lambda: ModifiedRamseyProgram(soccfg, dict(reset_cfg(
                        reset_read_settle=-1.0))),
                    "negative cfg['reset_read_settle'] was accepted (it would "
                    "compile to a negative waiti immediate)")
    r.notes["min_required_us"] = MIN_READ_SETTLE_US
    return r


def check_reset_parity(soccfg):
    """F11 -- the two active_reset_to_g() bodies must emit identical asm.

    ActiveResetVerify only validates ModifiedRamsey's reset if it runs the same
    instructions. check_reset_asm compares cmp_offset; this compares the whole
    emitted reset block, so a fix applied to one file and not the other fails
    here instead of silently invalidating every tier-C conclusion.
    """
    r = CheckResult("reset_parity", "F11, F6, F10")
    for reset_cycles in (1, 2):
        for relax, settle in ((5.0, 0.5), (0.0, 0.5), (5.0, 2.0)):
            cfg = reset_cfg(reset_cycles=reset_cycles, readout_threshold=1.0,
                            reset_readout_relax_delay=relax,
                            reset_read_settle=settle)
            mr = ModifiedRamseyProgram(soccfg, dict(cfg))
            arv = ActiveResetVerifyProgram(soccfg, dict(cfg))
            tag = f"reset_cycles={reset_cycles} relax={relax} settle={settle}"
            sig_mr = reset_asm_signature(mr)
            sig_arv = reset_asm_signature(arv)
            if not r.expect(len(sig_mr) == len(sig_arv),
                            f"{tag}: reset block is {len(sig_mr)} instructions in "
                            f"ModifiedRamsey and {len(sig_arv)} in "
                            "ActiveResetVerify"):
                continue
            first_diff = next((i for i, (a, b) in enumerate(zip(sig_mr, sig_arv))
                               if a != b), None)
            r.expect(first_diff is None,
                     f"{tag}: reset asm diverges at instruction {first_diff}: "
                     f"ModifiedRamsey {sig_mr[first_diff] if first_diff is not None else ''} "
                     f"vs ActiveResetVerify "
                     f"{sig_arv[first_diff] if first_diff is not None else ''}")
            for attr in ("cmp_offset", "reset_skip_op", "r_read", "r_thresh",
                         "reset_readout_syncdelay_cycles",
                         "reset_read_settle_cycles",
                         "reset_read_extra_wait_cycles"):
                r.expect(getattr(mr, attr) == getattr(arv, attr),
                         f"{tag}: {attr} is {getattr(mr, attr)} in ModifiedRamsey "
                         f"and {getattr(arv, attr)} in ActiveResetVerify")
            r.expect(read_settle_timings(mr) == read_settle_timings(arv),
                     f"{tag}: the two programs give different read settle margins")
    r.notes["signature_len_rc1"] = len(reset_asm_signature(
        ModifiedRamseyProgram(soccfg, dict(reset_cfg(readout_threshold=1.0)))))
    return r


def check_reset_capture_asm(soccfg):
    """F12 -- the r_read capture diagnostic is exact, and inert when disabled."""
    r = CheckResult("reset_capture_asm", "F12")
    if os.environ.get("ARV_RESET_CAPTURE"):
        r.notes["env_warning"] = (
            "ARV_RESET_CAPTURE is set in this shell. Every cfg below passes "
            "reset_capture explicitly so these checks are unaffected, but unset "
            "it before trusting any other check in this suite.")
    base = reset_cfg(reset_cycles=1, readout_threshold=1.0, reps=100)

    # OFF must be byte-identical to the program without the diagnostic
    off = ActiveResetVerifyProgram(soccfg, dict(base, reset_capture=False))
    stock = ActiveResetVerifyProgram(soccfg, dict(base))
    off.compile()
    stock.compile()
    r.expect(off.binprog == stock.binprog,
             "reset_capture=False changed the compiled program; the diagnostic is "
             "not inert")

    for reset_cycles in (1, 2):
        for with_tags in (True, False):
            cfg = dict(base, reset_cycles=reset_cycles, reset_capture=True,
                       reset_capture_tags=with_tags)
            prog = ActiveResetVerifyProgram(soccfg, dict(cfg))
            body, plist = _loop_body(prog)
            tag = f"rc={reset_cycles} tags={with_tags}"
            n_per_cycle = 2 if with_tags else 1

            reads = [i for i, x in enumerate(body) if x["name"] == "read"]
            offs = [i for i, x in enumerate(body)
                    if x["name"] == "mathi" and x["args"][4] == prog.cmp_offset]
            condjs = [i for i, x in enumerate(body) if x["name"] == "condj"]
            memws = [i for i, x in enumerate(body) if x["name"] == "memw"]
            r.expect(len(reads) == len(offs) == len(condjs) == reset_cycles,
                     f"{tag}: capture perturbed the read/mathi/condj counts "
                     f"({len(reads)}/{len(offs)}/{len(condjs)})")
            r.expect(len(memws) == reset_cycles * n_per_cycle,
                     f"{tag}: {len(memws)} memw, expected "
                     f"{reset_cycles * n_per_cycle}")
            for k in range(min(reset_cycles, len(offs), len(condjs))):
                mine = [i for i in memws if offs[k] < i < condjs[k]]
                if not r.expect(len(mine) == n_per_cycle,
                                f"{tag} cycle {k}: {len(mine)} capture memw "
                                "between the sign-safe mathi and the condj, "
                                f"expected {n_per_cycle}"):
                    continue
                # memw(page, r_data, r_addr) -> mem[r_addr] = r_data. Confirmed
                # against the tProc v1 encoding table (ctrl.sv: rb at bits 40..36
                # is the ADDRESS, ra at bits 35..31 is the DATA) and the datapath
                # (reg_addr0 = ir[40:36] -> dmem_addr, reg_addr1 = ir[35:31] ->
                # dmem_di). Swapping them would write r_read's value as an
                # address, i.e. scribble over program-visible memory.
                val_w = body[mine[-1]]
                r.expect(val_w["args"] == (prog.q_rp, prog.r_read, prog.r_capaddr),
                         f"{tag} cycle {k}: memw args {val_w['args']} are not "
                         f"(page={prog.q_rp}, data=r_read {prog.r_read}, "
                         f"addr=r_capaddr {prog.r_capaddr}) -- the data and "
                         "address registers are swapped")
            # the captured value must be the condj's operand, not the raw read
            for k in range(min(len(offs), len(condjs))):
                r.expect(reads[k] < offs[k] < condjs[k],
                         f"{tag} cycle {k}: read/mathi/condj order broken")

            for reg in (prog.r_capaddr, prog.r_captag):
                r.expect(reg not in (0, prog.r_read, prog.r_thresh),
                         f"{tag}: capture register {reg} collides with the zero "
                         "register / r_read / r_thresh")
                r.expect((prog.q_rp, reg) not in set(prog._gen_regmap.values())
                         and (prog.q_rp, reg) not in set(prog._ro_regmap.values()),
                         f"{tag}: capture register p{prog.q_rp} r{reg} is a "
                         "generator/readout pulse register on this firmware")
                r.expect(reg < 13,
                         f"{tag}: capture register {reg} is >= 13; it can collide "
                         "with the page-0 loop/shot counters (13-15), the trigger "
                         "bits (16) or the NDAverager counters (17-21)")

            # the address register must be initialised exactly once, OUTSIDE the
            # loop: a regwi inside would rewind the address every rep.
            init = _resolve_reg(plist, plist.index(body[0]), prog.q_rp,
                                prog.r_capaddr)
            r.expect(init == prog.capture_base,
                     f"{tag}: r_capaddr initialised to {init}, expected base "
                     f"{prog.capture_base}")
            r.expect(not [x for x in body if x["name"] == "regwi"
                          and x["args"][0] == prog.q_rp
                          and x["args"][1] in (prog.r_capaddr, prog.r_captag)],
                     f"{tag}: a capture register is re-initialised INSIDE the rep "
                     "loop, so every rep would overwrite the same dmem word")

            # the schedule must be untouched (memw/mathi advance no time)
            r.expect(rep_period_cycles_from_asm(prog)
                     == rep_period_cycles_from_asm(ActiveResetVerifyProgram(
                         soccfg, dict(cfg, reset_capture=False))),
                     f"{tag}: capture changed the scheduled rep period")
            # ... and so must the settle margin the fix installed
            r.expect(read_settle_timings(prog) == read_settle_timings(
                         ActiveResetVerifyProgram(soccfg,
                                                  dict(cfg, reset_capture=False))),
                     f"{tag}: capture changed the read settle margin; the "
                     "diagnostic must not perturb the bug it measures")

    # dmem capacity must be enforced loudly, never truncated silently
    dmem = int(soccfg["tprocs"][0]["dmem_size"])
    r.expect_raises(ValueError,
                    lambda: ActiveResetVerifyProgram(soccfg, dict(
                        base, reset_capture=True, reps=dmem)),
                    f"reps={dmem} at 2 words/rep exceeds dmem_size {dmem} but was "
                    "accepted")
    capped = ActiveResetVerifyProgram(soccfg, dict(
        base, reset_capture=True, reps=dmem, reset_capture_reps=64))
    r.expect(capped.cfg["reps"] == 64 and capped.capture_n_words == 128,
             "reset_capture_reps did not override cfg['reps'] "
             f"(reps={capped.cfg['reps']}, words={capped.capture_n_words})")
    r.expect(capped.loop_dims == [64],
             f"loop_dims is {capped.loop_dims} after the reset_capture_reps "
             "override; the tProc loop count and the acquisition would disagree")
    r.expect_raises(ValueError,
                    lambda: ActiveResetVerifyProgram(soccfg, dict(
                        base, use_active_reset=False, reset_capture=True)),
                    "reset_capture with use_active_reset=False was accepted, but "
                    "there is no condj operand to capture")

    # decoder round trip: an int32-negative accumulated I must survive the
    # UNSIGNED dmem readback (single_read hands back an mmio uint32)
    for raw in (-123456789, -1, 0, 1, 987654321):
        w = np.uint32(np.int32(raw + (1 << 28)))
        _, cmp_op, dec = decode_capture_words([w], 1 << 28, 1, with_tags=False)
        r.expect(int(dec.ravel()[0]) == raw,
                 f"decode_capture_words round trip failed for raw I {raw} (got "
                 f"{int(dec.ravel()[0])})")
        r.expect(int(cmp_op.ravel()[0]) == (raw + (1 << 28)),
                 f"decode_capture_words lost the condj operand for raw I {raw}")

    r.notes["dmem_size"] = dmem
    r.notes["base_addr"] = RESET_CAPTURE_BASE_ADDR
    r.notes["max_reps_rc1_with_tags"] = (dmem - RESET_CAPTURE_BASE_ADDR) // 2
    r.notes["prod_run_reps2000_fits"] = bool(
        RESET_CAPTURE_BASE_ADDR + 2 * 2000 <= dmem)
    return r


def check_timing_model(soccfg):
    """F7/F3 -- modified_ramsey_timing() vs the compiled program's sync sum."""
    r = CheckResult("timing_model", "F7, F3")
    timing = _timing_fn()

    cases = {
        "plain": base_cfg(),
        "echo": base_cfg(use_pi_pulse=True),
        "mr_relax_5us": base_cfg(mr_relax_delay=5.0),
        "mr_relax_20us": base_cfg(mr_relax_delay=20.0),
        # tau is now the pulse-CENTRE-to-CENTRE interval, so a usable df is
        # bounded by the envelope: df < 1/(8*sigma) (no pi). At sigma=0.1 us that
        # caps df at 1.25 MHz, so 2 MHz needs sigma < 0.0625 us or the program
        # correctly raises "parity phase condition is unreachable". Shrink sigma
        # rather than lowering df, to keep a genuinely short tau in the sweep.
        "df_2MHz": base_cfg(df=2.0, sigma=0.05),
        "short_readout": base_cfg(readout_length=2.0),
        "reset_1": reset_cfg(),
        "reset_2": reset_cfg(reset_cycles=2),
        "reset_2_echo_wait": reset_cfg(reset_cycles=2, use_pi_pulse=True,
                                       post_reset_wait=1.5, mr_relax_delay=3.0),
    }
    for label, cfg in cases.items():
        prog = ModifiedRamseyProgram(soccfg, dict(cfg))
        model = timing(soccfg, dict(cfg))
        asm_cycles = rep_period_cycles_from_asm(prog)
        r.expect(asm_cycles == model["scheduled_rep_period_tproc_cycles"],
                 f"{label}: asm sync sum {asm_cycles} != model "
                 f"{model['scheduled_rep_period_tproc_cycles']} tProc cycles")
        r.notes[label] = {"cycles": int(asm_cycles),
                          "us": round(model["scheduled_rep_period_us"], 4)}

    # F3 negative control: the spectroscopy relax_delay must NOT enter the
    # Ramsey schedule. Without this, F3 is untested -- the positive control
    # below would pass even if the program still used cfg["relax_delay"].
    slow_search = base_cfg(relax_delay=100000)
    r.expect(rep_period_cycles_from_asm(ModifiedRamseyProgram(soccfg, dict(slow_search)))
             == rep_period_cycles_from_asm(ModifiedRamseyProgram(soccfg, base_cfg())),
             "changing cfg['relax_delay'] moved the Ramsey rep period; "
             "mr_relax_delay is not actually separate")

    # positive control: mr_relax_delay must move it by exactly its tProc cycles
    delta_us = 7.0
    base_cycles = rep_period_cycles_from_asm(ModifiedRamseyProgram(soccfg, base_cfg()))
    bumped = rep_period_cycles_from_asm(
        ModifiedRamseyProgram(soccfg, base_cfg(mr_relax_delay=delta_us)))
    r.expect(bumped - base_cycles == soccfg.us2cycles(delta_us),
             f"mr_relax_delay={delta_us}us changed the period by "
             f"{bumped - base_cycles} cycles, expected {soccfg.us2cycles(delta_us)}")
    return r


def check_bfg_plumbing():
    """The uncommitted BFG changes: import paths and the NullYoko stub."""
    r = CheckResult("bfg_plumbing", "BFG plumbing")
    import importlib
    for mod in ("mTransmissionFF", "mSpecSliceFF", "mAmplitudeRabiFF"):
        full = ("WorkingProjects.QM_Team.qubit_measurements.Client_modules"
                ".Experiments." + mod)
        r.expect_no_raise(lambda m=full: importlib.import_module(m),
                          f"{mod} does not import from the repo root (a bare "
                          "'from utils import *' only resolves when cwd is "
                          "Experiments/)")

    from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Runners.runs.context import (
        NullYoko,
    )
    from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.utils import (
        ramp_to,
    )

    y = NullYoko(0.0)
    r.expect(float(y.query(":SOUR:LEV?")) == 0.0, "NullYoko level round-trip failed")
    r.expect_no_raise(lambda: y.write(":SOUR:LEV 0.0"),
                      "NullYoko rejected a same-value write")
    r.expect_no_raise(lambda: y.write(":SOUR:FUNC VOLT"),
                      "NullYoko rejected a non-level SCPI command")
    r.expect_raises(RuntimeError, lambda: y.write(":SOUR:LEV 0.005"),
                    "NullYoko silently faked a voltage change")

    # %.6f formatting would round this level, making ramp_to's own read-back
    # echo look like a real move.
    fine = NullYoko(0.00590001)
    r.expect(float(fine.query(":SOUR:LEV?")) == 0.00590001,
             "NullYoko.query rounds the level; ramp_to's read-back echo will "
             "raise for any start_voltage finer than 1e-6")
    r.expect_no_raise(lambda: ramp_to(fine, 0.00590001),
                      "ramp_to to the current level raised on NullYoko")
    return r


def run_offline_suite(soccfg=None, snapshot_path=None, out_dir=None, verbose=True):
    """Tier A. Needs only a QickConfig -- no board, no fridge."""
    source = "caller-supplied soccfg"
    if soccfg is None:
        soccfg, source = load_soccfg(snapshot_path)

    results = [
        _run(check_shot_buffers, soccfg),
        _run(check_tone_coverage, soccfg),
        _run(check_ro_ch_normalization, soccfg),
        _run(check_config_validation, soccfg),
        _run(check_reset_asm, soccfg),
        _run(check_reset_read_settle, soccfg),
        _run(check_reset_parity, soccfg),
        _run(check_reset_capture_asm, soccfg),
        _run(check_timing_model, soccfg),
        _run(check_bfg_plumbing),
    ]
    report = {
        "tier": "A (offline)",
        "timestamp": datetime.datetime.now().strftime("%Y_%m_%d_%H_%M_%S"),
        "soccfg_source": source,
        "board": soccfg["board"],
        "sw_version": soccfg._cfg.get("sw_version"),
        "passed": all(r.passed for r in results),
        "checks": [r.to_dict() for r in results],
    }
    if verbose:
        _print_report(report)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, f"verify_MR_offline_{report['timestamp']}.json")
        with open(path, "w") as f:
            json.dump(report, f, indent=2, default=str)
        report["sidecar"] = path
    return report


def _print_report(report):
    print("\n" + "=" * 74)
    print(f"verify_ModifiedRamsey -- tier {report['tier']}")
    print(f"soccfg: {report['soccfg_source']}  (board {report['board']}, "
          f"qick {report['sw_version']})")
    print("=" * 74)
    for c in report["checks"]:
        status = "PASS" if c["passed"] else "FAIL"
        print(f"  [{status}] {c['name']:<24} {c['fixes']}")
        if c["error"]:
            print(f"         ERROR {c['error']}")
            for line in c["notes"].get("traceback", []):
                print(f"           {line}")
        for f in c["failures"]:
            print(f"         - {f}")
        for k, v in c["notes"].items():
            if k not in ("traceback",):
                print(f"         . {k}: {v}")
    print("-" * 74)
    print("OVERALL: " + ("PASS" if report["passed"] else "FAIL"))
    print("=" * 74 + "\n")


# ---------------------------------------------------------------------------
# Tier B checks (board attached, no qubit signal required)
# ---------------------------------------------------------------------------

def check_board_env(soc, soccfg, snapshot_path=None, refresh=True):
    """Live soccfg vs the committed snapshot. A mismatch invalidates tier A."""
    r = CheckResult("board_env", "snapshot integrity")
    path = snapshot_path or DEFAULT_SNAPSHOT
    r.notes["live_board"] = soccfg["board"]
    r.notes["live_sw_version"] = soccfg._cfg.get("sw_version")
    r.notes["f_time"] = float(soccfg["tprocs"][0]["f_time"])
    r.notes["n_gens"] = len(soccfg["gens"])
    r.notes["n_readouts"] = len(soccfg["readouts"])
    r.notes["ro_f_output"] = [float(ro["f_output"]) for ro in soccfg["readouts"]]
    r.notes["ro_buf_maxlen"] = [int(ro["buf_maxlen"]) for ro in soccfg["readouts"]]
    r.notes["max_decimated_us"] = [
        round(float(ro["buf_maxlen"]) / float(ro["f_output"]), 3)
        for ro in soccfg["readouts"]]

    if os.path.exists(path):
        with open(path) as f:
            old = QickConfig(json.load(f))
        r.expect(float(old["tprocs"][0]["f_time"]) == float(soccfg["tprocs"][0]["f_time"]),
                 "tProc f_time changed vs snapshot")
        r.expect(len(old["gens"]) == len(soccfg["gens"]),
                 "generator count changed vs snapshot")
        r.expect(len(old["readouts"]) == len(soccfg["readouts"]),
                 "readout count changed vs snapshot")
        for i, (a, b) in enumerate(zip(old["gens"], soccfg["gens"])):
            r.expect(float(a["f_fabric"]) == float(b["f_fabric"]),
                     f"gen {i} f_fabric changed vs snapshot")
        for i, (a, b) in enumerate(zip(old["readouts"], soccfg["readouts"])):
            r.expect(float(a["f_output"]) == float(b["f_output"]),
                     f"readout {i} f_output changed vs snapshot")
            r.expect(int(a["buf_maxlen"]) == int(b["buf_maxlen"]),
                     f"readout {i} buf_maxlen changed vs snapshot")
        r.notes["snapshot"] = path
    else:
        r.notes["snapshot"] = "none -- writing one now"
    if refresh and (not os.path.exists(path) or r.passed):
        r.notes["snapshot_written"] = snapshot_soccfg(soccfg, path)
    return r


def prime_board(soc, soccfg, cfg_base, reps=16):
    """Throwaway acquisition to clear stale readout-buffer state.

    If a previous runner was killed mid-acquisition (Ctrl-C, a stopped job), the
    tProc is left looping and its readouts keep landing in the average buffer.
    The next program then reads a write pointer it did not produce, and qick
    reports 'got too much data: count=0, new_points=N, total_count=<your reps>'
    before dying in finish_round with a broadcast-shape error. Observed on the
    BFG board 2026-07-28: an identical suite passed cleanly, then failed exactly
    this way when relaunched seconds after a kill.

    One small discarded acquisition resynchronizes the pointer. Failures here
    are swallowed -- this is a cleanup step, not a check.
    """
    cfg = dict(cfg_base)
    cfg["reps"] = reps
    cfg["rounds"] = 1
    try:
        ModifiedRamseyProgram(soccfg, dict(cfg)).acquire(
            soc, load_pulses=True, progress=False)
        return {"primed": True}
    except Exception as e:
        return {"primed": False, "error": f"{type(e).__name__}: {e}"}


def check_buffer_shape(soc, soccfg, cfg_base, reps=200):
    """F9/F8 on hardware: acc_buf shape and one shot per rep."""
    r = CheckResult("buffer_shape", "F9, F8")
    for reset_cycles in (0, 1, 2):
        cfg = with_reset(cfg_base, reset_cycles) if reset_cycles else dict(cfg_base)
        cfg["reps"] = reps
        cfg["rounds"] = 1
        prog = ModifiedRamseyProgram(soccfg, dict(cfg))
        try:
            shots_i, shots_q = prog.acquire(soc, load_pulses=True, progress=False)
        except ValueError as e:
            if "broadcast" not in str(e):
                raise
            # stale-buffer signature (see prime_board): resync and retry once,
            # but say so -- a persistent failure here is a real defect.
            r.notes[f"reset_{reset_cycles}_retry"] = f"{type(e).__name__}: {e}"
            prime_board(soc, soccfg, cfg_base)
            prog = ModifiedRamseyProgram(soccfg, dict(cfg))
            shots_i, shots_q = prog.acquire(soc, load_pulses=True, progress=False)
        nreads = reset_cycles + 1
        r.expect(prog.acc_buf[0].shape == (reps, nreads, 2),
                 f"reset_cycles={reset_cycles}: acc_buf shape "
                 f"{prog.acc_buf[0].shape} != {(reps, nreads, 2)}")
        r.expect(shots_i.size == reps,
                 f"reset_cycles={reset_cycles}: {shots_i.size} shots for {reps} reps")
        r.expect(np.all(np.isfinite(shots_i)) and np.all(np.isfinite(shots_q)),
                 f"reset_cycles={reset_cycles}: non-finite shots")
    return r


def check_raw_i_scale(soc, soccfg, cfg_base, reps=1000):
    """F6 precondition: is the raw accumulator inside the sign-safe window?"""
    r = CheckResult("raw_i_scale", "F6")
    cfg = dict(cfg_base)
    cfg["reps"] = reps
    cfg["rounds"] = 1
    prog = ModifiedRamseyProgram(soccfg, dict(cfg))
    prog.acquire(soc, load_pulses=True, progress=False)
    raw_i = prog.acc_buf[0][..., 0].ravel().astype(np.int64)
    raw_q = prog.acc_buf[0][..., 1].ravel().astype(np.int64)
    offset = prog.cmp_offset

    r.notes["raw_i"] = {"min": int(raw_i.min()), "max": int(raw_i.max()),
                        "mean": float(raw_i.mean())}
    r.notes["raw_q"] = {"min": int(raw_q.min()), "max": int(raw_q.max())}
    r.notes["frac_negative_I"] = float(np.mean(raw_i < 0))
    r.notes["cmp_offset"] = int(offset)
    r.notes["headroom_ratio_max_over_offset"] = float(np.abs(raw_i).max() / offset)
    r.notes["readout_length_us"] = cfg["readout_length"]
    r.notes["window_cycles"] = int(prog.readout_window_cycles[cfg["ro_chs"][0]])

    r.expect(raw_i.min() > -offset,
             f"raw I minimum {raw_i.min()} is below -cmp_offset ({-offset}); the "
             "offset trick cannot make the compare sign-safe")
    r.expect(int(np.abs(raw_i).max()) + offset < 2 ** 31,
             f"raw I max {np.abs(raw_i).max()} + cmp_offset {offset} overflows the "
             "32-bit tProc register")
    # Informational, not a failure: tells you whether the unsigned-compare bug is
    # even reachable on this setup, which sets the expectation for tier C.
    r.notes["negative_branch_reachable"] = bool((raw_i < 0).any())
    return r


def check_decimated_tone_coverage(soc, soccfg, cfg_base):
    """F1 on hardware, within what the decimated buffer can actually show.

    The decimated capture starts at the ADC trigger and is exactly the readout
    window long, so the tone's trailing edge (which extends past the window by
    the cross-clock ceil extension) is OFF THE END of the record. What is
    observable is UNDER-coverage: samples collapsing to noise before the window
    closes. A true edge measurement needs a DAC->ADC loopback cable -- through
    the fridge, the resonator ringdown (~5 us at kappa/2pi ~ 190 kHz) swamps a
    ~1.6 ns generator-cycle edge.
    """
    r = CheckResult("decimated_tone_coverage", "F1")
    ro_ch = cfg_base["ro_chs"][0]
    rocfg = soccfg["readouts"][ro_ch]
    # get_decimated raises at >= buf_maxlen (readout.py), while acquire_decimated
    # only pre-checks > maxlen -- stay strictly below.
    max_us = 0.9 * float(rocfg["buf_maxlen"]) / float(rocfg["f_output"])
    r.notes["max_decimated_us"] = round(max_us, 3)

    lengths = [round(x, 3) for x in (0.5 * max_us, 0.75 * max_us, 0.9 * max_us)]
    extensions = set()
    for ro_len in lengths:
        cfg = dict(cfg_base)
        cfg.update({"readout_length": ro_len, "reps": 1, "rounds": 1,
                    "soft_avgs": 1})
        # drop the carried-over tone length so initialize() re-derives it from
        # the shortened window (that derivation is the thing under test)
        cfg.pop("length", None)
        prog = ModifiedRamseyProgram(soccfg, dict(cfg))
        extensions.add(prog.readout_tone_extension_cycles)
        trace = prog.acquire_decimated(soc, readouts_per_experiment=1,
                                       load_pulses=True, progress=False)
        arr = np.asarray(trace[0] if isinstance(trace, list) else trace)
        iq = arr.reshape(-1, 2) if arr.shape[-1] == 2 else np.moveaxis(arr, 0, -1)
        mag = np.abs(iq[:, 0] + 1j * iq[:, 1])
        n = mag.size
        head = float(np.median(mag[: max(1, n // 10)]))
        tail = float(np.median(mag[-max(1, n // 10):]))
        r.notes[f"len_{ro_len}us"] = {"samples": int(n), "head": round(head, 1),
                                      "tail": round(tail, 1),
                                      "extension_cycles": int(prog.readout_tone_extension_cycles)}
        r.expect(tail > 0.2 * head,
                 f"readout_length={ro_len}us: tone amplitude collapses before the "
                 f"integration window closes (head {head:.1f} -> tail {tail:.1f}); "
                 "the resonator pulse is shorter than adc_trig_offset + window")
    r.notes["extensions_seen"] = sorted(int(e) for e in extensions)
    if len(extensions) == 1:
        r.notes["coverage_gap"] = (
            "all decimated lengths landed on extension=%s; the other branch of "
            "the cross-clock ceil is only covered offline (check_tone_coverage)"
            % sorted(extensions)[0])
    return r


def check_rep_period(soc, soccfg, cfg_base, reps=5000,
                     delays_us=(0.0, 5.0, 10.0, 20.0), n_timing_samples=3):
    """F7/F3 on hardware: the scheduled period must match the real cadence.

    Differential, not absolute: config_all + envelope loading + Pyro round trips
    add hundreds of ms of variable overhead to a ~60 ms tProc run, so only the
    SLOPE of elapsed-time vs mr_relax_delay is trustworthy. It must equal reps.
    Timing comes from run_rounds(), which runs the program to completion with no
    data transfer at all.
    """
    r = CheckResult("rep_period", "F7, F3")
    timing = _timing_fn()

    for reset_cycles in (0, 1, 2):
        elapsed = []
        scheduled = []
        for d in delays_us:
            cfg = with_reset(cfg_base, reset_cycles) if reset_cycles else dict(cfg_base)
            cfg["reps"] = reps
            cfg["rounds"] = 1
            cfg["mr_relax_delay"] = d
            prog = ModifiedRamseyProgram(soccfg, dict(cfg))
            r.expect(prog.rounds == 1,
                     f"prog.rounds is {prog.rounds}, not 1; rounds multiplies the "
                     "total time and would scale the slope")
            model = timing(soccfg, dict(cfg))
            scheduled.append(model["scheduled_rep_period_us"])
            # Warm the program in (envelope load, first-touch allocation), then
            # take the MIN of several timed runs. The floor is the quantity of
            # interest: any single run can be inflated by OS scheduling, a Pyro
            # hiccup, or a leftover tProc program from a killed process (one
            # 7.9 s outlier against an 89 ms expectation was observed exactly
            # that way). A min is not cherry-picking -- the scheduled period is
            # a lower bound, so an inflated sample carries no information.
            prog.run_rounds(soc, load_pulses=True, progress=False)
            samples = []
            for _ in range(n_timing_samples):
                t0 = time.perf_counter()
                prog.run_rounds(soc, load_pulses=False, progress=False)
                samples.append((time.perf_counter() - t0) * 1e6)
            elapsed.append(min(samples))
            spread = (max(samples) - min(samples)) / max(min(samples), 1e-9)
            if spread > 0.25:
                r.notes.setdefault("timing_spread", {})[
                    f"reset_{reset_cycles}_delay_{d}"] = {
                        "samples_us": [round(s, 1) for s in samples],
                        "spread_frac": round(spread, 3)}

        slope = np.polyfit(np.array(delays_us, dtype=float),
                           np.array(elapsed, dtype=float), 1)[0]
        r.notes[f"reset_{reset_cycles}"] = {
            "elapsed_us": [round(e, 1) for e in elapsed],
            "scheduled_us_per_rep": [round(s, 4) for s in scheduled],
            "measured_us_per_rep": [round(e / reps, 4) for e in elapsed],
            "slope_vs_reps": round(float(slope) / reps, 4),
        }
        r.expect(abs(slope / reps - 1.0) < 0.05,
                 f"reset_cycles={reset_cycles}: d(elapsed)/d(mr_relax_delay) is "
                 f"{slope:.0f} us/us, expected {reps} (+-5%). Either the syncdelay "
                 "is not reaching the tProc or rounds != 1.")
        for e, s in zip(elapsed, scheduled):
            r.expect(s <= e / reps * 1.02,
                     f"reset_cycles={reset_cycles}: scheduled {s:.3f} us/rep "
                     f"exceeds measured {e / reps:.3f} us/rep -- the timing model "
                     "over-counts")
    return r


def run_modified_ramsey_fixed_voltage(ctx, params):
    """One real ModifiedRamsey acquisition at the present voltage.

    run_modified_ramsey() cannot run without a calibrated single shot (it calls
    get_apriori_separator_from_singleshot before the loop) and without the YOKO
    (it steps the voltage when the two-tone doublet search fails). This bypasses
    both: fixed f_ge, explicit df, no search. The IQ is not parity physics on an
    uncalibrated qubit -- the point is to exercise acquire -> raw_shot_buffers ->
    timing record -> plot -> save_data end to end.
    """
    timing = _timing_fn()
    cfg = ctx.working_config()
    mr_cfg = {
        "f_ge": params.get("f_ge", ctx.qubit_frequency_center),
        "df": params.get("df", 0.5),
        "pi2_gain": ctx.pi2_gain,
        "pi_gain": ctx.qubit_gain,
        "use_pi_pulse": params.get("use_pi_pulse", False),
        "flip_final_pi2": params.get("flip_final_pi2", False),
        "symmetric_ramsey": params.get("symmetric_ramsey", False),
        "use_active_reset": params.get("use_active_reset", False),
        "reset_cycles": params.get("reset_cycles", 1),
        "reset_ground_below_threshold": params.get("reset_ground_below_threshold", True),
        "reset_readout_relax_delay": params.get("reset_readout_relax_delay", 5.0),
        "post_reset_wait": params.get("post_reset_wait", 0.0),
        "mr_relax_delay": params.get("mr_relax_delay", 0.0),
        "sigma": ctx.qubit_sigma,
        "flattop_length": ctx.qubit_flattop,
        "reps": params.get("mr_reps", 2000),
        # never inherit rounds: it multiplies the acquisition and breaks the
        # per-shot interpretation of the record.
        "rounds": 1,
        "current_voltage": float(ctx.yoko.query(":SOUR:LEV?")),
        "Qubit_number": ctx.Qubit_Readout,
    }
    if params.get("readout_threshold") is not None:
        mr_cfg["readout_threshold"] = params["readout_threshold"]
    config_mr = cfg | mr_cfg
    config_mr["modified_ramsey_timing"] = timing(ctx.soccfg, config_mr)

    inst = ModifiedRamsey(path="VerifyModifiedRamsey", cfg=config_mr, soc=ctx.soc,
                          soccfg=ctx.soccfg, outerFolder=ctx.outerFolder)
    data = inst.acquire()
    inst.display(data, plotDisp=False, figNum=90)
    inst.save_data(data)
    inst.save_config()

    shots_i = np.ravel(data["data"]["shots_i"])
    return {
        "n_shots": int(shots_i.size),
        "reps_requested": int(config_mr["reps"]),
        "scheduled_rep_period_us": config_mr["modified_ramsey_timing"]["scheduled_rep_period_us"],
        "streamer_average_rep_period_us": data["data"]["streamer_average_rep_period_us"],
        "tau_us": data["data"]["tau_us"],
        "file": inst.fname,
    }


def run_board_suite(ctx, params=None, out_dir=None):
    """Tier B. Needs a live board; no qubit signal, no YOKO, no calibration."""
    params = params or {}
    # Real device config, not the synthetic base_cfg fixture: these stages pulse
    # the actual DACs, so channels/frequencies/gains must be this setup's.
    cfg_base = device_cfg(ctx, **(params.get("cfg_overrides") or {}))
    out_dir = out_dir or os.path.join(ctx.outerFolder, "VerifyModifiedRamsey")
    os.makedirs(out_dir, exist_ok=True)
    print("[verify_MR] device cfg: res_ch=%s qubit_ch=%s ro_chs=%s pulse_freq=%s "
          "pulse_gain=%s readout_length=%s adc_trig_offset=%s f_ge=%s"
          % (cfg_base.get("res_ch"), cfg_base.get("qubit_ch"), cfg_base.get("ro_chs"),
             cfg_base.get("pulse_freq"), cfg_base.get("pulse_gain"),
             cfg_base.get("readout_length"), cfg_base.get("adc_trig_offset"),
             cfg_base.get("f_ge")))

    results = [_run(check_board_env, ctx.soc, ctx.soccfg,
                    params.get("snapshot_path"), params.get("refresh_snapshot", True))]
    if not results[0].passed and not params.get("force", False):
        print("[verify_MR] board_env failed -- the committed snapshot does not "
              "describe this board, so offline results are void. Fix or refresh "
              "the snapshot, or pass force=True.")
    else:
        # Clear any stale readout-buffer state before the first real
        # acquisition (see prime_board).
        results[0].notes["prime"] = prime_board(ctx.soc, ctx.soccfg, cfg_base)
        results += [
            _run(check_buffer_shape, ctx.soc, ctx.soccfg, cfg_base,
                 params.get("buffer_reps", 200)),
            _run(check_raw_i_scale, ctx.soc, ctx.soccfg, cfg_base,
                 params.get("raw_i_reps", 1000)),
            _run(check_decimated_tone_coverage, ctx.soc, ctx.soccfg, cfg_base),
            _run(check_rep_period, ctx.soc, ctx.soccfg, cfg_base,
                 params.get("rep_period_reps", 5000)),
        ]

    report = {
        "tier": "B (board)",
        "timestamp": datetime.datetime.now().strftime("%Y_%m_%d_%H_%M_%S"),
        "soccfg_source": "live",
        "board": ctx.soccfg["board"],
        "sw_version": ctx.soccfg._cfg.get("sw_version"),
        "passed": all(r.passed for r in results),
        "checks": [r.to_dict() for r in results],
    }
    if params.get("run_fixed_voltage_ramsey", True):
        try:
            report["fixed_voltage_ramsey"] = run_modified_ramsey_fixed_voltage(
                ctx, params.get("ramsey_params", {}))
        except Exception as e:
            report["fixed_voltage_ramsey"] = {"error": f"{type(e).__name__}: {e}"}
            report["passed"] = False

    _print_report(report)
    if "fixed_voltage_ramsey" in report:
        print("  fixed-voltage ModifiedRamsey:", report["fixed_voltage_ramsey"])
    print(_TIER_C_CHECKLIST)

    path = os.path.join(out_dir, f"verify_MR_board_{report['timestamp']}.json")
    with open(path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    report["sidecar"] = path
    print(f"[verify_MR] report written to {path}")
    return report


if __name__ == "__main__":
    import sys
    rep = run_offline_suite()
    print(_TIER_C_CHECKLIST)
    sys.exit(0 if rep["passed"] else 1)
