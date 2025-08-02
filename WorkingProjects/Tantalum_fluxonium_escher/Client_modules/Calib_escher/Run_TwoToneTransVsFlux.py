#%%
import os
#path = r'/WorkingProjects/Tantalum_fluxonium_escher/Client_modules/PythonDrivers'
path = r'C:\Users\escher\Documents\GitHub\HouckLab_QICK\WorkingProjects\Tantalum_fluxonium_escher\Client_modules\PythonDrivers'
os.add_dll_directory(path)
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Calib_escher.initialize import *
from matplotlib import pyplot as plt
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mTwoToneTransVsFlux import TwoToneTransVsFlux
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
    "yokoVoltageStart": 0.09, #1.06, #-1,
    "yokoVoltageStop": 0.13, #1,
    "yokoVoltageNumPoints": 21, #5001,

    # Readout parameters
    "trans_reps": 8000,
    "read_pulse_style": "const",
    "read_length": 30,
    "pop_pulse_gain": 0,
    "pop_pulse_length": 15,
    "intermediate_delay": 15,
    "read_pulse_gain": 500,
    "trans_freq_start": 6664,
    "trans_freq_stop": 6665.5,
    "TransNumPoints": 201,

    # qubit spec parameters
    "spec_reps": 2,#1000,
    "qubit_pulse_style": "const", #"flat_top",
    "qubit_gain": 0,#10000, #2500,
    "qubit_length": .010,
    "flat_top_length": .010,
    "qubit_freq_start": 1125,
    "qubit_freq_stop": 1200,
    "SpecNumPoints": 2,#101, #401, #301,
    "sigma": 0.5,
    "relax_delay": 15, #150,
    "use_switch": False,

    # Changing qubit channel ( not the standard way !!! )
    "qubit_ch": 1,
    "qubit_nqz": 1,

    # Do we subtract the average of each voltage slice from the spectroscopy data?
    "subtract_avg": True,
    "ro_mode_periodic": False,
    "qubit_mode_periodic": False,
}
config = BaseConfig | UpdateConfig
#
mlbf_filter = MLBFDriver("192.168.1.100")
#Updating the mlbf filter
filter_freq = (config["trans_freq_start"] + config["trans_freq_stop"])/2
mlbf_filter.set_frequency(filter_freq)
 #%%
import matplotlib
matplotlib.use('Qt5Agg')
Instance_TwoToneTransVsFlux = TwoToneTransVsFlux(path="TwoToneTransVsFlux", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
data_TwoToneTransVsFlux = TwoToneTransVsFlux.acquire(Instance_TwoToneTransVsFlux, subtract_avg=config["subtract_avg"])
TwoToneTransVsFlux.save_data(Instance_TwoToneTransVsFlux, data_TwoToneTransVsFlux)
TwoToneTransVsFlux.save_config(Instance_TwoToneTransVsFlux)
plt.show()
