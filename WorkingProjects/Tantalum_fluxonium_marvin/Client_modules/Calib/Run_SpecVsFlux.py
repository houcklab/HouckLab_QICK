#%%
import os
# path = os.getcwd() # Old method, does not work with cells
path = r'C:\Users\pjatakia\Documents\GitHub\HouckLab_QICK\WorkingProjects\Tantalum_fluxonium_marvin\Client_modules\PythonDrivers'
os.add_dll_directory(os.path.dirname(path) + '\\PythonDrivers')
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Calib.initialize import *
from matplotlib import pyplot as plt
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mSpecVsFlux import SpecVsFlux


# define the saving path
outerFolder = "Z:\\TantalumFluxonium\\Data\\2024_07_29_cooldown\\QCage_dev\\"

# Only run this if no proxy already exists
soc, soccfg = makeProxy()
plt.ioff()

# Defining changes to the config
UpdateConfig = {
    # define the yoko voltage
    "yokoVoltageStart": -2.05,
    "yokoVoltageStop": -1.95,
    "yokoVoltageNumPoints": 101,

    # cavity and readout
    "trans_reps": 1000,
    "read_pulse_style": "const",
    "read_length": 50,  # us
    "read_pulse_gain": 1500,  # [DAC units]
    "trans_freq_start": 6671.5-1.5,  # [MHz]
    "trans_freq_stop": 6671.5 + 1.5,  # [MHz]
    "TransNumPoints": 101,

    # qubit spec parameters
    "spec_reps": 2,
    "qubit_pulse_style": "arb",
    "qubit_gain": 1,
    "qubit_length": 0.01,
    "flat_top_length" : 10,
    "qubit_freq_start": 200,
    "qubit_freq_stop": 400,
    "SpecNumPoints": 3,
    "sigma": 0.1,
    "relax_delay": 10,
    'use_switch': False,
    'initialize_pulse': False,
    'fridge_temp': 420,
}
config = BaseConfig | UpdateConfig

#%%
# Run the experiment

Instance_SpecVsFlux = SpecVsFlux(path="dataTestSpecVsFlux", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
data_SpecVsFlux = SpecVsFlux.acquire(Instance_SpecVsFlux)
SpecVsFlux.save_data(Instance_SpecVsFlux, data_SpecVsFlux)
SpecVsFlux.save_config(Instance_SpecVsFlux)
plt.show()
