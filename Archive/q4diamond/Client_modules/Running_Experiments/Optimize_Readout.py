import matplotlib.pyplot as plt
from q4diamond.Client_modules.socProxy import makeProxy, soc, soccfg
import h5py
from q4diamond.Client_modules.PythonDrivers.control_atten import setatten
import q4diamond.Client_modules.PythonDrivers.YOKOGS200 as YOKOGS200
import os
# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')

from q4diamond.Client_modules.initialize import *
from q4diamond.Client_modules.Experiment_Scripts.mOptimizeReaout import Optimize_Power
from q4diamond.Client_modules.mTransmission import Transmission
from q4diamond.Client_modules.mSpecSlice import SpecSlice
from q4diamond.Client_modules.mAmplitudeRabi import AmplitudeRabi







outerFolder = "Z:\Jeronimo\Measurements\RFSOC_3Qubit\\"

yoko72.SetVoltage(-0.42)
yoko74.SetVoltage(-0.1)
yoko76.SetVoltage(0)

UpdateConfig_transmission={
    "reps": 1000,  # this will used for all experiements below unless otherwise changed in between trials
    "pulse_style": "const", # --Fixed
    "readout_length": soc.us2cycles(3), # [Clock ticks]
    "pulse_gain":30000, # [DAC units]
    "pulse_freq": 250.3, # [MHz] actual frequency is this number + "cavity_LO"
    ##### define tranmission experiment parameters
    "TransSpan": 0.5, ### MHz, span will be center+/- this parameter
    "TransNumPoitns": 60, ### number of points in the transmission frequecny
    "cav_Atten": 25 #### cavity attenuator attenuation value
}
# Configure for qubit experiment
UpdateConfig_qubit = {
    "qubit_pulse_style": "const",
    "qubit_gain": 3000,
    "qubit_freq": 4905,
    "qubit_length": soc.us2cycles(40),
    ##### define spec slice experiment parameters
    "SpecSpan": 12,  ### MHz, span will be center+/- this parameter
    "SpecNumPoitns": 60,  ### number of points in the transmission frequecny
}

expt_cfg = {
    "center": UpdateConfig_qubit["qubit_freq"],
    "span": UpdateConfig_qubit["SpecSpan"],
    "expts": UpdateConfig_qubit["SpecNumPoitns"]
}
expt_cfg["step"] = 2 * expt_cfg["span"] / expt_cfg["expts"]
expt_cfg["start"] = expt_cfg["center"] - expt_cfg["span"]
UpdateConfig_qubit = {**UpdateConfig_qubit, **expt_cfg}


UpdateConfig = UpdateConfig_transmission | UpdateConfig_qubit
config = BaseConfig | UpdateConfig

cavityAtten.SetAttenuation(config["cav_Atten"], printOut=True)

# Instance_trans = Transmission(path="dataTestTransmission", cfg=config,soc=soc,soccfg=soccfg,
#                               outerFolder=outerFolder)
# data_trans= Transmission.acquire(Instance_trans)
# Transmission.display(Instance_trans, data_trans, plotDisp=True, figNum=1)
# Transmission.save_data(Instance_trans, data_trans)

# config["pulse_freq"] = Instance_trans.peakFreq_min
config["pulse_freq"] = 250.25


#### Qubit Spec experiment, readjust the number of reps

config["reps"] = 30
config["rounds"] = 100
print(config["pulse_freq"])
#
# Instance_specSlice = SpecSlice(path="dataTestSpecSlice", cfg=config,soc=soc,soccfg=soccfg,outerFolder=outerFolder)
# data_specSlice= SpecSlice.acquire(Instance_specSlice)
# SpecSlice.display(Instance_specSlice, data_specSlice, plotDisp=True, figNum=2)
# SpecSlice.save_data(Instance_specSlice, data_specSlice)


number_of_steps = 51
step = int(30000 / number_of_steps)
ARabi_config = {'start': 0, 'step': step, "expts": number_of_steps,
                "sigma":soccfg.us2cycles(0.03, gen_ch=2),"f_ge": 4904}
config = config | ARabi_config ### note that UpdateConfig will overwrite elements in BaseConfig

# iAmpRabi = AmplitudeRabi(path="dataAmpRabi", cfg=config,soc=soc,soccfg=soccfg,
# outerFolder=outerFolder)
# dAmpRabi = AmplitudeRabi.acquire(iAmpRabi)
# AmplitudeRabi.display(iAmpRabi, dAmpRabi, plotDisp=True, figNum=2)
# AmplitudeRabi.save_data(iAmpRabi, dAmpRabi)

expt_cfg={ "reps": 2000, "rounds": 1,"pi_gain": 6800, "relax_delay" : 500
       }

config = config | expt_cfg

#Next, optimize your pi pulse:

config["CavityAtten_Start"] = 40
config["CavityAtten_End"] = 0
config["CavityAtten_Points"] = 21


iOptimized = Optimize_Power(path="dataAmpRabi", cfg=config,soc=soc,soccfg=soccfg,
outerFolder=outerFolder, cavityAtten = cavityAtten)
dOptimized = Optimize_Power.acquire(iOptimized)
Optimize_Power.display(iOptimized, dOptimized, plotDisp=True, figNum=2)
Optimize_Power.save_data(iOptimized, dOptimized)

