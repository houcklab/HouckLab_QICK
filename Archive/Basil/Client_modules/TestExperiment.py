from mLoopback import Loopback
from mTransmission import Transmission
import matplotlib.pyplot as plt
from socProxy import makeProxy, soc, soccfg
import h5py
from PythonDrivers.control_atten import setatten
import PythonDrivers.YOKOGS200 as YOKOGS200
import os
os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
from initialize import *
from mAmplitudeRabi import AmplitudeRabi
from mT1 import T1
from mT2R import T2R

from mSpecSlice import *
from mSpecVsFFgain import *
from mSpecVsYokoFF import SpecVsYokoFF
from mTransmissionFF import TransmissionFF
from mSpecSliceFF import SpecSliceFF


#### define the saving path
outerFolder = "Z:\Jeronimo\Measurements\RFSOC_3Qubit\\"


yoko72.SetVoltage(-0.42)
yoko74.SetVoltage(-0.1)
yoko76.SetVoltage(0)



UpdateConfig_transmission={
    "reps": 1100,  # this will used for all experiements below unless otherwise changed in between trials
    "pulse_style": "const", # --Fixed
    "readout_length": soc.us2cycles(3), # [Clock ticks]
    "pulse_gain":30000, # [DAC units]
    "pulse_freq": 250.3, # [MHz] actual frequency is this number + "cavity_LO"
    ##### define tranmission experiment parameters
    "TransSpan": 0.3, ### MHz, span will be center+/- this parameter
    "TransNumPoints": 40, ### number of points in the transmission frequecny
    "cav_Atten": 32, #### cavity attenuator attenuation value
    "trans_reps": 1200,  # this will used for all experiements below unless otherwise changed in between trials

}
# Configure for qubit experiment
UpdateConfig_qubit = {
    "qubit_pulse_style": "const",
    "qubit_gain": 2000,
    "qubit_freq": 4908,
    "qubit_length": soc.us2cycles(40),
    ##### define spec slice experiment parameters
    "SpecSpan": 30,  ### MHz, span will be center+/- this parameter
    "SpecNumPoints": 80,  ### number of points in the transmission frequecny
    "qubit_Atten": 10, ### qubit attenuator value
    ##### define the yoko voltage
    "yokoVoltage": 0,
    "spec_reps": 35,
    "spec_rounds": 200,

}
UpdateConfig_FF = {
    "ff_pulse_style": "const", # --Fixed
    "ff_additional_length": soc.us2cycles(1), # [Clock ticks]
    "ff_gain": -30000, # [DAC units]
    "ff_freq": 0, # [MHz] actual frequency is this number + "cavity_LO"
    ##### define tranmission experiment parameters
    "ff_nqz": 1, ### MHz, span will be center+/- this parameter
    "relax_delay": 200, ### in units us
    "ff_ch": 4, #### cavity attenuator attenuation value
}

#
# UpdateConfig_transmission={
#     "reps": 1000,  # this will used for all experiements below unless otherwise changed in between trials
#     "pulse_style": "const", # --Fixed
#     "readout_length": soc.us2cycles(3), # [Clock ticks]
#     "pulse_gain":30000, # [DAC units]
#     "pulse_freq": 250.3, # [MHz] actual frequency is this number + "cavity_LO"
#     ##### define tranmission experiment parameters
#     "TransSpan": 0.5, ### MHz, span will be center+/- this parameter
#     "TransNumPoitns": 60, ### number of points in the transmission frequecny
#     "cav_Atten": 32, #### cavity attenuator attenuation value
# }
# # Configure for qubit experiment
# UpdateConfig_qubit = {
#     "qubit_pulse_style": "const",
#     "qubit_gain": 2000,
#     "qubit_freq": 4900.2,
#     "qubit_length": soc.us2cycles(40),
#     ##### define spec slice experiment parameters
#     "SpecSpan": 60,  ### MHz, span will be center+/- this parameter
#     "SpecNumPoitns": 120,  ### number of points in the transmission frequecny
#     "qubit_Atten": 10, ### qubit attenuator value
#     ##### define the yoko voltage
#     "yokoVoltage": 0,
# }
# UpdateConfig_FF = {
#     "ff_pulse_style": "const", # --Fixed
#     "ff_length": BaseConfig['length'] + UpdateConfig_qubit['qubit_length'] + soc.us2cycles(5), # [Clock ticks]
#     "ff_gain": -30000, # [DAC units]
#     "ff_freq": 0, # [MHz] actual frequency is this number + "cavity_LO"
#     ##### define tranmission experiment parameters
#     "ff_nqz": 1, ### MHz, span will be center+/- this parameter
#     "relax_delay": 200, ### in units us
#     "ff_ch": 4, #### cavity attenuator attenuation value
#     "soft_avgs": 20000
# }


expt_cfg = {
    "center": UpdateConfig_qubit["qubit_freq"],
    "span": UpdateConfig_qubit["SpecSpan"],
    "expts": UpdateConfig_qubit["SpecNumPoints"]
}
expt_cfg["step"] = 2 * expt_cfg["span"] / expt_cfg["expts"]
expt_cfg["start"] = expt_cfg["center"] - expt_cfg["span"]
UpdateConfig_qubit = {**UpdateConfig_qubit, **expt_cfg}
#
# UpdateConfig = {
#     ##### define attenuators
#     "qubit_Atten": 17,  ### qubit attenuator value
#     "cav_Atten": 32,  #### cavity attenuator attenuation value
#     ###### cavity
#     "trans_reps": 1500,  # this will used for all experiements below unless otherwise changed in between trials
#     "pulse_style": "const",  # --Fixed
#     "pulse_gain": 30000,  # [DAC units]
#     "trans_freq": 443.3,  # [MHz] actual frequency is this number + "cavity_LO"
#     "trans_span": 0.3,  # [MHz] actual frequency is this number + "cavity_LO"
#     "TransNumPoints": 61,  ### number of points in the transmission frequecny
#     "length": soc.us2cycles(10),
#     "adc_trig_offset": soc.us2cycles(3),
#     "readout_length": soc.us2cycles(3),  # [Clock ticks]
#     ##### qubit spec parameters
#     "spec_reps": 4000,
#     "qubit_pulse_style": "const",
#     "qubit_gain": 3000,
#     "qubit_length": soc.us2cycles(40),
#     "qubit_freq": 4940,
#     "qubit_span": 60,
#     "SpecNumPoints": 151,  ### number of points
#     ##### Yoko parameters
#     "yokoStart": -0.105, # [Clock ticks]
#     "yokoStop": -0.095, # [DAC units]
#     "yokoNumPoints": 3, # [MHz] actual frequency is this number + "cavity_LO"
#     "sleep_time": 0.1    #in seconds- sets the wait time in between gain changes to allow for cooldown
# }
#
# UpdateConfig_FF = {
#     "ff_pulse_style": "const", # --Fixed
#     "ff_additional_length": soc.us2cycles(2), # [Clock ticks]
#     "ff_gain": 0, # [DAC units]
#     "ff_freq": 0, # [MHz] actual frequency is this number + "cavity_LO"
#     ##### define tranmission experiment parameters
#     "ff_nqz": 1, ### MHz, span will be center+/- this parameter
#     "relax_delay": 200, ### in units us
#     "ff_ch": 4, #### cavity attenuator attenuation value
#     "soft_avgs": 20000
# }

# UpdateConfig_qubit={
#     "sigma":soccfg.us2cycles(0.025, gen_ch=2),
#     "pi_gain": 11500,
#     "pi2_gain":11500//2,
#     "f_ge": 5052.5,
#     "relax_delay":500, "qubit_Atten": 0
# }
#
UpdateConfig = UpdateConfig_transmission | UpdateConfig_qubit | UpdateConfig_FF
config = BaseConfig | UpdateConfig ### note that UpdateConfig will overwrite elements in BaseConfig
print(config)
#### update the qubit and cavity attenuation
cavityAtten.SetAttenuation(config["cav_Atten"], printOut=True)
# qubitAtten.SetAttenuation(config["qubit_Atten"], printOut=True)

### set the yoko frequency
# yoko1.SetVoltage(config["yokoVoltage"])
# print("Voltage is ", yoko1.GetVoltage(), " Volts")

#################################### Running the actual experiments

# Only run this if no proxy already exists
# soc, soccfg = makeProxy()
# print(soccfg)

# plt.ioff()

###################################### code for runnning basic transmission and specSlice
### perform the cavity transmission experiment
#

# config["reps"] = 40
# config["rounds"] = 50

# Instance_trans = Transmission(path="dataTestTransmission", cfg=config,soc=soc,soccfg=soccfg,
#                               outerFolder=outerFolder)
# data_trans= Transmission.acquire(Instance_trans)
# Transmission.display(Instance_trans, data_trans, plotDisp=True, figNum=1)
# Transmission.save_data(Instance_trans, data_trans)

## Fast Flux Version
# Instance_trans = TransmissionFF(path="dataTestTransmissionFF", cfg=config,soc=soc,soccfg=soccfg,
#                               outerFolder=outerFolder)
# data_trans= TransmissionFF.acquire(Instance_trans)
# TransmissionFF.display(Instance_trans, data_trans, plotDisp=True, figNum=1)
# TransmissionFF.save_data(Instance_trans, data_trans)
## Stop Fast Flux Version


## update the transmission frequency to be the peak
# config["pulse_freq"] = Instance_trans.peakFreq_max
#
# #### Qubit Spec experiment, readjust the number of reps

# config["reps"] = 30
# config["rounds"] = 300
# config["pulse_freq"] = 443.32
# print(config["pulse_freq"])
#
# Instance_specSlice = SpecSlice(path="dataTestSpecSlice", cfg=config,soc=soc,soccfg=soccfg,outerFolder=outerFolder)
# data_specSlice= SpecSlice.acquire(Instance_specSlice)
# SpecSlice.display(Instance_specSlice, data_specSlice, plotDisp=True, figNum=2)
# SpecSlice.save_data(Instance_specSlice, data_specSlice)

## Fast Flux Version
# Instance_specSlice = SpecSliceFF(path="dataTestSpecSliceFF", cfg=config,soc=soc,soccfg=soccfg,outerFolder=outerFolder)
# data_specSlice= SpecSliceFF.acquire(Instance_specSlice)
# SpecSliceFF.display(Instance_specSlice, data_specSlice, plotDisp=True, figNum=2)
# SpecSliceFF.save_data(Instance_specSlice, data_specSlice)
## Stop Fast Flux Version
#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# Amplitude Rabi
# qubitAtten.SetAttenuation(0, printOut=False)

# number_of_steps = 51
# step = int(30000 / number_of_steps)
# ARabi_config = {'start': 0, 'step': step, "expts": number_of_steps,
#                 "sigma":soccfg.us2cycles(0.03, gen_ch=2),"f_ge": 4941.2}
# config = config | ARabi_config ### note that UpdateConfig will overwrite elements in BaseConfig

# iAmpRabi = AmplitudeRabi(path="dataAmpRabi", cfg=config,soc=soc,soccfg=soccfg,
# outerFolder=outerFolder)
# dAmpRabi = AmplitudeRabi.acquire(iAmpRabi)
# AmplitudeRabi.display(iAmpRabi, dAmpRabi, plotDisp=True, figNum=2)
# AmplitudeRabi.save_data(iAmpRabi, dAmpRabi)

# expt_cfg={ "start":0, "step":7, "expts":50, "reps": 50, "rounds": 400,
#         "pi_gain": 12000, "relax_delay" : 500
#        }
#
# config = config | expt_cfg ### note that UpdateConfig will overwrite elements in BaseConfig
# #
# iT1 = T1(path="dataT1", cfg=config,soc=soc,soccfg=soccfg,outerFolder=outerFolder)
# dT1 = T1.acquire(iT1)
# T1.display(iT1, dT1, plotDisp=True, figNum=2)
# T1.save_data(iT1, dT1)

#from mT2R import T2R

# T2R_cfg={"start":0, "step":0.2, "phase_step": soccfg.deg2reg(0 * 360/50, gen_ch=2),
#          "expts":200, "reps": 60, "rounds": 500, "pi_gain": 18000,
#          "pi2_gain": 9000, "relax_delay" : 500, 'f_ge': 4262 + 0.4
#        }
#
# config = config | T2R_cfg ### note that UpdateConfig will overwrite elements in BaseConfig

# iT2R = T2R(path="dataT2R", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
# dT2R = T2R.acquire(iT2R)
# T2R.display(iT2R, dT2R, plotDisp=True, figNum=2)
# T2R.save_data(iT2R, dT2R)

#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

## Now lets start doing Rabi Oscillation stuff:

## First, lets do yoko vs frequency to see avoided crossings:
yoko74.rampstep = 0.0001

yoko72.SetVoltage(-0.42)
yoko74.SetVoltage(-0.1)
yoko76.SetVoltage(0)
swept_yoko = yoko74

#
# UpdateConfig = {
#     ##### define attenuators
#     "qubit_Atten": 17,  ### qubit attenuator value
#     "cav_Atten": 32,  #### cavity attenuator attenuation value
#     ###### cavity
#     "trans_reps": 1500,  # this will used for all experiements below unless otherwise changed in between trials
#     "pulse_style": "const",  # --Fixed
#     "pulse_gain": 30000,  # [DAC units]
#     "trans_freq": 443.3,  # [MHz] actual frequency is this number + "cavity_LO"
#     "trans_span": 0.3,  # [MHz] actual frequency is this number + "cavity_LO"
#     "TransNumPoints": 61,  ### number of points in the transmission frequecny
#     "length": soc.us2cycles(10),
#     "adc_trig_offset": soc.us2cycles(3),
#     "readout_length": soc.us2cycles(3),  # [Clock ticks]
#     ##### qubit spec parameters
#     "spec_reps": 4000,
#     "qubit_pulse_style": "const",
#     "qubit_gain": 3000,
#     "qubit_length": soc.us2cycles(40),
#     "qubit_freq": 4940,
#     "qubit_span": 60,
#     "SpecNumPoints": 151,  ### number of points
#     ##### Yoko parameters
#     "yokoStart": -0.105, # [Clock ticks]
#     "yokoStop": -0.095, # [DAC units]
#     "yokoNumPoints": 3, # [MHz] actual frequency is this number + "cavity_LO"
#     "sleep_time": 0.1    #in seconds- sets the wait time in between gain changes to allow for cooldown
# }
yoko_params = {
    "yokoStart": -0.115, # [Clock ticks]
    "yokoStop": -0.103, # [DAC units]
    "yokoNumPoints": 7, # [MHz] actual frequency is this number + "cavity_LO"
    "sleep_time": 0.1
}
frequencies_dictionary = {
    "trans_freq_start": UpdateConfig["pulse_freq"] - UpdateConfig["TransSpan"],  # [MHz] actual frequency is this number + "cavity_LO"
    "trans_freq_stop": UpdateConfig["pulse_freq"] + UpdateConfig["TransSpan"],  # [MHz] actual frequency is this number + "cavity_LO"
    "qubit_freq_start": UpdateConfig["qubit_freq"] - UpdateConfig["SpecSpan"],
    "qubit_freq_stop": UpdateConfig["qubit_freq"] + UpdateConfig["SpecSpan"],
}
config = config | yoko_params | frequencies_dictionary
#
# UpdateConfig_FF = {
#     "ff_pulse_style": "const", # --Fixed
#     "ff_length": BaseConfig['length'] + UpdateConfig_qubit['qubit_length'] + soc.us2cycles(5), # [Clock ticks]
#     "ff_gain": 0, # [DAC units]
#     "ff_freq": 0, # [MHz] actual frequency is this number + "cavity_LO"
#     ##### define tranmission experiment parameters
#     "ff_nqz": 1, ### MHz, span will be center+/- this parameter
#     "relax_delay": 200, ### in units us
#     "ff_ch": 4, #### cavity attenuator attenuation value
#     "soft_avgs": 20000,
#     "ff_additional_length": soc.us2cycles(2)
# }
# #
# frequencies_dictionary = {
#     "trans_freq_start": UpdateConfig["trans_freq"] - UpdateConfig["trans_span"],  # [MHz] actual frequency is this number + "cavity_LO"
#     "trans_freq_stop": UpdateConfig["trans_freq"] + UpdateConfig["trans_span"],  # [MHz] actual frequency is this number + "cavity_LO"
#     "qubit_freq_start": UpdateConfig["qubit_freq"] - UpdateConfig["qubit_span"],
#     "qubit_freq_stop": UpdateConfig["qubit_freq"] + UpdateConfig["qubit_span"],
# }
#
# expt_cfg = {
#     "center": UpdateConfig_qubit["qubit_freq"],
#     "span": UpdateConfig_qubit["SpecSpan"],
#     "expts": UpdateConfig_qubit["SpecNumPoitns"]
# }
# expt_cfg["step"] = 2 * expt_cfg["span"] / expt_cfg["expts"]
# expt_cfg["start"] = expt_cfg["center"] - expt_cfg["span"]
# #
#
# config = BaseConfig | UpdateConfig | UpdateConfig_FF | expt_cfg
cavityAtten.SetAttenuation(config["cav_Atten"])

outerFolder = "Z:\Jeronimo\Measurements\RFSOC_3Qubit\\"
#
#
##### run actual experiment
Instance_SpecVsYoko = SpecVsYokoFF(path="dataTestSpecVsYokoFF", outerFolder=outerFolder, cfg=config,
                                 soc=soc,soccfg=soccfg, yoko = swept_yoko)
data_SpecVsYoko = SpecVsYokoFF.acquire(Instance_SpecVsYoko, plotDisp=True, plotSave = True)
SpecVsYokoFF.save_data(Instance_SpecVsYoko, data_SpecVsYoko)
SpecVsYokoFF.save_config(Instance_SpecVsYoko)



#  Yoko vs flux:
# yoko75.rampstep = 0.0001
#
# yoko75.SetVoltage(-0.105)
# yoko72.SetVoltage(-0.401)
# # yoko78.SetVoltage(-0.29)
# swept_yoko = yoko78
# UpdateConfig = {
#     ##### define attenuators
#     "qubit_Atten": 17,  ### qubit attenuator value
#     "cav_Atten": 28,  #### cavity attenuator attenuation value
#     ###### cavity
#     "trans_reps": 2000,  # this will used for all experiements below unless otherwise changed in between trials
#     "pulse_style": "const",  # --Fixed
#     "pulse_gain": 30000,  # [DAC units]
#     "trans_freq": 514.75,  # [MHz] actual frequency is this number + "cavity_LO"
#     "trans_span": 0.2,  # [MHz] actual frequency is this number + "cavity_LO"
#     "TransNumPoints": 61,  ### number of points in the transmission frequecny
#     "length": soc.us2cycles(10),
#     "adc_trig_offset": soc.us2cycles(4),
#     "readout_length": soc.us2cycles(4),  # [Clock ticks]
#     ##### qubit spec parameters
#     "spec_reps": 4000,
#     "qubit_pulse_style": "const",
#     "qubit_gain": 30000,
#     "qubit_length": soc.us2cycles(12),
#     "qubit_freq": 5830,
#     "qubit_span": 50,
#     "SpecNumPoints": 151,  ### number of points
#     ##### Yoko parameters
#     "yokoStart": -0.3, # [Clock ticks]
#     "yokoStop": -0.25, # [DAC units]
#     "yokoNumPoints": 15, # [MHz] actual frequency is this number + "cavity_LO"
#     "sleep_time": 0.1    #in seconds- sets the wait time in between gain changes to allow for cooldown
# }
# # yoko75.SetVoltage(0)
# yoko72.rampstep = 0.001
#
# frequencies_dictionary = {
#     "trans_freq_start": UpdateConfig["trans_freq"] - UpdateConfig["trans_span"],  # [MHz] actual frequency is this number + "cavity_LO"
#     "trans_freq_stop": UpdateConfig["trans_freq"] + UpdateConfig["trans_span"],  # [MHz] actual frequency is this number + "cavity_LO"
#     "qubit_freq_start": UpdateConfig["qubit_freq"] - UpdateConfig["qubit_span"],
#     "qubit_freq_stop": UpdateConfig["qubit_freq"] + UpdateConfig["qubit_span"],
# }
#
#
# config = BaseConfig | UpdateConfig | frequencies_dictionary
#
# cavityAtten.SetAttenuation(config["cav_Atten"])
# qubitAtten.SetAttenuation(config["qubit_Atten"])
#
# outerFolder = "Z:\Jeronimo\Measurements\RFSOC_3Qubit\\"
#
#
# ##### run actual experiment
# Instance_SpecVsYoko = SpecVsYoko(path="dataTestSpecVsYoko", outerFolder=outerFolder, cfg=config,
#                                  soc=soc,soccfg=soccfg, yoko = swept_yoko)
# data_SpecVsYoko = SpecVsYoko.acquire(Instance_SpecVsYoko, plotSave = True)
# SpecVsYoko.save_data(Instance_SpecVsYoko, data_SpecVsYoko)
# SpecVsYoko.save_config(Instance_SpecVsYoko)
#
# swept_yoko.rampstep = 0.001
# yoko72.SetVoltage(0.0)
# yoko78.SetVoltage(0.0)
# yoko75.SetVoltage(0.0)
#
# #
# plt.show(block = True)









# Instance_trans = TransmissionFF(path="dataTestTransmission", cfg=config,soc=soc,soccfg=soccfg)
# data_trans= TransmissionFF.acquire(Instance_trans)
# TransmissionFF.display(Instance_trans, data_trans, plotDisp=True, figNum=1)
# TransmissionFF.save_data(Instance_trans, data_trans)


#
# yoko72.SetVoltage(0.0)
# yoko78.SetVoltage(0.0)
# UpdateConfig = {
#     ##### define attenuators
#     "qubit_Atten": 0,  ### qubit attenuator value
#     "cav_Atten": 33,  #### cavity attenuator attenuation value
#     ##### define the gain
#     "gainStart": 5000 - 1,
#     "gainStop": 5000 + 1,
#     "gainNumPoints": 11,
#     ###### cavity
#     "trans_reps": 2500,  # this will used for all experiements below unless otherwise changed in between trials
#     "pulse_style": "const",  # --Fixed
#     "pulse_gain": 30000,  # [DAC units]
#     "trans_freq": 515.38,  # [MHz] actual frequency is this number + "cavity_LO"
#     "trans_span": 0.2,  # [MHz] actual frequency is this number + "cavity_LO"
#     "TransNumPoints": 101,  ### number of points in the transmission frequecny
#     "length": soc.us2cycles(10),
#     "adc_trig_offset": soc.us2cycles(4),
#     "readout_length": soc.us2cycles(4),  # [Clock ticks]
#     ##### qubit spec parameters
#     "spec_reps": 2500,
#     "qubit_pulse_style": "const",
#     "qubit_gain": 30000,
#     "qubit_length": soc.us2cycles(12),
#     "qubit_freq": 6202,
#     "qubit_span": 12,
#     "SpecNumPoints": 151,  ### number of points
#     ##### FastFlux parameters
#     "ff_pulse_style": "const", # --Fixed
#     "ff_length": soc.us2cycles(15), # [Clock ticks]
#     "ff_gain": 30000, # [DAC units]
#     "ff_freq": 0, # [MHz] actual frequency is this number + "cavity_LO"
#     "ff_nqz": 1, ### MHz, span will be center+/- this parameter
#     "relax_delay": 40, ### in units us
#     "ff_ch": 4, #### cavity attenuator attenuation value
#     "sleep_time": 0.1    #in seconds- sets the wait time in between gain changes to allow for cooldown
# }
# yoko75.SetVoltage(0)
#
#
# frequencies_dictionary = {
#     "trans_freq_start": UpdateConfig["trans_freq"] - UpdateConfig["trans_span"],  # [MHz] actual frequency is this number + "cavity_LO"
#     "trans_freq_stop": UpdateConfig["trans_freq"] + UpdateConfig["trans_span"],  # [MHz] actual frequency is this number + "cavity_LO"
#     "qubit_freq_start": UpdateConfig["qubit_freq"] - UpdateConfig["qubit_span"],
#     "qubit_freq_stop": UpdateConfig["qubit_freq"] + UpdateConfig["qubit_span"],
# }
#
#
# config = BaseConfig | UpdateConfig | frequencies_dictionary
#
# cavityAtten.SetAttenuation(config["cav_Atten"])
# qubitAtten.SetAttenuation(config["qubit_Atten"])
#
# outerFolder = "Z:\Jeronimo\Measurements\RFSOC_3Qubit\\"
#
#
# ##### run actual experiment
# Instance_SpecVsFFgain = SpecVsFFgain(path="dataTestSpecVsFFgain", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
# data_SpecVsFFgain = SpecVsFFgain.acquire(Instance_SpecVsFFgain, plotSave = True)
# SpecVsFFgain.save_data(Instance_SpecVsFFgain, data_SpecVsFFgain)
# SpecVsFFgain.save_config(Instance_SpecVsFFgain)
#
#
# #
# plt.show(block = True)

# # Configure for transmission experiment
# UpdateConfig_transmission={
#     "reps": 1000,  # --Fixed
#     "pulse_style": "const", # --Fixed
#     "readout_length": soc.us2cycles(7), # [Clock ticks]
#     "pulse_gain":30000, # [DAC units]
#     "pulse_freq": 515.3, # [MHz] actual frequency is this number + "cavity_LO"
#     ##### define tranmission experiment parameters
#     "TransSpan": 1.5, ### MHz, span will be center+/- this parameter
#     "TransNumPoitns": 150, ### number of points in the transmission frequecny
#     "adc_trig_offset": soc.us2cycles(2),
#     "length": soc.us2cycles(10)
# }
#
# # Configure for qubit experiment
# UpdateConfig_qubit = {
#     "qubit_reps": 2000,
#     "qubit_pulse_style": "const",
#     "qubit_gain": 30000,
#     "qubit_freq": 4970,
#     "qubit_length": 500,
# }
# UpdateConfig = UpdateConfig_transmission | UpdateConfig_qubit
# config = BaseConfig | UpdateConfig_transmission ### note that UpdateConfig will overwrite elements in BaseConfig
#
#
# #################################### Running the actual experiments

#  Yoko vs flux:
# yoko75.rampstep = 0.0001
#
# yoko75.SetVoltage(-0.105)
# yoko72.SetVoltage(-0.401)
# # yoko78.SetVoltage(-0.29)
# swept_yoko = yoko78
# UpdateConfig = {
#     ##### define attenuators
#     "qubit_Atten": 17,  ### qubit attenuator value
#     "cav_Atten": 28,  #### cavity attenuator attenuation value
#     ###### cavity
#     "trans_reps": 2000,  # this will used for all experiements below unless otherwise changed in between trials
#     "pulse_style": "const",  # --Fixed
#     "pulse_gain": 30000,  # [DAC units]
#     "trans_freq": 514.75,  # [MHz] actual frequency is this number + "cavity_LO"
#     "trans_span": 0.2,  # [MHz] actual frequency is this number + "cavity_LO"
#     "TransNumPoints": 61,  ### number of points in the transmission frequecny
#     "length": soc.us2cycles(10),
#     "adc_trig_offset": soc.us2cycles(4),
#     "readout_length": soc.us2cycles(4),  # [Clock ticks]
#     ##### qubit spec parameters
#     "spec_reps": 4000,
#     "qubit_pulse_style": "const",
#     "qubit_gain": 30000,
#     "qubit_length": soc.us2cycles(12),
#     "qubit_freq": 5830,
#     "qubit_span": 50,
#     "SpecNumPoints": 151,  ### number of points
#     ##### Yoko parameters
#     "yokoStart": -0.3, # [Clock ticks]
#     "yokoStop": -0.25, # [DAC units]
#     "yokoNumPoints": 15, # [MHz] actual frequency is this number + "cavity_LO"
#     "sleep_time": 0.1    #in seconds- sets the wait time in between gain changes to allow for cooldown
# }
# # yoko75.SetVoltage(0)
# yoko72.rampstep = 0.001
#
# frequencies_dictionary = {
#     "trans_freq_start": UpdateConfig["trans_freq"] - UpdateConfig["trans_span"],  # [MHz] actual frequency is this number + "cavity_LO"
#     "trans_freq_stop": UpdateConfig["trans_freq"] + UpdateConfig["trans_span"],  # [MHz] actual frequency is this number + "cavity_LO"
#     "qubit_freq_start": UpdateConfig["qubit_freq"] - UpdateConfig["qubit_span"],
#     "qubit_freq_stop": UpdateConfig["qubit_freq"] + UpdateConfig["qubit_span"],
# }
#
#
# config = BaseConfig | UpdateConfig | frequencies_dictionary
#
# cavityAtten.SetAttenuation(config["cav_Atten"])
# qubitAtten.SetAttenuation(config["qubit_Atten"])
#
# outerFolder = "Z:\Jeronimo\Measurements\RFSOC_3Qubit\\"
#
#
# ##### run actual experiment
# Instance_SpecVsYoko = SpecVsYoko(path="dataTestSpecVsYoko", outerFolder=outerFolder, cfg=config,
#                                  soc=soc,soccfg=soccfg, yoko = swept_yoko)
# data_SpecVsYoko = SpecVsYoko.acquire(Instance_SpecVsYoko, plotSave = True)
# SpecVsYoko.save_data(Instance_SpecVsYoko, data_SpecVsYoko)
# SpecVsYoko.save_config(Instance_SpecVsYoko)
#
# swept_yoko.rampstep = 0.001
# yoko72.SetVoltage(0.0)
# yoko78.SetVoltage(0.0)
# yoko75.SetVoltage(0.0)
#
# #
# plt.show(block = True)
#
# # Only run this if no proxy already exists
# # soc, soccfg = makeProxy()
# # print(soccfg)
#
# # Loop over modules
# i = 0
# while i < 1:
#
#     Instance = Transmission(path="dataTestTransmission", cfg=config,soc=soc,soccfg=soccfg)
#     data= Transmission.acquire(Instance)
#     Transmission.display(Instance, data, plotDisp=False)
#     Transmission.save_data(Instance, data)
#
#     i += 1
#
# # Look at a data file
# with h5py.File(Instance.fname, "r") as f:
#     # List all groups
#     print("Keys: %s" % f.keys())
#     a_group_key = list(f.keys())[0]
#     # Get the data
#     data = list(f[a_group_key])
#     print("Viewing data file")

