#### import packages
import os
path = os.getcwd()
os.add_dll_directory(os.path.dirname(path)+'\\PythonDrivers')
from WorkingProjects.Tantalum_fluxonium.Client_modules.Calib_escher.initialize import *
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mSingleShotProgram import SingleShotProgram
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mSingleShot_2Dsweep import SingleShot_2Dsweep
# from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mT1_ThermalPS import T1_ThermalPS
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mT1_ThermalPS_pulse import T1_ThermalPS
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mSingleShotPS import SingleShotPS
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mAmplitudeRabiBlob_PS import AmplitudeRabi_PS
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mAmplitudeRabiFlux_PS import AmplitudeRabiFlux_PS
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mT2R_PS import T2R_PS
from matplotlib import pyplot as plt
import datetime
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mT1_PS import T1_PS
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mRepeatReadout import RepeatReadout

#### define the saving path
# outerFolder = "Z:\\TantalumFluxonium\\Data\\2023_10_31_BF2_cooldown_6\\WTF\\"
outerFolder = "Z:\\TantalumFluxonium\\Data\\2023_10_31_BF2_cooldown_6\\WTF\\TempChecks\\"
#################################### Running the actual experiments

# Only run this if no proxy already exists
soc, soccfg = makeProxy()
# # print(soccfg)

print('program starting: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
#
# plt.ioff()
#
#

# ####################################################################################################################
# # ####################################### code for running basic single shot exerpiment
# UpdateConfig = {
#     ##### set yoko
#     "yokoVoltage": -0.50,
#     ###### cavity
#     "reps": 2000,  # this will used for all experiements below unless otherwise changed in between trials
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 15, # [Clock ticks]
#     "read_pulse_gain":  6000, # [DAC units]
#     "read_pulse_freq": 7392.25, # [MHz]
#     ##### qubit spec parameters
#     "qubit_pulse_style": "flat_top",
#     "qubit_gain": 20000,
#     # "qubit_length": 10,  ###us, this is used if pulse style is const
#     "sigma": 0.005,  ### units us, define a 20ns sigma
#     "flat_top_length": 1.0, ### in us
#     "qubit_freq": 4827,
#     "relax_delay": 500,  ### turned into us inside the run function
#     #### define shots
#     "shots": 2000, ### this gets turned into "reps"
#     ##### record the fridge temperature in units of mK
#     "fridge_temp": 10,
# }
# config = BaseConfig | UpdateConfig
#
# yoko1.SetVoltage(config["yokoVoltage"])
#
# outerFolder = "Z:\\TantalumFluxonium\\Data\\2023_10_31_BF2_cooldown_6\\WTF\\TempChecks\\"
#
#
# Instance_SingleShotProgram = SingleShotProgram(path="SingleShot_yoko_"+str(config["yokoVoltage"]), outerFolder=outerFolder, cfg=config,
#                                                soc=soc, soccfg=soccfg)
# data_SingleShot = SingleShotProgram.acquire(Instance_SingleShotProgram)
# SingleShotProgram.save_data(Instance_SingleShotProgram, data_SingleShot)
# SingleShotProgram.save_config(Instance_SingleShotProgram)
# SingleShotProgram.display(Instance_SingleShotProgram, data_SingleShot, plotDisp=True, save_fig=True)

# ########
# ##### run the single shot experiment
# outerFolder = "Z:\\TantalumFluxonium\\Data\\2023_10_31_BF2_cooldown_6\\WTF\\singleShotSweeps\\"
# loop_len = 21
# freq_vec = config["read_pulse_freq"] + np.linspace(-0.5, 0.5, loop_len)
# # qubit_gain_vec = np.linspace(10000, 20000, loop_len, dtype=int)
# # read_gain_vec = np.linspace(4000, 5000, loop_len, dtype=int)
# for idx in range(loop_len):
#     config["read_pulse_freq"] = freq_vec[idx]
#     # config["qubit_gain"] = qubit_gain_vec[idx]
#     # config["read_pulse_gain"] = read_gain_vec[idx]
#     Instance_SingleShotProgram = SingleShotProgram(path="SingleShot_sweeps_yoko_"+str(config["yokoVoltage"]), outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
#     data_SingleShot = SingleShotProgram.acquire(Instance_SingleShotProgram)
#     # SingleShotProgram.display(Instance_SingleShotProgram, data_SingleShot, plotDisp=True, save_fig=False)
#     # ## SingleShotProgram.save_data(Instance_SingleShotProgram, data_SingleShot)
#     # ## SingleShotProgram.save_config(Instance_SingleShotProgram)
#     # plt.show()
#
#     SingleShotProgram.display(Instance_SingleShotProgram, data_SingleShot, plotDisp=True, save_fig=True)
#     plt.clf()
#     print(idx)
# ###########
####################################################################################################################

# ##################################################################################
# ################## code finding T1 of a thermal state
# UpdateConfig = {
#     ##### set yoko
#     "yokoVoltage": -0.29,
#     ###### cavity
#     #"reps": 0,  # this line does nothing, is overwritten with "shots"
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 20, # [Clock ticks]
#     "read_pulse_gain": 8000, # [DAC units]
#     "read_pulse_freq": 7392.15, # [MHz]
#     ##### qubit spec parameters
#     "qubit_pulse_style": "arb",
#     "qubit_gain": 0,
#     # "qubit_length": 10,  ###us, this is used if pulse style is const
#     "sigma": 0.3,  ### units us, define a 20ns sigma
#     "qubit_freq": 1715.6,
#     "relax_delay": 1000,  ### turned into us inside the run function
#     #### define shots
#     "shots": 7000, ### this gets turned into "reps"
#     ### define the wait times
#     "wait_start": 0,
#     "wait_stop": 20000,
#     "wait_num": 21,
#     ##### define number of clusters to use
#     "cen_num": 2,
#     ##### record the fridge temperature in units of mK
#     "fridge_temp": 10,
# }
# config = BaseConfig | UpdateConfig
#
# yoko1.SetVoltage(config["yokoVoltage"])
#
# print('starting scan: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
# Instance_T1_ThermalPS = T1_ThermalPS(path="dataTestT1_ThermalPS_yoko_"+str(config["yokoVoltage"]), outerFolder=outerFolder, cfg=config,
#                                                soc=soc, soccfg=soccfg)
# data_T1_ThermalPS = T1_ThermalPS.acquire(Instance_T1_ThermalPS)
# # T1_ThermalPS.display(Instance_T1_ThermalPS, data_T1_ThermalPS, plotDisp=True, save_fig=True)
# T1_ThermalPS.save_data(Instance_T1_ThermalPS, data_T1_ThermalPS)
#
# print('end of scan: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))


# ####################################################################################################################
# ################ code finding T1 of a thermal state using pulses
# UpdateConfig = {
#     ##### set yoko
#     "yokoVoltage": -0.5,
#     ###### cavity
#     #"reps": 0,  # this line does nothing, is overwritten with "shots"
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 15, # [Clock ticks]
#     "read_pulse_gain": 6000, # [DAC units]
#     "read_pulse_freq": 7392.25, # [MHz]
#     ##### qubit spec parameters
#     "qubit_pulse_style": "flat_top",
#     "qubit_gain": 20000, #12000,
#     # "qubit_length": 10,  ###us, this is used if pulse style is const
#     "sigma": 0.005,  ### units us, define a 20ns sigma
#     "flat_top_length": 1.0,
#     "qubit_freq": 4827,
#     "relax_delay": 10,  ### turned into us inside the run function
#     #### define shots
#     "shots": 5000, ### this gets turned into "reps"
#     ### define the wait times
#     "wait_start": 0,
#     "wait_stop": 1000,
#     "wait_num": 41,
#     ##### define number of clusters to use
#     "cen_num": 2,
#     ##### record the fridge temperature in units of mK
#     "fridge_temp": 10,
# }
# config = BaseConfig | UpdateConfig
#
# yoko1.SetVoltage(config["yokoVoltage"])
# print('starting scan: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
#
# Instance_T1_PS = T1_PS(path="T1_PS_yoko_"+str(config["yokoVoltage"]), outerFolder=outerFolder, cfg=config,
#                                                soc=soc, soccfg=soccfg)
# data_T1_PS = T1_PS.acquire(Instance_T1_PS)
# T1_PS.save_data(Instance_T1_PS, data_T1_PS)
# T1_PS.save_config(Instance_T1_PS)
#
# print('end of scan: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
####################################################################################################################

# ####################################### code for measuring the qubit temp using single shot
UpdateConfig = {
    ##### set yoko
    "yokoVoltage": -0.50,
    ###### cavity
    "reps": 2000,  # this will used for all experiements below unless otherwise changed in between trials
    "read_pulse_style": "const", # --Fixed
    "read_length": 15, # [Clock ticks]
    "read_pulse_gain":  6000, # [DAC units]
    "read_pulse_freq": 7392.25, # [MHz]
    ##### qubit spec parameters
    "qubit_pulse_style": "arb",
    "qubit_gain": 0,
    # "qubit_length": 10,  ###us, this is used if pulse style is const
    "sigma": 0.005,  ### units us, define a 20ns sigma
    # "flat_top_length": 1.0, ### in us
    "qubit_freq": 10,
    "relax_delay": 1000,  ### turned into us inside the run function
    #### define shots
    "shots": 500000, ### this gets turned into "reps"
    ##### record the fridge temperature in units of mK
    "fridge_temp": 10,
}
config = BaseConfig | UpdateConfig

yoko1.SetVoltage(config["yokoVoltage"])

Instance_SingleShotProgram = SingleShotProgram(path="TempMeas_yoko_"+str(config["yokoVoltage"]), outerFolder=outerFolder, cfg=config,
                                               soc=soc, soccfg=soccfg)
data_SingleShot = SingleShotProgram.acquire(Instance_SingleShotProgram)
SingleShotProgram.save_data(Instance_SingleShotProgram, data_SingleShot)
SingleShotProgram.save_config(Instance_SingleShotProgram)
SingleShotProgram.display(Instance_SingleShotProgram, data_SingleShot, plotDisp=True, save_fig=True)


#####################################################################################################################
print('program complete: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
plt.show()

