from qick import *
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.CoreLib.Experiment import ExperimentClass


class ConstantTwoToneProg(AveragerProgram):
    def initialize(self):
        cfg = self.cfg
        cfg["nqz"] = 2

        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])

        f_res = self.freq2reg(cfg["pulse_freq"], gen_ch=cfg["res_ch"])
        f_qub = self.freq2reg(cfg["qubit_freq"], gen_ch=cfg["qubit_ch"])

        res_len = min(self.us2cycles(cfg["tone_length"], gen_ch=cfg["res_ch"]), 65535)
        qub_len = min(self.us2cycles(cfg["tone_length"], gen_ch=cfg["qubit_ch"]), 65535)

        self.set_pulse_registers(
            ch=cfg["res_ch"],
            style="const",
            freq=f_res,
            phase=0,
            gain=cfg["pulse_gain"],
            length=res_len
        )

        self.set_pulse_registers(
            ch=cfg["qubit_ch"],
            style="const",
            freq=f_qub,
            phase=0,
            gain=cfg["qubit_gain"],
            length=qub_len
        )

        self.synci(200)

    def body(self):
        self.pulse(ch=self.cfg["res_ch"])
        self.pulse(ch=self.cfg["qubit_ch"])
        self.sync_all()


class ConstantTwoTone(ExperimentClass):
    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data',
                 cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder,
                         prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False, debug=False):
        prog = ConstantTwoToneProg(self.soccfg, self.cfg)


        prog.acquire(self.soc)
        print("Started constant two-tone output:")
        print(f"  resonator: {self.cfg['pulse_freq']} MHz, gain {self.cfg['pulse_gain']}")
        print(f"  qubit:     {self.cfg['qubit_freq']} MHz, gain {self.cfg['qubit_gain']}")
        print(f"  tone_length: {self.cfg['tone_length']} us")

        print("pulse_freq =", self.cfg["pulse_freq"])
        print("res_ch =", self.cfg["res_ch"])
        print(self.cfg['nqz'])
        print("mixer_freq =", self.cfg.get("mixer_freq", None))
        print("cavity_LO =", self.cfg.get("cavity_LO", None))
        print("ro_chs =", self.cfg.get("ro_chs", None))

        return {
            "config": self.cfg,
            "data": {
                "res_freq_MHz": self.cfg["pulse_freq"],
                "res_gain": self.cfg["pulse_gain"],
                "qubit_freq_MHz": self.cfg["qubit_freq"],
                "qubit_gain": self.cfg["qubit_gain"],
                "tone_length_us": self.cfg["tone_length"],
            }
        }

    def display(self, data=None, plotDisp=False, figNum=1, **kwargs):
        pass

    def save_data(self, data=None):
        pass