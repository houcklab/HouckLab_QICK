#### test experiments that use the fast flux in addition to standard measurements

#### import packages
import os
import h5py
import numpy as np

path = os.getcwd()
os.add_dll_directory(os.path.dirname(path)+'\\PythonDrivers')
from WTF.Client_modules.Calib.initialize import *
from WTF.Client_modules.Helpers.hist_analysis import *
from WTF.Client_modules.Helpers.MixedShots_analysis import *
from WTF.Client_modules.Helpers.MixedShots_analysis import *
from matplotlib import pyplot as plt
from sklearn.cluster import KMeans
import math

from WTF.Client_modules.Experiments.mSingleShotPS import SingleShotPS
from WTF.Client_modules.Experiments.mSingleShotPS_FF import SingleShotPS_FF
from WTF.Client_modules.Experiments.mFFPulse_WTF import FFPulse_WTF
from WTF.Client_modules.Experiments.mFFPulse_WTF_Sweep import FFPulse_WTF_Sweep
from WTF.Client_modules.Experiments.mGainReadOpt_wSingleShot import GainReadOpt_wSingleShot
from WTF.Client_modules.Experiments.mPiOpt_wSingleShot import PiOpt_wSingleShot
from WTF.Client_modules.Experiments.mT1_HalfFluxPS import T1_HalfFluxPS

#########################################################
def rotateBlob(i, q, theta):
    i_rot = i * np.cos(theta) - q * np.sin(theta)
    q_rot = i * np.sin(theta) + q * np.cos(theta)
    return i_rot, q_rot
##########################################################

#### define the saving path
outerFolder = "Z:\Shashwat\Data\Protomon\FMV8_TD\\"

# #### define the attenuators
# cavityAtten = attenuator(27787, attenuation_int= 35, print_int = False)


# Only run this if no proxy already exists
soc, soccfg = makeProxy()
# print(soccfg)

plt.ioff()

# #######################################################################################################################
###################################### code for running basic single shot exerpiment
UpdateConfig = {
    ### set flux point
    "yokoVoltage": 1.4, ###-0.128,
    ###### cavity
    # "reps": 2000,  # this will used for all experiements below unless otherwise changed in between trials
    "read_pulse_style": "const", # --Fixed
    "read_length": 10, # us
    "read_pulse_gain": 1000, # [DAC units]
    "read_pulse_freq": 5988.696, ### MHz
    ##### qubit spec parameters
    "qubit_pulse_style": "arb",
    "sigma": 0.100,  ### units us, define a 20ns sigma
    # "flat_top_length": 0.025, ### in us
    "qubit_gain": 8000,
    # "qubit_length": 4,  ###us, this is used if pulse style is const
    "qubit_freq": 1713.0,
    ##### define shots
    "shots": 5000, ### this gets turned into "reps"
    "relax_delay": 1000,  # us
}
config = BaseConfig | UpdateConfig

Instance_SingleShotPS = SingleShotPS(path="dataTestSingleShotPS", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg, progress=True)
data_SingleShotPS = SingleShotPS.acquire(Instance_SingleShotPS)
SingleShotPS.save_data(Instance_SingleShotPS, data_SingleShotPS)
SingleShotPS.save_config(Instance_SingleShotPS)
SingleShotPS.display(Instance_SingleShotPS, data_SingleShotPS, plotDisp=True)


#
# ####################################################################################################################
plt.show(block = True)
