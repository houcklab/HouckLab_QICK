#%%
import os
# path = os.getcwd() # Old method, does not work with cells
path = r'C:\Users\pjatakia\Documents\GitHub\HouckLab_QICK\WorkingProjects\Tantalum_fluxonium_marvin\Client_modules\PythonDrivers'
os.add_dll_directory(os.path.dirname(path) + '\\PythonDrivers')
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Calib.initialize import *
from matplotlib import pyplot as plt
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mSpecOnRepeat import SpecOnRepeat
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.PythonDrivers.mlbf_driver import *
# define the saving path
outerFolder = r"Z:\TantalumFluxonium\Data\2025_07_25\QCage_dev\\"


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
    "yokoVoltage": -0.1012,
    "NumPoints": 900,

    # Readout parameters
    "trans_reps": 2000,
    "read_pulse_style": "const",
    "read_length": 10,
    "read_pulse_gain": 3000,
    "trans_freq_start": 6671,
    "trans_freq_stop": 6673.5,
    "TransNumPoints": 201,

    # qubit spec parameters
    "spec_reps": 5000,
    "qubit_pulse_style": "const", #"flat_top",
    "qubit_gain": 10000,#10000, #2500,
    "qubit_length": 10,
    "flat_top_length": 10,
    "qubit_freq_start": 50,
    "qubit_freq_stop": 500,
    "SpecNumPoints": 201, #401, #301,
    "sigma": 0.5,
    "relax_delay": 10, #150,
    "use_switch": False,

    # Do we subtract the average of each voltage slice from the spectroscopy data?
    "subtract_avg": False,
    "mode_periodic": False, # Is the const qubit tone mode periodic or not
    "ro_periodic": False,
}
config = BaseConfig | UpdateConfig

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
