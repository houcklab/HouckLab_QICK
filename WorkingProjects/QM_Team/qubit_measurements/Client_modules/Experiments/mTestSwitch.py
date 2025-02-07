from qick import *
import matplotlib.pyplot as plt
import numpy as np
from qick.helpers import gauss
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.CoreLib.Experiment import ExperimentClass
import datetime
from tqdm.notebook import tqdm
import time

class Switch(AveragerProgram):
    def initialize(self):
        cfg = self.cfg

        f_ge = self.freq2reg(cfg["f_ge"], gen_ch=cfg["qubit_ch"])
        self.pulse_sigma = self.us2cycles(cfg["sigma"], gen_ch=self.cfg["qubit_ch"])
        self.pulse_qubit_lenth = self.us2cycles(cfg["sigma"] * 4, gen_ch=self.cfg["qubit_ch"])
        if cfg["flattop_length"] != None:
            flattop_length = self.us2cycles(self.cfg["flattop_length"], gen_ch=self.cfg["qubit_ch"])
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                           sigma=self.pulse_sigma,
                           length=self.pulse_qubit_lenth)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style='flat_top', freq=f_ge,
                                     phase=self.deg2reg(0, gen_ch=cfg["qubit_ch"]), gain=cfg["qubit_gain"],
                                     waveform="qubit",
                                     length=flattop_length)  # Flat part of flattop does NOT update with gain
            self.pulse_qubit_lenth += flattop_length
        else:
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                           sigma=self.pulse_sigma, length=self.pulse_qubit_lenth)

            self.set_pulse_registers(ch=cfg["qubit_ch"], style="arb", freq=f_ge,
                                     phase=self.deg2reg(0, gen_ch=cfg["qubit_ch"]), gain=cfg["qubit_gain"],
                                     waveform="qubit")
        self.trig_length = self.us2cycles((cfg["trig_buffer_start"] + cfg["trig_buffer_end"] + cfg["sigma"] * 4))
        if cfg["flattop_length"] != None:
            self.trig_length += self.us2cycles((cfg["flattop_length"]))

        self.synci(200)  # give processor some time to configure pulses

    def body(self):
        self.sync_all()
        print(self.trig_length)
        self.trigger(pins = [0], t = self.us2cycles(self.cfg["trig_delay"] - self.cfg["trig_buffer_start"]), width = self.trig_length)
        self.pulse(ch = self.cfg["qubit_ch"], t = self.us2cycles(self.cfg['pulse_start_time']))

        self.sync_all(self.us2cycles(self.cfg["relax_delay"]))

    # ====================================================== #

class SwitchTest(ExperimentClass):
    """
    Transmission Experiment basic
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False):
        for i in range(100):
            prog = Switch(self.soccfg, self.cfg)
            a, b = prog.acquire(self.soc, load_pulses=True)

    def display(self, data=None, plotDisp = False, figNum = 1, **kwargs):
        pass

    def save_data(self, data=None):
        pass






