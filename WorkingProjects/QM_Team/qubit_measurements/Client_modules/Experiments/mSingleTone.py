from qick import *
import matplotlib.pyplot as plt
import numpy as np
from qick.helpers import gauss
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.CoreLib.Experiment import ExperimentClass
import datetime
from tqdm.notebook import tqdm
import time

class ConstantTone(AveragerProgram):
    def initialize(self):
        cfg = self.cfg
        cfg['reps'] = 100000
        cfg['rounds'] = 1000
        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"], mixer_freq=cfg["mixer_freq"], ro_ch=cfg["ro_chs"][0])  # Readout
        freq = self.freq2reg(cfg["pulse_freq"], gen_ch=cfg["res_ch"],
                             ro_ch=cfg["ro_chs"][0])  # convert frequency to dac frequency (ensuring it is an available adc frequency)
        self.set_pulse_registers(ch=cfg["res_ch"], style="const", freq=freq, phase=0, gain=cfg["pulse_gain"],
                                 length=self.us2cycles(cfg["length"]))
        self.synci(200)  # give processor some time to configure pulses

    def body(self):
        self.pulse(ch = self.cfg["res_ch"])
        self.sync_all()
        print('oh yeah')

    # ====================================================== #

class SingleTone(ExperimentClass):
    """
    Transmission Experiment basic
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False):
        for i in range(100):
            prog = ConstantTone(self.soccfg, self.cfg)
            a, b = prog.acquire(self.soc, load_pulses=True)

    def display(self, data=None, plotDisp = False, figNum = 1, **kwargs):
        pass

    def save_data(self, data=None):
        pass






