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
outerFolder = "Z:\JakeB\Data\WTF01_A2_RFSOC\\"

#### define the attenuators
cavityAtten = attenuator(27787, attenuation_int= 35, print_int = False)


# Only run this if no proxy already exists
soc, soccfg = makeProxy()
# print(soccfg)

plt.ioff()

# #######################################################################################################################
#### testing out post selection protocol on h state
UpdateConfig = {
    ##### define attenuators
    "cav_Atten": 17,  #### cavity attenuator attenuation value
    "yokoVoltage": -0.6917,
    ###### cavity
    "read_pulse_style": "const", # --Fixed
    "read_length": 2, # us
    "read_pulse_gain": 1700, # [DAC units]
    "read_pulse_freq": 892.9, # [MHz] actual frequency is this number + "cavity_LO"
    ##### spec parameters for finding the qubit frequency
    "qubit_freq": 2855.0,
    "qubit_gain": 30000,
    "qubit_pulse_style": "flat_top",
    "sigma": 0.005,  ### units us, define a 20ns sigma
    "flat_top_length": 0.040,  ### in us
    "relax_delay": 1500,  ### turned into us inside the run function
    ##### fast flux parameters
    "ff_gain": 20000,
    "ff_length": 140, ### multiplied by 12
    ###### single shot parameters
    "shots": 20000,
}

config = BaseConfig | UpdateConfig

yoko1.SetVoltage(config["yokoVoltage"])

#### acquire the single shot data with post selection
Instance_SingleShotPS_FF = SingleShotPS_FF(path="dataTestSingleShotPS_FF", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
data_SingleShotPS_FF = SingleShotPS_FF.acquire(Instance_SingleShotPS_FF)
SingleShotPS_FF.display(Instance_SingleShotPS_FF, data_SingleShotPS_FF, plotDisp=True, figNum=1)

SingleShotPS_FF.save_data(Instance_SingleShotPS_FF, data_SingleShotPS_FF)
SingleShotPS_FF.save_config(Instance_SingleShotPS_FF)


### testing out post selection protocol on f state
UpdateConfig = {
    ##### define attenuators
    "cav_Atten": 17,  #### cavity attenuator attenuation value
    "yokoVoltage": -0.6917,
    ###### cavity
    "read_pulse_style": "const", # --Fixed
    "read_length": 2, # us
    "read_pulse_gain": 1700, # [DAC units]
    "read_pulse_freq": 892.9, # [MHz] actual frequency is this number + "cavity_LO"
    ##### spec parameters for finding the qubit frequency
    "qubit_freq": 5615,
    "qubit_gain": 3600,
    "qubit_pulse_style": "flat_top",
    "sigma": 0.005,  ### units us, define a 20ns sigma
    "flat_top_length": 0.020,  ### in us
    "relax_delay": 1500,  ### turned into us inside the run function
    ##### fast flux parameters
    "ff_gain": 20000,
    "ff_length": 140, ### multiplied by 12
    ###### single shot parameters
    "shots": 20000,
}

config = BaseConfig | UpdateConfig

yoko1.SetVoltage(config["yokoVoltage"])

#### acquire the single shot data with post selection
Instance_SingleShotPS_FF = SingleShotPS_FF(path="dataTestSingleShotPS_FF", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
data_SingleShotPS_FF = SingleShotPS_FF.acquire(Instance_SingleShotPS_FF)
SingleShotPS_FF.display(Instance_SingleShotPS_FF, data_SingleShotPS_FF, plotDisp=True, figNum=2)

SingleShotPS_FF.save_data(Instance_SingleShotPS_FF, data_SingleShotPS_FF)
SingleShotPS_FF.save_config(Instance_SingleShotPS_FF)


#######################################################################################################################
#### testing out post selection protocol with FF
UpdateConfig = {
    ##### define attenuators
    "cav_Atten": 7,  #### cavity attenuator attenuation value
    "yokoVoltage": -0.6917,
    ### define the yoko Sweep parameters
    "yokoVoltageStart": -0.6920 - 0.004,
    "yokoVoltageStop": -0.6920 + 0.006,
    "yokoVoltageNumPoints": 21,
    "WTF_avgs": 10,
    ###### cavity
    # "reps": 2000,  # this will used for all experiements below unless otherwise changed in between trials
    "read_pulse_style": "const", # --Fixed
    "read_length": 2, # us (length of the pulse applied)
    "read_pulse_gain": 1700, # [DAC units]
    "read_pulse_freq": 892.9, # [MHz] actual frequency is this number + "cavity_LO"
    ##### qubit spec parameters
    # "qubit_pulse_style": "flat_top",
    # "qubit_gain": 27000,
    # "qubit_length": 10,  ###us, this is used if pulse style is const
    # "sigma": 0.005,  ### units us, define a 20ns sigma
    # "flat_top_length": 0.015,
    # "qubit_freq": 5018.0,
    "qubit_pulse_style": "flat_top",
    "sigma": 0.005,  ### units us, define a 20ns sigma
    "flat_top_length": 0.025,
    "qubit_freq": 5023.0,
    "qubit_gain": 18000,
    ##### define shots
    "shots": 20000, ### this gets turned into "reps"
    "relax_delay": 500,  # us
    ##### define flux pulse parameters
    "ff_gain": 20000,
    "ff_length": 140, ### multiplied by 12
}

config = BaseConfig | UpdateConfig

yoko1.SetVoltage(config["yokoVoltage"])

#### acquire the single shot data with post selection
Instance_SingleShotPS_FF = SingleShotPS_FF(path="dataTestSingleShotPS_FF", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
data_SingleShotPS_FF = SingleShotPS_FF.acquire(Instance_SingleShotPS_FF)
SingleShotPS_FF.display(Instance_SingleShotPS_FF, data_SingleShotPS_FF, plotDisp=True, figNum=10)

SingleShotPS_FF.save_data(Instance_SingleShotPS_FF, data_SingleShotPS_FF)
SingleShotPS_FF.save_config(Instance_SingleShotPS_FF)
#
# #### acquire the flux pulse from half flux data
# config["shots"] = 5000
# Instance_FFPulse_WTF = FFPulse_WTF(path="dataTestFFPulse_WTF", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
# data_FFPulse_WTF = FFPulse_WTF.acquire(Instance_FFPulse_WTF)
#
# # FFPulse_WTF.display_process(Instance_FFPulse_WTF, calibData = data_SingleShotPS_FF)
#
# FFPulse_WTF.display(Instance_FFPulse_WTF, data_FFPulse_WTF, plotDisp=True, figNum=5)
#
# # FFPulse_WTF.save_data(Instance_FFPulse_WTF, data_FFPulse_WTF)
# # FFPulse_WTF.save_config(Instance_FFPulse_WTF)

# #
# #### acquire the flux pulse from half flux data
config["shots"] = 20000
Instance_FFPulse_WTF_Sweep = FFPulse_WTF_Sweep(path="dataTestFFPulse_WTF", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
data_FFPulse_WTF_Sweep = FFPulse_WTF_Sweep.acquire(Instance_FFPulse_WTF_Sweep, calibData = data_SingleShotPS_FF)
# FFPulse_WTF_Sweep.display(Instance_FFPulse_WTF_Sweep, data_FFPulse_WTF_Sweep, plotDisp=True, figNum=101)

FFPulse_WTF_Sweep.save_data(Instance_FFPulse_WTF_Sweep, data_FFPulse_WTF_Sweep)
FFPulse_WTF_Sweep.save_config(Instance_FFPulse_WTF_Sweep)
# #
######################################################################################################################
UpdateConfig = {
    ##### define attenuators starting values
    "qubit_Atten": 0,  ### qubit attenuator value
    "cav_Atten": 17,  #### cavity attenuator attenuation value
    "yokoVoltage": -0.6917,
    ###### cavity
    # "reps": 2000,  # this will used for all experiements below unless otherwise changed in between trials
    "read_pulse_style": "const", # --Fixed
    "read_length": 2, # us (length of the pulse applied)
    "read_pulse_gain": 1700, # [DAC units]
    "read_pulse_freq": 892.9, # [MHz] actual frequency is this number + "cavity_LO"
    ##### qubit spec parameters
    "qubit_pulse_style": "flat_top",
    "sigma": 0.005,  ### units us, define a 20ns sigma
    "flat_top_length": 0.025, ### in us
    ##### define qubit freq array
    "qubit_freq_start": 5020.0,
    "qubit_freq_stop": 5030.0,
    "qubit_freq_num": 11,  ### number of points
    ##### define the  gain array
    "qubit_gain_start": 18000,
    "qubit_gain_stop": 23000,
    "qubit_gain_num": 11,  ### number of points
    ##### give basic parameters
    "shots": 4000,
    "relax_delay": 100, # us
    ##### define flux pulse parameters
    "ff_gain": 20000,
    "ff_length": 140,  ### multiplied by 12
}
config = BaseConfig | UpdateConfig

# yoko1.SetVoltage(config["yokoVoltage"])
#
# Instance_PiOpt_wSingleShot = PiOpt_wSingleShot(path="dataTestPiOpt_wSingleShot", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
# data_PiOpt_wSingleShot = PiOpt_wSingleShot.acquire(Instance_PiOpt_wSingleShot, FF_PS = True)
# PiOpt_wSingleShot.save_data(Instance_PiOpt_wSingleShot, data_PiOpt_wSingleShot)
# PiOpt_wSingleShot.save_config(Instance_PiOpt_wSingleShot)


UpdateConfig = {
    ##### define yoko value
    "yokoVoltage": -0.6925,
    ##### change cavity gain
    "trans_gain_start": 1000,
    "trans_gain_stop": 2000,
    "trans_gain_num": 21,
    ###### cavity
    # "reps": 2000,  # this will used for all experiements below unless otherwise changed in between trials
    "read_pulse_style": "const", # --Fixed
    "read_length": 2, # us (length of the pulse applied)
    # "read_pulse_gain": 10000,  # [DAC units]
    "trans_freq_start": 892.0,  # [MHz] actual frequency is this number + "cavity_LO"
    "trans_freq_stop": 893.5,  # [MHz] actual frequency is this number + "cavity_LO"
    "TransNumPoints": 31,  ### number of points in the transmission frequecny
    ##### qubit spec parameters
    "qubit_pulse_style": "flat_top",
    "sigma": 0.005,  ### units us, define a 20ns sigma
    "flat_top_length": 0.010, ### in us
    "qubit_gain": 7220,
    "qubit_length": 4,  ###us, this is used if pulse style is const
    "qubit_freq": 5020.0,
    ##### give basic parameters
    "shots": 5000,
    "relax_delay": 100, # us
    ##### define flux pulse parameters
    "ff_gain": 20000,
    "ff_length": 140,  ### multiplied by 12
}
config = BaseConfig | UpdateConfig

# yoko1.SetVoltage(config["yokoVoltage"])
#
# ##### run the actual experiment
# Instance_GainReadOpt_wSingleShot = GainReadOpt_wSingleShot(path="dataTestGainReadOpt_wSingleShot", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
# data_GainReadOpt_wSingleShot = GainReadOpt_wSingleShot.acquire(Instance_GainReadOpt_wSingleShot, FF_PS = True)
# GainReadOpt_wSingleShot.save_data(Instance_GainReadOpt_wSingleShot, data_GainReadOpt_wSingleShot)
# GainReadOpt_wSingleShot.save_config(Instance_GainReadOpt_wSingleShot)



### testing out post selection protocol with FF
UpdateConfig = {
    ##### define attenuators
    "yokoVoltage": -0.6917,
    ###### cavity
    "read_pulse_style": "const", # --Fixed
    "read_length": 2, # us (length of the pulse applied)
    "read_pulse_gain": 1600, # [DAC units]
    "read_pulse_freq": 892.9, # [MHz] actual frequency is this number + "cavity_LO"
    ##### define shots
    "shots": 10000, ### this gets turned into "reps"
    "relax_delay": 100,  # us
    ### define the wait times
    "wait_start": 0,
    "wait_stop": 40, ### us
    "wait_num": 81,
}

config = BaseConfig | UpdateConfig

# yoko1.SetVoltage(config["yokoVoltage"])
#
# #### acquire the flux pulse from half flux data
# Instance_T1_HalfFluxPS = T1_HalfFluxPS(path="dataTestT1_HalfFluxPS", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
# data_T1_HalfFluxPS = T1_HalfFluxPS.acquire(Instance_T1_HalfFluxPS)
# T1_HalfFluxPS.display(Instance_T1_HalfFluxPS, data_T1_HalfFluxPS, plotDisp=True, figNum=5)
#
# T1_HalfFluxPS.save_data(Instance_T1_HalfFluxPS, data_T1_HalfFluxPS)
# T1_HalfFluxPS.save_config(Instance_T1_HalfFluxPS)

#
# ####################################################################################################################
plt.show(block = True)
