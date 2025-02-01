import numpy as np
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mSingleShotTemp_FullAnalysis import \
    SingleShotFull
import h5py
import json
import os
# %%
# TITLE : Load the data and config file

path = ("Z:\\TantalumFluxonium\\Data\\2024_07_29_cooldown\\QCage_dev\\Magnet_Heat_Check_6\\TempMeas_yoko_-1.9563696083657751\\TempMeas_yoko_-1.9563696083657751_2024_10_01\\")
outerFolder = os.path.dirname(path.rstrip(os.sep)) + os.sep
print("Path is ", path)
fname = r"TempMeas_yoko_-1.9563696083657751_2024_10_01_06_41_33_data"
print("Filename is ", fname)

file_loc = path +fname
print(file_loc)
# try to extract the qubit frequency
json_path = file_loc + '.json'

with open(json_path, "r") as json_file:
    config = json.loads(json_file.read())

# Loading the data
data_exp = {}
data_exp['data'] = {}
data_path = file_loc + '.h5'
with h5py.File(data_path, "r") as f:
    keys = f.keys()
    for key in keys:
        data_exp['data'][key] = f[key][()]
#%%
# Load the experiment
meas_temp_exp = SingleShotFull(path="TempMeas_yoko_" + str(config["yokoVoltage_freqPoint"]),outerFolder=outerFolder, cfg=config, soc=None, soccfg=None)
meas_temp_exp.data = data_exp
meas_temp_exp.process_data(data = data_exp)
#%%
