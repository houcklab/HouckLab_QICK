#### import packages
import os

import numpy as np

path = os.getcwd()
path = r'C:\Users\pjatakia\Documents\GitHub\HouckLab_QICK\WorkingProjects\Tantalum_fluxonium_marvin\Client_modules\PythonDrivers'
os.add_dll_directory(os.path.dirname(path) + '\\PythonDrivers')
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Calib.initialize import *
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mSingleShotProgram import SingleShotProgram
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mSpecSlice_SaraTest import SpecSlice
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mSingleShotTemp_sse import SingleShotSSE
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mT1_PS_sse import T1_PS_sse
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mSingleShotPS import SingleShotPS
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mQND import QNDmeas
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mAmplitudeRabiBlob_PS_sse import \
    AmplitudeRabi_PS_sse
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mAmplitudeRabiFlux_PS import \
    AmplitudeRabiFlux_PS
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mT2R_PS import T2R_PS
from matplotlib import pyplot as plt
import datetime
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mT1_PS import T1_PS
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mRepeatReadout import RepeatReadout

outerFolder = "Z:\\TantalumFluxonium\\Data\\2025_07_25_cooldown\\QCage_dev\\"

# Only run this if no proxy already exists
soc, soccfg = makeProxy()
# print(soccfg)

fridge_temp = 10
relax_delay = 1000
wait_stop = 800

SwitchConfig = {
    "trig_buffer_start": 0.035,  # in us
    "trig_buffer_end": 0.024,  # in us
    "trig_delay": 0.07,  # in us
}

BaseConfig = BaseConfig | SwitchConfig
# %%
UpdateConfig = {
    ##### set yoko
    "yokoVoltage": -3.835,
    "yokoVoltage_freqPoint": -3.835,
    ###### cavity
    "reps": 2000,  # this will used for all experiements below unless otherwise changed in between trials
    "read_pulse_style": "const",  # --Fixed
    "read_length": 15,  # [Clock ticks]
    "read_pulse_gain": 10000,  # [DAC units]
    "read_pulse_freq": 6437.6,  # [MHz]
    ##### qubit spec parameters
    "qubit_pulse_style": "flat_top",
    "qubit_gain": 500,
    # "qubit_length": 10,  ###us, this is used if pulse style is const
    "sigma": 0.005,  ### units us, define a 20ns sigma
    "flat_top_length": 20,  ### in us
    "qubit_freq": 427.33,
    "relax_delay": 500,  ### turned into us inside the run function
    #### define shots
    "shots": 4000,  ### this gets turned into "reps"
    ##### record the fridge temperature in units of mK
    "fridge_temp": fridge_temp,
    "use_switch": True,
}
config = BaseConfig | UpdateConfig

yoko1.SetVoltage(config["yokoVoltage"])

outerFolder = "Z:\\TantalumFluxonium\\Data\\2023_10_31_BF2_cooldown_6\\TF4\\TempChecks\\Yoko_" + str(
    config["yokoVoltage_freqPoint"]) + "\\"
# Instance_SingleShotProgram = SingleShotProgram(path="SingleShot_temp_"+str(config["fridge_temp"]), outerFolder=outerFolder, cfg=config,
#                                                soc=soc, soccfg=soccfg)
# data_SingleShot = SingleShotProgram.acquire(Instance_SingleShotProgram)
# SingleShotProgram.save_data(Instance_SingleShotProgram, data_SingleShot)
# SingleShotProgram.save_config(Instance_SingleShotProgram)
# SingleShotProgram.display(Instance_SingleShotProgram, data_SingleShot, plotDisp=True, save_fig=True)
#
# # # # ##### run the single shot experiment
outerFolder = "Z:\\TantalumFluxonium\\Data\\2023_10_31_BF2_cooldown_6\\TF4\\singleShotSweeps\\"
loop_len = 21
freq_vec = config["read_pulse_freq"] + np.linspace(-0.5, 0.5, loop_len)
# qubit_gain_vec = np.linspace(10000, 20000, loop_len, dtype=int)
# read_gain_vec = np.linspace(6000, 13000, loop_len, dtype=int)
# qubit_freq_vec = config["qubit_freq"] + np.linspace(-10,10,loop_len)
# qubit_gain_vec = np.linspace(20000,31000, loop_len, dtype = int)
# flat_top_length_vec = np.linspace(1,40,loop_len, dtype = int)
for idx in range(loop_len):
    config["read_pulse_freq"] = freq_vec[idx]
    # config["qubit_gain"] = qubit_gain_vec[idx]
    # config["read_pulse_gain"] = read_gain_vec[idx]
    # config["qubit_freq"] = qubit_freq_vec[idx]
    # config['flat_top_length'] = flat_top_length_vec[idx]
    Instance_SingleShotProgram = SingleShotProgram(path="SingleShot_sweeps_yoko_" + str(config["yokoVoltage"]),
                                                   outerFolder=outerFolder, cfg=config, soc=soc, soccfg=soccfg)
    data_SingleShot = SingleShotProgram.acquire(Instance_SingleShotProgram)
    SingleShotProgram.display(Instance_SingleShotProgram, data_SingleShot, plotDisp=False, save_fig=True)
    SingleShotProgram.save_data(Instance_SingleShotProgram, data_SingleShot)
    SingleShotProgram.save_config(Instance_SingleShotProgram)
    plt.clf()
    plt.close()
#     plt.clf()
#     print(idx)
# ###########

# %%
# TITLE : code finding T1 of a thermal state with and without pulses
UpdateConfig = {
    # yoko
    "yokoVoltage": -3,
    "yokoVoltage_freqPoint": -3,

    # cavity
    "read_pulse_style": "const",
    "read_length": 60,
    "read_pulse_gain": 1500,
    "read_pulse_freq": 6244.2,

    # qubit tone
    "qubit_pulse_style": "const",
    "qubit_gain": 10000,
    "qubit_length": 20,
    "sigma": 1,
    "flat_top_length": 10.0,
    "qubit_freq": 881,

    # experiment
    "shots": 20000,
    "wait_start": 0,
    "wait_stop": 4000,
    "wait_num": 21,
    'wait_type': 'linear',
    "cen_num": 2,
    "fridge_temp": 10,
    "relax_delay": 10,
    "use_switch": False,
}
config = BaseConfig | UpdateConfig

yoko1.SetVoltage(config["yokoVoltage"])

# calculate an estimate of the scan time
time_per_scan = config["shots"] * (
        np.linspace(config['wait_start'], config["wait_stop"], config["wait_num"]) + config["relax_delay"]) * 1e-6
total_time = np.sum(time_per_scan) / 60
print('total time estimate: ' + str(total_time) + " minutes")

# Run
print('starting scan: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
Instance_T1_PS = T1_PS_sse(path="T1_PS_temp_" + str(config["fridge_temp"]), outerFolder=outerFolder, cfg=config,
                           soc=soc, soccfg=soccfg)
data_T1_PS = Instance_T1_PS.acquire()
data_T1_PS = Instance_T1_PS.process_data(data_T1_PS)
Instance_T1_PS.save_data(data_T1_PS)
Instance_T1_PS.save_config()
Instance_T1_PS.display(data_T1_PS, plotDisp=True)
# %%
# TITLE : Measure Temperature using Single Shot

# Set the path to save data
outerFolder = "Z:\\TantalumFluxonium\\Data\\2024_06_29_cooldown\\QCage_dev\\"

# Update the dictionary
UpdateConfig = {
    # Yoko
    "yokoVoltage": 3,
    "yokoVoltage_freqPoint": 3,

    # Readout
    "reps": 2000,
    "read_pulse_style": "const",
    "read_length": 60,
    "read_pulse_gain": 1900,
    "read_pulse_freq": 6248.51,

    # Qubit Tone
    "qubit_pulse_style": "arb",
    "qubit_ge_gain": 1,
    "qubit_ef_gain": 1,
    "sigma": 0.05,
    "qubit_ge_freq": 1000,
    "qubit_ef_freq": 2000,
    "flat_top_length": 20,

    # Experiment
    "shots": 100000,
    "cen_num": 3,
    "relax_delay": 2000,
    "fridge_temp": 10,
    "use_switch": False,
    "initialize_pulse": False,
}
config = BaseConfig | UpdateConfig

# Set Yoko Voltage
yoko1.SetVoltage(config["yokoVoltage"])

# Estimate Time
time_required = config["shots"] * config["relax_delay"] * 1e-6 / 60
print("Time required is ", time_required, " mins")

# Run Experiment
inst_tempr = SingleShotSSE(path="TempMeas_temp_" + str(config["fridge_temp"]), outerFolder=outerFolder, cfg=config,
                           soc=soc, soccfg=soccfg)
data_tempr = inst_tempr.acquire()

# Process Data
centers = np.array([[-2,0.5],[0.5,0],[-1.5,-2]])
data_tempr = inst_tempr.process_data(data_tempr, bin_size=51, centers = centers)
inst_tempr.save_data(data_tempr)
inst_tempr.save_config()
inst_tempr.display(data_tempr, plotDisp=True, save_fig=True)

# %%
# TITLE :QNDness measurement
UpdateConfig = {
    # yoko
    "yokoVoltage": -0.1202,
    "yokoVoltage_freqPoint": -0.1202,

    # cavity
    "read_pulse_style": "const",
    "read_length": 35,
    "read_pulse_gain": 10000,
    "read_pulse_freq": 6671.25,

    # qubit tone
    "qubit_pulse_style": "flat_top",
    "qubit_gain": 20000,
    "qubit_length": 4,
    "sigma": 0.02,
    "flat_top_length": 4,
    "qubit_freq": 1024,

    # Experiment
    "shots": 500000,
    "cen_num": 2,
    "relax_delay": 10,
    "fridge_temp": 10,
    'use_switch': True,
}
config = BaseConfig | UpdateConfig

yoko1.SetVoltage(config["yokoVoltage"])

# %%
soc.reset_gens()
time_required = (config["relax_delay"] +config["read_length"] + config["flat_top_length"])* config["shots"] * 1e-6 / 60
print("QND Measure Time Required: ", time_required, "min")
inst_qnd = QNDmeas(path="QND_Meas_temp_" + str(config["fridge_temp"]), outerFolder=outerFolder, cfg=config,
                   soc=soc, soccfg=soccfg)

data_QNDmeas = inst_qnd.acquire()
data_QNDmeas = inst_qnd.process_data(data_QNDmeas, toPrint=True, confidence_selection=0.995)
inst_qnd.save_data(data_QNDmeas)
inst_qnd.save_config()
inst_qnd.display(data_QNDmeas, plotDisp=True)
#%%
# TITLE : Brute Search best parameters
param_bounds ={
    "read_pulse_freq" : (config["read_pulse_freq"] - 0.2, config["read_pulse_freq"] + 0.2 ),
    'read_length': (20, 40),
    'read_pulse_gain': (8000, 9000)
}
step_size = {
    "read_pulse_freq" : 0.04,
    'read_length': 5,
    'read_pulse_gain': 200,
}
keys = ["read_length", "read_pulse_gain"]
config["shots"] = 200000
inst_qndopt = QNDmeas(path="QND_Optimization", outerFolder=outerFolder, cfg=config, soc=soc, soccfg=soccfg)
opt_results = inst_qndopt.brute_search(keys, param_bounds, step_size, store = True, confidence_selection = 0.95)
inst_qndopt.brute_search_result_display(display = True)

#%%
# TITLE : Sweep Flux
UpdateConfig = {
    # yoko
    "yokoVoltage": -0.1205,
    "yokoVoltage_freqPoint": -0.1205,

    # cavity
    "read_pulse_style": "const",
    "read_length": 30,
    "read_pulse_gain": 10000,
    "read_pulse_freq": 6671.25,

    # qubit tone
    "qubit_pulse_style": "flat_top",
    "qubit_gain": 30000,
    "qubit_length": 4,
    "sigma": 0.02,
    "flat_top_length":1,
    "qubit_freq": 1010,

    # Experiment
    "shots": 100000,
    "cen_num": 2,
    "relax_delay": 10,
    "fridge_temp": 10,
    'use_switch': True,
}
config_qnd = BaseConfig | UpdateConfig

UpdateConfig = {
    # Parameters
    "reps": 3000,  # Number of repetitions

    # cavity
    "read_pulse_style": "const",
    "read_length": 30,
    "read_pulse_gain": 10000,
    "read_pulse_freq": 6671.25,  # 6253.8,

    # qubit tone
    "qubit_pulse_style": "flat_top",  # Constant pulse
    "qubit_gain": 30000,  # [DAC Units]
    'sigma': 2,
    'flat_top_length': 1,
    "qubit_length": 0.5,  # [us]

    # Define spec slice experiment parameters
    "qubit_freq_start": 800,
    "qubit_freq_stop": 1200,
    "SpecNumPoints": 101,  # Number of points
    'spec_reps': 4000,  # Number of repetition
    "delay_btwn_pulses" : 0.05, # Delay between the qubit tone and the readout tone. If not defined it uses 50ns

    # Define the yoko voltage
    "yokoVoltage": -0.1205,
    "relax_delay": 10,  # [us] Delay post one experiment
    'use_switch': False, # This is for turning off the heating tone
    'mode_periodic': False,
    'ro_periodic': False,
}
config_spec = BaseConfig | UpdateConfig

yoko_range = np.linspace(-0.1205, -0.1195, 21)
qnd_list = []
qnd0_list = []
qnd1_list = []
outerFolderQND = outerFolder + "QND_Flux_Sweep2\\"
for i in range(yoko_range.size):
    # Set yoko
    yoko1.SetVoltage(yoko_range[i])
    config_qnd["yokoVoltage"] = yoko_range[i]
    config_spec["yokoVoltage"] = yoko_range[i]
    # Wait for 5s for stabilization
    time.sleep(5)

    # Run Spec Slice
    soc.reset_gens()
    Instance_specSlice = SpecSlice(path="Spec_" + str(yoko_range[i]), cfg=config_spec, soc=soc, soccfg=soccfg,
                                   outerFolder=outerFolderQND)
    data_specSlice = SpecSlice.acquire(Instance_specSlice)
    SpecSlice.display(Instance_specSlice, data_specSlice, plotDisp=False)
    SpecSlice.save_data(Instance_specSlice, data_specSlice)
    print("Qubit frequency = ",Instance_specSlice.qubitFreq)
    # Update qubit frequency in QND config
    config_qnd["qubit_freq"] = Instance_specSlice.qubitFreq

    # Run QND
    soc.reset_gens()
    inst_qnd = QNDmeas(path="QND_Meas_" + str(yoko_range[i]), outerFolder=outerFolderQND, cfg=config_qnd,
                       soc=soc, soccfg=soccfg)

    data_QNDmeas = inst_qnd.acquire()
    data_QNDmeas = inst_qnd.process_data(data_QNDmeas, toPrint=True, confidence_selection=0.98)
    inst_qnd.save_data(data_QNDmeas)
    inst_qnd.save_config()
    inst_qnd.display(data_QNDmeas, plotDisp=False)
    qnd_list.append(data_QNDmeas['data']['qnd'])
    qnd0_list.append(data_QNDmeas['data']['state0_probs'][0])
    qnd1_list.append(data_QNDmeas['data']['state1_probs'][1])

#%%
# Plot QND vs Yoko Voltage in subplot 1
# Plot State 0 and State 1 probabilities vs Yoko Voltage in subplot 2
fig, axs = plt.subplots(2, 1, figsize=(8, 10))
axs[0].plot(yoko_range, qnd_list, marker='o')
axs[0].set_title('QND vs Yoko Voltage')
axs[0].set_xlabel('Yoko Voltage (V)')
axs[0].set_ylabel('QND')
axs[0].grid()
axs[1].plot(yoko_range, qnd0_list, marker='o', label='State 0 Probability')
axs[1].plot(yoko_range, qnd1_list, marker='o', label='State 1 Probability')
axs[1].set_title('State Probabilities vs Yoko Voltage')
axs[1].set_xlabel('Yoko Voltage (V)')
axs[1].set_ylabel('Probability')
axs[1].legend()
axs[1].grid()

plt.show()


#####################################################################################################################
print('program complete: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
plt.show()
