import time

from qick import QickProgram

from qicklab.core.experiment import ExperimentClass

# A periodic const pulse is repeated by the generator itself, back to back, until another pulse
# is queued on that generator (or soc.reset_gens()). With phrst = 0 the DDS phase runs on, so
# the output is a true CW tone and its length only sets the repetition period.
# docs/experiments/cw_tones.md.


def stop_tones(soc):
    """Silence every generator (soc.reset_gens()): the only thing that stops a periodic tone."""
    soc.reset_gens()


def wait_for_stop(hold_s=None):
    """Block while the armed CW tones play: until Enter (hold_s=None) or for hold_s seconds.

    The caller stops the tones with stop_tones(soc) in a finally, so Ctrl-C stops them too
    (and propagates). With no usable stdin (EOF, or a captured stdin as under pytest) and
    hold_s=None this returns at once with a warning, so the tones are stopped at once.
    """
    if hold_s is None:
        try:
            input(">>> CW TONES ARE ON. Press Enter to stop them (Ctrl-C also stops them). ")
        except (EOFError, OSError):
            print(
                "WARNING: no interactive stdin to wait on: stopping the CW tones now. "
                "Pass hold_s=<seconds> (params={'hold_s': ...}) to hold them."
            )
    else:
        print(f">>> CW TONES ARE ON for {hold_s} s (Ctrl-C stops them early).")
        time.sleep(hold_s)


class _CWProgram(QickProgram):
    """One periodic const pulse per generator, then end: no loop, no readout."""

    def __init__(self, soccfg, cfg):
        super().__init__(soccfg)
        self.cfg = cfg
        self.initialize()
        self.end()

    def _declare_res(self):
        """Resonator gen declared and its frequency rounded as Transmission does (mixer, ro_ch)."""
        cfg = self.cfg
        self.declare_gen(
            ch=cfg["res_ch"], nqz=cfg["nqz"], mixer_freq=cfg["mixer_freq"], ro_ch=cfg["ro_chs"][0]
        )
        return self.freq2reg(cfg["pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])

    def _periodic(self, ch, freq, gain, length):
        self.set_pulse_registers(
            ch=ch,
            style="const",
            freq=freq,
            phase=0,
            gain=gain,
            length=length,
            mode="periodic",
            phrst=0,
        )
        self.pulse(ch=ch, t=0)


class ConstantTwoToneProg(_CWProgram):
    def initialize(self):
        cfg = self.cfg

        f_res = self._declare_res()
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])
        f_qub = self.freq2reg(cfg["qubit_freq"], gen_ch=cfg["qubit_ch"])

        # Repetition period only (the output is continuous); 16-bit length register:
        # docs/concepts/timing_and_units.md#pulse-envelopes
        res_len = min(self.us2cycles(cfg["tone_length"], gen_ch=cfg["res_ch"]), 65535)
        qub_len = min(self.us2cycles(cfg["tone_length"], gen_ch=cfg["qubit_ch"]), 65535)

        print("Qubit Gain for constant two tone: ", cfg["qubit_gain"])
        print("Resonator Gain for constant two tone: ", cfg["pulse_gain"])

        self._periodic(cfg["res_ch"], f_res, cfg["pulse_gain"], res_len)
        self._periodic(cfg["qubit_ch"], f_qub, cfg["qubit_gain"], qub_len)


class ConstantTwoTone(ExperimentClass):
    """CW resonator + qubit tones (no readout), held until Enter / hold_s, then stopped.

    docs/experiments/cw_tones.md."""

    def __init__(
        self,
        soc=None,
        soccfg=None,
        path="",
        outerFolder="",
        prefix="data",
        cfg=None,
        config_file=None,
        progress=None,
    ):
        super().__init__(
            soc=soc,
            soccfg=soccfg,
            path=path,
            outerFolder=outerFolder,
            prefix=prefix,
            cfg=cfg,
            config_file=config_file,
            progress=progress,
        )

    def acquire(self, progress=False, debug=False, hold_s=None):
        prog = ConstantTwoToneProg(self.soccfg, self.cfg)

        try:
            prog.run(self.soc)  # config_all, start_src("internal"), start_tproc

            print("Started CW two-tone output:")
            print(f"  resonator: {self.cfg['pulse_freq']} MHz, gain {self.cfg['pulse_gain']}")
            print(f"  qubit:     {self.cfg['qubit_freq']} MHz, gain {self.cfg['qubit_gain']}")
            print(f"  tone_length (repetition period): {self.cfg['tone_length']} us")

            print("pulse_freq =", self.cfg["pulse_freq"])
            print("res_ch =", self.cfg["res_ch"])
            print(self.cfg["nqz"])
            print("mixer_freq =", self.cfg.get("mixer_freq", None))
            print("cavity_LO =", self.cfg.get("cavity_LO", None))
            print("ro_chs =", self.cfg.get("ro_chs", None))
            wait_for_stop(hold_s)
        finally:
            stop_tones(self.soc)
            print(">>> CW tones stopped (soc.reset_gens()).")

        return {
            "config": self.cfg,
            "data": {
                "res_freq_MHz": self.cfg["pulse_freq"],
                "res_gain": self.cfg["pulse_gain"],
                "qubit_freq_MHz": self.cfg["qubit_freq"],
                "qubit_gain": self.cfg["qubit_gain"],
                "tone_length_us": self.cfg["tone_length"],
            },
        }

    def display(self, data=None, plotDisp=False, figNum=1, **kwargs):
        pass

    def save_data(self, data=None):
        pass


class ConstantTone(_CWProgram):
    def initialize(self):
        cfg = self.cfg
        freq = self._declare_res()
        # Repetition period only (the output is continuous).
        self._periodic(
            cfg["res_ch"],
            freq,
            cfg["pulse_gain"],
            self.us2cycles(cfg["length"], gen_ch=cfg["res_ch"]),
        )


class SingleTone(ExperimentClass):
    """CW resonator tone (no readout), held until Enter / hold_s, then stopped;
    docs/experiments/cw_tones.md."""

    def __init__(
        self,
        soc=None,
        soccfg=None,
        path="",
        outerFolder="",
        prefix="data",
        cfg=None,
        config_file=None,
        progress=None,
    ):
        super().__init__(
            soc=soc,
            soccfg=soccfg,
            path=path,
            outerFolder=outerFolder,
            prefix=prefix,
            cfg=cfg,
            config_file=config_file,
            progress=progress,
        )

    def acquire(self, progress=False, hold_s=None):
        prog = ConstantTone(self.soccfg, self.cfg)
        try:
            prog.run(self.soc)  # config_all, start_src("internal"), start_tproc
            print(
                f"Started CW resonator tone: {self.cfg['pulse_freq']} MHz, "
                f"gain {self.cfg['pulse_gain']}"
            )
            wait_for_stop(hold_s)
        finally:
            stop_tones(self.soc)
            print(">>> CW tones stopped (soc.reset_gens()).")

    def display(self, data=None, plotDisp=False, figNum=1, **kwargs):
        pass

    def save_data(self, data=None):
        pass
