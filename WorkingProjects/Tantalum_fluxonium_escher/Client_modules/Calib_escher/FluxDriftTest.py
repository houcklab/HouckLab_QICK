#%%
#### import packages
import os
import time
import datetime
from matplotlib import pyplot as plt

import numpy as np
#path = r'/WorkingProjects/Tantalum_fluxonium_escher\Client_modules\PythonDrivers'
#os.add_dll_directory(path)
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Calib_escher.initialize import *
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mFluxDriftTest import FluxDriftTest
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mSpecSlice_bkg_subtracted import SpecSlice_bkg_sub

# Define the saving path, MUST END ON \\
outerFolder = r"Z:\TantalumFluxonium\Data\2024_10_14_cooldown\HouckCage_dev\\"

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
    "yokoVoltage": 0.14,  # [in V]
    "yokoVoltage_freqPoint": 0.14,  # [in V] used for naming the file systems

    # cavity
    "reps": 500,  # placeholder for reps. Cannot be undefined
    "read_pulse_style": "const",
    "read_length": 30,  # [in us]
    "read_pulse_gain": 1000,  # [in DAC units]
    "read_pulse_freq": 6664.634,  # [in MHz]

    # qubit drive parameters
    "qubit_pulse_style": "flat_top",
    "qubit_gain": 0,
    "sigma": 0.05,  ### units us, define a 20ns sigma
    "flat_top_length": 20,  ### in us

    # experiment parameters
    'use_switch': True,
    'fridge_temp': 10,
}

config = BaseConfig | UpdateConfig

# For the flux drift experiment
UpdateConfig = {
    # THIS CODE IS SUPER BROKEN AND USES SPEC PARAMETERS FOR TRANSMISSION
    # Define trans slic experiment parameters
    "trans_freq_start" : config["read_pulse_freq"] - 1,
    "trans_freq_stop" : config["read_pulse_freq"] + 1,
    "TransNumPoints" : 201,
    "trans_reps": 1000,

    # define spec slice experiment parameters
    "qubit_freq_start": 6664,
    "qubit_freq_stop": 6665.5,
    "SpecNumPoints": 201,
    'spec_reps': 1000,
    'relax_delay': 10,

    # Define the parameters for the drift scan
    "wait_num": 3,
    "wait_step": 0.1, # In minutes
}
config_fdrift = config | UpdateConfig
print(config_fdrift['read_pulse_freq'])
#%%
yoko1.SetVoltage(config_fdrift["yokoVoltage"])
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