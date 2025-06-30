#%%
import os
#path = r'/WorkingProjects/Tantalum_fluxonium_escher/Client_modules/PythonDrivers'
path = r'C:\Users\escher\Documents\GitHub\HouckLab_QICK\WorkingProjects\Tantalum_fluxonium_escher\Client_modules\PythonDrivers'
os.add_dll_directory(path)
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Calib_escher.initialize import *
from matplotlib import pyplot as plt
#from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mSpecSlice_SaraTest import SpecSlice
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mSpecOnRepeat import SpecOnRepeat
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
    "yokoVoltage": 0.245, #1.06, #-1,
    "NumPoints": 41, #5001,

    # Readout parameters
    "trans_reps": 2000,
    "read_pulse_style": "const",
    "read_length": 30,
    "read_pulse_gain": 2000,
    "trans_freq_start": 6422.5,
    "trans_freq_stop": 6423.5,
    "TransNumPoints": 151,

    # qubit spec parameters
    "spec_reps": 4000,
    "qubit_pulse_style": "const", #"flat_top",
    "qubit_gain": 15000,#10000, #2500,
    "qubit_length": 30,
    "flat_top_length": 10,
    "qubit_freq_start": 995,
    "qubit_freq_stop": 1015,
    "SpecNumPoints": 81, #401, #301,
    "sigma": 0.5,
    "relax_delay": 10, #150,
    "use_switch": True,

    # Changing qubit channel ( not the standard way !!! )
    "qubit_ch": 1,
    "qubit_nqz": 1,

    # Do we subtract the average of each voltage slice from the spectroscopy data?
    "subtract_avg": True,
    "mode_periodic": False, # Is the const qubit tone mode periodic or not
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
Instance_SpecOnRepeat= SpecOnRepeat(path="dataTestSpecOnRepeat", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
data_SpecOnRepeat = SpecOnRepeat.acquire(Instance_SpecOnRepeat, subtract_avg=config["subtract_avg"])
SpecOnRepeat.save_data(Instance_SpecOnRepeat, data_SpecOnRepeat)
SpecOnRepeat.save_config(Instance_SpecOnRepeat)
plt.show()

#%%
# TITLE: For multiple scans
#
# define the saving path
outerFolder = r"Z:\TantalumFluxonium\Data\2024_10_14_cooldown\HouckCage_dev\\"

mlbf_filter = MLBFDriver("192.168.1.100")
# Dictionary for multiple qubits

qubit_dicts = {
    "Q3_6p75_p1": {
    # set yoko
    "yokoVoltage": 0.005, #1.06, #-1,
    "NumPoints": 21, #5001,

    # Readout parameters
    "trans_reps": 500,
    "read_pulse_style": "const",
    "read_length": 35,
    "read_pulse_gain": 1200,
    "trans_freq_start": 6664.4,
    "trans_freq_stop": 6665.1,
    "TransNumPoints": 151,

    # qubit spec parameters
    "spec_reps": 2000,
    "qubit_pulse_style": "const", #"flat_top",
    "qubit_gain": 0,#10000, #2500,
    "qubit_length": 5,
    "flat_top_length": 10,
    "qubit_freq_start": 690,
    "qubit_freq_stop": 730,
    "SpecNumPoints": 201, #401, #301,
    "sigma": 0.5,
    "relax_delay": 10, #150,
    "use_switch": False,

    # Changing qubit channel ( not the standard way !!! )
    "qubit_ch": 1,
    "qubit_nqz": 1,

    # Do we subtract the average of each voltage slice from the spectroscopy data?
    "subtract_avg": True,
    "qubit_mode_periodic": True, # Is the const qubit tone mode periodic or not
    "ro_mode_periodic": False,
    },

    "Q3_6p75_p2": {
        # set yoko
        "yokoVoltage": 0.005,  # 1.06, #-1,
        "NumPoints": 21,  # 5001,

        # Readout parameters
        "trans_reps": 500,
        "read_pulse_style": "const",
        "read_length": 35,
        "read_pulse_gain": 1200,
        "trans_freq_start": 6664.4,
        "trans_freq_stop": 6665.1,
        "TransNumPoints": 151,

        # qubit spec parameters
        "spec_reps": 2000,
        "qubit_pulse_style": "const",  # "flat_top",
        "qubit_gain": 3000,  # 10000, #2500,
        "qubit_length": 5,
        "flat_top_length": 10,
        "qubit_freq_start": 690,
        "qubit_freq_stop": 730,
        "SpecNumPoints": 201,  # 401, #301,
        "sigma": 0.5,
        "relax_delay": 10,  # 150,
        "use_switch": False,

        # Changing qubit channel ( not the standard way !!! )
        "qubit_ch": 1,
        "qubit_nqz": 1,

        # Do we subtract the average of each voltage slice from the spectroscopy data?
        "subtract_avg": True,
        "qubit_mode_periodic": True,  # Is the const qubit tone mode periodic or not
        "ro_mode_periodic": True,
    },


}

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
#     Instance_SpecOnRepeat = SpecOnRepeat(path="dataTestSpecOnRepeat", outerFolder=outerFolder, cfg=config, soc=soc,
#                                      soccfg=soccfg)
#     data_SpecOnRepeat = SpecOnRepeat.acquire(Instance_SpecOnRepeat, subtract_avg=config["subtract_avg"])
#     SpecOnRepeat.save_data(Instance_SpecOnRepeat, data_SpecOnRepeat)
#     SpecOnRepeat.save_config(Instance_SpecOnRepeat)
#
#     # Close the plot
#     plt.close('all')