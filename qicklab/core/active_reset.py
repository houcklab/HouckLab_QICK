"""Hardware active reset to |g>: measure, read the accumulated I, play a corrective
pi only when the qubit is found in |e> (the ModifiedRamsey implementation).

See docs/experiments/active_reset.md.
"""


class ActiveResetMixin:
    """For an AveragerProgram with self.q_rp, a 4-sigma "qubit" gaussian played at
    self.f_ge_reg, and the attributes set by core.readout.cover_readout_window."""

    # True fires the corrective pi unconditionally (no condj). Only ActiveResetVerify's
    # force-pi diagnostic sets it; ModifiedRamsey never does.
    reset_force_pi = False

    def configure_active_reset(self):
        """Reset registers, flags and the sign-safe offset placeholder (no tProc writes)."""
        cfg = self.cfg
        # Registers 3/4/5 are free on any page (docs/architecture.md#generators-and-registers).
        self.r_read = 4
        self.r_thresh = 5

        self.use_active_reset = cfg.get("use_active_reset", False)
        self.reset_cycles = int(cfg.get("reset_cycles", 1)) if self.use_active_reset else 0
        if self.reset_cycles < 0:
            raise ValueError("cfg['reset_cycles'] must be non-negative")
        if self.use_active_reset:
            for delay_key in ("reset_readout_relax_delay", "post_reset_wait"):
                if cfg.get(delay_key, 0.0) < 0:
                    raise ValueError(f"cfg['{delay_key}'] must be non-negative")
        # condj skips the corrective pi when the qubit already reads as |g>.
        self.reset_skip_op = "<" if cfg.get("reset_ground_below_threshold", True) else ">"
        # Sized in load_reset_threshold(); 0 while active reset is off.
        self.cmp_offset = 0

    def load_reset_threshold(self):
        """Write threshold + sign-safe offset into r_thresh (no-op without active reset).

        The tProc compares raw accumulated I as unsigned, so both operands get
        cmp_offset = ro_norm << 15 > |raw I| (docs/experiments/active_reset.md#how-it-decides).
        """
        cfg = self.cfg
        if self.use_active_reset:
            if "readout_threshold" not in cfg:
                raise KeyError(
                    "use_active_reset=True requires cfg['readout_threshold'] "
                    "(single-shot I threshold, normalized units)."
                )
            if "pi_gain" not in cfg:
                raise KeyError(
                    "use_active_reset=True requires cfg['pi_gain'] for the corrective reset flip."
                )
            ro_norm = self.readout_window_cycles[cfg["ro_chs"][0]]
            raw_threshold = int(round(cfg["readout_threshold"] * ro_norm))

            self.cmp_offset = int(ro_norm) << 15
            if self.cmp_offset >= 1 << 30:
                raise ValueError(
                    f"cfg['readout_length']={cfg['readout_length']} us gives a "
                    f"readout window of {ro_norm} cycles, whose sign-safe "
                    f"comparison offset {self.cmp_offset} exceeds the 2^30 "
                    "immediate limit. Shorten the readout window for active reset."
                )
            if abs(raw_threshold) >= self.cmp_offset:
                raise ValueError(
                    f"raw_threshold {raw_threshold} exceeds the sign-safe "
                    f"comparison offset {self.cmp_offset}; the readout is "
                    "saturating the accumulator."
                )
            # safe_regwi: above 2^14 window cycles the sum can reach 2^30, which a plain
            # regwi immediate does not load correctly (identical to regwi below 2^30).
            self.safe_regwi(self.q_rp, self.r_thresh, raw_threshold + self.cmp_offset)

    def active_reset_to_g(self):
        """reset_cycles rounds of measure -> read I -> conditional pi, then post_reset_wait."""
        cfg = self.cfg
        ro_ch = cfg["ro_chs"][0]
        # `read` takes the tProc input channel, not the readout index.
        tproc_in_ch = self.soccfg["readouts"][ro_ch].get("tproc_ch")
        if tproc_in_ch is None or tproc_in_ch < 0:
            raise RuntimeError(
                f"readout channel {ro_ch} has no tProc input channel "
                f"(tproc_ch={tproc_in_ch}); its accumulated value cannot be read "
                "back by the tProc, so active reset is impossible on it."
            )

        for i in range(self.reset_cycles):
            done_label = "RESET_DONE_%d" % i

            self.measure(
                pulse_ch=cfg["res_ch"],
                adcs=self.ro_chs,
                adc_trig_offset=self.adc_trig_offset_cycles,
                wait=True,
                syncdelay=self.us2cycles(cfg.get("reset_readout_relax_delay", 1.0)),
            )

            self.read(tproc_in_ch, self.q_rp, "lower", self.r_read)
            self.mathi(self.q_rp, self.r_read, self.r_read, "+", self.cmp_offset)
            if not self.reset_force_pi:
                self.condj(self.q_rp, self.r_read, self.reset_skip_op, self.r_thresh, done_label)

            self.set_pulse_registers(
                ch=cfg["qubit_ch"],
                style="arb",
                freq=self.f_ge_reg,
                phase=0,
                gain=cfg["pi_gain"],
                waveform="qubit",
            )
            self.pulse(ch=cfg["qubit_ch"])

            # Label before the sync so timing reconverges whether or not the pi played.
            self.label(done_label)
            self.sync_all()

        if self.reset_cycles:
            self.sync_all(self.us2cycles(cfg.get("post_reset_wait", 0.0)))
