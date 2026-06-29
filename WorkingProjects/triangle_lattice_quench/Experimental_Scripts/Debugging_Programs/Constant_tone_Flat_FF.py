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

from WorkingProjects.triangle_lattice_quench.MUXInitialize import soc, soccfg


class ConstantTone(AveragerProgramV2):

    def _initialize(self, cfg):
        for ch in cfg["channels"]:
            self.declare_gen(ch=ch)

            self.add_pulse(ch=ch, name=f'flat_pulse{ch}', style="const", freq=cfg["freq"],
                           phase=0, gain=cfg["gain"] / 32766.,  length=20)
            self.add_pulse(ch=ch, name=f'inv_flat_pulse{ch}', style="const", freq=cfg["freq"],
                           phase=0, gain=cfg["gain"] / -32766., length=20)

    def _body(self, cfg):
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
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False, debug=False):
        prog = ConstantTone(self.soccfg, cfg=self.cfg, reps=self.cfg["reps"], final_delay=0)
        prog.run_rounds(self.soc,rounds=self.cfg['rounds'])

    def display(self, data=None, plotDisp = False, figNum = 1, **kwargs):
        pass

    def save_data(self, data=None):
        pass


UpdateConfig = {
    ###### cavity
    "read_pulse_style": "const",  # --Fixed
    "gain": 32000,  # [DAC units]
    "reps": 100000,
    "rounds":12000,
    # "qubit_LO_freq": 5000,
    "freq": 0, # [MHz] Leave as zero for flat pulse

    "channels": [1],  # TODO default value # 0-7 label the fast flux channels
}
print("Freq:", UpdateConfig["freq"])

config = UpdateConfig
outerFolder = ''

soc.reset_gens()
ConstantTone_Instance = ConstantTone_Experiment(path="dataTestConstPulse", outerFolder=outerFolder, cfg=config, soc=soc, soccfg=soccfg)
try:
    ConstantTone_Experiment.acquire(ConstantTone_Instance)
except Exception:
    print("Pyro traceback:")
    print("".join(Pyro4.util.getPyroTraceback()))
ConstantTone_Experiment.save_data(ConstantTone_Instance)
ConstantTone_Experiment.save_config(ConstantTone_Instance)