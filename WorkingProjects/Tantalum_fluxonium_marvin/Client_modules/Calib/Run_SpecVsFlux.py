#%%
import os
# path = os.getcwd() # Old method, does not work with cells
path = r'C:\Users\pjatakia\Documents\GitHub\HouckLab_QICK\WorkingProjects\Tantalum_fluxonium_marvin\Client_modules\PythonDrivers'
os.add_dll_directory(os.path.dirname(path) + '\\PythonDrivers')
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Calib.initialize import *
from matplotlib import pyplot as plt
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mSpecVsFlux import SpecVsFlux


# define the saving path
outerFolder = "Z:\\TantalumFluxonium\\Data\\2024_07_26_cooldown\\QCage_dev\\"

# Only run this if no proxy already exists
soc, soccfg = makeProxy()
plt.ioff()

# Defining changes to the config
UpdateConfig = {
    # define the yoko voltage
    "yokoVoltageStart": -0.5,
    "yokoVoltageStop": 0.5,
    "yokoVoltageNumPoints": 401,

    # cavity and readout
    "trans_reps": 500,
    "read_pulse_style": "const",
    "read_length": 20,  # us
    "read_pulse_gain": 1000,  # [DAC units]
    "trans_freq_start": 6671.6,  # [MHz]
    "trans_freq_stop": 6672.2,  # [MHz]
    "TransNumPoints": 101,

    # qubit spec parameters
    "spec_reps": 1,
    "qubit_pulse_style": "const",
    "qubit_gain": 0,
    "qubit_length": 10,
    "qubit_freq_start": 300,
    "qubit_freq_stop": 1000,
    "SpecNumPoints": 2,
    "sigma": 0.05,
    "relax_delay": 3,
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
