#%%
#### import packages
import os
import time

import numpy as np

from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mLoopback import LoopbackProgram

path = r'C:\Users\escher\Documents\GitHub\HouckLab_QICK\WorkingProjects\Tantalum_fluxonium_escher\Client_modules\PythonDrivers'
os.add_dll_directory(path)
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Calib_escher.initialize import *
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mQubit_Pulse_Test import Qubit_Pulse_Test
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mTransmission_SaraTest import Transmission
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mSpecSlice_bkg_subtracted import SpecSlice_bkg_sub
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mSpecSlice import SpecSlice
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mSpecSlice_shots import SpecSlice_shots
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mAmplitudeRabi import AmplitudeRabi
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mTransVsGain import TransVsGain
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

import sys
sys.path.insert(0, 'Z:\TantalumFluxonium\Data\HouckLabMeasurementCode\ADMV8818')
from admv8818_functions import set_filter
from matplotlib import pyplot as plt
import datetime
from tqdm import tqdm

# Define the saving path
outerFolder = r"Z:\TantalumFluxonium\Data\2024_07_29_cooldown\HouckCage_dev\\"

# Only run this if no proxy already exists
soc, soccfg = makeProxy()
# print(soccfg)

# plt.ioff()

# Defining the switch configuration
SwitchConfig = {
    "trig_buffer_start": 0.035, # in us
    "trig_buffer_end": 0.024, # in us
    "trig_delay": 0.07, # in us
}

BaseConfig = BaseConfig | SwitchConfig

#%%
# TITLE: Constant Tone Experiment
UpdateConfig = {
    ###### cavity
    "read_pulse_style": "const",  # --Fixed
    "gain": 0,  # [DAC units]

    "freq": 600,#3713,  # [MHz]

    "channel": 2,  # TODO default value # 0 is resonator, 1 is qubit
    "nqz": 1,#1,  # TODO default value
}

config = BaseConfig | UpdateConfig

ConstantTone_Instance = ConstantTone_Experiment(path="dataTestTransVsGain", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
data_ConstantTone = ConstantTone_Experiment.acquire(ConstantTone_Instance)
ConstantTone_Experiment.save_data(ConstantTone_Instance, data_ConstantTone)
ConstantTone_Experiment.save_config(ConstantTone_Instance)

# using the 10MHz-1GHz balun
# f_center = 10e9 #Hz
# settings = set_filter(f_center)
# print(settings)

#%%
# TITLE: Loopback experiment
config = {"res_ch": 0,  # --Fixed
          "ro_chs": [0],  # --Fixed
          "reps": 1,  # --Fixed
          "relax_delay": 1.0,  # --us
          "res_phase": 0,  # --degrees
          "pulse_style": "const",  # --Fixed

          "length": soc.us2cycles(0.1),  # [Clock ticks] # 1 us is around 430 clock ticks
          # Try varying length from 10-100 clock ticks

          "readout_length": 70,  # [Clock ticks]
          # Try varying readout_length from 50-1000 clock ticks

          "pulse_gain": 30000,  # [DAC units]
          # Try varying pulse_gain from 500 to 30000 DAC units

          "pulse_freq": 6648,  # [MHz]
          # In this program the signal is up and downconverted digitally so you won't see any frequency
          # components in the I/Q traces below. But since the signal gain depends on frequency,
          # if you lower pulse_freq you will see an increased gain.

          "adc_trig_offset": 220,  # [Clock ticks] NOTE: the rest of the code accepts this number in us, not clock cycles!
          # Try varying adc_trig_offset from 100 to 220 clock ticks

          "soft_avgs": 100#10000
          # Try varying soft_avgs from 1 to 200 averages
          }

prog =LoopbackProgram(soccfg, config)
iq_list = prog.acquire_decimated(soc, load_pulses=True, progress=True, debug=False)
fff = plt.figure(1)
for ii, iq in enumerate(iq_list):
    plt.plot(iq[0], label="I value, ADC %d"%(config['ro_chs'][ii]))
    plt.plot(iq[1], label="Q value, ADC %d"%(config['ro_chs'][ii]))
    plt.plot(np.abs(iq[0]+1j*iq[1]), label="mag, ADC %d"%(config['ro_chs'][ii]))
plt.ylabel("a.u.")
plt.xlabel("Clock ticks")
plt.title("Averages = " + str(config["soft_avgs"]))
plt.legend()
fff.show()

#%%

#TITLE: Transmission + SpecSlice + AmplitudeRabi

UpdateConfig_transmission = {
    "reps": 300,
    # cavity
    "read_pulse_style": "const",  # --Fixed
    "read_length": 30,  # us
    "read_pulse_gain": 1000,  # [DAC units]
    "read_pulse_freq": 6422.98,

    # Transmission Experiment
    "TransSpan": 2, # MHz
    "TransNumPoints": 251,


    # define the yoko voltage
    "yokoVoltage": 1.02,
}

UpdateConfig_qubit = {
    "qubit_pulse_style": "flat_top",
    "qubit_freq": 2106.66,
    "qubit_gain": 25000,

    # Constant Pulse Tone
    "qubit_length": 20,

    # Flat top or gaussian pulse tone
    "sigma": 0.5,#0.3,
    "flat_top_length": 20.0,

    # define spec slice experiment parameters
    "qubit_ch": 2,
    "qubit_freq_start": 200, #2105,
    "qubit_freq_stop": 500,#2120,
    "SpecNumPoints": 401,
    'spec_reps': 6000,

    # amplitude rabi parameters
    "qubit_gain_start": 10,
    "qubit_gain_step": 1000,
    "qubit_gain_expts": 31,
    "AmpRabi_reps": 10000,


    # Experiment parameters
    "relax_delay": 50, #2000,
    "fridge_temp": 10,
    "two_pulses": False, # Do e-f pulse
    "use_switch": True
}

UpdateConfig = UpdateConfig_transmission | UpdateConfig_qubit
config = BaseConfig | UpdateConfig

yoko1.SetVoltage(config["yokoVoltage"])

#%%
# TITLE: Performing the Cavity Transmission Experiment
config = BaseConfig | UpdateConfig
Instance_trans = Transmission(path="dataTestTransmission", cfg=config,soc=soc,soccfg=soccfg, outerFolder = outerFolder)
data_trans= Transmission.acquire(Instance_trans)
Transmission.display(Instance_trans, data_trans, plotDisp=True)
Transmission.save_data(Instance_trans, data_trans)

# update the transmission frequency to be the peak
config["read_pulse_freq"] = Instance_trans.peakFreq
print("Cavity freq IF [MHz] = ", Instance_trans.peakFreq)


#%%
# TITLE: Performing regular ole' spec slice

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
# TITLE: Performing background subtracted spec slice
plt.close("all")

Instance_specSlice = SpecSlice_bkg_sub(path="dataTestSpecSlice", cfg=config,soc=soc,soccfg=soccfg, outerFolder = outerFolder, progress = True)
data_specSlice= Instance_specSlice.acquire()
Instance_specSlice.display(data_specSlice, plotDisp=True)
Instance_specSlice.save_config()
Instance_specSlice.save_data(data_specSlice)

#%%
# TITLE : Perform the spec slice with Post Selection
config_spec_ps = {
    'spec_reps' : 10000, # Converted to shots
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
config["qubit_pulse_style"]= "flat_top" #"arb" #"arb"
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
    "yokoVoltage": 1.25, #3.1
    ##### change gain instead option
    "trans_gain_start": 500,
    "trans_gain_stop": 15000,
    "trans_gain_num": 31,
    ###### cavity
    "reps": 200,
    "trans_reps":200,  # this will used for all experiments below unless otherwise changed in between trials
    "read_pulse_style": "const",  # --Fixed
    "readout_length": 30,  # [us]
    # "read_pulse_gain": 10000,  # [DAC units]
    # "trans_freq_start": 7229.8 - 5.0,  # [MHz] actual frequency is this number + "cavity_LO"
    # "trans_freq_stop": 7229.8 + 5.0,  # [MHz] actual frequency is this number + "cavity_LO"
    "trans_freq_start": 6422.8,  # [MHz] actual frequency is this number + "cavity_LO"
    "trans_freq_stop": 6423.2,  # [MHz] actual frequency is this number + "cavity_LO"
    "TransNumPoints": 201,  ### number of points in the transmission frequecny
    "relax_delay": 5, # us
    "units": "dB",         # in dB or DAC
}
#
config = BaseConfig | UpdateConfig
#
# #### update the qubit and cavity attenuation
yoko1.SetVoltage(config["yokoVoltage"])
# #
import matplotlib
matplotlib.use('Qt5Agg')
Instance_TransVsGain = TransVsGain(path="dataTestTransVsGain", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
data_TransVsGain = TransVsGain.acquire(Instance_TransVsGain)
TransVsGain.save_data(Instance_TransVsGain, data_TransVsGain)
TransVsGain.save_config(Instance_TransVsGain)
# endregion
#%%
# TITLE: Amplitude Rabi Blob

UpdateConfig = {
    ##### define attenuators
    "yokoVoltage": 1.25,
    ###### cavity
    "read_pulse_style": "const",  # --Fixed
    "read_length": 30,  # us
    "read_pulse_gain": 1000,  # [DAC units]
    "read_pulse_freq": 6422.98,  # MHz
    ##### spec parameters for finding the qubit frequency
    "qubit_freq_start": 2110, #2106.7,
    "qubit_freq_stop": 2112, #2106.9,
    "RabiNumPoints": 6,  ### number of points
    "qubit_pulse_style": "flat_top",
    "sigma": 2,  ### units us, define a 20ns sigma
    "flat_top_length": 5.0, ### in us
    # "qubit_length": 1,
    "relax_delay": 50,  ### turned into us inside the run function
    ##### amplitude rabi parameters
    "qubit_gain_start": 10,
    "qubit_gain_step": 2000,  ### stepping amount of the qubit gain
    "qubit_gain_expts": 15,  ### number of steps
    "AmpRabi_reps": 50000,  # number of averages for the experiment
    "two_pulses": False, # Pulse twice for calibrating a pi/2 pulse
    'use_switch': True,
}
config = BaseConfig | UpdateConfig
#
yoko1.SetVoltage(config["yokoVoltage"])

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
    "yokoVoltage": 1.2869,

    # cavity
    "read_pulse_style": "const",
    "read_length": 80,
    "read_pulse_gain": 1000,
    "read_pulse_freq": 6230.327,

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
    "use_switch": True,
}
config = BaseConfig | UpdateConfig

yoko1.SetVoltage(config["yokoVoltage"])
print("Voltage is ", yoko1.GetVoltage(), " Volts")

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

###TITLE: Qubit spec on repeat
# region Spec on repeat Config
# UpdateConfig = {
#     ##### define attenuators
#     "yokoVoltage": 0.7,
#     ###### cavity
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 20, # us
#     "read_pulse_gain": 4800, # [DAC units]
#     "read_pulse_freq": 5749.4,
#     ##### spec parameters for finding the qubit frequency
#     "qubit_freq_start": 4647, #1167-10
#     "qubit_freq_stop": 4663,
#     "SpecNumPoints": 31,  ### number of points
#     "qubit_pulse_style": "arb",
#     "qubit_length": 1, # us, changes experiment time but is necessary for "const" style
#     "sigma": 0.05,  ### units us, define a 20ns sigma
#     # "qubit_length": 1, ### units us, doesnt really get used though
#     # "flat_top_length": 0.025, ### in us
#     "relax_delay": 1000,  ### turned into us inside the run function
#     "qubit_gain": 15000, # Constant gain to use
#     # "qubit_gain_start": 18500, # shouldn't need this...
#     "reps": 200, # number of averages of every experiment
#     ##### time parameters
#     "delay":  10, # s
#     "repetitions": 5000,  ### number of steps
# }
# config = BaseConfig | UpdateConfig
#
# yoko1.SetVoltage(config["yokoVoltage"])
# # #
# Instance_QubitSpecRepeat = QubitSpecRepeat(path="dataQubitSpecRepeat", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg, progress=True)
# data_QubitSpecRepeat = QubitSpecRepeat.acquire(Instance_QubitSpecRepeat)
# QubitSpecRepeat.save_data(Instance_QubitSpecRepeat, data_QubitSpecRepeat)
# QubitSpecRepeat.save_config(Instance_QubitSpecRepeat)

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

