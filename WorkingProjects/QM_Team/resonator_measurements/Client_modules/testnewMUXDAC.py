# Import the QICK drivers and auxiliary libraries
from qick import *
import time
from socProxy import makeProxy

# Only run this if no proxy already exists
soc, soccfg = makeProxy('192.168.1.103')
print(soccfg)

class LoopbackProgram(AveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        cfg = self.cfg
        self.declare_gen(ch=cfg["res_ch"], nqz=1,
                         mixer_freq=cfg["mixer_freq"],
                         mux_freqs=cfg["pulse_freqs"],
                         mux_gains=cfg["pulse_gains"],
                         ro_ch=cfg["ro_chs"][0])
        for iCh, ch in enumerate(cfg["ro_chs"]):  # configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, freq=cfg["pulse_freqs"][iCh], length=cfg["readout_length"],
                                 gen_ch=cfg["res_ch"])

        self.set_pulse_registers(ch=cfg["res_ch"], style="const", length=cfg["length"], mask=[0, 1, 2, 3])
        self.synci(200)  # give processor some time to configure pulses

    def body(self):
        self.synci(200)  # give processor time to get ahead of the pulses
        self.trigger(adcs=self.ro_chs, pins=[0],
                     adc_trig_offset=self.cfg["adc_trig_offset"])  # trigger the adc acquisition
        self.pulse(ch=self.cfg["res_ch"], t=0)

        # control should wait until the readout is over
        self.waiti(0, self.cfg["adc_trig_offset"] + self.cfg["readout_length"])
        self.sync_all(self.us2cycles(self.cfg["relax_delay"]))  # sync all channels


config = {"res_ch": 6,  # --Fixed
          "mixer_freq": 1000.0,  # MHz
          "ro_chs": [0, 1, 2, 3],  # --Fixed
          "reps": 1,  # --Fixed
          "relax_delay": 10,  # --Fixed
          "pulse_style": "const",  # --Fixed

          "length": 2 ** 31 - 1,  # [Clock ticks]
          # Try varying length from 10-100 clock ticks

          "readout_length": 300,  # [Clock ticks]
          # Try varying readout_length from 50-1000 clock ticks

          "pulse_freqs": [100.0005001, 300, 500, 700],  # [MHz]
          # In this program the signal is up and downconverted digitally so you won't see any frequency
          # components in the I/Q traces below. But since the signal gain depends on frequency,
          # if you lower pulse_freq you will see an increased gain.

          "pulse_gains": [1.0, 0.01, 1, 1],

          "adc_trig_offset": 50,  # [Clock ticks]
          # Try varying adc_trig_offset from 100 to 220 clock ticks

          "soft_avgs": 100
          # Try varying soft_avgs from 1 to 200 averages
          }

###################
# Try it yourself !
###################

prog = LoopbackProgram(soccfg, config)
iq_list = prog.acquire_decimated(soc, load_pulses=True, progress=True, debug=False)
# print(prog)