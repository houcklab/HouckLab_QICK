#%%
#### import packages
import os
import time

import numpy as np

from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mFFSpecVsDelay import FFSpecVsDelay_Experiment
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mFFRampTest import FFRampTest_Experiment
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mFFSpecVsFlux import FFSpecVsFlux_Experiment
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mFFTransSlice import FFTransSlice_Experiment
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mFFTransVsFlux import FFTransVsFlux_Experiment
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mLoopback import LoopbackProgram, Loopback
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mTwoToneTransmission import \
    TwoToneTransmission
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.PythonDrivers.mlbf_driver import MLBFDriver

path = r'C:\Users\escher\Documents\GitHub\HouckLab_QICK\WorkingProjects\Tantalum_fluxonium_escher\Client_modules\PythonDrivers'
os.add_dll_directory(path)
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Calib_escher.initialize import *
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mQubit_Pulse_Test import Qubit_Pulse_Test
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mTransmission_SaraTest import Transmission # This is Parth's
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mSpecSlice_bkg_subtracted import SpecSlice_bkg_sub
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mSpecSlice_SaraTest import SpecSlice
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mSpecSlice import SpecSliceBuggy # This is bugged
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mSpecSlice_shots import SpecSlice_shots
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mAmplitudeRabi import AmplitudeRabi
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mTransVsGain import TransVsGain
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mTransVsRelaxDelay import TransVsRelaxDelay
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mAmplitudeRabi_Blob import AmplitudeRabi_Blob
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mAmplitudeRabi_CavityPower import AmplitudeRabi_CavityPower
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mT1Experiment import T1Experiment
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mT2Experiment import T2Experiment
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mT2EchoExperiment import T2EchoExperiment
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mSingleShotProgram import SingleShotProgram
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mSingleShot_2Dsweep import SingleShot_2Dsweep
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mAmplitudeRabiBlob_PS import AmplitudeRabi_PS
#from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mAmplitudeRabiFlux_PS import AmplitudeRabiFlux_PS
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mQubitSpecRepeat import QubitSpecRepeat
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mQubit_ef_spectroscopy import Qubit_ef_spectroscopy
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mQubit_EF_Rabi import Qubit_ef_rabi
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mSingleShot_individual_state import SingleShotProgram_individual_state
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mSingleShot_individual_state import SingleShotProgram_ef
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mQubit_EF_Rabi import Qubit_ef_RPM
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.ConstantTone import ConstantTone_Experiment
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mSpecSlice_PS_sse import SpecSlice_PS_sse
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mTimeRabi_Blob import TimeRabi_Blob
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mStarkShift import StarkShift
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mQubitTwoToneResonatorCool import \
    QubitTwoToneResonatorCoolExperiment
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mFFSpecSlice import FFSpecSlice_Experiment


import sys
sys.path.insert(0, 'Z:\TantalumFluxonium\Data\HouckLabMeasurementCode\ADMV8818')
#from admv8818_functions import set_filter
from matplotlib import pyplot as plt
import datetime
from tqdm import tqdm
import math
import h5py
import Pyro4.util
import json
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.CoreLib.Experiment import MakeFile
# Define the saving path
outerFolder = r"Z:\TantalumFluxonium\Data\2025_07_25_cooldown\HouckCage_dev\WTF\\" # end in \\

# Only run this if no proxy already exists
soc, soccfg = makeProxy()
# print(soccfg)

# plt.ioff()

# Defining the switch configuration
SwitchConfig = {
    "trig_buffer_start": 0.05, #0.035, # in us
    "trig_buffer_end": 0.04, #0.024, # in us
    "trig_delay": 0.07, # in us
}

BaseConfig = BaseConfig | SwitchConfig

#mlbf_filter = MLBFDriver("192.168.1.10")
mlbf_filter = MLBFDriver("192.168.1.11")
#yoko = yoko
#%%
# TITLE: Constant Tone Experiment
UpdateConfig = {
    ###### cavity
    "read_pulse_style": "const",  # --Fixed
    "gain": 0,  # [DAC units]

    "freq": 50, #3713,  # [MHz]

    "channel": 1, #0,  # TODO default value # 0 is resonator, 1 is qubit
    "nqz": 1, #2,#1,  # TODO default value
}

config = BaseConfig | UpdateConfig

ConstantTone_Instance = ConstantTone_Experiment(path="dataTestTransVsGain", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
try:
    ConstantTone_Experiment.acquire(ConstantTone_Instance)
except Exception:
    print("Pyro traceback:")
    print("".join(Pyro4.util.getPyroTraceback()))
ConstantTone_Experiment.save_data(ConstantTone_Instance)
ConstantTone_Experiment.save_config(ConstantTone_Instance)

# cavityAtten.SetAttenuation(20,printOut=True)
# using the 10MHz-1GHz balun
# f_center = 10e9 #Hz
# settings = set_filter(f_center)
# print(settings)

#%%

#TITLE: Transmission + SpecSlice + AmplitudeRabi

UpdateConfig_transmission = {
    "reps": 2000,

    # cavity
    "read_pulse_style": "const",  # --Fixed
    "read_length": 15,
    "read_pulse_gain": 8000,
    "read_pulse_freq": 7391.9441,

    # Transmission Experiment
    "TransSpan": 5,
    "TransNumPoints": 301,
    "ro_mode_periodic": False,

    # define the yoko voltage
    "yokoVoltage": -1.478,

}

UpdateConfig_qubit = {
    "qubit_pulse_style": "arb",
    "qubit_freq": 944, #940.8,
    "qubit_gain": 30000,

    # Constant Pulse Tone
    "qubit_length": 10,

    # Flat top or gaussian pulse tone
    "sigma": 1,#0.3,
    "flat_top_length": 0.5,

    # define spec slice experiment parameters
    "qubit_ch": 1,
    "qubit_nqz": 1,
    "qubit_freq_start": 800, #2105,
    "qubit_freq_stop": 1100,#2120,
    "SpecNumPoints": 201,
    'spec_reps': 5000,#10000, #20000,

    # amplitude rabi parameters
    "qubit_gain_start": 0,
    "qubit_gain_step": 10000,
    "qubit_gain_expts": 5,
    "AmpRabi_reps": 1000,


    # Experiment parameters
    "relax_delay": 10, #2000,
    "fridge_temp": 10,
    "two_pulses": False, # Do e-f pulse
    "use_switch": False,
    "qubit_mode_periodic": False,
}
UpdateConfig = UpdateConfig_transmission | UpdateConfig_qubit
config = BaseConfig | UpdateConfig
#print("TestExperiment is not changing yoko voltage!")
yoko.SetVoltage(config["yokoVoltage"])

#%%
# TITLE: Performing the Cavity Transmission Experiment
config = BaseConfig | UpdateConfig

#Updating the mlbf filter
filter_freq = (config["read_pulse_freq"])
mlbf_filter.set_frequency(int(filter_freq))

## Changing the peak finder to maxima

Instance_trans = Transmission(path="dataTestTransmission", cfg=config,soc=soc,soccfg=soccfg, outerFolder = outerFolder)
data_trans= Transmission.acquire(Instance_trans)
Transmission.display(Instance_trans, data_trans, plotDisp=True)
Transmission.save_data(Instance_trans, data_trans)
Instance_trans.save_config()

# update the transmission frequency to be the peak
#config["read_pulse_freq"] = Instance_trans.peakFreq
print("Cavity freq IF [MHz] = ", Instance_trans.peakFreq)


#%%
# TITLE: Performing cavity transmission after a qubit pulse
config = BaseConfig | UpdateConfig
Instance_trans = TwoToneTransmission(path="TwoToneTransmission", cfg=config,soc=soc,soccfg=soccfg, outerFolder = outerFolder, progress = False)
data_trans= TwoToneTransmission.acquire(Instance_trans)
TwoToneTransmission.display(Instance_trans, data_trans, plotDisp=True)
TwoToneTransmission.save_data(Instance_trans, data_trans)
Instance_trans.save_config()

#%%
# TITLE: Performing regular ole' `spec slice`

soc.reset_gens()

# Estimate Time
time = config["spec_reps"]*config["SpecNumPoints"]*(config["relax_delay"] + config["qubit_length"] + config["read_length"])*1e-6
#print("Time required for spec slice experiment is ", datetime.timedelta(seconds = time).strftime('%H::%M::%S'))
print("Time for spec experiment is about ", time, " s")

Instance_specSlice = SpecSlice(path="dataTestSpecSlice", cfg=config,soc=soc,soccfg=soccfg, outerFolder = outerFolder)
data_specSlice= SpecSlice.acquire(Instance_specSlice)
SpecSlice.display(Instance_specSlice, data_specSlice, plotDisp=True)
SpecSlice.save_data(Instance_specSlice, data_specSlice)
# print(Instance_specSlice.qubitFreq)
plt.show()

#%%
# TITLE: Performing regular ole' spec slice BUGGY

# Estimate Time
time = config["spec_reps"]*config["SpecNumPoints"]*(config["relax_delay"] + config["qubit_length"] + config["read_length"])*1e-6
#print("Time required for spec slice experiment is ", datetime.timedelta(seconds = time).strftime('%H::%M::%S'))
print("Time for spec experiment is about ", time, " s")

Instance_specSliceBuggy = SpecSliceBuggy(path="dataTestSpecSliceBuggy", cfg=config,soc=soc,soccfg=soccfg, outerFolder = outerFolder)
data_specSliceBuggy= SpecSliceBuggy.acquire(Instance_specSliceBuggy)
SpecSliceBuggy.display(Instance_specSliceBuggy, data_specSliceBuggy, plotDisp=True)
SpecSliceBuggy.save_data(Instance_specSliceBuggy, data_specSliceBuggy)
# print(Instance_specSlice.qubitFreq)
plt.show()
#%%
# TITLE: Performing background subtracted spec slice
plt.close("all")

Instance_specSlice = SpecSlice_bkg_sub(path="dataTestSpecSlice", cfg=config,soc=soc,soccfg=soccfg, outerFolder = outerFolder, progress = True)
try:
    data_specSlice= Instance_specSlice.acquire()
except Exception:
    print("Pyro traceback:")
    print("".join(Pyro4.util.getPyroTraceback()))
Instance_specSlice.display(plotDisp=True)
Instance_specSlice.save_config()
Instance_specSlice.save_data(data_specSlice)

#%%
# TITLE : Perform the spec slice with Post Selection
config_spec_ps = {
    'spec_reps' : 10000, #20000, # Converted to shots
    'initialize_pulse': False,
    'fridge_temp': 420,
    "qubit_pulse_style": "flat_top"
}
config_spec_ps = config | config_spec_ps
inst_specslice = SpecSlice_PS_sse(path="dataTestSpecSlice_PS", cfg=config_spec_ps,
                                        soc=soc, soccfg=soccfg, outerFolder=outerFolder)
data_specSlice_PS = inst_specslice.acquire()
data_specSlice_PS = inst_specslice.process_data(data = data_specSlice_PS)
inst_specslice.display(data = data_specSlice_PS, plotDisp=True)
inst_specslice.save_data(data_specSlice_PS)
inst_specslice.save_config()

#%%
# TITLE: Performing the Amplitude Rabi Experiment
#config["qubit_pulse_style"]= "const" #"arb" #"arb"
#config["sigma"] = 0.6

Instance_AmplitudeRabi = AmplitudeRabi(path="dataTestAmplitudeRabi", cfg=config,soc=soc,soccfg=soccfg, outerFolder = outerFolder)
data_AmplitudeRabi = AmplitudeRabi.acquire(Instance_AmplitudeRabi)
AmplitudeRabi.display(Instance_AmplitudeRabi, data_AmplitudeRabi, plotDisp=True)
AmplitudeRabi.save_data(Instance_AmplitudeRabi, data_AmplitudeRabi)
AmplitudeRabi.save_config(Instance_AmplitudeRabi)


#%%
##TITLE: Transmission vs Power
###region Trans vs Power Config
UpdateConfig = {
    "yokoVoltage": -1.467, #0.09473, #3.1
    ##### change gain instead option
    "trans_gain_start": 100,
    "trans_gain_stop": 30000,
    "trans_gain_num": 31,
    ###### cavity
    "reps": 1000,
    "trans_reps": 1000,  # this will be used for all experiments below unless otherwise changed in between trials
    "read_pulse_style": "const",  # --Fixed
    #"readout_length": 35,  # [us] 1/7/2025 JL
    "read_length": 15,  # [us] 1/7/2025 JL
    # "read_pulse_gain": 10000,  # [DAC units]
    # "trans_freq_start": 7229.8 - 5.0,  # [MHz] actual frequency is this number + "cavity_LO"
    # "trans_freq_stop": 7229.8 + 5.0,  # [MHz] actual frequency is this number + "cavity_LO"
    "trans_freq_start": 7380,  # [MHz] actual frequency is this number + "cavity_LO"
    "trans_freq_stop": 7400,  # [MHz] actual frequency is this number + "cavity_LO"
    "TransNumPoints": 101,  ### number of points in the transmission frequecny
    "relax_delay": 2, # us
    "units": "DAC",         # in dB or DAC
}
#
config = BaseConfig | UpdateConfig
#
# #### update the qubit and cavity attenuation
yoko.SetVoltage(config["yokoVoltage"])
# #

import matplotlib
matplotlib.use('Qt5Agg')
Instance_TransVsGain = TransVsGain(path="dataTestTransVsGain", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
data_TransVsGain = TransVsGain.acquire(Instance_TransVsGain)
TransVsGain.save_data(Instance_TransVsGain, data_TransVsGain)
TransVsGain.save_config(Instance_TransVsGain)
# endregion
 #%%
## TITLE: Stark Shift (Sweep gain on the readout while doing spec)
UpdateConfig = {
    "yokoVoltage": -0.105,

    # Experiment Parameter
    "trans_gain_start": 300,
    "trans_gain_stop": 2300,
    "trans_gain_num": 21,
    "change_ro_gain": True, # If true even the gain of the readout pulse will change.

    # cavity
    "read_pulse_style": "const",  # --Fixed
    "read_length": 30,  # [us]
    "read_pulse_freq":  7392, # [MHz]
    "read_pulse_gain": 8000,
    "units": "DAC",         # in dB or DAC

    # qubit spec parameters
    "qubit_pulse_style": "const",
    "qubit_gain": 30000,
    "qubit_length": 30,

    # define spec slice experiment parameters
    "qubit_freq_start": 1000,
    "qubit_freq_stop": 2000,
    "SpecNumPoints": 501,
    'spec_reps': 1000,

    # Experiment parameters
    "relax_delay": 20,
    "use_switch": False, # On the qubit drive
    "mode_periodic": False, # On the qubit drive
    "ro_mode_periodic": True,
}
config = BaseConfig | UpdateConfig

import matplotlib
matplotlib.use('Qt5Agg')
Instance_StarkShift = StarkShift(path="dataTestStarkShift", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
data_StarkShift = StarkShift.acquire(Instance_StarkShift)
StarkShift.save_data(Instance_StarkShift, data_StarkShift)
StarkShift.save_config(Instance_StarkShift)


#
#%%
##TITLE: Transmission vs Read length
###region Trans vs Power Config
UpdateConfig = {
    "yokoVoltage": -1.3, #0.09473, #3.1
    ##### change gain instead option
    "read_length_start": 1,
    "read_length_stop": 10,
    "read_length_num": 11,
    ###### cavity
    "reps": 1000,
    "trans_reps": 300,  # this will used for all experiments below unless otherwise changed in between trials
    "read_pulse_style": "const",  # --Fixed
    #"readout_length": 45,  # [us]
    "read_pulse_gain": 9000,
    "trans_freq_start": 6722.8,  # [MHz] actual frequency is this number + "cavity_LO"
    "trans_freq_stop": 6724.7,  # [MHz] actual frequency is this number + "cavity_LO"
    "TransNumPoints": 151,  ### number of points in the transmission frequecny
    "relax_delay": 10, # us
    "units": "DAC",         # in dB or DAC
}
#
config = BaseConfig | UpdateConfig
#
# #### update the qubit and cavity attenuation
yoko.SetVoltage(config["yokoVoltage"])
# #
import matplotlib
matplotlib.use('Qt5Agg')
Instance_TransVsRelaxDelay= TransVsRelaxDelay(path="dataTestTransVsRelaxDelay", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
data_TransVsRelaxDelay = TransVsRelaxDelay.acquire(Instance_TransVsRelaxDelay)
TransVsRelaxDelay.save_data(Instance_TransVsRelaxDelay, data_TransVsRelaxDelay)
TransVsRelaxDelay.save_config(Instance_TransVsRelaxDelay)
# endregion
#%%
# TITLE: Amplitude Rabi Blob

UpdateConfig = {
    ##### define attenuators
    "yokoVoltage": 3.0,
    ###### cavity
    "read_pulse_style": "const",  # --Fixed
    "read_length": 5,  # us
    "read_pulse_gain": 9000,  # [DAC units]
    "read_pulse_freq": 6723.51629, #6664.53,  # MHz
    ##### spec parameters for finding the qubit frequency
    "qubit_freq_start": 500, #2106.7,
    "qubit_freq_stop": 1500, #2106.9,
    "RabiNumPoints": 501,  ### number of points
    "qubit_pulse_style": "const",
    "sigma": 0.15,  ### units us, define a 20ns sigm
    "flat_top_length": 30.0, ### in us
    "qubit_length": 2,
    "relax_delay": 5,  ### turned into us inside the run function
    ##### amplitude rabi parameters
    "qubit_gain_start": 0,
    "qubit_gain_step": 200,  ### stepping amount of the qubit gain
    "qubit_gain_expts": 51,  ### number of steps
    "AmpRabi_reps": 2000,  # number of averages for the experiment
    "two_pulses": False, # Pulse twice for calibrating a pi/2 pulse
    'use_switch': False,
}
config = BaseConfig | UpdateConfig
#
yoko.SetVoltage(config["yokoVoltage"])
matplotlib.use('Qt5Agg')
Instance_AmplitudeRabi_Blob = AmplitudeRabi_Blob(path="dataTestRabiAmpBlob", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg, progress=True)
data_AmplitudeRabi_Blob = AmplitudeRabi_Blob.acquire(Instance_AmplitudeRabi_Blob)
AmplitudeRabi_Blob.save_data(Instance_AmplitudeRabi_Blob, data_AmplitudeRabi_Blob)
AmplitudeRabi_Blob.save_config(Instance_AmplitudeRabi_Blob)

#%%
### TITLE: Time Rabi Blob
UpdateConfig = {
    ##### define attenuators
    "yokoVoltage": 1.25,
    ###### cavity
    "read_pulse_style": "const",  # --Fixed
    "read_length": 30,  # us
    "read_pulse_gain": 1000,  # [DAC units]
    "read_pulse_freq": 6422.98,  # MHz
    ##### spec parameters for finding the qubit frequency
    "qubit_freq_start": 2111,
    "qubit_freq_stop": 2111.1,
    "RabiNumPoints": 2,  ### number of points
    "qubit_pulse_style": "flat_top",
    "sigma": .1,  ### units us, define a 20ns sigma
    #"flat_top_length": 30.0, ### in us
    "qubit_gain": 30000,#30000,
    "relax_delay": 50,  ### turned into us inside the run function
    ##### time rabi parameters
    "qb_length": 10,
    "qubit_len_start": 0.5,
    "qubit_len_step": .8,  ### stepping amount of the qubit gain
    "qubit_len_expts": 80,  ### number of steps
    "TimeRabi_reps": 40000,  # number of averages for the experiment
    "two_pulses": False, # Pulse twice for calibrating a pi/2 pulse
    'use_switch': True,
}
config = BaseConfig | UpdateConfig
#
yoko1.SetVoltage(config["yokoVoltage"])

Instance_TimeRabi_Blob = TimeRabi_Blob(path="dataTestRabiTimeBlob", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg, progress=True)
data_TimeRabi_Blob = TimeRabi_Blob.acquire(Instance_TimeRabi_Blob)
TimeRabi_Blob.save_data(Instance_TimeRabi_Blob, data_TimeRabi_Blob)
TimeRabi_Blob.save_config(Instance_TimeRabi_Blob)
#%%
###TITLE: Amplitude Rabi vs Cavity Power
##region Amplitude Rabi vs Cavity Power Config
# UpdateConfig = {
#     ##### define attenuators
#     "yokoVoltage": 0,
#     ###### cavity gain steps
#     "reps": 5,  # this will used for all experiements below unless otherwise changed in between trials
#     "readout_length": 10, # us
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 10, # us
#     "read_pulse_gain" : 4000,
#     "cav_amp_start": 2000, # [DAC units]
#     "cav_amp_stop": 4000,
#     "cavNumPoints": 11,
#     "read_pulse_freq": 559.17, # [MHz] actual frequency is this number + "cavity_LO"
#     ##### define tranmission experiment parameters
#     "TransSpan": 2, ### MHz, span will be center+/- this parameter
#     "TransNumPoitns": 200, ### number of points in the transmission frequecny
#     ##### the qubit frequency
#     "qubit_freq" : 264.071,
#     "qubit_pulse_style": "arb",
#     "sigma": 0.2,  ### units us, define a 20ns sigma
#     "relax_delay": 6000,  ### turned into us inside the run function
#     ##### amplitude rabi parameters
#     "qubit_gain_start": 0,
#     "qubit_gain_step": 200, ### stepping amount of the qubit gain
#     "qubit_gain_expts": 11, ### number of steps
#     "AmpRabi_reps": 500,  # number of averages for the experiment
#     "two_pulses": False, # If we want to calibrate a pi/2 pulse
# }
# config = BaseConfig | UpdateConfig
#
# yoko1.SetVoltage(config["yokoVoltage"])
#
# Instance_AmplitudeRabi_CavityPower = AmplitudeRabi_CavityPower(path="dataTestRabiAmpCavity", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg, progress=True)
# data_AmplitudeRabi_CavityPower = AmplitudeRabi_CavityPower.acquire(Instance_AmplitudeRabi_CavityPower)
# AmplitudeRabi_CavityPower.save_data(Instance_AmplitudeRabi_CavityPower, data_AmplitudeRabi_CavityPower)
# AmplitudeRabi_CavityPower.save_config(Instance_AmplitudeRabi_CavityPower)
# endregion

# ###TITLE: Interleaved T1 measurement
##region T1 Config
# UpdateConfig = {
#     ##### define attenuators
#     "yokoVoltage": -0.5,
#     ###### cavity
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 10, # us
#     "read_pulse_gain": 10000, # [DAC units]
#     "read_pulse_freq": 7392.6 , # [MHz] actual frequency is this number + "cavity_LO"
#     ##### spec parameters for finding the qubit frequency
#     "qubit_freq": 4830.0,
#     "qubit_gain": 22500,
#     "sigma": 0.005,  ### units us, define a 20ns sigma
#     "flat_top_length": 0.025,  ### in us
#     "qubit_pulse_style": "arb", #### arb means gaussain here
#     "relax_delay": 500,  ### turned into us inside the run function
#     ##### T1 parameters
#     "start": 0, ### us
#     "step": 10, ### us
#     "expts": 101, ### number of experiemnts
#     "reps": 2000, ### number of averages on each experiment
# }
# config = BaseConfig | UpdateConfig
#
# # small_update_config = {
# #     "start": 0, ### us
# #     "step": 100, ### us
# #     "expts": 4, ### number of experiemnts
# #     "reps": 3000, ### number of averages on each experiment
# # }
# # config = config | small_update_config
# #
# # print(config)
# # config = UpdateConfig
#
# yoko1.SetVoltage(config["yokoVoltage"])
# print("Voltage is ", yoko1.GetVoltage(), " Volts")
#
# Instance_T1Experiment = T1Experiment(path="dataTestT1Experiment", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg,  progress=True)
# data_T1Experiment = T1Experiment.acquire(Instance_T1Experiment)
# T1Experiment.display(Instance_T1Experiment, data_T1Experiment, plotDisp=True)
# T1Experiment.save_data(Instance_T1Experiment, data_T1Experiment)
# T1Experiment.save_config(Instance_T1Experiment)

# for idx in range(30):
#     Instance_T1Experiment = T1Experiment(path="dataTestT1Experiment", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg,  progress=True)
#     data_T1Experiment = T1Experiment.acquire(Instance_T1Experiment)
#     T1Experiment.display(Instance_T1Experiment, data_T1Experiment, plotDisp=True)
#     T1Experiment.save_data(Instance_T1Experiment, data_T1Experiment)
#     T1Experiment.save_config(Instance_T1Experiment)
# endregion

###TITLE: Basic single shot experiment looped with a variable of choice
# region Single Shot Config
# UpdateConfig = {
#     # set yoko
#     "yokoVoltage": -0.38,
#     # cavity
#     "reps": 2000,  # Repitions
#     "read_pulse_style": "const",
#     "read_length": 20,  # [us]
#     "read_pulse_gain": 6000,  # [DAC units]
#     "read_pulse_freq": 7392.4,  # [MHz]
#     # qubit spec parameters
#     "qubit_pulse_style": "flat_top",
#     "qubit_gain": 30000, # 4 * 6500,  # [DAC units]
#     "sigma": 0.25,  # [us]
#     "qubit_freq": 2974.6,  # [MHz]
#     "flat_top_length": 20,
#     "relax_delay": 3000,  ### turned into us inside the run function
#     # define shots
#     "shots": 5000,  ### this gets turned into "reps"
#     "use_switch": True,
# }
# config = BaseConfig | UpdateConfig
#
# yoko1.SetVoltage(config["yokoVoltage"])
#
# ##### run the single shot experiment on loop
# loop_len = 5
# # freq_vec = config["read_pulse_freq"] + np.linspace(-0.02, 0.2, loop_len)
# read_gain_vec = np.linspace(11000, 15000, loop_len, dtype=int)
# # read_len_vec = np.linspace(5, 25, loop_len, dtype=int)
# # # qubit_gain_vec = np.linspace(12000, 14000, loop_len, dtype=int)
# # # qubit_freq_vec = config["qubit_freq"] + np.linspace(-0.2, 0.2, loop_len)
#
# fid_vec = np.zeros((loop_len, loop_len))
# for idx in range(loop_len):
#     # for idy in range(loop_len):
#     #     config["read_pulse_freq"] = freq_vec[idx]
#         config["read_pulse_gain"] = read_gain_vec[idx]
#         # config["read_length"] = read_len_vec[idx]
#         # config["qubit_freq"] = qubit_freq_vec[idx]
#         # config["qubit_gain"] = qubit_gain_vec[idx]
#         Instance_SingleShotProgram = SingleShotProgram(path="dataTestSingleShotProgram", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
#         data_SingleShot = SingleShotProgram.acquire(Instance_SingleShotProgram)
#         SingleShotProgram.display(Instance_SingleShotProgram, data_SingleShot, plotDisp=True, save_fig=True, figNum=idx + 100)
#         SingleShotProgram.save_data(Instance_SingleShotProgram, data_SingleShot)
#         SingleShotProgram.save_config(Instance_SingleShotProgram)
#         fid_vec[idx] = Instance_SingleShotProgram.fid
#
# # 2d plot
# # X, Y = np.meshgrid(freq_vec, read_gain_vec)
# # Z = np.transpose(fid_vec)
# # plt.pcolor(X,Y,Z)
# # plt.xlabel("Read Pulse Frequency")
# # plt.ylabel("Read Pulse Gain")
# # plt.colorbar()
# # plt.tight_layout()
#
# # 1d plot
# x = read_gain_vec
# y = fid_vec
# plt.figure()
# plt.plot(x, y)
# plt.xlabel("Read Length (in us)")
# plt.ylabel("Fidelity")
# plt.tight_layout()
#
# datetimenow = datetime.datetime.now()
# name = "fidvsreadlength"+datetimenow.strftime("_%Y_%m_%d_%H_%M_%S")
# plt.savefig(outerFolder + "dataTestSingleShotProgram\\" + name, dpi = 600)
#
# Instance_SingleShotProgram = SingleShotProgram(path="dataTestSingleShotProgram", outerFolder=outerFolder, cfg=config,
#                                                soc=soc, soccfg=soccfg)
# data_SingleShot = SingleShotProgram.acquire(Instance_SingleShotProgram)
# SingleShotProgram.display(Instance_SingleShotProgram, data_SingleShot, plotDisp=True, save_fig=True)
# SingleShotProgram.save_data(Instance_SingleShotProgram, data_SingleShot)
# SingleShotProgram.save_config(Instance_SingleShotProgram)
# endregion

###TITLE: 2D single shot fidelity optimization
# region 2D single shot config
# UpdateConfig = {
#     ##### set yoko
#     "yokoVoltage": 0.815,
#     #### define basic parameters
#     ###### cavity
#     "reps": 2000,  # this will used for all experiements below unless otherwise changed in between trials
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 8, # [Clock ticks]
#     "read_pulse_gain": 11000, # [DAC units]
#     "read_pulse_freq": 5988.33, # [MHz]
#     ##### qubit spec parameters
#     "qubit_pulse_style": "arb",
#     "qubit_gain": 20000,
#     # "qubit_length": 10,  ###us, this is used if pulse style is const
#     "sigma": 0.300,  ### units us, define a 20ns sigma
#     "qubit_freq": 1715.6,
#     "relax_delay": 500,  ### turned into us inside the run function
#     #### define shots
#     "shots": 1000, ### this gets turned into "reps"
#     #### define the loop parameters
#     "x_var": "read_pulse_freq",
#     "x_start": 5988.27 - 0.5,
#     "x_stop": 5988.27 + 0.5,
#     "x_num": 51,
#
#     "y_var": "read_pulse_gain",
#     "y_start": 14500,
#     "y_stop": 15500,
#     "y_num": 5,
# }
# config = BaseConfig | UpdateConfig
#
# yoko1.SetVoltage(config["yokoVoltage"])
#
# Instance_SingleShot_2Dsweep = SingleShot_2Dsweep(path="dataTestSingleShot_2Dsweep", outerFolder=outerFolder, cfg=config,
#                                                soc=soc, soccfg=soccfg)
# data_SingleShot_2Dsweep = SingleShot_2Dsweep.acquire(Instance_SingleShot_2Dsweep)
# SingleShot_2Dsweep.save_data(Instance_SingleShot_2Dsweep, data_SingleShot_2Dsweep)
# SingleShot_2Dsweep.save_config(Instance_SingleShot_2Dsweep)
# endregion
#%%
# TITLE: Amplitude rabi Blob with post selection
UpdateConfig = {
    # Yoko
    "yokoVoltage": -1.509,

    # cavity
    "read_pulse_style": "const",
    "read_length": 80,
    "read_pulse_gain": 1000,
    "read_pulse_freq": 7391.9,

    # qubit tone parameters
    "qubit_freq_start": 460,
    "qubit_freq_stop": 510,
    "RabiNumPoints": 61,
    "qubit_pulse_style": "flat_top",
    "sigma": 1.0,
    "flat_top_length": 20,
    "relax_delay": 1000,
    "qubit_gain_start": 18000,
    "qubit_gain_step": 1000,
    "qubit_gain_expts": 12,

    # Experiment Parameters
    "cen_num": 2,
    "shots": 800,
    "use_switch": False,
}
config = BaseConfig | UpdateConfig

#yoko1.SetVoltage(config["yokoVoltage"])
#print("Voltage is ", yoko1.GetVoltage(), " Volts")

Instance_AmplitudeRabi_PS = AmplitudeRabi_PS(path="dataTestAmplitudeRabi_PS", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg, progress=True)
data_AmplitudeRabi_PS = AmplitudeRabi_PS.acquire(Instance_AmplitudeRabi_PS)
AmplitudeRabi_PS.save_data(Instance_AmplitudeRabi_PS, data_AmplitudeRabi_PS)
AmplitudeRabi_PS.save_config(Instance_AmplitudeRabi_PS)
#%%

###TITLE: Amplitude rabi Blob while sweeping flux
# region Amplitude Rabi Blob vs Flux Config
# UpdateConfig = {
#     ##### define attenuators
#     "yokoVoltage": 0.87,
#     ###### cavity
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 10, # us
#     "read_pulse_gain": 14500, # [DAC units]
#     "read_pulse_freq": 8891.2, # [MHz]
#     ##### spec parameters for finding the qubit frequency
#     "qubit_freq_start": 303,
#     "qubit_freq_stop": 304.5,
#     "RabiNumPoints": 31,  ### number of points
#     "qubit_pulse_style": "arb",
#     "sigma": 1,  ### units us, define a 20ns sigma
#     "qubit_gain": 17000,
#     # "flat_top_length": 0.025, ### in us
#     "relax_delay": 3000,  ### turned into us inside the run function
#     ##### define the yoko voltage
#     "yokoVoltageStart": 0.85,
#     "yokoVoltageStop": 0.9,
#     "yokoVoltageNumPoints": 11,
#     # "AmpRabi_reps": 2000,  # number of averages for the experiment
#     ##### define number of clusters to use
#     "cen_num": 3,
#     "shots": 2000,  ### this gets turned into "reps"
# }
# config = BaseConfig | UpdateConfig
#
# yoko1.SetVoltage(config["yokoVoltage"])
#
# Instance_AmplitudeRabiFlux_PS = AmplitudeRabiFlux_PS(path="dataTestAmplitudeRabiFlux_PS", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg, progress=True)
# data_AmplitudeRabiFlux_PS = AmplitudeRabiFlux_PS.acquire(Instance_AmplitudeRabiFlux_PS)
# AmplitudeRabiFlux_PS.save_data(Instance_AmplitudeRabiFlux_PS, data_AmplitudeRabiFlux_PS)
# AmplitudeRabiFlux_PS.save_config(Instance_AmplitudeRabiFlux_PS)
# endregion

#%%

###TITLE: Qubit spec on repeat
# region Spec on repeat Config
UpdateConfig = {
    ##### define attenuators
    "yokoVoltage": -1.467,
    ###### cavity
    "read_pulse_style": "const", # --Fixed
    "read_length": 15, # us
    "read_pulse_gain": 8000, # [DAC units]
    "read_pulse_freq": 7391.9441,
    ##### spec parameters for finding the qubit frequency
    "qubit_freq_start": 900, #1167-10
    "qubit_freq_stop": 980,
    "SpecNumPoints": 101,  ### number of points
    "qubit_pulse_style": "arb",
    "qubit_length": 1, # us, changes experiment time but is necessary for "const" style
    "sigma": 0.5,  ### units us, define a 20ns sigma
    # "qubit_length": 1, ### units us, doesnt really get used though
    # "flat_top_length": 0.025, ### in us
    "relax_delay": 10,  ### turned into us inside the run function
    "qubit_gain": 32000, # Constant gain to use
    # "qubit_gain_start": 18500, # shouldn't need this...
    "reps": 5000, # number of averages of every experiment
    ##### time parameters
    "delay":  30, # s
    "repetitions": 60,  ### number of steps
}
config = BaseConfig | UpdateConfig

yoko.SetVoltage(config["yokoVoltage"])
# #
Instance_QubitSpecRepeat = QubitSpecRepeat(path="dataQubitSpecRepeat", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg, progress=True)
data_QubitSpecRepeat = QubitSpecRepeat.acquire(Instance_QubitSpecRepeat)
QubitSpecRepeat.save_data(Instance_QubitSpecRepeat, data_QubitSpecRepeat)
QubitSpecRepeat.save_config(Instance_QubitSpecRepeat)

#%%

# #
# for idx in range(4):
#     Instance_QubitSpecRepeat = QubitSpecRepeat(path="dataQubitSpecRepeat", outerFolder=outerFolder, cfg=config, soc=soc,
#                                                soccfg=soccfg, progress=True)
#     data_QubitSpecRepeat = QubitSpecRepeat.acquire(Instance_QubitSpecRepeat)
#     QubitSpecRepeat.save_data(Instance_QubitSpecRepeat, data_QubitSpecRepeat)
#     QubitSpecRepeat.save_config(Instance_QubitSpecRepeat)
# endregion

###TITLE: Qubit ef spectroscopy
# region EF Spec Config
# UpdateConfig = {
#     ##### define attenuators
#     "yokoVoltage": 0,
#     ###### cavity
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 10, # us
#     "read_pulse_gain": 4100, # [DAC units]
#     "read_pulse_freq": 5743,
#     # g-e parameters
#     "qubit_ge_freq": 4655.75, # MHz
#     "qubit_ge_gain": 15000, # Gain for pi pulse in DAC units
#     ##### spec parameters for finding the qubit frequency
#     "qubit_ef_freq_start": 4482, #1167-10
#     "qubit_ef_freq_step": 0.1,
#     "SpecNumPoints": 101,  ### number of points
#     "qubit_pulse_style": "arb",
#     "qubit_length": 1, # us, changes experiment time but is necessary for "const" style
#     "sigma": 0.088,  ### units us, define a 20ns sigma
#     # "qubit_length": 1, ### units us, doesn't really get used though
#     # "flat_top_length": 0.025, ### in us
#     "relax_delay": 500,  ### turned into us inside the run function
#     "qubit_gain": 10000, # Constant gain to use
#     # "qubit_gain_start": 18500, # shouldn't need this...
#     "reps": 3000, # number of averages of every experiment
# }
# config = BaseConfig | UpdateConfig
#
# yoko1.SetVoltage(config["yokoVoltage"])
# # #
# Instance_Qubit_ef_spectroscopy = Qubit_ef_spectroscopy(path="dataQubit_ef_spectroscopy", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg, progress=True)
# data_Qubit_ef_spectroscopy = Qubit_ef_spectroscopy.acquire(Instance_Qubit_ef_spectroscopy)
# Qubit_ef_spectroscopy.save_data(Instance_Qubit_ef_spectroscopy, data_Qubit_ef_spectroscopy)
# Qubit_ef_spectroscopy.save_config(Instance_Qubit_ef_spectroscopy)
# Qubit_ef_spectroscopy.display(Instance_Qubit_ef_spectroscopy, data_Qubit_ef_spectroscopy, plotDisp=True)

# plt.show()
# endregion

###TITLE: Qubit ef Rabi
# region EF Rabi Config
# UpdateConfig = {
#     ##### define attenuators
#     "yokoVoltage": 0,
#     ###### cavity
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 10, # us
#     "read_pulse_gain": 4100, # [DAC units]
#     "read_pulse_freq": 5743,
#     ###### qubit
#     # g-e parameters
#     "qubit_ge_freq": 4655.75, # MHz
#     "qubit_ge_gain": 15000, # Gain for pi pulse in DAC units
#     "apply_ge": True,
#    # e-f parameters
#     "qubit_ef_freq": 4487.8,
#     "qubit_ef_gain_start": 0, #1167-10
#     "qubit_ef_gain_step": 300,
#     "RabiNumPoints": 101,  ### number of points
#     "qubit_pulse_style": "arb",
#     "qubit_length": 1, # us, changes experiment time but is necessary for "const" style
#     "sigma": 0.088,  ### units us, define a 20ns sigma
#     # "qubit_length": 1, ### units us, doesnt really get used though
#     # "flat_top_length": 0.025, ### in us
#     "relax_delay": 1000,  ### turned into us inside the run function
#     "qubit_gain": 25000, # Constant gain to use
#     # "qubit_gain_start": 18500, # shouldn't need this...
#     "reps": 1500, # number of averages of every experiment
# }
# config = BaseConfig | UpdateConfig
#
# yoko1.SetVoltage(config["yokoVoltage"])
# # #
# Instance_Qubit_ef_rabi = Qubit_ef_rabi(path="dataQubit_ef_rabi", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg, progress=True)
# data_Qubit_ef_rabi = Qubit_ef_rabi.acquire(Instance_Qubit_ef_rabi)
# Qubit_ef_rabi.save_data(Instance_Qubit_ef_rabi, data_Qubit_ef_rabi)
# Qubit_ef_rabi.save_config(Instance_Qubit_ef_rabi)
# Qubit_ef_rabi.display(Instance_Qubit_ef_rabi, data_Qubit_ef_rabi, plotDisp=True)
# endregion

###TITLE: Single Shot of g-e-f
# region Single Shot g-e-f Config
# UpdateConfig = {
#     # set yoko
#     "yokoVoltage": 00,
#     # cavity
#     "reps": 1000,  # Repitions
#     "read_pulse_style": "const",
#     "read_length": 10, # [us]
#     "read_pulse_gain": 4000, # [DAC units]
#     "read_pulse_freq": 5753.5, # [MHz]
#     # qubit g-e pulse
#     "qubit_pulse_style": "arb",
#     "qubit_ge_gain": 4*6500, # [DAC units]
#     "sigma": 0.2/4,  # [us]
#     "qubit_ge_freq": 4655, # [MHz]
#     "relax_delay": 1000,  ### turned into us inside the run function
#     "qubit_length": 1,
#     # qubit e-f pulse
#     "qubit_ef_freq": 4487.6,
#     "qubit_ef_gain": 25244,
#     # define shots
#     "shots": 3000, ### this gets turned into "reps"
# }
# config = BaseConfig | UpdateConfig
#
# # Set the YOKO Voltage
# yoko1.SetVoltage(config["yokoVoltage"])
#
# # Run the experiment
# Instance_SingleShotProgram = SingleShotProgram_g_e_f(path="dataTestSingleShotProgram", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
# data_SingleShot = SingleShotProgram_g_e_f.acquire(Instance_SingleShotProgram)
# SingleShotProgram_g_e_f.save_data(Instance_SingleShotProgram, data_SingleShot)
# SingleShotProgram_g_e_f.save_config(Instance_SingleShotProgram)
# SingleShotProgram_g_e_f.display(Instance_SingleShotProgram, data_SingleShot, plotDisp=True, save_fig=True)
# endregion

###TITLE: Single Shot for individual states
# region Single shot for individual states config
# UpdateConfig = {
#     # set yoko
#     "yokoVoltage": 0,
#     # cavity
#     "reps": 1000,  # Repitions
#     "read_pulse_style": "const",
#     "read_length": 10, # [us]
#     "read_pulse_gain": 4100, # [DAC units]
#     "read_pulse_freq": 5743, # [MHz]
#     # qubit g-e pulse
#     "qubit_pulse_style": "arb",
#     "qubit_ge_gain": 15000, # [DAC units]
#     "sigma": 0.088,  # [us]
#     "qubit_ge_freq": 4655.75, # [MHz]
#     "relax_delay": 5000,  ### turned into us inside the run function
#     "qubit_length": 1,
#     # qubit e-f pulse
#     "qubit_ef_freq": 4487.8,
#     "qubit_ef_gain": 16541,
#     # define shots
#     "shots": 4000, ### this gets turned into "reps"
# }
# config = BaseConfig | UpdateConfig
#
# # Set the YOKO Voltage
# yoko1.SetVoltage(config["yokoVoltage"])
#
# # Run the experiment
# Instance_SingleShotProgram = SingleShotProgram_individual_state(path="dataTestSingleShotProgram", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
# data_SingleShot = SingleShotProgram_individual_state.acquire(Instance_SingleShotProgram)
# SingleShotProgram_individual_state.save_data(Instance_SingleShotProgram, data_SingleShot)
# SingleShotProgram_individual_state.save_config(Instance_SingleShotProgram)
# SingleShotProgram_individual_state.display(Instance_SingleShotProgram, data_SingleShot, plotDisp=True, save_fig=True)
# endregion

###TITLE: Single Shot E-F across different variables
# region Single shot E-F across different variables
# UpdateConfig = {
#     # set yoko
#     "yokoVoltage": 0,
#     # cavity
#     "reps": 1000,  # Repitions
#     "read_pulse_style": "const",
#     "read_length": 10, # [us]
#     "read_pulse_gain": 4100, # [DAC units]
#     "read_pulse_freq": 5745.5, # [MHz]
#     # qubit g-e pulse
#     "qubit_pulse_style": "arb",
#     "qubit_ge_gain": 15000, # [DAC units]
#     "sigma": 0.088,  # [us]
#     "qubit_ge_freq": 4655.75, # [MHz]
#     "relax_delay": 3000,  ### turned into us inside the run function
#     "qubit_length": 1,
#     # qubit e-f pulse
#     "qubit_ef_freq": 4487.8,
#     "qubit_ef_gain": 15300,
#     # define shots
#     "shots": 2000, ### this gets turned into "reps"
# }
# config = BaseConfig | UpdateConfig
#
# # Set the YOKO Voltage
# yoko1.SetVoltage(config["yokoVoltage"])
# #
# # # # Parameter to vary
# read_pulse_gain_arr = np.linspace(1000,10000,11, dtype = int)
# #
# # # Run the experiment
# # plt.clf()
# for i in tqdm(range(read_pulse_gain_arr.size)):
#     config["read_pulse_gain"] = read_pulse_gain_arr[i]
#     Instance_SingleShotProgram = SingleShotProgram_ef(path="dataTestSingleShot_ef_readgain", outerFolder=outerFolder, cfg=config,
#                                                       soc=soc, soccfg=soccfg)
#     data_SingleShot = SingleShotProgram_ef.acquire(Instance_SingleShotProgram)
#     SingleShotProgram_ef.save_data(Instance_SingleShotProgram, data_SingleShot)
#     SingleShotProgram_ef.save_config(Instance_SingleShotProgram)
#     SingleShotProgram_ef.display(Instance_SingleShotProgram, data_SingleShot, plotDisp=True, save_fig=True)
#     plt.clf()
#     plt.close()

# Instance_SingleShotProgram = SingleShotProgram_ef(path="dataTestSingleShot_ef_readgain", outerFolder=outerFolder, cfg=config,
#                                                       soc=soc, soccfg=soccfg)
# data_SingleShot = SingleShotProgram_ef.acquire(Instance_SingleShotProgram)
# SingleShotProgram_ef.save_data(Instance_SingleShotProgram, data_SingleShot)
# SingleShotProgram_ef.save_config(Instance_SingleShotProgram)
# SingleShotProgram_ef.display(Instance_SingleShotProgram, data_SingleShot, plotDisp=True, save_fig=True)

# endregion

#%%

###TITLE: Qubit RPM
#region Qubit RPM Config File
# print("sleeping 7200, zzz...")
# time.sleep(7200)
# print("rise and shine!")
# print(time.localtime())
# UpdateConfig = {
#     ##### define attenuators
#     "yokoVoltage": 0,
#     ###### cavity
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 10, # us
#     "read_pulse_gain": 6400, # [DAC units]
#     "read_pulse_freq": 5745.5,
#     ###### qubit
#     # g-e parameters
#     "qubit_ge_freq": 4655.75, # MHz
#     "qubit_ge_gain": 15000, # Gain for pi pulse in DAC units
#     "apply_ge": False,
#    # e-f parameters
#     "qubit_ef_freq": 4487.8,
#     "qubit_ef_gain_start": 0, #1167-10
#     "qubit_ef_gain_step": 1500,
#     "RabiNumPoints": 21,  ### number of points
#     "qubit_pulse_style": "arb",
#     "qubit_length": 1, # us, changes experiment time but is necessary for "const" style
#     "sigma": 0.088,  ### units us, define a 20ns sigma
#     "relax_delay": 2000,  ### turned into us inside the run function
#     "g_reps": 5000, # number of averages of every experiment
#     "e_reps": 400000, # number of averages of every experiment
#     "reps": 1
# }
# config = BaseConfig | UpdateConfig
#
# yoko1.SetVoltage(config["yokoVoltage"])
# # #
# Instance_Qubit_ef_rabi = Qubit_ef_RPM(path="dataQubit_ef_RPM", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg, progress=True)
# data_Qubit_ef_rabi = Qubit_ef_RPM.acquire(Instance_Qubit_ef_rabi)
# print(time.localtime())
# Qubit_ef_RPM.save_data(Instance_Qubit_ef_rabi, data_Qubit_ef_rabi)
# Qubit_ef_RPM.save_config(Instance_Qubit_ef_rabi)
# Qubit_ef_RPM.display(Instance_Qubit_ef_rabi, data_Qubit_ef_rabi, plotDisp=True)
#endregion

#%%
# TITLE: T2 Ramsey

UpdateConfig = {
    # Readout Parameters
    "read_pulse_style": "const",
    "read_length": 52,
    "read_pulse_gain": 1800,
    "read_pulse_freq": 6230.509,

    # Qubit Parameters
    "qubit_freq": 471.4 ,
    "pi_qubit_gain": 3000,
    "pi2_qubit_gain": 1500,
    "sigma": 0.40,
    "qubit_pulse_style": "arb",

    # Experiment Parameters
    "start": 0,
    "step": 0.2,
    "expts": 101,                   # Number of steps
    "yokoVoltage": 1.2869,
    "relax_delay": 4000,
    "reps": 5000,
}

config = BaseConfig | UpdateConfig
yoko1.SetVoltage(config["yokoVoltage"])




#%%
# Run experiment
inst_t2r = T2Experiment(path="dataTestT2Experiment", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
data_t2r = inst_t2r.acquire()
inst_t2r.display(data_t2r, plotDisp=True)
inst_t2r.save_data(data_t2r)
inst_t2r.save_config()

#%%
# TITLE: Two two parametric qubit cooling through resonator

UpdateConfig = {
    # Readout Parameters
    "read_length": 35,
    "read_pulse_gain": 15000,
    "read_pulse_freq": 6423.085,

    # Parametric drive parameters
    "cavity_drive_gain": 30000, # DAC units
    "qubit_drive_gain": 30000, # DAC units
    "qubit_freq": 943, # MHz
    "Delta": 3, #MHz
    "T": 50, # us

    # delta sweep parameters
    "start" : -8, # MHz
    "stop": 3, # MHz
    "steps": 21, # integer
    "sweep": "delta",

    # Experiment Parameters
    "yokoVoltage": 0.22,
    "relax_delay": 10, # us
    "reps": 30000,
    "use_switch": False
}

config = BaseConfig | UpdateConfig
yoko1.SetVoltage(config["yokoVoltage"])

inst_q2trc = QubitTwoToneResonatorCoolExperiment(path="dataQubit2TResonatorCool", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
data_q2trc = inst_q2trc.acquire()
inst_q2trc.display()
#inst_t2r.save_data(data_t2r)
#inst_t2r.save_config()

#%%
# region T2 Echo
#####################################################################################################################
######## T2 echo measurement
# UpdateConfig = {
#     ##### define attenuators
#     "yokoVoltage": 0.0,
#     ###### cavity
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 10, # us
#     "read_pulse_gain": 4000, # [DAC units]
#     "read_pulse_freq": 5747.5, # [MHz] actual frequency is this number + "cavity_LO"
#     ##### spec parameters for finding the qubit frequency
#     "qubit_freq": 4656.0,
#     "pi_qubit_gain": 25000, # Gain of pi pulse
#     "pi2_qubit_gain": 12500, # Gain of pi/2 pulse
#     "sigma": 0.050,  ### units us, define a 20ns sigma
#     "qubit_pulse_style": "arb", #### arb means gaussain here
#     "relax_delay": 500,  ### turned into us inside the run function
#     ##### T1 parameters
#     "start": 0, ### us
#     "step": 2, ### us
#     "expts": 101, ### number of experiemnts
#     "reps": 1000, ### number of averages on each experiment
# }
# config = BaseConfig | UpdateConfig
# yoko1.SetVoltage(config["yokoVoltage"])
# print("Voltage is ", yoko1.GetVoltage(), " Volts")
#
# Instance_T2EchoExperiment = T2EchoExperiment(path="dataTestT2EchoExperiment", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg,  progress=True)
# data_T2EchoExperiment = T2EchoExperiment.acquire(Instance_T2EchoExperiment)
# T2EchoExperiment.display(Instance_T2EchoExperiment, data_T2EchoExperiment, plotDisp=True)
# T2EchoExperiment.save_data(Instance_T2EchoExperiment, data_T2EchoExperiment)
# T2EchoExperiment.save_config(Instance_T2EchoExperiment)
# endregion


plt.show()
#%%
#TITLE: Fast Flux DC voltage Trans Slice

UpdateConfig = {
    # Readout section
    "read_pulse_style": "const",  # --Fixed
    "read_length": 13,  # [us]
    "read_pulse_gain": 5600,  # [DAC units]
    "ro_mode_periodic": False,  # Bool: if True, keeps readout tone on always

    # Fast flux pulse parameters
    "ff_gain": 500,  # [DAC units] Gain for fast flux pulse
    "ff_ch": 6,  # RFSOC output channel of fast flux drive
    "ff_nqz": 1,  # Nyquist zone to use for fast flux drive

    # Transmission Experiment. Parameter naming convention preserved from mTransmission_SaraTest below
    # "read_pulse_freq": 7000,        # [MHz] Centre frequency of transmission sweep
    # "TransSpan": 5,                 # [MHz] Span of transmission sweep
    # "TransNumPoints": 301,          # Number of poitns in transmission sweep

    # New format parameters for transmission experiment
    "start_freq": 7391.9 - 2,  # [MHz] Start frequency of sweep
    "stop_freq": 7391.9 + 2,  # [MHz] Stop frequency of sweep
    "num_freqs": 301,  # Number of frequency points to use
    "init_time": 5,  # [us] Thermalisation time after FF to new point before starting measurement
    "measure_at_0": True,  # [Bool] Do we go back to 0 DAC units on the FF to measure?

    "yokoVoltage": -1.494,  # [V] Yoko voltage for DC component of fast flux
    "relax_delay": 10,  # [us] Delay after measurement before starting next measurement
    "reps": 1000,  # Reps of measurements; init program is run only once
    "sets": 5,  # Sets of whole measurement; used in GUI
    "RFSOC_delay": 0,
}

config = BaseConfig | UpdateConfig
yoko.SetVoltage(config["yokoVoltage"])

Instance_FFTransSlice = FFTransSlice_Experiment(path="FFTransSlice", cfg=config,soc=soc,soccfg=soccfg,
                                              outerFolder = outerFolder, short_directory_names = True)

# Estimate Time
time = Instance_FFTransSlice.estimate_runtime()
print("Time for ff spec experiment is about ", time, " s")

try:
    data_FFTransSlice = FFTransSlice_Experiment.acquire(Instance_FFTransSlice, progress = True)
    FFTransSlice_Experiment.display(Instance_FFTransSlice, data_FFTransSlice, plot_disp=True)
    FFTransSlice_Experiment.save_data(Instance_FFTransSlice, data_FFTransSlice)
    FFTransSlice_Experiment.save_config(Instance_FFTransSlice)
    # print(Instance_specSlice.qubitFreq)
    plt.show()
except Exception:
    print("Pyro traceback:")
    print("".join(Pyro4.util.getPyroTraceback()))


#%%
#TITLE: Fast Flux DC voltage Trans vs Flux

UpdateConfig = {
    # Readout section
    "read_pulse_style": "const",  # --Fixed
    "read_length": 13,  # [us]
    "read_pulse_gain": 5600,  # [DAC units]
    "ro_mode_periodic": False,  # Bool: if True, keeps readout tone on always

    # Fast flux pulse parameters
    "ff_pulse_style": "const",  # one of ["const", "flat_top", "arb"], currently only "const" is supported
    "ff_ch": 6,  # RFSOC output channel of fast flux drive
    "ff_nqz": 1,  # Nyquist zone to use for fast flux drive

    # ff_gain sweep parameters: DAC value of fast flux pulse endpoint
    "ff_gain_start": -100,  # [DAC] Initial value
    "ff_gain_stop": 300,  # [DAC] Final value
    "ff_gain_steps": 101,  # number of qubit_spec_delay points to take

    # Transmission Experiment. Parameter naming convention preserved from mTransmission_SaraTest below
    # "read_pulse_freq": 7000,        # [MHz] Centre frequency of transmission sweep
    # "TransSpan": 5,                 # [MHz] Span of transmission sweep
    # "TransNumPoints": 301,          # Number of poitns in transmission sweep

    # New format parameters for transmission experiment
    "start_freq": 7390.5,  # [MHz] Start frequency of sweep
    "stop_freq": 7393,  # [MHz] Stop frequency of sweep
    "num_freqs": 301,  # Number of frequency points to use
    "init_time": 100000,  # [us] Thermalisation time after FF to new point before starting measurement
    "therm_time": 1000,  # [us] Thermalisation time after moving FF down to 0 for measurement, if measure_at_0
    "measure_at_0": True,  # [Bool] Do we go back to 0 DAC units on the FF to measure?

    "yokoVoltage": -1.494,  # [V] Yoko voltage for DC component of fast flux
    "relax_delay": 10,  # [us] Delay after measurement before starting next measurement
    "reps": 500,  # Reps of measurements; init program is run only once
    "sets": 5,  # Sets of whole measurement; used in GUI
    "RFSOC_delay": 0,
}

config = BaseConfig | UpdateConfig
yoko.SetVoltage(config["yokoVoltage"])

Instance_FFTransVsFlux = FFTransVsFlux_Experiment(path="FFTransVsFlux", cfg=config,soc=soc,soccfg=soccfg,
                                              outerFolder = outerFolder, short_directory_names = True)

# Estimate Time
time = Instance_FFTransVsFlux.estimate_runtime()
print("Time for ff spec experiment is about ", time, " s")

try:
    data_FFTransVsFlux = FFTransVsFlux_Experiment.acquire(Instance_FFTransVsFlux, progress = True)
    FFTransVsFlux_Experiment.display(Instance_FFTransVsFlux, data_FFTransVsFlux, plot_disp=True)
    FFTransVsFlux_Experiment.save_data(Instance_FFTransVsFlux, data_FFTransVsFlux)
    FFTransVsFlux_Experiment.save_config(Instance_FFTransVsFlux)
    # print(Instance_specSlice.qubitFreq)
    plt.show()
except Exception:
    print("Pyro traceback:")
    print("".join(Pyro4.util.getPyroTraceback()))

#%%
#TITLE: Fast Flux DC voltage Spec Slice

UpdateConfig = {
    # Readout section
    "read_pulse_style": "const",     # --Fixed
    "read_length": 13,                # [us]
    "read_pulse_gain": 5600,         # [DAC units]
    "read_pulse_freq": 7391.9,      # [MHz]
    "ro_mode_periodic": False,  # currently unused

    # Qubit spec parameters
    "qubit_freq_start": 10,        # [MHz]
    "qubit_freq_stop": 110,         # [MHz]
    "qubit_pulse_style": "flat_top", # one of ["const", "flat_top", "arb"]
    "sigma": 0.0250,                  # [us], used with "arb" and "flat_top"
    "qubit_length": 0.2,               # [us], used with "const"
    "flat_top_length": 0.05,        # [us], used with "flat_top"
    "qubit_gain": 32000,             # [DAC units]
    "qubit_ch": 1,                   # RFSOC output channel of qubit drive
    "qubit_nqz": 1,                  # Nyquist zone to use for qubit drive
    "qubit_mode_periodic": False,    # Currently unused, applies to "const" drive
    "qubit_spec_delay": 0.,          # [us] Delay before qubit pulse

    # Fast flux pulse parameters
    "ff_gain": 630,                  # [DAC units] Gain for fast flux pulse
    "ff_length": 0.15,                  # [us] Total length of positive fast flux pulse
    "pre_ff_delay": 0,               # [us] Delay before the fast flux pulse
    "ff_pulse_style": "const",
    "ff_ch": 6,                      # RFSOC output channel of fast flux drive
    "ff_nqz": 1,                     # Nyquist zone to use for fast flux drive

    "yokoVoltage": -1.494,           # [V] Yoko voltage for DC component of fast flux
    "relax_delay": 10,               # [us]
    "qubit_freq_expts": 51,         # number of points
    "reps": 50000,
    "use_switch": False,
}

config = BaseConfig | UpdateConfig
yoko.SetVoltage(config["yokoVoltage"])

Instance_FFSpecSlice = FFSpecSlice_Experiment(path="FFSpecSlice", cfg=config,soc=soc,soccfg=soccfg,
                                              outerFolder = outerFolder, short_directory_names = True)

# Estimate Time
time = Instance_FFSpecSlice.estimate_runtime()
print("Time for ff spec experiment is about ", time, " s")

data_FFSpecSlice = FFSpecSlice_Experiment.acquire(Instance_FFSpecSlice, progress = True)
FFSpecSlice_Experiment.display(Instance_FFSpecSlice, data_FFSpecSlice, plot_disp=True)
FFSpecSlice_Experiment.save_data(Instance_FFSpecSlice, data_FFSpecSlice)
FFSpecSlice_Experiment.save_config(Instance_FFSpecSlice)
# print(Instance_specSlice.qubitFreq)
plt.show()

#%%
#TITLE: Fast Flux DC voltage Spec vs Delay

UpdateConfig = {
    # Readout section
    "read_pulse_style": "const",     # --Fixed
    "read_length": 13,                # [us]
    "read_pulse_gain": 5600,         # [DAC units]
    "read_pulse_freq": 7391.9,      # [MHz]
    "ro_mode_periodic": False,  # currently unused

    # Qubit spec parameters
    "qubit_freq_start": 500,        # [MHz]
    "qubit_freq_stop": 1050,         # [MHz]
    "qubit_pulse_style": "flat_top", # one of ["const", "flat_top", "arb"]
    "sigma": 0.05,                  # [us], used with "arb" and "flat_top"
    "qubit_length": 0.05,               # [us], used with "const"
    "flat_top_length": 0.05,        # [us], used with "flat_top"
    "qubit_gain": 32000,             # [DAC units]
    "qubit_ch": 1,                   # RFSOC output channel of qubit drive
    "qubit_nqz": 1,                  # Nyquist zone to use for qubit drive
    "qubit_mode_periodic": False,    # Currently unused, applies to "const" drive

    # Fast flux pulse parameters
    "ff_gain": 200,                  # [DAC units] Gain for fast flux pulse
    "ff_length": 0.1,                  # [us] Total length of positive fast flux pulse
    "pre_ff_delay": 0.1,               # [us] Delay before the fast flux pulse
    "ff_pulse_style": "const",
    "ff_ch": 6,                      # RFSOC output channel of fast flux drive
    "ff_nqz": 1,                     # Nyquist zone to use for fast flux drive

    "yokoVoltage": -1.494,           # [V] Yoko voltage for DC component of fast flux
    "relax_delay": 5,               # [us]
    "qubit_freq_expts": 25,         # number of points
    "reps": 20000,
    "use_switch": False,

    # post_ff_delay sweep parameters: delay after fast flux pulse (before qubit pulse)
    "qubit_spec_delay_start": 0.0,  # [us] Initial value
    "qubit_spec_delay_stop": 0.21,      # [us] Final value
    "qubit_spec_delay_steps": 5,    # number of post_ff_delay points to take
}

config = BaseConfig | UpdateConfig
yoko.SetVoltage(config["yokoVoltage"])

Instance_FFSpecVsDelay = FFSpecVsDelay_Experiment(path="FFSpecVsDelay", cfg=config,soc=soc,soccfg=soccfg,
                                              outerFolder = outerFolder, short_directory_names = True)

# Estimate Time
time = Instance_FFSpecVsDelay.estimate_runtime()
print("Time for ff spec experiment is about ", time, " s")

try:
    data_FFSpecVsDelay = FFSpecVsDelay_Experiment.acquire(Instance_FFSpecVsDelay, progress = True)
    FFSpecVsDelay_Experiment.display(Instance_FFSpecVsDelay, data_FFSpecVsDelay, plot_disp=True)
    FFSpecVsDelay_Experiment.save_data(Instance_FFSpecVsDelay, data_FFSpecVsDelay)
    FFSpecVsDelay_Experiment.save_config(Instance_FFSpecVsDelay)
    # print(Instance_specSlice.qubitFreq)
    plt.show()
except Exception:
    print("Pyro traceback:")
    print("".join(Pyro4.util.getPyroTraceback()))


#%%
#TITLE: Fast flux ramp test experiment

config = {
        # Readout section
        "read_pulse_style": "const",  # --Fixed
        "read_length": 13,  # [us]
        "read_pulse_gain": 5600, #5600,  # [DAC units]
        "read_pulse_freq": 7391.9,  # [MHz]

        # Fast flux pulse parameters
        "ff_ramp_style": "linear",  # one of ["linear"]
        "ff_ramp_start": 1150, # [DAC units] Starting amplitude of ff ramp, -32766 < ff_ramp_start < 32766
        "ff_ramp_stop": 1300, # [DAC units] Ending amplitude of ff ramp, -32766 < ff_ramp_stop < 32766
        "ff_delay": 10000, # [us] Delay between fast flux ramps
        "ff_ch": 6,  # RFSOC output channel of fast flux drive
        "ff_nqz": 1,  # Nyquist zone to use for fast flux drive

        # Optional qubit pulse before measurement, intended as pi/2 to populate both blobs
        "qubit_pulse": True,  # [bool] Whether to apply the optional qubit pulse at the beginning
        "qubit_freq": 943,  # [MHz] Frequency of qubit pulse
        "qubit_pulse_style": "arb",  # one of ["const", "flat_top", "arb"]
        "sigma": 0.50,  # [us], used with "arb" and "flat_top"
        "qubit_length": 1,  # [us], used with "const"
        "flat_top_length": 1,  # [us], used with "flat_top"
        "qubit_gain": 32000,  # [DAC units]
        "qubit_ch": 1,  # RFSOC output channel of qubit drive
        "qubit_nqz": 1,  # Nyquist zone to use for qubit drive

        # Ramp sweep parameters
        "ff_ramp_length_start": 0.02,  # [us] Total length of positive fast flux pulse, start of sweep
        "ff_ramp_length_stop": 0.1,  # [us] Total length of positive fast flux pulse, end of sweep
        "ff_ramp_length_expts": 15, # [int] Number of points in the ff ramp length sweep
        "yokoVoltage": -1.478,  # [V] Yoko voltage for magnet offset of flux
        "relax_delay_1": 0.2,# - BaseConfig["adc_trig_offset"],  # [us] Relax delay after first readout
        "relax_delay_2": 20 - BaseConfig["adc_trig_offset"], # [us] Relax delay after second readout

        # Gain sweep parameters
        "ff_gain_expts": 3,    # [int] How many different ff ramp gains to use
        "ff_ramp_length": 0.01,    # [us] Half-length of ramp to use when sweeping gain

        # Number of cycle repetitions sweep parameters
        "cycle_number_expts": 2,     # [int] How many different values for number of cycles around to use in this experiment
        "max_cycle_number": 10,        # [int] What is the largest number of cycles to use in sweep? Smallest value always 1
        "cycle_delay": 0.005,          # [us] How long to wait between cycles in one experiment?

        # General parameters
        "sweep_type": 'ff_gain',  # [str] What to sweep? 'ramp_length', 'ff_gain', 'cycle_number'
        "reps": 1000,
        "sets": 5,
        "angle": None, # [radians] Angle of rotation for readout
        "threshold": None, # [DAC units] Threshold between g and e
        "confidence": 0.999,
        "plot_all_points": True,
        "verbose": True,
    }

# We have 65536 samples (9.524 us) wave memory on the FF channel (and all other channels)

yoko.SetVoltage(config["yokoVoltage"])

mlbf_filter = MLBFDriver("192.168.1.11")
filter_freq = (config["read_pulse_freq"])
mlbf_filter.set_frequency(int(filter_freq))

config = BaseConfig | config
# length = 1.5
#from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mFFRampTest import FFRampTest
#prog = FFRampTest(soccfg, cfg | {"ff_ramp_length": length})

Instance_FFRampTest = FFRampTest_Experiment(path="FFRampTest", cfg=config,soc=soc,soccfg=soccfg,
                                              outerFolder = outerFolder, short_directory_names = True)

# Estimate Time
time = Instance_FFRampTest.estimate_runtime()
print("Time for ff spec experiment is about ", time, " s")


try:
    data_FFRampTest = FFRampTest_Experiment.acquire(Instance_FFRampTest, progress = True)
    FFRampTest_Experiment.display(Instance_FFRampTest, data_FFRampTest, plot_disp=True,
                                  plot_all_points=config['plot_all_points'])
    FFRampTest_Experiment.save_data(Instance_FFRampTest, data_FFRampTest)
    FFRampTest_Experiment.save_config(Instance_FFRampTest)
except Exception:
    print("Pyro traceback:")
    print("".join(Pyro4.util.getPyroTraceback()))

# print(Instance_specSlice.qubitFreq)
plt.show()

#%%
#TITLE: Fast Flux DC voltage Spec vs FLUX

UpdateConfig = {
    # Readout section
    "read_pulse_style": "const",     # --Fixed
    "read_length": 13,                # [us]
    "read_pulse_gain": 5600,         # [DAC units]
    "read_pulse_freq": 7391.9,      # [MHz]
    "ro_mode_periodic": False,  # currently unused

    # Qubit spec parameters
    "qubit_freq_start": 700,        # [MHz]
    "qubit_freq_stop": 1000,         # [MHz]
    "qubit_pulse_style": "flat_top", # one of ["const", "flat_top", "arb"]
    "qubit_spec_delay": 0.1,  # [us] Delay before starting qubit spec
    "sigma": 0.05,                  # [us], used with "arb" and "flat_top"
    "qubit_length": 0.05,               # [us], used with "const"
    "flat_top_length": 0.2,        # [us], used with "flat_top"
    "qubit_gain": 32000,             # [DAC units]
    "qubit_ch": 1,                   # RFSOC output channel of qubit drive
    "qubit_nqz": 1,                  # Nyquist zone to use for qubit drive
    "qubit_mode_periodic": False,    # Currently unused, applies to "const" drive

    # Fast flux pulse parameters
    "ff_length": 0.4,                  # [us] Total length of positive fast flux pulse
    "pre_ff_delay": 0.,               # [us] Delay before the fast flux pulse
    "ff_pulse_style": "const",
    "ff_ch": 6,                      # RFSOC output channel of fast flux drive
    "ff_nqz": 1,                     # Nyquist zone to use for fast flux drive

    "yokoVoltage": -1.494,           # [V] Yoko voltage for DC component of fast flux
    "relax_delay": 10,               # [us]
    "qubit_freq_expts": 75,         # number of points
    "reps": 50000,
    "use_switch": False,

    # ff_gain sweep parameters: DAC value of fast flux pulse endpoint
    "ff_gain_start": 0,  # [DAC] Initial value
    "ff_gain_stop": 100,  # [DAC] Final value
    "ff_gain_steps": 3,  # number of qubit_spec_delay points to take
}

config = BaseConfig | UpdateConfig
yoko.SetVoltage(config["yokoVoltage"])

Instance_FFSpecVsFlux= FFSpecVsFlux_Experiment(path="FFSpecVsFlux", cfg=config,soc=soc,soccfg=soccfg,
                                              outerFolder = outerFolder, short_directory_names = True)

# Estimate Time
time = Instance_FFSpecVsFlux.estimate_runtime()
print("Time for ff spec experiment is about ", time, " s")

try:
    data_FFSpecVsFlux = FFSpecVsFlux_Experiment.acquire(Instance_FFSpecVsFlux, progress = True)
    FFSpecVsFlux_Experiment.display(Instance_FFSpecVsFlux, data_FFSpecVsFlux, plot_disp=True)
    FFSpecVsFlux_Experiment.save_data(Instance_FFSpecVsFlux, data_FFSpecVsFlux)
    FFSpecVsFlux_Experiment.save_config(Instance_FFSpecVsFlux)
    # print(Instance_specSlice.qubitFreq)
    plt.show()
except Exception:
    print("Pyro traceback:")
    print("".join(Pyro4.util.getPyroTraceback()))




#%%
# TITLE: Loopback experiment
#

# Perform an actual loopback experiment, i.e. send a signal and just measure it. The point is to see how much
# adc trigger delay you need due to the delay in the lines and electronics, such that you're not just averaging noise
# in the beginning, and then losing the end of the actual signal.

UpdateConfig = {
    ###### cavity
    "pulse_style": "const",  # --Fixed
    "pulse_gain": 10000,  # [DAC units]
    "pulse_freq": 6725, #3713,  # [MHz]
    "length": 100, # [generator clock ticks] Length of the pulse
    "readout_length": 500, # [readout clock ticks!] Length of the readout
    "mode_periodic": False, # This should always be false for this experiment

    "res_ch": 0, # 0 is resonator, 1 is qubit
    "nqz": 2,

    "adc_trig_offset": 0, # [main clock cycles] The trigger offset to vary, convert to us via soc.cycles2us()
    "reps": 1,
    "soft_avgs": 100,
    "relax_delay": 0.01, # [us]
}

config = BaseConfig | UpdateConfig

Instance_loopback = Loopback(path="Loopback", cfg=config,soc=soc,soccfg=soccfg, outerFolder = outerFolder)
data_trans= Loopback.acquire(Instance_loopback)
Loopback.display(Instance_loopback, data_trans, plotDisp=True)
Loopback.save_data(Instance_loopback, data_trans)
Instance_loopback.save_config()

#%%
# TITLE: "Loopback" experiment DDR4
# to check the specs of your rfsoc, use print(soccfg). Relevant info in the readout channels and DDR4 memory buffer section
def time2transfers(time):
    # Takes a time in us and returns the number of transfers needed to extract from the DDR4 buffer
    n_transfers = int(math.ceil(307.2*time/128)) # Decimated sampling rate of the readout channel * time of acquisition / samples/transfer
    return n_transfers

config = {"res_ch": 0,  # --Fixed
          "ro_chs": [0],  # --Fixed
          "reps": 1,  # --Fixed
          "relax_delay": 30,  # --us
          "res_phase": 0,  # --degrees
          "pulse_style": "const",  # --Fixed
          "mode_periodic": False,
          "length": soc.us2cycles(20),  # [Clock ticks] # 1 us is around 430 clock ticks # How long the pulse is on
          # Try varying length from 10-100 clock ticks

          "readout_length": 100,  # [Clock ticks]
          # Try varying readout_length from 50-1000 clock ticks # amount of data collected in the normal buffer

          "pulse_gain": 8000,  # [DAC units]
          # Try varying pulse_gain from 500 to 30000 DAC units

          "pulse_freq": 7391.9441, #6666.0, #6664.6135, ##6666.45,  # [MHz]
          # In this program the signal is up and downconverted digitally so you won't see any frequency
          # components in the I/Q traces below. But since the signal gain depends on frequency,
          # if you lower pulse_freq you will see an increased gain.

          "adc_trig_offset": 310, #185,  # [Clock ticks] NOTE: the rest of the code accepts this number in us, not clock cycles!
          # Try varying adc_trig_offset from 100 to 220 clock ticks

          "soft_avgs": 1,#10000
          # Try varying soft_avgs from 1 to 200 averages

          "ddr4_avgs": 1,
          "nqz": 2, # Needs to be 2 if pulse_freq > first nyquist zone (~3.5 GHz)
          "ddr4_duration": int(1e5), # amount of time to read out of DDR4 buffer (us)
          "save_data": True,
          "yokoVoltage": -1.467, #0.103, #0.11,#0.124, #0.131 #.09473,#0.09542,
          }
yoko.SetVoltage(config["yokoVoltage"])
if config['mode_periodic']:
    print("Mode periodic!")
prog =LoopbackProgram(soccfg, config)

# Use DDR4
n_transfers_init = 200 # each transfer (aka burst) is 128 decimated samples
soc.arm_ddr4(ch=config['ro_chs'][0],nt=n_transfers_init)

iq_list = prog.acquire_decimated(soc, load_pulses=True, progress=False) # leftovers, debug=False)
print(np.shape(iq_list))


#plt.close('all')
fff = plt.figure()
for ii, iq in enumerate(iq_list):
    plt.plot(iq[0], label="I value, ADC %d"%(config['ro_chs'][ii]))
    plt.plot(iq[1], label="Q value, ADC %d"%(config['ro_chs'][ii]))
    plt.plot(np.abs(iq[0]+1j*iq[1]), label="mag, ADC %d"%(config['ro_chs'][ii]))
plt.ylabel("a.u.")
plt.xlabel("Clock ticks")
plt.title("Averages = " + str(config["soft_avgs"]))
plt.legend()
fff.show()

# Look at the DDR4 buffer
duration = config['ddr4_duration'] # us, how much time you want to take out of the buffer
n_transfers = time2transfers(duration) # Number of smaples we need
print("Taking ",n_transfers, " transfers")
tlist = np.linspace(0,duration,n_transfers*128) # num_samples is num_transfers * samples/transfer

# Implement soft averaging over ddr4 buffer readout
i_mat = []
q_mat = []
start = time.time()
for i in range(config['ddr4_avgs']):

    prog = LoopbackProgram(soccfg, config)

    # Use DDR4
    n_transfers_init = n_transfers*2  # each transfer (aka burst) is 128 decimated samples
    soc.arm_ddr4(ch=config['ro_chs'][0], nt=n_transfers_init)
    iq_list = prog.acquire_decimated(soc, load_pulses=True, progress=False)  # leftovers, debug=False)

    iq_ddr4 = soc.get_ddr4(n_transfers,start=401)
    #print("iq_ddr4 is",iq_ddr4[0:10])
    i_mat.append(iq_ddr4[:,0])
    q_mat.append(iq_ddr4[:,1])
    if i == 1:
        it_time = time.time() - start
        print("Time of one is",it_time)
        print("Estimated total time is", it_time*config['ddr4_avgs'],'s')

#print("i_mat shape is",np.shape(i_mat))
#print("Imat mean shape is",np.shape(np.mean(i_mat,0)))
#iq_ddr4_noavg = np.vstack[i_mat,q_mat]
#print("no avg size is",np.shape(iq_ddr4_noavg))

# T1 type averaging
ddr4_sig = np.array(i_mat) + 1j*np.array(q_mat)
print(np.shape(ddr4_sig))
#print("Ddr4 sig is",ddr4_sig[0,0:10])
mag_arr = np.abs(ddr4_sig)
phase_arr = np.angle(ddr4_sig)
print(np.shape(mag_arr))

mag = [] #np.zeros([1,np.shape])
phase = []
# Inefficient (probably, don't know how python works) -- remove loop
for i in range(np.shape(i_mat)[1]):
    mag.append(np.mean(mag_arr[:,i]))
    phase.append(np.mean(phase_arr[:, i]))
print("Mag avg is",np.shape(mag))

# T2 type averaging
iq_ddr4 = np.vstack([np.mean(i_mat,0), np.mean(q_mat,0)]).T
ddr4_sig_t2 = iq_ddr4[:, 0]+1j*iq_ddr4[:, 1]
mag_t2 = np.abs(ddr4_sig_t2)
phase_t2 = np.angle(ddr4_sig_t2)

#print("Iq ddr4 shape is",np.shape(iq_ddr4))
#iq_ddr4 = soc.get_ddr4(n_transfers,start=401) # first argument: number of data transfers (128 samples/transfer), second argument: clear stale data from prev acquisition
# don't need this?
fig, axs = plt.subplots(nrows=5,ncols=1, sharex=True)
plt.suptitle("DDR4")
fig.tight_layout()
axs[0].plot(tlist, iq_ddr4[:, 0],label="I")
axs[0].set_title("I")
axs[0].set_xlabel("Time (us)")

axs[1].plot(tlist, iq_ddr4[:, 1],label="Q")
axs[1].set_title("Q")
axs[1].set_xlabel("Time (us)")

axs[2].plot(tlist, mag,label="Mag")
axs[2].set_title("Magnitude - T2 type")
axs[2].set_xlabel("Time (us)")

axs[3].plot(tlist, phase,label="Phase")
axs[3].set_title("Phase")
axs[3].set_xlabel("Time (us)")

axs[4].plot(tlist, mag_t2,label="Mag")
axs[4].set_title("Magnitude - T1 type")
axs[4].set_xlabel("Time (us)")

print("I (avg +/- std) is", np.mean(iq_ddr4[:, 0]),"+/-", np.std(iq_ddr4[:,0]))
print("Q (avg +/- std) is", np.mean(iq_ddr4[:, 1]),"+/-", np.std(iq_ddr4[:,1]))
#print("Mag in high is",np.mean(mag[500:3000]),"+/-", np.std(mag[500:3000]))
#print("Mag in low is",np.mean(mag[4000:-1]),"+/-", np.std(mag[4000:-1]))
#plt.xlabel("sample number [fabric ticks]")

plt.show()

fig = plt.figure()
for ii,iq in enumerate(iq_list):
    #print("iq0 shape is", np.size(iq_ddr4[:, 0]))
    #print("iq1 shape is", np.size(iq_ddr4[:, 1]))
    print(np.shape(iq_ddr4[:, 0]), np.shape(iq_ddr4[:, 1]))
    plt.scatter(iq_ddr4[:, 0], iq_ddr4[:, 1])

plt.xlabel("I")
plt.ylabel("Q")
plt.title("IQ Trajectories")

iq_axs = fig.axes[0]
iq_axs.axis('equal')
plt.show()

if config["save_data"]:
    datetimenow = datetime.datetime.now()
    datetimestring = datetimenow.strftime("%Y_%m_%d_%H_%M_%S")
    datestring = datetimenow.strftime("%Y_%m_%d")

    subFolder = r"continuousTimeTrace\\" + datestring
    path = outerFolder + subFolder
    if not os.path.exists(path):
        os.makedirs(path)
    fname = path + r"\\" + "continuousTimeTrace_1RFL_2CMA_" + datetimestring + '_data.h5'
    hf = h5py.File(fname, 'w')
    hf.create_dataset("iq_ddr4",data=iq_ddr4)
    hf.create_dataset("i_mat", data=i_mat)
    hf.create_dataset("q_mat", data=q_mat)
    hf.close()

    # The following is from ExperimentClass, it should not be necessary when we inherit it in a real class
    class NpEncoder(json.JSONEncoder):
        """ Ensure json dump can handle np arrays """

        def default(self, obj):
            if isinstance(obj, np.integer):
                return int(obj)
            if isinstance(obj, np.floating):
                return float(obj)
            if isinstance(obj, np.ndarray):
                return obj.tolist()
            return super(NpEncoder, self).default(obj)

        def datafile(self, group=None, remote=False, data_file=None, swmr=False):
            """returns a SlabFile instance
               proxy functionality not implemented yet"""
            if data_file == None:
                data_file = self.fname

            f = MakeFile(data_file, 'a')
            return f

    if fname[:-3] != '.h5':
        with open(fname, 'w') as fid:
            json.dump(config, fid, cls=NpEncoder),