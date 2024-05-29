#%%
#### import packages
import os
import time
import datetime

import numpy as np
path = r'/WorkingProjects/Tantalum_fluxonium_escher\Client_modules\PythonDrivers'
os.add_dll_directory(path)
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Calib_escher.initialize import *
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mSingleShotTemp_sse import SingleShotSSE
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mSpecSlice_bkg_subtracted import SpecSlice_bkg_sub
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mT1_PS_sse import T1_PS_sse
import WorkingProjects.Tantalum_fluxonium_escher.Client_modules.PythonDrivers.LS370 as lk
import pyvisa

# Define the saving path
outerFolder = "Z:\\TantalumFluxonium\\Data\\2024_03_25_BF2_cooldown_7\\WTF\\Magnet_Heating_Check\\"

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
    "yokoVoltage": 2.384,  # [in V]
    "yokoVoltage_freqPoint": 2.384,  # [in V] used for naming the file systems

    # cavity
    "reps": 2000,  # placeholder for reps. Cannot be undefined
    "read_pulse_style": "const",
    "read_length": 20,  # [in us]
    "read_pulse_gain": 10000,  # [in DAC units]
    "read_pulse_freq": 7392.3,  # [in MHz]

    # qubit drive parameters
    "qubit_freq": 830.73,  # [in MHz]
    "qubit_pulse_style": "flat_top",
    "qubit_gain": 7000,
    "sigma": 0.05,  ### units us, define a 20ns sigma
    "flat_top_length": 20,  ### in us

    # experiment parameters
    "cen_num": 2,  # Number of states expected
    "relax_delay": 5*10000,
    'use_switch': True,
    'fridge_temp': 10,
}

config = BaseConfig | UpdateConfig

# For the spec slice experiment
UpdateConfig = {
    # define spec slice experiment parameters
    "qubit_freq_start": 800,
    "qubit_freq_stop": 900,
    "SpecNumPoints": 301,
    'spec_reps': 2000,
    'relax_delay': 1000,
}
config_spec = config | UpdateConfig

# For the single shot experiment
UpdateConfig = {
        ## define experiment parameters
        "shots": int(5e4),
        "use_switch": True,
        "initialize_pulse": True,
    }
config_ss = config | UpdateConfig

# For the T1 experiment
UpdateConfig = {
    "shots": 12000,  # Number of shots
    "wait_start": 0,  # [in us]
    "wait_stop": 12000,  # [in us]
    "wait_num": 31,  # number of points in linspace
    'wait_type': 'linear',
    "use_switch": True,
    "relax_delay": 10,
}
config_t1 = config | UpdateConfig

#%%
yoko1.SetVoltage(config_ss["yokoVoltage"])
time_required = config_ss["shots"] * config_ss["relax_delay"] * 1e-6 / 60
print("SingleShot : Total time estimate is ", time_required, " mins")
print('starting scan: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
Instance_SingleShotProgram = SingleShotSSE(path="TempMeas_yoko_" + str(config_ss["yokoVoltage_freqPoint"]),
                                           outerFolder=outerFolder, cfg=config_ss,
                                           soc=soc, soccfg=soccfg)
data_SingleShot = Instance_SingleShotProgram.acquire()
data_SingleShot = Instance_SingleShotProgram.process_data(data_SingleShot, bin_size=51)
Instance_SingleShotProgram.save_data(data_SingleShot)
Instance_SingleShotProgram.display(data_SingleShot, plotDisp=False, save_fig=True)
print('end of scan: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
#%%
#TITLE: Set up the Lakeshore
rm = pyvisa.ResourceManager()
LS370_connection = rm.open_resource('GPIB0::12::INSTR')
lakeshore = lk.Lakeshore370(LS370_connection)

# Sweep over yoko voltage symmetry points
half_flux_pt = 4.033
flux_quantum = 7.88
flux_pt = 3.6
right_pts = flux_quantum*np.array([-4,-3,-2,-1,0,1]) + flux_pt
left_pts = [] # flux_quantum*np.array([-1,0,1]) + (2*half_flux_pt - flux_pt)
yoko_list = np.sort(np.concatenate((left_pts,right_pts)))
print(yoko_list)

# Creating empty lists to store the temperatures and error
tempr_list = []
tempr_std_list = []
tempr_fridge = []
t1_list = []
t1_instance = []
#%%
for idx_yoko in range(yoko_list.size):
    config_ss["yokoVoltage"] = yoko_list[idx_yoko]
    config_ss["yokoVoltage_freqPoint"] = yoko_list[idx_yoko]
    config_spec["YokoVoltage"] = yoko_list[idx_yoko]
    config_spec["yokoVoltage_freqPoint"] = yoko_list[idx_yoko]
    config_t1["yokoVoltage"] = yoko_list[idx_yoko]
    config_t1["yokoVoltage_freqPoint"] = yoko_list[idx_yoko]

    # Set the yoko voltage
    print("Setting Yoko Voltage to ", config_ss["yokoVoltage"])
    yoko2.SetVoltage(config_ss["yokoVoltage"])
    time.sleep(300)

    # Get the qubit frequency
    Instance_specSlice = SpecSlice_bkg_sub(path="dataTestSpecSlice", cfg=config_spec, soc=soc, soccfg=soccfg,
                                           outerFolder=outerFolder, progress=True)
    data_specSlice = Instance_specSlice.acquire()
    Instance_specSlice.display(data_specSlice, plotDisp=False)
    Instance_specSlice.save_config()
    Instance_specSlice.save_data(data_specSlice)
    qubit_freq = data_specSlice["data"]["f_reqd"]
    print("Qubit frequency is ", qubit_freq)
    config_ss["qubit_freq"] = qubit_freq

    # Get the qubit temperature
    time_required = config_ss["shots"] * config_ss["relax_delay"] * 1e-6 / 60
    print("SingleShot : Total time estimate is ", time_required, " mins")
    print('starting scan: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
    Instance_SingleShotProgram = SingleShotSSE(path="TempMeas_yoko_" + str(config_ss["yokoVoltage_freqPoint"]),
                                               outerFolder=outerFolder, cfg=config_ss,
                                               soc=soc, soccfg=soccfg)
    data_SingleShot = Instance_SingleShotProgram.acquire()
    data_SingleShot = Instance_SingleShotProgram.process_data(data_SingleShot, bin_size=51)
    Instance_SingleShotProgram.save_data(data_SingleShot)
    Instance_SingleShotProgram.display(data_SingleShot, plotDisp=False, save_fig=True)
    print('end of scan: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))

    # Getting the temperatures
    tempr_list.append(data_SingleShot["data"]["tempr"])
    tempr_std_list.append(data_SingleShot["data"]["tempr_std"])

    # Getting the fridge temperature
    tempr_fridge.append(float(lakeshore.get_temp(7)) * 1e3)
    data_SingleShot["data"]["fridge_temp_meas"] = tempr_fridge[-1]

    Instance_SingleShotProgram.save_config()

    # Get the T1 of the data
    # Estimating Time
    time_per_scan = config_t1["shots"] * (
            np.linspace(config_t1["wait_start"], config_t1["wait_stop"], config_t1["wait_num"])
            + config_t1["relax_delay"]) * 1e-6
    total_time = np.sum(time_per_scan) / 60

    # Measuring
    print('T1 : Total time estimate: ' + str(total_time) + " minutes")
    print('starting scan: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
    Instance_T1_PS = T1_PS_sse(path="T1_PS_temp_" + str(config["fridge_temp"]), outerFolder=outerFolder,
                               cfg=config_t1,
                               soc=soc, soccfg=soccfg)
    data_T1_PS = Instance_T1_PS.acquire()
    data_T1_PS = Instance_T1_PS.process_data(data_T1_PS)
    Instance_T1_PS.display(data_T1_PS, plotDisp=False)
    T1_meas = data_T1_PS["data"]["T1"]
    T1_meas_err = data_T1_PS["data"]["T1_err"]
    rate_tempr = data_T1_PS["data"]["temp_rate"]
    rate_tempr_std = data_T1_PS["data"]["temp_std_rate"]
    Instance_T1_PS.save_data(data_T1_PS)
    Instance_T1_PS.save_config()
    t1_list.append(T1_meas)
    t1_instance.append(Instance_T1_PS)
    print('end of scan: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))

#%%
#TITLE Saving the data

# Create a dictionary to store the data
data_dict = {
    "yoko_voltage": yoko_list,
    "tempr": tempr_list,
    "tempr_std": tempr_std_list,
    "tempr_fridge": tempr_fridge,
    "t1_list": t1_list,
}

# Save the data as a h5 file
import h5py
now = datetime.datetime.now()
formatted_datetime = now.strftime("%Yy%mm%dd_%Hh_%Mm")
filename = outerFolder + "Processed_Data\\Temp_vs_YokoVoltage" + formatted_datetime +".h5"
with h5py.File(filename, "w") as f:
    for key in data_dict.keys():
        f.create_dataset(key, data=data_dict[key])

#%%
# Plotting the temperatures
import matplotlib.pyplot as plt
plt.close('all')
fig, ax = plt.subplots(1, 1, figsize=(8, 6))
plt.rcParams.update({'font.size': 10})
ax.errorbar(np.array(yoko_list), np.array(tempr_list)*1e3, yerr=np.array(tempr_std_list)*1e3, fmt='o', label = 'Temperature')
ax.plot(yoko_list, tempr_fridge, 'o', label = 'Fridge Temperature')
ax.set_xlabel('Yoko Voltage (V)')
ax.set_ylabel('Temperature (mK)')
# add grid
ax.grid()
# add legend
ax.legend()
plt.tight_layout()

plt.savefig(outerFolder +  "Processed_Data\\Temp_vs_YokoVoltage"+formatted_datetime+".png")
plt.show()
#%%
plt.close('all')
fig, ax = plt.subplots(1, 1, figsize=(8, 6))
ax.plot( yoko_list, t1_list, 'o-', label = 'T1')
ax.set_xlabel('Yoko Voltage (V)')
ax.set_ylabel('Temperature (mK)')
# add grid
ax.grid()
# add legend
ax.legend()
plt.tight_layout()

plt.savefig(outerFolder +  "Processed_Data\\T1_vs_YokoVoltage"+formatted_datetime+".png")
plt.show()
