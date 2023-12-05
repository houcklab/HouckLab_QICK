import matplotlib.pyplot as plt
from q4diamond.Client_modules.socProxy import makeProxy, soc, soccfg
import h5py
from q4diamond.Client_modules.PythonDrivers.control_atten import setatten
import q4diamond.Client_modules.PythonDrivers.YOKOGS200 as YOKOGS200
import os
# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')
# import os
# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')


from q4diamond.Client_modules.initialize import *

# from q4diamond.Client_modules.mSpecVsYoko import SpecVsYoko
from q4diamond.Client_modules.mTransmission import Transmission
from q4diamond.Client_modules.mSpecSlice import SpecSlice
from q4diamond.Client_modules.mAmplitudeRabi import AmplitudeRabi
from q4diamond.Client_modules.Experiment_Scripts.mSingleShotProgram import SingleShotProgram
from q4diamond.Client_modules.Experiment_Scripts.mReadOpt_wSingleShot import ReadOpt_wSingleShot



#### define the saving path
outerFolder = "Z:\Jeronimo\Measurements\RFSOC_3Qubit\\"


yoko72.SetVoltage(0)
yoko74.SetVoltage(-0.1)
yoko76.SetVoltage(0)

#Left Qubit
# resonator_frequency_center = 250.1
# qubit_frequency_center = 4485
# cavity_attenuation = 15
# cavity_min = True

# #Middle Qubit
resonator_frequency_center = 443.26
qubit_frequency_center = 4942
# qubit_frequency_center = 4530.4
cavity_attenuation = 7
cavity_min = False

# #Right Qubit
# resonator_frequency_center = 641.05
# qubit_frequency_center = 4531.8
# cavity_attenuation = 12
# cavity_min = False



UpdateConfig_transmission={
    "reps": 1000,  # this will used for all experiements below unless otherwise changed in between trials
    "pulse_style": "const", # --Fixed
    "readout_length": soc.us2cycles(3), # [Clock ticks]
    "pulse_gain": 30000, # [DAC units]
    "pulse_freq": resonator_frequency_center, # [MHz] actual frequency is this number + "cavity_LO"
    "TransSpan": 0.7, ### MHz, span will be center+/- this parameter
    "TransNumPoints": 60, ### number of points in the transmission frequecny
    "cav_Atten": cavity_attenuation, #### cavity attenuator attenuation value
}
# Configure for qubit experiment
UpdateConfig_qubit = {
    "qubit_pulse_style": "const",
    "qubit_gain": 100,
    "qubit_freq": qubit_frequency_center,
    "qubit_length": soc.us2cycles(40),
    "SpecSpan": 2,  ### MHz, span will be center+/- this parameter
    "SpecNumPoints": 60,  ### number of points in the transmission frequecny
}

expt_cfg = {
    "center": UpdateConfig_qubit["qubit_freq"],
    "span": UpdateConfig_qubit["SpecSpan"],
    "expts": UpdateConfig_qubit["SpecNumPoints"]
}
expt_cfg["step"] = 2 * expt_cfg["span"] / expt_cfg["expts"]
expt_cfg["start"] = expt_cfg["center"] - expt_cfg["span"]
UpdateConfig_qubit = {**UpdateConfig_qubit, **expt_cfg}


UpdateConfig = UpdateConfig_transmission | UpdateConfig_qubit
config = BaseConfig | UpdateConfig ### note that UpdateConfig will overwrite elements in BaseConfig
#### update the qubit and cavity attenuation
cavityAtten.SetAttenuation(config["cav_Atten"], printOut=True)


#################################### Running the actual experiments

# Only run this if no proxy already exists
# soc, soccfg = makeProxy()
# print(soccfg)

# plt.ioff()

###################################### code for runnning basic transmission and specSlice
### perform the cavity transmission experiment
#

config["reps"] = 20
config["rounds"] = 20

# Instance_trans = Transmission(path="dataTestTransmission", cfg=config,soc=soc,soccfg=soccfg,
#                               outerFolder=outerFolder)
# data_trans= Transmission.acquire(Instance_trans)
# Transmission.display(Instance_trans, data_trans, plotDisp=True, figNum=1)
# Transmission.save_data(Instance_trans, data_trans)

## update the transmission frequency to be the peak
# if cavity_min:
#     config["pulse_freq"] = Instance_trans.peakFreq_min
# else:
#     config["pulse_freq"] = Instance_trans.peakFreq_max

# config["pulse_freq"] = 640.9
config["pulse_freq"] = 443.2
# config["pulse_freq"] = 249.95


# #### Qubit Spec experiment, readjust the number of reps

config["reps"] = 30
config["rounds"] = 30
print(config["pulse_freq"])
#
# Instance_specSlice = SpecSlice(path="dataTestSpecSlice", cfg=config,soc=soc,soccfg=soccfg,outerFolder=outerFolder)
# data_specSlice= SpecSlice.acquire(Instance_specSlice)
# SpecSlice.display(Instance_specSlice, data_specSlice, plotDisp=True, figNum=2)
# SpecSlice.save_data(Instance_specSlice, data_specSlice)

#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# Amplitude Rabi

number_of_steps = 51
step = int(30000 / number_of_steps)
ARabi_config = {'start': 0, 'step': step, "expts": number_of_steps,
                "sigma":soccfg.us2cycles(0.05, gen_ch=2),"f_ge": 4942.45}
config = config | ARabi_config ### note that UpdateConfig will overwrite elements in BaseConfig

# iAmpRabi = AmplitudeRabi(path="dataAmpRabi", cfg=config,soc=soc,soccfg=soccfg,
# outerFolder=outerFolder)
# dAmpRabi = AmplitudeRabi.acquire(iAmpRabi)
# AmplitudeRabi.display(iAmpRabi, dAmpRabi, plotDisp=True, figNum=2)
# AmplitudeRabi.save_data(iAmpRabi, dAmpRabi)


# expt_cfg={
#     "shots": 1000,
#     "pi_gain": 6300,
#     "relax_delay" : 500
#        }
#
# config = config | expt_cfg ### note that UpdateConfig will overwrite elements in BaseConfig
# #Single shot
#
# I_Singleshot = SingleShotProgram(path="dataSingleShot", cfg=config,soc=soc,soccfg=soccfg,outerFolder=outerFolder)
# D_Singleshot= SingleShotProgram.acquire(I_Singleshot)
# SingleShotProgram.display(I_Singleshot, D_Singleshot, plotDisp=True, figNum=2)
# SingleShotProgram.save_data(I_Singleshot, D_Singleshot)



###################################################
UpdateConfig = {
    ###### cavity
    "read_pulse_style": "const", # --Fixed
    "read_length": 3, # us (length of the pulse applied)
    "adc_trig_offset": soc.us2cycles(3),
    "read_pulse_gain": 30000, # [DAC units]
    "read_pulse_freq": 443.2, # [MHz] actual frequency is this number + "cavity_LO"
    ##### qubit spec parameters
    "qubit_pulse_style": "arb",
    "sigma": 0.05,  ### units us, define a 20ns sigma
    "flat_top_length": 0.025, ### in us
    "qubit_gain": 6300,
    "qubit_freq": 4942.45,
    ##### define shots
    "shots": 500, ### this gets turned into "reps"
    "relax_delay": 300,  # us
}
config = BaseConfig | UpdateConfig
#
# Instance_SingleShotProgram = SingleShotProgram(path="dataSingleShot", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
# data_SingleShotProgram = SingleShotProgram.acquire(Instance_SingleShotProgram)
# # print(data_SingleShotProgram)
# SingleShotProgram.display(Instance_SingleShotProgram, data_SingleShotProgram, plotDisp=True)
#
# SingleShotProgram.save_data(Instance_SingleShotProgram, data_SingleShotProgram)
# SingleShotProgram.save_config(Instance_SingleShotProgram)
#########################################################

exp_parameters = {
    ###### cavity
    "cav_Atten_Start": 15,
    "cav_Atten_Stop": 0,
    "cav_Atten_Points": 16,
    "trans_freq_start": 442.9,
    "trans_freq_stop": 443.6,
    "TransNumPoints": 15,
}
config = config | exp_parameters
# Now lets optimize powers and readout frequencies
Instance_SingleShotOptimize = ReadOpt_wSingleShot(path="dataSingleShot_Optimize", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
data_SingleShotProgramOptimize = ReadOpt_wSingleShot.acquire(Instance_SingleShotOptimize, cavityAtten = cavityAtten)
# print(data_SingleShotProgram)
ReadOpt_wSingleShot.display(Instance_SingleShotOptimize, data_SingleShotProgramOptimize, plotDisp=True)

ReadOpt_wSingleShot.save_data(Instance_SingleShotOptimize, data_SingleShotProgramOptimize)
ReadOpt_wSingleShot.save_config(Instance_SingleShotOptimize)



expt_cfg={ "start":0, "step":7, "expts":50, "reps": 50, "rounds": 400,
        "pi_gain": 6300, "relax_delay" : 500
       }

config = config | expt_cfg ### note that UpdateConfig will overwrite elements in BaseConfig
# #
# iT1 = T1(path="dataT1", cfg=config,soc=soc,soccfg=soccfg,outerFolder=outerFolder)
# dT1 = T1.acquire(iT1)
# T1.display(iT1, dT1, plotDisp=True, figNum=2)
# T1.save_data(iT1, dT1)

#from mT2R import T2R

T2R_cfg={"start":0, "step":0.2, "phase_step": soccfg.deg2reg(0 * 360/50, gen_ch=2),
         "expts":200, "reps": 60, "rounds": 500, "pi_gain": 18000,
         "pi2_gain": 9000, "relax_delay" : 500, 'f_ge': 4262 + 0.4
       }

config = config | T2R_cfg ### note that UpdateConfig will overwrite elements in BaseConfig

# iT2R = T2R(path="dataT2R", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
# dT2R = T2R.acquire(iT2R)
# T2R.display(iT2R, dT2R, plotDisp=True, figNum=2)
# T2R.save_data(iT2R, dT2R)

#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

## Now lets start doing Rabi Oscillation stuff:

# ## First, lets do yoko vs frequency to see avoided crossings:
# yoko74.rampstep = 0.0001
#
# yoko72.SetVoltage(-0.42)
# yoko74.SetVoltage(-0.1)
# yoko76.SetVoltage(0)
# swept_yoko = yoko74
#
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
#     "expts": UpdateConfig_qubit["SpecNumPoints"]
# }
# expt_cfg["step"] = 2 * expt_cfg["span"] / expt_cfg["expts"]
# expt_cfg["start"] = expt_cfg["center"] - expt_cfg["span"]
# #
# #
# config = BaseConfig | UpdateConfig | frequencies_dictionary | UpdateConfig_FF | expt_cfg
# cavityAtten.SetAttenuation(config["cav_Atten"])
#
# outerFolder = "Z:\Jeronimo\Measurements\RFSOC_3Qubit\\"
#
#
##### run actual experiment
# Instance_SpecVsYoko = SpecVsYokoFF(path="dataTestSpecVsYokoFF", outerFolder=outerFolder, cfg=config,
#                                  soc=soc,soccfg=soccfg, yoko = swept_yoko)
# data_SpecVsYoko = SpecVsYokoFF.acquire(Instance_SpecVsYoko, plotSave = True)
# SpecVsYokoFF.save_data(Instance_SpecVsYoko, data_SpecVsYoko)
# SpecVsYokoFF.save_config(Instance_SpecVsYoko)



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

