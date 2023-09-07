#### import packages
import os
os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
from WTF.Client_modules.Calib.initialize import *
from matplotlib import pyplot as plt

from Experiments.mSpecVsFlux import SpecVsFlux

#### define the saving path
outerFolder = "Z:\JakeB\Data\WTF01_A2_RFSOC\\"

#### define the attenuators
cavityAtten = attenuator(27787, attenuation_int= 35, print_int = False)
###qubitAtten = attenuator(27797, attenuation_int= 10, print_int = False)

#################################### Running the actual experiments

# Only run this if no proxy already exists
soc, soccfg = makeProxy()
# print(soccfg)

plt.ioff()

###################################### code for running spec vs flux experiement
UpdateConfig = {
    ##### define attenuators
    "qubit_Atten": 20,  ### qubit attenuator value, not actively used
    "cav_Atten": 25,  #### cavity attenuator attenuation value
    ##### define the yoko voltage
    "yokoVoltageStart": -0.695, #-0.65,
    "yokoVoltageStop": -0.690, #-0.63,
    "yokoVoltageNumPoints": 51,
    ###### cavity
    "trans_reps": 100,  # this will used for all experiements below unless otherwise changed in between trials
    "read_pulse_style": "const",  # --Fixed
    "read_length": 10,  # us
    "read_pulse_gain": 1500,  # [DAC units]
    "trans_freq_start": 892,  # [MHz] actual frequency is this number + "cavity_LO"
    "trans_freq_stop": 894,  # [MHz] actual frequency is this number + "cavity_LO"
    "TransNumPoints": 300,  ### number of points in the transmission frequecny
    ##### qubit spec parameters
    "spec_reps": 2,
    "qubit_pulse_style": "const",
    "qubit_gain": 20000,
    "qubit_length": 20.00, ### in units of us
    "qubit_freq_start": 4815,
    "qubit_freq_stop": 5015,
    "SpecNumPoints": 2,  ### number of points
    "sigma": None,
    ##### fast flux parameters
    "ff_gain": 0,
    "ff_length": 10,  ### us, this gets repeated 10x
}
config = BaseConfig | UpdateConfig

#######################################################################################################################
########################################################################################################################

#### update the qubit and cavity attenuation
### cavityAtten.SetAttenuation(config["cav_Atten"])
###qubitAtten.SetAttenuation(config["qubit_Atten"])

##### run actual experiment
Instance_SpecVsFlux = SpecVsFlux(path="dataTestSpecVsFlux", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
data_SpecVsFlux = SpecVsFlux.acquire(Instance_SpecVsFlux)
SpecVsFlux.save_data(Instance_SpecVsFlux, data_SpecVsFlux)
SpecVsFlux.save_config(Instance_SpecVsFlux)

#
plt.show(block = True)