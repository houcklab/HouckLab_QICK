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
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mSingleShotProgram import SingleShotProgram
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mSingleShotProgram_switch import \
    SingleShot_SwitchProgram
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mSingleShot_2Dsweep import SingleShot_2Dsweep
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mT1_ThermalPS import T1_ThermalPS
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mT1_ThermalPS_withERROR import T1_ThermalPS_Err
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mT1_PS_sse import T1_PS_sse
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mT2R_PS import T2R_PS
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mSingleShotPS import SingleShotPS
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mAmplitudeRabiBlob_PS_sse import AmplitudeRabi_PS_sse
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mAmplitudeRabiFlux_PS import AmplitudeRabiFlux_PS
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mSingleShotTemp_sse import SingleShotSSE
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mRepeatReadout import RepeatReadout
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mSingleShotOptimize import SingleShotMeasure

from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mSingleShotMIST import SingleShotMISTMeasure

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
# %%
# TITLE: Basic Single Shot Experiment
UpdateConfig = {
    # define yoko
    "yokoVoltage": -0.1205,#1.6,

    # cavity
    "read_pulse_style": "const",  # --Fixed
    "read_length": 30,  # us
    "read_pulse_gain": 9000,  # [DAC units]
    "read_pulse_freq": 6671.25,#509,#7391.96,#7392.36,#957,
    "mode_periodic": False,

    # MIST
    "pop_pulse_gain":0,
    "pop_pulse_length": .01,
    "depop_delay": .010, # 5/kappa

    # qubit spec
    "qubit_pulse_style": "const",
    "qubit_gain": 15000,
    "qubit_length": 1,  ###us, this is used if pulse style is const
    "sigma": 1,  ### units us
    "flat_top_length": 5,  ### in us
    "qubit_freq": 1010,
    "relax_delay": 1000,
    'qubit_mode_periodic' : False,

    # define shots
    "shots": 10000,  ### this gets turned into "reps"
    "cen_num": 2,
    "keys": ['kl'],
    # Added for switch
    "use_switch": False,

}
config = BaseConfig | UpdateConfig

yoko1.SetVoltage(config["yokoVoltage"])
#%% Basic Single Shot
# plt.close('all')
scan_time = (config["relax_delay"] * config["shots"] * 2) * 1e-6 / 60

print('estimated time: ' + str(round(scan_time, 2)) + ' minutes')

Instance_SingleShotProgram = SingleShotProgram(path="dataTestSingleShotProgram", outerFolder=outerFolder, cfg=config,
                                               soc=soc, soccfg=soccfg)
data_SingleShot = SingleShotProgram.acquire(Instance_SingleShotProgram)
SingleShotProgram.display(Instance_SingleShotProgram, data_SingleShot, plotDisp=True, save_fig=True)
SingleShotProgram.save_data(Instance_SingleShotProgram, data_SingleShot)
SingleShotProgram.save_config(Instance_SingleShotProgram)
plt.show()

#%%
outerFolder_sweep = outerFolder + "singleShotSweeps_read_pulse_freq_950\\"
loop_len = 21
param_dict = {
    'read_pulse_freq': config["read_pulse_freq"] + np.linspace(-0.5, 0.5, 51),
    'qubit_freq': config["qubit_freq"] + np.linspace(-50, 50, 21),
    'qubit_gain': np.linspace(15000, 22000, 21, dtype=int),
    'read_pulse_gain': np.linspace(5000, 30000, 51, dtype=int),
    'read_length':np.linspace(1,20,20, dtype=int)
}
vary = "read_pulse_freq"
fid = []

for idx in range(param_dict[vary].shape[0]):
    config[vary] = param_dict[vary][idx]
    Instance_SingleShotProgram = SingleShotProgram(path="SingleShot_sweeps_yoko_"+str(config["yokoVoltage"]), outerFolder=outerFolder_sweep, cfg=config,soc=soc,soccfg=soccfg)
    data_SingleShot = SingleShotProgram.acquire(Instance_SingleShotProgram)
    SingleShotProgram.display(Instance_SingleShotProgram, data_SingleShot, plotDisp=False, save_fig=True)
    SingleShotProgram.save_data(Instance_SingleShotProgram, data_SingleShot)
    SingleShotProgram.save_config(Instance_SingleShotProgram)
    fid.append(Instance_SingleShotProgram.fid)
    plt.clf()
    print(idx)

# Plot the fidelity vs the varying parameter
plt.figure(figsize=(10, 6))
plt.plot(param_dict[vary], fid, marker='o', linestyle='-', color='b')
plt.xlabel(vary)
plt.ylabel('Fidelity')
plt.title('Fidelity vs ' + vary)
plt.grid()
plt.show()


#%% TITLE Single Shot MIST
plt.close('all')
scan_time = (config["relax_delay"] * config["shots"] * 2) * 1e-6 / 60

print('estimated time: ' + str(round(scan_time, 2)) + ' minutes')

# Run experiment
inst_singleshotMIST = SingleShotMISTMeasure(path="SingleShotMIST", outerFolder=outerFolder, cfg=config,
                                       soc=soc, soccfg=soccfg, fast_analysis=True)
data_singleshotMIST = inst_singleshotMIST.acquire()
data_singleshotMIST = inst_singleshotMIST.process(data=data_singleshotMIST)
inst_singleshotMIST.save_data(data_singleshotMIST)
inst_singleshotMIST.save_config()

print(data_singleshotMIST['data']['mean'])

#%% TITLE Single Shot MIST Sweep Power
datetimenow = datetime.datetime.now()
datetimestring = datetimenow.strftime("%Y_%m_%d_%H_%M_%S")
outerFolderSweep = f"{outerFolder}\\SingleShotMISTSweep\\{datetimestring}\\"
#os.mkdir(sweeppath)

num_steps = 21
pop_gains_vec = np.linspace(0,30000,num_steps)
blob_populations = np.zeros((config['cen_num'], num_steps))

for idx in range(num_steps):
    UpdateConfig['pop_pulse_gain'] = int(pop_gains_vec[idx])
    config = BaseConfig | UpdateConfig
    print("idx is",idx)
    #print(config['pop_pulse_gain'])
    if idx == 0:
        inst_singleshotMIST = SingleShotMISTMeasure(path="Sweep", outerFolder=outerFolderSweep, cfg=config,
                                                    soc=soc, soccfg=soccfg, fast_analysis=True)
        data_singleshotMIST = inst_singleshotMIST.acquire()
        data_singleshotMIST = inst_singleshotMIST.process(data=data_singleshotMIST)
        precalc_centers = inst_singleshotMIST.centers

    else:
        # If not the first run, pass in the previous fits for the centers
        inst_singleshotMIST = SingleShotMISTMeasure(path="Sweep", outerFolder=outerFolderSweep, cfg=config,
                                                    soc=soc, soccfg=soccfg, centers = precalc_centers, fast_analysis=True)
        data_singleshotMIST = inst_singleshotMIST.acquire()
        data_singleshotMIST = inst_singleshotMIST.process(data=data_singleshotMIST)


    # Save the populations after each step
    blob_populations[0,idx] = data_singleshotMIST['data']['mean'][0]
    blob_populations[1, idx] = data_singleshotMIST['data']['mean'][1]

fname_fig = f"V={config['yokoVoltage']}_ReadGain={config['read_pulse_gain']}_ReadLength={config['read_length']}_PopPulseLength={config['pop_pulse_length']}_DepopDelay={config['depop_delay']}"

plt.figure(figsize=(10, 10))
plt.scatter(pop_gains_vec, blob_populations[0,:],label='0')
plt.scatter(pop_gains_vec, blob_populations[1,:],label='1')
plt.xlabel("Pulse Amplitude (DAC)")
plt.ylabel("Population")
plt.legend()
plt.title(fname_fig)
plt.show()

savepath = f"{inst_singleshotMIST.path_only}\\{fname_fig}"
plt.savefig(f"{savepath}.png")
print("Saved in ",savepath)

#%% TITLE Single Shot MIST Sweep Pulse Length
datetimenow = datetime.datetime.now()
datetimestring = datetimenow.strftime("%Y_%m_%d_%H_%M_%S")
outerFolderSweep = f"{outerFolder}\\SingleShotMISTSweep\\{datetimestring}\\"
#os.mkdir(sweeppath)

num_steps = 5
pop_pulse_length_vec = np.linspace(10,100,num_steps)
blob_populations = np.zeros((config['cen_num'], num_steps))

for idx in range(num_steps):
    UpdateConfig['pop_pulse_length'] = int(pop_pulse_length_vec[idx])
    config = BaseConfig | UpdateConfig
    print("idx is",idx)
    #print(config['pop_pulse_gain'])
    if idx == 0:
        inst_singleshotMIST = SingleShotMISTMeasure(path="Sweep", outerFolder=outerFolderSweep, cfg=config,
                                                    soc=soc, soccfg=soccfg, fast_analysis=True)
        data_singleshotMIST = inst_singleshotMIST.acquire()
        data_singleshotMIST = inst_singleshotMIST.process(data=data_singleshotMIST)
        precalc_centers = inst_singleshotMIST.centers

    else:
        # If not the first run, pass in the previous fits for the centers
        inst_singleshotMIST = SingleShotMISTMeasure(path="Sweep", outerFolder=outerFolderSweep, cfg=config,
                                                    soc=soc, soccfg=soccfg, centers = precalc_centers, fast_analysis=True)
        data_singleshotMIST = inst_singleshotMIST.acquire()
        data_singleshotMIST = inst_singleshotMIST.process(data=data_singleshotMIST)


    # Save the populations after each step
    blob_populations[0,idx] = data_singleshotMIST['data']['mean'][0]
    blob_populations[1, idx] = data_singleshotMIST['data']['mean'][1]

fname_fig = f"V={config['yokoVoltage']}_ReadGain={config['read_pulse_gain']}_ReadLength={config['read_length']}_PopPulseLength={config['pop_pulse_length']}_DepopDelay={config['depop_delay']}"

plt.figure(figsize=(10, 10))
plt.scatter(pop_pulse_length_vec, blob_populations[0,:],label='0')
plt.scatter(pop_pulse_length_vec, blob_populations[1,:],label='1')
plt.xlabel("Pulse Length")
plt.ylabel("Population")
plt.legend()
plt.title(fname_fig)
plt.show()

savepath = f"{inst_singleshotMIST.path_only}\\{fname_fig}"
plt.savefig(f"{savepath}.png")
print("Saved in ",savepath)

#%%

# TITLE : code for running single shot experiment with post selection
# UpdateConfig = {
#     ##### set yoko
#     "yokoVoltage": -2.4,
#     ###### cavity
#     # "reps": 2000,  # this will be used for all experiments below unless otherwise changed in between trials
#     "read_pulse_style": "const",  # --Fixed
#     "read_length": 10,  # us
#     "read_pulse_gain": 7000,  # [DAC units]
#     "read_pulse_freq": 6437.55 - 0.3,  # [MHz]
#     ##### qubit spec parameters
#     "qubit_pulse_style": "arb",
#     "qubit_gain": 5000,
#     # "qubit_length": 10,  ###us, this is used if pulse style is const
#     # "flat_top_length": 0.900, ### in us
#     "sigma": 0.100,  ### units us, define a 20ns sigma
#     "qubit_freq": 3948.5,
#     "relax_delay": 10,  ### turned into us inside the run function
#     #### define shots
#     "shots": 50000,  ### this gets turned into "reps"
#     #### define info for clustering
#     "cen_num": 3,
# }
# config = BaseConfig | UpdateConfig
#
# yoko1.SetVoltage(config["yokoVoltage"])
# Instance_SingleShotPS = SingleShotPS(path="dataTestSingleShotPS", outerFolder=outerFolder, cfg=config,
#                                      soc=soc, soccfg=soccfg)
# data_SingleShotPS = SingleShotPS.acquire(Instance_SingleShotPS)
# # SingleShotPS.display(Instance_SingleShotPS, data_SingleShotPS, plotDisp=True, save_fig=True)
# SingleShotPS.save_data(Instance_SingleShotPS, data_SingleShotPS)
# SingleShotPS.save_config(Instance_SingleShotPS)
#%%
# TITLE : code for running Amplitude rabi Blob with post selection
UpdateConfig = {
    "yokoVoltage": -0.1205,
    'yokoVoltage_freqPoint': -0.1285,

    # Readout
    "read_pulse_style": "const",
    "read_length": 35,
    "read_pulse_gain": 11000,
    "read_pulse_freq": 6671.25,

    # Qubit Tone
    "qubit_freq_start": 900,
    "qubit_freq_stop": 1100,
    "RabiNumPoints": 41,
    "qubit_pulse_style": "const",
    "sigma": 0.1,
    "flat_top_length": 10,
    'qubit_length': 0.5,
    "relax_delay": 10,
    "initialize_qubit_gain" : 30000,
    "qubit_freq_base": 1010,

    # amplitude rabi parameters
    "qubit_gain_start": 1000,
    "qubit_gain_step": 3000,
    "qubit_gain_expts": 11,

    # define number of clusters to use
    "cen_num": 2,
    "shots": 10000,
    "use_switch": False,
    'initialize_pulse': True,
    'fridge_temp': 10,

}
config = BaseConfig | UpdateConfig

yoko1.SetVoltage(config["yokoVoltage"])

#%%
Instance_AmplitudeRabi_PS = AmplitudeRabi_PS_sse(path="dataTestAmplitudeRabi_PS", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg, progress=True)
data_AmplitudeRabi_PS = AmplitudeRabi_PS_sse.acquire(Instance_AmplitudeRabi_PS)
data_AmplitudeRabi_PS = Instance_AmplitudeRabi_PS.process_data(data_AmplitudeRabi_PS)
AmplitudeRabi_PS_sse.save_data(Instance_AmplitudeRabi_PS, data_AmplitudeRabi_PS)
AmplitudeRabi_PS_sse.save_config(Instance_AmplitudeRabi_PS)
Instance_AmplitudeRabi_PS.display(plotDisp=True, data=data_AmplitudeRabi_PS)

#%%
# TITLE: T1 of a thermal state using pulses
UpdateConfig = {

    # Define yoko
    "yokoVoltage": -0.1015,

    # Readout
    "read_pulse_style": "const",  # --Fixed
    "read_length": 20,  # us
    "read_pulse_gain": 5000,  # [DAC units]
    "read_pulse_freq": 6672.535,#7391.996,

    # Qubit g-e initialization
    "qubit_pulse_style": "const",
    "qubit_gain": 2000,
    "qubit_length": 4,
    "sigma": 1,
    "flat_top_length": 20,
    "qubit_freq": 155,

    # Qubit e-f initialization,
    "use_two_pulse": False,  # If this is False the other values dont matter
    "qubit_ef_gain": 0,
    "qubit_ef_freq": 1991,

    # Experiment
    "relax_delay": 10,
    "shots": 15000,
    "wait_start": 0,
    "wait_stop": 5000,
    "wait_num": 15,
    "use_switch": False,
    "wait_type":"linear",

    # Analysis
    "cen_num": 2,
    'fridge_temp': 20,
    'yokoVoltage_freqPoint' : -0.1015,

}
config = BaseConfig | UpdateConfig | SwitchConfig
yoko1.SetVoltage(config["yokoVoltage"])

# %%
print('starting scan: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
scan_time = (np.sum(np.linspace(config["wait_start"], config["wait_stop"], config["wait_num"])) + config[
    "relax_delay"]) * config["shots"] * 1e-6 / 60
print('estimated time: ' + str(round(scan_time, 2)) + ' minutes')

Instance_T1_PS = T1_PS_sse(path="dataTestT1_PS", outerFolder=outerFolder, cfg=config,
                       soc=soc, soccfg=soccfg)
data_T1_PS = T1_PS_sse.acquire(Instance_T1_PS)
T1_PS_sse.save_data(Instance_T1_PS, data_T1_PS)
print('scan complete starting data processing: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
T1_PS_sse.save_config(Instance_T1_PS)
T1_PS_sse.process_data(Instance_T1_PS, data_T1_PS)
Instance_T1_PS.display()
print('end of analysis: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
 # %%

# TITLE code finding T2R of a thermal state using pulses
# UpdateConfig = {
#     ##### set yoko
#     "yokoVoltage": -2.8,
#     ###### cavity
#     #"reps": 0,  # this line does nothing, is overwritten with "shots"
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 5, # [Clock ticks]
#     "read_pulse_gain": 10000, # [DAC units]
#     "read_pulse_freq": 6437.2, # [MHz]
#     ##### qubit spec parameters
#     "qubit_pulse_style": "arb",
#     "qubit_gain": 8000, #22000,
#     # "qubit_length": 10,  ###us, this is used if pulse style is const
#     "sigma": 0.150,  ### units us, define a 20ns sigma
#     # "flat_top_length": 0.150,
#     "qubit_freq": 2034.5 - 1.0,
#     "relax_delay": 100,  ### turned into us inside the run function
#     #### define shots
#     "shots": 6000, ### this gets turned into "reps"
#     ### define the wait times
#     "wait_start": 0.0,
#     "wait_stop": 10.0,
#     "wait_num": 101,
#     ##### define number of clusters to use
#     "cen_num": 3,
#     "pre_pulse": True,
# }
# config = BaseConfig | UpdateConfig
#
# yoko1.SetVoltage(config["yokoVoltage"])
# print('starting scan: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
#
# Instance_T2R_PS = T2R_PS(path="dataTestT2R_PS", outerFolder=outerFolder, cfg=config,
#                                                soc=soc, soccfg=soccfg)
# data_T2R_PS = T2R_PS.acquire(Instance_T2R_PS)
# T2R_PS.save_data(Instance_T2R_PS, data_T2R_PS)
# T2R_PS.save_config(Instance_T2R_PS)
#
# print('end of scan: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))

#%%
# TITLE: Single Shot Optimize
UpdateConfig = {
    # define yoko
    "yokoVoltage": -0.1205,

    # cavity
    "read_pulse_style": "const",  # --Fixed
    "read_length": 25,  # us
    "read_pulse_gain": 11000,  # [DAC units]
    "read_pulse_freq": 6671.25,
    "mode_periodic" : False,

    # qubit spec
    "qubit_pulse_style": "const",
    "qubit_ge_gain": 15000,
    "qubit_ef_gain": 1,
    "qubit_ge_freq": 1010,
    "qubit_ef_freq": 110,
    "apply_ge": True,
    "apply_ef": False,
    "qubit_length": 2,
    "sigma": 0.05,
    "relax_delay": 10,

    # Experiment
    "cen_num": 2,
    "keys": ['kl'],           # Possible keys ["mahalanobis", "bhattacharyya", "kl", "hellinger"]
    "shots": 30000,
    "use_switch": False,

}
config = BaseConfig | UpdateConfig

yoko1.SetVoltage(config["yokoVoltage"])
plt.close('all')
#%%
scan_time = (config["relax_delay"] * config["shots"] ) * 1e-6 / 60

print('estimated time: ' + str(round(scan_time, 2)) + ' minutes')

inst_singleshotopt = SingleShotMeasure(path="dataTestSingleShotOpt", outerFolder=outerFolder, cfg=config,
                                       soc=soc, soccfg=soccfg, fast_analysis = False, disp_image = True)
data_singleshot = inst_singleshotopt.acquire()
inst_singleshotopt.process(data = data_singleshot)
inst_singleshotopt.save_data(data_singleshot)
inst_singleshotopt.save_config()


#%%
# TITLE Running automatic optimization
# config["read_pulse_freq"] = 6248.5
param_bounds ={
    "read_pulse_freq" : (config["read_pulse_freq"] - 0.6, config["read_pulse_freq"]+ 0.1 ),
    'read_length': (10, 70),
    'read_pulse_gain': (4000, 20000)
}
step_size = {
    "read_pulse_freq" : 0.02,
    'read_length': 10,
    'read_pulse_gain': 1000,
}
keys = ["read_pulse_gain"]


config["shots"] = 40000
inst_singleshotopt = SingleShotMeasure(path="SingleShotOpt_vary_WTF", outerFolder=outerFolder, cfg=config,
                                       soc=soc, soccfg=soccfg, fast_analysis=True)
opt_param = inst_singleshotopt.brute_search( keys, param_bounds, step_size, )
inst_singleshotopt.display_opt()
print(opt_param)

#%%

