#%%
import os
# path = os.getcwd() # Old method, does not work with cells
path = r'/WorkingProjects/Tantalum_fluxonium_marvin\Client_modules\PythonDrivers'
os.add_dll_directory(os.path.dirname(path) + '\\PythonDrivers')
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Calib.initialize import *
from matplotlib import pyplot as plt
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mSpecVsFlux import SpecVsFlux


# define the saving path
outerFolder = "Z:\\TantalumFluxonium\\Data\\2023_10_31_BF2_cooldown_6\\TF4\\"

# Only run this if no proxy already exists
soc, soccfg = makeProxy()
plt.ioff()

# Defining changes to the config
UpdateConfig = {
    # define the yoko voltage
    "yokoVoltageStart": -2.0,
    "yokoVoltageStop": 10.0,
    "yokoVoltageNumPoints": 49,

    # cavity and readout
    "trans_reps": 200,
    "read_pulse_style": "const",
    "read_length": 20,  # us
    "read_pulse_gain": 7000,  # [DAC units]
    "trans_freq_start": 6437.4 - 2.0,  # [MHz]
    "trans_freq_stop": 6437.4 + 2.0,  # [MHz]
    "TransNumPoints": 151,

    # qubit spec parameters
    "spec_reps": 1,
    "qubit_pulse_style": "const",
    "qubit_gain": 1,
    "qubit_length": 0.1,
    "qubit_freq_start": 600,
    "qubit_freq_stop": 1000,
    "SpecNumPoints": 3,
    "sigma": None,
    "relax_delay": 5,
    'use_switch': True,
}
config = BaseConfig | UpdateConfig

#%%
# Run the experiment

Instance_SpecVsFlux = SpecVsFlux(path="dataTestSpecVsFlux", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
data_SpecVsFlux = SpecVsFlux.acquire(Instance_SpecVsFlux)
SpecVsFlux.save_data(Instance_SpecVsFlux, data_SpecVsFlux)
SpecVsFlux.save_config(Instance_SpecVsFlux)
plt.show()