from q4diamond.Client_modules.initialize import *

from q4diamond.Client_modules.mSpecVsYokoFF import SpecVsYokoFF




#### define the saving path
outerFolder = "Z:\Jeronimo\Measurements\RFSOC_3Qubit\\"


yoko72.SetVoltage(-0.213)
yoko74.SetVoltage(0.023)
yoko76.SetVoltage(0.52)

#Left Qubit
# resonator_frequency_center = 249.9
# qubit_frequency_center = 4570
# cavity_attenuation = 12
# cavity_min = True

#Middle Qubit
resonator_frequency_center = 442.85
qubit_frequency_center = 4560
cavity_attenuation = 15
cavity_min = False

# #Right Qubit
# resonator_frequency_center = 641.05
# qubit_frequency_center = 4530.4
# cavity_attenuation = 12
# cavity_min = False


FF_channel = 4 #4 is middle qubit, 6 is left qubit
FF_gain = 0

FF_channel1 = 6 #4 is middle qubit, 6 is left qubit
FF_gain1 = 0
FF_channel2 = 4 #4 is middle qubit, 6 is left qubit
FF_gain2 = 0




UpdateConfig_FF_multiple = {
    "FF_list": [(FF_channel1, FF_gain1),
    (FF_channel2, FF_gain2)]
}


UpdateConfig_transmission={
    "trans_reps": 1000,  # this will used for all experiements below unless otherwise changed in between trials
    "pulse_style": "const", # --Fixed
    "readout_length": 3, # [Clock ticks]
    "pulse_gain": 30000, # [DAC units]
    "pulse_freq": resonator_frequency_center, # [MHz] actual frequency is this number + "cavity_LO"
    "TransSpan": 0.5, ### MHz, span will be center+/- this parameter
    "TransNumPoints": 60, ### number of points in the transmission frequecny
    "cav_Atten": cavity_attenuation, #### cavity attenuator attenuation value
}
# Configure for qubit experiment
UpdateConfig_qubit = {
    "qubit_pulse_style": "const",
    "qubit_gain": 750,
    "qubit_freq": qubit_frequency_center,
    "qubit_length": 50,
    "SpecSpan": 35,  ### MHz, span will be center+/- this parameter
    "SpecNumPoints": 71,  ### number of points in the transmission frequecny
    "spec_reps": 40,
    "spec_rounds": 25,
    "cavity_min": cavity_min
}
UpdateConfig_FF = {
    "ff_pulse_style": "const", # --Fixed
    "ff_additional_length": 1, # [Clock ticks]
    "ff_gain": FF_gain, # [DAC units]
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



yoko_params = {
    "yokoStart": 0.03, # [Clock ticks]
    "yokoStop": 0.08, # [DAC units]
    "yokoNumPoints": 11, # [MHz] actual frequency is this number + "cavity_LO"
    "sleep_time": 0.1
}
frequencies_dictionary = {
    "trans_freq_start": config["pulse_freq"] - config["TransSpan"],  # [MHz] actual frequency is this number + "cavity_LO"
    "trans_freq_stop": config["pulse_freq"] + config["TransSpan"],  # [MHz] actual frequency is this number + "cavity_LO"
    "qubit_freq_start": config["qubit_freq"] - config["SpecSpan"],
    "qubit_freq_stop": config["qubit_freq"] + config["SpecSpan"],
}

config = config | yoko_params | frequencies_dictionary
swept_yoko = yoko74

Instance_SpecVsYoko = SpecVsYokoFF(path="dataTestSpecVsYokoFF", outerFolder=outerFolder, cfg=config,
                                 soc=soc,soccfg=soccfg, yoko = swept_yoko)
data_SpecVsYoko = SpecVsYokoFF.acquire(Instance_SpecVsYoko, plotDisp=True, plotSave = True)
SpecVsYokoFF.save_data(Instance_SpecVsYoko, data_SpecVsYoko)
SpecVsYokoFF.save_config(Instance_SpecVsYoko)