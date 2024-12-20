import numpy as np
import sys
# path = "/Users/photon/My_Data/Research/Houcklab_QICK/"
# sys.path.append(path)
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mSingleShotOptimize import SingleShotMeasure
import h5py
import json
import os
# %%
# TITLE : Load the data and config file

path = "/Volumes/ourphoton/TantalumFluxonium/Data/2024_07_29_cooldown/HouckCage_dev/dataTestSingleShotProgram/dataTestSingleShotProgram_2024_10_25/"
outerFolder = os.path.dirname(path.rstrip(os.sep)) + os.sep
print("Path is ", path)
fname = "dataTestSingleShotProgram_2024_10_25_18_13_19_data"
print("Filename is ", fname)

file_loc = path +fname
print(file_loc)
# try to extract the qubit frequency
json_path = file_loc + '.json'

with open(json_path, "r") as json_file:
    config = json.loads(json_file.read())

config["cen_num"] = 2
config["initialize_pulse"] = False

# Loading the data
data_exp = {}
data_exp['data'] = {}
data_path = file_loc + '2.h5'
print(data_path)
with h5py.File(data_path, "r") as f:
    keys = f.keys()
    for key in keys:
        data_exp['data'][key] = f[key][()]

data_exp['data']['i_arr'] = np.hstack([data_exp['data']['i_e'], data_exp['data']['i_g']])
data_exp['data']['q_arr'] = np.hstack([data_exp['data']['q_e'], data_exp['data']['q_g']])
config['qubit_ge_freq'] = 500
#%%
# Load the experiment
meas_temp_exp = SingleShotMeasure(path="dataTestSingleShotOpt", outerFolder=outerFolder, cfg=config,
                                       soc=None, soccfg=None, fast_analysis = False,  max_iter = 1000, num_trials = 1000, pop_perc = 11)
meas_temp_exp.data = data_exp
meas_temp_exp.process_data(data = data_exp)
#%%
