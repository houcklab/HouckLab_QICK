#%%
import os
path = r'/WorkingProjects/Tantalum_fluxonium_escher\Client_modules\PythonDrivers'
os.add_dll_directory(path)
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Calib_escher.initialize import *
from matplotlib import pyplot as plt
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mSpecVsFlux_Parth import SpecVsFlux

# define the saving path
outerFolder = "Z:\\TantalumFluxonium\\Data\\2024_03_25_BF2_cooldown_7\\WTF\\"

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
    # set yoko
    "yokoVoltageStart": 3.0,
    "yokoVoltageStop": 3.2,
    "yokoVoltageNumPoints": 11,

    # Readout parameters
    "trans_reps": 300,
    "read_pulse_style": "const",
    "read_length": 20,
    "read_pulse_gain": 10000,
    "trans_freq_start": 7392.0 - 2,
    "trans_freq_stop": 7392.0 + 2,
    "TransNumPoints": 31,

    # qubit spec parameters
    "spec_reps": 500,
    "qubit_pulse_style": "flat_top",
    "qubit_gain": 15000,
    "flat_top_length": 20,
    "qubit_freq_start": 800,
    "qubit_freq_stop": 850,
    "SpecNumPoints": 25,
    "sigma": 0.5,
    "relax_delay": 1000,
    "use_switch": True,
}
config = BaseConfig | UpdateConfig

#%%

Instance_SpecVsFlux = SpecVsFlux(path="dataTestSpecVsFlux", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
data_SpecVsFlux = SpecVsFlux.acquire(Instance_SpecVsFlux)
SpecVsFlux.save_data(Instance_SpecVsFlux, data_SpecVsFlux)
SpecVsFlux.save_config(Instance_SpecVsFlux)
plt.show(block = True)
