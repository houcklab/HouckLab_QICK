#### import packages
import os

import numpy as np

path = os.getcwd()
os.add_dll_directory(os.path.dirname(path) + '\\PythonDrivers')
from WorkingProjects.Tantalum_fluxonium.Client_modules.Calib.initialize import *
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mSingleShotProgram import SingleShotProgram
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mSingleShotProgram_switch import SingleShot_SwitchProgram
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mSingleShot_2Dsweep import SingleShot_2Dsweep
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mT1_ThermalPS import T1_ThermalPS
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mT1_ThermalPS_withERROR import T1_ThermalPS_Err
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mT1_PS import T1_PS
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mT2R_PS import T2R_PS
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mSingleShotPS import SingleShotPS
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mAmplitudeRabiBlob_PS import AmplitudeRabi_PS
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mAmplitudeRabiFlux_PS import AmplitudeRabiFlux_PS

from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mRepeatReadout import RepeatReadout

from matplotlib import pyplot as plt
import datetime

#### define the saving path
outerFolder = "Z:\\TantalumFluxonium\\Data\\2023_10_31_BF2_cooldown_6\\TF4\\"

###qubitAtten = attenuator(27797, attenuation_int= 10, print_int = False)


#################################### Running the actual experiments

# # Only run this if no proxy already exists
# soc, soccfg = makeProxy()
# # print(soccfg)
#
# plt.ioff()
#

# #################################### code for running basic single shot exerpiment
# UpdateConfig = {
#     ##### set yoko
#     "yokoVoltage": -2.8,
#     ###### cavity
#     "reps": 2000,  # this will used for all experiements below unless otherwise changed in between trials
#     "read_pulse_style": "const",  # --Fixed
#     "read_length": 5,  # [Clock ticks]
#     "read_pulse_gain": 8000,  # [DAC units]
#     "read_pulse_freq": 6437.4,  # [MHz]
#     ##### qubit spec parameters
#     "qubit_pulse_style": "flat_top",
#     "qubit_gain": 25000,
#     # "qubit_length": 10,  ###us, this is used if pulse style is const
#     "sigma": 0.025,  ### units us
#     "flat_top_length": 0.900,  ### in us
#     "qubit_freq": 3513.0,
#     "relax_delay": 1000,  ### turned into us inside the run function
#     #### define shots
#     "shots": 2000,  ### this gets turned into "reps"
#     ### Added for switch
#     "trig_buffer_start": 0.035, # in us
#     "trig_buffer_end": 0.024, # in us
#     "trig_delay": 0.07, # in us
#
# }
# config = BaseConfig | UpdateConfig
#
# yoko1.SetVoltage(config["yokoVoltage"])
#
# Instance_SingleShotProgram = SingleShotProgram(path="dataTestSingleShotProgram", outerFolder=outerFolder, cfg=config,
#                                                soc=soc, soccfg=soccfg)
# data_SingleShot = SingleShotProgram.acquire(Instance_SingleShotProgram)
# SingleShotProgram.display(Instance_SingleShotProgram, data_SingleShot, plotDisp=True, save_fig=True)
# SingleShotProgram.save_data(Instance_SingleShotProgram, data_SingleShot)
# SingleShotProgram.save_config(Instance_SingleShotProgram)

# # ##### run the single shot experiment
# loop_len = 11
# freq_vec = config["read_pulse_freq"] + np.linspace(-0.25, 0.25, loop_len)
# # qubit_gain_vec = np.linspace(10000, 20000, loop_len, dtype=int)
# # read_gain_vec = np.linspace(4000, 5000, loop_len, dtype=int)
# # yoko_vec = config["yokoVoltage"] + np.linspace(-0.02, 0.02, 21)
# for idx in range(loop_len):
#     config["read_pulse_freq"] = freq_vec[idx]
#     # config["qubit_gain"] = qubit_gain_vec[idx]
#     # config["read_pulse_gain"] = read_gain_vec[idx]
#     # yoko1.SetVoltage(yoko_vec[idx])
#     Instance_SingleShotProgram = SingleShotProgram(path="dataTestSingleShotProgram_paramSweep_q2", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
#     data_SingleShot = SingleShotProgram.acquire(Instance_SingleShotProgram)
#     # SingleShotProgram.display(Instance_SingleShotProgram, data_SingleShot, plotDisp=True, save_fig=False)
#     # ## SingleShotProgram.save_data(Instance_SingleShotProgram, data_SingleShot)
#     # ## SingleShotProgram.save_config(Instance_SingleShotProgram)
#     # plt.show()
#
#     SingleShotProgram.display(Instance_SingleShotProgram, data_SingleShot, plotDisp=True, save_fig=True)
#     plt.clf()
#     print(idx)


#
# # ####################################### code for running  2D single shot fidelity optimization
# UpdateConfig = {
#     ##### set yoko
#     "yokoVoltage": 0.8,
#     #### define basic parameters
#     ###### cavity
#     "reps": 500,  # this will used for all experiements below unless otherwise changed in between trials
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 10, # [Clock ticks]
#     "read_pulse_gain": 6600, # [DAC units]
#     "read_pulse_freq": 6438, # [MHz]
#     ##### qubit spec parameters
#     "qubit_pulse_style": "arb",
#     "qubit_gain": 1230,
#     # "qubit_length": 10,  ###us, this is used if pulse style is const
#     "sigma": 0.05,  ### units us, define a 20ns sigma
#     # "flat_top_length": 0.250,
#     "qubit_freq": 2691.07,
#     "relax_delay": 2000,  ### turned into us inside the run function
#     #### define shots
#     "shots": 1000, ### this gets turned into "reps"
#     #### define the loop parameters
#
#     "x_var": "qubit_freq",
#     "x_start": 2691.0 - 0.1,
#     "x_stop": 2691.0 + 0.1,
#     "x_num": 9,
#
#     "y_var": "qubit_gain",
#     "y_start": 700,
#     "y_stop": 1200,
#     "y_num": 11,
# }
# config = BaseConfig | UpdateConfig
#
# yoko1.SetVoltage(config["yokoVoltage"])
#
# Instance_SingleShot_2Dsweep = SingleShot_2Dsweep(path="dataTestSingleShot_2Dsweep", outerFolder=outerFolder, cfg=config,
#                                                soc=soc, soccfg=soccfg)
# data_SingleShot_2Dsweep = SingleShot_2Dsweep.acquire(Instance_SingleShot_2Dsweep, switch=True)
# SingleShot_2Dsweep.save_data(Instance_SingleShot_2Dsweep, data_SingleShot_2Dsweep)
# SingleShot_2Dsweep.save_config(Instance_SingleShot_2Dsweep)

#
# # TITLE: T1 of a thermal state
# # region Config File
# UpdateConfig = {
#     # Define yoko
#     "yokoVoltage": -2.25,
#
#     # Cavity Parameters
#     "read_pulse_style": "const",  # --Fixed
#     "read_length": 10,  # [Clock ticks]
#     "read_pulse_gain": 8000,  # [DAC units]
#     "read_pulse_freq": 6436.95,  # [MHz]
#
#     # Qubit spec parameters
#     "qubit_pulse_style": "arb",
#     "qubit_gain": 0,
#     # "qubit_length": 10,  ###us, this is used if pulse style is const
#     "sigma": 0.0,  ### units us, define a 20ns sigma
#     "qubit_freq": 0,
#     "relax_delay": 2000,  ### turned into us inside the run function
#
#     # Define shots
#     "shots": 10000,  ### this gets turned into "reps"
#
#     # Define the wait times
#     "wait_start": 1,
#     "wait_stop": 2001,
#     "wait_num": 21,
#
#     # Define number of clusters to use
#     "cen_num": 2,
# }
# config = BaseConfig | UpdateConfig
# yoko1.SetVoltage(config["yokoVoltage"])
# print('starting scan: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
# Instance_T1_ThermalPS_Err = T1_ThermalPS_Err(path="dataTestT1_ThermalPS_Err", outerFolder=outerFolder, cfg=config,
#                                              soc=soc, soccfg=soccfg)
# data_T1_ThermalPS_Err = T1_ThermalPS_Err.acquire(Instance_T1_ThermalPS_Err)
# # T1_ThermalPS_Err.display(Instance_T1_ThermalPS_Err, data_T1_ThermalPS_Err, plotDisp=True, save_fig=True)
# T1_ThermalPS_Err.save_data(Instance_T1_ThermalPS_Err, data_T1_ThermalPS_Err)
# T1_ThermalPS_Err.save_config(Instance_T1_ThermalPS_Err)
# print('end of scan: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))

# # #### loop over different flux points
# # yoko_vec = -3.825 + np.linspace(-0.050, 0.050, 11)
# #
# # print(yoko_vec)
# #
# # for idx in range(len(yoko_vec)):
# #     print('starting run number ' + str(idx))
# #     config["yokoVoltage"] = yoko_vec[idx]
# #     yoko1.SetVoltage(config["yokoVoltage"])
# #     print('starting scan: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
# #
# #     Instance_T1_ThermalPS = T1_ThermalPS(path="dataTestT1_ThermalPS_YokoSweep", outerFolder=outerFolder, cfg=config,
# #                                          soc=soc, soccfg=soccfg)
# #     data_T1_ThermalPS = T1_ThermalPS.acquire(Instance_T1_ThermalPS)
# #     # T1_ThermalPS.display(Instance_T1_ThermalPS, data_T1_ThermalPS, plotDisp=True, save_fig=True)
# #     T1_ThermalPS.save_data(Instance_T1_ThermalPS, data_T1_ThermalPS)
# #     T1_ThermalPS.save_config(Instance_T1_ThermalPS)
# #
# #     print('end of scan: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
# #
# #     print('finished run number ' + str(idx))
# endregion

# # ##############################################################################################################
# ####################################### code for running basic single shot experiment with post selection
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

# # # # #####################################################################################################################
# ###################################### code for running Amplitude rabi Blob with post selection
# UpdateConfig = {
#     ##### define attenuators
#     "yokoVoltage": -4.537,
#     ###### cavity
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 10, # us
#     "read_pulse_gain": 7000, # [DAC units]
#     "read_pulse_freq": 6032.15, # [MHz]
#     ##### spec parameters for finding the qubit frequency
#     "qubit_freq_start": 93,
#     "qubit_freq_stop": 98,
#     "RabiNumPoints": 11,  ### number of points
#     "qubit_pulse_style": "flat_top",
#     "sigma": 0.010,  ### units us, define a 20ns sigma
#     "flat_top_length": 0.150, ### in us
#     "relax_delay": 500,  ### turned into us inside the run function
#     ##### amplitude rabi parameters
#     "qubit_gain_start": 20000,
#     "qubit_gain_step": 500, ### stepping amount of the qubit gain
#     "qubit_gain_expts": 21, ### number of steps
#     # "AmpRabi_reps": 2000,  # number of averages for the experiment
#     ##### define number of clusters to use
#     "cen_num": 2,
#     "shots": 4000,  ### this gets turned into "reps"
# }
# config = BaseConfig | UpdateConfig
#
# yoko1.SetVoltage(config["yokoVoltage"])
#
# Instance_AmplitudeRabi_PS = AmplitudeRabi_PS(path="dataTestAmplitudeRabi_PS", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg, progress=True)
# data_AmplitudeRabi_PS = AmplitudeRabi_PS.acquire(Instance_AmplitudeRabi_PS)
# AmplitudeRabi_PS.save_data(Instance_AmplitudeRabi_PS, data_AmplitudeRabi_PS)
# AmplitudeRabi_PS.save_config(Instance_AmplitudeRabi_PS)


SwitchConfig = {
    "trig_buffer_start": 0.035, # in us
    "trig_buffer_end": 0.024, # in us
    "trig_delay": 0.07, # in us
}
#
# ###############################################################################
################## code finding T1 of a thermal state using pulses
UpdateConfig = {
    ##### set yoko
    "yokoVoltage": -2.4,
    ###### cavity
    #"reps": 0,  # this line does nothing, is overwritten with "shots"
    "read_pulse_style": "const", # --Fixed
    "read_length": 10, # [Clock ticks]
    "read_pulse_gain": 7500,  # [DAC units]
    "read_pulse_freq": 6437.55 - 0.3,  # [MHz]
    ##### qubit spec parameters
    "qubit_pulse_style": "arb",
    "qubit_gain": 1400, #12000,
    # "qubit_length": 10,  ###us, this is used if pulse style is const
    "sigma": 0.100,  ### units us, define a 20ns sigma
    # "flat_top_length": 0.300,
    "qubit_freq": 3964.5,
    "relax_delay": 2000,  ### turned into us inside the run function
    #### define shots
    "shots": 10000, ### this gets turned into "reps"
    ### define the wait times
    "wait_start": 0,
    "wait_stop": 2000,
    "wait_num": 21,
    ##### define number of clusters to use
    "cen_num": 3,
    "use_switch": True,
}
config = BaseConfig | UpdateConfig | SwitchConfig

yoko1.SetVoltage(config["yokoVoltage"])
print('starting scan: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))

scan_time = (np.sum(np.linspace(config["wait_start"], config["wait_stop"], config["wait_num"])) + config["relax_delay"])*config["shots"] *1e-6 / 60

print('estimated time: ' + str(round(scan_time, 2)) + ' minutes')

Instance_T1_PS = T1_PS(path="dataTestT1_PS", outerFolder=outerFolder, cfg=config,
                                               soc=soc, soccfg=soccfg)
data_T1_PS = T1_PS.acquire(Instance_T1_PS)
T1_PS.save_data(Instance_T1_PS, data_T1_PS)
print('scan complete starting data processing: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
T1_PS.save_config(Instance_T1_PS)
T1_PS.process_data(Instance_T1_PS, data_T1_PS)

print('end of analysis: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))


# # # ####################################################################################
# ################## code finding T2R of a thermal state using pulses
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

# ##### loop over flux points
# yoko_vec = config["yokoVoltage"] + np.linspace(-0.002, 0.002, 5)
#
# print(yoko_vec)
#
# for idx in range(len(yoko_vec)):
#     print('starting run number ' + str(idx))
#     config["yokoVoltage"] = yoko_vec[idx]
#     yoko1.SetVoltage(config["yokoVoltage"])
#
#     print('yoko value: ' + str(config["yokoVoltage"]) )
#
#     print('starting scan: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
#
#     Instance_T2R_PS = T2R_PS(path="dataTestT2R_PS_yokoSweep", outerFolder=outerFolder, cfg=config,
#                              soc=soc, soccfg=soccfg)
#     data_T2R_PS = T2R_PS.acquire(Instance_T2R_PS)
#     T2R_PS.save_data(Instance_T2R_PS, data_T2R_PS)
#     T2R_PS.save_config(Instance_T2R_PS)
#
#     print('end of scan: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
#


# # ####################################### code for running repeated single shot measurements
# UpdateConfig = {
#     ##### set yoko
#     "yokoVoltage": -4.42,
#     ###### cavity
#     "reps": 2000,  # this will used for all experiements below unless otherwise changed in between trials
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 10, # [Clock ticks]
#     "read_pulse_gain": 3000, # [DAC units]
#     "read_pulse_freq": 6424.6, # [MHz]
#     ##### qubit spec parameters
#     "qubit_pulse_style": "flat_top",
#     "qubit_gain": 25000,
#     "qubit_length": 10,  ###us, this is used if pulse style is const
#     "sigma": 0.010,  ### units us
#     "flat_top_length": 0.200,  ### in us
#     "qubit_freq": 2218,
#     "relax_delay": 2000,  ### turned into us inside the run function
#     #### define shots
#     "shots": 5000, ### this gets turned into "reps"
#
#     ##### time parameters
#     "delay": 10, # s
#     "repetitions": 501,  ### number of steps
# }
# config = BaseConfig | UpdateConfig
#
# yoko1.SetVoltage(config["yokoVoltage"])
#
# Instance_RepeatReadout = RepeatReadout(path="dataTestRepeatReadout", outerFolder=outerFolder, cfg=config,
#                                                soc=soc, soccfg=soccfg)
# data_RepeatReadout = RepeatReadout.acquire(Instance_RepeatReadout)
# # RepeatReadout.display(Instance_SingleShotProgram, data_SingleShot, plotDisp=True, save_fig=True)
# RepeatReadout.save_data(Instance_RepeatReadout, data_RepeatReadout)
# RepeatReadout.save_config(Instance_RepeatReadout)

#####################################################################################################################
plt.show()
