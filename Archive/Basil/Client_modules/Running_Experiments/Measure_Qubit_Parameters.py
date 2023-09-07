import matplotlib.pyplot as plt
from Basil.Client_modules.socProxy import makeProxy, soc, soccfg
import h5py
import os
# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')
# import os
# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')


from Basil.Client_modules.initialize import *

# from Basil.Client_modules.mSpecVsYoko import SpecVsYoko
from Basil.Client_modules.mTransmission import Transmission
from Basil.Client_modules.mSpecSlice import SpecSlice
from Basil.Client_modules.mAmplitudeRabi import AmplitudeRabi
#

from Basil.Client_modules.mT1 import T1
from Basil.Client_modules.mT2R import T2R

#### define the saving path
outerFolder = "Z:\Basil\Measurements\\"

resonator_frequency_center = 306.67
qubit_frequency_center = 3830.4
cavity_gain = 5000
qubit_gain = 1500
cavity_min = True


UpdateConfig_transmission={
    "reps": 1000,  # this will used for all experiements below unless otherwise changed in between trials
    "pulse_style": "const", # --Fixed
    "readout_length": 2, # [Clock ticks]
    "pulse_gain": cavity_gain, # [DAC units]
    "pulse_freq": resonator_frequency_center, # [MHz] actual frequency is this number + "cavity_LO"
    "TransSpan": 2, ### MHz, span will be center+/- this parameter
    "TransNumPoints": 101, ### number of points in the transmission frequecny
}
# Configure for qubit experiment
UpdateConfig_qubit = {
    "qubit_pulse_style": "const",
    "qubit_gain": qubit_gain,
    "qubit_freq": qubit_frequency_center,
    "qubit_length": 80,
    "SpecSpan": 4,  ### MHz, span will be center+/- this parameter
    "SpecNumPoints": 51,  ### number of points in the transmission frequecny
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


#################################### Running the actual experiments

# Only run this if no proxy already exists
# soc, soccfg = makeProxy()
# print(soccfg)

# plt.ioff()

###################################### code for runnning basic transmission and specSlice
### perform the cavity transmission experiment
#

config["reps"] = 10
config["rounds"] = 10

# Instance_trans = Transmission(path="dataTestTransmission", cfg=config,soc=soc,soccfg=soccfg,
#                               outerFolder=outerFolder)
# data_trans= Transmission.acquire(Instance_trans)
# Transmission.display(Instance_trans, data_trans, plotDisp=True, figNum=1)
# Transmission.save_data(Instance_trans, data_trans)
#
# # update the transmission frequency to be the peak
# if cavity_min:
#     config["pulse_freq"] = Instance_trans.peakFreq_min
# else:
#     config["pulse_freq"] = Instance_trans.peakFreq_max

config["pulse_freq"] = 306.67


# #### Qubit Spec experiment, readjust the number of reps

config["reps"] = 30
config["rounds"] = 40
print(config["pulse_freq"])
#
# Instance_specSlice = SpecSlice(path="dataTestSpecSlice", cfg=config,soc=soc,soccfg=soccfg,outerFolder=outerFolder)
# data_specSlice= SpecSlice.acquire(Instance_specSlice)
# SpecSlice.display(Instance_specSlice, data_specSlice, plotDisp=True, figNum=2)
# SpecSlice.save_data(Instance_specSlice, data_specSlice)

#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# Amplitude Rabi

number_of_steps = 51
step = int(10000 / number_of_steps)
ARabi_config = {'start': 0, 'step': step, "expts": number_of_steps,
                "sigma":0.06,"f_ge": 3830.55}
config = config | ARabi_config ### note that UpdateConfig will overwrite elements in BaseConfig

# iAmpRabi = AmplitudeRabi(path="dataAmpRabi", cfg=config,soc=soc,soccfg=soccfg,
# outerFolder=outerFolder)
# dAmpRabi = AmplitudeRabi.acquire(iAmpRabi)
# AmplitudeRabi.display(iAmpRabi, dAmpRabi, plotDisp=True, figNum=2)
# AmplitudeRabi.save_data(iAmpRabi, dAmpRabi)

expt_cfg={ "start":0, "step":10, "expts":61, "reps": 50, "rounds": 50,
        "pi_gain": 5200, "relax_delay" : 500
       }

config = config | expt_cfg ### note that UpdateConfig will overwrite elements in BaseConfig
#
# iT1 = T1(path="dataT1", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
# dT1 = T1.acquire(iT1)
# T1.display(iT1, dT1, plotDisp=False, figNum=2)
# T1.save_data(iT1, dT1)

#from mT2R import T2R

T2R_cfg={"start":0, "step":.7, "phase_step": soccfg.deg2reg(0 * 360/50, gen_ch=2),
         "expts":61, "reps": 200, "rounds": 200, "pi_gain": 5200,
         "pi2_gain": 2600, "relax_delay": 500, 'f_ge': 3830.55
       }

config = config | T2R_cfg ### note that UpdateConfig will overwrite elements in BaseConfig
#
iT2R = T2R(path="dataT2R", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
dT2R = T2R.acquire(iT2R)
T2R.display(iT2R, dT2R, plotDisp=True, figNum=2)
T2R.save_data(iT2R, dT2R)

#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
