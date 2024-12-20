#%%
import os
#path = r'/WorkingProjects/Tantalum_fluxonium_escher/Client_modules/PythonDrivers'
path = r'C:\Users\escher\Documents\GitHub\HouckLab_QICK\WorkingProjects\Tantalum_fluxonium_escher\Client_modules\PythonDrivers'
os.add_dll_directory(path)
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Calib_escher.initialize import *
from matplotlib import pyplot as plt
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mSpecVsFlux import SpecVsFlux
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.PythonDrivers.mlbf_driver import *
# define the saving path
outerFolder = r"Z:\TantalumFluxonium\Data\2024_10_14_cooldown\HouckCage_dev\\"



# Only run this if no proxy already exists
soc, soccfg = makeProxy()
# plt.ion()
plt.ioff()
SwitchConfig = {
    "trig_buffer_start": 0.05, #0.035, # in us
    "trig_buffer_end": 0.04, #0.024, # in us
    "trig_delay": 0.07, # in us
}

BaseConfig = BaseConfig | SwitchConfig


UpdateConfig = {
    # set yoko
    "yokoVoltageStart": 0.1275, #1.06, #-1,
    "yokoVoltageStop": 0.1285, #1,
    "yokoVoltageNumPoints": 11, #5001,

    # Readout parameters
    "trans_reps": 500,
    "read_pulse_style": "const",
    "read_length": 30,
    "read_pulse_gain": 2000,
    "trans_freq_start": 6664,
    "trans_freq_stop": 6665.5,
    "TransNumPoints": 151,

    # qubit spec parameters
    "spec_reps": 2,
    "qubit_pulse_style": "const", #"flat_top",
    "qubit_gain": 0,#10000, #2500,
    "qubit_length": .30,
    "flat_top_length": .30,
    "qubit_freq_start": 1120,
    "qubit_freq_stop": 1150,
    "SpecNumPoints": 2, #401, #301,
    "sigma": 0.5,
    "relax_delay": 10, #150,
    "use_switch": True,

    # Changing qubit channel ( not the standard way !!! )
    "qubit_ch": 1,
    "qubit_nqz": 1,

    # Do we subtract the average of each voltage slice from the spectroscopy data?
    "subtract_avg": True,
    "mode_periodic": True, # Is the const qubit tone mode periodic or not
    "ro_mode_periodic": False,
}
config = BaseConfig | UpdateConfig

mlbf_filter = MLBFDriver("192.168.1.100")
#Updating the mlbf filter
filter_freq = (config["trans_freq_start"] + config["trans_freq_stop"])/2
mlbf_filter.set_frequency(filter_freq)
 #%%
import matplotlib
matplotlib.use('Qt5Agg')
Instance_SpecVsFlux = SpecVsFlux(path="dataTestSpecVsFlux", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
data_SpecVsFlux = SpecVsFlux.acquire(Instance_SpecVsFlux, subtract_avg=config["subtract_avg"])
SpecVsFlux.save_data(Instance_SpecVsFlux, data_SpecVsFlux)
SpecVsFlux.save_config(Instance_SpecVsFlux)
plt.show()

#%%
# # TITLE: For multiple scans
# #
# # define the saving path
# outerFolder = r"Z:\TantalumFluxonium\Data\2024_07_29_cooldown\HouckCage_dev\\"
#
# mlbf_filter = MLBFDriver("192.168.1.100")
# # Dictionary for multiple qubits
#
# qubit_dicts = {
#     # "Q2_6p5": {
#     # # set yoko
#     # "yokoVoltageStart": -2,  # 1.06, #-1,
#     # "yokoVoltageStop": 2,  # 1,
#     # "yokoVoltageNumPoints": 101,  # 5001,
#     #
#     # # Readout parameters
#     # "trans_reps": 1000,
#     # "read_pulse_style": "const",
#     # "read_length": 30,
#     # "read_pulse_gain": 5000,
#     # "trans_freq_start": 6220.0,
#     # "trans_freq_stop": 6290.0,
#     # "TransNumPoints": 701,
#     #
#     # # qubit spec parameters
#     # "spec_reps": 2,  # 5000,
#     # "qubit_pulse_style": "flat_top",  # "flat_top",
#     # "qubit_gain": 0,  # 2500,
#     # "qubit_length": .01,
#     # "flat_top_length": .01,
#     # "qubit_freq_start": 1200,
#     # "qubit_freq_stop": 1500,
#     # "SpecNumPoints": 2,  # 301,
#     # "sigma": 0.5,
#     # "relax_delay": .01,  # 150,
#     # "use_switch": True,
#     #
#     # # Changing qubit channel ( not the standard way !!! )
#     # "qubit_ch": 1,
#     # "qubit_nqz": 1,
#     #
#     # # Do we subtract the average of each voltage slice from the spectroscopy data?
#     # "subtract_avg": True,
#     # },
#
#     "Q3_6p75": {
#         "yokoVoltageStart": 0.1,  # 1.06, #-1,
#         "yokoVoltageStop": 0.14,  # 1,
#         "yokoVoltageNumPoints": 81,  # 5001,
#
#         # Readout parameters
#         "trans_reps": 1000,
#         "read_pulse_style": "const",
#         "read_length": 30,
#         "read_pulse_gain": 1000,
#         "trans_freq_start": 6664.0,
#         "trans_freq_stop": 6665.5,
#         "TransNumPoints": 201,
#     }
# }
#
# # Loop over each qubit
# qubits = qubit_dicts.keys()
# for qubit in qubits:
#     print("Running transmission vs flux for ", qubit)
#     # Updating all the keys in config that are in qubit
#     config_keys = qubit_dicts[qubit].keys()
#     for config_key in config_keys:
#         config[config_key] = qubit_dicts[qubit][config_key]
#
#     # Updating the mlbf filter
#     filter_freq = (config["trans_freq_start"] + config["trans_freq_stop"])/2
#     mlbf_filter.set_frequency(filter_freq)
#
#     # Running transmission vs flux
#     Instance_SpecVsFlux = SpecVsFlux(path="dataTestSpecVsFlux", outerFolder=outerFolder, cfg=config, soc=soc,
#                                      soccfg=soccfg)
#     data_SpecVsFlux = SpecVsFlux.acquire(Instance_SpecVsFlux, subtract_avg=config["subtract_avg"])
#     SpecVsFlux.save_data(Instance_SpecVsFlux, data_SpecVsFlux)
#     SpecVsFlux.save_config(Instance_SpecVsFlux)
#
#     # Close the plot
#     plt.close('all')