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
    "yokoVoltageStart": 1.2,#-.08,
    "yokoVoltageStop": 1.4,
    "yokoVoltageNumPoints": 51,#201,#151,

    # Readout parameters
    "trans_reps": 200,
    "read_pulse_style": "const",
    "read_length": 80,
    "read_pulse_gain": 2500,
    "trans_freq_start": 6230,
    "trans_freq_stop": 6240,
    "TransNumPoints": 101,

    # qubit spec parameters
    "spec_reps": 1,
    "qubit_pulse_style": "const", #"flat_top",
    "qubit_gain": 0,
    "qubit_length": 20,
    "flat_top_length": 20,
    "qubit_freq_start": 600,
    "qubit_freq_stop": 900,
    "SpecNumPoints": 2,#91,
    "sigma": 0.5,
    "relax_delay": 10,#10,
    "use_switch": False,
}
config = BaseConfig | UpdateConfig

#%%

Instance_SpecVsFlux = SpecVsFlux(path="dataTestSpecVsFlux", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
data_SpecVsFlux = SpecVsFlux.acquire(Instance_SpecVsFlux)
SpecVsFlux.save_data(Instance_SpecVsFlux, data_SpecVsFlux)
SpecVsFlux.save_config(Instance_SpecVsFlux)
plt.show()

