from qick import *
import matplotlib.pyplot as plt
import numpy as np
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.CoreLib.Experiment import ExperimentClass


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
    cfg["post_reset_wait"]             : settle time (us) after the reset block
                                         (default 0.0).
    cfg["reset_force_pi"]              : diagnostic; fire the corrective pi
                                         UNCONDITIONALLY (skip the condj) to
                                         measure the bare post-readout pi
                                         fidelity (default False).
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
        ):
            if cfg.get(delay_key, 0.0) < 0:
                raise ValueError(f"cfg['{delay_key}'] must be non-negative")

        self.q_rp = self.ch_page(cfg["qubit_ch"])

        # Free user registers on the qubit page (mirrors ModifiedRamsey).
        self.r_read = 4    # holds the accumulated I read back from the ADC
        self.r_thresh = 5  # holds the single-shot discrimination threshold

        self.prep_excited = cfg.get("prep_excited", False)
        self.use_active_reset = cfg.get("use_active_reset", False)
        self.reset_cycles = int(cfg.get("reset_cycles", 1)) if self.use_active_reset else 0
        if self.reset_cycles < 0:
            raise ValueError("cfg['reset_cycles'] must be non-negative")
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
        # correct under either firmware behaviour. 2^24 >> any |raw I|
        # (~1e4-1e5) and offset+|raw| << 2^30 (immediate sign-bit limit).
        self.cmp_offset = 1 << 24
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

        self.sync_all(self.us2cycles(0.2))

    def active_reset_to_g(self):
        """
        Real measurement-feedback reset to |g>. Copied verbatim (logic) from
        ModifiedRamseyProgram.active_reset_to_g() so this experiment validates the
        identical sequence.
        """
        cfg = self.cfg
        ro_ch = cfg["ro_chs"][0]

        for i in range(self.reset_cycles):
            done_label = "VRESET_DONE_%d" % i

            self.measure(
                pulse_ch=cfg["res_ch"],
                adcs=self.ro_chs,
                adc_trig_offset=self.adc_trig_offset_cycles,
                wait=True,
                syncdelay=self.us2cycles(cfg.get("reset_readout_relax_delay", 1.0))
            )

            self.read(ro_ch, self.q_rp, "lower", self.r_read)

            # Offset the (possibly negative) accumulated I into strictly
            # positive territory so the comparison below is sign-safe (see
            # cmp_offset comment in initialize()). r_thresh already carries
            # the same offset.
            self.mathi(self.q_rp, self.r_read, self.r_read, "+", self.cmp_offset)

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
        super().acquire(
            soc,
            readouts_per_experiment=self.reads_per_rep,
            load_pulses=load_pulses,
            start_src=start_src,
            progress=progress
        )
        return self.collect_shots()

    def collect_shots(self):
        ro_ch = self.cfg["ro_chs"][0]
        norm = self.us2cycles(self.cfg["readout_length"], ro_ch=ro_ch)
        reps = self.cfg["reps"]
        reads_per_rep = self.reads_per_rep
        # Verification read k of each rep lives at di_buf[ch][reset_cycles+k :: reads_per_rep].
        verify_i = np.empty((self.n_verify_reads, reps))
        verify_q = np.empty((self.n_verify_reads, reps))
        for k in range(self.n_verify_reads):
            idx = self.reset_cycles + k
            verify_i[k] = self.di_buf[0][idx::reads_per_rep][:reps] / norm
            verify_q[k] = self.dq_buf[0][idx::reads_per_rep][:reps] / norm
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
        prog = ActiveResetVerifyProgram(self.soccfg, self.cfg)
        verify_i, verify_q = prog.acquire(
            self.soc,
            load_pulses=True,
            progress=progress
        )
        verify_i = np.asarray(verify_i)
        verify_q = np.asarray(verify_q)

        g_center = np.asarray(self.cfg["g_center"], dtype=float)
        e_center = np.asarray(self.cfg["e_center"], dtype=float)
        normal = e_center - g_center
        midpoint = 0.5 * (g_center + e_center)

        # Classify each read: score>0 is closer to |e>, so P(|g>) = fraction <= 0.
        n_reads, n_reps = verify_i.shape
        p_ground = np.empty(n_reads)
        for k in range(n_reads):
            iq = np.column_stack([verify_i[k], verify_q[k]])
            scores = (iq - midpoint) @ normal
            p_ground[k] = float(np.mean(scores <= 0))

        data = {
            'config': self.cfg,
            'data': {
                'verify_i': verify_i,
                'verify_q': verify_q,
                'p_ground': p_ground,
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
