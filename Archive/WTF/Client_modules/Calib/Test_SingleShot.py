
#### import packages
import os
path = os.getcwd()
os.add_dll_directory(os.path.dirname(path)+'\\PythonDrivers')
from STFU.Client_modules.Calib.initialize import *
from STFU.Client_modules.Experiments.mSingleShotProgram import SingleShotProgram
from STFU.Client_modules.Experiments.mSingleShot_2Dsweep import SingleShot_2Dsweep
from STFU.Client_modules.Experiments.mT1_ThermalPS import T1_ThermalPS
from STFU.Client_modules.Experiments.mSingleShotPS import SingleShotPS
from matplotlib import pyplot as plt

#### define the saving path
outerFolder = "Z:\JakeB\Data\Tantalum_Fluxonium\TF3SC1_B1\\"

###qubitAtten = attenuator(27797, attenuation_int= 10, print_int = False)


#################################### Running the actual experiments

# # Only run this if no proxy already exists
# soc, soccfg = makeProxy()
# # print(soccfg)
#
# plt.ioff()
#
#
# # # ####################################### code for running basic single shot exerpiment
# UpdateConfig = {
#     ##### set yoko
#     "yokoVoltage": -1.64,
#     ###### cavity
#     "reps": 2000,  # this will used for all experiements below unless otherwise changed in between trials
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 10, # [Clock ticks]
#     "read_pulse_gain": 6000, # [DAC units]
#     "read_pulse_freq": 6360.35 - 0.05*0, # [MHz]
#     ##### qubit spec parameters
#     "qubit_pulse_style": "arb",
#     "qubit_gain": 19000,
#     # "qubit_length": 10,  ###us, this is used if pulse style is const
#     "sigma": 0.200,  ### units us, define a 20ns sigma
#     "qubit_freq": 145.5,
#     "relax_delay": 2000,  ### turned into us inside the run function
#     #### define shots
#     "shots": 5000, ### this gets turned into "reps"
# }
# config = BaseConfig | UpdateConfig
# # #
# # # yoko1.SetVoltage(config["yokoVoltage"])
# # # # #
# # # # # ##### run the single shot experiment
# # # # # loop_len = 11
# # # # # #freq_vec = config["read_pulse_freq"] + np.linspace(-0.2, 0.2, loop_len)
# # # # # #qubit_gain_vec = np.linspace(10000, 29000, loop_len, dtype=int)
# # # # # read_gain_vec = np.linspace(4000, 5000, loop_len, dtype=int)
# # # # # fid_vec = np.zeros(loop_len)
# # # # # for idx in range(loop_len):
# # # # #     #config["read_pulse_freq"] = freq_vec[idx]
# # # # #     #config["qubit_gain"] = qubit_gain_vec[idx]
# # # # #     config["read_pulse_gain"] = read_gain_vec[idx]
# # # # #     Instance_SingleShotProgram = SingleShotProgram(path="dataTestSingleShotProgram", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
# # # # #     data_SingleShot = SingleShotProgram.acquire(Instance_SingleShotProgram)
# # # # #     SingleShotProgram.display(Instance_SingleShotProgram, data_SingleShot, plotDisp=False, save_fig=False)
# # # # #     # SingleShotProgram.save_data(Instance_SingleShotProgram, data_SingleShot)
# # # # #     # SingleShotProgram.save_config(Instance_SingleShotProgram)
# # # # #
# # # # #     plt.show()
# # # # #
# # # # #     fid_vec[idx] = Instance_SingleShotProgram.fid
# # # # #
# # # # # plt.figure(107)
# # # # # #plt.plot(qubit_gain_vec, fid_vec, 'o')
# # # # # #plt.xlabel('qubit gain')
# # # # #
# # # # # plt.plot(read_gain_vec, fid_vec, 'o')
# # # # # plt.xlabel('readout gain')
# # # # #
# # # # # # plt.plot(freq_vec, fid_vec, 'o')
# # # # # # plt.xlabel('read pulse freq')
# # # # # plt.ylabel('fidelity')
# # # # # plt.ylim([0,1])
# # # # #
# # # #
# Instance_SingleShotProgram = SingleShotProgram(path="dataTestSingleShotProgram", outerFolder=outerFolder, cfg=config,
#                                                soc=soc, soccfg=soccfg)
# data_SingleShot = SingleShotProgram.acquire(Instance_SingleShotProgram)
# SingleShotProgram.display(Instance_SingleShotProgram, data_SingleShot, plotDisp=True, save_fig=True)


####################################### code for running  2D single shot fidelity optimization
UpdateConfig = {
    ##### set yoko
    "yokoVoltage": -1.64,
    #### define basic parameters
    ###### cavity
    "reps": 2000,  # this will used for all experiements below unless otherwise changed in between trials
    "read_pulse_style": "const", # --Fixed
    "read_length": 10, # [Clock ticks]
    "read_pulse_gain": 6000, # [DAC units]
    "read_pulse_freq": 6360.35, # [MHz]
    ##### qubit spec parameters
    "qubit_pulse_style": "arb",
    "qubit_gain": 19000,
    # "qubit_length": 10,  ###us, this is used if pulse style is const
    "sigma": 0.100,  ### units us, define a 20ns sigma
    "qubit_freq": 145,
    "relax_delay": 1000,  ### turned into us inside the run function
    #### define shots
    "shots": 2000, ### this gets turned into "reps"
    #### define the loop parameters
    "x_var": "qubit_gain",
    "x_start": 15000,
    "x_stop": 30000,
    "x_num": 4,

    "y_var": "qubit_freq",
    "y_start": 135,
    "y_stop": 155,
    "y_num": 11,
}
config = BaseConfig | UpdateConfig

yoko1.SetVoltage(config["yokoVoltage"])

Instance_SingleShot_2Dsweep = SingleShot_2Dsweep(path="dataTestSingleShot_2Dsweep", outerFolder=outerFolder, cfg=config,
                                               soc=soc, soccfg=soccfg)
data_SingleShot_2Dsweep = SingleShot_2Dsweep.acquire(Instance_SingleShot_2Dsweep)
SingleShot_2Dsweep.save_data(Instance_SingleShot_2Dsweep, data_SingleShot_2Dsweep)
SingleShot_2Dsweep.save_config(Instance_SingleShot_2Dsweep)


# ####################################################################################
# ################### code finding T1 of a thermal state
# UpdateConfig = {
#     ##### set yoko
#     "yokoVoltage": -1.64,
#     ###### cavity
#     "reps": 2000,  # this will used for all experiements below unless otherwise changed in between trials
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 10, # [Clock ticks]
#     "read_pulse_gain": 6000, # [DAC units]
#     "read_pulse_freq": 6360.35, # [MHz]
#     ##### qubit spec parameters
#     "qubit_pulse_style": "arb",
#     "qubit_gain": 19000,
#     # "qubit_length": 10,  ###us, this is used if pulse style is const
#     "sigma": 0.200,  ### units us, define a 20ns sigma
#     "qubit_freq": 145.5,
#     "relax_delay": 1000,  ### turned into us inside the run function
#     #### define shots
#     "shots": 20000, ### this gets turned into "reps"
#     ### define the wait times
#     "wait_start": 0,
#     "wait_stop": 1500,
#     "wait_num": 31,
#     ##### define number of clusters to use
#     "cen_num": 3,
# }
# config = BaseConfig | UpdateConfig
#
# yoko1.SetVoltage(config["yokoVoltage"])
#
# Instance_T1_ThermalPS = T1_ThermalPS(path="dataTestT1_ThermalPS", outerFolder=outerFolder, cfg=config,
#                                                soc=soc, soccfg=soccfg)
# data_T1_ThermalPS = T1_ThermalPS.acquire(Instance_T1_ThermalPS)
# # T1_ThermalPS.display(Instance_T1_ThermalPS, data_T1_ThermalPS, plotDisp=True, save_fig=True)
# T1_ThermalPS.save_data(Instance_T1_ThermalPS, data_T1_ThermalPS)

# ####################################### code for running basic single shot exerpiment with post selection
# UpdateConfig = {
#     ##### set yoko
#     "yokoVoltage": -1.64,
#     ###### cavity
#     "reps": 2000,  # this will used for all experiements below unless otherwise changed in between trials
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 10, # [Clock ticks]
#     "read_pulse_gain": 6000, # [DAC units]
#     "read_pulse_freq": 6360.35, # [MHz]
#     ##### qubit spec parameters
#     "qubit_pulse_style": "arb",
#     "qubit_gain": 19000,
#     # "qubit_length": 10,  ###us, this is used if pulse style is const
#     "sigma": 0.200,  ### units us, define a 20ns sigma
#     "qubit_freq": 145.5,
#     "relax_delay": 2000,  ### turned into us inside the run function
#     #### define shots
#     "shots": 10000, ### this gets turned into "reps"
#     #### define info for clustering
#     "cen_num": 3,
# }
# config = BaseConfig | UpdateConfig
#
# yoko1.SetVoltage(config["yokoVoltage"])
# Instance_SingleShotPS = SingleShotPS(path="dataTestSingleShotPS", outerFolder=outerFolder, cfg=config,
#                                                soc=soc, soccfg=soccfg)
# data_SingleShotPS = SingleShotPS.acquire(Instance_SingleShotPS)
# # SingleShotPS.display(Instance_SingleShotPS, data_SingleShotPS, plotDisp=True, save_fig=True)
# SingleShotPS.save_data(Instance_SingleShotPS, data_SingleShotPS)


#####################################################################################################################
plt.show()
