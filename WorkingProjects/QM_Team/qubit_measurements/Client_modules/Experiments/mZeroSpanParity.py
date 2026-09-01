"""
Zero-span two-tone parity-switching acquisition (QICK / RFSoC).

Canonical reference:
    docs/superpowers/specs/2026-05-16-bfc-charge-parity-zero-span-design.md

This module contains the device-agnostic acquisition code:
    ZeroSpanParityProgStrobe       (Path A, v1) per-rep IQ via di_buf/dq_buf
    ZeroSpanParityProgDecimated    (Path B, v2) raw decimated ADC waveform
    ZeroSpanParity                 ExperimentClass dispatching on cfg["mode"]
    _validate_cfg                  fail-fast configuration validation (spec §5.3)

cfg keys consumed by ZeroSpanParity (see spec §5.2 for the full contract):

  === required (all modes) ===
  mode               "strobe" | "decimated"
  start_src          "internal" | "external"
  res_ch, qubit_ch, ro_chs, nqz, qubit_nqz, mixer_freq
  read_pulse_freq    MHz, parking freq for readout tone
  parity_drive_freq  MHz, parking freq for qubit tone (one parity peak)
  qubit_gain, pulse_gain, res_phase
  adc_trig_offset    us
  read_length        us

  === required if mode=="strobe" ===
  sample_period_us   us, sample cadence
  reps_per_chunk     int, samples per acquire() call (chunking via chunked_acquire)

  === required if mode=="decimated" ===
  capture_length_us  us, duration of const tone pulse (must cover the readout window)
  soft_avgs          int, software-averaged rounds (must be 1 unless
                     allow_soft_avgs=True; >1 destroys parity trajectories)
  === optional in mode=="decimated" ===
  n_captures         int, number of outer captures to stitch (default 1).
                     gap_indices marks the boundaries.
  allow_soft_avgs    bool, opt-in to soft_avgs > 1 (non-time-resolved).

  === optional (all modes) ===
  allow_reps_over_avg_maxlen
                     bool, opt-in to reps_per_chunk > avg_maxlen. The
                     accumulated buffer is a circular buffer streamed during the
                     run, so this is legal and reduces the number of chunk gaps
                     in the record; see rule 4 below.

Validation errors include the spec rule number, the offending value, and the
violated bound.

DECIMATED-MODE CAPACITY (Path B). The decimated buffer holds
soccfg['readouts'][ro_ch]['buf_maxlen'] samples at the readout output rate
f_output. On the BFG ZCU216 that is 1024 samples at 307.2 MHz, i.e. a maximum
capture of ~3.3 us. Path B is therefore not usable for parity telegraph work on
this firmware -- run mode="strobe" until a DDR4-streaming path exists.

For decimated mode the time axis t_us is computed from f_output, which IS the
true decimated sample rate: declare_readout's `length` is in decimated samples
(tProc v1), so the returned sample count is us2cycles(read_length, ro_ch)
== read_length * f_output. (An earlier revision of this module converted that
length with the tProc clock instead, which made the returned count 1.4x larger
than read_length * f_output and looked like an f_output mismatch. It was a unit
bug here, not a firmware quirk.) The metadata fields read_length_us,
capture_length_us, samples_per_capture and decimated_fs_source are still
persisted so a time axis can be rebuilt post-hoc if a firmware change ever does
break the relation.
"""

import numpy as np
from qick import AveragerProgram

from WorkingProjects.QM_Team.qubit_measurements.Client_modules.CoreLib.Experiment import (
    ExperimentClass,
)
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Helpers.shot_buffers import (
    raw_shot_buffers,
)


_STROBE_REQUIRED = (
    "sample_period_us", "reps_per_chunk",
)
_DECIMATED_REQUIRED = (
    "capture_length_us", "soft_avgs",
)
# n_captures is optional; defaults to 1. When >1, _acquire_decimated runs the
# acquire_decimated() call back-to-back and stitches results with gap_indices,
# mirroring chunked_acquire semantics for strobe mode.
_SHARED_REQUIRED = (
    "mode", "start_src", "res_ch", "qubit_ch", "ro_chs", "nqz", "qubit_nqz",
    "mixer_freq", "read_pulse_freq", "parity_drive_freq",
    "qubit_gain", "pulse_gain", "res_phase",
    "adc_trig_offset", "read_length",
)


def _validate_cfg(cfg, soccfg):
    """
    Fail-fast validation of a ZeroSpanParity cfg dict (spec §5.3 rules 1-5, 8, 9).

    Raises RuntimeError on the first violation found. Each error message names
    the rule number, the offending value, and the violated bound.
    """
    # Presence checks first — easier to debug than indexing errors below.
    missing = [k for k in _SHARED_REQUIRED if k not in cfg]
    if missing:
        raise RuntimeError(
            f"[ZeroSpanParity cfg] missing required keys: {missing}"
        )
    mode = cfg["mode"]
    if mode not in ("strobe", "decimated"):
        raise RuntimeError(
            f"[ZeroSpanParity cfg] cfg['mode']={mode!r} must be 'strobe' or 'decimated'"
        )
    extra = _STROBE_REQUIRED if mode == "strobe" else _DECIMATED_REQUIRED
    missing_extra = [k for k in extra if k not in cfg]
    if missing_extra:
        raise RuntimeError(
            f"[ZeroSpanParity cfg] missing keys for mode={mode!r}: {missing_extra}"
        )

    # Rule 1: sample_period floor
    if mode == "strobe":
        sp = float(cfg["sample_period_us"])
        floor = float(cfg["adc_trig_offset"]) + float(cfg["read_length"]) + 1.0
        if sp < floor:
            raise RuntimeError(
                f"[ZeroSpanParity §5.3 rule 1] sample_period_us={sp} us is below "
                f"floor (adc_trig_offset + read_length + 1.0 = {floor:.3f} us). "
                f"Increase sample_period_us or shorten read_length."
            )

    # Rules 2 & 3: const-pulse length must fit QICK's mode register. asm_v1's
    # AbsGenManager.get_mode_code raises for length >= 2**16 OR length < 3, so
    # both bounds are checked here (the minimum is unreachable given rules 1/9,
    # but a bad cfg should say which bound it broke, not fail inside QICK).
    # us2cycles depends on the channel; soccfg exposes us2cycles via soccfg.us2cycles.
    def _check_cycle_cap(length_key, rule_no):
        for label in ("qubit_ch", "res_ch"):
            cyc = soccfg.us2cycles(cfg[length_key], gen_ch=cfg[label])
            if cyc > 65535:
                raise RuntimeError(
                    f"[ZeroSpanParity §5.3 rule {rule_no}] {length_key} yields "
                    f"{cyc} cycles on {label} > 65535 cap. Reduce {length_key}."
                )
            if cyc < 3:
                raise RuntimeError(
                    f"[ZeroSpanParity §5.3 rule {rule_no}] {length_key}="
                    f"{cfg[length_key]} us yields {cyc} cycles on {label}, below "
                    f"the 3-cycle minimum const-pulse length. Increase "
                    f"{length_key}."
                )
    if mode == "strobe":
        _check_cycle_cap("sample_period_us", 2)
    else:
        _check_cycle_cap("capture_length_us", 3)

    # Rules 4 & 5: avg_maxlen / buf_maxlen
    ro_ch = cfg["ro_chs"][0]
    try:
        ro_info = soccfg["readouts"][ro_ch]
    except (KeyError, IndexError, TypeError) as ex:
        raise RuntimeError(
            f"[ZeroSpanParity cfg] cannot read soccfg['readouts'][{ro_ch}]: {ex!r}"
        )
    if mode == "strobe":
        # Rule 4 (relaxed). The accumulated buffer is NOT a hard cap: qick
        # streams it during the run and wraps modulo avg_maxlen
        # (qick/streamer.py, `addr = last_shots * reads_per_count % avg_maxlen`),
        # and there is no reps <= avg_maxlen assertion anywhere in qick. The only
        # real limits are the host keeping up (streamer raises only if Python
        # falls >= avg_maxlen shots behind) and RAM (acc_buf is 16 B/rep).
        #
        # Exceeding avg_maxlen is therefore *desirable*: every chunk boundary is
        # a real time gap in the parity record, so fewer, longer chunks give a
        # cleaner trace. It stays opt-in because falling behind raises mid-run,
        # so verify it in the loopback check before relying on it.
        avg_maxlen = int(ro_info["avg_maxlen"])
        reps = int(cfg["reps_per_chunk"])
        if reps > avg_maxlen and not cfg.get("allow_reps_over_avg_maxlen", False):
            raise RuntimeError(
                f"[ZeroSpanParity §5.3 rule 4] reps_per_chunk={reps} > "
                f"avg_maxlen={avg_maxlen} for readout ch {ro_ch}. This is "
                f"legal (qick streams the accumulated buffer and wraps modulo "
                f"avg_maxlen) but raises mid-run if the host cannot keep up. "
                f"Either reduce reps_per_chunk and raise n_chunks, or set "
                f"cfg['allow_reps_over_avg_maxlen']=True to take one long "
                f"gapless chunk."
            )
    else:
        # The decimated buffer is sized by the declared readout length
        # (declare_readout(length=us2cycles(read_length, ro_ch=ch))), NOT by the
        # const pulse length (capture_length_us). Check read_length against the
        # buffer cap.
        #
        # This bound is now EXACT rather than an estimate: _setup_two_tones
        # declares the readout with us2cycles(read_length, ro_ch=ch), which IS
        # the decimated sample count qick allocates, so compute it the same way
        # instead of via read_length * f_output.
        #
        # The comparison is >= because qick's readout.transfer_buf raises on
        # `length >= buf_maxlen`. (acquire_decimated's own pre-check uses >, so a
        # length of exactly buf_maxlen passes there and still fails in the
        # transfer.)
        buf_maxlen = int(ro_info["buf_maxlen"])
        decimated_fs_MHz = float(ro_info["f_output"])
        n_samples = int(soccfg.us2cycles(cfg["read_length"], ro_ch=ro_ch))
        if n_samples >= buf_maxlen:
            raise RuntimeError(
                f"[ZeroSpanParity §5.3 rule 5] read_length={cfg['read_length']} "
                f"us => {n_samples} decimated samples >= buf_maxlen={buf_maxlen} "
                f"for readout ch {ro_ch} at {decimated_fs_MHz} MHz. Reduce "
                f"read_length below {(buf_maxlen - 1) / decimated_fs_MHz:.3f} us. "
                f"NOTE: that caps decimated mode at a very short capture on this "
                f"firmware -- use mode='strobe' for parity telegraph work."
            )
        # Sanity check: pulse must cover the readout window. The readout fires
        # at adc_trig_offset and lasts read_length, so capture_length_us must
        # be >= adc_trig_offset + read_length.
        cap_us = float(cfg["capture_length_us"])
        floor = float(cfg["adc_trig_offset"]) + float(cfg["read_length"])
        if cap_us < floor:
            raise RuntimeError(
                f"[ZeroSpanParity §5.3 rule 9] capture_length_us={cap_us} us "
                f"< adc_trig_offset + read_length = {floor:.3f} us. "
                f"Pulse ends before readout window closes. Increase "
                f"capture_length_us or shorten read_length."
            )

    # Rule 8: parity_drive_freq within the qubit DDS range. QICK's valid DDS
    # band is [-f_dds/2, +f_dds/2] (see qick_asm.py freq2reg / the
    # "outside of [-range/2, range/2]" check), NOT [0, f_dds]. The qubit
    # channel is declared without a mixer (declare_gen, no mixer_freq), so no
    # mixer_freq subtraction is needed here. Use try/except instead of
    # `in soccfg` because QickConfig.__getitem__ exists but __contains__ does
    # not, which makes `"gens" in soccfg` crash on KeyError.
    qch = cfg["qubit_ch"]
    try:
        gen_info = soccfg["gens"][qch]
    except (KeyError, IndexError, TypeError):
        gen_info = None
    if gen_info is not None:
        try:
            f_dds = float(gen_info["f_dds"])
        except (KeyError, TypeError):
            f_dds = None
        if f_dds is not None:
            half = f_dds / 2.0
            f_drive = float(cfg["parity_drive_freq"])
            if not (-half <= f_drive <= half):
                raise RuntimeError(
                    f"[ZeroSpanParity §5.3 rule 8] parity_drive_freq={f_drive} MHz "
                    f"outside qubit channel {qch} DDS range [-{half}, {half}] MHz."
                )

    # Rules 6 & 7 are caller-level constraints (Recalibrate flags vs cached values).
    # The orchestrator enforces them before constructing cfg, so they are not
    # re-checked here.


class _ZeroSpanParityProgBase(AveragerProgram):
    """
    Shared two-tone setup and gate sequence for both parity acquisition paths.

    Both programs declare the same two generators (readout + qubit) and single
    readout, park a const readout tone and a const qubit "parity drive" tone,
    and run the same body() (pulse the drive, then measure). The ONLY difference
    is the const-pulse length: the strobe path holds each tone for one
    sample_period; the decimated path holds them for the full capture window.
    Subclasses supply that length via _const_length_us().

    Required cfg keys: see module docstring.
    """

    def _const_length_us(self):
        """Return the const-pulse duration (us) for this acquisition path."""
        raise NotImplementedError

    def _setup_two_tones(self):
        cfg = self.cfg
        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"],
                          mixer_freq=cfg["mixer_freq"], ro_ch=cfg["ro_chs"][0])
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])
        for ch in cfg["ro_chs"]:
            # `length` is in DECIMATED READOUT SAMPLES for tProc-v1 programs
            # (qick_asm.py declare_readout: USER_DURATIONS is False here, so the
            # value is taken verbatim as a sample count and interpreted against
            # the readout's f_output). us2cycles WITHOUT ro_ch uses the tProc
            # clock instead -- on the BFG board that is 430.08 vs 307.2 MHz, so
            # omitting ro_ch declares a window 1.4x longer than read_length. That
            # skews the accumulated I/Q scale away from the single-shot
            # separator, pushes the sync_all() reference past sample_period (so
            # t_us no longer matches the real rep period), and leaves the tail of
            # the integration window undriven. Every sibling program here
            # (mSingleShotProgramFFMUX, mModifiedRamsey, mUndrivenSingleShot,
            # mActiveResetVerify) passes ro_ch; so must this one.
            self.declare_readout(
                ch=ch,
                length=self.us2cycles(cfg["read_length"], ro_ch=ch),
                freq=cfg["read_pulse_freq"],
                gen_ch=cfg["res_ch"],
            )
        f_res = self.freq2reg(cfg["read_pulse_freq"], gen_ch=cfg["res_ch"],
                              ro_ch=cfg["ro_chs"][0])
        f_qub = self.freq2reg(cfg["parity_drive_freq"], gen_ch=cfg["qubit_ch"])
        return f_res, f_qub

    def initialize(self):
        cfg = self.cfg
        f_res, f_qub = self._setup_two_tones()
        length_us = self._const_length_us()
        length_cyc_q = self.us2cycles(length_us, gen_ch=cfg["qubit_ch"])
        length_cyc_r = self.us2cycles(length_us, gen_ch=cfg["res_ch"])

        self.set_pulse_registers(ch=cfg["qubit_ch"], style="const", freq=f_qub,
                                  phase=0, gain=cfg["qubit_gain"],
                                  length=length_cyc_q)
        self.set_pulse_registers(ch=cfg["res_ch"], style="const", freq=f_res,
                                  phase=cfg["res_phase"], gain=cfg["pulse_gain"],
                                  length=length_cyc_r)
        self.synci(200)

    def body(self):
        self.pulse(ch=self.cfg["qubit_ch"], t=0)
        self.measure(
            pulse_ch=self.cfg["res_ch"],
            adcs=self.cfg["ro_chs"],
            adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
            wait=True,
            syncdelay=0,
        )


class ZeroSpanParityProgStrobe(_ZeroSpanParityProgBase):
    """
    Path A: stroboscopic per-rep IQ acquisition for zero-span parity measurement.

    Both tones are held on for the full duration of each rep; reps run back-to-
    back with syncdelay=0 so the qubit drive is effectively CW from the qubit's
    perspective (apart from a small inter-rep tProc-overhead gap).

    Each rep contributes one integrated IQ point to prog.di_buf[ro_ch] /
    prog.dq_buf[ro_ch]. The ExperimentClass wrapper reshapes those into a time-
    resolved 1-D IQ trace with sample period = cfg["sample_period_us"].

    Required cfg keys: see module docstring.
    """

    def _const_length_us(self):
        return self.cfg["sample_period_us"]


class ZeroSpanParityProgDecimated(_ZeroSpanParityProgBase):
    """
    Path B: decimated raw-ADC waveform acquisition for zero-span parity.

    Both tones held on for the full capture window; ADC streams decimated samples
    for the entire window. ExperimentClass wrapper calls prog.acquire_decimated()
    instead of prog.acquire() to extract the (length, 2) IQ array.

    Sample period = 1 / soccfg['readouts'][ro_ch]['f_output'] (us). The returned
    trace length per capture is set by the DECLARED readout window
    (declare_readout(length=us2cycles(read_length, ro_ch=ch))) — i.e.
    read_length_us * f_output_MHz samples, capped by buf_maxlen — NOT by
    capture_length_us. capture_length_us only sets the const-pulse duration,
    which must cover the readout window (spec §5.3 rule 9).

    CAPACITY WARNING: buf_maxlen is only 1024 samples on the BFG ZCU216, i.e.
    ~3.3 us per capture at f_output = 307.2 MHz. Path B cannot record a parity
    telegraph on this firmware; use ZeroSpanParityProgStrobe.
    """

    def _const_length_us(self):
        return self.cfg["capture_length_us"]


class ZeroSpanParity(ExperimentClass):
    """
    Dispatcher ExperimentClass for the zero-span parity measurement.

    cfg["mode"] selects between strobe (Path A) and decimated (Path B). See
    module docstring + spec §5 for the full configuration contract.

    Saves data via the standard ExperimentClass HDF5 + JSON pattern:
      .h5  : datasets I, Q, t_us, gap_indices; attrs sample_period_us, mode, etc.
      .json: cfg dict (via save_config)
      .png : optional, written by display() if called
    """

    def __init__(self, soc=None, soccfg=None, path="", outerFolder="",
                 prefix="data", cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder,
                         prefix=prefix, cfg=cfg, config_file=config_file,
                         progress=progress)
        _validate_cfg(self.cfg, self.soccfg)
        mode = self.cfg["mode"]
        # AveragerProgram.__init__ reads cfg["reps"] during make_program() —
        # we must set it BEFORE constructing the program. For strobe mode,
        # reps_per_chunk drives the loop; for decimated mode, reps=1 and the
        # whole capture is one shot (averaged in software via soft_avgs).
        if mode == "strobe":
            self.cfg["reps"] = int(self.cfg["reps_per_chunk"])
            # AveragerProgram.__init__ sets self.rounds from cfg["soft_avgs"], or
            # cfg["rounds"] if present. acc_buf is re-zeroed at the start of every
            # round, so with rounds > 1 the per-rep stream we read back would be
            # the LAST round only — silently discarding (rounds-1)/rounds of the
            # record at rounds x the runtime. A strobe trace is inherently
            # single-round; pin both keys rather than trusting the caller's cfg.
            self.cfg["soft_avgs"] = 1
            self.cfg["rounds"] = 1
            self.prog = ZeroSpanParityProgStrobe(self.soccfg, self.cfg)
        elif mode == "decimated":
            self.cfg["reps"] = 1
            self.prog = ZeroSpanParityProgDecimated(self.soccfg, self.cfg)
        else:
            # _validate_cfg already raised, but keep defensive check.
            raise ValueError(f"Unknown mode: {mode!r}")

    def set_qubit_gain(self, gain):
        """Update qubit drive gain and rebuild the strobe program in place.

        Used by modulated_strobe_acquire to square-wave the drive across blocks.
        Strobe mode only.
        """
        if self.cfg.get("mode", "strobe") != "strobe":
            raise RuntimeError("set_qubit_gain is strobe-mode only")
        self.cfg["qubit_gain"] = gain
        # Re-sync the effective reps from reps_per_chunk before rebuilding.
        # AveragerProgram bakes cfg["reps"] at construction, and only __init__
        # translated reps_per_chunk->reps. A caller (e.g. validate's
        # run_static_contrast) may bump reps_per_chunk after construction; without
        # this re-sync that change is silently ignored and the sidecar's logged
        # reps disagree with the reps actually run.
        if "reps_per_chunk" in self.cfg:
            self.cfg["reps"] = int(self.cfg["reps_per_chunk"])
        self.prog = ZeroSpanParityProgStrobe(self.soccfg, self.cfg)

    def acquire(self, progress=False, **kwargs):
        mode = self.cfg["mode"]
        if mode == "strobe":
            return self._acquire_strobe(progress=progress)
        if mode == "decimated":
            return self._acquire_decimated(progress=progress)
        raise ValueError(f"Unknown mode: {mode!r}")

    def _acquire_strobe(self, progress=False):
        import datetime
        cfg = self.cfg
        wall_clock_start = datetime.datetime.now().isoformat()
        # cfg["reps"] was already set to reps_per_chunk in __init__ before
        # AveragerProgram.make_program() ran. No further mutation needed here.
        prog = self.prog
        # AveragerProgram.acquire returns (avg_di, avg_dq) along with filling
        # prog.di_buf/prog.dq_buf with the raw per-rep stream.
        prog.acquire(
            self.soc,
            load_pulses=True,
            start_src=cfg["start_src"],
            progress=progress,
            readouts_per_experiment=1,
            save_experiments=None,
        )
        ro_ch = cfg["ro_chs"][0]
        # Normalize the accumulated I/Q by the number of decimated samples the
        # readout actually integrated, so the trace is in the same per-sample
        # units as the g/e centroids from mSingleShotProgramFFMUX.collect_shots.
        # That method divides by us2cycles(readout_length, ro_ch=cfg["ro_chs"][i])
        # — keyed off the ABSOLUTE channel from ro_chs, not hard-coded to 0 — so
        # key off ro_chs[0] here to match it on a MUX setup where ro_chs[0] != 0.
        #
        # Read the divisor from the program itself (prog.ro_chs[ro_ch]["length"],
        # set by declare_readout) rather than recomputing it. Recomputing is how
        # the two drifted apart before: the declaration used the tProc clock while
        # the divisor used the readout clock, leaving the trace 1.4x off the
        # separator's scale. Taking the authoritative value makes that class of
        # mismatch impossible.
        try:
            ro_cycles = float(prog.ro_chs[ro_ch]["length"])
        except (AttributeError, KeyError, TypeError):
            ro_cycles = float(self.soccfg.us2cycles(cfg["read_length"], ro_ch=ro_ch))
        if ro_cycles <= 0:
            ro_cycles = 1.0
        # di_buf/dq_buf are indexed by readout DECLARATION ORDER, not absolute
        # channel number (QICK builds one entry per declared ro_ch). Use
        # positional index 0 for the single declared readout. ro_ch above is
        # kept for the soccfg.us2cycles(..., ro_ch=ro_ch) call and any
        # soccfg["readouts"][ro_ch] lookups, which ARE keyed by absolute channel.
        prog_di_buf, prog_dq_buf = raw_shot_buffers(prog)
        I = np.asarray(prog_di_buf[0], dtype=float).ravel() / ro_cycles
        Q = np.asarray(prog_dq_buf[0], dtype=float).ravel() / ro_cycles
        sp = float(cfg["sample_period_us"])
        t_us = np.arange(I.size, dtype=float) * sp
        data = {
            "I": I, "Q": Q, "t_us": t_us,
            "gap_indices": np.array([], dtype=int),
            "wall_clock_start": wall_clock_start,
            "sample_period_us": sp,
            "read_length_us": float(cfg["read_length"]),
            "adc_trig_offset_us": float(cfg["adc_trig_offset"]),
            "ro_norm_cycles": ro_cycles,
            "mode": "strobe",
        }
        self.data = {"data": data}
        return data

    def _acquire_decimated(self, progress=False):
        import datetime
        cfg = self.cfg
        wall_clock_start = datetime.datetime.now().isoformat()
        prog = self.prog
        ro_ch = cfg["ro_chs"][0]
        # TODO(hardware): the loopback smoke test on this firmware empirically
        # observed that soccfg['readouts'][ro_ch]['f_output'] is NOT the true
        # rate of samples returned by acquire_decimated. Until that mismatch is
        # resolved, sample_period_us below is the *nominal* rate from soccfg
        # and t_us cannot be trusted as an absolute physical time axis. We
        # persist read_length_us and the raw returned-sample count so the time
        # axis can be reconstructed once the true rate is known.
        decimated_fs_MHz = float(self.soccfg["readouts"][ro_ch]["f_output"])
        sp = 1.0 / decimated_fs_MHz  # us per decimated sample (nominal); invariant

        n_captures = int(cfg.get("n_captures", 1))
        if n_captures < 1:
            raise RuntimeError(
                f"[ZeroSpanParity] n_captures={n_captures} must be >= 1"
            )
        soft_avgs = int(cfg.get("soft_avgs", 1))
        if soft_avgs > 1:
            # soft_avgs > 1 averages independent captures together — it
            # destroys per-shot parity trajectories. Allowed only when the
            # caller has explicitly opted in via an averaged-mode flag.
            if not cfg.get("allow_soft_avgs", False):
                raise RuntimeError(
                    f"[ZeroSpanParity] soft_avgs={soft_avgs} > 1 averages "
                    f"across independent captures and destroys parity "
                    f"trajectories. Set cfg['allow_soft_avgs']=True if you "
                    f"really want a non-time-resolved averaged trace."
                )

        I_parts, Q_parts, t_parts = [], [], []
        capture_sizes = []
        chunk_wall_clocks = []
        gap_indices = []
        cum_offset_us = 0.0
        cum_idx = 0
        for ci in range(n_captures):
            chunk_wall_clocks.append(datetime.datetime.now().isoformat())
            # soft_avgs is handled by AveragerProgram.__init__ from cfg["soft_avgs"];
            # passing it again here would collide with the kwarg that
            # AveragerProgram.acquire_decimated injects internally.
            dec = prog.acquire_decimated(
                self.soc,
                load_pulses=(ci == 0),
                start_src=cfg["start_src"],
                progress=progress,
            )
            # AveragerProgram.acquire_decimated returns a list with one ndarray
            # per ro_ch, with the I/Q axis as the SECOND-TO-LAST axis (it applies
            # np.moveaxis(buf, -1, -2)):
            #   (2, length)       — reps=1: (I/Q, sample)   [our case; reps pinned to 1]
            #   (reps, 2, length) — reps>1: (rep, I/Q, sample)
            # Some other firmware/paths return I/Q on the trailing axis
            #   (length, 2)       — handled below for robustness.
            arr = np.asarray(dec[0])
            if arr.ndim == 2 and arr.shape[0] == 2:
                I_c = arr[0]; Q_c = arr[1]
            elif arr.ndim == 2 and arr.shape[1] == 2:
                I_c = arr[:, 0]; Q_c = arr[:, 1]
            elif arr.ndim == 3:
                # (reps, 2, length): I/Q is axis -2, NOT the trailing axis, so
                # reshape(-1, 2) would interleave samples. Split on axis -2.
                I_c = arr[:, 0, :].ravel()
                Q_c = arr[:, 1, :].ravel()
            else:
                raise RuntimeError(f"unexpected acquire_decimated shape: {arr.shape}")
            t_c = np.arange(I_c.size, dtype=float) * sp
            if ci > 0:
                cum_offset_us = float(t_parts[-1][-1]) + sp
                gap_indices.append(cum_idx)
            t_shifted = t_c + cum_offset_us
            I_parts.append(I_c); Q_parts.append(Q_c); t_parts.append(t_shifted)
            capture_sizes.append(int(I_c.size))
            cum_idx += I_c.size

        I = np.concatenate(I_parts)
        Q = np.concatenate(Q_parts)
        t_us = np.concatenate(t_parts)
        data = {
            "I": I, "Q": Q, "t_us": t_us,
            "gap_indices": np.asarray(gap_indices, dtype=int),
            "wall_clock_start": wall_clock_start,
            "chunk_wall_clock_starts": chunk_wall_clocks,
            "n_captures": int(n_captures),
            "sample_period_us": sp,
            "decimated_fs_MHz": decimated_fs_MHz,
            "decimated_fs_source": "soccfg.f_output_unverified",
            "read_length_us": float(cfg["read_length"]),
            "capture_length_us": float(cfg["capture_length_us"]),
            "adc_trig_offset_us": float(cfg["adc_trig_offset"]),
            # Actual returned sample count per capture (spec §7.3) — the real
            # first-capture length, not total/n_captures, so an O(1) firmware
            # disagreement or a short final capture can't turn this into a
            # rounded average that matches no actual capture.
            "samples_per_capture": int(capture_sizes[0]) if capture_sizes else 0,
            "capture_sizes": np.asarray(capture_sizes, dtype=int),
            "soft_avgs": soft_avgs,
            "mode": "decimated",
        }
        self.data = {"data": data}
        return data

    def save_data(self, data=None):
        """Write IQ trace + metadata to self.fname (.h5)."""
        import h5py
        if data is None:
            data = self.data["data"] if isinstance(self.data, dict) and "data" in self.data else self.data
        # Append mode ("a", not "w") so a config attr written by the base
        # ExperimentClass.save_config into the same .h5 is not truncated,
        # regardless of save_data/save_config call order. Delete-then-recreate
        # each dataset so re-saving the same file is idempotent.
        with h5py.File(self.fname, "a") as f:
            def _put(name, arr):
                if name in f:
                    del f[name]
                f.create_dataset(name, data=arr)
            _put("I", np.asarray(data["I"]))
            _put("Q", np.asarray(data["Q"]))
            _put("t_us", np.asarray(data["t_us"]))
            _put("gap_indices", np.asarray(data.get("gap_indices", []), dtype=int))
            # Per-capture sample counts (decimated mode) — preserves the actual
            # length of every capture for post-hoc time-axis reconstruction even
            # if captures ever return unequal counts (spec §7.3/§7.5).
            if "capture_sizes" in data:
                _put("capture_sizes", np.asarray(data["capture_sizes"], dtype=int))
            # Per-chunk wall-clock starts (when chunked_acquire was used, or
            # when n_captures > 1 in decimated mode) — needed to reconstruct
            # actual inter-chunk gaps post-hoc.
            if "chunk_wall_clock_starts" in data:
                wcs = [str(s) if s is not None else "" for s in
                       data["chunk_wall_clock_starts"]]
                _put("chunk_wall_clock_starts",
                     np.asarray(wcs, dtype=h5py.string_dtype("utf-8")))
            # Scalar metadata. Keep this list in sync with whatever the
            # acquire-path dicts return; missing keys are silently skipped.
            scalar_keys = (
                "wall_clock_start", "sample_period_us", "mode",
                "decimated_fs_MHz", "decimated_fs_source",
                "read_length_us", "capture_length_us", "adc_trig_offset_us",
                "ro_norm_cycles", "samples_per_capture",
                "n_chunks", "n_captures", "soft_avgs",
            )
            for k in scalar_keys:
                if k in data:
                    try:
                        f.attrs[k] = data[k]
                    except TypeError:
                        f.attrs[k] = str(data[k])

    def save_config(self):
        """Write the cfg JSON only, without reopening the .h5.

        The base ExperimentClass.save_config also does
        ``self.datafile().attrs['config'] = ...``, which opens self.fname in 'a'
        mode and drops the handle without closing it. That survives today only on
        CPython refcounting, and the caller sequence here is
        save_data() -> save_config() -> analyze_parity_run() opening the same file
        'r', so a lingering write handle would be an HDF5 lock error. Everything
        that attr would carry is already in the .h5 attrs written by save_data
        plus the .json written here, so skip the reopen entirely.
        """
        import json
        from WorkingProjects.QM_Team.qubit_measurements.Client_modules.CoreLib.Experiment import (
            NpEncoder,
        )
        with open(self.cname, "w") as fid:
            json.dump(self.cfg, fid, cls=NpEncoder)

    def display(self, data=None, plotDisp=False, **kwargs):
        """No-op for live display; analysis module generates plots from the .h5."""
        return None


if __name__ == "__main__":
    # Synthetic soccfg-like object for unit testing _validate_cfg without QICK
    # hardware. The clocks deliberately MATCH the real BFG ZCU216 board and, more
    # importantly, DIFFER between domains: tProc/gen fabric 430.08 MHz vs readout
    # output 307.2 MHz. An earlier version of this stub returned us*384.0 for
    # every channel, collapsing the two domains into one number — which is
    # exactly why its "normalization matches single-shot units" guard could not
    # detect that _setup_two_tones was declaring the readout window on the tProc
    # clock. Keep these two rates distinct or that class of bug goes unseen again.
    _F_TIME = 430.08     # tProc + generator fabric clock (MHz)
    _F_OUTPUT = 307.2    # readout decimated output clock (MHz)

    class _FakeSocCfg:
        def __init__(self):
            self._d = {
                "readouts": {0: {"avg_maxlen": 16384, "buf_maxlen": 8192,
                                 "f_output": _F_OUTPUT}},
                "gens": {0: {"f_dds": 6144.0}, 1: {"f_dds": 6144.0}},
            }
        def us2cycles(self, us, gen_ch=None, ro_ch=None):
            # ro_ch -> readout output clock; gen_ch or neither -> tProc clock.
            # (QICK's real us2cycles picks the generator's f_fabric for gen_ch,
            # which equals f_time on this board, and f_time when given neither.)
            fclk = _F_OUTPUT if ro_ch is not None else _F_TIME
            return int(round(us * fclk))
        def __getitem__(self, k): return self._d[k]
        def __contains__(self, k): return k in self._d

    sc = _FakeSocCfg()
    base = {
        "mode": "strobe", "start_src": "internal",
        "res_ch": 0, "qubit_ch": 1, "ro_chs": [0],
        "nqz": 2, "qubit_nqz": 2, "mixer_freq": 0.0,
        "read_pulse_freq": 7000.0, "parity_drive_freq": 3050.0,
        "qubit_gain": 5000, "pulse_gain": 1000, "res_phase": 0,
        "adc_trig_offset": 0.5, "read_length": 5.0,
        "sample_period_us": 20.0, "reps_per_chunk": 1000,
    }

    # Valid cfg passes.
    _validate_cfg(base, sc)
    print("_validate_cfg valid strobe: OK")

    # Rule 1: sample_period too small
    bad = dict(base); bad["sample_period_us"] = 1.0
    try: _validate_cfg(bad, sc)
    except RuntimeError as ex: assert "rule 1" in str(ex), ex
    else: raise AssertionError("expected rule 1 to fire")

    # Rule 2: sample_period too long => cycles > 65535
    bad = dict(base); bad["sample_period_us"] = 500.0
    try: _validate_cfg(bad, sc)
    except RuntimeError as ex: assert "rule 2" in str(ex), ex
    else: raise AssertionError("expected rule 2 to fire")

    # Rule 3: const pulse under QICK's 3-cycle minimum. In strobe mode rule 1's
    # 1.0 us floor always dominates, so the minimum is only reachable through the
    # decimated path (where capture_length_us has no such floor -- rule 9 only
    # requires it to cover adc_trig_offset + read_length).
    bad = dict(base)
    bad.update({"mode": "decimated", "soft_avgs": 1,
                "capture_length_us": 0.005, "adc_trig_offset": 0.0,
                "read_length": 0.0})
    del bad["sample_period_us"]; del bad["reps_per_chunk"]
    try: _validate_cfg(bad, sc)
    except RuntimeError as ex:
        assert "rule 3" in str(ex) and "3-cycle" in str(ex), ex
    else: raise AssertionError("expected rule 3 to fire on the 3-cycle minimum")

    # Rule 4: reps_per_chunk above avg_maxlen raises WITHOUT the opt-in ...
    bad = dict(base); bad["reps_per_chunk"] = 10**6
    try: _validate_cfg(bad, sc)
    except RuntimeError as ex: assert "rule 4" in str(ex), ex
    else: raise AssertionError("expected rule 4 to fire")
    # ... and is accepted WITH it. qick streams the accumulated buffer and wraps
    # modulo avg_maxlen, so a single long gapless chunk is legal; the opt-in
    # exists only because falling behind raises mid-run.
    ok = dict(base)
    ok.update({"reps_per_chunk": 10**6, "allow_reps_over_avg_maxlen": True})
    _validate_cfg(ok, sc)

    # Rule 5: read_length too long (decimated mode) — buffer cap is sized by the
    # declared readout window (us2cycles(read_length, ro_ch), i.e. f_output
    # samples), not by the const-pulse length and not by the tProc clock.
    dec_base = dict(base)
    dec_base.update({"mode": "decimated", "capture_length_us": 50.0,
                     "soft_avgs": 1})
    del dec_base["sample_period_us"]
    del dec_base["reps_per_chunk"]
    # read_length=5 us * 307.2 MHz = 1536 samples < buf_maxlen 8192
    _validate_cfg(dec_base, sc)
    bad = dict(dec_base); bad["read_length"] = 90.0  # 27648 samples >= 8192
    bad["capture_length_us"] = 100.0                  # keep capture >= read+offset
    try: _validate_cfg(bad, sc)
    except RuntimeError as ex: assert "rule 5]" in str(ex), ex
    else: raise AssertionError("expected rule 5 to fire")

    # Rule 5 boundary: exactly buf_maxlen samples must be REJECTED. qick's
    # readout.transfer_buf raises on `length >= buf_maxlen` while
    # acquire_decimated's own pre-check uses `>`, so a length of exactly
    # buf_maxlen would pass validation and still blow up in the transfer.
    _edge_us = 8192 / _F_OUTPUT           # -> exactly 8192 decimated samples
    bad = dict(dec_base)
    bad["read_length"] = _edge_us
    bad["capture_length_us"] = _edge_us + 1.0
    assert sc.us2cycles(bad["read_length"], ro_ch=0) == 8192
    try: _validate_cfg(bad, sc)
    except RuntimeError as ex: assert "rule 5]" in str(ex), ex
    else: raise AssertionError("expected rule 5 to reject exactly buf_maxlen")

    # Rule 5 must be computed on the READOUT clock, not the tProc clock. At
    # read_length = 20 us the two disagree: 20*307.2 = 6144 samples (legal,
    # < 8192) vs 20*430.08 = 8602 (would be rejected). If someone reverts rule 5
    # to the tProc conversion this config starts failing for no reason.
    ok = dict(dec_base)
    ok["read_length"] = 20.0
    ok["capture_length_us"] = 30.0
    assert sc.us2cycles(20.0, ro_ch=0) == 6144 and sc.us2cycles(20.0) == 8602
    _validate_cfg(ok, sc)

    # Rule 9: pulse shorter than readout window — pulse ends before readout closes.
    bad = dict(dec_base); bad["capture_length_us"] = 3.0  # < adc_trig_offset + read_length = 5.5
    try: _validate_cfg(bad, sc)
    except RuntimeError as ex: assert "rule 9" in str(ex), ex
    else: raise AssertionError("expected rule 9 to fire")

    # Rule 8: parity_drive_freq out of range (above f_dds)
    bad = dict(base); bad["parity_drive_freq"] = 9000.0
    try: _validate_cfg(bad, sc)
    except RuntimeError as ex: assert "rule 8" in str(ex), ex
    else: raise AssertionError("expected rule 8 to fire")

    # Rule 8: parity_drive_freq in (f_dds/2, f_dds] must be rejected. f_dds=6144
    # for the fake gens, so 5000 MHz passes the old [0, f_dds] bound but is
    # outside QICK's true [-3072, 3072] DDS band. Regression guard for the
    # half-bandwidth fix.
    bad = dict(base); bad["parity_drive_freq"] = 5000.0
    try: _validate_cfg(bad, sc)
    except RuntimeError as ex: assert "rule 8" in str(ex), ex
    else: raise AssertionError("expected rule 8 to fire for 5000 MHz > f_dds/2")

    # Missing key
    bad = dict(base); del bad["qubit_gain"]
    try: _validate_cfg(bad, sc)
    except RuntimeError as ex: assert "missing required keys" in str(ex)
    else: raise AssertionError("expected missing-key error")

    print("_validate_cfg all rules: OK")

    # --- soft_avgs > 1 opt-in gate (decimated mode) --------------------------
    # Per Codex review: soft_avgs > 1 averages across independent parity
    # captures and destroys the time-resolved trajectory. _acquire_decimated
    # must reject it unless the user explicitly opts in.
    class _StubExp:
        """Minimal ZeroSpanParity stand-in to exercise _acquire_decimated's
        soft_avgs gate without instantiating QICK programs."""
        _acquire_decimated = ZeroSpanParity._acquire_decimated
        def __init__(self, cfg, soccfg):
            self.cfg = cfg
            self.soccfg = soccfg
            self.soc = None
            self.prog = None
    cfg_soft = dict(base)
    cfg_soft.update({"mode": "decimated", "capture_length_us": 50.0,
                     "soft_avgs": 4, "read_length": 5.0,
                     "adc_trig_offset": 0.5})
    del cfg_soft["sample_period_us"]; del cfg_soft["reps_per_chunk"]
    try:
        _StubExp(cfg_soft, sc)._acquire_decimated(progress=False)
    except RuntimeError as ex:
        assert "soft_avgs" in str(ex), ex
    else:
        raise AssertionError("expected soft_avgs gate to raise without opt-in")
    print("_acquire_decimated soft_avgs gate fires without opt-in: OK")

    # --- strobe I/Q normalization matches single-shot units ------------------
    # Raw accumulated I/Q are sums over the readout window, but the apriori
    # separator from mSingleShotProgramFFMUX.collect_shots is per-decimated-
    # sample (raw acc_buf / us2cycles(readout_length, ro_ch)). _acquire_strobe
    # must divide by the SAME count or the separator's midpoint lands on the
    # wrong scale and parity classification is biased.
    #
    # The divisor is taken from prog.ro_chs[ro_ch]["length"] — the value
    # declare_readout actually used — precisely so it cannot drift from the
    # declaration. With _F_OUTPUT = 307.2, a 5 us window is 1536 samples.
    _RO_SAMPLES = int(round(5.0 * _F_OUTPUT))     # 1536
    assert _RO_SAMPLES == 1536

    class _FakeProg:
        """Stands in for a run ZeroSpanParityProgStrobe.

        ro_chs mirrors what declare_readout(length=us2cycles(read_length,
        ro_ch=ch)) leaves behind, keyed by absolute channel; di_buf/dq_buf stand
        in for the pre-0.2.29x raw buffers that raw_shot_buffers falls back to
        when acc_buf is absent.
        """
        def __init__(self, di_val, dq_val, n, ro_ch=0, ro_length=_RO_SAMPLES):
            self.di_buf = {0: np.full(n, di_val, dtype=float)}
            self.dq_buf = {0: np.full(n, dq_val, dtype=float)}
            self.ro_chs = {ro_ch: {"length": ro_length}}
        def acquire(self, *_a, **_k):
            return None

    class _StrobeStub:
        _acquire_strobe = ZeroSpanParity._acquire_strobe
        def __init__(self, cfg, soccfg, prog):
            self.cfg = cfg
            self.soccfg = soccfg
            self.soc = None
            self.prog = prog

    cfg_strobe = dict(base)
    n_reps = 1000
    cfg_strobe["reps_per_chunk"] = n_reps
    # di_val chosen so the per-sample answer is a round 100.0
    di_val = 100.0 * _RO_SAMPLES
    fake = _FakeProg(di_val=di_val, dq_val=0.0, n=n_reps)
    stub = _StrobeStub(cfg_strobe, sc, fake)
    out = stub._acquire_strobe(progress=False)
    assert abs(float(out["I"][0]) - 100.0) < 1e-9, (
        f"strobe normalization wrong: got {out['I'][0]}, expected 100.0"
    )
    assert out["ro_norm_cycles"] == float(_RO_SAMPLES), out["ro_norm_cycles"]
    assert out["read_length_us"] == 5.0
    assert out["mode"] == "strobe"

    # Regression guard for the clock-domain bug: the divisor must be the READOUT
    # sample count, never the tProc-cycle count. Those differ by f_time/f_output
    # = 1.4 on this board, so assert the wrong value is not what came out.
    _WRONG = float(sc.us2cycles(5.0))              # 2150 tProc cycles
    assert _WRONG != float(_RO_SAMPLES)
    assert out["ro_norm_cycles"] != _WRONG, (
        "ro_norm_cycles is on the tProc clock; declare_readout takes decimated "
        "samples, so read_length must be converted with ro_ch="
    )

    # Fallback path: no prog.ro_chs (e.g. a stub or a future qick refactor) must
    # still land on the same divisor via us2cycles(..., ro_ch=ro_chs[0]).
    class _FakeProgNoRoChs(_FakeProg):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            del self.ro_chs
    stub2 = _StrobeStub(dict(cfg_strobe), sc,
                        _FakeProgNoRoChs(di_val=di_val, dq_val=0.0, n=n_reps))
    out2 = stub2._acquire_strobe(progress=False)
    assert out2["ro_norm_cycles"] == float(_RO_SAMPLES), out2["ro_norm_cycles"]
    assert abs(float(out2["I"][0]) - 100.0) < 1e-9

    print("_acquire_strobe normalizes I/Q by the declared readout sample count: OK")
