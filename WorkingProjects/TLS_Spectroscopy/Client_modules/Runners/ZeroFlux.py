import numpy as np
from qick import AveragerProgram

from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.socProxy import makeProxy
from WorkingProjects.TLS_Spectroscopy.Client_modules.Calib.initialize import BaseConfig
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.pulse_setup import set_readout_pulse
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.acquisition import suppress_stdout


class FluxZero(AveragerProgram):

    def initialize(self):
        cfg = self.cfg
        cfg["reps"] = 10
        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"],
                         mixer_freq=cfg.get("mixer_freq", 0), ro_ch=cfg["ro_chs"][0])
        self.declare_gen(ch=cfg["ff_ch"], nqz=cfg.get("ff_nqz", 1))
        for ro in cfg["ro_chs"]:
            self.declare_readout(ch=ro, freq=cfg["read_pulse_freq"],
                                 length=self.us2cycles(cfg["read_length"], ro_ch=ro),
                                 gen_ch=cfg["res_ch"])
        set_readout_pulse(self, self.freq2reg(cfg["read_pulse_freq"],
                                              gen_ch=cfg["res_ch"],
                                              ro_ch=cfg["ro_chs"][0]), gain=500)
        self.synci(200)

    def body(self):
        cfg = self.cfg
        self.set_pulse_registers(ch=cfg["ff_ch"], freq=0, style="const", phase=0,
                                 stdysel="zero", gain=0,
                                 length=self.us2cycles(1.0, gen_ch=cfg["ff_ch"]))
        self.pulse(ch=cfg["ff_ch"])
        self.sync_all(self.us2cycles(1.0))
        self.measure(pulse_ch=cfg["res_ch"], adcs=cfg["ro_chs"],
                     adc_trig_offset=self.us2cycles(cfg["adc_trig_offset"]),
                     wait=True, syncdelay=self.us2cycles(10.0))


def main():
    ff_ch = BaseConfig["ff_ch"]
    print(f"initialize.py ff_park_gain = "
          f"{BaseConfig.get('ff_park_gain', 'KEY MISSING')!r}  (ignored here)")
    soc, soccfg = makeProxy()
    try:
        soc.reset_gens()
        print("soc.reset_gens() -> all generators zeroed")
    except Exception as exc:
        print(f"soc.reset_gens() unavailable ({type(exc).__name__})")
    cfg = dict(BaseConfig)
    cfg.update({"shots": 10, "reps": 10, "relax_delay": 10.0,
                "ff_park_gain": 0, "ff_gain": 0})
    with suppress_stdout():
        FluxZero(soccfg, cfg).acquire(soc, load_pulses=True, progress=False)
    print(f"FLUX ZEROED: ch {ff_ch} driven to 0 with stdysel='zero'")


if __name__ == "__main__":
    main()
