import matplotlib.pyplot as plt
from q3diamond.Client_modules.socProxy import makeProxy, soc, soccfg
import h5py
from q3diamond.Client_modules.PythonDrivers.control_atten import setatten
import q3diamond.Client_modules.PythonDrivers.YOKOGS200 as YOKOGS200
import os
# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')

from q3diamond.Client_modules.initialize import *
from q3diamond.Client_modules.Experiment_Scripts.mOptimizeReaout import Optimize_Power

from q3diamond.Client_modules.mSpecVsYokoFF import SpecVsYokoFF
from q3diamond.Client_modules.mTransmissionFF import TransmissionFF
from q3diamond.Client_modules.mSpecSliceFF import SpecSliceFF
from q3diamond.Client_modules.mAmplitudeRabiFF import AmplitudeRabiFF
from q3diamond.Client_modules.mT1FF import T1FF
from q3diamond.Client_modules.mT2RFF import T2R




#### define the saving path
outerFolder = "Z:\Jeronimo\Measurements\RFSOC_3Qubit\\"


yoko72.rampstep = 0.0001
yoko74.rampstep = 0.0001
yoko76.rampstep = 0.0001

# yoko72.SetVoltage(-.242 + .03 + 0.008)
# yoko74.SetVoltage(-0.267 + 0.0003)
# yoko76.SetVoltage(0.2885 + 0.0002)

yoko72.SetVoltage(0)
yoko74.SetVoltage(0.2)
yoko76.SetVoltage(0)


#Left Qubit
# resonator_frequency_center = 250.1
# qubit_frequency_center = 4485
# cavity_attenuation = 15
# cavity_min = True

# #Middle Qubit
resonator_frequency_center = 443.1
qubit_frequency_center = 4937.5
# qubit_frequency_center = 4530.4
cavity_attenuation = 5
cavity_min = False

# resonator_frequency_center = 442.85
# qubit_frequency_center = 4520
# cavity_attenuation = 10
# cavity_min = False

# #Right Qubit
# resonator_frequency_center = 641.05
# qubit_frequency_center = 4531.8
# cavity_attenuation = 12
# cavity_min = False


FF_channel = 4 #4 is middle qubit, 6 is left qubit
FF_gain = 0

FF_channel1 = 6 #4 is middle qubit, 6 is left qubit
FF_channel2 = 4 #4 is middle qubit, 6 is left qubit
FF_channel3 = 5 #4 is middle qubit, 6 is left qubit

#Readout
FF_gain1 = 0
FF_gain2 = 0
FF_gain3 = 0


UpdateConfig_FF_multiple = {
    "FF_list_readout": [(FF_channel1, FF_gain1),
    (FF_channel2, FF_gain2), (FF_channel3, FF_gain3)]
}

#experiment(pulse)
FF_gain1_pulse = 0  #Left Qubit
FF_gain2_pulse = 0  #Middle Qubit
FF_gain3_pulse = 0  #Middle Qubit

UpdateConfig_FF_pulse = {
    "FF_list_exp": [(FF_channel1, FF_gain1_pulse),
    (FF_channel2, FF_gain2_pulse), (FF_channel3, FF_gain3_pulse)]
}
UpdateConfig_FF_multiple = UpdateConfig_FF_multiple | UpdateConfig_FF_pulse

UpdateConfig_transmission={
    "reps": 1000,  # this will used for all experiements below unless otherwise changed in between trials
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
    "qubit_gain": 100,
    "qubit_freq": qubit_frequency_center,
    "qubit_length": 100,
    "SpecSpan": 1.5,  ### MHz, span will be center+/- this parameter
    "SpecNumPoints": 61,  ### number of points in the transmission frequecny
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

# Instance_trans = TransmissionFF(path="dataTestTransmissionFF", cfg=config,soc=soc,soccfg=soccfg,
#                               outerFolder=outerFolder)
# data_trans= TransmissionFF.acquire(Instance_trans)
# TransmissionFF.display(Instance_trans, data_trans, plotDisp=True, figNum=1)
# TransmissionFF.save_data(Instance_trans, data_trans)


## update the transmission frequency to be the peak
# if cavity_min:
#     config["pulse_freq"] = Instance_trans.peakFreq_min
# else:
#     config["pulse_freq"] = Instance_trans.peakFreq_max

# config["pulse_freq"] = 640.9
config["pulse_freq"] = 443.24
# config["pulse_freq"] = 249.95


# #### Qubit Spec experiment, readjust the number of reps

config["reps"] = 40
config["rounds"] = 50
print(config["pulse_freq"])

## Fast Flux Version
# Instance_specSlice = SpecSliceFF(path="dataTestSpecSliceFF", cfg=config,soc=soc,soccfg=soccfg,outerFolder=outerFolder)
# data_specSlice= SpecSliceFF.acquire(Instance_specSlice)
# SpecSliceFF.display(Instance_specSlice, data_specSlice, plotDisp=True, figNum=2)
# SpecSliceFF.save_data(Instance_specSlice, data_specSlice)
## Stop Fast Flux Version
#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# Amplitude Rabi
config["ff_additional_length"] = soc.us2cycles(4)
config["reps"] = 40
config["rounds"] = 90

number_of_steps = 51
step = int(12000 / number_of_steps)
ARabi_config = {'start': 0, 'step': step, "expts": number_of_steps,
                "sigma":0.05,"f_ge": 4937.7, "relax_delay": 300}
config = config | ARabi_config ### note that UpdateConfig will overwrite elements in BaseConfig

# iAmpRabi = AmplitudeRabiFF(path="dataAmpRabi", cfg=config,soc=soc,soccfg=soccfg,
#                             outerFolder=outerFolder)
# dAmpRabi = AmplitudeRabiFF.acquire(iAmpRabi)
# AmplitudeRabiFF.display(iAmpRabi, dAmpRabi, plotDisp=True, figNum=2)
# AmplitudeRabiFF.save_data(iAmpRabi, dAmpRabi)

expt_cfg={ "start":0, "step":8, "expts":50, "reps": 50, "rounds": 80,
        "pi_gain": 7500, "relax_delay" : 300
       }

config = config | expt_cfg ### note that UpdateConfig will overwrite elements in BaseConfig
#
# iT1 = T1FF(path="dataT1", cfg=config,soc=soc,soccfg=soccfg,outerFolder=outerFolder)
# dT1 = T1FF.acquire(iT1)
# T1FF.display(iT1, dT1, plotDisp=True, figNum=2)
# T1FF.save_data(iT1, dT1)


T2R_cfg={"start":0, "step":0.1, "phase_step": soccfg.deg2reg(0 * 360/50, gen_ch=2),
         "expts":85, "reps": 50, "rounds": 50, "pi_gain": 7500,
         "pi2_gain": 3750, "relax_delay" : 400, 'f_ge': 4937.7 + 1.2
       }

config = config | T2R_cfg ### note that UpdateConfig will overwrite elements in BaseConfig

iT2R = T2R(path="dataT2R", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
dT2R = T2R.acquire(iT2R)
T2R.display(iT2R, dT2R, plotDisp=True, figNum=2)
T2R.save_data(iT2R, dT2R)

#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

## Now lets start doing Rabi Oscillation stuff:

