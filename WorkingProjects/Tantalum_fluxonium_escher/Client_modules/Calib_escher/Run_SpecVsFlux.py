#%%
import os
#path = r'/WorkingProjects/Tantalum_fluxonium_escher/Client_modules/PythonDrivers'
path = r'C:\Users\escher\Documents\GitHub\HouckLab_QICK\WorkingProjects\Tantalum_fluxonium_escher\Client_modules\PythonDrivers'
os.add_dll_directory(path)
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Calib_escher.initialize import *
from matplotlib import pyplot as plt
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mSpecVsFlux import SpecVsFlux

# define the saving path
outerFolder = r"Z:\TantalumFluxonium\Data\2024_07_29_cooldown\HouckCage_dev\\"


# Only run this if no proxy already exists
soc, soccfg = makeProxy()
# plt.ion()
plt.ioff()
SwitchConfig = {
    "trig_buffer_start": 0.035, # in us
    "trig_buffer_end": 0.024, # in us
    "trig_delay": 0.07, # in us
}

BaseConfig = BaseConfig | SwitchConfig


UpdateConfig = {
    # set yoko
    "yokoVoltageStart": 0.,
    "yokoVoltageStop": 2,
    "yokoVoltageNumPoints": 201,

    # Readout parameters
    "trans_reps": 300,
    "read_pulse_style": "const",
    "read_length": 30,
    "read_pulse_gain": 1580,
    "trans_freq_start": 6422.4,
    "trans_freq_stop": 6423.6,
    "TransNumPoints": 151,

    # qubit spec parameters
    "spec_reps": 1,
    "qubit_pulse_style": "const", #"flat_top",
    "qubit_gain": 0,
    "qubit_length": 20,
    "flat_top_length": 20,
    "qubit_freq_start": 100,
    "qubit_freq_stop": 800,
    "SpecNumPoints": 2,
    "sigma": 0.5,
    "relax_delay": 10,
    "use_switch": True,

    # Changing qubit channel ( not the standard way !!! )
    "qubit_ch": 2,
    "qubit_nqz": 1,
}
config = BaseConfig | UpdateConfig

#%%
import matplotlib
matplotlib.use('Qt5Agg')
Instance_SpecVsFlux = SpecVsFlux(path="dataTestSpecVsFlux", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
data_SpecVsFlux = SpecVsFlux.acquire(Instance_SpecVsFlux)
SpecVsFlux.save_data(Instance_SpecVsFlux, data_SpecVsFlux)
SpecVsFlux.save_config(Instance_SpecVsFlux)
plt.show()


