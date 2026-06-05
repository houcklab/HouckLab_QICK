from qick import *
import matplotlib.pyplot as plt
import numpy as np
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.CoreLib.Experiment import ExperimentClass


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
    cfg["post_reset_wait"]     : extra settle time (us) after the reset block,
                                 before the first Ramsey pi/2 (default 0.0).
    """

    def initialize(self):
        cfg = self.cfg

        self.q_rp = self.ch_page(cfg["qubit_ch"])
        self.r_wait = 3
        self.r_phase = self.sreg(cfg["qubit_ch"], "phase")

        # Free user registers on the qubit page (pulse registers occupy 11-30,
        # r_wait uses 3). Used for active-reset measurement feedback.
        self.r_read = 4    # holds the accumulated I read back from the ADC
        self.r_thresh = 5  # holds the single-shot discrimination threshold

        self.use_active_reset = cfg.get("use_active_reset", False)
        self.reset_cycles = int(cfg.get("reset_cycles", 1)) if self.use_active_reset else 0
        # condj jumps (skips the corrective pi) when the qubit is already in |g>.
        # If |g> sits below threshold in I, the "already ground" test is I < thresh.
        self.reset_skip_op = "<" if cfg.get("reset_ground_below_threshold", True) else ">"

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

        for ch in cfg["ro_chs"]:
            self.declare_readout(
                ch=ch,
                length=self.us2cycles(cfg["readout_length"]),
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
            length=self.us2cycles(cfg["length"])
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
            ro_norm = self.us2cycles(cfg["readout_length"], ro_ch=0)
            raw_threshold = int(round(cfg["readout_threshold"] * ro_norm))
            self.regwi(self.q_rp, self.r_thresh, raw_threshold)

        self.sync_all(self.us2cycles(0.2))

    def active_reset_to_g(self):
        """
        Real measurement-feedback reset to |g>.

        For each reset cycle: fire the readout, read back the accumulated I value
        into a tProc register, and conditionally apply a pi pulse ONLY if the
        qubit was found in |e>. After the block the qubit is in |g>.
        """
        cfg = self.cfg
        ro_ch = cfg["ro_chs"][0]

        for i in range(self.reset_cycles):
            done_label = "RESET_DONE_%d" % i

            # 1) Measure the qubit (this readout also lands in the data buffer;
            #    collect_shots() ignores it and keeps only the final readout).
            self.measure(
                pulse_ch=cfg["res_ch"],
                adcs=self.ro_chs,
                adc_trig_offset=self.us2cycles(cfg["adc_trig_offset"]),
                wait=True,
                syncdelay=self.us2cycles(cfg.get("reset_readout_relax_delay", 1.0))
            )

            # 2) Read the accumulated in-phase value (lower = I) into r_read.
            self.read(ro_ch, self.q_rp, "lower", self.r_read)

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

        # Readout with no relax delay.
        self.measure(
            pulse_ch=cfg["res_ch"],
            adcs=self.ro_chs,
            adc_trig_offset=self.us2cycles(cfg["adc_trig_offset"]),
            wait=True,
            syncdelay=0
        )

    def acquire(self, soc, threshold=None, angle=None, load_pulses=True,
                readouts_per_experiment=None, save_experiments=None,
                start_src="internal", progress=False):
        # One readout per reset cycle plus the single final Ramsey readout.
        self.reads_per_rep = self.reset_cycles + 1
        super().acquire(
            soc,
            readouts_per_experiment=self.reads_per_rep,
            load_pulses=load_pulses,
            start_src=start_src,
            progress=progress
        )
        return self.collect_shots()

    def collect_shots(self):
        norm = self.us2cycles(self.cfg["readout_length"], ro_ch=0)
        reads_per_rep = getattr(self, "reads_per_rep", 1)
        # Readout ii of each rep lives at di_buf[ch][ii::reads_per_rep]; the final
        # Ramsey readout is the last one in each rep (the earlier ones are resets).
        final = reads_per_rep - 1
        shots_i = self.di_buf[0][final::reads_per_rep].reshape((1, self.cfg["reps"])) / norm
        shots_q = self.dq_buf[0][final::reads_per_rep].reshape((1, self.cfg["reps"])) / norm
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
