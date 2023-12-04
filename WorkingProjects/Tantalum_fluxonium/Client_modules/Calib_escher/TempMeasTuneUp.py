#### import packages
import os

import numpy as np

path = os.getcwd()
os.add_dll_directory(os.path.dirname(path)+'\\PythonDrivers')
from WorkingProjects.Tantalum_fluxonium.Client_modules.Calib_escher.initialize import *
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mSingleShotProgram import SingleShotProgram
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mSingleShot_2Dsweep import SingleShot_2Dsweep
# from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mT1_ThermalPS import T1_ThermalPS
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mT1_ThermalPS_pulse import T1_ThermalPS
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mSingleShotPS import SingleShotPS
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mQND import QNDmeas
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mAmplitudeRabiBlob_PS import AmplitudeRabi_PS
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mAmplitudeRabiFlux_PS import AmplitudeRabiFlux_PS
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mT2R_PS import T2R_PS
from matplotlib import pyplot as plt
import datetime
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mT1_PS import T1_PS
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mRepeatReadout import RepeatReadout

#### define the saving path
# outerFolder = "Z:\\TantalumFluxonium\\Data\\2023_10_31_BF2_cooldown_6\\WTF\\"
# outerFolder = "Z:\\TantalumFluxonium\\Data\\2023_10_31_BF2_cooldown_6\\WTF\\TempChecks\\"
#################################### Running the actual experiments

# Only run this if no proxy already exists
soc, soccfg = makeProxy()
# # print(soccfg)

print('program starting: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
#
# plt.ioff()
#
#
fridge_temp = 10
relax_delay = 1000
wait_stop = 800

# # ################################################################################################################
# # # ####################################### code for running basic single shot exerpiment
# UpdateConfig = {
#     ##### set yoko
#     "yokoVoltage": -0.5,
#     "yokoVoltage_freqPoint": -0.5,
#     ###### cavity
#     "reps": 2000,  # this will used for all experiements below unless otherwise changed in between trials
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 15, # [Clock ticks]
#     "read_pulse_gain":  7000, # [DAC units]
#     "read_pulse_freq": 7392.25, # [MHz]
#     ##### qubit spec parameters
#     "qubit_pulse_style": "flat_top",
#     "qubit_gain": 23000,
#     # "qubit_length": 10,  ###us, this is used if pulse style is const
#     "sigma": 0.005,  ### units us, define a 20ns sigma
#     "flat_top_length": 10, ### in us
#     "qubit_freq": 4819,
#     "relax_delay": 1000,  ### turned into us inside the run function
#     #### define shots
#     "shots": 20000, ### this gets turned into "reps"
#     ##### record the fridge temperature in units of mK
#     "fridge_temp": fridge_temp,
# }
# config = BaseConfig | UpdateConfig
#
# yoko1.SetVoltage(config["yokoVoltage"])
# #
# outerFolder = "Z:\\TantalumFluxonium\\Data\\2023_10_31_BF2_cooldown_6\\WTF\\TempChecks\\Yoko_"+str(config["yokoVoltage_freqPoint"])+"\\"
# Instance_SingleShotProgram = SingleShotProgram(path="SingleShot_temp_"+str(config["fridge_temp"]), outerFolder=outerFolder, cfg=config,
#                                                soc=soc, soccfg=soccfg)
# data_SingleShot = SingleShotProgram.acquire(Instance_SingleShotProgram)
# SingleShotProgram.save_data(Instance_SingleShotProgram, data_SingleShot)
# SingleShotProgram.save_config(Instance_SingleShotProgram)
# SingleShotProgram.display(Instance_SingleShotProgram, data_SingleShot, plotDisp=True, save_fig=True)

# # ##### run the single shot experiment
# outerFolder = "Z:\\TantalumFluxonium\\Data\\2023_10_31_BF2_cooldown_6\\WTF\\singleShotSweeps\\"
# loop_len = 21
# # freq_vec = config["read_pulse_freq"] + np.linspace(-1, 1, loop_len)
# # qubit_gain_vec = np.linspace(10000, 20000, loop_len, dtype=int)
# # read_gain_vec = np.linspace(12000, 15000, loop_len, dtype=int)
# qubit_freq_vec = config["qubit_freq"] + np.linspace(-10,10,loop_len)
# # qubit_gain_vec = np.linspace(20000,31000, loop_len, dtype = int)
# # flat_top_length_vec = np.linspace(1,40,loop_len, dtype = int)
# for idx in range(loop_len):
#     # config["read_pulse_freq"] = freq_vec[idx]
#     # config["qubit_gain"] = qubit_gain_vec[idx]
#     # config["read_pulse_gain"] = read_gain_vec[idx]
#     config["qubit_freq"] = qubit_freq_vec[idx]
#     # config['flat_top_length'] = flat_top_length_vec[idx]
#     Instance_SingleShotProgram = SingleShotProgram(path="SingleShot_sweeps_yoko_"+str(config["yokoVoltage"]), outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
#     data_SingleShot = SingleShotProgram.acquire(Instance_SingleShotProgram)
#     SingleShotProgram.display(Instance_SingleShotProgram, data_SingleShot, plotDisp=False, save_fig=True)
#     SingleShotProgram.save_data(Instance_SingleShotProgram, data_SingleShot)
#     SingleShotProgram.save_config(Instance_SingleShotProgram)
#     plt.clf()
#     print(idx)
# ###########


# ##################################################################################
# ################## code finding T1 of a thermal state
#
# # time.sleep(300)
UpdateConfig = {
    ##### set yoko
    "yokoVoltage": -0.22,
    "yokoVoltage_freqPoint": -0.22,
    ###### cavity
    #"reps": 0,  # this line does nothing, is overwritten with "shots"
    "read_pulse_style": "const", # --Fixed
    "read_length": 10, # [Clock ticks]
    "read_pulse_gain": 9000, # [DAC units]
    "read_pulse_freq": 7392.357, # [MHz]
    ##### qubit spec parameters
    "qubit_pulse_style": "arb",
    "qubit_gain": 0,
    # "qubit_length": 10,  ###us, this is used if pulse style is const
    "sigma": 0.005,  ### units us, define a 20ns sigma
    "qubit_freq": 495,
    "relax_delay": relax_delay,  ### turned into us inside the run function
    #### define shots
    "shots": 16000, ### this gets turned into "reps"
    ### define the wait times
    "wait_start": 0,
    "wait_stop": wait_stop,
    "wait_num": 15,
    ##### define number of clusters to use
    "cen_num": 2,
    ##### record the fridge temperature in units of mK
    "fridge_temp": fridge_temp,
}
config = BaseConfig | UpdateConfig

yoko1.SetVoltage(config["yokoVoltage"])

outerFolder = "Z:\\TantalumFluxonium\\Data\\2023_10_31_BF2_cooldown_6\\WTF\\TempChecks\\Yoko_"+str(config["yokoVoltage_freqPoint"])+"\\"

########
## calculate an estimate of the scan time
time_per_scan = config["shots"] * (np.linspace(config["wait_start"], config["wait_stop"], config["wait_num"]) + config["relax_delay"])*1e-6
total_time = np.sum(time_per_scan) /60
print('total time estimate: ' + str(total_time) + " minutes" )
#########

print('starting scan: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
Instance_T1_ThermalPS = T1_ThermalPS(path="T1_PS_temp_"+str(config["fridge_temp"]), outerFolder=outerFolder, cfg=config,
                                               soc=soc, soccfg=soccfg)
data_T1_ThermalPS = T1_ThermalPS.acquire(Instance_T1_ThermalPS)

# T1_ThermalPS.display(Instance_T1_ThermalPS, data_T1_ThermalPS, plotDisp=True, save_fig=True)
T1_ThermalPS.save_data(Instance_T1_ThermalPS, data_T1_ThermalPS)
T1_ThermalPS.save_config(Instance_T1_ThermalPS)
print('end of scan: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))


# # # # # # ####################################################################################################################
################ code finding T1 of a thermal state using pulses
# UpdateConfig = {
#     ##### set yoko
#     "yokoVoltage": -0.5,
#     "yokoVoltage_freqPoint": -0.5,
#     ###### cavity
#     #"reps": 0,  # this line does nothing, is overwritten with "shots"
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 10, # [Clock ticks]
#     "read_pulse_gain": 7000, # [DAC units]
#     "read_pulse_freq": 7392.25, # [MHz]
#     ##### qubit spec parameters
#     "qubit_pulse_style": "flat_top",
#     "qubit_gain": 20000, #12000,
#     # "qubit_length": 10,  ###us, this is used if pulse style is const
#     "sigma": 0.005,  ### units us, define a 20ns sigma
#     "flat_top_length": 1.0,
#     "qubit_freq": 4827+25,
#     "relax_delay": 1,  ### turned into us inside the run function
#     #### define shots
#     "shots": 5000, ### this gets turned into "reps"
#     ### define the wait times
#     "wait_start": 0,
#     "wait_stop": 400,
#     "wait_num": 41,
#     ##### define number of clusters to use
#     "cen_num": 2,
#     ##### record the fridge temperature in units of mK
#     "fridge_temp": 70,
# }
# config = BaseConfig | UpdateConfig
#
# yoko1.SetVoltage(config["yokoVoltage"])
#
# outerFolder = "Z:\\TantalumFluxonium\\Data\\2023_10_31_BF2_cooldown_6\\WTF\\TempChecks\\Yoko_"+str(config["yokoVoltage_freqPoint"])+"\\"
#
# print('starting scan: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
#
# Instance_T1_PS = T1_PS(path="T1_PS_temp_"+str(config["fridge_temp"]), outerFolder=outerFolder, cfg=config,
#                                                soc=soc, soccfg=soccfg)
# data_T1_PS = T1_PS.acquire(Instance_T1_PS)
# T1_PS.save_data(Instance_T1_PS, data_T1_PS)
# T1_PS.save_config(Instance_T1_PS)
#
# print('end of scan: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
# # ####################################################################################################################
#
# # # # ####################################### code for measuring the qubit temp using single shot
# UpdateConfig = {
#     ##### set yoko
#     "yokoVoltage": -0.22,
#     "yokoVoltage_freqPoint": -0.22,
#     ###### cavity
#     "reps": 2000,  # this will be used for all experiments below unless otherwise changed in between trials
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 10, # [Clock ticks]
#     "read_pulse_gain": 9000, # [DAC units]
#     "read_pulse_freq": 7392.357, # [MHz]
#     ##### qubit spec parameters
#     "qubit_pulse_style": "arb",
#     "qubit_gain": 0,
#     # "qubit_length": 10,  ###us, this is used if pulse style is const
#     "sigma": 0.005,  ### units us, define a 20ns sigma
#     # "flat_top_length": 1.0, ### in us
#     "qubit_freq": 495,
#     "relax_delay": relax_delay,  ### turned into us inside the run function
#     #### define shots
#     "shots": 30000, ### this gets turned into "reps"
#     ##### record the fridge temperature in units of mK
#     "fridge_temp": fridge_temp,
# }
# config = BaseConfig | UpdateConfig
#
# yoko1.SetVoltage(config["yokoVoltage"])
#
# outerFolder = "Z:\\TantalumFluxonium\\Data\\2023_10_31_BF2_cooldown_6\\WTF\\TempChecks\\Yoko_"+str(config["yokoVoltage_freqPoint"])+"\\"
# time_required = 2*config["shots"]*config["relax_delay"]*1e-6/60
# print("Time required is ", time_required, " mins")
#
# Instance_SingleShotProgram = SingleShotProgram(path="TempMeas_temp_"+str(config["fridge_temp"]), outerFolder=outerFolder, cfg=config,
#                                                soc=soc, soccfg=soccfg)
# data_SingleShot = SingleShotProgram.acquire(Instance_SingleShotProgram)
# SingleShotProgram.save_data(Instance_SingleShotProgram, data_SingleShot)
# SingleShotProgram.save_config(Instance_SingleShotProgram)
# SingleShotProgram.display(Instance_SingleShotProgram, data_SingleShot, plotDisp=True, save_fig=True)
#
# # # # #

# ####################################################################################################################
###################################### QNDness measurement
UpdateConfig = {
    ##### set yoko
    "yokoVoltage": -0.5,
    "yokoVoltage_freqPoint": -0.5,
    ###### cavity
    "reps": 2000,  # this will used for all experiements below unless otherwise changed in between trials
    "read_pulse_style": "const", # --Fixed
    "read_length": 15, # us
    "read_pulse_gain": 6000, # [DAC units]
    "read_pulse_freq": 7392.25, # [MHz]
    ##### qubit spec parameters
    "qubit_pulse_style": "flat_top",
    "qubit_gain": 23000,
    # "qubit_length": 10,  ###us, this is used if pulse style is const
    "sigma": 0.005,  ### units us, define a 20ns sigma
    "flat_top_length": 10.0, ### in us
    "qubit_freq": 4819,
    "relax_delay": 0.01,  ### turned into us inside the run function
    #### define shots
    "shots": 20000000, ### this gets turned into "reps"
    #### define info for clustering
    "cen_num": 2,
#     ##### record the fridge temperature in units of mK
    "fridge_temp": fridge_temp,
}
config = BaseConfig | UpdateConfig

outerFolder = "Z:\\TantalumFluxonium\\Data\\2023_10_31_BF2_cooldown_6\\WTF\\QND_Checks\\Yoko_"+str(config["yokoVoltage_freqPoint"])+"\\"

yoko1.SetVoltage(config["yokoVoltage"])

Instance_QNDmeas = QNDmeas(path="QND_Meas_temp_"+str(config["fridge_temp"]), outerFolder=outerFolder, cfg=config,
                                               soc=soc, soccfg=soccfg)
data_QNDmeas = QNDmeas.acquire(Instance_QNDmeas)
QNDmeas.save_data(Instance_QNDmeas, data_QNDmeas)
QNDmeas.save_config(Instance_QNDmeas)
print('data saved: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
#
# ##### loop over readout parameters and try to improve QNDness
# # ##### run the QND loop
# loop_len = 11
# loop_param = "read_pulse_gain"
# loop_vec = np.linspace(5000, 10000, loop_len, dtype=int)
#
# QND = []
# QND_err = []
#
# state0_0_prob = []
# state0_1_prob = []
# state0_prob_err = []
# state0_num = []
#
# state1_0_prob = []
# state1_1_prob = []
# state1_prob_err = []
# state1_num = []
#
# for idx in range(loop_len):
#     # config["read_pulse_freq"] = read_freq_vec[idx]
#     config[loop_param] = loop_vec[idx]
#     Instance_QNDmeas = QNDmeas(path="QND_Meas_Sweeps_temp_" + str(config["fridge_temp"]), outerFolder=outerFolder, cfg=config,
#                                soc=soc, soccfg=soccfg)
#     data_QNDmeas = QNDmeas.acquire(Instance_QNDmeas)
#     QNDmeas.save_data(Instance_QNDmeas, data_QNDmeas)
#     QNDmeas.save_config(Instance_QNDmeas)
#
#     state0_0_prob.append(data_QNDmeas['data']['state0_probs'][0])
#     state0_1_prob.append(data_QNDmeas['data']['state0_probs'][1])
#     state0_prob_err.append(data_QNDmeas['data']['state0_probs_err'][0])
#     state0_num.append(data_QNDmeas['data']['state0_num'])
#
#     state1_0_prob.append(data_QNDmeas['data']['state1_probs'][0])
#     state1_1_prob.append(data_QNDmeas['data']['state1_probs'][1])
#     state1_prob_err.append(data_QNDmeas['data']['state1_probs_err'][0])
#     state1_num.append(data_QNDmeas['data']['state1_num'])
#
#     QND.append(data_QNDmeas['data']['QND'])
#     QND_err.append(data_QNDmeas['data']['QND_err'])
#
#     print(idx)
# ###########
#
# fig, axs = plt.subplots(3,1, figsize = (8, 6))
#
# axs[0].errorbar(loop_vec, state0_0_prob, state0_prob_err, marker = 'o', ls = 'none')
# axs[0].errorbar(loop_vec, state1_1_prob, state1_prob_err, marker = 'o', ls = 'none')
# axs[0].set_xlabel(loop_param)
# axs[0].set_ylabel('state populations')
#
# axs[1].plot(loop_vec, state0_num)
# axs[1].plot(loop_vec, state1_num)
# axs[1].set_xlabel(loop_param)
# axs[1].set_ylabel('state populations')
#
# axs[2].errorbar(loop_vec, QND, QND_err)
# axs[2].set_xlabel(loop_param)
# axs[2].set_ylabel('QND fidelity')
#
# plt.tight_layout()

#####################################################################################################################
print('program complete: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
plt.show()

