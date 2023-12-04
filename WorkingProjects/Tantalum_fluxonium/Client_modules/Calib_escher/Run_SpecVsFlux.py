#### import packages
import os
path = os.getcwd()
os.add_dll_directory(os.path.dirname(path)+'\\PythonDrivers')
from WorkingProjects.Tantalum_fluxonium.Client_modules.Calib_escher.initialize import *
from matplotlib import pyplot as plt
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mSpecVsFlux import SpecVsFlux

#### define the saving path
outerFolder = "Z:\\TantalumFluxonium\\Data\\2023_10_31_BF2_cooldown_6\\WTF\\"

#################################### Running the actual experiments

# Only run this if no proxy already exists
soc, soccfg = makeProxy()
plt.ion()

# UpdateConfig = {
#     ##### define attenuators
#     ##### define the yoko voltage
#     "yokoVoltageStart": -0.21, #-0.65,
#     "yokoVoltageStop": -0.24, #-0.63,
#     "yokoVoltageNumPoints": 40,
#     ###### cavity
#     "trans_reps": 500,  # this will used for all experiements below unless otherwise changed in between trials
#     "read_pulse_style": "const",  # --Fixed
#     "read_length": 20,  # us
#     "read_pulse_gain": 5000,  # [DAC units]
#     "trans_freq_start": 7392.3 - 1.5,  # [MHz] actual frequency is this number + "cavity_LO"
#     "trans_freq_stop": 7392.3 + 1.5,  # [MHz] actual frequency is this number + "cavity_LO"
#     "TransNumPoints": 201,  ### number of points in the transmission frequecny
#     ##### qubit spec parameters
#     "spec_reps": 14000, #2500
#     "qubit_pulse_style": "const",
#     "qubit_gain": 20000,
#     "qubit_length": 5, ### in units of us
#     "qubit_freq_start": 400,
#     "qubit_freq_stop": 600,
#     "SpecNumPoints": 81,  ### number of points
#     "sigma": 1,
#     "relax_delay": 20,
# }
config = BaseConfig | UpdateConfig

#######################################################################################################################
########################################################################################################################

##### run actual experiment
Instance_SpecVsFlux = SpecVsFlux(path="dataTestSpecVsFlux", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
data_SpecVsFlux = SpecVsFlux.acquire(Instance_SpecVsFlux)
SpecVsFlux.save_data(Instance_SpecVsFlux, data_SpecVsFlux)
SpecVsFlux.save_config(Instance_SpecVsFlux)

#
plt.show(block = True)