# %%
import os
import time
import datetime
import numpy as np
import WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.PythonDrivers.LS370 as lk
import pyvisa
import matplotlib.pyplot as plt

from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Calib.initialize import *
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mSingleShotTemp_sse import SingleShotSSE
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mSpecSlice_bkg_subtracted import \
    SpecSlice_bkg_sub
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mSpecSlice_SaraTest import SpecSlice
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mQubit_ef_spectroscopy import \
    Qubit_ef_spectroscopy
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mTransmission_SaraTest import Transmission
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mTransmission_Enhance import \
    Transmission_Enhance
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mSpecSlice_PS_sse import SpecSlice_PS_sse
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mAutoCalibrator import CalibratedFlux
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mSingleShotOptimize import SingleShotMeasure
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mSingleShotTemp_FullAnalysis import \
    SingleShotFull
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mQND import QNDmeas
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mT1_PS_sse import T1_PS_sse
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mSpecFind import SpecFind

# Define the saving path
outerFolder = "Z:\\TantalumFluxonium\\Data\\2024_10_14_cooldown\\QCage_dev\\TemperatureDriftCheck2\\"
outerFolder_og = outerFolder

# Defining the standard config files
SwitchConfig = {
    "trig_buffer_start": 0.035,  # in us
    "trig_buffer_end": 0.024,  # in us
    "trig_delay": 0.07,  # in us
}

BaseConfig = BaseConfig | SwitchConfig
# %%
# 6.5 GHz Qubit
update_config_q1 = {
    # set yoko
    "yokoVoltage": -1.20151,  # [in V]
    "yokoVoltage_freqPoint": -1.20151,  # [in V] used for naming the file systems
    "flux": 0.5,

    # cavity
    "read_pulse_style": "const",
    "read_length": 50,  # [in us]
    "read_pulse_gain": 800,  # [in DAC units]
    "read_pulse_freq": 6432.615,  # [in MHz]
    "mode_periodic": False,

    # qubit g-e drive parameters
    "qubit_ge_freq": 105,  # [in MHz]
    'qubit_freq': 105,
    "qubit_pulse_style": "flat_top",
    "qubit_length": 60,
    "qubit_ge_gain": 7500,
    "qubit_gain": 7500,
    "sigma": 1,
    "flat_top_length": 60,

    # qubit e-f drive parameters
    "qubit_ef_freq": 10000,
    "qubit_ef_gain": 0,

    # experiment parameters
    "cen_num": 2,  # Number of states expected
    "relax_delay": 10,
    'use_switch': True,
    'fridge_temp': 10,
}

# 6.75 GHz Qubit
update_config_q2 = {
    # set yoko
    "yokoVoltage": -1.20151,  # [in V]
    "yokoVoltage_freqPoint": -1.20151,  # [in V] used for naming the file systems
    "flux": 0.5,

    # cavity
    "read_pulse_style": "const",
    "read_length": 50,  # [in us]
    "read_pulse_gain": 1200,  # [in DAC units]
    "read_pulse_freq": 6670.54,  # [in MHz]
    "mode_periodic": False,

    # qubit g-e drive parameters
    "qubit_ge_freq": 157,  # [in MHz]
    'qubit_freq': 157,
    "qubit_pulse_style": "flat_top",
    "qubit_length": 60,
    "qubit_ge_gain": 4000,
    "qubit_gain": 4000,
    "sigma": 1,
    "flat_top_length": 60,

    # qubit e-f drive parameters
    "qubit_ef_freq": 10000,
    "qubit_ef_gain": 0,

    # experiment parameters
    "cen_num": 2,  # Number of states expected
    "relax_delay": 10,
    'use_switch': True,
    'fridge_temp': 10,
}


main_config = {
    'q1': BaseConfig | update_config_q1,
    'q2': BaseConfig | update_config_q2,
}

# %%
# TITLE : Perform Transmission

qkey = 'q1'

UpdateConfig_transmission_q1 = {
    # Parameters
    "reps": 4000,  # Number of repetitions

    # Experiment Parameters
    "TransSpan": 3,  # [MHz] span will be center frequency +/- this parameter
    "TransNumPoints": 301,  # number of points in the transmission frequency
    "relax_delay": 10,
}

UpdateConfig_transmission_q2 = {
    # Parameters
    "reps": 4000,  # Number of repetitions

    # Experiment Parameters
    "TransSpan": 3,  # [MHz] span will be center frequency +/- this parameter
    "TransNumPoints": 301,  # number of points in the transmission frequency
    "relax_delay": 10,
}

UpdateConfig_transmission = {
    'q1': UpdateConfig_transmission_q1,
    'q2': UpdateConfig_transmission_q2
}



# %%
config_trans = main_config[qkey] | UpdateConfig_transmission[qkey]
mlbf_filter.set_frequency(config_trans["read_pulse_freq"])
transm_exp = Transmission_Enhance(path="TransmisionEnhanced", cfg=config_trans, soc=soc, soccfg=soccfg,
                                  outerFolder=outerFolder + qkey + "\\")
data_transm = transm_exp.acquire()
transm_exp.save_data(data_transm)
transm_exp.save_config()
transm_exp.display(data_transm, plotDisp=True)
opt_freq = transm_exp.findOptimalFrequency(data=data_transm, debug=True)

# Update the transmission frequency to be the peak
config_trans["read_pulse_freq"] = opt_freq
print("Cavity freq IF [MHz] = ", opt_freq)

# %%
# TITLE : Frequency optimization with single shot SNR
qkey = 'q1'

UpdateConfig_ss_opt_q1 = {
    # Experiment
    "keys": ['kl'],  # Possible keys ["mahalanobis", "bhattacharyya", "kl", "hellinger"]
    "shots": 20000,
    "relax_delay": 10,
    "bound": 0.2,
    "step_size": 0.02,
    "apply_ge": True,
    "apply_ef": False,
}

UpdateConfig_ss_opt_q2 = {
    # Experiment
    "keys": ['kl'],  # Possible keys ["mahalanobis", "bhattacharyya", "kl", "hellinger"]
    "shots": 20000,
    "relax_delay": 10,
    "bound": 0.2,
    "step_size": 0.02,
    "apply_ge": True,
    "apply_ef": False,
}

UpdateConfig_ss_opt = {
    'q1': UpdateConfig_ss_opt_q1,
    'q2': UpdateConfig_ss_opt_q2
}

# %%
config_ss_opt = main_config[qkey] | UpdateConfig_ss_opt[qkey]
param_bounds = {
    "read_pulse_freq": (config_ss_opt["read_pulse_freq"] - config_ss_opt["bound"], config_ss_opt["read_pulse_freq"] + config_ss_opt["bound"]),
}
step_size = {
    "read_pulse_freq": config_ss_opt["step_size"],
}
keys = ["read_pulse_freq"]
mlbf_filter.set_frequency(config_ss_opt["read_pulse_freq"])
inst_singleshotopt = SingleShotMeasure(path="SingleShotOpt_vary_6p75", outerFolder=outerFolder + qkey + "\\", cfg=config_ss_opt,
                                       soc=soc, soccfg=soccfg, fast_analysis=True)
opt_param = inst_singleshotopt.brute_search(keys, param_bounds, step_size, )
inst_singleshotopt.display_opt(plotDisp=True)
print(opt_param)
main_config[qkey]['read_pulse_freq'] = opt_param[0][0]

#%%
# TITLE: Get the qubit frequency using spec slice
qkey = 'q1'

# For the spec slice experiment
UpdateConfig_spec_q1 = {
    # define spec slice experiment parameters
    "qubit_freq_start": 70,
    "qubit_freq_stop": 130,
    "SpecNumPoints": 61,
    'spec_reps': 1000,
    'qubit_gain': 7500,
    'relax_delay': 10,
}

UpdateConfig_spec_q2 = {
    # define spec slice experiment parameters
    "qubit_freq_start": 120,
    "qubit_freq_stop": 180,
    "SpecNumPoints": 61,
    'spec_reps': 1000,
    'qubit_gain': 4000,
    'relax_delay': 10,
}

UpdateConfig_spec = {
    "q1" : UpdateConfig_spec_q1,
    "q2" : UpdateConfig_spec_q2
}

# %%
config_spec = main_config[qkey] | UpdateConfig_spec[qkey]
mlbf_filter.set_frequency(config_spec["read_pulse_freq"])
inst_specslice = SpecSlice_bkg_sub(path="dataTestSpecSlice_PS", cfg=config_spec,
                                        soc=soc, soccfg=soccfg, outerFolder=outerFolder + qkey + "\\")
data_specSlice = inst_specslice.acquire()
inst_specslice.display(data = data_specSlice, plotDisp=True)
inst_specslice.save_data(data_specSlice)
inst_specslice.save_config()

main_config[qkey]['qubit_freq'] = data_specSlice["data"]["f_reqd"]
main_config[qkey]['qubit_ge_freq'] = data_specSlice["data"]["f_reqd"]

# %%
# TITLE: Get the qubit frequency using post selected spec slice

qkey = "q2"

# For the spec slice experiment with PS
UpdateConfig_spec_ps_q1 = {
    # define spec slice experiment parameters
    "qubit_freq_start": 70,
    "qubit_freq_stop": 150,
    "SpecNumPoints": 81,
    'spec_reps': 8000,

    # Qubit tone
    'qubit_gain': 7500,
    'relax_delay': 10,
    'initialize_pulse': False,
    'fridge_temp': 420,
    "qubit_pulse_style": "flat_top",
    "flat_top_length" : 60,
    "sigma": 1,
}

UpdateConfig_spec_ps_q2 = {
    # define spec slice experiment parameters
    "qubit_freq_start": 110,
    "qubit_freq_stop": 190,
    "SpecNumPoints": 81,
    'spec_reps': 8000,

    # Qubit tone
    'qubit_gain': 5000,
    'relax_delay': 10,
    'initialize_pulse': False,
    'fridge_temp': 420,
    "qubit_pulse_style": "flat_top",
    "flat_top_length": 60,
    "sigma": 1,

}

UpdateConfig_spec_ps = {
    "q1" : UpdateConfig_spec_ps_q1,
    "q2" : UpdateConfig_spec_ps_q2
}

# %%
config_spec_ps = main_config[qkey] | UpdateConfig_spec_ps[qkey]
mlbf_filter.set_frequency(config_spec_ps["read_pulse_freq"])
inst_specslice = SpecSlice_PS_sse(path="dataTestSpecSlice_PS", cfg=config_spec_ps,
                                        soc=soc, soccfg=soccfg, outerFolder=outerFolder + qkey + "\\")
data_specSlice_PS = inst_specslice.acquire()
data_specSlice_PS = inst_specslice.process_data(data = data_specSlice_PS)
inst_specslice.display(data = data_specSlice_PS, plotDisp=True)
inst_specslice.save_data(data_specSlice_PS)
inst_specslice.save_config()

main_config[qkey]['qubit_freq'] = data_specSlice_PS['data']['resonant_freq']
main_config[qkey]['qubit_ge_freq'] = data_specSlice_PS['data']['resonant_freq']

# %%
# TITLE : Get the T1 data

qkey = "q2"

UpdateConfig_t1_q1 = {
    # experiment
    "shots": 60000,
    "wait_start": 1,
    "wait_stop": 2000,
    "wait_num": 11,
    'wait_type': 'linear',
    "fridge_temp": 10,
    "relax_delay": 10,
}

UpdateConfig_t1_q2 = {
    # experiment
    "shots": 60000,
    "wait_start": 1,
    "wait_stop": 5000,
    "wait_num": 11,
    'wait_type': 'linear',
    "fridge_temp": 10,
    "relax_delay": 10,
}

UpdateConfig_t1 = {
    "q1": UpdateConfig_t1_q1,
    "q2": UpdateConfig_t1_q2
}

#%%
config_t1 = main_config[qkey] | UpdateConfig_t1[qkey]
mlbf_filter.set_frequency(config_t1["read_pulse_freq"])
# calculate an estimate of the scan time
time_per_scan = config_t1["shots"] * (
        np.linspace(config_t1['wait_start'], config_t1["wait_stop"], config_t1["wait_num"]) + config_t1["relax_delay"]) * 1e-6
total_time = np.sum(time_per_scan) / 60
print('total time estimate: ' + str(total_time) + " minutes")

# Run
print('starting scan: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
Instance_T1_PS = T1_PS_sse(path="T1_PS_temp_" + str(config_t1["fridge_temp"]), outerFolder=outerFolder + qkey + "\\", cfg=config_t1,
                           soc=soc, soccfg=soccfg)
data_T1_PS = Instance_T1_PS.acquire()
data_T1_PS = Instance_T1_PS.process_data(data_T1_PS)
Instance_T1_PS.save_data(data_T1_PS)
Instance_T1_PS.save_config()
Instance_T1_PS.display(data_T1_PS, plotDisp=True)
main_config[qkey]['relax_delay'] = 10*data_T1_PS['data']['T1']
UpdateConfig_t1[qkey]['wait_stop'] = 5*data_T1_PS['data']['T1']

#%%
# TITLE : Measure Temperature

qkey = 'q1'

UpdateConfig_ss_q1 = {
        # define experiment parameters
        "shots": int(2e5),
        "initialize_pulse": True,
        "apply_ef": False
    }

UpdateConfig_ss_q2 = {
        # define experiment parameters
        "shots": int(2e5),
        "initialize_pulse": True,
        "apply_ef": False
    }

UpdateConfig_ss = {
    'q1' : UpdateConfig_ss_q1,
    'q2' : UpdateConfig_ss_q2
}

#%%
config_ss = main_config[qkey] | UpdateConfig_ss[qkey]
mlbf_filter.set_frequency(config_ss["read_pulse_freq"])
# Get the qubit temperature
time_required = config_ss["shots"] * config_ss["relax_delay"] * 1e-6 / 60
print("SingleShot : Total time estimate is ", time_required, " mins")
print('starting scan: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
Instance_SingleShotProgram = SingleShotFull(path="Tempr_ss",
                                                   outerFolder=outerFolder+ qkey + "\\", cfg=config_ss ,
                                                   soc=soc, soccfg=soccfg)
data_SingleShot = Instance_SingleShotProgram.acquire()
data_SingleShot = Instance_SingleShotProgram.process_data(data_SingleShot)
Instance_SingleShotProgram.save_data(data_SingleShot)
Instance_SingleShotProgram.save_config()
('end of scan: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
#%%
# TITLE : Continuous scan planning

# qkeys
qkeys = ['q1','q2']

# Scanning same flux point
n_times = 120

#%%
#TITLE : Begin Scan

run_trans = {'q1': True, 'q2' : True}
run_ss_opt = {'q1': True, 'q2' : True}
run_ge_spec = {'q1': False, 'q2' : False}
run_ge_spec_ps = {'q1': True, 'q2' : True}
run_t1 = {'q1': True, 'q2' : True}
run_ss = {'q1': True, 'q2' : True}

from tqdm import tqdm
for idx_flux in tqdm(range(n_times)):
    outerFolder = outerFolder_og + "Meas_" + str(idx_flux) + "\\"

    # TITLE : Transmission Scan
    for qkey in qkeys:
        if run_trans[qkey]:
            config_trans = main_config[qkey] | UpdateConfig_transmission[qkey]
            mlbf_filter.set_frequency(config_trans["read_pulse_freq"])
            transm_exp = Transmission_Enhance(path="dataTestTransmission", cfg=config_trans, soc=soc, soccfg=soccfg,
                                              outerFolder=outerFolder + qkey + "\\")
            data_transm = transm_exp.acquire()
            transm_exp.save_data(data_transm)
            transm_exp.save_config()
            transm_exp.display(data_transm, plotDisp=False)
            opt_freq = transm_exp.findOptimalFrequency(data=data_transm, debug=True)

        plt.close('all')

    # TITLE : Single Shot SNR Optimization
    for qkey in qkeys:
        if run_ss_opt[qkey]:
            config_ss_opt = main_config[qkey] | UpdateConfig_ss_opt[qkey]
            param_bounds = {
                "read_pulse_freq": (config_ss_opt["read_pulse_freq"] - config_ss_opt["bound"],
                                    config_ss_opt["read_pulse_freq"] + config_ss_opt["bound"]),
            }
            step_size = {
                "read_pulse_freq": config_ss_opt["step_size"],
            }
            keys = ["read_pulse_freq"]
            mlbf_filter.set_frequency(config_ss_opt["read_pulse_freq"])
            inst_singleshotopt = SingleShotMeasure(path="SingleShotOpt_vary_6p75",
                                                   outerFolder=outerFolder + qkey + "\\", cfg=config_ss_opt,
                                                   soc=soc, soccfg=soccfg, fast_analysis=True)
            opt_param = inst_singleshotopt.brute_search(keys, param_bounds, step_size, )
            inst_singleshotopt.display_opt(plotDisp=True)
            print("Optimized Readout Frequency ",opt_param[0][0]," MHz")
            main_config[qkey]['read_pulse_freq'] = opt_param[0][0]
        plt.close('all')

    # TITLE: g-e: spec slice
    for qkey in qkeys:
        if run_ge_spec[qkey]:
            config_spec = main_config[qkey] | UpdateConfig_spec[qkey]
            mlbf_filter.set_frequency(config_spec["read_pulse_freq"])
            inst_specslice = SpecSlice_bkg_sub(path="dataTestSpecSlice_PS", cfg=config_spec,
                                               soc=soc, soccfg=soccfg, outerFolder=outerFolder + qkey + "\\")
            data_specSlice = inst_specslice.acquire()
            inst_specslice.display(data=data_specSlice, plotDisp=True)
            inst_specslice.save_data(data_specSlice)
            inst_specslice.save_config()

            main_config[qkey]['qubit_freq'] = data_specSlice["data"]["f_reqd"]
            main_config[qkey]['qubit_ge_freq'] = data_specSlice["data"]["f_reqd"]
    plt.close('all')

    # TITLE: g-e PS Spec Slice
    for qkey in qkeys:
        if run_ge_spec_ps[qkey]:
            config_spec_ps = main_config[qkey] | UpdateConfig_spec_ps[qkey]
            mlbf_filter.set_frequency(config_spec_ps["read_pulse_freq"])
            inst_specslice = SpecSlice_PS_sse(path="dataTestSpecSlice_PS", cfg=config_spec_ps,
                                              soc=soc, soccfg=soccfg, outerFolder=outerFolder + qkey + "\\")
            data_specSlice_PS = inst_specslice.acquire()
            data_specSlice_PS = inst_specslice.process_data(data=data_specSlice_PS)
            inst_specslice.display(data=data_specSlice_PS, plotDisp=False)
            inst_specslice.save_data(data_specSlice_PS)
            inst_specslice.save_config()

            main_config[qkey]['qubit_freq'] = data_specSlice_PS['data']['resonant_freq']
            main_config[qkey]['qubit_ge_freq'] = data_specSlice_PS['data']['resonant_freq']
        plt.close('all')

    # TITLE : Measure T1
    for qkey in qkeys:
        if run_t1[qkey]:
            config_t1 = main_config[qkey] | UpdateConfig_t1[qkey]
            mlbf_filter.set_frequency(config_t1["read_pulse_freq"])

            Instance_T1_PS = T1_PS_sse(path="T1_PS_temp_" + str(config_t1["fridge_temp"]),
                                       outerFolder=outerFolder + qkey + "\\", cfg=config_t1,
                                       soc=soc, soccfg=soccfg)
            data_T1_PS = Instance_T1_PS.acquire()
            data_T1_PS = Instance_T1_PS.process_data(data_T1_PS)
            Instance_T1_PS.save_data(data_T1_PS)
            Instance_T1_PS.save_config()
            Instance_T1_PS.display(data_T1_PS, plotDisp=False)
            main_config[qkey]['relax_delay'] = 10 * data_T1_PS['data']['T1']
            UpdateConfig_t1[qkey]['wait_stop'] = 5 * data_T1_PS['data']['T1']

    # TITLE : Measure Temperature
    for qkey in qkeys:
        if run_ss[qkey]:
            config_ss = main_config[qkey] | UpdateConfig_ss[qkey]
            mlbf_filter.set_frequency(config_ss["read_pulse_freq"])
            Instance_SingleShotProgram = SingleShotFull(path="Tempr_ss",
                                                        outerFolder=outerFolder + qkey + "\\", cfg=config_ss,
                                                        soc=soc, soccfg=soccfg)
            data_SingleShot = Instance_SingleShotProgram.acquire()
            data_SingleShot = Instance_SingleShotProgram.process_data(data_SingleShot)
            Instance_SingleShotProgram.save_data(data_SingleShot)
            Instance_SingleShotProgram.save_config()