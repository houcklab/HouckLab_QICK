### This experiment just outputs a constant tone on a given chanel at a given frequency and gain.
# Note that the RFSOC will continue playing the tone after the experiment is complete, until THIS CHANNEL
# is told to play something else, e.g. if we play a tone on channel 1, then run this experiment for channel 0,
# both channel 1 AND channel 0 will continue playing their respective tones.

from qick import AveragerProgram
# from WorkingProjects.QM_Team.qubit_measurements.Client_modules.CoreLib.Experiment import ExperimentClass
import Pyro4.util

# from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Calib.initialize4Q_2QGates import *
import time
import numpy as np
from qick.asm_v2 import AveragerProgramV2
from scipy.optimize import curve_fit
import matplotlib.pyplot as plt
# from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Helpers.SQ_RB_Helpers import *
from WorkingProjects.triangle_lattice_quench.Experiment import ExperimentClass

from WorkingProjects.triangle_lattice_quench.socProxy import makeProxy



soc, soccfg = makeProxy()



class ConstantTone(AveragerProgramV2):

    def _initialize(self, cfg):
        for ch in cfg["channels"]:
            self.declare_gen(ch=ch)

            self.add_pulse(ch=ch, name=f'flat_pulse{ch}', style="const", freq=cfg["freq"],
                           phase=0, gain=cfg["gain"] / 32766.,  length=cfg["length"])
            self.add_pulse(ch=ch, name=f'inv_flat_pulse{ch}', style="const", freq=cfg["freq"],
                           phase=0, gain=cfg["gain"] / -32766., length=cfg["length"])

        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"],
                         mixer_freq=cfg["mixer_freq"])  # Qubit

        self.add_pulse(ch=cfg["qubit_ch"], name='qubit_drive', style="const", freq=cfg["qubit_freq"],
                       phase=0, gain=cfg["qubit_gain"] / 32766., length=cfg['qubit_length'])

    def _body(self, cfg):
        self.pulse(self.cfg["qubit_ch"], name='qubit_drive')  # play probe pulse
        for ch in cfg["channels"]:
            self.pulse(ch, name=f'flat_pulse{ch}')
            self.pulse(ch, name=f'inv_flat_pulse{ch}')


    ## define the template config
    ################################# code for outputting a single cw tone

# ====================================================== #

class ConstantTone_Experiment(ExperimentClass):
    """
    This experiment just sets the RFSOC to output a constant tone on a given chanel at a given frequency and gain.
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path,  prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False, debug=False):
        prog = ConstantTone(self.soccfg, cfg=self.cfg, reps=self.cfg["reps"], final_delay=30)
        prog.run_rounds(self.soc,rounds=self.cfg['rounds'])

    def display(self, data=None, plotDisp = False, figNum = 1, **kwargs):
        pass

    def save_data(self, data=None):
        pass


UpdateConfig = {
    ###### cavity
    "read_pulse_style": "const",  # --Fixed
    "gain": 20000,  # [DAC units]
    "reps": 100000,
    "rounds":12000,
    # "qubit_LO_freq": 5000,
    "freq": 0, # [MHz] Leave as zero for flat pulse
    "length": 0.050,

    "channels": [0],  # TODO default value # 0-7 label the fast flux channels
}

QubitConfig = {
    "qubit_gain": 32000,  # [DAC units]
    "mixer_freq": 4000,
    "qubit_freq": 4000, # [MHz]
    "qubit_length": 0.023,

    "qubit_ch": 9, #0,  # TODO default value # 8 is resonator, 9 is qubit
    "qubit_nqz": 2, #2,#1,  # TODO default value
}

print("Freq:", UpdateConfig["freq"])

config = UpdateConfig | QubitConfig
outerFolder = ''

soc.reset_gens()
ConstantTone_Instance = ConstantTone_Experiment(path="dataTestConstPulse",  cfg=config, soc=soc, soccfg=soccfg)
try:
    ConstantTone_Experiment.acquire(ConstantTone_Instance)
except Exception:
    print("Pyro traceback:")
    print("".join(Pyro4.util.getPyroTraceback()))
# ConstantTone_Experiment.save_data(ConstantTone_Instance)
# ConstantTone_Experiment.save_config(ConstantTone_Instance)