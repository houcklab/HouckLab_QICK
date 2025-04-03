import numpy as np
import h5py
from tqdm import tqdm
import json
import csv
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Helpers.SingleShotAnalysis import PS_Analysis

path = r"Z:\TantalumFluxonium\Data\2023_10_31_BF2_cooldown_6\WTF\TempChecks\Yoko_-1.8\SingleShot_NoDelay_35\SingleShot_NoDelay_35_2024_02_20"
print("Path is ",path)
fname = r"SingleShot_NoDelay_35_2024_02_20_16_53_21_data"
print("Filename is ",fname)

file_loc = path+ '\\' +fname
print(file_loc)
# try to extract the qubit frequency
json_path = file_loc + '.json'

with open(json_path, "r") as json_file:
    config = json.loads(json_file.read())
    qubit_freq = config["qubit_ge_freq"]
    yoko_volt = config["yokoVoltage"]
    try :
        fridge_tempr = config["fridge_temp"]
    except:
        print("No Temperature")
        exit()


print("qubit frequency " + str(qubit_freq))

# Loading the data
data_exp = h5py.File(file_loc + ".h5", 'r')
print(data_exp.keys())
# Creating the class object for analyzing post-selected data
cen_num = 3

### try to perform the fit and if it fails continue
SSData = PS_Analysis(
    data=data_exp,
    cen_num=cen_num,
    cluster_method='gmm',
    init_method='all',
    data_name=fname,
    outerFolder=path,
    gauss_fit=True,
)

# Calculate the populations and temperatures
estimates_full = SSData.GaussFitMeasurement(
    wait_num=0,
    confidence_selection=0.0,
    bin_size=51,
    plot_title='Final_Meas_Fit',
    save_estimates_name='Value_Estimates',
    save_pop_results=True,
    qubit_freq=qubit_freq
)

