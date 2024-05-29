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

SwitchConfig = {
    "trig_buffer_start": 0.035, # in us
    "trig_buffer_end": 0.024, # in us
    "trig_delay": 0.07, # in us
}

BaseConfig = BaseConfig | SwitchConfig


UpdateConfig = {
    ##### define attenuators
    ##### define the yoko voltage
    "yokoVoltageStart": -0.40, #-0.65,
    "yokoVoltageStop": 0.1, #-0.63,
    "yokoVoltageNumPoints": 51,
    ###### cavity
    "trans_reps": 500,  # this will used for all experiements below unless otherwise changed in between trials
    "read_pulse_style": "const",  # --Fixed
    "read_length": 20,  # us
    "read_pulse_gain": 5000,  # [DAC units]
    "trans_freq_start": 7392.3 - 2,  # [MHz] actual frequency is this number + "cavity_LO"
    "trans_freq_stop": 7392.3 + 2,  # [MHz] actual frequency is this number + "cavity_LO"
    "TransNumPoints": 101,  ### number of points in the transmission frequecny
    ##### qubit spec parameters
    "spec_reps": 2, #2500
    "qubit_pulse_style": "const",
    "qubit_gain": 0,
    "qubit_length": 1, ### in units of us
    "qubit_freq_start": 400,
    "qubit_freq_stop": 500,
    "SpecNumPoints": 2,  ### number of points
    "sigma": 1,
    "relax_delay": 1,
    "use_switch": True,
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