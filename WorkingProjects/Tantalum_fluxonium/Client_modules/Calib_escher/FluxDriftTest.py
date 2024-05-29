#%%
#### import packages
import os
import time
import datetime
from matplotlib import pyplot as plt

import numpy as np
path = r'C:\Users\escher\Documents\GitHub\HouckLab_QICK\WorkingProjects\Tantalum_fluxonium\Client_modules\PythonDrivers'
os.add_dll_directory(path)
from WorkingProjects.Tantalum_fluxonium.Client_modules.Calib_escher.initialize import *
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mFluxDriftTest import FluxDriftTest
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mSpecSlice_bkg_subtracted import SpecSlice_bkg_sub

# Define the saving path
outerFolder = "Z:\\TantalumFluxonium\\Data\\2024_03_25_BF2_cooldown_7\\WTF\\"

# Only run this if no proxy already exists
soc, soccfg = makeProxy()

# Defining the standard config files
SwitchConfig = {
    "trig_buffer_start": 0.035, # in us
    "trig_buffer_end": 0.024, # in us
    "trig_delay": 0.07, # in us
}

BaseConfig = BaseConfig | SwitchConfig

# Defining common experiment configurations
UpdateConfig = {
    # set yoko
    "yokoVoltage": 3.6,  # [in V]
    "yokoVoltage_freqPoint": 3.6,  # [in V] used for naming the file systems

    # cavity
    "reps": 2000,  # placeholder for reps. Cannot be undefined
    "read_pulse_style": "const",
    "read_length": 20,  # [in us]
    "read_pulse_gain": 10000,  # [in DAC units]
    "read_pulse_freq": 7392.3,  # [in MHz]

    # qubit drive parameters
    "qubit_pulse_style": "flat_top",
    "qubit_gain": 12000,
    "sigma": 0.05,  ### units us, define a 20ns sigma
    "flat_top_length": 20,  ### in us

    # experiment parameters
    'use_switch': True,
    'fridge_temp': 10,
}

config = BaseConfig | UpdateConfig

# For the flux drift experiment
UpdateConfig = {
    # Define trans slic experiment parameters
    "trans_freq_start" : config["read_pulse_freq"] - 2.,
    "trans_freq_stop" : config["read_pulse_freq"] + 2.,
    "TransNumPoints" : 101,
    "trans_reps": 500,

    # define spec slice experiment parameters
    "qubit_freq_start": 800,
    "qubit_freq_stop": 900,
    "SpecNumPoints": 101,
    'spec_reps': 1000,
    'relax_delay': 10,

    # Define the parameters for the drift scan
    "wait_num": 600,
    "wait_step": 0.1, # In minutes
}
config_fdrift = config | UpdateConfig

#%%
yoko2.SetVoltage(config_fdrift["yokoVoltage"])
# plt.close("all")
# Instance_specSlice = SpecSlice_bkg_sub(path="dataTestSpecSlice", cfg=config_fdrift,soc=soc,soccfg=soccfg, outerFolder = outerFolder, progress = True)
# data_specSlice= Instance_specSlice.acquire()
# Instance_specSlice.display(data_specSlice, plotDisp=True)
# Instance_specSlice.save_config()
# Instance_specSlice.save_data(data_specSlice)
#%%
flux_drift_test = FluxDriftTest(path="dataTestFluxDrift", cfg=config_fdrift, soc=soc, soccfg=soccfg, outerFolder=outerFolder, progress=True)
data_flux_drift = flux_drift_test.acquire()
flux_drift_test.display(data_flux_drift, plotDisp=True)
flux_drift_test.save_config()
flux_drift_test.save_data(data_flux_drift)
#%%