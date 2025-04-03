from qick import *
from socProxy import makeProxy
import matplotlib.pyplot as plt
import numpy as np
from qick.helpers import gauss
from Experiment import ExperimentClass
import datetime
from tqdm.notebook import tqdm
import time



class MuxProgram(AveragerProgram):
    def __init__(self,soccfg,cfg):
        super().__init__(soccfg,cfg)

    def initialize(self):
        cfg=self.cfg
        self.declare_gen(ch=cfg["res_ch"], nqz=1, mixer_freq=cfg["mixer_freq"], mux_freqs=cfg["pulse_freqs"], ro_ch=cfg["ro_chs"][0])
        for iCh, ch in enumerate(cfg["ro_chs"]): #configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, freq=cfg["pulse_freqs"][iCh], length=cfg["readout_length"], gen_ch=cfg["res_ch"])

        self.set_pulse_registers(ch=cfg["res_ch"], style="const", length=cfg["length"], mask=cfg["ro_chs"], gain = 3000)
        self.synci(200)  # give processor some time to configure pulses

    def body(self):
        self.synci(200) # give processor time to get ahead of the pulses
        self.trigger(adcs=self.ro_chs, pins=[0],adc_trig_offset=self.cfg["adc_trig_offset"])  # trigger the adc acquisition
        self.pulse(ch=self.cfg["res_ch"],t=0)

        # control should wait until the readout is over
        self.waiti(0, self.cfg["adc_trig_offset"]+self.cfg["readout_length"])
        self.sync_all(self.us2cycles(self.cfg["relax_delay"]))  # sync all channels



