#### test experiments that use the fast flux in addition to standard measurements

#### import packages
import os

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

from WTF.Client_modules.Experiments.mTransmission import Transmission
from WTF.Client_modules.Experiments.mSpecSlice import SpecSlice
from WTF.Client_modules.Experiments.mSpecVsFastFlux import SpecVsFastFlux
from WTF.Client_modules.Experiments.mSingleShotProgram import SingleShotProgram
from WTF.Client_modules.Experiments.mAmplitudeRabi import AmplitudeRabi
from WTF.Client_modules.Experiments.mAmplitudeRabi_BlobFF import AmplitudeRabi_BlobFF
from WTF.Client_modules.Experiments.mT1ExperimentFF import T1ExperimentFF
from WTF.Client_modules.Experiments.mT2ExperimentFF import T2ExperimentFF
from WTF.Client_modules.Experiments.mT2Experiment import T2Experiment
from WTF.Client_modules.Experiments.mfastFlux import LoopbackProgramFastFlux
from WTF.Client_modules.Experiments.mFluxDriftTest import FluxDriftTest
from WTF.Client_modules.Experiments.mFFPulse_WTF import FFPulse_WTF

#### define the saving path
outerFolder = "Z:\JakeB\Data\WTF01_A2_RFSOC\\"

#### define the attenuators
cavityAtten = attenuator(27787, attenuation_int= 35, print_int = False)


# Only run this if no proxy already exists
soc, soccfg = makeProxy()
# print(soccfg)

plt.ioff()

######################################################################################################################
####################################################################################################################
####### config fpr flux drift sweep
UpdateConfig = {
    ##### define attenuators
    "cav_Atten": 15,  #### cavity attenuator attenuation value
    ##### define the yoko voltage
    "yokoVoltage": -0.6923,
    ###### cavity
    # "trans_reps": 1000,  # this will used for all experiements below unless otherwise changed in between trials
    "read_pulse_style": "const", # --Fixed
    "read_length": 5, # us (length of the pulse applied)
    "read_pulse_gain": 1600, # [DAC units]
    "read_pulse_freq": 892.9, # [MHz] actual frequency is this number + "cavity_LO"
    ##### qubit spec parameters
    "spec_reps": 200,
    "qubit_pulse_style": "arb", #"const",
    "sigma": 0.025, ### us
    "qubit_gain": 18000, #500,
    "qubit_length": 20.00, ### in units of us
    "qubit_freq_start": 4980,
    "qubit_freq_stop": 5030,
    "SpecNumPoints": 101,  ### number of points
    ##### wait time parameters
    "wait_step": 0.01,  ### (min) time of each waiting step
    "wait_num": 2,  ### number of steps to take
    ##### fast flux parameters
    "ff_gain": 20000,
    "ff_length": 130,  ### us, this gets repeated 10x
}
config = BaseConfig | UpdateConfig

#### update the qubit and cavity attenuation
####cavityAtten.SetAttenuation(config["cav_Atten"])
### set the yoko frequency
# yoko1.SetVoltage(config["yokoVoltage"])
#
# ##### run actual experiment
# Instance_FluxDriftTest = FluxDriftTest(path="dataTestFluxDriftTest", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
# data_FluxDriftTest = FluxDriftTest.acquire(Instance_FluxDriftTest)
# FluxDriftTest.save_data(Instance_FluxDriftTest, data_FluxDriftTest)
# FluxDriftTest.save_config(Instance_FluxDriftTest)

####################################################################################################################
###################################### code for running spec vs flux experiement
UpdateConfig = {
    ##### define attenuator
    "cav_Atten": 35,  #### cavity attenuator attenuation value
    ##### define the yoko voltage
    "yokoVoltage": -0.6925,
    ##### define the flux pulse gain values
    "ff_gain_start": 19000,
    "ff_gain_stop": 20000,
    "FFNumPoints": 11,
    "ff_length": 100,  ### us, this gets repeated 10 times to ensure the state decays coming from half flux
    ###### cavity
    "trans_reps": 100,  # this will used for all experiements below unless otherwise changed in between trials
    "read_pulse_freq": 892.8,
    "read_pulse_style": "const",  # --Fixed
    "read_length": 4,  # us
    "read_pulse_gain": 1500,  # [DAC units]
    "trans_freq_start": 891.5,  # [MHz] actual frequency is this number + "cavity_LO"
    "trans_freq_stop": 894.5,  # [MHz] actual frequency is this number + "cavity_LO"
    "TransNumPoints": 151,  ### number of points in the transmission frequecny
    ##### qubit spec parameters
    "spec_reps": 200,
    "qubit_pulse_style": "const",
    "qubit_gain": 500, #1000,
    "qubit_length": 10.00, ### in units of us
    "qubit_freq_start": 4900,
    "qubit_freq_stop": 5000,
    "SpecNumPoints": 51,  ### number of points
    "sigma": 0.025,
}
config = BaseConfig | UpdateConfig

# #### update the qubit and cavity attenuation
# cavityAtten.SetAttenuation(config["cav_Atten"])
# ### set the yoko frequency
# yoko1.SetVoltage(config["yokoVoltage"])
#
# ##### run actual experiment
# Instance_SpecVsFastFlux = SpecVsFastFlux(path="dataTestSpecVsFastFlux", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
# data_SpecVsFastFlux = SpecVsFastFlux.acquire(Instance_SpecVsFastFlux)
# SpecVsFastFlux.save_data(Instance_SpecVsFastFlux, data_SpecVsFastFlux)
# SpecVsFastFlux.save_config(Instance_SpecVsFastFlux)


####################################################################################################################
####### config for rabi power blob
UpdateConfig = {
    ##### define attenuators
    "cav_Atten": 7,  #### cavity attenuator attenuation value
    "yokoVoltage": -0.6917,
    ###### cavity
    "read_pulse_style": "const", # --Fixed
    "read_length": 2, # us
    "read_pulse_gain": 1600, # [DAC units]
    "read_pulse_freq": 892.8, # [MHz] actual frequency is this number + "cavity_LO"
    ##### spec parameters for finding the qubit frequency
    # "qubit_gain": 500,
    "qubit_freq_start": 5590, #5605, #4985, #2845.0,
    "qubit_freq_stop": 5610, #5606, #5035, #2865.0
    "RabiNumPoints": 11,  ### number of points
    "qubit_pulse_style": "arb", #### arb means gaussain here
    "sigma": 0.025,  ### units us, define a 20ns sigma
    "flat_top_length": 0.020,
    "relax_delay": 1000,  ### turned into us inside the run function
    ##### amplitude rabi parameters
    "qubit_gain_start": 0,
    "qubit_gain_step": 600, ### stepping amount of the qubit gain
    "qubit_gain_expts": 51, ### number of steps
    "AmpRabi_reps": 200,  # number of averages for the experiment
    ##### fast flux parameters
    "ff_gain": 20000,
    "ff_length": 130,  ### us, this gets repeated 10x
}
config = BaseConfig | UpdateConfig

# yoko1.SetVoltage(config["yokoVoltage"])
#
# Instance_AmplitudeRabi_BlobFF = AmplitudeRabi_BlobFF(path="dataTestRabiAmpBlobFF", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
# data_AmplitudeRabi_BlobFF = AmplitudeRabi_BlobFF.acquire(Instance_AmplitudeRabi_BlobFF)
# AmplitudeRabi_BlobFF.save_data(Instance_AmplitudeRabi_BlobFF, data_AmplitudeRabi_BlobFF)
# AmplitudeRabi_BlobFF.save_config(Instance_AmplitudeRabi_BlobFF)


######################################################################################################################
########### T1 measurement
UpdateConfig = {
    ##### define attenuators
    "cav_Atten": 15,  #### cavity attenuator attenuation value
    "yokoVoltage": -0.6917,
    ###### cavity
    "read_pulse_style": "const", # --Fixed
    "read_length": 2, # us
    "read_pulse_gain": 1600, # [DAC units]
    "read_pulse_freq": 892.9, # [MHz] actual frequency is this number + "cavity_LO"
    ##### spec parameters for finding the qubit frequency
    "qubit_freq": 2855.0, #2850.0, #5010.0,
    "qubit_gain": 30000, #8000,
    "sigma": 0.005,  ### units us, define a 20ns sigma
    "flat_top_length": 0.040,
    "qubit_pulse_style": "flat_top", #### arb means gaussain here
    "relax_delay": 1400,  ### turned into us inside the run function
    ##### T1 parameters
    "start": 0, ### us
    "step": 1, ### us
    "expts": 300, ### number of experiemnts
    "reps": 300, ### number of averages on each experiment
    ##### fast flux parameters
    "ff_gain": 20000,
    "ff_length": 140,  ### us, this gets repeated 10x
}
config = BaseConfig | UpdateConfig

# yoko1.SetVoltage(config["yokoVoltage"])
# cavityAtten.SetAttenuation(config["cav_Atten"])
#
# Instance_T1ExperimentFF = T1ExperimentFF(path="dataTestT1ExperimentFF", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
# data_T1ExperimentFF = T1ExperimentFF.acquire(Instance_T1ExperimentFF)
# T1ExperimentFF.display(Instance_T1ExperimentFF, data_T1ExperimentFF, plotDisp=True)
# T1ExperimentFF.save_data(Instance_T1ExperimentFF, data_T1ExperimentFF)
# T1ExperimentFF.save_config(Instance_T1ExperimentFF)

# #####################################################################################################################
#####################################################################################################################
########### T2 measurement
UpdateConfig = {
    ##### define attenuators
    "cav_Atten": 15,  #### cavity attenuator attenuation value
    "yokoVoltage": -0.6917,
    ###### cavity
    "read_pulse_style": "const", # --Fixed
    "read_length": 2, # us
    "read_pulse_gain": 1600, # [DAC units]
    "read_pulse_freq": 892.9, # [MHz] actual frequency is this number + "cavity_LO"
    ##### spec parameters for finding the qubit frequency
    "qubit_freq": 2855.0+2,
    "qubit_gain": int(30000/1.3),
    "sigma": 0.005,  ### units us, define a 20ns sigma
    "flat_top_length": 0.040,
    "qubit_pulse_style": "flat_top", #### arb means gaussain here
    "relax_delay": 500,  ### turned into us inside the run function
    ##### fast flux parameters
    "ff_gain": 20000,
    "ff_length": 140,  ### us, this gets repeated 10x
    # ##### T1 parameters
    ##### T2 ramsey parameters
    "start": 0.005,  ### us
    "step": 0.005,  ### us
    "expts": 500,  ### number of experiemnts
    "reps": 400,  ### number of averages on each experiment
}
config = BaseConfig | UpdateConfig

yoko1.SetVoltage(config["yokoVoltage"])
# cavityAtten.SetAttenuation(config["cav_Atten"])
#
Instance_T2ExperimentFF = T2ExperimentFF(path="dataTestT2ExperimentFF", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
data_T2ExperimentFF = T2ExperimentFF.acquire(Instance_T2ExperimentFF)
T2ExperimentFF.display(Instance_T2ExperimentFF, data_T2ExperimentFF, plotDisp=True)
T2ExperimentFF.save_data(Instance_T2ExperimentFF, data_T2ExperimentFF)
T2ExperimentFF.save_config(Instance_T2ExperimentFF)

#
#
# # Instance_AmplitudeRabi_BlobFF = AmplitudeRabi_BlobFF(path="dataTestRabiAmpBlobFF", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
# # data_AmplitudeRabi_BlobFF = AmplitudeRabi_BlobFF.acquire(Instance_AmplitudeRabi_BlobFF)
# # AmplitudeRabi_BlobFF.save_data(Instance_AmplitudeRabi_BlobFF, data_AmplitudeRabi_BlobFF)
# # AmplitudeRabi_BlobFF.save_config(Instance_AmplitudeRabi_BlobFF)


####################################################################################################################
########## WTF expirement
# UpdateConfig = {
#     ##### define attenuators
#     "cav_Atten": 7,  #### cavity attenuator attenuation value
#     "yokoVoltage": -0.6374,
#     ###### cavity
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 10, # us
#     "read_pulse_gain": 10000, # [DAC units]
#     "read_pulse_freq": 891.35, # [MHz] actual frequency is this number + "cavity_LO"
#     ##### spec parameters for finding the qubit frequency
#     "qubit_freq": 4954.0,
#     "qubit_gain": 23000,
#     "sigma": 0.025,  ### units us, define a 20ns sigma
#     "qubit_pulse_style": "arb", #### arb means gaussain here
#     "relax_delay": 1400,  ### turned into us inside the run function
#     ##### fast flux parameters
#     "ff_gain": 19730,
#     "ff_length": 140,  ### us, this gets repeated 10x
#     ###### single shot parameters
#     "shots": 5000,
# }
#
# UpdateConfig = {
#     ##### define attenuators
#     "cav_Atten": 17,  #### cavity attenuator attenuation value
#     "yokoVoltage": -0.128,
#     ###### cavity
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 2, # us
#     "read_pulse_gain": 2000, # [DAC units]
#     "read_pulse_freq": 892.5, # [MHz] actual frequency is this number + "cavity_LO"
#     ##### spec parameters for finding the qubit frequency
#     "qubit_freq": 4951.0,
#     "qubit_gain": 16500,
#     "qubit_pulse_style": "flat_top",
#     "sigma": 0.015,  ### units us, define a 20ns sigma
#     "flat_top_length": 0.025,  ### in us
#     "relax_delay": 1500,  ### turned into us inside the run function
#     ##### fast flux parameters
#     "ff_gain": 0,
#     "ff_length": 1,  ### us, this gets repeated 10x
#     ###### single shot parameters
#     "shots": 2500,
# }
#
# config = BaseConfig | UpdateConfig
#
# yoko1.SetVoltage(config["yokoVoltage"])
# #####cavityAtten.SetAttenuation(config["cav_Atten"])
# #
# Instance_FFPulse_WTF = FFPulse_WTF(path="dataTestFFPulse_WTF", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
# # data_FFPulse_WTF = FFPulse_WTF.acquire(Instance_FFPulse_WTF)
# # FFPulse_WTF.display(Instance_FFPulse_WTF, data_FFPulse_WTF, plotDisp=True)
#
# i_0, i_1, q_0, q_1 = FFPulse_WTF.acquire(Instance_FFPulse_WTF)
#
#
# ##### sort into mixed state arrays
# mixed0 = MixedShots(i_0, q_0, numbins=25)
# mixed1 = MixedShots(i_1, q_1, numbins=25)
#
# theta = mixed0.theta
#
# i_0_rot = i_0 * np.cos(theta) - q_0 * np.sin(theta)
# q_0_rot = i_0 * np.sin(theta) + q_0 * np.cos(theta)
#
# i_1_rot = i_1 * np.cos(theta) - q_1 * np.sin(theta)
# q_1_rot = i_1 * np.sin(theta) + q_1 * np.cos(theta)
#
# ### find the mid point as an approximate divider
# thresh_g = -20
# thresh_e = 5
# # sort into arrays on either side of the threshold
# #### arbirtarily label with g and e
# i_0_g = np.array([])
# q_0_g = np.array([])
# i_1_g = np.array([])
# q_1_g = np.array([])
#
# i_0_e = np.array([])
# q_0_e = np.array([])
# i_1_e = np.array([])
# q_1_e = np.array([])
#
# for i in range(len(i_0)):
#     if i_0_rot[i] < thresh_g:
#         i_0_g = np.append(i_0_g, i_0[i])
#         q_0_g = np.append(q_0_g, q_0[i])
#
#         i_1_g = np.append(i_1_g, i_1[i])
#         q_1_g = np.append(q_1_g, q_1[i])
#     if i_0_rot[i] > thresh_e:
#         i_0_e = np.append(i_0_e, i_0[i])
#         q_0_e = np.append(q_0_e, q_0[i])
#
#         i_1_e = np.append(i_1_e, i_1[i])
#         q_1_e = np.append(q_1_e, q_1[i])
#
# ### use the helper hist function to make a historgram of the sorted data
# fid, threshold, angle = hist_process(data=[i_1_g, q_1_g, i_1_e, q_1_e], plot=True)
#
#
# #### plotting
# alpha = 0.3
#
# fig, axs = plt.subplots(3,2, figsize = (8,10), num = 2)
#
# axs[0,0].plot(i_0, q_0, 'go', alpha = alpha, label = '0')
# axs[0,0].set_xlabel('I (a.u.)')
# axs[0,0].set_ylabel('Q (a.u.)')
# axs[0,0].set_title('meas 0')
#
# axs[0,1].plot(i_1, q_1, 'mo', alpha = alpha, label = '1')
# axs[0,1].set_xlabel('I (a.u.)')
# axs[0,1].set_ylabel('Q (a.u.)')
# axs[0,1].set_title('meas 1')
# i_1_lim = axs[0,1].get_xlim()
# q_1_lim = axs[0,1].get_ylim()
#
#
# axs[1,0].plot(i_0_rot, q_0_rot, 'go', alpha = alpha, label = '0g')
# axs[1,0].axvline(thresh_e, color = 'k')
# axs[1,0].axvline(thresh_g, color = 'k')
# # axs[1,0].plot(i_1_rot, q_1_rot, 'o', alpha = 0.5, label = '0')
# axs[1,0].set_xlabel('I (a.u.)')
# axs[1,0].set_ylabel('Q (a.u.)')
# axs[1,0].set_title('meas 0, rotated')
#
#
# axs[2,0].plot(i_0_g, q_0_g, 'ro', alpha = alpha, label = '0g')
# axs[2,0].plot(i_0_e, q_0_e, 'bo', alpha = alpha, label = '0e')
# # axs[1,0].plot(i_1_rot, q_1_rot, 'o', alpha = 0.5, label = '0')
# axs[2,0].set_xlabel('I (a.u.)')
# axs[2,0].set_ylabel('Q (a.u.)')
# axs[2,0].set_title('meas 0, sorted')
#
#
# axs[1,1].plot(i_1_g, q_1_g, 'ro', alpha = alpha, label = '1g')
# # axs[1,1].plot(i_1_e, q_1_e, 'bo', alpha = alpha, label = '1e')
# axs[1,1].set_xlabel('I (a.u.)')
# axs[1,1].set_ylabel('Q (a.u.)')
# axs[1,1].set_title('meas 1, sorted')
# axs[1,1].set_xlim(i_1_lim)
# axs[1,1].set_ylim(q_1_lim)
#
# # axs[2,1].plot(i_1_g, q_1_g, 'ro', alpha = alpha, label = '1g')
# axs[2,1].plot(i_1_e, q_1_e, 'bo', alpha = alpha, label = '1e')
# axs[2,1].set_xlabel('I (a.u.)')
# axs[2,1].set_ylabel('Q (a.u.)')
# axs[2,1].set_title('meas 1, sorted')
# axs[2,1].set_xlim(i_1_lim)
# axs[2,1].set_ylim(q_1_lim)
#
# plt.legend()
#

####################################################################################################################
plt.show(block = True)
