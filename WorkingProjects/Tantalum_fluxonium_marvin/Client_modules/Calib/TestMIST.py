# %%

import os
from matplotlib import pyplot as plt
import datetime
import numpy as np
from tqdm import tqdm

# path = os.getcwd()
path = r'C:\Users\pjatakia\Documents\GitHub\HouckLab_QICK\WorkingProjects\Tantalum_fluxonium_marvin\Client_modules\PythonDrivers'
os.add_dll_directory(os.path.dirname(path) + '\\PythonDrivers')
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Calib.initialize import *
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mStarkShift_PS import StarkShiftPS

# Define the saving path
outerFolder = "Z:\\TantalumFluxonium\\Data\\2025_07_25_cooldown\\QCage_dev\\"

SwitchConfig = {
    "trig_buffer_start": 0.035,  # in us
    "trig_buffer_end": 0.024,  # in us
    "trig_delay": 0.07,  # in us
}
BaseConfig = BaseConfig | SwitchConfig

# Only run this if no proxy already exists
soc, soccfg = makeProxy()

#%% TITLE : Doing Stark Shift with Post Selection : Helpful at half flux
# Lot of fixed values have been parameterized. Open the experiment file to understand all of them
UpdateConfig = {

    # Readout Tone
    "read_pulse_style": "const",
    "read_length": 20,
    "read_pulse_gain": 5000,
    "read_pulse_freq": 6672.535,

    # Qubit Tone
    "qubit_pulse_style": "const",  # Fixed
    "qubit_gain": 1000,  # [DAC Units]
    "qubit_length": 0.2,  # [us]
    'use_switch': False,
    'qubit_freq_base' : 155.5,

    # Define qubit experiment parameters
    "qubit_freq_start": 110,
    "qubit_freq_stop": 165,
    "SpecNumPoints": 101,  # Number of points
    'spec_reps': 20000,

    # Define cavity experiment parameters
    "trans_gain_start" : 0,
    "trans_gain_stop" : 8000,
    "trans_gain_num" : 11,
    'units': 'DAC',
    'pop_length': 20,

    # Define experiment
    'qubit_periodic': False,
    'ro_periodic': False,
    'post_pop_tone_delay': 0.005,
    'pre_meas_delay': 10,
    'wait_before_exp': 10,
    'align': 'right',
    'simultaneous': True,

    # Other stuff
    'initialize_pulse' : True,
    'initialize_qubit_gain' : 2000,
    "yokoVoltage": -0.1015,
    "relax_delay": 20,  # [us] Delay post one experiment
}
config = BaseConfig | UpdateConfig
yoko1.SetVoltage(config["yokoVoltage"])
#%%
soc.reset_gens()
try:
    inst_stark_shift = StarkShiftPS(path="StarkShiftPS", outerFolder=outerFolder, cfg=config, soc=soc, soccfg=soccfg,
                                     progress=True)
except Exception:
    print("Pyro traceback:")
    print("".join(Pyro4.util.getPyroTraceback()))
data_stark_shift = inst_stark_shift.acquire()
inst_stark_shift.save_data(data = data_stark_shift)
inst_stark_shift.save_config()
#%%