import matplotlib.pyplot as plt
from q4diamond.Client_modules.socProxy import makeProxy, soc, soccfg
import h5py
from q4diamond.Client_modules.PythonDrivers.control_atten import setatten
import q4diamond.Client_modules.PythonDrivers.YOKOGS200 as YOKOGS200
import os
# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')

from q4diamond.Client_modules.initialize import *
from q4diamond.Client_modules.Running_Experiments.Calibrated_parameters import *
from q4diamond.Client_modules.Experiment_Scripts.mSpecSliceFF_HigherLevels import SpecSliceFF_HigherExc
from q4diamond.Client_modules.Experiment_Scripts.mAmplitudeRabiFF_HigherLevels import AmplitudeRabiFF_HigherExc
from q4diamond.Client_modules.Experiment_Scripts.mSingleShotProgramFF_HigherLevels import SingleShotProgramFF_HigherLevels, SingleShotProgramFF_2States
from q4diamond.Client_modules.Experiment_Scripts.mSingleShotProgramFF import SingleShotProgramFF
from q4diamond.Client_modules.Experiment_Scripts.mChiShift import ChiShift
from q4diamond.Client_modules.Experiment_Scripts.mOptimizeReadoutandPulse_FF import ReadOpt_wSingleShotFF, ReadOpt_wSingleShotFF_HigherStates



#### define the saving path
outerFolder = "Z:\Jeronimo\Measurements\RFSOC_3Qubit\\"

parameter = parameter_higher_excited

yoko_values = parameter["yoko_values"]
yoko72.SetVoltage(yoko_values[0])
yoko74.SetVoltage(yoko_values[1])
yoko76.SetVoltage(yoko_values[2])

FF_channel1 = 6 #6 is left, 4 is middle, 5 is right
FF_channel2 = 4 #4 is middle qubit, 6 is left qubit
FF_channel3 = 5 #4 is middle qubit, 6 is left qubit,

Read_Qubit = "Left_Qubit"
Pi_Pulse = "Left_Qubit"

qubit_reading_from = parameter[Read_Qubit]
qubit_pi_pulsing = parameter[Pi_Pulse]

Spec_relevant_params = {"qubit_frequency_center": 3987,
                        "qubit_gain": 200,
                        "SpecSpan": 4,
                        "SpecNumPoints": 61}

config = {}

FF_Read_params = parameter["FF_gains"]
FF_gain1_read = FF_Read_params[0]
FF_gain2_read = FF_Read_params[1]
FF_gain3_read = FF_Read_params[2]

FF_gain1_exp = 0 #FF_Read_params[0]  # Left Qubit
FF_gain2_exp = 0 #FF_Read_params[1]  # Middle Qubit
FF_gain3_exp = 0 #FF_Read_params[1]  # Right Qubit

UpdateConfig_FF_multiple = {
    "FF_list_readout": [(FF_channel1, FF_gain1_read),
    (FF_channel2, FF_gain2_read), (FF_channel3, FF_gain3_read)]
}
UpdateConfig_FF_pulse = {
    "FF_list_exp": [(FF_channel1, FF_gain1_exp),
    (FF_channel2, FF_gain2_exp), (FF_channel3, FF_gain3_exp)]
}
UpdateConfig_FF_multiple = UpdateConfig_FF_multiple | UpdateConfig_FF_pulse

cavityAtten.SetAttenuation(qubit_reading_from["cavity_atten"], printOut=False)

config["read_pulse_freq"] = qubit_reading_from["cavity_frequency"]
config["read_pulse_gain"] = qubit_reading_from["cavity_gain"]
config["readout_time"] = qubit_reading_from["readout_time"]
config["adc_trig_offset"] = qubit_reading_from["adc_offset"]
config["relax_delay"] = qubit_reading_from["relax_delay"]
config["read_length"] = qubit_reading_from["readout_time"]

config["qubit_freq01"] = qubit_pi_pulsing["qubit_frequency01"]
config["qubit_freq12"] = qubit_pi_pulsing["qubit_frequency12"]

config["sigma"] = qubit_pi_pulsing["qubit_pulse_parameters01"]["sigma"]
config["qubit_gain01"] = qubit_pi_pulsing["qubit_pulse_parameters01"]["pi_gain"]
config["qubit_gain12"] = qubit_pi_pulsing["qubit_pulse_parameters12"]["pi_gain"]

print(config["qubit_freq01"],config["qubit_freq12"] )
print(config["qubit_gain01"],config["qubit_gain12"] )


leftover_parameters = {
    "read_pulse_style": "const",
    "qubit_pulse_style": "arb",
    "ff_freq": 0,
    "ff_ch": 6,
    "ff_nqz": 1,
    "ff_pulse_style": "const",
}

UpdateConfig_qubit = {
    "qubit_pulse_style": "const",
    "qubit_gain": Spec_relevant_params["qubit_gain"],
    "qubit_freq": Spec_relevant_params["qubit_frequency_center"],
    "qubit_length": 10,
    "SpecSpan": Spec_relevant_params["SpecSpan"],  ### MHz, span will be center+/- this parameter
    "SpecNumPoints": Spec_relevant_params["SpecNumPoints"],  ### number of points in the transmission frequecny
    "read_pulse_style": "const",
    "qubit_pulse_style": "arb",
}


expt_cfg = {
    "center": UpdateConfig_qubit["qubit_freq"],
    "span": UpdateConfig_qubit["SpecSpan"],
    "expts": UpdateConfig_qubit["SpecNumPoints"]
}
expt_cfg["step"] = 2 * expt_cfg["span"] / expt_cfg["expts"]
expt_cfg["start"] = expt_cfg["center"] - expt_cfg["span"]
UpdateConfig_qubit = {**UpdateConfig_qubit, **expt_cfg}

config = BaseConfig | config | UpdateConfig_FF_multiple | leftover_parameters | UpdateConfig_qubit

config["reps"] = 40
config["rounds"] = 40

# Instance_specSlice = SpecSliceFF_HigherExc(path="dataTestSpecSliceFF", cfg=config, soc=soc, soccfg=soccfg,
#                                  outerFolder=outerFolder)
# data_specSlice = SpecSliceFF_HigherExc.acquire(Instance_specSlice)
# SpecSliceFF_HigherExc.display(Instance_specSlice, data_specSlice, plotDisp=True, figNum=2)
# SpecSliceFF_HigherExc.save_data(Instance_specSlice, data_specSlice)

number_of_steps = 31
max_gain = 10000
step = int(max_gain / number_of_steps)

expt_cfg = {"start": 0 , "step": step, "expts": number_of_steps}
config = config | expt_cfg

config["qubit_freq12"] = qubit_pi_pulsing["qubit_frequency12"]
#
# iAmpRabi = AmplitudeRabiFF_HigherExc(path="dataAmpRabi", cfg=config,soc=soc,soccfg=soccfg,
#                                 outerFolder=outerFolder)
# dAmpRabi = AmplitudeRabiFF_HigherExc.acquire(iAmpRabi)
# AmplitudeRabiFF_HigherExc.display(iAmpRabi, dAmpRabi, plotDisp=True, figNum=2)
# AmplitudeRabiFF_HigherExc.save_data(iAmpRabi, dAmpRabi)

config["pulse_expt"] = {}
config["pulse_expt"]["check_12"] = True
config["pulse_freq"] = 249.35#249.5
config["cavity_atten"] = 4#15
config["TransSpan"] = 1    #total span is 2 times this. span plus or minus
config["reps"] = 5000
config["TransNumPoints"] = 5 * 15

config["read_pulse_freq"] = 249.35#249.5

cavityAtten.SetAttenuation(config["cavity_atten"], printOut=False)



# iChi = ChiShift(path="dataChiShift", cfg=config,soc=soc,soccfg=soccfg,
#                                   outerFolder=outerFolder)
# dChi= ChiShift.acquire(iChi)
# ChiShift.display(iChi, dChi, plotDisp=True, figNum=1)
# ChiShift.save_data(iChi, dChi)



config["shots"] = 2000

SS_higher = SingleShotProgramFF_HigherLevels(path="SingleShot_Multiple", cfg=config,soc=soc,soccfg=soccfg,
                                outerFolder=outerFolder)
dSS_higher = SS_higher.acquire()
SS_higher.display(dSS_higher)
SS_higher.save_data(dSS_higher)



# SS_higher = SingleShotProgramFF_2States(path="SingleShot_Multiple", cfg=config,soc=soc,soccfg=soccfg,
#                                 outerFolder=outerFolder)
# dSS_higher = SS_higher.acquire(ground_pulse=1, excited_pulse=2)
# SS_higher.display(dSS_higher)
# SS_higher.save_data(dSS_higher)




parameter = {
    "FF": [0, 0, 0],
    "qubit_gain": 5200,
    'qubit_freq': 4215.2,
    "pulse_freq": 249.4
}
FF_gain1_read = parameter["FF"][0]
FF_gain2_read = parameter["FF"][1]
FF_gain3_read = parameter["FF"][2]


FF_gain1_exp = parameter["FF"][0] #Left Qubit
FF_gain2_exp = parameter["FF"][1] #Middle Qubit
FF_gain3_exp = parameter["FF"][2] #Middle Qubit


UpdateConfig_FF_multiple = {
    "FF_list_readout": [(FF_channel1, FF_gain1_read),
    (FF_channel2, FF_gain2_read), (FF_channel3, FF_gain3_read)]
}
UpdateConfig_FF_pulse = {
    "FF_list_exp": [(FF_channel1, FF_gain1_exp),
    (FF_channel2, FF_gain2_exp), (FF_channel3, FF_gain3_exp)]
}
UpdateConfig_FF = {
    "ff_pulse_style": "const", # --Fixed
    "ff_additional_length": 1, # [us]
    "ff_freq": 0, # [MHz] actual frequency is this number + "cavity_LO"
    "ff_nqz": 1, ### MHz, span will be center+/- this parameter
    "relax_delay": 200, ### in units us
    "ff_ch": 6, #### cavity attenuator attenuation value
}
UpdateConfig_FF = UpdateConfig_FF | UpdateConfig_FF_multiple | UpdateConfig_FF_pulse


UpdateConfig = {
    ###### cavity
    "read_pulse_style": "const", # --Fixed
    "read_length": 4, # us (length of the pulse applied)
    "adc_trig_offset": 1.2,
    "read_pulse_gain": 30000, # [DAC units]
    "read_pulse_freq": parameter["pulse_freq"], # [MHz] actual frequency is this number + "cavity_LO"
    ##### qubit spec parameters
    "qubit_pulse_style": "arb",
    "sigma": config["sigma"],  ### units us, define a 20ns sigma
    "qubit_gain": parameter["qubit_gain"],
    "qubit_freq": parameter["qubit_freq"],
    ##### define shots
    "shots": 3000, ### this gets turned into "reps"
    "relax_delay": 300,  # us
}
config = config | BaseConfig | UpdateConfig_FF | UpdateConfig | UpdateConfig_FF_multiple

span = 1.2
exp_parameters = {
    ###### cavity
    "cav_Atten_Start": 15,
    "cav_Atten_Stop": 0,
    "cav_Atten_Points": 16,
    "trans_freq_start": parameter["pulse_freq"] - span / 2, #249.6,
    "trans_freq_stop": parameter["pulse_freq"] + span / 2, #250.3,
    "TransNumPoints": 25,
}

config["pulse_expt"] = {}

config = config | exp_parameters
# # Now lets optimize powers and readout frequencies
# Instance_SingleShotOptimize = ReadOpt_wSingleShotFF(path="dataSingleShot_Optimize", outerFolder=outerFolder,
# cfg=config,soc=soc,soccfg=soccfg)
# data_SingleShotProgramOptimize = ReadOpt_wSingleShotFF.acquire(Instance_SingleShotOptimize, cavityAtten = cavityAtten)
# # print(data_SingleShotProgram)
# ReadOpt_wSingleShotFF.display(Instance_SingleShotOptimize, data_SingleShotProgramOptimize, plotDisp=True)
#
# ReadOpt_wSingleShotFF.save_data(Instance_SingleShotOptimize, data_SingleShotProgramOptimize)
# ReadOpt_wSingleShotFF.save_config(Instance_SingleShotOptimize)


# Instance_SingleShotOptimize = ReadOpt_wSingleShotFF_HigherStates(path="dataSingleShot_Optimize", outerFolder=outerFolder,
#                                                                  cfg=config,soc=soc,soccfg=soccfg)
# data_SingleShotProgramOptimize = ReadOpt_wSingleShotFF_HigherStates.acquire(Instance_SingleShotOptimize,
#                                                                             cavityAtten = cavityAtten, ground_pulse = 1,
#                                                                             excited_pulse= 2 )
# ReadOpt_wSingleShotFF_HigherStates.display(Instance_SingleShotOptimize, data_SingleShotProgramOptimize, plotDisp=True)
#
# ReadOpt_wSingleShotFF_HigherStates.save_data(Instance_SingleShotOptimize, data_SingleShotProgramOptimize)
# ReadOpt_wSingleShotFF_HigherStates.save_config(Instance_SingleShotOptimize)

