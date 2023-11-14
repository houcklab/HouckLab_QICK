#### import packages
import os
path = os.getcwd()
os.add_dll_directory(os.path.dirname(path)+'\\PythonDrivers')
from WorkingProjects.Tantalum_fluxonium.Client_modules.Calib_escher.initialize import *
from matplotlib import pyplot as plt
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mSpecVsFlux import SpecVsFlux

#### define the saving path
outerFolder = "Z:\\TantalumFluxonium\\Data\\2023_06_02_BF2_cooldown\\TF1SC1\\"

#################################### Running the actual experiments

# Only run this if no proxy already exists
soc, soccfg = makeProxy()
plt.ioff()

UpdateConfig = {
    ##### define attenuators
    ##### define the yoko voltage
    "yokoVoltageStart": -0.585, #-0.65,
    "yokoVoltageStop": -0.58, #-0.63,
    "yokoVoltageNumPoints": 2,
    ###### cavity
    "trans_reps": 500,  # this will used for all experiements below unless otherwise changed in between trials
    "read_pulse_style": "const",  # --Fixed
    "read_length": 20,  # us
    "read_pulse_gain": 5000,  # [DAC units]
    "trans_freq_start": 7392.8 - 1.5,  # [MHz] actual frequency is this number + "cavity_LO"
    "trans_freq_stop": 7392.8 + 1.5,  # [MHz] actual frequency is this number + "cavity_LO"
    "TransNumPoints": 201,  ### number of points in the transmission frequecny
    ##### qubit spec parameters
    "spec_reps": 1000, #2500
    "qubit_pulse_style": "const",
    "qubit_gain": 10000,
    "qubit_length": 1, ### in units of us
    "qubit_freq_start": 5432 - 50,
    "qubit_freq_stop": 5432 + 50,
    "SpecNumPoints": 101,  ### number of points
    "sigma": 1,
    "relax_delay": 5,
}
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