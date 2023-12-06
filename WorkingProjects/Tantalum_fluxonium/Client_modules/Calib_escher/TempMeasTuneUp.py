#### import packages
import os

import numpy as np

path = os.getcwd()
os.add_dll_directory(os.path.dirname(path)+'\\PythonDrivers')
from WorkingProjects.Tantalum_fluxonium.Client_modules.Calib_escher.initialize import *
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mSingleShotProgram import SingleShotProgram
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mSingleShotTemp_sse import SingleShotSSE
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mSingleShot_2Dsweep import SingleShot_2Dsweep
# from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mT1_ThermalPS import T1_ThermalPS
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mT1_ThermalPS_pulse import T1_ThermalPS
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mT1_PS_sse import T1_PS_sse
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
UpdateConfig = {
    ##### set yoko
    "yokoVoltage": -0.23,
    "yokoVoltage_freqPoint": -0.23,
    ###### cavity
    "reps": 2000,  # this will used for all experiements below unless otherwise changed in between trials
    "read_pulse_style": "const", # --Fixed
    "read_length": 10, # [Clock ticks]
    "read_pulse_gain": 8000, # [DAC units]
    "read_pulse_freq": 7392.14, # [MHz]
    ##### qubit spec parameters
    "qubit_pulse_style": "arb",
    "qubit_gain": 0,
    # "qubit_length": 10,  ###us, this is used if pulse style is const
    "sigma": 0.005,  ### units us, define a 20ns sigma
    "flat_top_length": 10, ### in us
    "qubit_freq": 600,
    "relax_delay": 1000,  ### turned into us inside the run function
    #### define shots
    "shots": 5000, ### this gets turned into "reps"
    ##### record the fridge temperature in units of mK
    "fridge_temp": fridge_temp,
}
config = BaseConfig | UpdateConfig

yoko1.SetVoltage(config["yokoVoltage"])

outerFolder = "Z:\\TantalumFluxonium\\Data\\2023_10_31_BF2_cooldown_6\\WTF\\TempChecks\\Yoko_"+str(config["yokoVoltage_freqPoint"])+"\\"
Instance_SingleShotProgram = SingleShotProgram(path="SingleShot_temp_"+str(config["fridge_temp"]), outerFolder=outerFolder, cfg=config,
                                               soc=soc, soccfg=soccfg)
data_SingleShot = SingleShotProgram.acquire(Instance_SingleShotProgram)
SingleShotProgram.save_data(Instance_SingleShotProgram, data_SingleShot)
SingleShotProgram.save_config(Instance_SingleShotProgram)
SingleShotProgram.display(Instance_SingleShotProgram, data_SingleShot, plotDisp=True, save_fig=True)

# # ##### run the single shot experiment
# outerFolder = "Z:\\TantalumFluxonium\\Data\\2023_10_31_BF2_cooldown_6\\WTF\\singleShotSweeps\\"
# loop_len = 21
# freq_vec = config["read_pulse_freq"] + np.linspace(-0.3, 0.3, loop_len)
# # qubit_gain_vec = np.linspace(10000, 20000, loop_len, dtype=int)
# # read_gain_vec = np.linspace(12000, 15000, loop_len, dtype=int)
# # qubit_freq_vec = config["qubit_freq"] + np.linspace(-10,10,loop_len)
# # qubit_gain_vec = np.linspace(20000,31000, loop_len, dtype = int)
# # flat_top_length_vec = np.linspace(1,40,loop_len, dtype = int)
# for idx in range(loop_len):
#     config["read_pulse_freq"] = freq_vec[idx]
#     # config["qubit_gain"] = qubit_gain_vec[idx]
#     # config["read_pulse_gain"] = read_gain_vec[idx]
#     # config["qubit_freq"] = qubit_freq_vec[idx]
#     # config['flat_top_length'] = flat_top_length_vec[idx]
#     Instance_SingleShotProgram = SingleShotProgram(path="SingleShot_sweeps_yoko_"+str(config["yokoVoltage"]), outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
#     data_SingleShot = SingleShotProgram.acquire(Instance_SingleShotProgram)
#     SingleShotProgram.display(Instance_SingleShotProgram, data_SingleShot, plotDisp=False, save_fig=True)
#     SingleShotProgram.save_data(Instance_SingleShotProgram, data_SingleShot)
#     SingleShotProgram.save_config(Instance_SingleShotProgram)
#     plt.clf()
#     plt.close()
#     plt.clf()
#     print(idx)
# ###########


# ##################################################################################
# ################## code finding T1 of a thermal state with and without pulses
#
# # time.sleep(300)
# UpdateConfig = {
#     ##### set yoko
#     "yokoVoltage": -0.23,
#     "yokoVoltage_freqPoint": -0.23,
#     ###### cavity
#     #"reps": 0,  # this line does nothing, is overwritten with "shots"
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 10, # [Clock ticks]
#     "read_pulse_gain": 8000, # [DAC units]
#     "read_pulse_freq": 7392.17, # [MHz]
#     ##### qubit spec parameters
#     "qubit_pulse_style": "arb",
#     "qubit_gain": 0,
#     "flat_top_length":10,
#     # "qubit_length": 10,  ###us, this is used if pulse style is const
#     "sigma": 0.005,  ### units us, define a 20ns sigma
#     "qubit_freq": 600,
#     "relax_delay": 2000,  ### turned into us inside the run function
#     #### define shots
#     "shots": 10000, ### this gets turned into "reps"
#     ### define the wait times
#     "wait_start": 0,
#     "wait_stop": 50,
#     "wait_num": 4,
#     'wait_type': 'linear',
#     ##### define number of clusters to use
#     "cen_num": 2,
#     ##### record the fridge temperature in units of mK
#     "fridge_temp": fridge_temp,
# }
# config = BaseConfig | UpdateConfig
#
# yoko1.SetVoltage(config["yokoVoltage"])
#
# outerFolder = "Z:\\TantalumFluxonium\\Data\\2023_10_31_BF2_cooldown_6\\WTF\\TempChecks\\Yoko_"+str(config["yokoVoltage_freqPoint"])+"\\"
#
# ########
# ## calculate an estimate of the scan time
# time_per_scan = config["shots"] * (np.linspace(config["wait_start"], config["wait_stop"], config["wait_num"]) + config["relax_delay"])*1e-6
# total_time = np.sum(time_per_scan) /60
# print('total time estimate: ' + str(total_time) + " minutes" )
# #########
#
# print('starting scan: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
# Instance_T1_PS = T1_PS_sse(path="T1_PS_temp_"+str(config["fridge_temp"]), outerFolder=outerFolder, cfg=config,
#                                                soc=soc, soccfg=soccfg)
# data_T1_PS = Instance_T1_PS.acquire()
# data_T1_PS = Instance_T1_PS.process_data(data_T1_PS)
# Instance_T1_PS.save_data(data_T1_PS)
# Instance_T1_PS.save_config()
# Instance_T1_PS.display(data_T1_PS, plotDisp=True)
#
# print('end of scan: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))

# # # # ####################################### code for measuring the qubit temp using single shot
# UpdateConfig = {
#     ##### set yoko
#     "yokoVoltage": -0.22,
#     "yokoVoltage_freqPoint": -0.22,
#     ###### cavity
#     "reps": 2000,  # this will be used for all experiments below unless otherwise changed in between trials
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 10, # [Clock ticks]
#     "read_pulse_gain": 8000, # [DAC units]
#     "read_pulse_freq": 7392.14, # [MHz]
#     ##### qubit spec parameters
#     "qubit_pulse_style": "arb",
#     "qubit_gain": 0,
#     "sigma": 0.005,  ### units us, define a 20ns sigma
#     "qubit_freq": 495,
#     "relax_delay": 25000,  ### turned into us inside the run function
#     "flat_top_length":10,
#     #### define shots
#     "shots": 10000, ### this gets turned into "reps"
#     ##### record the fridge temperature in units of mK
#     "fridge_temp": fridge_temp,
# }
# config = BaseConfig | UpdateConfig
#
# yoko1.SetVoltage(config["yokoVoltage"])
#
# outerFolder = "Z:\\TantalumFluxonium\\Data\\2023_10_31_BF2_cooldown_6\\WTF\\TempChecks\\Yoko_"+str(config["yokoVoltage_freqPoint"])+"\\"
# time_required = config["shots"]*config["relax_delay"]*1e-6/60
# print("Time required is ", time_required, " mins")
#
# Instance_SingleShotProgram = SingleShotSSE(path="TempMeas_temp_"+str(config["fridge_temp"]), outerFolder=outerFolder, cfg=config,
#                                                soc=soc, soccfg=soccfg)
# data_SingleShot = Instance_SingleShotProgram.acquire()
# data_SingleShot = Instance_SingleShotProgram.process_data(data_SingleShot, bin_size = 51)
# Instance_SingleShotProgram.save_data(data_SingleShot)
# Instance_SingleShotProgram.save_config()
# Instance_SingleShotProgram.display(data_SingleShot, plotDisp=True, save_fig=True)

# # # #

# ####################################################################################################################
###################################### QNDness measurement
# UpdateConfig = {
#     ##### set yoko
#     "yokoVoltage": -0.22,
#     "yokoVoltage_freqPoint": -0.22,
#     ###### cavity
#     "reps": 2000,  # this will used for all experiements below unless otherwise changed in between trials
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 5, # us
#     "read_pulse_gain": 8000, # [DAC units]
#     "read_pulse_freq": 7392.14, # [MHz]
#     ##### qubit spec parameters
#     "qubit_pulse_style": "arb",
#     "qubit_gain": 0,
#     # "qubit_length": 10,  ###us, this is used if pulse style is const
#     "sigma": 0.005,  ### units us, define a 20ns sigma
#     "flat_top_length": 10.0, ### in us
#     "qubit_freq": 495,
#     "relax_delay": 0.01,  ### turned into us inside the run function
#     #### define shots
#     "shots": 1000000, ### this gets turned into "reps"
#     #### define info for clustering
#     "cen_num": 2,
# #     ##### record the fridge temperature in units of mK
#     "fridge_temp": fridge_temp,
# }
# config = BaseConfig | UpdateConfig
#
# outerFolder = "Z:\\TantalumFluxonium\\Data\\2023_10_31_BF2_cooldown_6\\WTF\\QND_Checks\\Yoko_"+str(config["yokoVoltage_freqPoint"])+"\\"
#
# yoko1.SetVoltage(config["yokoVoltage"])
#
# Instance_QNDmeas = QNDmeas(path="QND_Meas_temp_"+str(config["fridge_temp"]), outerFolder=outerFolder, cfg=config,
#                                                soc=soc, soccfg=soccfg)
# data_QNDmeas = Instance_QNDmeas.acquire()
# data_QNDmeas = Instance_QNDmeas.process_data(data_QNDmeas, toPrint=True, confidence_selection=0.95)
# Instance_QNDmeas.save_data(data_QNDmeas)
# Instance_QNDmeas.save_config()
# Instance_QNDmeas.display(data_QNDmeas, plotDisp=True)
# print('data saved: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))

# #
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

