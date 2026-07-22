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
from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.Program_Templates.AveragerProgramFF import FFAveragerProgramV2
from WorkingProjects.triangle_lattice_quench.Helpers.Compensated_Pulse_Josh import Compensated_Pulse

from WorkingProjects.triangle_lattice_quench.build_config import build_config
from WorkingProjects.triangle_lattice_quench.socProxy import makeProxy

soc, soccfg = makeProxy()


class ArbTone(FFAveragerProgramV2):

    def _initialize(self, cfg):
        for ch in cfg["channels"]:
            self.declare_gen(ch=ch)

            self.add_envelope(ch=ch, name=f"envelope{ch}", idata=cfg["IQArrays_dict"][ch])

            self.add_pulse(ch=ch, name=f'arb_pulse{ch}', style="arb", envelope=f"envelope{ch}",
                           freq=cfg["freq"], phase=0, gain=1, outsel='input')
            self.add_pulse(ch=ch, name=f'inv_arb_pulse{ch}', style="arb", envelope=f"envelope{ch}",
                           freq=cfg["freq"], phase=0, gain=-1, outsel='input')

    def _body(self, cfg):
        for ch in cfg["channels"]:
            self.pulse(ch, name=f'arb_pulse{ch}')
            self.pulse(ch, name=f'inv_arb_pulse{ch}')


    ## define the template config
    ################################# code for outputting a single cw tone

# ====================================================== #

class ArbTone_Experiment(ExperimentClass):
    """
    This experiment just sets the RFSOC to output a constant tone on a given chanel at a given frequency and gain.
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path,  prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False, debug=False):
        prog = ArbTone(self.soccfg, cfg=self.cfg, reps=self.cfg["reps"], final_delay=30)
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

    "channels": [0,4],  # TODO default value # 0-7 label the fast flux channels
    "IQArrays_dict": {} # populated below
}

TIME_US = 5
for ch in UpdateConfig["channels"]:
    qubit = ch+1
    arr = Compensated_Pulse(UpdateConfig["gain"], 0, qubit)
    num_samples = int(((TIME_US // 0.290e-3) + 15) // 16 * 16) # TIME_US/us_per_sample -> round to next 16
    UpdateConfig["IQArrays_dict"][ch] = arr[:num_samples]

print("Freq:", UpdateConfig["freq"])

config = UpdateConfig
outerFolder = ''

soc.reset_gens()
ArbTone_Instance = ArbTone_Experiment(path="dataTestConstPulse",  cfg=config, soc=soc, soccfg=soccfg)
try:
    ArbTone_Experiment.acquire(ArbTone_Instance)
except Exception:
    print("Pyro traceback:")
    print("".join(Pyro4.util.getPyroTraceback()))
ArbTone_Experiment.save_data(ArbTone_Instance)
ArbTone_Experiment.save_config(ArbTone_Instance)