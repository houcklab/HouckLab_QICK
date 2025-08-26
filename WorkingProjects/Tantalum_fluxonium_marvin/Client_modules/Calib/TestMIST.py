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
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mStarkShift import StarkShift
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mStarkShift_whitenoise_PS import StarkShiftwhitenoise_PS
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mStarkShift_whitenoise import StarkShift_whitenoise

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
    "read_length": 25,
    "read_pulse_gain": 7500,
    "read_pulse_freq": 6672.5512,
    "read_pulse_freq_resonant" : 6672.367,

    # Qubit Tone
    "qubit_pulse_style": "const",  # Fixed
    "qubit_gain": 1000,  # [DAC Units]
    "qubit_length": 0.8,  # [us]
    'use_switch': False,
    'qubit_freq_base' : 155.5,

    # Define qubit experiment parameters
    "qubit_freq_start": 147.5,
    "qubit_freq_stop": 160,
    "SpecNumPoints": 51,  # Number of points
    'spec_reps': 20000,

    # Define cavity experiment parameters
    "trans_gain_start" : 100,
    "trans_gain_stop" : 6000,
    "trans_gain_num" : 11,
    'units': 'DAC',
    'pop_length': 20,

    # Define experiment
    'qubit_periodic': False,
    'ro_periodic': False,
    'post_pop_tone_delay': 0.02,
    'pre_meas_delay': 10,
    'wait_before_exp': 10,
    'align': 'right',
    'simultaneous': True,

    # Other stuff
    'initialize_pulse' : True,
    'initialize_qubit_gain' : 2000,
    "yokoVoltage": -0.104,
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
# inst_stark_shift.save_data_pkl(data = data_stark_shift)
inst_stark_shift.save_config()

#%% TITLE : Stark Shift PS with Agilent
UpdateConfig = {
    # cavity
    "read_pulse_style": "const",
    "read_length": 25,
    "read_pulse_gain": 7500,
    "read_pulse_freq": 6672.5512,  # 6253.8,

    # qubit
    "qubit_pulse_style": "const",  # Constant pulse
    "qubit_gain": 1000,  # [DAC Units]
    "qubit_length": 0.8,  # [us]

    # Define spec slice experiment parameters
    "qubit_freq_start": 120,
    "qubit_freq_stop": 165,
    "qubit_freq_base": 155,
    "SpecNumPoints": 201,  # Number of points
    'spec_reps': 70000,  # Number of repetition
    'align': 'right',
    'pop_length': 20,
    "delay_btwn_pulses" : 10, # Delay between the qubit tone and the readout tone. If not defined it uses 50ns

    # Define agilent setting
    "units" : "DAC",
    "awg_start" : 0.001, # in Vpp
    "awg_stop" : 1, # in Vpp
    "awg_num" : 21, # in Vpp

    # Define the yoko voltage
    "yokoVoltage": -0.104,
    "relax_delay": 10,  # [us] Delay post one experiment
    'use_switch': True, # This is for turning off the heating tone
    'initialize_pulse': False,
    'initialize_qubit_gain': 1000,
    'fridge_temp': 420,
}
config = BaseConfig | UpdateConfig
yoko1.SetVoltage(config["yokoVoltage"])

#%%
soc.reset_gens()
try:
    inst_stark_shift_wn = StarkShiftwhitenoise_PS(path="StarkShiftwhitenoise_PS", outerFolder=outerFolder, cfg=config, soc=soc, soccfg=soccfg,
                                     progress=True)
except Exception:
    print("Pyro traceback:")
    print("".join(Pyro4.util.getPyroTraceback()))
data_stark_shift_wn = inst_stark_shift_wn.acquire()
inst_stark_shift_wn.save_data(data = data_stark_shift_wn)
inst_stark_shift_wn.save_config()

#%%
#%%
# TITLE : Stark Shift

UpdateConfig = {

    # cavity
    "read_pulse_style": "const",
    "read_length": 6.6,
    "read_pulse_gain": 10000,
    "read_pulse_freq": 6671.6612,

    # Parameters
    "reps": 4000,  # Number of repetitions
    "TransSpan": 1,  # [MHz] span will be center frequency +/- this parameter
    "TransNumPoints": 51,  # number of points in the transmission frequency

    # Qubit
    "qubit_pulse_style": "const",  # Constant pulse
    "qubit_gain": 3500,  # [DAC Units]
    "qubit_length": 0.5,  # [us]
    "flat_top_length":5,
    'sigma': 1,

    # Define qubit experiment parameters
    "qubit_freq_start": 2180,
    "qubit_freq_stop": 2230,
    "SpecNumPoints": 301,  # Number of points
    'spec_reps': 300000,

    # Define cavity experiment parameters
    "trans_gain_start" : 2000,
    "trans_gain_stop" : 4500,
    "trans_gain_num" :  3,
    "pop_pulse_length": 10,
    'align': 'right',

    # Define experiment
    "yokoVoltage": -0.42,
    "relax_delay": 10,  # [us] Delay post one experiment
    'wait_between_pulses': 0.05,
    'use_switch': False,
    'mode_periodic': False,
    'ro_periodic': False,
    'units': 'DAC',
    "calibrate_cav": False,
    "simultaneous": True,
}
#%%
soc.reset_gens()
config = BaseConfig | UpdateConfig
yoko1.SetVoltage(config["yokoVoltage"])
try:
    inst_stark_shift = StarkShift(path="StarkShift", outerFolder=outerFolder, cfg=config, soc=soc, soccfg=soccfg,
                                     progress=True)
except Exception:
    print("Pyro traceback:")
    print("".join(Pyro4.util.getPyroTraceback()))
try:
    data_stark_shift = inst_stark_shift.acquire()
except Exception:
    print("Pyro traceback:")
    print("".join(Pyro4.util.getPyroTraceback()))

inst_stark_shift.save_data(data = data_stark_shift)
inst_stark_shift.save_config()

#%%
# TITLE : Stark Shift with Whitenoise

UpdateConfig = {

    # cavity
    "read_pulse_style": "const",
    "read_length": 6.6,
    "read_pulse_gain": 10000,
    "read_pulse_freq": 6671.6612,

    # Parameters
    "reps": 4000,  # Number of repetitions
    "TransSpan": 1,  # [MHz] span will be center frequency +/- this parameter
    "TransNumPoints": 51,  # number of points in the transmission frequency

    # Qubit
    "qubit_pulse_style": "const",  # Constant pulse
    "qubit_gain": 3500,  # [DAC Units]
    "qubit_length": 0.5,  # [us]
    "flat_top_length":5,
    'sigma': 1,

    # Define qubit experiment parameters
    "qubit_freq_start": 2180,
    "qubit_freq_stop": 2230,
    "SpecNumPoints": 301,  # Number of points
    'spec_reps': 10000,

    # Define cavity experiment parameters
    "awg_gain_start" : 0,
    "awg_gain_stop" : 1,
    "awg_gain_num" :  5,
    "pop_pulse_length": 10,
    'align': 'right',

    # Define experiment
    "yokoVoltage": -0.42,
    "relax_delay": 10,  # [us] Delay post one experiment
    'wait_between_pulses': 0.05,
    'use_switch': False,
    'mode_periodic': False,
    'ro_periodic': False,
    'units': 'DAC',
    "calibrate_cav": False,
    "simultaneous": True,
}
#%%
soc.reset_gens()
config = BaseConfig | UpdateConfig
yoko1.SetVoltage(config["yokoVoltage"])
try:
    inst_stark_shift = StarkShift_whitenoise(path="StarkShift", outerFolder=outerFolder, cfg=config, soc=soc, soccfg=soccfg,
                                     progress=True)
except Exception:
    print("Pyro traceback:")
    print("".join(Pyro4.util.getPyroTraceback()))
try:
    data_stark_shift = inst_stark_shift.acquire()
except Exception:
    print("Pyro traceback:")
    print("".join(Pyro4.util.getPyroTraceback()))

inst_stark_shift.save_data(data = data_stark_shift)
inst_stark_shift.save_config()

#%%