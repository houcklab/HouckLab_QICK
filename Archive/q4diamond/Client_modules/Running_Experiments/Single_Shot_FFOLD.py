# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')

from q4diamond.Client_modules.initialize import *

from q4diamond.Client_modules.mTransmissionFF import TransmissionFF
from q4diamond.Client_modules.Experiment_Scripts.mSpecSliceFF import QubitSpecSliceFF
from q4diamond.Client_modules.Experiment_Scripts.mAmplitudeRabiFF import AmplitudeRabiFF

#### define the saving path
outerFolder = "Z:\Jeronimo\Measurements\RFSOC_3Qubit\\"


yoko72.rampstep = 0.0001
yoko74.rampstep = 0.0001
yoko76.rampstep = 0.0001

# yoko72.SetVoltage(-.242 + .03 + 0.008)
# yoko74.SetVoltage(-0.267 + 0.0003)
# yoko76.SetVoltage(0.2885 + 0.0002)

yoko72.SetVoltage(0.0553)
yoko74.SetVoltage(0.2625)
yoko76.SetVoltage(0.3983)

#Readout
FF_gain1 = 0
FF_gain2 = 0
FF_gain3 = 0

#experiment(pulse)
FF_gain1_pulse = 0   #Left Qubit
FF_gain2_pulse = 0 #Middle Qubit
FF_gain3_pulse = 0 #Right Qubit

# Left Qubit
resonator_frequency_center = 249.8
qubit_frequency_center = 4300
cavity_attenuation = 12
cavity_min = True

##Middle Qubit
# resonator_frequency_center = 442.9
# qubit_frequency_center = 5000
# cavity_attenuation = 15
# cavity_min = False

#Right Qubit
# resonator_frequency_center = 640.9
# qubit_frequency_center = 4500
# cavity_attenuation = 12
# cavity_min = True


RunTransmissionSweep = False
Run2ToneSpec = True
Spec_relevant_params = {"qubit_gain": 100, "SpecSpan": 2, "SpecNumPoints": 61}

RunAmplitudeRabi = False
Amplitude_Rabi_params = {"qubit_freq": 4213.75, "sigma": 0.05, "max_gain": 8000}


FF_channel = 4 #4 is middle qubit, 6 is left qubit
FF_gain = 0

FF_channel1 = 6 #4 is middle qubit, 6 is left qubit
FF_channel2 = 4 #4 is middle qubit, 6 is left qubit
FF_channel3 = 5 #4 is middle qubit, 6 is left qubit

UpdateConfig_FF_multiple = {
    "FF_list_readout": [(FF_channel1, FF_gain1),
    (FF_channel2, FF_gain2), (FF_channel3, FF_gain3)]
}
UpdateConfig_FF_pulse = {
    "FF_list_exp": [(FF_channel1, FF_gain1_pulse),
    (FF_channel2, FF_gain2_pulse), (FF_channel3, FF_gain3_pulse)]
}
UpdateConfig_FF_multiple = UpdateConfig_FF_multiple | UpdateConfig_FF_pulse

UpdateConfig_transmission={
    "reps": 1000,  # this will used for all experiments below unless otherwise changed in between trials
    "pulse_style": "const", # --Fixed
    "readout_length": 3, # [Clock ticks]
    "pulse_gain": 30000, # [DAC units]
    "pulse_freq": resonator_frequency_center, # [MHz] actual frequency is this number + "cavity_LO"
    "TransSpan": 0.7, ### MHz, span will be center+/- this parameter
    "TransNumPoints": 60, ### number of points in the transmission frequecny
    "cav_Atten": cavity_attenuation, #### cavity attenuator attenuation value
}
# Configure for qubit experiment
UpdateConfig_qubit = {
    "qubit_pulse_style": "const",
    "qubit_gain": Spec_relevant_params["qubit_gain"],
    "qubit_freq": qubit_frequency_center,
    "qubit_length": 100,
    "SpecSpan": Spec_relevant_params["SpecSpan"],  ### MHz, span will be center+/- this parameter
    "SpecNumPoints": Spec_relevant_params["SpecNumPoints"],  ### number of points in the transmission frequecny
}
UpdateConfig_FF = {
    "ff_pulse_style": "const", # --Fixed
    "ff_additional_length": 1, # [us]
    "ff_freq": 0, # [MHz] actual frequency is this number + "cavity_LO"
    "ff_nqz": 1, ### MHz, span will be center+/- this parameter
    "relax_delay": 200, ### in units us
    "ff_ch": FF_channel, #### cavity attenuator attenuation value
}

expt_cfg = {
    "center": UpdateConfig_qubit["qubit_freq"],
    "span": UpdateConfig_qubit["SpecSpan"],
    "expts": UpdateConfig_qubit["SpecNumPoints"]
}
expt_cfg["step"] = 2 * expt_cfg["span"] / expt_cfg["expts"]
expt_cfg["start"] = expt_cfg["center"] - expt_cfg["span"]
UpdateConfig_qubit = {**UpdateConfig_qubit, **expt_cfg}


UpdateConfig = UpdateConfig_transmission | UpdateConfig_qubit | UpdateConfig_FF | UpdateConfig_FF_multiple
config = BaseConfig | UpdateConfig ### note that UpdateConfig will overwrite elements in BaseConfig
#### update the qubit and cavity attenuation
cavityAtten.SetAttenuation(config["cav_Atten"], printOut=True)

###################################### code for runnning basic transmission and specSlice
### perform the cavity transmission experiment
#

config["reps"] = 20
config["rounds"] = 20

if RunTransmissionSweep:
    Instance_trans = TransmissionFF(path="dataTestTransmissionFF", cfg=config,soc=soc,soccfg=soccfg,
                                  outerFolder=outerFolder)
    data_trans= TransmissionFF.acquire(Instance_trans)
    TransmissionFF.display(Instance_trans, data_trans, plotDisp=True, figNum=1)
    TransmissionFF.save_data(Instance_trans, data_trans)


    # update the transmission frequency to be the peak
    if cavity_min:
        config["pulse_freq"] = Instance_trans.peakFreq_min
    else:
        config["pulse_freq"] = Instance_trans.peakFreq_max

# #### Qubit Spec experiment, readjust the number of reps

config["reps"] = 40
config["rounds"] = 50
print(config["pulse_freq"])

## Fast Flux Version
if Run2ToneSpec:
    Instance_specSlice = QubitSpecSliceFF(path="dataTestSpecSliceFF", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
    data_specSlice= QubitSpecSliceFF.acquire(Instance_specSlice)
    QubitSpecSliceFF.display(Instance_specSlice, data_specSlice, plotDisp=True, figNum=2)
    QubitSpecSliceFF.save_data(Instance_specSlice, data_specSlice)
# Stop Fast Flux Version
#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# Amplitude Rabi
config["ff_additional_length"] = soc.us2cycles(4)
number_of_steps = 31
step = int(Amplitude_Rabi_params["max_gain"] / number_of_steps)
# ARabi_config = {'start': 0, 'step': step, "expts": number_of_steps,
#                 "sigma":0.05,"f_ge": 4485.2, "relax_delay": 300}
ARabi_config = {'start': 0, 'step': step, "expts": number_of_steps,
                "sigma":Amplitude_Rabi_params["sigma"],"f_ge": Amplitude_Rabi_params["qubit_freq"], "relax_delay": 300}
config = config | ARabi_config ### note that UpdateConfig will overwrite elements in BaseConfig
if RunAmplitudeRabi:

    iAmpRabi = AmplitudeRabiFF(path="dataAmpRabi", cfg=config,soc=soc,soccfg=soccfg,
                                outerFolder=outerFolder)
    dAmpRabi = AmplitudeRabiFF.acquire(iAmpRabi)
    AmplitudeRabiFF.display(iAmpRabi, dAmpRabi, plotDisp=True, figNum=2)
    AmplitudeRabiFF.save_data(iAmpRabi, dAmpRabi)


# parameter = {
#     "FF": [15000, -30000, 0],
#     "qubit_gain": 4300,
#     'qubit_freq': 4392.5,
#     "pulse_freq": 249.7
# }
parameter = {
    "FF": [0, 0, 0],
    "qubit_gain": 5200,
    'qubit_freq': 4215.2,
    "pulse_freq": 249.6
}
# parameter = {
#     "FF": [15000, 15000, 0],
#     "qubit_gain": 4800,
#     'qubit_freq': 4691.9,
#     "pulse_freq": 442.85
# }
# parameter = {
#     "FF": [15000, 15000, 0],
#     "qubit_gain": 3800,
#     'qubit_freq': 4528.25 + 3,
#     "pulse_freq": 640.83
# }

# drive_parameters = {
#     "qubit_gain": 4650,
#     'qubit_freq': 4384.65,
# }
# drive_parameters = {
#     "qubit_gain": 4800,
#     'qubit_freq': 4691.9,
# }
# drive_parameters = {
#     "qubit_gain": 3800,
#     'qubit_freq': 4528.25 + 3,
# }
#
# parameter = parameter | drive_parameters
print(parameter)

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
UpdateConfig_FF_multiple = UpdateConfig_FF_multiple | UpdateConfig_FF_pulse


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
    "shots": 2500, ### this gets turned into "reps"
    "relax_delay": 300,  # us
}
config = BaseConfig | UpdateConfig_FF | UpdateConfig | UpdateConfig_FF_multiple

print(config)
#

# Instance_SingleShotProgram = SingleShotProgram(path="dataSingleShot", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
# data_SingleShotProgram = SingleShotProgram.acquire(Instance_SingleShotProgram)
# # print(data_SingleShotProgram)
# SingleShotProgram.display(Instance_SingleShotProgram, data_SingleShotProgram, plotDisp=True)
#
# SingleShotProgram.save_data(Instance_SingleShotProgram, data_SingleShotProgram)
# SingleShotProgram.save_config(Instance_SingleShotProgram)

# Instance_SingleShotProgram = SingleShotProgramFF(path="dataSingleShot", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
# data_SingleShotProgram = SingleShotProgramFF.acquire(Instance_SingleShotProgram)
# # print(data_SingleShotProgram)
# SingleShotProgramFF.display(Instance_SingleShotProgram, data_SingleShotProgram, plotDisp=True)
#
# SingleShotProgramFF.save_data(Instance_SingleShotProgram, data_SingleShotProgram)
# SingleShotProgramFF.save_config(Instance_SingleShotProgram)


span = 0.8
exp_parameters = {
    ###### cavity
    "cav_Atten_Start": 10,
    "cav_Atten_Stop": 0,
    "cav_Atten_Points": 11,
    "trans_freq_start": parameter["pulse_freq"] - span / 2, #249.6,
    "trans_freq_stop": parameter["pulse_freq"] + span / 2, #250.3,
    "TransNumPoints": 17,
}
config = config | exp_parameters
# # Now lets optimize powers and readout frequencies
# Instance_SingleShotOptimize = ReadOpt_wSingleShotFF(path="dataSingleShot_Optimize", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
# data_SingleShotProgramOptimize = ReadOpt_wSingleShotFF.acquire(Instance_SingleShotOptimize, cavityAtten = cavityAtten)
# # print(data_SingleShotProgram)
# ReadOpt_wSingleShotFF.display(Instance_SingleShotOptimize, data_SingleShotProgramOptimize, plotDisp=True)
#
# ReadOpt_wSingleShotFF.save_data(Instance_SingleShotOptimize, data_SingleShotProgramOptimize)
# ReadOpt_wSingleShotFF.save_config(Instance_SingleShotOptimize)


UpdateConfig = {
    ###### cavity
    "read_pulse_freq": 249.5,  # [MHz] actual frequency is this number + "cavity_LO"
    "cav_atten": 4,
    "read_pulse_style": "const", # --Fixed
    "read_length": 4, # us (length of the pulse applied)
    "adc_trig_offset": 1.2,
    "read_pulse_gain": 30000, # [DAC units]
    ##### qubit spec parameters
    "qubit_pulse_style": "arb",
    "sigma": config["sigma"],  ### units us, define a 20ns sigma
    "qubit_gain": parameter["qubit_gain"],
    "qubit_freq": parameter["qubit_freq"],
    ##### define shots
    "shots": 3000, ### this gets turned into "reps"
    "relax_delay": 300,  # us
}
config = BaseConfig | UpdateConfig_FF | UpdateConfig | UpdateConfig_FF_multiple
cavityAtten.SetAttenuation(config['cav_atten'], printOut=True)

print(config)

#
# Instance_SingleShotProgram = SingleShotProgramFF(path="dataSingleShot", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
# data_SingleShotProgram = SingleShotProgramFF.acquire(Instance_SingleShotProgram)
# # print(data_SingleShotProgram)
# SingleShotProgramFF.display(Instance_SingleShotProgram, data_SingleShotProgram, plotDisp=True)
#
# SingleShotProgramFF.save_data(Instance_SingleShotProgram, data_SingleShotProgram)
# SingleShotProgramFF.save_config(Instance_SingleShotProgram)


span = 5
gain_span = 2000
exp_parameters = {
    ###### cavity
    "gain_Start": parameter["qubit_gain"] - gain_span,
    "gain_Stop": parameter["qubit_gain"] + gain_span,
    "gain_Points": 11,
    "qubit_freq_start": parameter["qubit_freq"] - span / 2, #249.6,
    "qubit_freq_stop": parameter["qubit_freq"] + span / 2, #250.3,
    "QubitNumPoints": 6,
}
config = config | exp_parameters

# Instance_SingleShotOptimize = PiOpt_wSingleShotFF(path="dataSingleShot_Optimize_PiPulse", outerFolder=outerFolder,
#                                                   cfg=config,soc=soc,soccfg=soccfg)
# data_SingleShotProgramOptimize = PiOpt_wSingleShotFF.acquire(Instance_SingleShotOptimize, cavityAtten = cavityAtten)
# # print(data_SingleShotProgram)
# PiOpt_wSingleShotFF.display(Instance_SingleShotOptimize, data_SingleShotProgramOptimize, plotDisp=True)
#
# PiOpt_wSingleShotFF.save_data(Instance_SingleShotOptimize, data_SingleShotProgramOptimize)
# PiOpt_wSingleShotFF.save_config(Instance_SingleShotOptimize)


UpdateConfig = {
    ###### cavity
    "read_pulse_style": "const", # --Fixed
    "read_length": 3, # us (length of the pulse applied)
    "adc_trig_offset": 1,
    "read_pulse_gain": 30000, # [DAC units]
    "read_pulse_freq": 443.05, # [MHz] actual frequency is this number + "cavity_LO"
    ##### define shots
    "shots": 2500, ### this gets turned into "reps"
    "relax_delay": 300,  # us
}
#
# Qubit_pulse = {
#     ##### qubit spec parameters
#     "qubit_pulse_style": "arb",
#     "sigma": config["sigma"],  ### units us, define a 20ns sigma
#     "qubit_gain": 2700,
#     "qubit_freq": 4485.2,
# }
Qubit_pulse = {
    ##### qubit spec parameters
    "qubit_pulse_style": "arb",
    "sigma": config["sigma"],  ### units us, define a 20ns sigma
    "qubit_gain": 5600,
    "qubit_freq": 4587.4,
}

Qubit_pulse_first = {
    "qubit_gain_first": 2700,
    "qubit_freq_first": 4485.2,
}
# Qubit_pulse_first = {
#     "qubit_gain_first": 5600,
#     "qubit_freq_first": 4587.4,
# }

FF_gain1_read = 30000
FF_gain2_read = 30000

FF_gain1_exp = 30000  #Left Qubit
FF_gain2_exp = 30000   #Middle Qubit

UpdateConfig_FF_multiple = {
    "FF_list_readout": [(FF_channel1, FF_gain1_read),
    (FF_channel2, FF_gain2_read)]
}
UpdateConfig_FF_pulse = {
    "FF_list_exp": [(FF_channel1, FF_gain1_exp),
    (FF_channel2, FF_gain2_exp)]
}
UpdateConfig_FF_multiple = UpdateConfig_FF_multiple | UpdateConfig_FF_pulse
config = BaseConfig | UpdateConfig_FF | UpdateConfig | Qubit_pulse | Qubit_pulse_first | UpdateConfig_FF_multiple
# cavityAtten.SetAttenuation(10, printOut=True)

print(config)

# Instance_SingleShotProgram = SingleShotProgramFFPiPulse(path="dataSingleShot", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
# data_SingleShotProgram = SingleShotProgramFFPiPulse.acquire(Instance_SingleShotProgram)
# # print(data_SingleShotProgram)
# SingleShotProgramFFPiPulse.display(Instance_SingleShotProgram, data_SingleShotProgram, plotDisp=True)
#
# SingleShotProgramFFPiPulse.save_data(Instance_SingleShotProgram, data_SingleShotProgram)
# SingleShotProgramFFPiPulse.save_config(Instance_SingleShotProgram)


# Instance_SingleShotProgram = SingleShotProgramFF(path="dataSingleShot", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
# data_SingleShotProgram = SingleShotProgramFF.acquire(Instance_SingleShotProgram)
# # print(data_SingleShotProgram)
# SingleShotProgramFF.display(Instance_SingleShotProgram, data_SingleShotProgram, plotDisp=True)
#
# SingleShotProgramFF.save_data(Instance_SingleShotProgram, data_SingleShotProgram)
# SingleShotProgramFF.save_config(Instance_SingleShotProgram)

