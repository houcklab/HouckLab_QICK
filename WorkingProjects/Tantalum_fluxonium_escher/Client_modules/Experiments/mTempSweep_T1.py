#### code to monitor the qubit coherence while sweeping the temperature
#### code by default uses the post selection code for monitoring temperature
#### dynamically finds the qubit temperature at each temperature


from qick import *
import matplotlib.pyplot as plt
import numpy as np
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.CoreLib.Experiment import ExperimentClass
from tqdm.notebook import tqdm
import time
import datetime

import matplotlib.dates as mdates



from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mT1_PS import *
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.PythonDrivers.LS370 import *
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mQubitSpecRepeat import LoopbackProgramTwoToneFreqSweep


class TempSweep_T1(ExperimentClass):
    """
    sweep fridge temperature and monitor T1
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False, debug=False):


