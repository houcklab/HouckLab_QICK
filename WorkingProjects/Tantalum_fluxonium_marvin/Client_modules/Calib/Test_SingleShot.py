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
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mSpecSlice_PS_sse import SpecSlice_PS_sse

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
    "yokoVoltage": 0.0113,#1.6,

    # cavity
    "read_pulse_style": "const",  # --Fixed
    "read_length": 30,  # us
    "read_pulse_gain": 6000,  # [DAC units]
    "read_pulse_freq": 6671.695,#509,#7391.96,#7392.36,#957,
    "mode_periodic": False,

    # MIST
    "pop_pulse_gain":0,
    "pop_pulse_length": .01,
    "depop_delay": .010, # 5/kappa

    # qubit spec
    "qubit_pulse_style": "const",
    "qubit_gain": 4000,
    "qubit_length": 20,  ###us, this is used if pulse style is const
    "sigma": 1,  ### units us
    "flat_top_length": 5,  ### in us
    "qubit_freq": 1470,
    "relax_delay": 30,
    'qubit_mode_periodic' : False,

    # define shots
    "shots": 50000,  ### this gets turned into "reps"
    "cen_num": 2,
    "keys": ['kl'],
    # Added for switch
    "use_switch": False,

}
config = BaseConfig | UpdateConfig

yoko1.SetVoltage(config["yokoVoltage"])
#%% Basic Single Shot
plt.close('all')
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
    "yokoVoltage": 0.01,
    'yokoVoltage_freqPoint': 0.01,

    # Readout
    "read_pulse_style": "const",
    "read_length": 30,
    "read_pulse_gain": 5000,
    "read_pulse_freq": 6671.695,

    # Qubit Tone
    "qubit_freq_start": 1450,
    "qubit_freq_stop": 1580,
    "RabiNumPoints": 51,
    "qubit_pulse_style": "const",
    "sigma": 0.1,
    "flat_top_length": 10,
    'qubit_length': 2,
    "relax_delay": 10,
    "initialize_qubit_gain" : 10000,
    "qubit_freq_base": 1470,

    # amplitude rabi parameters
    "qubit_gain_start": 0,
    "qubit_gain_step": 800,
    "qubit_gain_expts": 21,

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
    "yokoVoltage": -0.1085,

    # Readout
    "read_pulse_style": "const",  # --Fixed
    "read_length": 35,  # us
    "read_pulse_gain": 5200,  # [DAC units]
    "read_pulse_freq": 6672.635,#7391.996,

    # Qubit g-e initialization
    "qubit_pulse_style": "const",
    "qubit_gain": 25000,
    "qubit_length": 0.04,
    "sigma": 1,
    "flat_top_length": 20,
    "qubit_freq": 156,

    # Qubit e-f initialization,
    "use_two_pulse": False,  # If this is False the other values dont matter
    "qubit_ef_gain": 0,
    "qubit_ef_freq": 1991,

    # Experiment
    "relax_delay": 10,
    "shots": 30000,
    "wait_start": 0,
    "wait_stop": 2000,
    "wait_num": 21,
    "use_switch": False,
    "wait_type":"linear",

    # Analysis
    "cen_num": 2,
    'fridge_temp': 20,
    'yokoVoltage_freqPoint' : -0.1085,

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
UpdateConfig = {
    ##### set yoko
    "yokoVoltage": -0.1094,
    ###### cavity
    #"reps": 0,  # this line does nothing, is overwritten with "shots"
    "read_pulse_style": "const", # --Fixed
    "read_length": 40, # [Clock ticks]
    "read_pulse_gain": 5200, # [DAC units]
    "read_pulse_freq": 6672.634, # [MHz]
    ##### qubit spec parameters
    "qubit_pulse_style": "const",
    "qubit_gain": 12500, #22000,
    "qubit_length": 0.04,  ###us, this is used if pulse style is const
    "sigma": 0.150,  ### units us, define a 20ns sigma
    # "flat_top_length": 0.150,
    "qubit_freq": 164,
    "relax_delay": 200,  ### turned into us inside the run function
    #### define shots
    "shots": 25000, ### this gets turned into "reps"
    ### define the wait times
    "wait_start": 0.0,
    "wait_stop": 0.25,
    "wait_num": 31,
    ##### define number of clusters to use
    "cen_num": 2,
    "pre_pulse": True,
}
config = BaseConfig | UpdateConfig

yoko1.SetVoltage(config["yokoVoltage"])
print('starting scan: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))

Instance_T2R_PS = T2R_PS(path="dataTestT2R_PS", outerFolder=outerFolder, cfg=config,
                                               soc=soc, soccfg=soccfg)
data_T2R_PS = T2R_PS.acquire(Instance_T2R_PS)
T2R_PS.save_data(Instance_T2R_PS, data_T2R_PS)
T2R_PS.save_config(Instance_T2R_PS)

print('end of scan: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))

#%%
# TITLE: Single Shot Optimize
UpdateConfig = {
    # define yoko
    "yokoVoltage": 0.04,

    # cavity
    "read_pulse_style": "const",  # --Fixed
    "read_length": 30,  # us
    "read_pulse_gain": 5000,  # [DAC units]
    "read_pulse_freq": 6671.805,
    "mode_periodic" : False,

    # qubit spec
    "qubit_pulse_style": "const",
    "qubit_ge_gain": 25000,
    "qubit_ef_gain": 1,
    "qubit_ge_freq": 1345,
    "qubit_ef_freq": 110,
    "apply_ge": True,
    "apply_ef": False,
    "qubit_length": 20,
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
    "read_pulse_freq" : (config["read_pulse_freq"] - 0.05, config["read_pulse_freq"] + 0.05 ),
    'read_length': (10, 70),
    'read_pulse_gain': (4000, 20000)
}
step_size = {
    "read_pulse_freq" : 0.005,
    'read_length': 10,
    'read_pulse_gain': 1000,
}
keys = ["read_pulse_freq"]


config["shots"] = 40000
inst_singleshotopt = SingleShotMeasure(path="SingleShotOpt_vary_WTF", outerFolder=outerFolder, cfg=config,
                                       soc=soc, soccfg=soccfg, fast_analysis=True)
opt_param = inst_singleshotopt.brute_search( keys, param_bounds, step_size, )
inst_singleshotopt.display_opt()
print(opt_param)

#%%

# TITLE : Perform the spec slice with Post Selection
UpdateConfig = {
    # cavity
    "read_pulse_style": "const",
    "read_length": 40,
    "read_pulse_gain": 5200,
    "read_pulse_freq": 6672.635,  # 6253.8,

    "qubit_pulse_style": "const",  # Constant pulse
    "qubit_gain": 20000,  # [DAC Units]
    'sigma': 2,
    'flat_top_length': 2,
    "qubit_length": 1,  # [us]

    # Define spec slice experiment parameters
    "qubit_freq_start": 145,
    "qubit_freq_stop": 180,
    "SpecNumPoints": 31,  # Number of points
    "delay_btwn_pulses": 0.05,

    # Define the yoko voltage
    "yokoVoltage": -0.1094,
    "relax_delay": 200,  # [us] Delay post one experiment
    'use_switch': False, # This is for turning off the heating tone
    'mode_periodic': False,
    'ro_periodic': False,

    'spec_reps': 6000,  # Converted to shots
    'initialize_pulse': True,
    'initialize_qubit_gain': 20000,
    'fridge_temp': 420,
    'qubit_freq_base': 120,
}
config = BaseConfig | UpdateConfig
yoko1.SetVoltage(config["yokoVoltage"])
inst_specslice = SpecSlice_PS_sse(path="dataTestSpecSlice_PS", cfg=config,
                                  soc=soc, soccfg=soccfg, outerFolder=outerFolder)
data_specSlice_PS = inst_specslice.acquire()
data_specSlice_PS = inst_specslice.process_data(data=data_specSlice_PS)
inst_specslice.display(data=data_specSlice_PS, plotDisp=True)
inst_specslice.save_data(data_specSlice_PS)
#%%
# TITLE : T2 vs flux using post-selection
from tqdm import tqdm

outerFolder = "Z:\\TantalumFluxonium\\Data\\2025_07_25_cooldown\\QCage_dev\\T2vsFlux_30Dec_1534\\"
yokoVoltages = np.linspace(-0.1094, -0.1074, 21)

UpdateConfig_spec_ps = {
    # cavity
    "read_pulse_style": "const",
    "read_length": 40,
    "read_pulse_gain": 5200,
    "read_pulse_freq": 6672.635,  # 6253.8,

    "qubit_pulse_style": "const",  # Constant pulse
    "qubit_gain": 5000,  # [DAC Units]
    'sigma': 2,
    'flat_top_length': 2,
    "qubit_length": 1,  # [us]

    # Define spec slice experiment parameters
    "qubit_freq_start": 145,
    "qubit_freq_stop": 180,
    "SpecNumPoints": 31,  # Number of points
    "delay_btwn_pulses": 0.05,

    # Define the yoko voltage
    "yokoVoltage": -0.1094,
    "relax_delay": 200,  # [us] Delay post one experiment
    'use_switch': False, # This is for turning off the heating tone
    'mode_periodic': False,
    'ro_periodic': False,

    'spec_reps': 6000,  # Converted to shots
    'initialize_pulse': True,
    'initialize_qubit_gain': 20000,
    'fridge_temp': 420,
    'qubit_freq_base': 160,
}
config_spec_ps = BaseConfig | UpdateConfig_spec_ps

UpdateConfig_t2_ps = {
    ##### set yoko
    "yokoVoltage": -0.1094,
    ###### cavity
    #"reps": 0,  # this line does nothing, is overwritten with "shots"
    "read_pulse_style": "const", # --Fixed
    "read_length": 40, # [Clock ticks]
    "read_pulse_gain": 5200, # [DAC units]
    "read_pulse_freq": 6672.634, # [MHz]
    ##### qubit spec parameters
    "qubit_pulse_style": "const",
    "qubit_gain": 12500, #22000,
    "qubit_length": 0.04,  ###us, this is used if pulse style is const
    "sigma": 0.150,  ### units us, define a 20ns sigma
    # "flat_top_length": 0.150,
    "qubit_freq": 164,
    "relax_delay": 200,  ### turned into us inside the run function
    #### define shots
    "shots": 25000, ### this gets turned into "reps"
    ### define the wait times
    "wait_start": 0.0,
    "wait_stop": 0.25,
    "wait_num": 31,
    ##### define number of clusters to use
    "cen_num": 2,
    "pre_pulse": True,
}
config_t2_ps = BaseConfig | UpdateConfig_t2_ps

qubit_freq_ps_list = []
t2_list = []
t2_err_list = []
qubit_freq_fringe_corr_list = []
fringe_Freq_list = []

#%%
for i in range(yokoVoltages.shape[0]):

    outerFolder_yoko = outerFolder + f"Yoko_{yokoVoltages[i]:.4f}\\"

    print("Starting for yoko voltage:", yokoVoltages[i])
    # First run the spec slice to find the qubit frequency
    config_spec_ps['yokoVoltage'] = yokoVoltages[i]
    config_t2_ps['yokoVoltage'] = yokoVoltages[i]
    yoko1.SetVoltage(yokoVoltages[i])
    inst_specslice = SpecSlice_PS_sse(path="SpecSlice_PS", cfg=config_spec_ps,
                                      soc=soc, soccfg=soccfg, outerFolder=outerFolder_yoko)
    data_specSlice_PS = inst_specslice.acquire()
    data_specSlice_PS = inst_specslice.process_data(data=data_specSlice_PS)
    inst_specslice.save_data(data_specSlice_PS)
    qubit_freq = data_specSlice_PS['data']['resonant_freq']
    qubit_freq_ps_list.append(qubit_freq)

    # Now run the T2 experiment at the found qubit frequency
    config_t2_ps['qubit_freq'] = qubit_freq + 5  # Slightly detuned
    yoko1.SetVoltage(config_t2_ps["yokoVoltage"])
    Instance_T2R_PS = T2R_PS(path="T2R_PS", outerFolder=outerFolder_yoko, cfg=config_t2_ps,
                                                     soc=soc, soccfg=soccfg)
    data_T2R_PS = T2R_PS.acquire(Instance_T2R_PS)
    T2R_PS.save_data(Instance_T2R_PS, data_T2R_PS)
    T2R_PS.save_config(Instance_T2R_PS)
    t2 = np.average(data_T2R_PS['data']['T2'], weights=np.array(data_T2R_PS['data']['T2_err'])**2)
    t2_err = np.sqrt(1/np.sum(1/np.array(data_T2R_PS['data']['T2_err'])**2))
    fringe_freq = np.mean(data_T2R_PS['data']['fringefreq'])
    qubit_freq_fringe_corr = config_t2_ps['qubit_freq'] - fringe_freq
    t2_list.append(t2)
    t2_err_list.append(t2_err)
    fringe_Freq_list.append(fringe_freq)
    qubit_freq_fringe_corr_list.append(qubit_freq_fringe_corr)
    print(f"Yoko: {yokoVoltages[i]:.4f}, Qubit Freq: {qubit_freq:.2f}, T2: {t2:.2f} +/- {t2_err:.2f}, Fringe Freq: {fringe_freq:.2f}")
#%%
# Collating the data
collated_data = {
    'yokoVoltages': yokoVoltages,
    'qubit_freqs': qubit_freq_ps_list,
    't2_values': t2_list,
    't2_errors': t2_err_list,
    'fringe_freqs': fringe_Freq_list,
    'qubit_freqs_fringe_corrected': qubit_freq_fringe_corr_list
}

# Saving the collated data using h5
import h5py
savepath = outerFolder + "T2vsFlux_collated_data.h5"
with h5py.File(savepath, 'w') as hf:
    for key, value in collated_data.items():
        hf.create_dataset(key, data=value)

print("Collated data saved at:", savepath)

# Plotting T2 vs Yoko Voltage
# Plot all the data
import numpy as np
import matplotlib.pyplot as plt
def make_pretty(ax, xlabel, ylabel, title=None):
    ax.set_xlabel(xlabel, fontsize=12)
    ax.set_ylabel(ylabel, fontsize=12)
    if title:
        ax.set_title(title, fontsize=14)
    ax.grid(True, alpha=0.3)
    ax.tick_params(axis="both", labelsize=10)


def save_fig(fig, name):
    os.makedirs(outerFolder, exist_ok=True)
    fig.tight_layout()
    fig.savefig(os.path.join(outerFolder, f"{name}.png"), dpi=300)
    fig.savefig(os.path.join(outerFolder, f"{name}.pdf"))


# Fig 1 : Qubit Frequency vs Yoko Voltage
fig, ax = plt.subplots(figsize=(6, 4))
ax.plot(collated_data['yokoVoltages'], collated_data['qubit_freqs'], marker='o', linestyle='-')
make_pretty(ax, "Yoko Voltage (V)", "Qubit Frequency (MHz)", "Qubit Frequency using Spec PS vs Yoko Voltage")
save_fig(fig, "QubitFreqSpec_vs_YokoVoltage")

# Fig 2 : T2 vs Yoko Voltage
fig, ax = plt.subplots(figsize=(6, 4))
ax.errorbar(collated_data['yokoVoltages'], collated_data['t2_values'], yerr=collated_data['t2_errors'],
            marker='o', linestyle='-', capsize=5)
make_pretty(ax, "Yoko Voltage (V)", "T2 (us)", "T2 using Post Selection vs Yoko Voltage")
save_fig(fig, "T2_PS_vs_YokoVoltage")

# Fig 3 : Fringe Frequency vs Yoko Voltage
fig, ax = plt.subplots(figsize=(6, 4))
ax.plot(collated_data['yokoVoltages'], collated_data['fringe_freqs'], marker='o', linestyle='-')
make_pretty(ax, "Yoko Voltage (V)", "Fringe Frequency (MHz)", "Fringe Frequency vs Yoko Voltage")
save_fig(fig, "FringeFreq_vs_YokoVoltage")

# Fig 4 : Qubit Frequency (fringe corrected) vs Yoko Voltage
fig, ax = plt.subplots(figsize=(6, 4))
ax.plot(collated_data['yokoVoltages'], collated_data['qubit_freqs_fringe_corrected'], marker='o', linestyle='-')
make_pretty(ax, "Yoko Voltage (V)", "Qubit Frequency (MHz)", "Qubit Frequency (fringe corrected) vs Yoko Voltage")
save_fig(fig, "QubitFreq_fringeCorrected_vs_YokoVoltage")

plt.show()
#%%


