#### import packages
import os

import numpy as np

os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
from WTF.Client_modules.Calib.initialize import *
from matplotlib import pyplot as plt
from Calib.initialize import *
from Helpers.hist_analysis import *
from Experiments.mTransmission import Transmission
from Experiments.mSpecSlice import SpecSlice
from Experiments.mSingleShotProgram import SingleShotProgram
from Experiments.mSingleShotProgramFF import SingleShotProgramFF
from Experiments.mReadOpt_wSingleShot import ReadOpt_wSingleShot
from Experiments.mGainReadOpt_wSingleShot import GainReadOpt_wSingleShot
from Experiments.mPiOpt_wSingleShot import PiOpt_wSingleShot

#### define the saving path
outerFolder = "Z:\JakeB\Data\WTF01_A2_RFSOC\\"

#### define the attenuators
cavityAtten = attenuator(27787, attenuation_int= 35, print_int = False)
#####qubitAtten = attenuator(27797, attenuation_int= 10, print_int = False)


#################################### Running the actual experiments

# Only run this if no proxy already exists
soc, soccfg = makeProxy()
# print(soccfg)

plt.ioff()

###################################### code for running basic single shot exerpiment
UpdateConfig = {
    ##### define attenuators
    "qubit_Atten": 0,  ### qubit attenuator value
    "cav_Atten": 16,  #### cavity attenuator attenuation value
    "yokoVoltage": -0.715, ###-0.128,
    ###### cavity
    "reps": 2000,  # this will used for all experiements below unless otherwise changed in between trials
    "read_pulse_style": "const", # --Fixed
    "read_length": 2, # us (length of the pulse applied)
    "read_pulse_gain": 1500, # [DAC units]
    "read_pulse_freq": 892.8, # [MHz] actual frequency is this number + "cavity_LO"
    ##### qubit spec parameters
    "qubit_pulse_style": "flat_top",
    "sigma": 0.015,  ### units us, define a 20ns sigma
    "flat_top_length": 0.025, ### in us
    "qubit_gain": 16500*0,
    "qubit_length": 4,  ###us, this is used if pulse style is const
    "qubit_freq": 4951.0,
    ##### define shots
    "shots": 5000, ### this gets turned into "reps"
    "relax_delay": 10,  # us
}
config = BaseConfig | UpdateConfig

# yoko1.SetVoltage(config["yokoVoltage"])
# # ########cavityAtten.SetAttenuation(config["cav_Atten"])
# # ######qubitAtten.SetAttenuation(config["qubit_Atten"])
# #
# # #### run the single shot experiment
#
# Instance_SingleShotProgram = SingleShotProgram(path="dataTestSingleShotProgram", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
# data_SingleShotProgram = SingleShotProgram.acquire(Instance_SingleShotProgram)
# # print(data_SingleShotProgram)
# SingleShotProgram.display(Instance_SingleShotProgram, data_SingleShotProgram, plotDisp=True)
#
# SingleShotProgram.save_data(Instance_SingleShotProgram, data_SingleShotProgram)
# SingleShotProgram.save_config(Instance_SingleShotProgram)


################################################################################################################



#### loop over a few read times to find fidelity as a function of read time
###readArr = np.array([1,2,4,6,8,10,12,14,16,18,20,25,30,35,40,45,50, 60,70,80,90,100,110,120,130,140])
# readArr = np.linspace(1, 40, 40)
# fidArr = np.zeros(len(readArr))
#
# for i in range(len(readArr)):
#     config['read_length'] = readArr[i]
#
#     Instance_SingleShotProgram = SingleShotProgram(path="SingleShot_readTimeSweeps", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
#     data_SingleShotProgram = SingleShotProgram.acquire(Instance_SingleShotProgram)
#     SingleShotProgram.display(Instance_SingleShotProgram, data_SingleShotProgram, plotDisp=False)
#     fidArr[i] = Instance_SingleShotProgram.fid
#     plt.clf()
#     print(i/len(readArr))
#
# plt.figure(101)
# plt.plot(readArr, fidArr, 'o')
# plt.xlabel('Read Length (us)')
# plt.ylabel('Fidelity')

### loop over a different read frequencies
# freqDiffArr = np.linspace(-1.0,1.0, 21)
# fidArr = np.zeros(len(freqDiffArr))
#
# for i in range(len(freqDiffArr)):
#     config['read_pulse_freq'] = 892.8 + freqDiffArr[i]
#
#     Instance_SingleShotProgram = SingleShotProgram(path="SingleShot_readFreqSweeps", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
#     data_SingleShotProgram = SingleShotProgram.acquire(Instance_SingleShotProgram)
#     SingleShotProgram.display(Instance_SingleShotProgram, data_SingleShotProgram, plotDisp=False)
#     fidArr[i] = Instance_SingleShotProgram.fid
#     plt.clf()
#     print(i/len(freqDiffArr))
#
# plt.figure(101)
# plt.plot(freqDiffArr, fidArr, 'o')
# plt.xlabel('Detunning (MHz)')
# plt.ylabel('Fidelity')

########################################################################################################################
###################################### code for optimizing readout parameters
UpdateConfig = {
    ##### define attenuators starting values
    "qubit_Atten": 0,  ### qubit attenuator value
    "cav_Atten": 45,  #### cavity attenuator attenuation value
    "yokoVoltage": -0.055, #-0.6397,
    ##### define the attenuation vector
    "cav_Atten_Start": 25,
    "cav_Atten_Stop": 10,
    "cav_Atten_Points": 26,
    ###### cavity
    "trans_reps": 2000,  # this will used for all experiements below unless otherwise changed in between trials
    "read_pulse_style": "const",  # --Fixed
    "read_length": 10,  # us
    "read_pulse_gain": 10000,  # [DAC units]
    "trans_freq_start": 891.0,  # [MHz] actual frequency is this number + "cavity_LO"
    "trans_freq_stop": 893.5,  # [MHz] actual frequency is this number + "cavity_LO"
    "TransNumPoints": 51,  ### number of points in the transmission frequecny
    ##### qubit spec parameters
    "spec_reps": 2000,
    "qubit_pulse_style": "arb",
    "qubit_length": 20,  ###us, this is used if pulse style is const
    "sigma": 0.025,  ### units us, define a 20ns sigma
    "qubit_freq": 4942.5,
    "qubit_freq_start": 4940,
    "qubit_freq_stop": 4990,
    "SpecNumPoints": 100,  ### number of points
    "qubit_gain": 27000,
    "shots": 2000,
    "relax_delay": 1500, # us
}

# config = BaseConfig | UpdateConfig
# yoko1.SetVoltage(config["yokoVoltage"])
# cavityAtten.SetAttenuation(config["cav_Atten"])
# #####qubitAtten.SetAttenuation(config["qubit_Atten"])
# #
# ##### run the actual experiment
# Instance_ReadOpt_wSingleShot = ReadOpt_wSingleShot(path="dataTestReadOpt_wSingleShot", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
# # Instance_ReadOpt_wSingleShot.acquire(calibrate = False, cavityAtten =cavityAtten)
# data_ReadOpt_wSingleShot = ReadOpt_wSingleShot.acquire(Instance_ReadOpt_wSingleShot, calibrate = False, cavityAtten =cavityAtten)
# ReadOpt_wSingleShot.save_data(Instance_ReadOpt_wSingleShot, data_ReadOpt_wSingleShot)
# ReadOpt_wSingleShot.save_config(Instance_ReadOpt_wSingleShot)


###################################### code for transmission gain sweep
UpdateConfig = {
    ##### define attenuators
    "yokoVoltage": -0.128,
    ##### change gain instead option
    "trans_gain_start": 100,
    "trans_gain_stop": 4500,
    "trans_gain_num": 45,
    ###### cavity
    "reps": 2000,  # this will used for all experiements below unless otherwise changed in between trials
    "read_pulse_style": "const", # --Fixed
    "read_length": 2, # us (length of the pulse applied)
    # "read_pulse_gain": 10000,  # [DAC units]
    "trans_freq_start": 891.0,  # [MHz] actual frequency is this number + "cavity_LO"
    "trans_freq_stop": 894.0,  # [MHz] actual frequency is this number + "cavity_LO"
    "TransNumPoints": 61,  ### number of points in the transmission frequecny
    ##### qubit spec parameters
    "qubit_pulse_style": "flat_top",
    "sigma": 0.015,  ### units us, define a 20ns sigma
    "flat_top_length": 0.025, ### in us
    "qubit_gain": 16500,
    "qubit_length": 4,  ###us, this is used if pulse style is const
    "qubit_freq": 4951.0,
    ##### define shots
    "shots": 1500, ### this gets turned into "reps"
    "relax_delay": 1500,  # us
}
config = BaseConfig | UpdateConfig
# yoko1.SetVoltage(config["yokoVoltage"])
# # cavityAtten.SetAttenuation(config["cav_Atten"])
# #####qubitAtten.SetAttenuation(config["qubit_Atten"])
# #
# ##### run the actual experiment
# Instance_GainReadOpt_wSingleShot = GainReadOpt_wSingleShot(path="dataTestGainReadOpt_wSingleShot", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
# data_GainReadOpt_wSingleShot = GainReadOpt_wSingleShot.acquire(Instance_GainReadOpt_wSingleShot)
# GainReadOpt_wSingleShot.save_data(Instance_GainReadOpt_wSingleShot, data_GainReadOpt_wSingleShot)
# GainReadOpt_wSingleShot.save_config(Instance_GainReadOpt_wSingleShot)

######################################################################################################################
UpdateConfig = {
    ##### define attenuators starting values
    "qubit_Atten": 0,  ### qubit attenuator value
    "cav_Atten": 17,  #### cavity attenuator attenuation value
    "yokoVoltage": -0.128,
    ###### cavity
    "read_pulse_style": "const",
    "read_length": 2,  # us
    "read_pulse_gain": 2000,  # [DAC units]
    "read_pulse_freq": 892.5,  # [MHz] actual frequency is this number + "cavity_LO"
    ##### qubit spec parameters
    "qubit_pulse_style": "flat_top",
    "sigma": 0.005,  ### units us, define a 20ns sigma
    "flat_top_length": 0.030, ### in us
    ##### define qubit freq array
    "qubit_freq_start": 4945.0,
    "qubit_freq_stop": 4970.0,
    "qubit_freq_num": 26,  ### number of points
    ##### define the  gain array
    "qubit_gain_start": 15000,
    "qubit_gain_stop": 30000,
    "qubit_gain_num": 16,  ### number of points
    ##### give basic parameters
    "shots": 1500,
    "relax_delay": 1500, # us
}
config = BaseConfig | UpdateConfig

# yoko1.SetVoltage(config["yokoVoltage"])
# ####cavityAtten.SetAttenuation(config["cav_Atten"])
# ###qubitAtten.SetAttenuation(config["qubit_Atten"])
#
# Instance_PiOpt_wSingleShot = PiOpt_wSingleShot(path="dataTestPiOpt_wSingleShot", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
# data_PiOpt_wSingleShot = PiOpt_wSingleShot.acquire(Instance_PiOpt_wSingleShot)
# PiOpt_wSingleShot.save_data(Instance_PiOpt_wSingleShot, data_PiOpt_wSingleShot)
# PiOpt_wSingleShot.save_config(Instance_PiOpt_wSingleShot)


########################################################################################################################
###################################### running single shot with fast flux pulses
UpdateConfig = {
    ##### define attenuators
    "cav_Atten": 7,  #### cavity attenuator attenuation value
    "yokoVoltage": -0.6925,
    ###### cavity
    # "reps": 2000,  # this will used for all experiements below unless otherwise changed in between trials
    "read_pulse_style": "const", # --Fixed
    "read_length": 2, # us (length of the pulse applied)
    "read_pulse_gain": 1500, # [DAC units]
    "read_pulse_freq": 892.8, # [MHz] actual frequency is this number + "cavity_LO"
    ##### qubit spec parameters
    "qubit_pulse_style": "arb",
    "qubit_gain": 25000,
    "qubit_length": 10,  ###us, this is used if pulse style is const
    "sigma": 0.025,  ### units us, define a 20ns sigma
    "qubit_freq": 4958.0,
    ##### define shots
    "shots": 2000, ### this gets turned into "reps"
    "relax_delay": 1300,  # us
    ##### define flux pulse parameters
    "ff_gain": 19800,
    "ff_length": 140, ### multiplied by 12
}
config = BaseConfig | UpdateConfig

yoko1.SetVoltage(config["yokoVoltage"])
#######cavityAtten.SetAttenuation(config["cav_Atten"])
#######qubitAtten.SetAttenuation(config["qubit_Atten"])

## run the single shot experiment

Instance_SingleShotProgramFF = SingleShotProgramFF(path="dataTestSingleShotProgramFF", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
data_SingleShotProgramFF = SingleShotProgramFF.acquire(Instance_SingleShotProgramFF)
SingleShotProgramFF.display(Instance_SingleShotProgramFF, data_SingleShotProgramFF, plotDisp=True)

SingleShotProgramFF.save_data(Instance_SingleShotProgramFF, data_SingleShotProgramFF)
SingleShotProgramFF.save_config(Instance_SingleShotProgramFF)

########################################################################################################################
plt.show()