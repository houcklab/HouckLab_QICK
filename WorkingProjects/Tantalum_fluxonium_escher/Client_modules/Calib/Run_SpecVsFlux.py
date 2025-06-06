#### import packages
import os
path = os.getcwd()
os.add_dll_directory(os.path.dirname(path)+'\\PythonDrivers')
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Calib.initialize import *
from matplotlib import pyplot as plt
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mSpecVsFlux import SpecVsFlux
# from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mSpecVsFlux_SPI import SpecVsFlux_SPI

#### define the saving path
outerFolder = "Z:\\TantalumFluxonium\\Data\\2023_07_20_BF2_cooldown_3\\TF4\\"

#################################### Running the actual experiments

# Only run this if no proxy already exists
soc, soccfg = makeProxy()
plt.ioff()
#
###################################### code for running spec vs flux experiement
UpdateConfig = {
    ##### define attenuators
    ##### define the yoko voltage
    "yokoVoltageStart": 0, #-0.65,
    "yokoVoltageStop": 2.5, #-0.63,
    "yokoVoltageNumPoints": 251,
    ###### cavity
    "trans_reps": 300,  # this will used for all experiements below unless otherwise changed in between trials
    "read_pulse_style": "const",  # --Fixed
    "read_length": 30,  # us
    "read_pulse_gain": 1580,  # [DAC units]
    "trans_freq_start": 6422.4,  # [MHz]
    "trans_freq_stop": 6423.6,  # [MHz]
    "TransNumPoints": 151,  ### number of points in the transmission frequecny
    ##### qubit spec parameters
    "spec_reps": 1,
    "qubit_pulse_style": "const",
    "qubit_gain": 20,
    "qubit_length": 20, ### in units of us
    "qubit_freq_start": 100,
    "qubit_freq_stop": 800,
    "SpecNumPoints": 2,  ### number of points
    "sigma": 0.5,
    "relax_delay": 10,

    # Changing qubit channel ( not the standard way !!! )
    "qubit_ch": 2,
    "qubit_nqz": 1,
}
config = BaseConfig | UpdateConfig

#######################################################################################################################
########################################################################################################################

##### run actual experiment
Instance_SpecVsFlux = SpecVsFlux(path="dataTestSpecVsFlux", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
data_SpecVsFlux = SpecVsFlux.acquire(Instance_SpecVsFlux)
SpecVsFlux.save_data(Instance_SpecVsFlux, data_SpecVsFlux)
SpecVsFlux.save_config(Instance_SpecVsFlux)



###################################### code for running spec vs flux experiement
# ###################################### code for running spec vs flux experiement
# UpdateConfig = {
#     ##### define attenuators
#     ##### define the yoko voltage
#     "SPIVoltageStart": -0.2, #-0.65,
#     "SPIVoltageStop": 0.2 , #-0.63,
#     "SPIVoltageNumPoints": 21,
#     ###### cavity
#     "trans_reps": 200,  # this will used for all experiements below unless otherwise changed in between trials
#     "read_pulse_style": "const",  # --Fixed
#     "read_length": 10,  # us
#     "read_pulse_gain": 8000,  # [DAC units]
#     "trans_freq_start": 5988.1 - 0.5,  # [MHz] actual frequency is this number + "cavity_LO"
#     "trans_freq_stop": 5988.1 + 0.5,  # [MHz] actual frequency is this number + "cavity_LO"
#     "TransNumPoints": 201,  ### number of points in the transmission frequecny
#     ##### qubit spec parameters
#     "spec_reps": 2500,
#     "qubit_pulse_style": "const",
#     "qubit_gain": 10000,
#     "qubit_length": 1, ### in units of us
#     "qubit_freq_start": 600,
#     "qubit_freq_stop": 1800,
#     "SpecNumPoints": 601,  ### number of points
#     "sigma": None,
#     "relax_delay": 2,
# }
# config = BaseConfig | UpdateConfig
#
# #######################################################################################################################
# ########################################################################################################################
#
# ##### run actual experiment
# Instance_SpecVsFlux_SPI = SpecVsFlux_SPI(path="dataTestSpecVsFlux_SPI", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
# data_SpecVsFlux_SPI = SpecVsFlux_SPI.acquire(Instance_SpecVsFlux_SPI)
# SpecVsFlux_SPI.save_data(Instance_SpecVsFlux_SPI, data_SpecVsFlux_SPI)
# SpecVsFlux_SPI.save_config(Instance_SpecVsFlux_SPI)

#
plt.show(block = True)