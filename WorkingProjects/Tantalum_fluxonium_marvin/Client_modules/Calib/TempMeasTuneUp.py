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
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mTransmission_SaraTest import Transmission
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mAmplitudeRabiBlob_PS_sse import \
    AmplitudeRabi_PS_sse
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mAmplitudeRabiFlux_PS import \
    AmplitudeRabiFlux_PS
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mT2R_PS import T2R_PS
from matplotlib import pyplot as plt
import datetime
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mT1_PS import T1_PS
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mRepeatReadout import RepeatReadout
outerFolder = "Z:\\TantalumFluxonium\\Data\\2026_06_07_cooldown\\QCage_dev\\"


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
    "yokoVoltage": 0.0113,
    "yokoVoltage_freqPoint": 0.0113,

    # cavity
    "read_pulse_style": "const",
    "read_length": 9,
    "read_pulse_gain": 9000,
    "read_pulse_freq": 6671.695,

    # qubit tone
    "qubit_pulse_style": "const",
    "qubit_gain": 4000,
    "qubit_length": 20,
    "sigma": 1,
    "flat_top_length": 10.0,
    "qubit_freq": 1470,

    # experiment
    "shots": 20000,
    "wait_start": 0,
    "wait_stop": 300,
    "wait_num": 31,
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
    "yokoVoltage": 0.0951,
    "yokoVoltage_freqPoint": 0.0951,

    # cavity
    "read_pulse_style": "const",
    "read_length": 35,
    "read_pulse_gain": 2200,
    "read_pulse_freq": 7077.48,

    # qubit tone
    "qubit_ch":1,
    "qubit_pulse_style": "const",
    "qubit_gain": 25000,
    "qubit_length": 20,
    "sigma": 0.2,
    "flat_top_length": 40,
    "qubit_freq": 3050,

    # Experiment
    "shots": 400000,
    "cen_num": 2,
    "relax_delay": 50,
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
data_QNDmeas = inst_qnd.process_data(data_QNDmeas, toPrint=True, confidence_selection=0.99)
inst_qnd.save_data(data_QNDmeas)
inst_qnd.save_config()
inst_qnd.display(data_QNDmeas, plotDisp=True)
#%%
# TITLE : Brute Search best parameters
config = BaseConfig | UpdateConfig
param_bounds ={
    "read_pulse_freq" : (config["read_pulse_freq"] - 0.04 , config["read_pulse_freq"] + 0.04),
    'read_length': (2, 20),
    'read_pulse_gain': (1500, 5100)
}
step_size = {
    "read_pulse_freq" : 0.001,
    'read_length': 2,
    'read_pulse_gain': 200,
}
keys = ["read_pulse_freq"]
config["shots"] = 50000
soc.reset_gens()
inst_qndopt = QNDmeas(path="QND_Optimization", outerFolder=outerFolder, cfg=config, soc=soc, soccfg=soccfg)
opt_results = inst_qndopt.brute_search(keys, param_bounds, step_size, store = True, confidence_selection = 0.95)
inst_qndopt.brute_search_result_display(display = True)
print(opt_results)

#%%
# TITLE : Sweep Flux
UpdateConfig = {
    # yoko
    "yokoVoltage": -0.1205,
    "yokoVoltage_freqPoint": -0.1205,

    # cavity
    "read_pulse_style": "const",
    "read_length": 30,
    "read_pulse_gain": 5000,
    "read_pulse_freq": 6670.47,

    # qubit tone
    "qubit_pulse_style": "flat_top",
    "qubit_gain": 30000,
    "qubit_length": 4,
    "sigma": 0.02,
    "flat_top_length":1,
    "qubit_freq": 1960,

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
    "read_pulse_gain": 3000,
    "read_pulse_freq": 6670.47,  # 6253.8,

    # qubit tone
    "qubit_pulse_style": "flat_top",  # Constant pulse
    "qubit_gain": 30000,  # [DAC Units]
    'sigma': 2,
    'flat_top_length': 1,
    "qubit_length": 0.5,  # [us]

    # Define spec slice experiment parameters
    "qubit_freq_start": 1800,
    "qubit_freq_stop": 2200,
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

yoko_range = np.linspace(-0.14, -0.15, 51)
qnd_list = []
qnd0_list = []
qnd1_list = []
outerFolderQND = outerFolder + "QND_Flux_Sweep3\\"
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

# %%
# TITLE : QND readout sweep over gain and length with transmission calibration
UpdateConfig = {
    # yoko
    "yokoVoltage": 0.0941,
    "yokoVoltage_freqPoint": 0.0941,

    # cavity
    "read_pulse_style": "const",
    "read_length": 23,
    "read_pulse_gain": 2200,
    "read_pulse_freq": 7077.494,
    "TransSpan": 1,
    "TransNumPoints": 101,
    "reps": 500,
    "meas_config": "hanger",

    # qubit tone
    "qubit_ch": 1,
    "qubit_pulse_style": "const",
    "qubit_gain": 32000,
    "qubit_length": 30,
    "sigma": 0.2,
    "flat_top_length": 80,
    "qubit_freq": 3050,

    # experiment
    "shots": 50000,
    "cen_num": 2,
    "relax_delay": 50,
    "fridge_temp": 10,
    "use_switch": True,
}
config = BaseConfig | UpdateConfig

yoko1.SetVoltage(config["yokoVoltage"])

read_pulse_gain_vec = np.linspace(1400, 2400, 21, dtype=int)
read_length_vec = np.linspace(15,55, 11, dtype=int)

# Manually choose only the readout settings worth testing.
# Add or remove pairs here instead of sweeping the full Cartesian product.
# readout_pairs = [
#     (1000, 20),
#     (1000, 50),
#     (3000, 10),
#     (3000, 20),
#     (3000, 50),
#     (5000, 1),
#     (5000, 5),
#     (5000, 10),
#     (7000, 0.5),
#     (7000, 5),
# ]

# Generate every gain/length combination instead of using the manual list above.
readout_pairs = [(int(gain), float(length)) for gain in read_pulse_gain_vec for length in read_length_vec]


qnd_grid = np.full((read_length_vec.size, read_pulse_gain_vec.size), np.nan)
peak_freq_grid = np.full((read_length_vec.size, read_pulse_gain_vec.size), np.nan)
qnd_sweep_results = []

run_timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
sweep_folder = os.path.join(outerFolder, "QND_Readout_Sweep", run_timestamp) + "\\"
os.makedirs(sweep_folder, exist_ok=True)

for read_pulse_gain, read_length in readout_pairs:
    gain_idx_array = np.where(read_pulse_gain_vec == int(read_pulse_gain))[0]
    length_idx_array = np.where(np.isclose(read_length_vec, read_length))[0]
    if gain_idx_array.size == 0 or length_idx_array.size == 0:
        print("Skipping pair not present in sweep axes:", read_pulse_gain, read_length)
        continue

    gain_idx = gain_idx_array[0]
    length_idx = length_idx_array[0]

    config_trans = config.copy()
    config_qnd = config.copy()
    config_trans["read_length"] = read_length
    config_trans["read_pulse_gain"] = int(read_pulse_gain)
    config_qnd["read_length"] = read_length
    config_qnd["read_pulse_gain"] = int(read_pulse_gain)

    # First recalibrate the resonator frequency with a transmission scan.
    soc.reset_gens()
    Instance_trans = Transmission(
        path="dataTestTransmission_len_" + str(read_length) + "_gain_" + str(read_pulse_gain),
        cfg=config_trans,
        soc=soc,
        soccfg=soccfg,
        outerFolder=sweep_folder,
    )
    data_trans = Instance_trans.acquire()
    Instance_trans.save_data(data_trans)
    Instance_trans.display(data_trans, plotDisp=False)
    config_qnd["read_pulse_freq"] = Instance_trans.peakFreq
    peak_freq_grid[length_idx, gain_idx] = Instance_trans.peakFreq
    plt.close()

    # Run the QND experiment at the calibrated resonator frequency.
    soc.reset_gens()
    time_required = (
        (config_qnd["relax_delay"] + config_qnd["read_length"] + config_qnd["flat_top_length"])
        * config_qnd["shots"] * 1e-6 / 60
    )
    print(
        "Running read_length =",
        read_length,
        "read_pulse_gain =",
        read_pulse_gain,
        "read_pulse_freq =",
        config_qnd["read_pulse_freq"],
        "QND Measure Time Required:",
        time_required,
        "min",
    )
    inst_qnd = QNDmeas(
        path="QND_Meas_temp_" + str(config["fridge_temp"]) + "_len_" + str(read_length) + "_gain_" + str(read_pulse_gain),
        outerFolder=sweep_folder,
        cfg=config_qnd,
        soc=soc,
        soccfg=soccfg,
    )

    data_QNDmeas = inst_qnd.acquire()
    data_QNDmeas = inst_qnd.process_data(data_QNDmeas, toPrint=True, confidence_selection=0.95)
    inst_qnd.save_data(data_QNDmeas)
    inst_qnd.save_config()
    inst_qnd.display(data_QNDmeas, plotDisp=False)

    qnd_value = data_QNDmeas["data"]["qnd"]
    qnd_grid[length_idx, gain_idx] = qnd_value
    qnd_sweep_results.append({
        "read_length": float(read_length),
        "read_pulse_gain": int(read_pulse_gain),
        "read_pulse_freq": float(config_qnd["read_pulse_freq"]),
        "qnd": float(qnd_value),
    })
    plt.close()

np.savez(
    os.path.join(sweep_folder, "qnd_readout_sweep_results.npz"),
    read_length_vec=read_length_vec,
    read_pulse_gain_vec=read_pulse_gain_vec,
    qnd_grid=qnd_grid,
    peak_freq_grid=peak_freq_grid,
    qnd_sweep_results=np.array(qnd_sweep_results, dtype=object),
)

gain_mesh, length_mesh = np.meshgrid(read_pulse_gain_vec, read_length_vec)
plt.figure(figsize=(8, 6))
mesh = plt.pcolormesh(gain_mesh, length_mesh, qnd_grid, shading="auto")
plt.xlabel("Read Pulse Gain (DAC units)")
plt.ylabel("Read Length")
plt.title("QND vs Read Pulse Gain and Read Length")
plt.colorbar(mesh, label="QND")
plt.tight_layout()
plt.savefig(os.path.join(sweep_folder, "qnd_readout_sweep_results.png"), dpi=300, bbox_inches="tight")
plt.show()

# %%
# TITLE : Plot QND center separation over saved readout sweep
import json
import h5py
from sklearn.mixture import GaussianMixture
from tqdm import tqdm

qnd_sweep_folder = sweep_folder

qnd_data_files = []

for qnd_folder_name in sorted(os.listdir(qnd_sweep_folder)):
    if not qnd_folder_name.startswith("QND"):
        continue

    qnd_folder = os.path.join(qnd_sweep_folder, qnd_folder_name)
    if not os.path.isdir(qnd_folder):
        continue

    for run_folder_name in sorted(os.listdir(qnd_folder)):
        run_folder = os.path.join(qnd_folder, run_folder_name)
        if not os.path.isdir(run_folder):
            continue

        h5_files = sorted(
            file_name for file_name in os.listdir(run_folder)
            if file_name.endswith(".h5")
        )

        for h5_file_name in h5_files:
            h5_path = os.path.join(run_folder, h5_file_name)
            json_path = os.path.splitext(h5_path)[0] + ".json"
            qnd_data_files.append((h5_path, json_path))

snr_records = []

for h5_path, json_path in tqdm(qnd_data_files, desc="Processing QND files"):
    if not os.path.isfile(json_path):
        print("Skipping, missing JSON:", h5_path)
        continue

    try:
        with h5py.File(h5_path, "r") as h5_file:
            i_0 = np.array(h5_file["i_0"])
            q_0 = np.array(h5_file["q_0"])
            qnd_value = float(np.array(h5_file["qnd"]))

        iq_data = np.column_stack((i_0, q_0))
        gmm = GaussianMixture(
            n_components=2,
            covariance_type="tied",
            n_init=5,
            reg_covar=1e-6,
            random_state=0,
        )
        gmm.fit(iq_data)

        centers = gmm.means_
        shared_covariance = gmm.covariances_
        center_delta = centers[0] - centers[1]
        center_distance = np.linalg.norm(center_delta)
        shared_sigma = np.sqrt(np.trace(shared_covariance) / 2)
        snr = center_distance / shared_sigma

        with open(json_path, "r") as json_file:
            config_from_file = json.load(json_file)

        snr_records.append({
            "read_length": float(config_from_file["read_length"]),
            "read_pulse_gain": int(config_from_file["read_pulse_gain"]),
            "snr": float(snr),
            "center_distance": float(center_distance),
            "shared_sigma": float(shared_sigma),
            "qnd": qnd_value,
            "centers": centers,
            "shared_covariance": shared_covariance,
            "h5_path": h5_path,
        })
    except Exception as exc:
        print("Skipping due to error:", h5_path, exc)

if len(snr_records) == 0:
    raise RuntimeError("No QND SNR records found.")
#%%
read_lengths = np.array([record["read_length"] for record in snr_records])
read_pulse_gains = np.array([record["read_pulse_gain"] for record in snr_records])
snr_values = np.array([record["snr"] for record in snr_records])
qnd_values = np.array([record["qnd"] for record in snr_records])

read_length_vec_saved = np.array(sorted(np.unique(read_lengths)))
read_pulse_gain_vec_saved = np.array(sorted(np.unique(read_pulse_gains)))
snr_grid = np.full((read_length_vec_saved.size, read_pulse_gain_vec_saved.size), np.nan)
qnd_grid_saved = np.full((read_length_vec_saved.size, read_pulse_gain_vec_saved.size), np.nan)

for length_idx, read_length in enumerate(read_length_vec_saved):
    for gain_idx, read_pulse_gain in enumerate(read_pulse_gain_vec_saved):
        matching_points = (
            np.isclose(read_lengths, read_length)
            & (read_pulse_gains == read_pulse_gain)
        )
        if np.any(matching_points):
            snr_grid[length_idx, gain_idx] = np.mean(snr_values[matching_points])
            qnd_grid_saved[length_idx, gain_idx] = np.mean(qnd_values[matching_points])

snr_grid_norm = snr_grid / np.nanmax(snr_grid)
qnd_grid_norm = qnd_grid_saved
combined_snr_qnd_grid = snr_grid_norm * qnd_grid_norm

gain_mesh, length_mesh = np.meshgrid(read_pulse_gain_vec_saved, read_length_vec_saved)

finite_product_indices = np.argwhere(np.isfinite(combined_snr_qnd_grid))
finite_product_values = combined_snr_qnd_grid[np.isfinite(combined_snr_qnd_grid)]
top_count = min(5, finite_product_values.size)
top_product_points = []

if top_count > 0:
    top_order = np.argsort(finite_product_values)[-top_count:][::-1]
    for order_idx in top_order:
        length_idx, gain_idx = finite_product_indices[order_idx]
        top_product_points.append({
            "read_length": read_length_vec_saved[length_idx],
            "read_pulse_gain": read_pulse_gain_vec_saved[gain_idx],
            "product": combined_snr_qnd_grid[length_idx, gain_idx],
            "snr": snr_grid[length_idx, gain_idx],
            "qnd": qnd_grid_saved[length_idx, gain_idx],
        })

fig, axs = plt.subplots(1, 3, figsize=(18, 5), sharex=True, sharey=True)

mesh_snr = axs[0].pcolormesh(gain_mesh, length_mesh, snr_grid, shading="auto")
axs[0].scatter(read_pulse_gains, read_lengths, c="k", s=8, alpha=0.5)
axs[0].set_title("GMM SNR")
axs[0].set_xlabel("Read Pulse Gain (DAC units)")
axs[0].set_ylabel("Read Length")
fig.colorbar(mesh_snr, ax=axs[0], label="Distance / Shared Sigma")

mesh_qnd = axs[1].pcolormesh(gain_mesh, length_mesh, qnd_grid_norm, shading="auto")
axs[1].scatter(read_pulse_gains, read_lengths, c="k", s=8, alpha=0.5)
axs[1].set_title("QND")
axs[1].set_xlabel("Read Pulse Gain (DAC units)")
fig.colorbar(mesh_qnd, ax=axs[1], label="QND Normalized")

mesh_product = axs[2].pcolormesh(gain_mesh, length_mesh, combined_snr_qnd_grid, shading="auto")
axs[2].scatter(read_pulse_gains, read_lengths, c="k", s=8, alpha=0.5)
for rank, point in enumerate(top_product_points, start=1):
    axs[2].scatter(
        point["read_pulse_gain"],
        point["read_length"],
        facecolors="none",
        edgecolors="red",
        s=120,
        linewidths=2,
    )
    axs[2].scatter(
        point["read_pulse_gain"],
        point["read_length"],
        marker="*",
        c="red",
        s=90,
    )
    axs[2].text(
        point["read_pulse_gain"],
        point["read_length"],
        str(rank),
        color="red",
        fontsize=9,
        fontweight="bold",
        ha="center",
        va="center",
    )
axs[2].set_title("SNR Norm x QND Norm")
axs[2].set_xlabel("Read Pulse Gain (DAC units)")
fig.colorbar(mesh_product, ax=axs[2], label="Product")

plt.suptitle("QND Readout Sweep GMM SNR Summary")
plt.tight_layout()
summary_plot_path = os.path.join(qnd_sweep_folder, "qnd_gmm_snr_qnd_product_summary.png")
plt.savefig(summary_plot_path, dpi=300, bbox_inches="tight")
plt.show()

print("Found", len(snr_records), "QND files.")
print("Top product points:")
for rank, point in enumerate(top_product_points, start=1):
    print(
        rank,
        "read_length =",
        point["read_length"],
        "read_pulse_gain =",
        point["read_pulse_gain"],
        "product =",
        point["product"],
        "snr =",
        point["snr"],
        "qnd =",
        point["qnd"],
    )
print("Saved plot to:", summary_plot_path)

# %%
# TITLE : Plot GMM SNR only where QND is greater than 90 percent
from scipy.ndimage import gaussian_filter

qnd_threshold = 0
qnd_smoothing_sigma = 1.0

snr_qnd_threshold_grid = np.where(qnd_grid_saved > qnd_threshold, snr_grid, np.nan)
snr_qnd_threshold_grid = np.ma.masked_invalid(snr_qnd_threshold_grid)

valid_qnd_points = np.isfinite(qnd_grid_saved)
if np.any(valid_qnd_points):
    qnd_fill_value = np.nanmean(qnd_grid_saved[valid_qnd_points])
    qnd_grid_filled = np.where(valid_qnd_points, qnd_grid_saved, qnd_fill_value)
    qnd_weight_grid = valid_qnd_points.astype(float)

    qnd_smooth_numerator = gaussian_filter(qnd_grid_filled * qnd_weight_grid, sigma=qnd_smoothing_sigma)
    qnd_smooth_denominator = gaussian_filter(qnd_weight_grid, sigma=qnd_smoothing_sigma)
    qnd_grid_smooth = qnd_smooth_numerator / np.maximum(qnd_smooth_denominator, 1e-12)
    qnd_grid_smooth = np.clip(qnd_grid_smooth, 0, 1)
else:
    raise RuntimeError("No finite QND values found for contour plot.")

plt.figure(figsize=(8, 6))
mesh = plt.pcolormesh(
    gain_mesh,
    length_mesh,
    snr_qnd_threshold_grid,
    shading="auto",
)
# plt.scatter(read_pulse_gains, read_lengths, c="k", s=8, alpha=0.35)

qnd_min = np.nanmin(qnd_grid_smooth)
qnd_max = np.nanmax(qnd_grid_smooth)
qnd_contour_levels = [0.80, 0.85, 0.90, 0.91,0.92, 0.93, 0.95, 0.99]
# qnd_contour_levels = [
#     level for level in qnd_contour_levels
#     if qnd_min <= level <= qnd_max
# ]
if len(qnd_contour_levels) > 0:
    contours = plt.contour(
        gain_mesh,
        length_mesh,
        qnd_grid_smooth,
        levels=qnd_contour_levels,
        colors="black",
        linewidths=1.2,
    )
    plt.clabel(contours, inline=True, fontsize=8, fmt=lambda value: f"{100 * value:.0f}%")

# if qnd_min <= qnd_threshold <= qnd_max:
#     threshold_contour = plt.contour(
#         gain_mesh,
#         length_mesh,
#         qnd_grid_smooth,
#         levels=[qnd_threshold],
#         colors="red",
#         linewidths=2.0,
#     )
#     plt.clabel(threshold_contour, inline=True, fontsize=9, fmt=lambda value: f"{100 * value:.0f}%")

plt.xlabel("Read Pulse Gain (DAC units)")
plt.ylabel("Read Length")
plt.title("GMM SNR Where QND > "+str(qnd_threshold*100)+ " with Smoothed QND Contours")
plt.colorbar(mesh, label="GMM SNR")
plt.tight_layout()
snr_qnd_contour_plot_path = os.path.join(qnd_sweep_folder, "qnd_snr_above_" + str(qnd_threshold*100)+"_with_qnd_contours.png")
plt.savefig(snr_qnd_contour_plot_path, dpi=300, bbox_inches="tight")
plt.show()

print("Saved plot to:", snr_qnd_contour_plot_path)
