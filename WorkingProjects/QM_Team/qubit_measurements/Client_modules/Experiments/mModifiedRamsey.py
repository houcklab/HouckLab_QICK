from qick import *
import matplotlib.pyplot as plt
import numpy as np
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.CoreLib.Experiment import ExperimentClass
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Helpers.shot_buffers import raw_shot_buffers

# Minimum real tProc stall (us) between the reset readout window closing and the
# feedback `read`. The accumulated word has to cross the avg buffer's async FIFO
# into the PS clock domain and then an AXIS converter into the tProc domain --
# tens to ~150 ns. 0.5 us is ~3x that and is free in practice: the runners
# already wait 5 us here for the resonator to ring down. Must match
# mActiveResetVerify.MIN_RESET_READ_SETTLE_US (verify_ModifiedRamsey asserts it).
MIN_RESET_READ_SETTLE_US = 0.5


class ModifiedRamseyProgram(AveragerProgram):
    """
    Fixed-tau Ramsey for charge-parity switching detection.

    Each shot optionally begins with hardware active reset to |g> (real
    measurement feedback: measure -> read accumulated I -> conditionally
    apply a pi pulse only if the qubit was found in |e>). After reset the
    qubit is deterministically in |g>, which is the correct starting state
    for the Ramsey sequence below.

    No-pi sequence:
        [active reset to |g>] -> pi/2 -> wait tau -> pi/2(final_phase) -> readout

    Echo/pi sequence:
        [active reset to |g>] -> pi/2 -> wait tau/2 -> pi -> wait tau/2 -> pi/2(final_phase) -> readout

    tau = 1 / (2 * cfg["df"]), df in MHz => tau in us. (Same tau in both the
    standard and symmetric-drive schemes; the |relative phase| between branches
    is pi either way.)

    cfg["use_pi_pulse"]: if True, inserts a pi pulse in the middle.

    cfg["symmetric_ramsey"]: selects the drive frequency and the closing-pi/2 base
                          phase.
        False (default): STANDARD scheme. Drive on-resonant with the upper parity
            peak (cfg["f_ge"]). Closing pi/2 base phase 180 deg.
            on-resonant (upper) -> |g>,   off-resonant (lower) -> |e>.
        True:            SYMMETRIC-DRIVE scheme. Drive at the midpoint
            f_avg = (f_lower + f_upper)/2 = cfg["f_ge"] - cfg["df"]/2. The two
            branches are symmetrically detuned by +/- df/2 and rotate +/- 90 deg
            during tau. Closing pi/2 base phase 90 deg.
            f_upper -> |e>,   f_lower -> |g>.

    cfg["flip_final_pi2"]: adds 180 deg to the closing-pi/2 phase (sign-flips the
                           second pulse), which swaps the parity -> state mapping
                           in EITHER scheme (standard 180<->0, symmetric 90<->270).
    cfg["pi_gain"]     : DAC gain for the pi pulse, required if use_pi_pulse=True
                         or if use_active_reset=True (same pi pulse is reused
                         for the reset corrective flip).
    cfg["mr_relax_delay"]:
                         optional inter-shot delay in us after the final Ramsey
                         readout (default 0). This is deliberately separate from
                         cfg["relax_delay"], which the surrounding runner uses
                         for its two-tone spectroscopy search.

    Active-reset config:
    cfg["use_active_reset"]    : if True, prepend active reset to |g> to every
                                 shot. Default False (opt-in), which preserves the
                                 old behaviour (rely on thermal/measurement reset).
    cfg["readout_threshold"]   : single-shot I discrimination threshold, in the
                                 SAME normalized units as collect_shots()/the IQ
                                 plot (i.e. accumulated I divided by the readout
                                 window length in cycles). Internally rescaled to
                                 the raw accumulator units the tProc compares.
                                 NOTE: the feedback thresholds on the raw in-phase
                                 (I) value only, so this requires the readout phase
                                 (res_phase) to be rotated such that |g> and |e>
                                 separate ALONG I. If your single-shot calibration
                                 discriminates along an arbitrary 2D separator
                                 line, rotate the readout first (or ask for the
                                 rotated-projection variant of the feedback).
    cfg["reset_ground_below_threshold"]:
                                 True (default) if |g> has I below threshold (and
                                 |e> above). Set False if your IQ blobs are flipped.
    cfg["reset_cycles"]        : number of measure->feedback rounds per shot
                                 (default 1). More rounds = better ground-state
                                 fidelity at the cost of extra readouts.
    cfg["reset_readout_relax_delay"]:
                                 syncdelay (us) after each reset readout before the
                                 conditional flip (default 1.0).
    cfg["reset_read_settle"]   : MINIMUM real tProc stall (us) between the reset
                                 readout window closing and the `read` that feeds
                                 the condj (default 0.5). Load-bearing; see the
                                 long comment in active_reset_to_g(). Only the
                                 SHORTFALL against reset_readout_relax_delay is
                                 emitted, as a waiti, so the scheduled rep period
                                 is unchanged for every cfg.
    cfg["post_reset_wait"]     : extra settle time (us) after the reset block,
                                 before the first Ramsey pi/2 (default 0.0).
    """

    def initialize(self):
        cfg = self.cfg

        if cfg["df"] <= 0:
            raise ValueError("cfg['df'] must be positive")
        if cfg["sigma"] <= 0:
            raise ValueError("cfg['sigma'] must be positive")
        if cfg["readout_length"] <= 0:
            raise ValueError("cfg['readout_length'] must be positive")
        if not cfg["ro_chs"]:
            raise ValueError("cfg['ro_chs'] must contain at least one readout channel")
        for delay_key in ("adc_trig_offset", "mr_relax_delay"):
            if cfg.get(delay_key, 0.0) < 0:
                raise ValueError(f"cfg['{delay_key}'] must be non-negative")

        self.q_rp = self.ch_page(cfg["qubit_ch"])
        self.r_wait = 3
        self.r_phase = self.sreg(cfg["qubit_ch"], "phase")

        # Free user registers on the qubit page (pulse registers occupy 11-30,
        # r_wait uses 3). Used for active-reset measurement feedback.
        self.r_read = 4    # holds the accumulated I read back from the ADC
        self.r_thresh = 5  # holds the single-shot discrimination threshold

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
        if self.use_active_reset:
            for delay_key in ("reset_readout_relax_delay", "post_reset_wait",
                              "reset_read_settle"):
                if cfg.get(delay_key, 0.0) < 0:
                    raise ValueError(f"cfg['{delay_key}'] must be non-negative")
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
        # not configurable away.
        self.reset_read_settle_cycles = max(
            self.us2cycles(cfg.get("reset_read_settle",
                                   MIN_RESET_READ_SETTLE_US)),
            self.us2cycles(MIN_RESET_READ_SETTLE_US),
        )
        self.reset_read_extra_wait_cycles = max(
            0,
            self.reset_read_settle_cycles - self.reset_readout_syncdelay_cycles
        )
        # The shortfall is emitted as a waiti BEYOND the tProc time reference, but
        # the corrective pi's `set` targets reference+0, so the pi fires this late
        # and the real rep period exceeds the scheduled one by the same amount
        # (modified_ramsey_timing stays correct as a *scheduled*-period model).
        # Zero for every shipped cfg: the runners pass
        # reset_readout_relax_delay=5.0 and charge_parity defaults it to 1.0.
        if (self.use_active_reset and self.reset_cycles
                and self.reset_read_extra_wait_cycles > 0):
            late_us = self.cycles2us(self.reset_read_extra_wait_cycles)
            print(
                "[ModifiedRamsey] WARNING: reset_readout_relax_delay "
                f"({cfg.get('reset_readout_relax_delay', 1.0)} us) is shorter "
                f"than the feedback-read settle floor "
                f"({MIN_RESET_READ_SETTLE_US} us). The corrective pi will fire "
                f"{late_us:.3f} us LATER than scheduled, on a resonator that has "
                "had that much less time to ring down, and the real rep period "
                "will exceed the modelled one by the same amount."
            )
        # condj jumps (skips the corrective pi) when the qubit is already in |g>.
        # If |g> sits below threshold in I, the "already ground" test is I < thresh.
        self.reset_skip_op = "<" if cfg.get("reset_ground_below_threshold", True) else ">"
        # Sign-safe comparison offset. ActiveResetVerify data on TATQ01/BFE
        # (2026-06-05/06) showed the corrective pi firing on every shot whose
        # accumulated I is NEGATIVE (the deployed tProc compares as if
        # unsigned, so negative two's-complement I reads as a huge positive).
        # Adding the same large positive constant to BOTH operands keeps them
        # strictly positive, so signed and unsigned comparison agree.
        # Sized 2^28 (was 2^24): the raw accumulator scales with the readout
        # window, and raw_threshold = readout_threshold * window_cycles below.
        # At the deployed 15 us window (~4600 cycles) a normalized threshold of
        # a few thousand puts raw_threshold within ~1.2x of a 2^24 offset, i.e.
        # against the guard. 2^28 keeps offset + |raw| well under the 2^31
        # register/immediate limit while restoring real headroom.
        self.cmp_offset = 1 << 28

        # Total parity-mapping evolution time. tau = 1/(2*df) for both schemes:
        # the |relative phase| accumulated between the two parity branches is pi.
        self.tau_us = 1.0 / (2.0 * cfg["df"])
        self.use_pi_pulse = cfg.get("use_pi_pulse", False)

        # symmetric_ramsey: drive at the midpoint f_avg = (f_lower + f_upper)/2
        # rather than on-resonant with the upper branch. cfg["f_ge"] is passed as
        # the upper peak, so f_avg = f_ge - df/2. Both branches are then detuned by
        # +/- df/2 and rotate +/- 90 deg during tau.
        self.symmetric_ramsey = cfg.get("symmetric_ramsey", False)
        self.drive_freq_mhz = (
            cfg["f_ge"] - cfg["df"] / 2.0 if self.symmetric_ramsey else cfg["f_ge"]
        )

        # Closing-pi/2 phase sets the parity -> computational-state mapping. Base
        # phase is 180 deg (standard, undoes the first pi/2) or 90 deg (symmetric).
        # flip_final_pi2 adds 180 deg, swapping the mapping in either scheme.
        base_pi2_phase_deg = 90 if self.symmetric_ramsey else 180
        flip_offset_deg = 180 if cfg.get("flip_final_pi2", False) else 0
        self.final_pi2_phase_deg = (base_pi2_phase_deg + flip_offset_deg) % 360

        # If using echo, split the same total tau around the pi pulse.
        wait_us = self.tau_us / 2.0 if self.use_pi_pulse else self.tau_us
        self.regwi(self.q_rp, self.r_wait, self.us2cycles(wait_us))

        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])

        # The ADC trigger starts adc_trig_offset after the resonator pulse starts,
        # so the tone must cover offset + integration window. Keep all config
        # durations in us, then convert each register using its actual clock domain.
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

        # Re-check coverage after every duration has been quantized on its own
        # hardware clock. Equality in user-space microseconds does not guarantee
        # equality after generator/readout/tProc rounding.
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
        # Cross-clock rounding can make length == offset + window a fraction of
        # a cycle short. Extend only by the exact number of resonator-generator
        # cycles needed to cover the quantized ADC window.
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
        # All qubit pulses (reset pi, pi/2s, echo pi) play at the drive frequency:
        # cfg["f_ge"] in the standard scheme, the midpoint f_avg in symmetric_ramsey.
        self.f_ge_reg = self.freq2reg(self.drive_freq_mhz, gen_ch=cfg["qubit_ch"])

        self.pulse_sigma = self.us2cycles(cfg["sigma"], gen_ch=cfg["qubit_ch"])
        self.pulse_qubit_length = self.us2cycles(
            cfg["sigma"] * 4,
            gen_ch=cfg["qubit_ch"]
        )

        # The pi and pi/2 pulses share the SAME gaussian envelope shape; they
        # differ only in DAC gain, which is set per-pulse below. Define ONE
        # waveform rather than two identical ones: each gaussian envelope is
        # sigma*4 long, and two full-size copies on the same generator would be
        # loaded at sequential addresses (0 and ~length), so their combined
        # footprint can exceed the 65536-sample envelope memory even when a
        # single copy fits. (With sigma=2 us each copy is ~55056 samples, so two
        # copies = ~110112 > 65536 -> "AxisSignalGen: buffer length must be
        # 65536 samples or less.") Sharing one envelope halves the footprint.
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

        if self.use_active_reset:
            if "readout_threshold" not in cfg:
                raise KeyError(
                    "use_active_reset=True requires cfg['readout_threshold'] "
                    "(single-shot I threshold, normalized units)."
                )
            if "pi_gain" not in cfg:
                raise KeyError(
                    "use_active_reset=True requires cfg['pi_gain'] for the "
                    "corrective reset flip."
                )
            # collect_shots() divides the accumulated I by the readout-window
            # length, so the threshold the user reads off the IQ plot is in those
            # normalized units. The tProc compares the RAW accumulator, so scale
            # the threshold back up by the same window length here.
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

        self.sync_all(self.us2cycles(0.2))

    def active_reset_to_g(self):
        """
        Real measurement-feedback reset to |g>.

        For each reset cycle: fire the readout, read back the accumulated I value
        into a tProc register, and conditionally apply a pi pulse ONLY if the
        qubit was found in |e>. After the block the qubit is in |g>.
        """
        cfg = self.cfg
        ro_ch = self.reset_ro_ch

        for i in range(self.reset_cycles):
            done_label = "RESET_DONE_%d" % i

            # 1) Measure the qubit (this readout also lands in the data buffer;
            #    collect_shots() ignores it and keeps only the final readout).
            self.measure(
                pulse_ch=cfg["res_ch"],
                adcs=self.ro_chs,
                adc_trig_offset=self.adc_trig_offset_cycles,
                wait=True,
                syncdelay=self.reset_readout_syncdelay_cycles
            )

            # 1b) STALL the tProc until the accumulated I is actually AT the
            # tProc input. DO NOT REMOVE THIS LINE.
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
            # What that cost, measured 2026-07-28 on TATQ01-SiO2 Q3 via
            # ActiveResetVerify (2000 reps/condition, 5 verification readouts):
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

            # 2) Read the accumulated in-phase value (lower = I) into r_read.
            # `read` addresses a tProc INPUT PORT, not an ADC/readout index.
            self.read(self.reset_read_port, self.q_rp, "lower", self.r_read)

            # Offset I into strictly positive territory so the comparison is
            # sign-safe (see cmp_offset in initialize()); r_thresh already
            # carries the same offset.
            self.mathi(self.q_rp, self.r_read, self.r_read, "+", self.cmp_offset)

            # 3) If already in |g>, skip the corrective pi. Otherwise flip e -> g.
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

            # Label sits before the sync so timing reconverges on both branches
            # (whether or not the corrective pi played).
            self.label(done_label)
            self.sync_all()

        if self.reset_cycles:
            self.sync_all(self.us2cycles(cfg.get("post_reset_wait", 0.0)))

    def body(self):
        cfg = self.cfg

        # Per-shot active reset so every Ramsey sequence starts from |g>.
        if self.use_active_reset:
            self.active_reset_to_g()

        # First pi/2 at phase 0.
        self.regwi(self.q_rp, self.r_phase, 0)
        self.set_pulse_registers(
            ch=cfg["qubit_ch"],
            style="arb",
            freq=self.f_ge_reg,
            phase=0,
            gain=cfg["pi2_gain"],
            waveform="qubit"
        )
        self.pulse(ch=cfg["qubit_ch"])

        self.sync_all()
        self.sync(self.q_rp, self.r_wait)

        if self.use_pi_pulse:
            # Echo pi pulse in the middle.
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
            self.sync(self.q_rp, self.r_wait)

        # Final pi/2. Phase (180 deg default, 0 deg if flip_final_pi2) sets the
        # parity -> computational-state mapping; see class docstring.
        self.set_pulse_registers(
            ch=cfg["qubit_ch"],
            style="arb",
            freq=self.f_ge_reg,
            phase=self.deg2reg(self.final_pi2_phase_deg, gen_ch=cfg["qubit_ch"]),
            gain=cfg["pi2_gain"],
            waveform="qubit"
        )
        self.pulse(ch=cfg["qubit_ch"])
        self.sync_all(self.us2cycles(0.05))

        # Final readout. The MR-specific delay is explicit so the spectroscopy
        # relax_delay carried in the shared cfg cannot silently slow this loop.
        self.measure(
            pulse_ch=cfg["res_ch"],
            adcs=self.ro_chs,
            adc_trig_offset=self.adc_trig_offset_cycles,
            wait=True,
            syncdelay=self.us2cycles(cfg.get("mr_relax_delay", 0.0))
        )

    def acquire(self, soc, threshold=None, angle=None, load_pulses=True,
                readouts_per_experiment=None, save_experiments=None,
                start_src="internal", progress=False):
        # One readout per reset cycle plus the single final Ramsey readout.
        self.reads_per_rep = self.reset_cycles + 1
        if (
            readouts_per_experiment is not None
            and readouts_per_experiment != self.reads_per_rep
        ):
            raise ValueError(
                "readouts_per_experiment must equal reset_cycles + 1 "
                f"({self.reads_per_rep}) for ModifiedRamseyProgram"
            )
        if threshold is not None:
            # qick's threshold mode REPLACES the accumulated data with heaviside
            # decisions and zeros Q (AcquireMixin._process_accumulated), while
            # this class returns collect_shots() -- read straight out of the raw
            # acc_buf -- and discards super().acquire()'s return value. Accepting
            # a threshold here would silently hand back meaningless IQ. Threshold
            # the shots yourself after acquire(); the g/e separator lives in the
            # runner (get_apriori_separator_from_singleshot).
            raise ValueError(
                "ModifiedRamseyProgram.acquire() does not support threshold=...; "
                "it returns raw per-shot IQ. Classify the returned shots instead."
            )
        super().acquire(
            soc,
            readouts_per_experiment=self.reads_per_rep,
            load_pulses=load_pulses,
            start_src=start_src,
            progress=progress,
            angle=angle,
            save_experiments=save_experiments,
        )
        return self.collect_shots()

    def collect_shots(self):
        ro_ch = self.cfg["ro_chs"][0]
        norm = self.us2cycles(self.cfg["readout_length"], ro_ch=ro_ch)
        reads_per_rep = getattr(self, "reads_per_rep", 1)
        # Readout ii of each rep lives at di_buf[ch][ii::reads_per_rep]; the final
        # Ramsey readout is the last one in each rep (the earlier ones are resets).
        final = reads_per_rep - 1
        di_buf, dq_buf = raw_shot_buffers(self)
        shots_i = di_buf[0][final::reads_per_rep].reshape((1, self.cfg["reps"])) / norm
        shots_q = dq_buf[0][final::reads_per_rep].reshape((1, self.cfg["reps"])) / norm
        return shots_i, shots_q


class ModifiedRamsey(ExperimentClass):
    """
    Repeated fixed-tau Ramsey for charge-parity switching time-series.
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
        prog = ModifiedRamseyProgram(self.soccfg, self.cfg)
        shots_i, shots_q = prog.acquire(
            self.soc,
            load_pulses=True,
            progress=progress
        )

        shots_i = np.asarray(shots_i).ravel()
        shots_q = np.asarray(shots_q).ravel()

        # QICK streamer stats measure start_tproc -> completed data-transfer
        # chunks. This is useful for comparing end-to-end acquisition throughput
        # against the scheduled cadence, but includes polling/transfer latency and
        # therefore is not used as the physical shot-time axis.
        streamer_elapsed_s = np.nan
        streamer_average_rep_period_us = np.nan
        if prog.stats:
            last_elapsed_s, last_shots, _, _ = prog.stats[-1]
            streamer_elapsed_s = float(last_elapsed_s)
            if last_shots:
                streamer_average_rep_period_us = (
                    streamer_elapsed_s * 1e6 / float(last_shots)
                )

        data = {
            'config': self.cfg,
            'data': {
                'shots_i': shots_i,
                'shots_q': shots_q,
                'tau_us': 1.0 / (2.0 * self.cfg["df"]),
                'wait_us': (
                    1.0 / (4.0 * self.cfg["df"])
                    if self.cfg.get("use_pi_pulse", False)
                    else 1.0 / (2.0 * self.cfg["df"])
                ),
                'f_ge': self.cfg["f_ge"],
                'df': self.cfg["df"],
                'use_pi_pulse': self.cfg.get("use_pi_pulse", False),
                'flip_final_pi2': self.cfg.get("flip_final_pi2", False),
                'symmetric_ramsey': self.cfg.get("symmetric_ramsey", False),
                'final_pi2_phase_deg': (
                    (90 if self.cfg.get("symmetric_ramsey", False) else 180)
                    + (180 if self.cfg.get("flip_final_pi2", False) else 0)
                ) % 360,
                'drive_freq': (
                    self.cfg["f_ge"] - self.cfg["df"] / 2.0
                    if self.cfg.get("symmetric_ramsey", False)
                    else self.cfg["f_ge"]
                ),
                'use_active_reset': self.cfg.get("use_active_reset", False),
                'reset_cycles': (
                    int(self.cfg.get("reset_cycles", 1))
                    if self.cfg.get("use_active_reset", False) else 0
                ),
                'streamer_elapsed_s': streamer_elapsed_s,
                'streamer_average_rep_period_us': streamer_average_rep_period_us,
            }
        }
        self.data = data
        return data

    def display(self, data=None, plotDisp=False, figNum=1, **kwargs):
        if data is None:
            data = self.data

        shots_i = np.asarray(data['data']['shots_i'])
        shots_q = np.asarray(data['data']['shots_q'])
        tau_us = data['data']['tau_us']
        wait_us = data['data']['wait_us']
        df = data['data']['df']
        use_pi_pulse = data['data'].get('use_pi_pulse', False)

        while plt.fignum_exists(num=figNum):
            figNum += 1

        seq_label = "echo pi" if use_pi_pulse else "no pi"

        fig = plt.figure(figNum)
        plt.plot(shots_i, shots_q, '.', alpha=0.4, markersize=3)
        plt.xlabel("I (a.u.)")
        plt.ylabel("Q (a.u.)")
        plt.axis('equal')
        plt.title(
            self.titlename
            + f"\n{seq_label}, tau={tau_us:.4f} us, wait={wait_us:.4f} us, df={df:.4f} MHz"
        )
        plt.tight_layout()
        plt.savefig(self.iname[:-4] + '_IQ.png')

        if plotDisp:
            plt.show(block=True)
            plt.pause(0.1)
        else:
            fig.clf(True)
            plt.close(fig)

    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])
