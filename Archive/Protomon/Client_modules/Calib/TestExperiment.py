
#### import packages
import os
path = os.getcwd()
os.add_dll_directory(os.path.dirname(path)+'\\PythonDrivers')
from Protomon.Client_modules.Calib.initialize import *
#from Protomon.Client_modules.Helpers.hist_analysis import *
#from Protomon.Client_modules.Helpers.MixedShots_analysis import *
from matplotlib import pyplot as plt

from Protomon.Client_modules.Experiments.mTransmission import Transmission
# from Protomon.Client_modules.Experiments.mSpecSlice import SpecSlice
#from Protomon.Client_modules.Experiments.mSpecSlice_SaraTest import SpecSlice

from Protomon.Client_modules.Experiments.mSpecSlice_ShashwatTest import SpecSlice

from Protomon.Client_modules.Experiments.mSpecVsFlux import SpecVsFlux
from Protomon.Client_modules.Experiments.mSingleShotProgram import SingleShotProgram
from Protomon.Client_modules.Experiments.mAmplitudeRabi_ShashwatTest import AmplitudeRabi
from Protomon.Client_modules.Experiments.mAmplitudeRabi_Blob_ShashwatTest import AmplitudeRabi_Blob
from Protomon.Client_modules.Experiments.mT1Experiment import T1Experiment
from Protomon.Client_modules.Experiments.mT2Experiment import T2Experiment
#from Protomon.Client_modules.Experiments.mfastFlux import LoopbackProgramFastFlux
#from Protomon.Client_modules.Experiments.mTransVsAtten import TransVsAtten
from Protomon.Client_modules.Experiments.mTransVsGain import TransVsGain
from Protomon.Client_modules.Experiments.mLoopback import Loopback

#### define the saving path
outerFolder = "Y:\Shashwat\Data\Protomon\FMV7_A2\\"

#### define the attenuators
#cavityAtten = attenuator(27787, attenuation_int= 35, print_int = False)
###qubitAtten = attenuator(27797, attenuation_int= 10, print_int = False)

# Configure for transmission experiment
UpdateConfig_transmission={

    #"cav_Atten": 35, #### cavity attenuator attenuation value
}


# Configure for qubit experiment
UpdateConfig_qubit = {
    "qubit_pulse_style": "const",
    "qubit_gain": 0,
    "qubit_freq": 4987,
    "qubit_length": 1000,
    ##### define spec slice experiment parameters
    "qubit_freq_start": 4915,
    "qubit_freq_stop": 5015,
    "SpecNumPoints": 150,  ### number of points
    "qubit_Atten": 10, ### qubit attenuator value
    'spec_reps': 100,
    ##### define the yoko voltage
    "yokoVoltage": -0.053,

}

#UpdateConfig = UpdateConfig_transmission | UpdateConfig_qubit
#config = BaseConfig | UpdateConfig_transmission ### note that UpdateConfig will overwrite elements in BaseConfig
config = {**BaseConfig, **UpdateConfig_transmission}
#### update the qubit and cavity attenuation
# cavityAtten.SetAttenuation(config["cav_Atten"])
###qubitAtten.SetAttenuation(config["qubit_Atten"])

# ### set the yoko frequency
# yoko1.SetVoltage(config["yokoVoltage"])
# print("Voltage is ", yoko1.GetVoltage(), " Volts")

#################################### Running the actual experiments

# Only run this if no proxy already exists
soc, soccfg = makeProxy()
# print(soccfg)

plt.ioff()

###################################### code for runnning basic transmission and specSlice

# Run loopback as a sanity check
#
# config = {"res_ch": 0,  # --Fixed
#           "ro_chs": [0],  # --Fixed
#           "reps": 1,  # --Fixed
#           "relax_delay": 1.0,  # --us
#           "res_phase": 0,  # --degrees
#           "pulse_style": "arb",  # --Fixed
#
#           "sigma": 50,  # [Clock ticks]
#           # Try varying sigma from 10-50 clock ticks
#
#           "readout_length": 300,  # [Clock ticks]
#           # Try varying readout_length from 50-1000 clock ticks
#
#           "pulse_gain": 20000,  # [DAC units]
#           # Try varying pulse_gain from 500 to 30000 DAC units
#
#           "pulse_freq": 4729,#1000,  # [MHz]
#           # In this program the signal is up and downconverted digitally so you won't see any frequency
#           # components in the I/Q traces below. But since the signal gain depends on frequency,
#           # if you lower pulse_freq you will see an increased gain.
#
#           "adc_trig_offset": 0.510,  # [us]
#           # Try varying adc_trig_offset from 100 to 220 clock ticks
#
#           "soft_avgs": 5000
#           # Try varying soft_avgs from 1 to 200 averages
#
#           }
#
# Instance = Loopback(path="dataTestLoopback", cfg=config, soc=soc, soccfg=soccfg, outerFolder = outerFolder)
# data = Loopback.acquire(Instance)
# Loopback.display(Instance, data)
# Loopback.save_data(Instance, data)

config={
        "res_ch": 0, #5, # --Fixed
        "qubit_ch": 2, #1,  # --Fixed
        "mixer_freq":0.0, # MHz
        "ro_chs":[0], #0 , # --Fixed
        "reps":2000, # --Fixed
        "nqz":1, #### refers to cavity
        "qubit_nqz": 1,
        "relax_delay":20, # us, cavity relax delay
        "res_phase":0, # --Fixed
        # "pulse_style": "const", # --Fixed
        "read_length": 7, # units us, previously this was just names "length"
        "read_pulse_style": "const",  # --Fixed
        "read_pulse_gain": 100,  # 3000, # [DAC units]
        "read_pulse_freq": 4728,  # [MHz] actual frequency is this number + "cavity_LO"
        "adc_trig_offset": 0.510,  # [us]
        "cavity_LO": 0,
        ##### define tranmission experiment parameters
        "TransSpan": 5,  ### MHz, span will be center+/- this parameter
        "TransNumPoints": 351,  ### number of points in the transmission frequecny
        ### trans vs gain specific parameters
        "trans_gain_start": 1,
        "trans_gain_stop": 100,
        "trans_gain_num": 51,
        "trans_freq_start": 4726,  # [MHz] actual frequency is this number + "cavity_LO"
        "trans_freq_stop": 4732,  # [MHz] actual frequency is this number + "cavity_LO"
        "trans_reps": 5000,  # --Fixed
        "yokoVoltage": 0.11,
        ### trans vs gain specific parameters
}

# # ### perform the cavity transmission experiment
# yoko1.SetVoltage(config["yokoVoltage"])
# Instance_trans = Transmission(path="dataTestTransmission", cfg=config,soc=soc,soccfg=soccfg, outerFolder = outerFolder)
# data_trans= Transmission.acquire(Instance_trans)
# Transmission.display(Instance_trans, data_trans, plotDisp=True)
# Transmission.save_data(Instance_trans, data_trans)

# ### change gain instead of attenuation
# Instance_TransVsGain = TransVsGain(path="dataTestTransVsGain", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
# data_TransVsGain = TransVsGain.acquire(Instance_TransVsGain)
# TransVsGain.save_data(Instance_TransVsGain, data_TransVsGain)
# TransVsGain.save_config(Instance_TransVsGain)
#
# UpdateConfig_qubit = {
#     "qubit_pulse_style": "const",
#     "qubit_gain": 700,
#     "relax_delay":20, # for cavity, us
#     "qubit_freq": 2556  ,
#     "qubit_length": 50,#us
#     "qubit_relax_delay": 20, #700  # for qubit, should be 10*T1 roughly (predicted?)
#     ##### define spec slice experiment parameters
#     "qubit_freq_start": 2540,
#     "qubit_freq_stop": 2560,
#     "SpecNumPoints": 101,  ### number of points
#     #"qubit_Atten": 10, ### qubit attenuator value
#     'spec_reps': 20, #15000,
#     'spec_rounds': 500,
#     ##### define the yoko voltage
#     "yokoVoltage": 0.08, #yoko not working from here, figure out how to use it
#     "read_pulse_style": "const",  # --Fixed
#     #"readout_length": soc.us2cycles(5),  # [Clock ticks]
#     "read_length": 20,
#     "read_pulse_gain": 100,  # [DAC units]
#     "read_pulse_freq": 4729.1,  # [MHz] actual frequency is this number + "cavity_LO
#     ##### amplitude rabi parameters
#     "sigma": 0.050,  ### units us, define a 20ns sigma
#     "qubit_pulse_style": "arb",  # --Fixed
#     "qubit_gain_start": 0,
#     "qubit_gain_step": 50, ### stepping amount of the qubit gain
#     "qubit_gain_expts": 151, ### number of steps
#     "AmpRabi_reps": 10,  # number of averages for the experiment
#     "AmpRabi_rounds": 1000,  # number of averages for the experiment
#     ##### define the yoko voltage
#     "yokoVoltageStart": 0.1,
#     "yokoVoltageStop": -0.1,
#     "yokoVoltageNumPoints": 51,
#     "trans_freq_start": 4723,  # [MHz] actual frequency is this number + "cavity_LO"
#     "trans_freq_stop": 4733,  # [MHz] actual frequency is this number + "cavity_LO"
#     "TransNumPoints": 11,#101,  ### number of points in the transmission frequecny
#     "trans_reps": 2000,
# }

#UpdateConfig = UpdateConfig_transmission | UpdateConfig_qubit
#config = BaseConfig | UpdateConfig_transmission ### note that UpdateConfig will overwrite elements in BaseConfig
# config = {**BaseConfig, **UpdateConfig_qubit}

config = {'res_ch': 0, 'qubit_ch': 2, 'mixer_freq': 0.0, 'ro_chs': [0],
 'nqz': 1, 'qubit_nqz': 1, 'relax_delay': 20, 'res_phase': 0,
 'adc_trig_offset': 0.51, 'cavity_LO': 0, 'qubit_pulse_style': 'arb', 'qubit_gain': 1000,
 'qubit_freq': 2494.9, 'qubit_length': 50, 'qubit_relax_delay': 2000, 'qubit_freq_start': 2480,
 'qubit_freq_stop': 2518, 'SpecNumPoints': 101, 'spec_reps': 10, 'spec_rounds': 10, 'yokoVoltage': 0.11,
 'read_pulse_style': 'const', 'read_pulse_gain': 100, 'read_pulse_freq': 4729.1,
 'sigma': 0.08, 'qubit_gain_start': 0, 'qubit_gain_step': 750, 'qubit_gain_expts': 39, 'AmpRabi_reps': 10, 'AmpRabi_rounds': 5000, # 4000
 'yokoVoltageStart': .1, 'yokoVoltageStop': 0.25, 'yokoVoltageNumPoints': 41,
 'trans_freq_start': 4723, 'trans_freq_stop': 4733, 'TransNumPoints': 101, 'trans_reps': 2000, 'trans_rounds': 1,
 'qubit_freq_start_rabiBlob': 2494, 'qubit_freq_stop_rabiBlob': 2496, 'qubit_freq_expts_rabiBlob': 8,
 'qubit_gain_pi': 8000, 'shots':1000, 'read_length': 10}

# yoko1.SetVoltage(config["yokoVoltage"])
# Instance_trans = Transmission(path="dataTestTransmission", cfg=config,soc=soc,soccfg=soccfg, outerFolder = outerFolder)
# data_trans= Transmission.acquire(Instance_trans)
# Transmission.display(Instance_trans, data_trans, plotDisp=True)
# Transmission.save_data(Instance_trans, data_trans)
#
# ### update the transmission frequency to be the peak
# config["read_pulse_freq"] = Instance_trans.peakFreq
# print("new cavity freq =", config["read_pulse_freq"])
# # config["read_pulse_freq"] = 4729.581196581196
#
# Instance_specSlice = SpecSlice(path="dataTestSpecSlice", cfg=config,soc=soc,soccfg=soccfg, outerFolder = outerFolder)
# data_specSlice= SpecSlice.acquire(Instance_specSlice)
# SpecSlice.display(Instance_specSlice, data_specSlice, plotDisp=True)
# SpecSlice.save_data(Instance_specSlice, data_specSlice)

# Instance_SpecVsFlux = SpecVsFlux(path="dataTestSpecVsFlux", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
# data_SpecVsFlux = SpecVsFlux.acquire(Instance_SpecVsFlux,plotDisp = False, plotSave = True)
# SpecVsFlux.save_data(Instance_SpecVsFlux, data_SpecVsFlux)
# SpecVsFlux.save_config(Instance_SpecVsFlux)

## update the spec frequency to be the peak
# config["qubit_freq"] = Instance_specSlice.qubitFreq
# print("new qubit freq: " + str(config["qubit_freq"]))

# # ##### run the single shot experiment
Instance_SingleShotProgram = SingleShotProgram(path="dataTestSingleShotProgram", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
data_SingleShot = SingleShotProgram.acquire(Instance_SingleShotProgram)
SingleShotProgram.display(Instance_SingleShotProgram, data_SingleShot, plotDisp=False)
SingleShotProgram.save_data(Instance_SingleShotProgram, data_SingleShot)
SingleShotProgram.save_config(Instance_SingleShotProgram)

# Instance_AmplitudeRabi = AmplitudeRabi(path="dataTestAmplitudeRabi", cfg=config,soc=soc,soccfg=soccfg, outerFolder = outerFolder)
# data_AmplitudeRabi = AmplitudeRabi.acquire(Instance_AmplitudeRabi)
# AmplitudeRabi.display(Instance_AmplitudeRabi, data_AmplitudeRabi, plotDisp=True)
# AmplitudeRabi.save_data(Instance_AmplitudeRabi, data_AmplitudeRabi)
# AmplitudeRabi.save_config(Instance_AmplitudeRabi)

#
# Instance_AmplitudeRabi_Blob = AmplitudeRabi_Blob(path="dataTestRabiAmpBlob", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
# data_AmplitudeRabi_Blob = AmplitudeRabi_Blob.acquire(Instance_AmplitudeRabi_Blob, plotDisp = False, plotSave = True)
# AmplitudeRabi_Blob.save_data(Instance_AmplitudeRabi_Blob, data_AmplitudeRabi_Blob)
# AmplitudeRabi_Blob.save_config(Instance_AmplitudeRabi_Blob)



########################################################################################################################
#
# ####################################### code for transmission vs power
# UpdateConfig = {
#     ##### define attenuators
#     #"cav_Atten": 50,  #### cavity attenuator attenuation value
#     "yokoVoltage": .1,
#     # ##### define the attenuator values
#     # "trans_attn_start": 30,
#     # "trans_attn_stop": 10,
#     # "trans_attn_num": 21,
#     ##### change gain instead option
#     "trans_gain_start": 0,
#     "trans_gain_stop": 7500,
#     "trans_gain_num": 76,
#     ###### cavity
#     "trans_reps": 2000,  # this will used for all experiements below unless otherwise changed in between trials
#     "read_pulse_style": "const",  # --Fixed
#     "readout_length": 15,  # [Clock ticks]
#     # "read_pulse_gain": 10000,  # [DAC units]
#     "trans_freq_start": 890.0,  # [MHz] actual frequency is this number + "cavity_LO"
#     "trans_freq_stop": 895.0,  # [MHz] actual frequency is this number + "cavity_LO"
#     "TransNumPoints": 200,  ### number of points in the transmission frequecny
# }
#
# #config = BaseConfig | UpdateConfig
# config = {**BaseConfig, **UpdateConfig}
# # #### update the qubit and cavity attenuation
# # cavityAtten.SetAttenuation(config["cav_Atten"])
# # yoko1.SetVoltage(config["yokoVoltage"])
# #
# # # ##### run actual experiment
# # # Instance_TransVsAtten = TransVsAtten(path="dataTestTransVsAtten", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
# # # data_TransVsAtten = TransVsAtten.acquire(Instance_TransVsAtten)
# # # TransVsAtten.save_data(Instance_TransVsAtten, data_TransVsAtten)
# # # TransVsAtten.save_config(Instance_TransVsAtten)
# #
#
#
# # ########################################################################################################################
#
#
#
# ####################################### code for running spec vs flux experiement
# UpdateConfig = {
#     ##### define attenuators
#     #"qubit_Atten": 20,  ### qubit attenuator value
#     #"cav_Atten": 50,  #### cavity attenuator attenuation value
#     ##### define the yoko voltage
#     "yokoVoltageStart": 0,
#     "yokoVoltageStop": .01,
#     "yokoVoltageNumPoints": 3,
#     ###### cavity
#     "trans_reps": 100,  # this will used for all experiements below unless otherwise changed in between trials
#     "read_pulse_style": "const",  # --Fixed
#     "readout_length": 20,  # [Clock ticks]
#     "pulse_gain": 100,  # [DAC units]
#     "trans_freq_start": 4726.4,  # [MHz] actual frequency is this number + "cavity_LO"
#     "trans_freq_stop": 4730.4,  # [MHz] actual frequency is this number + "cavity_LO"
#     "TransNumPoints": 21,  ### number of points in the transmission frequecny
#     ##### qubit spec parameters
#     "spec_reps": 100,
#     "qubit_pulse_style": "const",
#     "qubit_gain": 1000,
#     "qubit_length": 50, ###us
#     "qubit_freq_start": 2500,
#     "qubit_freq_stop": 3000,
#     "SpecNumPoints": 11,  ### number of points
# }
#
# #config = BaseConfig | UpdateConfig
# config = {**BaseConfig, **UpdateConfig}
# # #### update the qubit and cavity attenuation
# # cavityAtten.SetAttenuation(config["cav_Atten"])
# # ###qubitAtten.SetAttenuation(config["qubit_Atten"])
# #
# ##### run actual experiment
# Instance_SpecVsFlux = SpecVsFlux(path="dataTestSpecVsFlux", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
# data_SpecVsFlux = SpecVsFlux.acquire(Instance_SpecVsFlux)
# SpecVsFlux.save_data(Instance_SpecVsFlux, data_SpecVsFlux)
# SpecVsFlux.save_config(Instance_SpecVsFlux)
#
#
#
# ####################################### code for running basic single shot exerpiment
# UpdateConfig = {
#     ##### define attenuators
#     "qubit_Atten": 0,  ### qubit attenuator value
#     "cav_Atten": 45,  #### cavity attenuator attenuation value
#     "yokoVoltage": -0.060,
#     ###### cavity
#     "reps": 2000,  # this will used for all experiements below unless otherwise changed in between trials
#     "read_pulse_style": "const", # --Fixed
#     "readout_length": soc.us2cycles(5), # [Clock ticks]
#     "read_pulse_gain":30000, # [DAC units]
#     "read_pulse_freq": 1000, # [MHz] actual frequency is this number + "cavity_LO"
#     ##### qubit spec parameters
#     "qubit_pulse_style": "arb",
#     "qubit_gain": 30000,
#     "qubit_length": 10,  ###us, this is used if pulse style is const
#     "sigma": 0.050,  ### units us, define a 20ns sigma
#     "qubit_freq": 4927.33,
#     ##### define shots
#     "shots": 2000, ### this gets turned into "reps"
# }
# #config = BaseConfig | UpdateConfig
# config = {**BaseConfig, **UpdateConfig}
# # yoko1.SetVoltage(config["yokoVoltage"])
# # cavityAtten.SetAttenuation(config["cav_Atten"])
# # ###qubitAtten.SetAttenuation(config["qubit_Atten"])
# #
# # ##### run the single shot experiment
# # Instance_SingleShotProgram = SingleShotProgram(path="dataTestSingleShotProgram", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
# # data_SingleShot = SingleShotProgram.acquire(Instance_SingleShotProgram)
# # SingleShotProgram.display(Instance_SingleShotProgram, data_SingleShot, plotDisp=True)
#
#
# # ####################################### code for running Amplitude rabi
# UpdateConfig = {
#     ##### define attenuators
#     "qubit_Atten": 0,  ### qubit attenuator value
#     "cav_Atten": 24,  #### cavity attenuator attenuation value
#     "yokoVoltage": -0.055,
#     ###### cavity
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 2, # us
#     "read_pulse_gain": 30000, # [DAC units]
#     "read_pulse_freq": 1000, # [MHz] actual frequency is this number + "cavity_LO"
#     "TransSpan": 1, ### MHz, span will be center+/- this parameter
#     "TransNumPoitns": 100, ### number of points in the transmission frequecny
#     "trans_reps": 1000,  # this will used for all experiements below unless otherwise changed in between trials
#     ##### spec parameters for finding the qubit frequency
#     "qubit_freq_start": 4880,
#     "qubit_freq_stop": 4980,
#     "SpecNumPoints": 200,  ### number of points
#     "qubit_gain": 5000,
#     "sigma": 0.050,  ### units us, define a 20ns sigma
#     "qubit_pulse_style": "arb", #### arb means gaussain here
#     "relax_delay": 50,  ### turned into us inside the run function
#     "spec_reps": 2000, ### number of reps
#     ##### amplitude rabi parameters
#     "qubit_freq": 4969.0, ### just an estimate
#     "qubit_gain_start": 0,
#     "qubit_gain_step": 300, ### stepping amount of the qubit gain
#     "qubit_gain_expts": 100, ### number of steps
#     "AmpRabi_reps": 2000,  # number of averages for the experiment
# }
# #config = BaseConfig | UpdateConfig
# config = {**BaseConfig, **UpdateConfig}
#
# # yoko1.SetVoltage(config["yokoVoltage"])
# # cavityAtten.SetAttenuation(config["cav_Atten"])
# ###qubitAtten.SetAttenuation(config["qubit_Atten"])
#
# # Instance_trans = Transmission(path="dataTestTransmission", cfg=config,soc=soc,soccfg=soccfg, outerFolder = outerFolder)
# # data_trans= Transmission.acquire(Instance_trans)
# # Transmission.display(Instance_trans, data_trans, plotDisp=True)
# # Transmission.save_data(Instance_trans, data_trans)
# #
# # plt.show(block=False)
# # plt.pause(0.1)
# #
# # ### update the transmission frequency to be the peak
# # config["read_pulse_freq"] = Instance_trans.peakFreq
#
# Instance_specSlice = SpecSlice(path="dataTestSpecSlice", cfg=config,soc=soc,soccfg=soccfg, outerFolder = outerFolder)
# data_specSlice= SpecSlice.acquire(Instance_specSlice)
# SpecSlice.display(Instance_specSlice, data_specSlice, plotDisp=True)
# SpecSlice.save_data(Instance_specSlice, data_specSlice)
# #
# # plt.show(block=False)
# # plt.pause(0.1)
# #
# # ## update the transmission frequency to be the peak
# # config["qubit_freq"] = Instance_specSlice.qubitFreq
# # print("new qubit freq: " + str(config["qubit_freq"]))
# #
# # Instance_AmplitudeRabi = AmplitudeRabi(path="dataTestAmplitudeRabi", cfg=config,soc=soc,soccfg=soccfg, outerFolder = outerFolder)
# # data_AmplitudeRabi = AmplitudeRabi.acquire(Instance_AmplitudeRabi)
# # AmplitudeRabi.display(Instance_AmplitudeRabi, data_AmplitudeRabi, plotDisp=True)
# # AmplitudeRabi.save_data(Instance_AmplitudeRabi, data_AmplitudeRabi)
# # AmplitudeRabi.save_config(Instance_AmplitudeRabi)
#
#
# # ####################################### code for running Amplitude rabi
# UpdateConfig = {
#     ##### define attenuators
#     #"cav_Atten": 17,  #### cavity attenuator attenuation value
#     "yokoVoltage": 0.06,
#     ###### cavity
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 20, # us
#     "read_pulse_gain": 100, # [DAC units]
#      "read_pulse_freq": 4729.3, # [MHz] actual frequency is this number + "cavity_LO"
#     ##### spec parameters for finding the qubit frequency
#     "qubit_freq_start": 2545,
#     "qubit_freq_stop": 2570,
#     "RabiNumPoints": 6,  ### number of points
#     "qubit_pulse_style": "arb",
#     "sigma": 0.020,  ### units us, define a 20ns sigma
#     #"flat_top_length": 0.025, ### in us
#     "relax_delay": 700,  ### turned into us inside the run function
#     ##### amplitude rabi parameters
#     "qubit_gain_start": 0,
#     "qubit_gain_step": 20, ### stepping amount of the qubit gain
#     "qubit_gain_expts": 501, ### number of steps
#     "AmpRabi_reps": 10000,  # number of averages for the experiment
# }
# #config = BaseConfig | UpdateConfig
# config = {**BaseConfig, **UpdateConfig}
# yoko1.SetVoltage(config["yokoVoltage"])
# # cavityAtten.SetAttenuation(config["cav_Atten"])
#
# Instance_AmplitudeRabi_Blob = AmplitudeRabi_Blob(path="dataTestRabiAmpBlob", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
# data_AmplitudeRabi_Blob = AmplitudeRabi_Blob.acquire(Instance_AmplitudeRabi_Blob)
# AmplitudeRabi_Blob.save_data(Instance_AmplitudeRabi_Blob, data_AmplitudeRabi_Blob)
# AmplitudeRabi_Blob.save_config(Instance_AmplitudeRabi_Blob)
#
#
# ######################################################################################################################
# ########### T1 measurement
# UpdateConfig = {
#     ##### define attenuators
#     "cav_Atten": 15,  #### cavity attenuator attenuation value
#     "yokoVoltage": -0.055,
#     ###### cavity
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 10, # us
#     "read_pulse_gain": 30000, # [DAC units]
#     "read_pulse_freq": 891.0, # [MHz] actual frequency is this number + "cavity_LO"
#     ##### spec parameters for finding the qubit frequency
#     "qubit_freq": 4937.0,
#     "qubit_gain": 27000,
#     "sigma": 0.025,  ### units us, define a 20ns sigma
#     "qubit_pulse_style": "arb", #### arb means gaussain here
#     "relax_delay": 1000,  ### turned into us inside the run function
#     ##### T1 parameters
#     "start": 0, ### us
#     "step": 1, ### us
#     "expts": 500, ### number of experiemnts
#     "reps": 1000, ### number of averages on each experiment
# }
# config = BaseConfig | UpdateConfig
#
# # yoko1.SetVoltage(config["yokoVoltage"])
# # cavityAtten.SetAttenuation(config["cav_Atten"])
# #
# # Instance_T1Experiment = T1Experiment(path="dataTestT1Experiment", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
# # data_T1Experiment = T1Experiment.acquire(Instance_T1Experiment)
# # T1Experiment.display(Instance_T1Experiment, data_T1Experiment, plotDisp=True)
# # T1Experiment.save_data(Instance_T1Experiment, data_T1Experiment)
# # T1Experiment.save_config(Instance_T1Experiment)
#
#
# ######################################################################################################################
# ########### T2 measurement
# UpdateConfig = {
#     ##### define attenuators
#     "cav_Atten": 15,  #### cavity attenuator attenuation value
#     "yokoVoltage": -0.055,
#     ###### cavity
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 10, # us
#     "read_pulse_gain": 30000, # [DAC units]
#     "read_pulse_freq": 891.0, # [MHz] actual frequency is this number + "cavity_LO"
#     ##### spec parameters for finding the qubit frequency
#     "qubit_freq": 4937.0 - 10,
#     "qubit_gain": 27000,
#     "sigma": 0.025,  ### units us, define a 20ns sigma
#     "qubit_pulse_style": "arb", #### arb means gaussain here
#     "relax_delay": 1500,  ### turned into us inside the run function
#     ##### T2 ramsey parameters
#     "start": 0.010, ### us
#     "step": 0.005, ### us
#     "expts": 150, ### number of experiemnts
#     "reps": 200, ### number of averages on each experiment
# }
# config = BaseConfig | UpdateConfig
#
# # yoko1.SetVoltage(config["yokoVoltage"])
# # cavityAtten.SetAttenuation(config["cav_Atten"])
# #
# # Instance_T2Experiment = T2Experiment(path="dataTestT2Experiment", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
# # data_T2Experiment = T2Experiment.acquire(Instance_T2Experiment)
# # T2Experiment.display(Instance_T2Experiment, data_T2Experiment, plotDisp=True)
# # T2Experiment.save_data(Instance_T2Experiment, data_T2Experiment)
# # T2Experiment.save_config(Instance_T2Experiment)
#
# ###################################################################################################################
# ###### testing fast flux experiement
# config={
#     "reps": 2000,  # this will used for all experiements below unless otherwise changed in between trials
#     # "ff_pulse_style": "const", # --Fixed
#     "ff_length": soc.us2cycles(100), # [Clock ticks]
#     "ff_gain": 10000, # [DAC units]
#     "ff_freq": 0, # [MHz] actual frequency is this number + "cavity_LO"
#     ##### define tranmission experiment parameters
#     # "ff_nqz": 1, ### MHz, span will be center+/- this parameter
#     "relax_delay": 50, ### number of points in the transmission frequecny
#     # "ff_ch": 4, #### cavity attenuator attenuation value
#     "soft_avgs": 20000
# }
#
# #
# # ###prog = LoopbackProgramFastFlux(soccfg, config)
# # ###prog.acquire_decimated(soc, load_pulses=True, progress=False)



#####################################################################################################################
plt.show()

# #
# plt.show(block = True)
