#%%
import os
import time
import datetime
import numpy as np
import WorkingProjects.Tantalum_fluxonium.Client_modules.PythonDrivers.LS370 as lk
import pyvisa

from WorkingProjects.Tantalum_fluxonium.Client_modules.Calib.initialize import *
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mSingleShotTemp_sse import SingleShotSSE
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mSpecSlice_bkg_subtracted import SpecSlice_bkg_sub
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mQubit_ef_spectroscopy import Qubit_ef_spectroscopy


# Define the saving path
outerFolder = "Z:\\TantalumFluxonium\\Data\\2023_10_31_BF2_cooldown_6\\TF4\\Magnet_Heating_Check\\"

# Defining the standard config files
SwitchConfig = {
    "trig_buffer_start": 0.035, # in us
    "trig_buffer_end": 0.024, # in us
    "trig_delay": 0.07, # in us
}

BaseConfig = BaseConfig | SwitchConfig
#%%
# TITLE: Auto Calibration

# import the measurement class
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mAutoCalibrator import CalibratedFlux

# Defining changes to the config
UpdateConfig = {
    # define the yoko voltage
    "yokoVoltageStart": 0.0,
    "yokoVoltageStop": 10.0,
    "yokoVoltageNumPoints": 321,

    # cavity and readout
    "trans_reps": 100,
    "read_pulse_style": "const",
    "read_length": 20,  # us
    "read_pulse_gain": 7000,  # [DAC units]
    "trans_freq_start": 6437.4 - 1.0,  # [MHz]
    "trans_freq_stop": 6437.4 + 1.0,  # [MHz]
    "TransNumPoints": 51,

    # Experiment Parameters
    "relax_delay": 5,
    "flux_quantum": 9.3906,
    'use_switch': True,
}
config_cal = BaseConfig | UpdateConfig

#%%
yoko_calibration = CalibratedFlux(path="data_calibration", outerFolder=outerFolder, cfg=config_cal, soc=soc, soccfg=soccfg)
yoko_calibration.calibrate()
yoko_calibration.save_data()
yoko_calibration.display()

#%%
# Get the flux point for the old yoko voltage
# old_flux = 0.3823529411764705
old_flux = yoko_calibration.yoko_to_flux(7.3, 3.725, 8.4)
print(old_flux)
new_yoko = yoko_calibration.flux_to_yoko(old_flux + 1)
print(new_yoko)
yoko1.SetVoltage(new_yoko)

#%%
# TITLE Defining common experiment configurations
UpdateConfig = {
    # set yoko
    "yokoVoltage": 0,  # [in V]
    "yokoVoltage_freqPoint": 0,  # [in V] used for naming the file systems

    # cavity
    "read_pulse_style": "const",
    "read_length": 4,  # [in us]
    "read_pulse_gain": 14000,  # [in DAC units]
    "read_pulse_freq": 6437.1,  # [in MHz]

    # qubit g-e drive parameters
    "qubit_ge_freq": 2000,  # [in MHz]
    "qubit_pulse_style": "arb",
    "qubit_ge_gain": 2000,
    "sigma": 1,
    "flat_top_length": 30,

    # qubit e-f drive parameters
    "qubit_ef_freq": 1630.503,
    "qubit_ef_gain": 12000,

    # experiment parameters
    "cen_num": 3,  # Number of states expected
    "relax_delay": 6*300,
    'use_switch': True,
    'fridge_temp': 10,
}

config = BaseConfig | UpdateConfig


#%%
# TITLE : Run a g-e spec slice

# For the spec slice experiment
UpdateConfig = {
    # define spec slice experiment parameters
    "qubit_freq_start": 1800,
    "qubit_freq_stop": 2100,
    "SpecNumPoints": 601,
    'spec_reps': 6000,
    'qubit_gain': 4000,
    'relax_delay': 10,
}
config_spec = config | UpdateConfig

#%%

Instance_specSlice = SpecSlice_bkg_sub(path="dataTestSpecSlice", cfg=config_spec, soc=soc, soccfg=soccfg,
                                       outerFolder=outerFolder, progress=True)
data_specSlice = Instance_specSlice.acquire()
Instance_specSlice.display(data_specSlice, plotDisp=False)
Instance_specSlice.save_config()
Instance_specSlice.save_data(data_specSlice)
qubit_freq = data_specSlice["data"]["f_reqd"]
print("Qubit frequency is ", qubit_freq)
config["qubit_ge_freq"] = qubit_freq

#%%
# TITLE : Get the e-f frequency

# For the e-f frequency spec
UpdateConfig = {
    # e-f parameters
    "qubit_ef_freq_start": 1600,
    "qubit_ef_freq_step": 1,
    "qubit_ef_gain": 12000,
    "SpecNumPoints": 401,
    "reps": 500,
}
config_ef = config | UpdateConfig

#%%
instance_ef_spec = Qubit_ef_spectroscopy(path="dataQubit_ef_spectroscopy", outerFolder=outerFolder, cfg=config_ef,soc=soc,soccfg=soccfg, progress=True)
data_ef_spec = instance_ef_spec.acquire()
instance_ef_spec.save_data(data_ef_spec)
instance_ef_spec.save_config()
instance_ef_spec.display(data_ef_spec, plotDisp=True)
config["qubit_ef_freq"] = data_ef_spec['data']['f_reqd']


#%%
# TITLE : Measure temperature

# For the single shot experiment
UpdateConfig = {
        ## define experiment parameters
        "shots": int(2e6),
        "use_switch": True,
        "initialize_pulse": True,
    }
config_ss = config | UpdateConfig

#%%

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


#%%
# Set up the Lakeshore
rm = pyvisa.ResourceManager()
LS370_connection = rm.open_resource('GPIB1::12::INSTR')
lakeshore = lk.Lakeshore370(LS370_connection)

# Sweep over yoko voltage symmetry points
N = 2 # will go from -N to N
old_flux = 0.3823529411764705
flux_list = old_flux*np.tile(np.array([-1,1]), 2*N + 1) + np.repeat(np.linspace(-N,N,2*N+1),2)
print(flux_list) # For N = 1 -> -phi-phi_0,phi-phi_0,-phi,phi,-phi+phi_0,phi+phi_0
flux_list = np.repeat(flux_list, 3)
print(flux_list)

# Creating empty lists to store the temperatures and error
tempr_list = []
tempr_std_list = []
tempr_fridge = []
yoko_list = []

#%%
from tqdm import tqdm
for idx_flux in tqdm(range(flux_list.size)):

    # Calibrate the flux
    yoko_calibration = CalibratedFlux(path="data_calibration", outerFolder=outerFolder, cfg=config_cal, soc=soc,
                                      soccfg=soccfg)
    yoko_calibration.calibrate()
    yoko_calibration.save_data()
    yoko_calibration.display()

    # Find the new yoko voltage
    new_yoko = yoko_calibration.flux_to_yoko(flux_list[idx_flux])
    print("Setting the yoko to ", new_yoko)
    yoko1.SetVoltage(new_yoko)
    time.sleep(900)

    # Update all
    config_ss["yokoVoltage"] = new_yoko
    config_ss["yokoVoltage_freqPoint"] = new_yoko
    config_ss["flux"] = flux_list[idx_flux]
    config_spec["yokoVoltage"] = new_yoko
    config_spec["yokoVoltage_freqPoint"] = new_yoko
    config_spec["flux"] = flux_list[idx_flux]
    config_ef["yokoVoltage"] = new_yoko
    config_ef["yokoVoltage_freqPoint"] = new_yoko
    config_ef["flux"] = config_spec["flux"] = flux_list[idx_flux]

    yoko_list.append(new_yoko)

    # Get the qubit g-e frequency
    Instance_specSlice = SpecSlice_bkg_sub(path="dataTestSpecSlice", cfg=config_spec, soc=soc, soccfg=soccfg,
                                           outerFolder=outerFolder, progress=True)
    data_specSlice = Instance_specSlice.acquire()
    Instance_specSlice.display(data_specSlice, plotDisp=False)
    Instance_specSlice.save_config()
    Instance_specSlice.save_data(data_specSlice)
    qubit_freq = data_specSlice["data"]["f_reqd"]
    print("Qubit frequency is ", qubit_freq)
    config_ss["qubit_ge_freq"] = qubit_freq

    # Get the qubit e-f frequency
    instance_ef_spec = Qubit_ef_spectroscopy(path="dataQubit_ef_spectroscopy", outerFolder=outerFolder, cfg=config_ef,
                                             soc=soc, soccfg=soccfg, progress=True)
    data_ef_spec = instance_ef_spec.acquire()
    instance_ef_spec.save_data(data_ef_spec)
    instance_ef_spec.save_config()
    instance_ef_spec.display(data_ef_spec, plotDisp=False)
    config["qubit_ef_freq"] = data_ef_spec["data"]['f_reqd']

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

#%%
#TITLE Saving the data

# Create a dictionary to store the data
data_dict = {
    "yoko_voltage": yoko_list,
    "tempr": tempr_list,
    "tempr_std": tempr_std_list,
    "tempr_fridge": tempr_fridge
}

# Save the data as a h5 file
import h5py
now = datetime.datetime.now()
formatted_datetime = now.strftime("%Yy%mm%dd_%Hh_%Mm")
filename = outerFolder + "Temp_vs_YokoVoltage" + formatted_datetime +".h5"
with h5py.File(filename, "w") as f:
    for key in data_dict.keys():
        f.create_dataset(key, data=data_dict[key])

#%%
tempr01 = []
tempr01_std = []
tempr12 = []
tempr12_std = []
tempr02 = []
tempr02_std = []

for idx in range(len(tempr_list)):
    tempr01.append(tempr_list[idx][0, 1])
    tempr12.append(tempr_list[idx][1, 2])
    tempr02.append(tempr_list[idx][0, 2])
    tempr01_std.append(tempr_std_list[idx][0, 1])
    tempr12_std.append(tempr_std_list[idx][1, 2])
    tempr02_std.append(tempr_std_list[idx][0, 2])


#%%
# Plotting the temperatures
import matplotlib.pyplot as plt
plt.close('all')
fig, ax = plt.subplots(1, 1, figsize=(8, 6))
ax.errorbar(np.array(yoko_list[1:]), np.array(tempr01)*1e3, yerr=np.array(tempr01_std)*1e3, fmt='o', label = 'Temperature 01')
ax.errorbar(np.array(yoko_list[1:]), np.array(tempr12)*1e3, yerr=np.array(tempr12_std)*1e3, fmt='o', label = 'Temperature 12')
ax.errorbar(np.array(yoko_list[1:]), np.array(tempr02)*1e3, yerr=np.array(tempr02_std)*1e3, fmt='o', label = 'Temperature 02')
ax.plot(yoko_list[1:], tempr_fridge, 'o', label = 'Fridge Temperature')
ax.set_xlabel('Yoko Voltage (V)')
ax.set_ylabel('Temperature (mK)')
# add grid
ax.grid()
# add legend
ax.legend()
# Make the font size bigger
plt.rcParams.update({'font.size': 20})
plt.tight_layout()

plt.savefig(outerFolder + "Temp_vs_YokoVoltage"+formatted_datetime+".png")
plt.show()



# # Getting the temperatures
# state_prob = data_SingleShot["data"]["prob"]
# state_prob_std = data_SingleShot["data"]["prob_std"]
# state_tempr = data_SingleShot["data"]["tempr"]
# state_tempr_std = data_SingleShot["data"]["tempr_std"]

