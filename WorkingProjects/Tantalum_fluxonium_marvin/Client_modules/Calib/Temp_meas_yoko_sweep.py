#%%
import os
import time
import datetime
import numpy as np
import WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.PythonDrivers.LS370 as lk
import pyvisa
import matplotlib.pyplot as plt

from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Calib.initialize import *
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mSingleShotTemp_sse import SingleShotSSE
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mSpecSlice_bkg_subtracted import SpecSlice_bkg_sub
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mQubit_ef_spectroscopy import Qubit_ef_spectroscopy
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mTransmission_SaraTest import  Transmission
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mSpecSlice_PS_sse import SpecSlice_PS_sse
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mAutoCalibrator import CalibratedFlux
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mSingleShotOptimize import SingleShotMeasure
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mQND import QNDmeas
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mT1_PS_sse import T1_PS_sse

# Define the saving path
outerFolder = "Z:\\TantalumFluxonium\\Data\\2024_07_29_cooldown\\QCage_dev\\Magnet_Heat_Check_2\\"

# Defining the standard config files
SwitchConfig = {
    "trig_buffer_start": 0.035, # in us
    "trig_buffer_end": 0.024, # in us
    "trig_delay": 0.07, # in us
}

BaseConfig = BaseConfig | SwitchConfig
#%%
# TITLE: Auto Calibration


# Defining changes to the config
UpdateConfig_cal = {
    # define the yoko voltage
    "yokoVoltageStart": -0.4,
    "yokoVoltageStop": 0.7,
    "yokoVoltageNumPoints": 401,

    # cavity and readout
    "trans_reps": 100,
    "read_pulse_style": "const",
    "read_length": 30,  # us
    "read_pulse_gain": 1500,  # [DAC units]
    "trans_freq_start": 6671.5 - 1.5,  # [MHz]
    "trans_freq_stop": 6671.5 + 1.5,  # [MHz]
    "TransNumPoints": 51,

    # Experiment Parameters
    "relax_delay": 2,
    "flux_quantum": 0.635,
    'use_switch': True,
}
config_cal = BaseConfig | UpdateConfig_cal

#%%
yoko_calibration = CalibratedFlux(path="data_calibration", outerFolder=outerFolder, cfg=config_cal, soc=soc,
                                  soccfg=soccfg)
yoko_calibration.calibrate(dev_name = "6p75_qcage_0729")
yoko_calibration.save_data()
yoko_calibration.display()
config_cal['flux_quantum'] = yoko_calibration.flux_quantum

#%%
# Calibrate for that quantum flux
flux_val = -2.494
config_cal["n_quantum"] = np.floor(flux_val)
config_cal['yokoVoltageStart'] += np.floor(flux_val) * config_cal['flux_quantum']
config_cal['yokoVoltageStop'] += np.floor(flux_val) * config_cal['flux_quantum']
# Pretty Print
print("Starting scan from : " , config_cal["yokoVoltageStart"], " V")
print("Stopping scan at : ", config_cal["yokoVoltageStop"], " V")
print("Flux Quantum is ", config_cal['flux_quantum'], " V")
yoko_calibration = CalibratedFlux(path="data_calibration", outerFolder=outerFolder, cfg=config_cal, soc=soc,
                                  soccfg=soccfg)
yoko_calibration.calibrate(dev_name="6p75_qcage_0729")
yoko_calibration.save_data()
yoko_calibration.display()
#%%
# TITLE: Choose a flux value and get the yoko value
chsn_yoko = yoko_calibration.flux_to_yoko(flux_val - np.floor(flux_val))
print("Chosen yoko value is ", chsn_yoko, " V")
print("Zero Flux Point is at ", yoko_calibration.zero_flux, "V")
print("Half Flux Point is at ", yoko_calibration.half_flux, "V")
print("Flux Quantum is ", yoko_calibration.flux_quantum, " V")
yoko1.SetVoltage(chsn_yoko)

#%%
# TITLE : Get Transmission
UpdateConfig_transmission = {
    # Parameters
    "reps": 4000,  # Number of repetitions

    # cavity
    "read_pulse_style": "const",
    "read_length": 20,
    "read_pulse_gain": 1500,
    "read_pulse_freq":  6671.5, #6253.8,

    # Experiment Parameters
    "TransSpan": 3,  # [MHz] span will be center frequency +/- this parameter
    "TransNumPoints": 501,  # number of points in the transmission frequency
}

config_trans = BaseConfig | UpdateConfig_transmission

#%%
Instance_trans = Transmission(path="dataTestTransmission", cfg=config_trans, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
data_trans = Instance_trans.acquire()
Instance_trans.save_data(data_trans)
Instance_trans.display(data_trans, plotDisp=True)
plt.show()

# Update the transmission frequency to be the peak

config_trans["read_pulse_freq"] = Instance_trans.peakFreq
print("Cavity freq IF [MHz] = ", Instance_trans.peakFreq)
#%%
# TITLE Defining common experiment configurations
UpdateConfig = {
    # set yoko
    "yokoVoltage": 0,  # [in V]
    "yokoVoltage_freqPoint": 0,  # [in V] used for naming the file systems

    # cavity
    "read_pulse_style": "const",
    "read_length": 75,  # [in us]
    "read_pulse_gain": 1500,  # [in DAC units]
    "read_pulse_freq": 6670.84,  # [in MHz]

    # qubit g-e drive parameters
    "qubit_ge_freq": 259.0,  # [in MHz]
    "qubit_pulse_style": "flat_top",
    "qubit_ge_gain": 10000,
    "sigma": 1,
    "flat_top_length": 10,

    # qubit e-f drive parameters
    "qubit_ef_freq": 10000,
    "qubit_ef_gain": 0,

    # experiment parameters
    "cen_num": 2,  # Number of states expected
    "relax_delay": 10*1300,
    'use_switch': True,
    'fridge_temp': 10,
}

config = BaseConfig | UpdateConfig
#%%
# TITLE : Optimize Readout Frequency
UpdateConfig_ss_opt = {

    # qubit spec
    "qubit_pulse_style": "arb",
    "qubit_ge_gain": 1,
    "qubit_ef_gain": 1,
    "qubit_ge_freq": 110,
    "qubit_ef_freq": 110,
    "apply_ge": False,
    "apply_ef": False,
    "qubit_length": 10,
    "sigma": 0.05,
    "relax_delay": 200,

    # Experiment
    "cen_num": 2,
    "keys": ['kl'],           # Possible keys ["mahalanobis", "bhattacharyya", "kl", "hellinger"]
    "shots": 100000,
    "use_switch": True,
    "relax_delay": 10,
}
config_ss_opt = config | UpdateConfig_ss_opt

#%%
param_bounds ={
    "read_pulse_freq" : (config_ss_opt["read_pulse_freq"] - 0.1, config_ss_opt["read_pulse_freq"] + 0.1),
}
step_size = {
    "read_pulse_freq" : 0.002,
}
keys = ["read_pulse_freq"]
config["shots"] = 10000
inst_singleshotopt = SingleShotMeasure(path="SingleShotOpt_vary_6p75", outerFolder=outerFolder, cfg=config_ss_opt,
                                       soc=soc, soccfg=soccfg, fast_analysis=True)
opt_param = inst_singleshotopt.brute_search( keys, param_bounds, step_size, )
print(opt_param)
config["read_pulse_freq"] = opt_param[0][0]
#%%
# Extract the first and second parameter values
param1_values = [param[0][0] for param in inst_singleshotopt.params]
quants = inst_singleshotopt.quants

# Create a 2D color plot
plt.figure(figsize=(10, 8))
scatter = plt.scatter(param1_values, quants)
plt.xlabel('Resonator Pulse Frequency')
plt.ylabel('KL Divergence')
plt.title('Optimization')
plt.colorbar(scatter, label='Quant Values')
plt.show()

#%%
# TITLE : Run a g-e spec slice

# For the spec slice experiment
UpdateConfig_spec = {
    # define spec slice experiment parameters
    "qubit_freq_start": 50,
    "qubit_freq_stop": 650,
    "SpecNumPoints": 301,
    'spec_reps': 2000,
    'qubit_gain': 10000,
    'relax_delay': 10,
}
config_spec = config | UpdateConfig_spec

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
# TITLE : Run g-e spec slice with Post Selection

# For the spec slice experiment with PS
UpdateConfig_spec_ps = {
    # define spec slice experiment parameters
    "qubit_freq_start": 50,
    "qubit_freq_stop": 550,
    "SpecNumPoints": 201,
    'spec_reps': 8000,
    'qubit_gain': 10000,
    'relax_delay': 10,
    'initialize_pulse': False,
    'fridge_temp': 420,
    "qubit_pulse_style": "flat_top"
}
config_spec_ps = config | UpdateConfig_spec_ps

#%%

inst_specslice = SpecSlice_PS_sse(path="dataTestSpecSlice_PS", cfg=config_spec_ps,
                                        soc=soc, soccfg=soccfg, outerFolder=outerFolder)
data_specSlice_PS = inst_specslice.acquire()
data_specSlice_PS = inst_specslice.process_data(data = data_specSlice_PS)
inst_specslice.display(data = data_specSlice_PS, plotDisp=True)
inst_specslice.save_data(data_specSlice_PS)
config['qubit_freq'] = data_specSlice_PS['data']['resonant_freq']
config['qubit_ge_freq'] = data_specSlice_PS['data']['resonant_freq']

#%%
# TITLE : Get the e-f frequency

# For the e-f frequency spec
UpdateConfig_ef = {
    # e-f parameters
    "qubit_ef_freq_start": 1600,
    "qubit_ef_freq_step": 1,
    "qubit_ef_gain": 12000,
    "SpecNumPoints": 401,
    "reps": 500,
}
config_ef = config | UpdateConfig_ef

#%%
instance_ef_spec = Qubit_ef_spectroscopy(path="dataQubit_ef_spectroscopy", outerFolder=outerFolder, cfg=config_ef,soc=soc,soccfg=soccfg, progress=True)
data_ef_spec = instance_ef_spec.acquire()
instance_ef_spec.save_data(data_ef_spec)
instance_ef_spec.save_config()
instance_ef_spec.display(data_ef_spec, plotDisp=True)
config["qubit_ef_freq"] = data_ef_spec['data']['f_reqd']


#%%
# TITLE: Optimize QND -> Get the optimal readout length and gain
UpdateConfig_qnd = {
    # qubit tone
    "qubit_pulse_style": "flat_top",
    "qubit_gain": 10000,
    "qubit_length": 10,
    "sigma": 1,
    "flat_top_length": 10.0,

    # Experiment
    "shots": 100000,
    "cen_num": 2,
    "relax_delay": 10,
    "fridge_temp": 10,
    'use_switch': True,
}
config_qnd = config | UpdateConfig_qnd
#%%
# TITLE : Optimizing readout gain
param_bounds ={
    'read_pulse_gain': (1000, 2500)
}
step_size = {
    'read_pulse_gain': 100,
}
keys = ["read_pulse_gain"]
config_qnd["shots"] = 300000
inst_qndopt = QNDmeas(path="QND_Optimization", outerFolder=outerFolder, cfg=config_qnd, soc=soc, soccfg=soccfg)
opt_results = inst_qndopt.brute_search(keys, param_bounds, step_size, store = True)
inst_qndopt.brute_search_result_display(display = True)
config['read_pulse_gain'] = opt_results[0]
config_qnd['read_pulse_gain'] = opt_results[0]

#%%
# TITLE : Optimizng readout length
param_bounds ={
    'read_length': (20, 90),
}
step_size = {
    'read_length': 10,
}
keys = ["read_length"]
config_qnd["shots"] = 300000
inst_qndopt = QNDmeas(path="QND_Optimization", outerFolder=outerFolder, cfg=config_qnd, soc=soc, soccfg=soccfg)
opt_results = inst_qndopt.brute_search(keys, param_bounds, step_size, store = True)
inst_qndopt.brute_search_result_display(display = True)
config['read_length'] = opt_results[0]
config_qnd['read_length'] = opt_results[0]

#%%
# Measure T1
UpdateConfig_t1 = {
    # qubit tone
    "qubit_pulse_style": "flat_top",
    "qubit_gain": 10000,
    "qubit_length": 10,
    "sigma": 1,
    "flat_top_length": 10.0,

    # experiment
    "shots": 20000,
    "wait_start": 1,
    "wait_stop": 13000,
    "wait_num": 21,
    'wait_type': 'linear',
    "cen_num": 2,
    "fridge_temp": 10,
    "relax_delay": 10,
    "use_switch": True
}
config_t1 = config | UpdateConfig_t1

#%%
# calculate an estimate of the scan time
time_per_scan = config_t1["shots"] * (
        np.linspace(config_t1['wait_start'], config_t1["wait_stop"], config_t1["wait_num"]) + config_t1["relax_delay"]) * 1e-6
total_time = np.sum(time_per_scan) / 60
print('total time estimate: ' + str(total_time) + " minutes")

# Run
print('starting scan: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
Instance_T1_PS = T1_PS_sse(path="T1_PS_temp_" + str(config_t1["fridge_temp"]), outerFolder=outerFolder, cfg=config_t1,
                           soc=soc, soccfg=soccfg)
data_T1_PS = Instance_T1_PS.acquire()
data_T1_PS = Instance_T1_PS.process_data(data_T1_PS)
Instance_T1_PS.save_data(data_T1_PS)
Instance_T1_PS.save_config()
Instance_T1_PS.display(data_T1_PS, plotDisp=True)

#%%
# TITLE : Measure temperature

# For the single shot experiment
UpdateConfig_ss = {
        ## define experiment parameters
        "shots": int(6e5),
        "use_switch": True,
        "initialize_pulse": True,
        "apply_ef": False
    }
config_ss = config | UpdateConfig_ss

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
old_flux = chsn_phase = 0.494
flux_list = old_flux*np.tile(np.array([-1,1]), 2*N + 1) + np.repeat(np.linspace(-N,N,2*N+1),2)
print(flux_list) # For N = 1 -> -phi-phi_0,phi-phi_0,-phi,phi,-phi+phi_0,phi+phi_0
# flux_list = np.repeat(flux_list, 3)
# print(flux_list)

# Creating empty lists to store the temperatures and error
tempr_list = []
tempr_std_list = []
tempr_fridge = []
yoko_list = []

#%%
run_calib = True
run_trans = True
run_ss_opt = True
run_ge_spec = True
run_ge_spec_ps = True
run_qnd_gain = True
run_qnd_length = True
run_ef_spec = False
run_t1 = False
run_ss = True

from tqdm import tqdm
for idx_flux in tqdm(range(flux_list.size)):

    # Calibrate the flux
    if run_calib:
        print("Running Calibrated Flux")
        config_cal = BaseConfig | UpdateConfig_cal
        yoko_calibration = CalibratedFlux(path="data_calibration", outerFolder=outerFolder, cfg=config_cal, soc=soc,
                                          soccfg=soccfg)
        yoko_calibration.calibrate(dev_name = "6p75_qcage_0729")
        yoko_calibration.save_data()
        yoko_calibration.display()
        config_cal['flux_quantum'] = yoko_calibration.flux_quantum

        # Calibrate for that quantum flux
        config_cal["n_quantum"] = np.floor(flux_list[idx_flux])
        config_cal['yokoVoltageStart'] += np.floor(flux_list[idx_flux])*yoko_calibration.flux_quantum
        config_cal['yokoVoltageStop'] += np.floor(flux_list[idx_flux]) * yoko_calibration.flux_quantum
        yoko_calibration = CalibratedFlux(path="data_calibration", outerFolder=outerFolder, cfg=config_cal, soc=soc,
                                          soccfg=soccfg)
        yoko_calibration.calibrate(dev_name="6p75_qcage_0729")
        yoko_calibration.save_data()
        yoko_calibration.display()

    # Find the new yoko voltage
    # yoko_calibration.half_flux = -0.14
    # yoko_calibration.zero_flux = -0.4575
    new_yoko = yoko_calibration.flux_to_yoko(flux_list[idx_flux] - np.floor(flux_list[idx_flux]))
    print("Setting the yoko to ", new_yoko)
    yoko1.SetVoltage(new_yoko)
    time.sleep(120)

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

    # Get the cavity frequency
    if run_trans:
        Instance_trans = Transmission(path="dataTestTransmission", cfg=config_trans, soc=soc, soccfg=soccfg,
                                      outerFolder=outerFolder)
        data_trans = Instance_trans.acquire()
        Instance_trans.save_data(data_trans)
        Instance_trans.display(data_trans, plotDisp=False)

        # Update the transmission frequency to be the peak
        config_trans["read_pulse_freq"] = Instance_trans.peakFreq
        print("Cavity freq IF [MHz] = ", Instance_trans.peakFreq)
        config["read_pulse_freq"] = Instance_trans.peakFreq

    if run_ss_opt:
        # Update config
        config_ss_opt = config | UpdateConfig_ss_opt
        print("Running ss optmization")
        param_bounds = {
            "read_pulse_freq": (config_ss_opt["read_pulse_freq"] - 0.15, config_ss_opt["read_pulse_freq"] + 0.15),
        }
        step_size = {
            "read_pulse_freq": 0.002,
        }
        keys = ["read_pulse_freq"]
        config_ss_opt["shots"] = 10000
        inst_singleshotopt = SingleShotMeasure(path="SingleShotOpt_vary_6p75", outerFolder=outerFolder,
                                               cfg=config_ss_opt,
                                               soc=soc, soccfg=soccfg, fast_analysis=True)
        opt_param = inst_singleshotopt.brute_search(keys, param_bounds, step_size, )
        inst_singleshotopt.display_opt()
        print("Optimized Readout Frequency ",opt_param[0][0]," MHz")
        # Update Readout Frequency
        config["read_pulse_freq"] = opt_param[0][0]

    # Get the qubit g-e frequency
    if run_ge_spec:
        # Update config
        config_spec = config | UpdateConfig_spec
        print("Running g_e spec")
        Instance_specSlice = SpecSlice_bkg_sub(path="dataTestSpecSlice", cfg=config_spec, soc=soc, soccfg=soccfg,
                                               outerFolder=outerFolder, progress=True)
        data_specSlice = Instance_specSlice.acquire()
        Instance_specSlice.display(data_specSlice, plotDisp=False)
        Instance_specSlice.save_config()
        Instance_specSlice.save_data(data_specSlice)
        qubit_freq = data_specSlice["data"]["f_reqd"]
        print("Qubit frequency according to spec slice ", qubit_freq)

    # Get qubit frequency using spec slice with PS
    if run_ge_spec_ps:
        # Update config
        config_spec_ps = config | UpdateConfig_spec_ps
        print("Running spec with Post Selection")
        inst_specslice = SpecSlice_PS_sse(path="dataTestSpecSlice_PS", cfg=config_spec_ps,
                                          soc=soc, soccfg=soccfg, outerFolder=outerFolder)
        data_specSlice_PS = inst_specslice.acquire()
        data_specSlice_PS = inst_specslice.process_data(data=data_specSlice_PS)
        inst_specslice.display(data=data_specSlice_PS, plotDisp=False)
        inst_specslice.save_data(data_specSlice_PS)
        config['qubit_freq'] = data_specSlice_PS['data']['resonant_freq']
        config['qubit_ge_freq'] = data_specSlice_PS['data']['resonant_freq']

    # Get the qubit e-f frequency
    if run_ef_spec:
        # Update config
        config_ef = config | UpdateConfig_ef
        print("Running ef spec")
        instance_ef_spec = Qubit_ef_spectroscopy(path="dataQubit_ef_spectroscopy", outerFolder=outerFolder, cfg=config_ef,
                                                 soc=soc, soccfg=soccfg, progress=True)
        data_ef_spec = instance_ef_spec.acquire()
        instance_ef_spec.save_data(data_ef_spec)
        instance_ef_spec.save_config()
        instance_ef_spec.display(data_ef_spec, plotDisp=False)
        config["qubit_ef_freq"] = data_ef_spec["data"]['f_reqd']

    # Optimize the readout gain
    if run_qnd_gain:
        config_qnd = config | UpdateConfig_qnd
        print("Optimizing over readout gain")
        param_bounds = {
            'read_pulse_gain': (1000, 2500)
        }
        step_size = {
            'read_pulse_gain': 100,
        }
        keys = ["read_pulse_gain"]
        config_qnd["shots"] = 300000
        inst_qndopt = QNDmeas(path="QND_Optimization", outerFolder=outerFolder, cfg=config_qnd, soc=soc, soccfg=soccfg)
        opt_results = inst_qndopt.brute_search(keys, param_bounds, step_size, store=True)
        inst_qndopt.brute_search_result_display(display=False)
        config['read_pulse_gain'] = int(opt_results[1]['read_pulse_gain'])

    if run_qnd_length:
        # Update config
        config_qnd = config | UpdateConfig_qnd
        print("Optimizing over readout length")
        param_bounds = {
            'read_length': (20, 90),
        }
        step_size = {
            'read_length': 10,
        }
        keys = ["read_length"]
        config_qnd["shots"] = 300000
        inst_qndopt = QNDmeas(path="QND_Optimization", outerFolder=outerFolder, cfg=config_qnd, soc=soc, soccfg=soccfg)
        opt_results = inst_qndopt.brute_search(keys, param_bounds, step_size, store=True)
        inst_qndopt.brute_search_result_display(display=False)
        config['read_length'] = int(opt_results[1]["read_length"])

    # Get the qubit T1
    if run_t1:
        config_t1 = config | UpdateConfig_t1
        print("Running T1 experiment")
        Instance_T1_PS = T1_PS_sse(path="T1_PS_temp_" + str(config_t1["fridge_temp"]), outerFolder=outerFolder,
                                   cfg=config_t1,
                                   soc=soc, soccfg=soccfg)
        data_T1_PS = Instance_T1_PS.acquire()
        data_T1_PS = Instance_T1_PS.process_data(data_T1_PS)
        Instance_T1_PS.save_data(data_T1_PS)
        Instance_T1_PS.save_config()
        Instance_T1_PS.display(data_T1_PS, plotDisp=False)
        config['relax_delay'] = 10 * data_T1_PS['data']['T1']

    # Get the qubit temperature
    if run_ss:
        # Updating config
        config_ss = config | UpdateConfig_ss
        print("Running Single Shot")
        time_required = config_ss["shots"] * config_ss["relax_delay"] * 1e-6 / 60
        print("SingleShot : Total time estimate is ", time_required, " mins")
        Instance_SingleShotProgram = SingleShotSSE(path="TempMeas_yoko_" + str(config_ss["yokoVoltage_freqPoint"]),
                                                   outerFolder=outerFolder, cfg=config_ss,
                                                   soc=soc, soccfg=soccfg)
        data_SingleShot = Instance_SingleShotProgram.acquire()
        data_SingleShot = Instance_SingleShotProgram.process_data(data_SingleShot, bin_size=51)
        Instance_SingleShotProgram.save_data(data_SingleShot)
        Instance_SingleShotProgram.display(data_SingleShot, plotDisp=False, save_fig=True)

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
ax.errorbar(np.array(yoko_list[:]), np.array(tempr01)*1e3, yerr=np.array(tempr01_std)*1e3, fmt='o', label = 'Temperature 01')
ax.errorbar(np.array(yoko_list[:]), np.array(tempr12)*1e3, yerr=np.array(tempr12_std)*1e3, fmt='o', label = 'Temperature 12')
ax.errorbar(np.array(yoko_list[:]), np.array(tempr02)*1e3, yerr=np.array(tempr02_std)*1e3, fmt='o', label = 'Temperature 02')
ax.plot(yoko_list[:], tempr_fridge, 'o', label = 'Fridge Temperature')
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


