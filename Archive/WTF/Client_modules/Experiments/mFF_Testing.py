from qick import *
# from socProxy import makeProxy
import matplotlib.pyplot as plt
import numpy as np
from qick.helpers import gauss
from WTF.Client_modules.CoreLib.Experiment import ExperimentClass
import datetime
from tqdm.notebook import tqdm
import time

class LoopbackProgramFF_Testing(AveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        cfg = self.cfg

        ffChannel = cfg["ff_ch"]
        self.declare_gen(ch=ffChannel, nqz=cfg["ff_nqz"])

        # style = self.cfg["ff_pulse_style"]

        ff_freq = self.freq2reg(cfg["ff_freq"],
                                   gen_ch=ffChannel)  # convert frequency to dac frequency (ensuring it is an available adc frequency)
        self.ff_freq = ff_freq
        # self.style = style
        length = self.us2cycles(cfg["length_us"], gen_ch=ffChannel)

        gencfg = self.soccfg['gens'][ffChannel]

        idata = np.zeros(length * 16)
        qdata = np.zeros(length * 16)

        ### define a gaussian
        gauss_length = 15
        sigma = 1
        for i in range(gauss_length):
            # idata[i] = np.exp(-( (i - gauss_length/2)**2/ (2*sigma**2) ))
            idata[i] = 1.0

        # idata = idata * gencfg['maxv'] * gencfg['maxv_scale']
        # idata = idata * (2**15 -2) * 1.0

        self.add_pulse(ch = ffChannel, name = "SF", idata = idata, qdata = qdata)

        #

        # sigma = self.us2cycles(0.005, gen_ch=ffChannel)
        # total_length = 4*sigma

        # sigma = 1
        # total_length = 3 * sigma
        # #
        # self.add_gauss(ch=ffChannel, name="SF", sigma=sigma, length=total_length)

        self.set_pulse_registers(ch=ffChannel, freq=0, style='arb',
                                 phase=0, gain=int(self.cfg["ff_gain"]),
                                 waveform="SF", outsel="input",
                                 # mode = "periodic",
                                 )

        self.synci(200)  # give processor some time to configure pulses

    def body(self):
        self.synci(200)  # give processor time to get ahead of the pulses

        self.pulse(ch=self.cfg["ff_ch"])

        self.sync_all(self.us2cycles(1))

    # def SFPulses(self, length_us, t_start = none, idata_pulse = False):
    #     length = self.us2cycles(length_us, gen_ch = ffChannel)

