#### import packages
import os
path = os.getcwd()
os.add_dll_directory(os.path.dirname(path)+'\\PythonDrivers')

from WorkingProjects.Tantalum_fluxonium.Client_modules.Calib.initialize import *
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mQubit_EF_Rabi import Qubit_ef_rabi
# from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mQubit_EF_Rabi import Qubit_ef_RPM
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mQubit_ef_spectroscopy import Qubit_ef_spectroscopy

from matplotlib import pyplot as plt
import datetime

#### define the saving path
outerFolder = "Z:\\TantalumFluxonium\\Data\\2023_10_09_BF2_cooldown_5\\TF4\\"

###qubitAtten = attenuator(27797, attenuation_int= 10, print_int = False)

print('starting time: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))

#################################### Running the actual experiments

# Only run this if no proxy already exists
soc, soccfg = makeProxy()
# print(soccfg)

plt.ioff()



# # # #######################################################################################################################
############## qubit ef spectroscopy
UpdateConfig = {
    ##### define attenuators
    "yokoVoltage": -2.8,
    ###### cavity
    "read_pulse_style": "const", # --Fixed
    "read_length": 5, # us
    "read_pulse_gain": 10000, # [DAC units]
    "read_pulse_freq": 6437.2,
    # g-e parameters
    "qubit_ge_freq": 2033.0, # MHz
    "qubit_ge_gain": 16000, # Gain for pi pulse in DAC units
    ##### spec parameters for finding the qubit frequency
    "qubit_ef_freq_start": 1550 - 25, #1167-10
    "qubit_ef_freq_step": 1,
    "SpecNumPoints": 51,  ### number of points
    "qubit_pulse_style": "arb",
    # "qubit_length": 1, # us, changes experiment time but is necessary for "const" style
    "sigma": 0.150,  ### units us, define a 20ns sigma
    # "qubit_length": 1, ### units us, doesn't really get used though
    # "flat_top_length": 0.025, ### in us
    "relax_delay": 1500,  ### turned into us inside the run function
    "qubit_gain": 20000, # Constant gain to use
    # "qubit_gain_start": 18500, # shouldn't need this...
    "reps": 2000, # number of averages of every experiment
}
config = BaseConfig | UpdateConfig

yoko1.SetVoltage(config["yokoVoltage"])
# #
Instance_Qubit_ef_spectroscopy = Qubit_ef_spectroscopy(path="dataQubit_ef_spectroscopy", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg, progress=True)
data_Qubit_ef_spectroscopy = Qubit_ef_spectroscopy.acquire(Instance_Qubit_ef_spectroscopy)
Qubit_ef_spectroscopy.save_data(Instance_Qubit_ef_spectroscopy, data_Qubit_ef_spectroscopy)
Qubit_ef_spectroscopy.save_config(Instance_Qubit_ef_spectroscopy)
Qubit_ef_spectroscopy.display(Instance_Qubit_ef_spectroscopy, data_Qubit_ef_spectroscopy, plotDisp=True)


# #######################################################################################################################
# ###### qubit ef rabi measurement
# UpdateConfig = {
#     ##### define attenuators
#     "yokoVoltage": -2.8,
#     ###### cavity
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 5, # us
#     "read_pulse_gain": 10000, # [DAC units]
#     "read_pulse_freq": 6437.2,
#     ###### qubit
#     # g-e parameters
#     "qubit_ge_freq": 2033.0, # MHz
#     "qubit_ge_gain": 16000, # Gain for pi pulse in DAC units
#     "apply_ge": True,
#    # e-f parameters
#     "qubit_ef_freq": 1545,
#     "qubit_ef_gain_start": 0, #1167-10
#     "qubit_ef_gain_step": 1000,
#     "RabiNumPoints": 31,  ### number of points
#     "qubit_pulse_style": "arb",
#     "qubit_length": 1, # us, changes experiment time but is necessary for "const" style
#     "sigma": 0.150,  ### units us
#     # "qubit_length": 1, ### units us, doesnt really get used though
#     # "flat_top_length": 0.025, ### in us
#     "relax_delay": 1500,  ### turned into us inside the run function
#     "qubit_gain": 25000, # Constant gain to use
#     # "qubit_gain_start": 18500, # shouldn't need this...
#     "reps": 2000, # number of averages of every experiment
# }
# config = BaseConfig | UpdateConfig
#
# yoko1.SetVoltage(config["yokoVoltage"])
# # #
# Instance_Qubit_ef_rabi = Qubit_ef_rabi(path="dataQubit_ef_rabi", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg, progress=True)
# data_Qubit_ef_rabi = Qubit_ef_rabi.acquire(Instance_Qubit_ef_rabi)
# Qubit_ef_rabi.save_data(Instance_Qubit_ef_rabi, data_Qubit_ef_rabi)
# Qubit_ef_rabi.save_config(Instance_Qubit_ef_rabi)
# Qubit_ef_rabi.display(Instance_Qubit_ef_rabi, data_Qubit_ef_rabi, plotDisp=True)

#
# #######################################################################################################################
# UpdateConfig = {
#     ##### define attenuators
#     "yokoVoltage": 0,
#     ###### cavity
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 10, # us
#     "read_pulse_gain": 6400, # [DAC units]
#     "read_pulse_freq": 5745.5,
#     ###### qubit
#     # g-e parameters
#     "qubit_ge_freq": 2033, # MHz
#     "qubit_ge_gain": 8000, # Gain for pi pulse in DAC units
#     "apply_ge": False,
#    # e-f parameters
#     "qubit_ef_freq": 4487.8,
#     "qubit_ef_gain_start": 0, #1167-10
#     "qubit_ef_gain_step": 1500,
#     "RabiNumPoints": 21,  ### number of points
#     "qubit_pulse_style": "arb",
#     "qubit_length": 1, # us, changes experiment time but is necessary for "const" style
#     "sigma": 0.300,  ### units us, define a 20ns sigma
#     "relax_delay": 2000,  ### turned into us inside the run function
#     "g_reps": 2000, # number of averages of every experiment
#     "e_reps": 2000, # number of averages of every experiment
#     "reps": 1
# }
# config = BaseConfig | UpdateConfig
#
# yoko1.SetVoltage(config["yokoVoltage"])
# # #
# Instance_Qubit_ef_rabi = Qubit_ef_RPM(path="dataQubit_ef_RPM", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg, progress=True)
# data_Qubit_ef_rabi = Qubit_ef_RPM.acquire(Instance_Qubit_ef_rabi)
# print(time.localtime())
# Qubit_ef_RPM.save_data(Instance_Qubit_ef_rabi, data_Qubit_ef_rabi)
# Qubit_ef_RPM.save_config(Instance_Qubit_ef_rabi)
# Qubit_ef_RPM.display(Instance_Qubit_ef_rabi, data_Qubit_ef_rabi, plotDisp=True)

#######################################################################################################################


print('end time: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))

plt.show()

