import os

from qick import *
import matplotlib.pyplot as plt
import numpy as np
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.CoreLib.Experiment import ExperimentClass
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Helpers.shot_buffers import raw_shot_buffers


# ======================================================================
# r_read capture diagnostic (tProc v1)
#
# The reset decision variable r_read lives in a tProc register and has never
# been observable from Python -- which is why a condj firing on ~50% of shots,
# uncorrelated with the qubit state, survived a full regression suite (see the
# 2026-07-28 data quoted in ActiveResetVerifyProgram.active_reset_to_g). When
# enabled, the reset block mirrors the exact condj operand into the tProc data
# memory once per reset cycle; acquire() reads dmem back and compares it, shot
# by shot, against the accumulated I that the SAME acquisition handed to Python
# in prog.acc_buf.
#
# Turning it on requires NO runner edit (Runners/ is out of edit scope, and
# run_active_reset_verify passes a fixed cfg literal):
#     Windows cmd:  set ARV_RESET_CAPTURE=1     then run the runner unchanged
#     PowerShell:   $env:ARV_RESET_CAPTURE = "1"
#     bash:         export ARV_RESET_CAPTURE=1
# or pass cfg["reset_capture"]=True, or flip RESET_CAPTURE_DEFAULT below.
# Precedence: cfg key > env var > module default. Default OFF, and with it off
# the compiled program is byte-identical to the program without the diagnostic
# (verify_ModifiedRamsey.check_reset_capture_asm asserts that on binprog).
# ======================================================================
RESET_CAPTURE_DEFAULT = False
RESET_CAPTURE_ENV = "ARV_RESET_CAPTURE"
# dmem word 1 is AveragerProgram.COUNTER_ADDR (the rep counter, rewritten every
# rep and zeroed by clear_tproc_counter); word 0 is left alone. 4 is the first
# address nothing in qick touches.
RESET_CAPTURE_BASE_ADDR = 4
RESET_CAPTURE_SENTINEL = 0xDEADBEEF  # prefill, so "never written" stays visible

# Minimum real tProc stall (us) between the reset readout window closing and the
# feedback `read`. The accumulated word has to cross the avg buffer's async FIFO
# into the PS clock domain and then an AXIS converter into the tProc domain --
# tens to ~150 ns. 0.5 us is ~3x that and is free in practice: the runners
# already wait 5 us here for the resonator to ring down. Must match
# mModifiedRamsey.MIN_RESET_READ_SETTLE_US (verify_ModifiedRamsey asserts it).
MIN_RESET_READ_SETTLE_US = 0.5


def _reset_capture_enabled(cfg):
    """(enabled, explicit) -- explicit=True only when cfg asked for it by name.

    The distinction is load-bearing. run_active_reset_verify sweeps six
    conditions and the first two have use_active_reset=False, so there is no
    condj operand to capture. An explicit cfg["reset_capture"]=True on such a
    condition is a mistake worth raising on; the ARV_RESET_CAPTURE env var
    (the only way to enable the diagnostic without editing Runners/, which is
    out of edit scope) necessarily applies to all six, so those two must
    degrade to capture-off instead of killing the sweep before any data is
    taken.
    """
    if "reset_capture" in cfg:
        return bool(cfg["reset_capture"]), True
    env = os.environ.get(RESET_CAPTURE_ENV)
    if env is not None:
        return env.strip() not in ("", "0", "false", "False"), False
    return RESET_CAPTURE_DEFAULT, False


def decode_capture_words(words, cmp_offset, reset_cycles, with_tags=True):
    """Decode the raw dmem readback into (tags, cmp_operand, raw_i).

    Layout per rep, per reset cycle: [tag, r_read+cmp_offset], or just the value
    when with_tags is False. Words come back UNSIGNED (single_read hands back an
    mmio uint32), so a negative accumulated I arrives as a large unsigned word
    and has to be decoded through int32 -- which is also exactly how the tProc's
    32-bit register held it.
    """
    stride = 2 if with_tags else 1
    w = np.asarray(words, dtype=np.uint32).reshape(-1, stride * reset_cycles)
    if with_tags:
        tags = w[:, 0::2].astype(np.int64)
        vals = w[:, 1::2]
    else:
        tags = None
        vals = w
    vals = np.ascontiguousarray(vals, dtype=np.uint32)
    cmp_operand = vals.astype(np.int64)                  # as the tProc compares it
    raw_i = vals.view(np.int32).astype(np.int64) - cmp_offset
    return tags, cmp_operand, raw_i


def analyze_reset_capture(words, acc_i, reads_per_rep, reset_cycles, cmp_offset,
                          thresh_cmp, skip_op, with_tags=True, max_lag=3,
                          sentinel=RESET_CAPTURE_SENTINEL, is_ground=None):
    """Locate the captured r_read inside this acquisition's own readout stream.

    acc_i : (reps, reads_per_rep) raw accumulated I from prog.acc_buf[0][...,0]
            (rep-major, read-minor; reads 0..reset_cycles-1 are the reset reads).
    is_ground : optional (reps,) bool classification of the FIRST verification
            read, used for the P(|g>) | pi fired) closure.

    Two families of hypotheses are tested by EXACT integer equality:
      H_position(d): the tProc saw the readout d positions away from this rep's
                     own reset read. d=0 is correct; d=-1 is the previous rep's
                     LAST verification read, i.e. the one-readout-lag model.
      H_fifo(d):     the tProc input advances once per `read` INSTRUCTION, so
                     capture k sees readout k-d of the whole run (it would then
                     fall behind by reads_per_rep-1 every rep).
    """
    raw_words = np.asarray(words, dtype=np.uint32)
    tags, cmp_operand, raw_i = decode_capture_words(
        words, cmp_offset, reset_cycles, with_tags)
    reps = int(acc_i.shape[0])
    cmp_operand, raw_i = cmp_operand[:reps], raw_i[:reps]
    if tags is not None:
        tags = tags[:reps]
    flat = np.asarray(acc_i, dtype=np.int64).ravel()      # rep-major, read-minor

    n_cap = reps * reset_cycles
    k = np.arange(n_cap)
    rep = k // reset_cycles
    cyc = k % reset_cycles
    cap = raw_i.ravel()
    pos_base = rep * reads_per_rep + cyc                  # this rep's OWN reset read

    out = {"reps": reps, "reset_cycles": int(reset_cycles),
           "reads_per_rep": int(reads_per_rep)}
    out["n_sentinel_left"] = int(np.count_nonzero(raw_words == np.uint32(sentinel)))
    out["tags_ok"] = (None if tags is None
                      else bool(np.array_equal(tags.ravel(), np.arange(n_cap))))
    out["n_distinct_values"] = int(np.unique(cap).size)
    out["frac_repeat_of_previous"] = (float(np.mean(cap[1:] == cap[:-1]))
                                      if n_cap > 1 else 0.0)

    def frac_match(idx):
        ok = (idx >= 0) & (idx < flat.size)
        return 0.0 if not ok.any() else float(np.mean(cap[ok] == flat[idx[ok]]))

    def corr_fit(idx):
        ok = (idx >= 0) & (idx < flat.size)
        if ok.sum() < 10:
            return 0.0, 0.0
        x = flat[idx[ok]].astype(float)
        y = cap[ok].astype(float)
        if x.std() == 0 or y.std() == 0:
            return 0.0, 0.0
        return float(np.corrcoef(x, y)[0, 1]), float(np.polyfit(x, y, 1)[0])

    lags = range(-max_lag, max_lag + 1)
    out["H_position"] = {d: round(frac_match(pos_base + d), 4) for d in lags}
    out["H_fifo"] = {d: round(frac_match(k + d), 4) for d in lags}
    corrs = {("pos", d): corr_fit(pos_base + d) for d in lags}
    corrs.update({("fifo", d): corr_fit(k + d) for d in lags})
    best_c = max(corrs, key=lambda key: abs(corrs[key][0]))
    out["best_correlation"] = {"hypothesis": "%s%+d" % best_c,
                               "r": round(corrs[best_c][0], 4),
                               "slope": round(corrs[best_c][1], 6)}
    best_pos = max(out["H_position"], key=lambda d: out["H_position"][d])
    best_fifo = max(out["H_fifo"], key=lambda d: out["H_fifo"][d])
    out["best_position_lag"] = (int(best_pos), out["H_position"][best_pos])
    out["best_fifo_lag"] = (int(best_fifo), out["H_fifo"][best_fifo])

    if raw_words.size and out["n_sentinel_left"] == raw_words.size:
        verdict = ("MEMW NEVER WROTE: the whole capture region is still the "
                   "sentinel. The capture itself is broken -- do not interpret "
                   "anything else in this report.")
    elif tags is not None and not out["tags_ok"]:
        verdict = ("CAPTURE ADDRESSING BROKEN: the tag ramp is not 0..N-1, so "
                   "the memw argument order or the address register is wrong. "
                   "The captured values are not trustworthy.")
    elif out["H_position"].get(0, 0.0) > 0.99:
        verdict = ("CORRECT: r_read IS this rep's own reset readout. The "
                   "one-readout-lag model is REFUTED for this run -- if P(|g>) "
                   "is still wrong the fault is the threshold/compare (sign, "
                   "scale, res_phase rotation), not the read timing.")
    elif out["H_position"].get(-1, 0.0) > 0.99:
        verdict = ("ONE-READOUT LAG: r_read is the PREVIOUS readout (rep n-1's "
                   "LAST verification read). The tProc input had not been "
                   "updated by the reset readout when `read` executed -- the "
                   "settle stall is missing or too short.")
    elif out["H_fifo"][best_fifo] > 0.99:
        verdict = ("INPUT DESYNC: r_read tracks the read-order stream with "
                   "offset %d -- the tProc input advances once per `read` "
                   "instruction, so it falls behind by (reads_per_rep-1) every "
                   "rep." % best_fifo)
    elif out["n_distinct_values"] <= 1:
        verdict = ("TPROC INPUT NEVER UPDATES: every captured r_read is the same "
                   "word. Suspect the `read` channel: it must be the tProc input "
                   "PORT soccfg['readouts'][ro_ch]['tproc_ch'], not the readout "
                   "index (they coincide on the BFG board only by luck).")
    elif abs(out["best_correlation"]["r"]) > 0.95:
        verdict = ("SCALED MATCH: no exact equality, but hypothesis %s "
                   "correlates at r=%.3f with slope %.4g -- the tProc sees a "
                   "scaled copy, so the raw threshold is wrong by that factor."
                   % (out["best_correlation"]["hypothesis"],
                      out["best_correlation"]["r"],
                      out["best_correlation"]["slope"]))
    else:
        verdict = ("UNMATCHED: the captured r_read is not any readout of this "
                   "acquisition, at any tested lag or scale.")
    out["verdict"] = verdict

    # Decision reconstruction: what the condj actually did, against what it
    # should have done from this rep's own reset read.
    ops = {"<": np.less, ">": np.greater, "<=": np.less_equal, ">=": np.greater_equal}
    op = ops[skip_op]
    fire_actual = ~op(cmp_operand.ravel(), thresh_cmp)
    own_cmp = flat[np.clip(pos_base, 0, max(flat.size - 1, 0))] + cmp_offset
    fire_correct = ~op(own_cmp, thresh_cmp)
    out["frac_pi_fired"] = float(np.mean(fire_actual))
    out["frac_pi_should_have_fired"] = float(np.mean(fire_correct))
    out["decision_agreement"] = float(np.mean(fire_actual == fire_correct))
    if is_ground is not None and reset_cycles == 1:
        g = np.asarray(is_ground, dtype=bool)[:reps]
        out["p_ground_given_fired"] = (float(np.mean(g[fire_actual]))
                                       if fire_actual.any() else float("nan"))
        out["p_ground_given_skipped"] = (float(np.mean(g[~fire_actual]))
                                         if (~fire_actual).any() else float("nan"))

    # Flat numeric arrays for the caller to save. ExperimentClass.save_data does
    # np.array() on every top-level key, so nested dicts/strings are not allowed
    # through: the verdict goes to stdout and a text sidecar instead.
    out["arrays"] = {
        "capture_tag": (np.zeros(0, dtype=np.int64) if tags is None
                        else tags.ravel().astype(np.int64)),
        "capture_raw_i": cap.astype(np.int64),
        "capture_cmp_operand": cmp_operand.ravel().astype(np.int64),
        "capture_own_reset_i": flat[np.clip(pos_base, 0, max(flat.size - 1, 0))],
        "capture_prev_read_i": flat[np.clip(pos_base - 1, 0, max(flat.size - 1, 0))],
        "capture_fire_actual": fire_actual.astype(np.int8),
        "capture_fire_correct": fire_correct.astype(np.int8),
    }
    return out


def format_capture_report(res, header="", n_show=8):
    """Human-readable verdict. This text is the whole point of the diagnostic."""
    L = ["=" * 72, "[ARV reset-capture] " + header, "=" * 72]
    L.append("  reps=%d  reset_cycles=%d  reads_per_rep=%d"
             % (res["reps"], res["reset_cycles"], res["reads_per_rep"]))
    L.append("  tag ramp 0..N-1 intact  : %s" % res["tags_ok"])
    L.append("  sentinel words left     : %d  (0 = every capture slot written)"
             % res["n_sentinel_left"])
    L.append("  distinct captured r_read: %d   repeat-of-previous: %.1f%%"
             % (res["n_distinct_values"], 100 * res["frac_repeat_of_previous"]))
    L.append("")
    L.append("  EXACT-match fraction, captured r_read vs acc_buf accumulated I:")
    for d in sorted(res["H_position"]):
        tag = {0: "this rep's own reset read",
               -1: "PREVIOUS read (rep n-1 last verify read)",
               1: "NEXT read"}.get(d, "position %+d" % d)
        L.append("     pos %+d  %-42s %.4f%s"
                 % (d, tag, res["H_position"][d],
                    "   <-- MATCH" if res["H_position"][d] > 0.99 else ""))
    for d in sorted(res["H_fifo"]):
        L.append("     fifo%+d  %-42s %.4f%s"
                 % (d, "read-order stream (pop-per-read)", res["H_fifo"][d],
                    "   <-- MATCH" if res["H_fifo"][d] > 0.99 else ""))
    L.append("  best correlation: %s  r=%.4f  slope=%.6g"
             % (res["best_correlation"]["hypothesis"],
                res["best_correlation"]["r"], res["best_correlation"]["slope"]))
    L.append("")
    L.append("  VERDICT: " + res["verdict"])
    L.append("")
    L.append("  decision: corrective pi FIRED on %.1f%% of shots; from this rep's"
             % (100 * res["frac_pi_fired"]))
    L.append("            own reset read it SHOULD have fired on %.1f%%;"
             % (100 * res["frac_pi_should_have_fired"]))
    L.append("            agreement %.1f%%  (50%% = the decision carries no "
             "information)" % (100 * res["decision_agreement"]))
    if "p_ground_given_fired" in res:
        L.append("  P(|g>) on verify read 0 | pi fired   = %.3f"
                 % res["p_ground_given_fired"])
        L.append("  P(|g>) on verify read 0 | pi skipped = %.3f"
                 % res["p_ground_given_skipped"])
    a = res["arrays"]
    L.append("")
    L.append("  first %d captures:   tag   captured r_read   this rep reset I"
             "    prev read I" % n_show)
    for i in range(min(n_show, a["capture_raw_i"].size)):
        L.append("     %8d %17d %17d %14d"
                 % ((a["capture_tag"][i] if a["capture_tag"].size else -1),
                    a["capture_raw_i"][i], a["capture_own_reset_i"][i],
                    a["capture_prev_read_i"][i]))
    L.append("=" * 72)
    return "\n".join(L)


class ActiveResetVerifyProgram(AveragerProgram):
    """
    Verification harness for the hardware active reset used by ModifiedRamsey.

    Per-shot sequence (each optional stage is config-gated):

        [prep pi -> |e>]  ->  [active reset -> |g>]  ->  N verification readouts

    The active-reset block here is a faithful copy of
    ModifiedRamseyProgram.active_reset_to_g() so this experiment validates the
    EXACT mechanism the Modified Ramsey relies on (measure -> read accumulated I
    -> conditionally apply a corrective pi only when the qubit is found in |e>).

    The point of the verification is differential. Resetting from thermal
    equilibrium (already mostly |g>) cannot distinguish a working reset from a
    qubit that was already cold, so the driver sweeps four conditions:

        prep |g>, reset off  -> thermal baseline
        prep |e>, reset off  -> control: qubit stays excited
        prep |g>, reset on   -> should be |g>
        prep |e>, reset on   -> KEY PROOF: reset recovers |g> from |e>

    For each condition the qubit is read out N times in a row, so P(|g>) can be
    tracked vs readout index (a working, QND reset gives a flat, high P(|g>)).

    Config keys (channel/pulse keys shared with ModifiedRamsey):
    cfg["prep_excited"]        : if True, play a pi pulse (pi_gain) before the
                                 reset block to deterministically prepare |e>.
                                 Default False.
    cfg["n_verify_reads"]      : number of back-to-back readouts after the reset
                                 block (default 5).
    cfg["verify_relax_delay"]  : syncdelay (us) between consecutive verification
                                 readouts (default 5.0). The LAST verification
                                 read uses cfg["relax_delay"] instead so the
                                 qubit re-thermalises before the next rep (so the
                                 prep stage starts from |g>).

    Active-reset config (identical meaning to ModifiedRamsey):
    cfg["use_active_reset"]            : enable the reset block (default False).
    cfg["readout_threshold"]           : single-shot I discrimination threshold in
                                         the normalized collect_shots() units.
    cfg["reset_ground_below_threshold"]: True (default) if |g> sits below threshold
                                         in I.
    cfg["reset_cycles"]                : measure->feedback rounds per shot (default 1).
    cfg["pi_gain"]                     : DAC gain for the prep pi and the corrective
                                         reset flip (same gaussian envelope).
    cfg["reset_readout_relax_delay"]   : syncdelay (us) after each reset readout
                                         (default 1.0).
    cfg["reset_read_settle"]           : MINIMUM real tProc stall (us) between the
                                         reset readout window closing and the
                                         `read` that feeds the condj (default
                                         0.5). Load-bearing; see the long comment
                                         in active_reset_to_g(). Only the
                                         SHORTFALL against
                                         reset_readout_relax_delay is emitted, as
                                         a waiti, so the scheduled rep period is
                                         unchanged for every cfg.
    cfg["post_reset_wait"]             : settle time (us) after the reset block
                                         (default 0.0).
    cfg["reset_force_pi"]              : diagnostic; fire the corrective pi
                                         UNCONDITIONALLY (skip the condj) to
                                         measure the bare post-readout pi
                                         fidelity (default False).

    r_read capture diagnostic (default OFF, see RESET_CAPTURE_DEFAULT):
    cfg["reset_capture"]           : mirror the exact condj operand into the tProc
                                     data memory once per reset cycle, so the
                                     decision variable becomes observable from
                                     Python and comparable against acc_buf.
                                     Defaults to the ARV_RESET_CAPTURE env var,
                                     else RESET_CAPTURE_DEFAULT (False). With it
                                     off the compiled program is byte-identical.
    cfg["reset_capture_reps"]      : diagnostic-only override of cfg["reps"] (dmem
                                     is 4096 words, a production run may not fit).
                                     Applied inside initialize(), before
                                     make_program reads cfg["reps"].
    cfg["reset_capture_base_addr"] : first dmem word to use (default 4; word 1 is
                                     AveragerProgram.COUNTER_ADDR).
    cfg["reset_capture_tags"]      : also write a monotone counter word per
                                     capture (default True). The 0..N-1 ramp is
                                     the self-check on the memw addressing;
                                     False halves the dmem footprint.
    cfg["reset_capture_prefill"]   : sentinel-fill the region first (default True)
                                     so "never written" is distinguishable from
                                     "wrote the wrong value".
    cfg["reset_capture_max_lag"]   : lags tested by the analyzer (default 3).
    """

    def initialize(self):
        cfg = self.cfg

        if cfg["sigma"] <= 0:
            raise ValueError("cfg['sigma'] must be positive")
        if cfg["readout_length"] <= 0:
            raise ValueError("cfg['readout_length'] must be positive")
        if not cfg["ro_chs"]:
            raise ValueError("cfg['ro_chs'] must contain at least one readout channel")
        for delay_key in (
            "adc_trig_offset",
            "verify_relax_delay",
            "relax_delay",
            "reset_readout_relax_delay",
            "post_reset_wait",
            "reset_read_settle",
        ):
            if cfg.get(delay_key, 0.0) < 0:
                raise ValueError(f"cfg['{delay_key}'] must be non-negative")

        # r_read capture diagnostic. Resolved FIRST because it may shrink
        # cfg["reps"], and make_program() reads cfg["reps"] immediately after
        # initialize() returns (averager_program.py make_program), with loop_dims
        # built after that -- so an override here is picked up by the tProc loop
        # counter, by loop_dims and by collect_shots alike.
        self.reset_capture, self.reset_capture_explicit = (
            _reset_capture_enabled(cfg))
        # The two reset-OFF conditions of the ARV sweep have no condj operand to
        # capture. When the diagnostic was switched on globally (env var), those
        # two must degrade quietly instead of raising and killing the sweep
        # before any data is taken.
        if self.reset_capture and not self.reset_capture_explicit:
            if not cfg.get("use_active_reset", False) or int(
                    cfg.get("reset_cycles", 1)) < 1:
                print("[ARV reset-capture] OFF for this condition "
                      "(use_active_reset=%s, reset_cycles=%s): no condj operand "
                      "to capture. The reset-ON conditions in the same sweep "
                      "still capture."
                      % (cfg.get("use_active_reset", False),
                         cfg.get("reset_cycles", 1)))
                self.reset_capture = False
        if self.reset_capture and cfg.get("reset_capture_reps") is not None:
            cap_reps = int(cfg["reset_capture_reps"])
            if cap_reps != int(cfg["reps"]):
                print("[ARV reset-capture] cfg['reps'] %d -> %d "
                      "(reset_capture_reps); tProc dmem cannot hold more."
                      % (cfg["reps"], cap_reps))
            cfg["reps"] = cap_reps

        self.q_rp = self.ch_page(cfg["qubit_ch"])

        # Free user registers on the qubit page (mirrors ModifiedRamsey).
        self.r_read = 4    # holds the accumulated I read back from the ADC
        self.r_thresh = 5  # holds the single-shot discrimination threshold

        self.prep_excited = cfg.get("prep_excited", False)
        self.use_active_reset = cfg.get("use_active_reset", False)
        self.reset_cycles = int(cfg.get("reset_cycles", 1)) if self.use_active_reset else 0
        if self.reset_cycles < 0:
            raise ValueError("cfg['reset_cycles'] must be non-negative")
        self.reset_ro_ch = int(cfg["ro_chs"][0])
        reset_rocfg = self.soccfg["readouts"][self.reset_ro_ch]
        if "tproc_ch" not in reset_rocfg:
            raise KeyError(
                f"soccfg['readouts'][{self.reset_ro_ch}] has no 'tproc_ch'; "
                "hardware feedback cannot identify the tProc input port."
            )
        self.reset_read_port = int(reset_rocfg["tproc_ch"])
        if not 0 <= self.reset_read_port < 8:
            raise ValueError(
                f"readout {self.reset_ro_ch} maps to invalid tProc v1 input "
                f"port {self.reset_read_port}; expected 0..7."
            )
        self.reset_skip_op = "<" if cfg.get("reset_ground_below_threshold", True) else ">"
        # Diagnostic: fire the corrective pi UNCONDITIONALLY (skip the condj).
        # Measures the bare pi fidelity in the post-readout environment,
        # decoupled from the threshold decision.
        self.reset_force_pi = cfg.get("reset_force_pi", False)
        # Sign-safe comparison offset. ARV data on TATQ01/BFE (2026-06-05/06)
        # showed the corrective pi firing on every shot whose accumulated I is
        # NEGATIVE (ground-state damage tracked the below-zero fraction of the
        # g blob; the g_I~0 sweep lost exactly half its ground shots), i.e. the
        # deployed tProc compares r_read/r_thresh as if unsigned. Adding the
        # same large positive constant to BOTH operands makes them strictly
        # positive, so signed and unsigned comparison agree and the decision is
        # correct under either firmware behaviour. Sized 2^28 (was 2^24, which
        # assumed |raw I| ~1e4-1e5): the raw accumulator scales with the readout
        # window, so at 15 us raw_threshold can approach 2^24. Must match
        # ModifiedRamseyProgram.cmp_offset -- verify_ModifiedRamsey asserts it.
        self.cmp_offset = 1 << 28
        # Feedback-read settle. reset_read_settle is the MINIMUM real stall
        # required between the reset readout window closing and the `read`; the
        # measure's syncdelay already advances the tProc time reference by
        # reset_readout_relax_delay, and waiti's immediate is relative to that
        # reference, so only the shortfall has to be emitted. Emitting the
        # shortfall as a waiti (never as extra synci) is what keeps the scheduled
        # rep period -- and therefore runs.charge_parity.modified_ramsey_timing --
        # byte-identical for every cfg. See active_reset_to_g().
        self.reset_readout_syncdelay_cycles = self.us2cycles(
            cfg.get("reset_readout_relax_delay", 1.0))
        # FLOOR, not merely a default. reset_read_settle=0.0 passes the
        # non-negativity validation above, and combined with
        # reset_readout_relax_delay=0.0 it collapses the real margin to 0.8 tProc
        # cycles (1.9 ns) -- functionally the pre-fix bug, and low enough that
        # nothing downstream would notice. The stall is load-bearing, so it is
        # not configurable away: MIN_RESET_READ_SETTLE_US is ~3x the worst-case
        # avg_buf -> clock-converter -> tProc-input latency.
        self.reset_read_settle_cycles = max(
            self.us2cycles(cfg.get("reset_read_settle",
                                   MIN_RESET_READ_SETTLE_US)),
            self.us2cycles(MIN_RESET_READ_SETTLE_US),
        )
        self.reset_read_extra_wait_cycles = max(
            0,
            self.reset_read_settle_cycles - self.reset_readout_syncdelay_cycles
        )
        # D3: the shortfall is emitted as a waiti BEYOND the tProc time
        # reference, but the corrective pi's `set` targets reference+0, so the pi
        # fires this late and the real rep period exceeds the scheduled one by
        # the same amount. Zero for every shipped cfg (runners pass
        # reset_readout_relax_delay=5.0; charge_parity defaults it to 1.0), so
        # this only fires if someone shortens the ring-down wait below the floor.
        if (self.use_active_reset and self.reset_cycles
                and self.reset_read_extra_wait_cycles > 0):
            late_us = self.cycles2us(self.reset_read_extra_wait_cycles)
            print(
                "[ActiveResetVerify] WARNING: reset_readout_relax_delay "
                f"({cfg.get('reset_readout_relax_delay', 1.0)} us) is shorter "
                f"than the feedback-read settle floor "
                f"({MIN_RESET_READ_SETTLE_US} us). The corrective pi will fire "
                f"{late_us:.3f} us LATER than scheduled and the real rep period "
                f"will exceed the modelled one by the same amount. Raise "
                "reset_readout_relax_delay to >= the settle (and keep it >= "
                "~6/kappa so the pi still sees a photon-free resonator)."
            )
        self.n_verify_reads = int(cfg.get("n_verify_reads", 5))
        if self.n_verify_reads < 1:
            raise ValueError("cfg['n_verify_reads'] must be >= 1.")

        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])

        # Match ModifiedRamsey exactly: ADC windows use the readout clock,
        # resonator pulses use the generator fabric clock, and trigger/delay
        # values use the tProc clock.
        required_tone_us = cfg["adc_trig_offset"] + cfg["readout_length"]
        cfg.setdefault("length", required_tone_us)
        if cfg["length"] < required_tone_us:
            raise ValueError(
                "cfg['length'] must cover cfg['adc_trig_offset'] + "
                f"cfg['readout_length'] ({cfg['length']} us < "
                f"{required_tone_us} us)"
            )

        self.adc_trig_offset_cycles = self.us2cycles(cfg["adc_trig_offset"])
        requested_tone_cycles = self.us2cycles(
            cfg["length"], gen_ch=cfg["res_ch"]
        )
        self.readout_window_cycles = {
            ch: self.us2cycles(cfg["readout_length"], ro_ch=ch)
            for ch in cfg["ro_chs"]
        }

        f_time = self.soccfg["tprocs"][0]["f_time"]
        res_f_fabric = self.soccfg["gens"][cfg["res_ch"]]["f_fabric"]
        adc_end_tproc = max(
            self.adc_trig_offset_cycles
            + self.readout_window_cycles[ch]
            * f_time / self.soccfg["readouts"][ch]["f_output"]
            for ch in cfg["ro_chs"]
        )
        required_tone_cycles = int(np.ceil(
            adc_end_tproc * res_f_fabric / f_time - 1e-12
        ))
        self.readout_tone_cycles = max(
            requested_tone_cycles, required_tone_cycles
        )
        self.readout_tone_extension_cycles = (
            self.readout_tone_cycles - requested_tone_cycles
        )

        for ch in cfg["ro_chs"]:
            self.declare_readout(
                ch=ch,
                length=self.readout_window_cycles[ch],
                freq=cfg["pulse_freq"],
                gen_ch=cfg["res_ch"]
            )

        f_res = self.freq2reg(
            cfg["pulse_freq"],
            gen_ch=cfg["res_ch"],
            ro_ch=cfg["ro_chs"][0]
        )
        # Qubit pulses (prep pi, reset corrective pi) play at f_ge.
        self.f_ge_reg = self.freq2reg(cfg["f_ge"], gen_ch=cfg["qubit_ch"])

        self.pulse_sigma = self.us2cycles(cfg["sigma"], gen_ch=cfg["qubit_ch"])
        self.pulse_qubit_length = self.us2cycles(
            cfg["sigma"] * 4,
            gen_ch=cfg["qubit_ch"]
        )
        self.add_gauss(
            ch=cfg["qubit_ch"],
            name="qubit",
            sigma=self.pulse_sigma,
            length=self.pulse_qubit_length
        )

        self.set_pulse_registers(
            ch=cfg["res_ch"],
            style="const",
            freq=f_res,
            phase=cfg["res_phase"],
            gain=cfg["pulse_gain"],
            length=self.readout_tone_cycles
        )

        if self.use_active_reset or self.prep_excited:
            if "pi_gain" not in cfg:
                raise KeyError(
                    "prep_excited/use_active_reset require cfg['pi_gain'] for the "
                    "pi pulse."
                )
        if self.use_active_reset:
            if "readout_threshold" not in cfg:
                raise KeyError(
                    "use_active_reset=True requires cfg['readout_threshold'] "
                    "(single-shot I threshold, normalized units)."
                )
            # Rescale the normalized threshold back to the raw accumulator units the
            # tProc compares (collect_shots divides accumulated I by the window len).
            ro_norm = self.readout_window_cycles[cfg["ro_chs"][0]]
            raw_threshold = int(round(cfg["readout_threshold"] * ro_norm))
            if abs(raw_threshold) >= self.cmp_offset:
                raise ValueError(
                    f"raw_threshold {raw_threshold} exceeds the sign-safe "
                    f"comparison offset {self.cmp_offset}; increase cmp_offset."
                )
            # r_thresh holds threshold + offset; r_read gets the same offset
            # added (mathi) right after each read, before the condj.
            self.regwi(self.q_rp, self.r_thresh, raw_threshold + self.cmp_offset)
            # DIAGNOSTIC: shows the exact decision the reset will make. The corrective
            # pi is SKIPPED when (r_read reset_skip_op r_thresh) is true. For a correct
            # reset this must skip when the qubit is in |g>. Cross-check against the
            # measured g_I/e_I printed by calibrate_active_reset_readout.
            print(
                f"[ActiveResetVerify reset cfg] reset_ground_below_threshold="
                f"{cfg.get('reset_ground_below_threshold', True)}, skip_op='"
                f"{self.reset_skip_op}', readout_threshold(norm)="
                f"{cfg['readout_threshold']:.6f}, raw_threshold={raw_threshold}, "
                f"reset_cycles={self.reset_cycles}, force_pi={self.reset_force_pi} "
                f"(skip the pi when r_read+{self.cmp_offset} {self.reset_skip_op} "
                f"{raw_threshold + self.cmp_offset}; offset makes the compare "
                f"sign-safe)"
            )

        self.capture_words_per_rep = 0
        if self.reset_capture:
            self._init_reset_capture()

        self.sync_all(self.us2cycles(0.2))

    def _init_reset_capture(self):
        """Allocate the capture registers and size the dmem region."""
        cfg = self.cfg
        if not self.use_active_reset or self.reset_cycles < 1:
            raise ValueError(
                "reset_capture requires use_active_reset=True with "
                "reset_cycles >= 1: there is no condj operand to capture "
                "otherwise.")
        # Free user registers on the qubit page. Registers are allocated from the
        # END of each page (asm_v1._allocate_registers: regnum = 32 - nRegs), so
        # the low registers are the free ones; r_wait=3 (ModifiedRamsey), r_read=4
        # and r_thresh=5 are already taken here. 6/7 are also below every page-0
        # reservation (13-15 loop/shot counters, 16 trigger bits, 17-21
        # NDAverager), so they stay safe if the qubit channel ever lands on page 0.
        # Asserted rather than assumed, because a bitstream with more generators
        # repacks the pages.
        self.r_capaddr = 6   # dmem write address, incremented per word
        self.r_captag = 7    # monotone capture counter (addressing self-check)
        pulse_regs = {v for v in self._gen_regmap.values()}
        pulse_regs |= {v for v in self._ro_regmap.values()}
        for reg in (self.r_capaddr, self.r_captag):
            if (self.q_rp, reg) in pulse_regs:
                raise ValueError(
                    f"reset_capture register p{self.q_rp} r{reg} is a generator/"
                    "readout pulse register on this firmware; pick another.")
            if reg in (0, self.r_read, self.r_thresh):
                raise ValueError(
                    f"reset_capture register {reg} collides with the zero "
                    "register / r_read / r_thresh.")

        self.capture_with_tags = bool(cfg.get("reset_capture_tags", True))
        self.capture_base = int(cfg.get("reset_capture_base_addr",
                                        RESET_CAPTURE_BASE_ADDR))
        self.capture_words_per_rep = ((2 if self.capture_with_tags else 1)
                                      * self.reset_cycles)
        dmem = int(self.tproccfg["dmem_size"])          # 4096 on the BFG board
        self.capture_max_reps = ((dmem - self.capture_base)
                                 // self.capture_words_per_rep)
        self.capture_n_words = int(cfg["reps"]) * self.capture_words_per_rep
        if self.capture_base + self.capture_n_words > dmem:
            raise ValueError(
                "reset_capture does not fit in the tProc data memory: "
                f"reps={cfg['reps']} x {self.capture_words_per_rep} words/rep + "
                f"base {self.capture_base} = "
                f"{self.capture_base + self.capture_n_words} words > dmem_size "
                f"{dmem}. Set cfg['reset_capture_reps'] <= {self.capture_max_reps} "
                "(or reset_capture_tags=False to halve the footprint). NOT "
                "truncating silently.")
        # Initialised ONCE, outside the rep loop: a regwi inside the loop would
        # reset the address every rep and overwrite the same word forever.
        self.regwi(self.q_rp, self.r_capaddr, self.capture_base)
        self.regwi(self.q_rp, self.r_captag, 0)
        print("[ARV reset-capture] ON  page=%d r_read=%d r_thresh=%d r_capaddr=%d "
              "r_captag=%d | dmem base=%d words/rep=%d reps=%d words=%d "
              "(dmem %d, max reps %d)"
              % (self.q_rp, self.r_read, self.r_thresh, self.r_capaddr,
                 self.r_captag, self.capture_base, self.capture_words_per_rep,
                 cfg["reps"], self.capture_n_words, dmem, self.capture_max_reps))

    def active_reset_to_g(self):
        """
        Real measurement-feedback reset to |g>. Copied verbatim (logic) from
        ModifiedRamseyProgram.active_reset_to_g() so this experiment validates the
        identical sequence.
        """
        cfg = self.cfg
        ro_ch = self.reset_ro_ch

        for i in range(self.reset_cycles):
            done_label = "VRESET_DONE_%d" % i

            self.measure(
                pulse_ch=cfg["res_ch"],
                adcs=self.ro_chs,
                adc_trig_offset=self.adc_trig_offset_cycles,
                wait=True,
                syncdelay=self.reset_readout_syncdelay_cycles
            )

            # STALL the tProc until the accumulated I is actually AT the tProc
            # input. DO NOT REMOVE THIS LINE.
            #
            # measure(wait=True) emits waiti(0, int(window_end)) and syncdelay
            # emits synci. Only waiti stalls the control core; synci merely
            # advances the tProc TIME REFERENCE ("This does not pause the tProc",
            # asm_v1.py sync_all). So without this stall the `read` below ran ~2
            # instructions (~5 ns) after the ADC window closed -- in fact 0.2
            # tProc cycles BEFORE it closed, because wait_all() truncates the
            # fractional readout-end timestamp with int(). And the tProc input
            # port is a bare last-value latch: s_axis_read.vhd is one register
            # loaded whenever s_axis_tvalid is high with s_axis_tready tied to
            # '1', and the `read` instruction samples it unconditionally without
            # ever inspecting tvalid. The accumulated word meanwhile has to cross
            # the avg buffer's async FIFO into the 100 MHz PS domain and an AXIS
            # clock converter into the 430 MHz tProc domain -- tens to ~150 ns.
            # A read that early therefore returns the PREVIOUS readout's I.
            #
            # What that cost, measured 2026-07-28 on TATQ01-SiO2 Q3 via this very
            # experiment (2000 reps/condition, 5 verification readouts):
            #     prep|g> reset OFF   P(|g>) = 0.872   thermal baseline
            #     prep|e> reset OFF   P(|g>) = 0.152   control
            #     prep|g> reset ON    P(|g>) = 0.539   <- should be ~0.78
            #     prep|e> reset ON    P(|g>) = 0.497   <- should be ~0.74
            #     prep|e> force_pi    P(|g>) = 0.847   pi + readout are FINE
            #     prep|g> force_pi    P(|g>) = 0.132
            # The corrective pi fired on ~50% of shots, uncorrelated with THIS
            # shot's state, while force_pi (same readout, same 5 us, same pi, no
            # condj) reproduced the baselines to 0.02. Forensics on the saved
            # per-shot h5: corr(read0 of rep n, read4 of rep n-1) = -0.723 for
            # prep|e> and +0.750 for prep|g> -- the sign flips because the pi
            # repairs |e> but damages |g> -- against |corr| <= 0.04 in all four
            # control conditions, and P(|g>) | previous read = |e>) = 0.847
            # reproduces the force-pi baseline to 0.0004. The decision variable
            # was the PREVIOUS rep's last readout: exactly one readout of lag.
            #
            # wait_all(t) emits waiti(0, t), which stalls until the tProc time
            # counter reaches reference + t. measure()'s sync_all has just set
            # reference = window_end + reset_readout_relax_delay and zeroed the
            # readout timestamps, so wait_all(0) alone already buys the whole
            # reset_readout_relax_delay (5.0 us on the deployed runner cfg,
            # against the 200 cycles = 0.47 us the canonical qick active-reset
            # demo waits). reset_read_extra_wait_cycles is therefore only the
            # shortfall against cfg["reset_read_settle"], so a shorter
            # reset_readout_relax_delay still gets a real settle and no synci is
            # ever added. verify_ModifiedRamsey.check_reset_read_settle measures
            # this margin offline and fails if it goes away.
            self.wait_all(self.reset_read_extra_wait_cycles)

            # `read` addresses a tProc INPUT PORT, not an ADC/readout index.
            # They happen to be equal on the current BFG bitstream, but using
            # soccfg's explicit mapping keeps feedback correct if a future
            # bitstream reorders the ports.
            self.read(self.reset_read_port, self.q_rp, "lower", self.r_read)

            # Offset the (possibly negative) accumulated I into strictly
            # positive territory so the comparison below is sign-safe (see
            # cmp_offset comment in initialize()). r_thresh already carries
            # the same offset.
            self.mathi(self.q_rp, self.r_read, self.r_read, "+", self.cmp_offset)

            if self.reset_capture:
                # Mirror the EXACT condj operand into tProc data memory, so the
                # decision variable stops being invisible. Placement is load
                # bearing: AFTER the read so it cannot perturb the read's timing
                # (i.e. cannot mask the bug it measures), AFTER the sign-safe
                # mathi so the captured word is literally what condj compares,
                # and BEFORE the condj so every shot is captured including the
                # ones where the pi is skipped.
                #
                # memw(page, r_data, r_addr) -> mem[r_addr] = r_data. Verified
                # against the tProc v1 encoding table in the firmware source
                # (ctrl.sv: "memw p, $ra, $rb : $mem[$rb] = $ra" with rb at bits
                # 40..36 and ra at bits 35..31) and against the datapath
                # (tproc64x32_x8.v: reg_addr0 = ir[40:36] -> dmem_addr,
                # reg_addr1 = ir[35:31] -> dmem_di), both of which agree with
                # asm_v1's fmt ((0,53),(2,36),(1,31)). NOTE qick's own
                # parser.py disagrees (it packs the two registers at bits 41/36);
                # parser.py is the text-.asm front end, is not used by
                # QickProgram, and is wrong here.
                if self.capture_with_tags:
                    self.memw(self.q_rp, self.r_captag, self.r_capaddr)
                    self.mathi(self.q_rp, self.r_capaddr, self.r_capaddr, "+", 1)
                self.memw(self.q_rp, self.r_read, self.r_capaddr)
                self.mathi(self.q_rp, self.r_capaddr, self.r_capaddr, "+", 1)
                if self.capture_with_tags:
                    self.mathi(self.q_rp, self.r_captag, self.r_captag, "+", 1)

            if not self.reset_force_pi:
                self.condj(self.q_rp, self.r_read, self.reset_skip_op,
                           self.r_thresh, done_label)

            self.set_pulse_registers(
                ch=cfg["qubit_ch"],
                style="arb",
                freq=self.f_ge_reg,
                phase=0,
                gain=cfg["pi_gain"],
                waveform="qubit"
            )
            self.pulse(ch=cfg["qubit_ch"])

            self.label(done_label)
            self.sync_all()

        if self.reset_cycles:
            self.sync_all(self.us2cycles(cfg.get("post_reset_wait", 0.0)))

    def body(self):
        cfg = self.cfg

        # 1) Optionally prepare |e> with a pi pulse (stringent reset test).
        if self.prep_excited:
            self.set_pulse_registers(
                ch=cfg["qubit_ch"],
                style="arb",
                freq=self.f_ge_reg,
                phase=0,
                gain=cfg["pi_gain"],
                waveform="qubit"
            )
            self.pulse(ch=cfg["qubit_ch"])
            self.sync_all()

        # 2) Optionally active-reset to |g>.
        if self.use_active_reset:
            self.active_reset_to_g()

        # 3) N back-to-back verification readouts. Intermediate reads use the short
        #    verify_relax_delay; the final read uses the full relax_delay so the
        #    qubit re-thermalises before the next rep's prep stage.
        verify_delay = self.us2cycles(cfg.get("verify_relax_delay", 5.0))
        relax_delay = self.us2cycles(cfg["relax_delay"])
        for j in range(self.n_verify_reads):
            syncdelay = relax_delay if j == self.n_verify_reads - 1 else verify_delay
            self.measure(
                pulse_ch=cfg["res_ch"],
                adcs=self.ro_chs,
                adc_trig_offset=self.adc_trig_offset_cycles,
                wait=True,
                syncdelay=syncdelay
            )

    def acquire(self, soc, load_pulses=True, start_src="internal", progress=False):
        # reset readouts (if any) precede the N verification readouts each rep.
        self.reads_per_rep = self.reset_cycles + self.n_verify_reads
        if self.reset_capture:
            self._capture_prefill(soc)
        super().acquire(
            soc,
            readouts_per_experiment=self.reads_per_rep,
            load_pulses=load_pulses,
            start_src=start_src,
            progress=progress
        )
        if self.reset_capture:
            # NEVER let a diagnostic readback discard a good acquisition: the
            # shots are already in acc_buf at this point, and on a cooled-down
            # device they are expensive. Both dmem read paths can fail on the
            # client (pynq is not installed, so an mmio buffer can fail to
            # unpickle across Pyro).
            try:
                self.capture_result = self._capture_readback_and_analyze(soc)
            except Exception as e:
                self.capture_result = {"error": f"{type(e).__name__}: {e}"}
                print("[ARV reset-capture] readback/analysis FAILED (%s: %s); "
                      "the shot data is unaffected." % (type(e).__name__, e))
        return self.collect_shots()

    # ---- reset-capture plumbing -------------------------------------------

    def _capture_prefill(self, soc):
        """Sentinel-fill the dmem capture region so "never written" is visible.

        Nothing in the tProc v1 acquisition path overwrites dmem afterwards:
        load_bin_program writes program memory only, reload_mem is a v2-only
        no-op, prepare_round/cleanup_round are no-ops, and clear_tproc_counter
        writes only COUNTER_ADDR=1, which is below capture_base.
        """
        self.capture_prefilled = False
        if not self.cfg.get("reset_capture_prefill", True):
            return
        try:
            fill = np.full(self.capture_n_words,
                           np.uint32(RESET_CAPTURE_SENTINEL).astype(np.int32),
                           dtype=np.int32)
            soc.load_mem(fill, mem_sel="dmem", addr=self.capture_base)
            self.capture_prefilled = True
        except Exception as e:
            print("[ARV reset-capture] prefill unavailable (%s: %s); 'never "
                  "written' will not be distinguishable from 'wrong value'."
                  % (type(e).__name__, e))

    def _capture_read_dmem(self, soc):
        """Read the capture region back as a uint32 array.

        Fast path: soc.read_mem(n, mem_sel='dmem', addr=...) -> one Pyro round
        trip. It returns a pynq-allocated buffer (an ndarray SUBCLASS), and pynq
        is not installed on the client, so the unpickle can fail -- hence the
        fallback. Fallback: soc.get_tproc_counter(addr) per word, which is the
        only dmem read path qick itself already drives across Pyro.
        """
        n, base = self.capture_n_words, self.capture_base
        try:
            buf = soc.read_mem(n, mem_sel="dmem", addr=base)
            return np.asarray(buf).astype(np.uint32).ravel()[:n]
        except Exception as e:
            print("[ARV reset-capture] block dmem read failed (%s: %s); falling "
                  "back to %d single-word reads." % (type(e).__name__, e, n))
        return np.array([int(soc.get_tproc_counter(addr=base + i))
                         for i in range(n)], dtype=np.uint32)

    def _capture_readback_and_analyze(self, soc):
        cfg = self.cfg
        ro_ch = cfg["ro_chs"][0]
        words = self._capture_read_dmem(soc)
        acc_i = np.asarray(self.acc_buf[0])[..., 0].astype(np.int64)
        acc_i = acc_i.reshape(int(cfg["reps"]), self.reads_per_rep)
        raw_threshold = int(round(cfg["readout_threshold"]
                                  * self.readout_window_cycles[ro_ch]))
        res = analyze_reset_capture(
            words, acc_i,
            reads_per_rep=self.reads_per_rep,
            reset_cycles=self.reset_cycles,
            cmp_offset=self.cmp_offset,
            thresh_cmp=raw_threshold + self.cmp_offset,
            skip_op=self.reset_skip_op,
            with_tags=self.capture_with_tags,
            max_lag=int(cfg.get("reset_capture_max_lag", 3)),
        )
        res["prefilled"] = getattr(self, "capture_prefilled", False)
        res["raw_threshold"] = raw_threshold
        res["thresh_cmp"] = raw_threshold + self.cmp_offset
        # The read's first argument is a tProc INPUT PORT, not a readout index.
        # Record both so the mapping used for this run remains auditable.
        res["tproc_ch_expected"] = int(
            self.soccfg["readouts"][ro_ch].get("tproc_ch", -1))
        res["read_ch_used"] = self.reset_read_port
        self.capture_words = words
        return res

    def collect_shots(self):
        ro_ch = self.cfg["ro_chs"][0]
        norm = self.us2cycles(self.cfg["readout_length"], ro_ch=ro_ch)
        reps = self.cfg["reps"]
        reads_per_rep = self.reads_per_rep
        # Verification read k of each rep lives at di_buf[ch][reset_cycles+k :: reads_per_rep].
        verify_i = np.empty((self.n_verify_reads, reps))
        verify_q = np.empty((self.n_verify_reads, reps))
        di_buf, dq_buf = raw_shot_buffers(self)
        for k in range(self.n_verify_reads):
            idx = self.reset_cycles + k
            verify_i[k] = di_buf[0][idx::reads_per_rep][:reps] / norm
            verify_q[k] = dq_buf[0][idx::reads_per_rep][:reps] / norm
        return verify_i, verify_q


class ActiveResetVerify(ExperimentClass):
    """
    Drives ActiveResetVerifyProgram for one (prep_excited, use_active_reset)
    condition and classifies the per-read IQ against a calibrated g/e separator
    to produce P(|g>) vs readout index.

    Requires cfg["g_center"] and cfg["e_center"] (each [I, Q], normalized units,
    from a SingleShot calibration) for shot classification.
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='',
                 prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(
            soc=soc,
            soccfg=soccfg,
            path=path,
            outerFolder=outerFolder,
            prefix=prefix,
            cfg=cfg,
            config_file=config_file,
            progress=progress
        )

    def acquire(self, progress=False, debug=False):
        # Separator/threshold validation runs BEFORE the acquisition, not after:
        # every check below is on cfg alone, and raising after prog.acquire()
        # would throw away a completed shot record (2000 reps on a cooled-down
        # device) and abort the remaining conditions of the sweep.
        g_center, e_center, normal, midpoint = self._validate_separator()

        prog = ActiveResetVerifyProgram(self.soccfg, self.cfg)
        verify_i, verify_q = prog.acquire(
            self.soc,
            load_pulses=True,
            progress=progress
        )
        verify_i = np.asarray(verify_i)
        verify_q = np.asarray(verify_q)
        return self._finish_acquire(prog, verify_i, verify_q,
                                    g_center, e_center, normal, midpoint)

    def _validate_separator(self):
        """Check cfg's g/e separator + I-threshold. Returns the derived vectors.

        The hardware feedback thresholds the RAW in-phase value only, while the
        verification classifies in 2D, so a separator that is fine for the
        verification can still be meaningless for the reset decision. These are
        the failure modes that survive the feedback-read timing fix: a threshold
        outside the two blob centers, or a reset_ground_below_threshold sign that
        disagrees with them, degenerate the reset into always-fire or never-fire.
        """
        g_center = np.asarray(self.cfg["g_center"], dtype=float)
        e_center = np.asarray(self.cfg["e_center"], dtype=float)
        if g_center.shape != (2,) or e_center.shape != (2,):
            raise ValueError("cfg['g_center'] and cfg['e_center'] must each be [I, Q]")
        if not np.all(np.isfinite(g_center)) or not np.all(np.isfinite(e_center)):
            raise ValueError("cfg['g_center']/cfg['e_center'] contain non-finite values")
        normal = e_center - g_center
        if np.linalg.norm(normal) <= np.finfo(float).eps:
            raise ValueError(
                "cfg['g_center'] and cfg['e_center'] are indistinguishable; "
                "P(|g>) classification would be meaningless."
            )
        threshold = float(self.cfg["readout_threshold"])
        g_i, e_i = float(g_center[0]), float(e_center[0])
        if not min(g_i, e_i) < threshold < max(g_i, e_i):
            raise ValueError(
                f"readout_threshold={threshold:.6g} is not between calibrated "
                f"g_I={g_i:.6g} and e_I={e_i:.6g}; active-reset decisions "
                "cannot be interpreted."
            )
        calibrated_ground_below = g_i < e_i
        configured_ground_below = bool(
            self.cfg.get("reset_ground_below_threshold", True)
        )
        if configured_ground_below != calibrated_ground_below:
            raise ValueError(
                "reset_ground_below_threshold disagrees with the supplied "
                f"centers (g_I={g_i:.6g}, e_I={e_i:.6g})."
            )
        if abs(normal[1]) > 0.1 * abs(normal[0]):
            print(
                "[ActiveResetVerify] WARNING: the calibrated g/e axis retains "
                f"substantial Q separation (dI={normal[0]:.6g}, "
                f"dQ={normal[1]:.6g}). Verification classifies in 2D, but "
                "hardware feedback thresholds I only; re-check res_phase."
            )
        midpoint = 0.5 * (g_center + e_center)
        return g_center, e_center, normal, midpoint

    def _finish_acquire(self, prog, verify_i, verify_q,
                        g_center, e_center, normal, midpoint):
        """Classify the shots, print the verdict, assemble the data dict."""
        # Classify each read: score>0 is closer to |e>, so P(|g>) = fraction <= 0.
        n_reads, n_reps = verify_i.shape
        p_ground = np.empty(n_reads)
        for k in range(n_reads):
            iq = np.column_stack([verify_i[k], verify_q[k]])
            scores = (iq - midpoint) @ normal
            p_ground[k] = float(np.mean(scores <= 0))
        print(
            "[ActiveResetVerify] immediate post-reset read0 P(|g>)="
            f"{p_ground[0]:.3f}; mean across {n_reads} verification reads="
            f"{np.mean(p_ground):.3f}. Use read0 for reset fidelity; the mean "
            "also includes later measurement/relaxation dynamics."
        )

        capture = self._report_reset_capture(prog, verify_i, verify_q,
                                            midpoint, normal)

        data = {
            'config': self.cfg,
            'data': {
                **({} if capture is None else {
                    **capture["arrays"],
                    'capture_match_own': capture["H_position"].get(0, 0.0),
                    'capture_match_prev': capture["H_position"].get(-1, 0.0),
                    'capture_decision_agreement': capture["decision_agreement"],
                    'capture_frac_pi_fired': capture["frac_pi_fired"],
                    'capture_frac_pi_should_fire': capture["frac_pi_should_have_fired"],
                    'capture_n_distinct': capture["n_distinct_values"],
                    'capture_n_sentinel_left': capture["n_sentinel_left"],
                    'capture_tags_ok': int(bool(capture["tags_ok"])),
                }),
                'verify_i': verify_i,
                'verify_q': verify_q,
                'p_ground': p_ground,
                'p_ground_read0': p_ground[0],
                'p_ground_mean': np.mean(p_ground),
                'read_index': np.arange(n_reads),
                'g_center': g_center,
                'e_center': e_center,
                'prep_excited': self.cfg.get("prep_excited", False),
                'use_active_reset': self.cfg.get("use_active_reset", False),
                'reset_force_pi': self.cfg.get("reset_force_pi", False),
                'reset_cycles': (
                    int(self.cfg.get("reset_cycles", 1))
                    if self.cfg.get("use_active_reset", False) else 0
                ),
            }
        }
        self.data = data
        self.p_ground = p_ground
        return data

    def _report_reset_capture(self, prog, verify_i, verify_q, midpoint, normal):
        """Print/save the r_read capture verdict. No-op unless the flag is on."""
        capture = getattr(prog, "capture_result", None)
        if capture is None:
            return None
        if "error" in capture:
            # acquire() already reported it and kept the shot data; do not let
            # the re-analysis below raise the same failure a second time.
            print("[ARV reset-capture] no verdict: %s" % capture["error"])
            self.capture_result = capture
            return capture
        # Re-run the analysis with the per-rep classification of the FIRST
        # verification read, which closes the loop: P(|g>) | pi fired) must
        # reproduce the force-pi baseline if the decision really drove the pi.
        iq0 = np.column_stack([verify_i[0], verify_q[0]])
        is_ground = ((iq0 - midpoint) @ normal) <= 0
        capture = analyze_reset_capture(
            prog.capture_words,
            np.asarray(prog.acc_buf[0])[..., 0].astype(np.int64).reshape(
                int(self.cfg["reps"]), prog.reads_per_rep),
            reads_per_rep=prog.reads_per_rep,
            reset_cycles=prog.reset_cycles,
            cmp_offset=prog.cmp_offset,
            thresh_cmp=capture["thresh_cmp"],
            skip_op=prog.reset_skip_op,
            with_tags=prog.capture_with_tags,
            max_lag=int(self.cfg.get("reset_capture_max_lag", 3)),
            is_ground=is_ground)
        ro_ch = self.cfg["ro_chs"][0]
        header = ("prep=%s reset=%s force_pi=%s | read ch=%d (soccfg tproc_ch=%d) "
                  "| raw_threshold=%d skip_op='%s' | settle=%d+%d cycles"
                  % ("|e>" if self.cfg.get("prep_excited") else "|g>",
                     self.cfg.get("use_active_reset"),
                     self.cfg.get("reset_force_pi"), ro_ch,
                     int(self.soccfg["readouts"][ro_ch].get("tproc_ch", -1)),
                     int(round(self.cfg["readout_threshold"]
                               * prog.readout_window_cycles[ro_ch])),
                     prog.reset_skip_op, prog.reset_readout_syncdelay_cycles,
                     prog.reset_read_extra_wait_cycles))
        report = format_capture_report(capture, header=header)
        print(report)
        try:
            with open(self.iname[:-4] + "_resetcapture.txt", "w") as f:
                f.write(report + "\n")
        except Exception as e:
            print("[ARV reset-capture] sidecar write failed: %r" % (e,))
        self.capture_result = capture
        self.capture_report = report
        return capture

    def display(self, data=None, plotDisp=False, figNum=1, **kwargs):
        if data is None:
            data = self.data

        d = data['data']
        p_ground = np.asarray(d['p_ground'])
        read_index = np.asarray(d['read_index'])
        prep_excited = d.get('prep_excited', False)
        use_active_reset = d.get('use_active_reset', False)
        force_pi = d.get('reset_force_pi', False)

        while plt.fignum_exists(num=figNum):
            figNum += 1

        cond = (
            f"prep={'|e>' if prep_excited else '|g>'}, "
            f"reset={'FORCE-PI' if (use_active_reset and force_pi) else ('ON' if use_active_reset else 'OFF')}"
        )

        fig = plt.figure(figNum)
        plt.plot(read_index, p_ground, 'o-', linewidth=1.5)
        plt.xlabel("Verification readout index")
        plt.ylabel("P(|g>)")
        plt.ylim(-0.05, 1.05)
        plt.title(self.titlename + f"\n{cond}")
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig(self.iname[:-4] + '_Pg.png')

        if plotDisp:
            plt.show(block=False)
            plt.pause(0.1)
        else:
            fig.clf(True)
            plt.close(fig)

    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])
