
#### import packages
import os
path = os.getcwd()
os.add_dll_directory(os.path.dirname(path)+'\\PythonDrivers')
from STFU.Client_modules.Calib_escher.initialize import *
from STFU.Client_modules.Experiments.mSingleShotProgram import SingleShotProgram
from STFU.Client_modules.Experiments.mSingleShot_2Dsweep import SingleShot_2Dsweep
# from STFU.Client_modules.Experiments.mT1_ThermalPS import T1_ThermalPS
from STFU.Client_modules.Experiments.mT1_ThermalPS_pulse import T1_ThermalPS
from STFU.Client_modules.Experiments.mSingleShotPS import SingleShotPS
from STFU.Client_modules.Experiments.mAmplitudeRabiBlob_PS import AmplitudeRabi_PS
from STFU.Client_modules.Experiments.mAmplitudeRabiFlux_PS import AmplitudeRabiFlux_PS
from matplotlib import pyplot as plt
import datetime
from STFU.Client_modules.Experiments.mT1_PS import T1_PS
from STFU.Client_modules.Experiments.mRepeatReadout import RepeatReadout

#### define the saving path
outerFolder = "Z:\\TantalumFluxonium\\Data\\2023_07_20_BF2_cooldown_3\\TF3SC1\\"

###qubitAtten = attenuator(27797, attenuation_int= 10, print_int = False)


#################################### Running the actual experiments

# # Only run this if no proxy already exists
# soc, soccfg = makeProxy()
# # print(soccfg)
#
# plt.ioff()
#
#
# # ####################################### code for running basic single shot exerpiment
# UpdateConfig = {
#     ##### set yoko
#     "yokoVoltage": -1.7,
#     ###### cavity
#     "reps": 2000,  # this will used for all experiements below unless otherwise changed in between trials
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 5, # [Clock ticks]
#     "read_pulse_gain": 13000, # [DAC units]
#     "read_pulse_freq": 5988.2, # [MHz]
#     ##### qubit spec parameters
#     "qubit_pulse_style": "arb",
#     "qubit_gain": 25000,
#     # "qubit_length": 10,  ###us, this is used if pulse style is const
#     "sigma": 0.3,  ### units us, define a 20ns sigma
#     "qubit_freq": 1334.75,
#     "relax_delay": 3000,  ### turned into us inside the run function
#     #### define shots
#     "shots": 2000, ### this gets turned into "reps"
# }
# config = BaseConfig | UpdateConfig
#
# yoko1.SetVoltage(config["yokoVoltage"])
#
# Instance_SingleShotProgram = SingleShotProgram(path="dataTestSingleShotProgram", outerFolder=outerFolder, cfg=config,
#                                                soc=soc, soccfg=soccfg)
# data_SingleShot = SingleShotProgram.acquire(Instance_SingleShotProgram)
# SingleShotProgram.save_data(Instance_SingleShotProgram, data_SingleShot)
# SingleShotProgram.save_config(Instance_SingleShotProgram)
# SingleShotProgram.display(Instance_SingleShotProgram, data_SingleShot, plotDisp=True, save_fig=True)

#
# # ##### run the single shot experiment
# # loop_len = 21
# # freq_vec = config["read_pulse_freq"] + np.linspace(-0.50, 0.50, loop_len)
# # # qubit_gain_vec = np.linspace(10000, 20000, loop_len, dtype=int)
# # # read_gain_vec = np.linspace(4000, 5000, loop_len, dtype=int)
# # for idx in range(loop_len):
# #     config["read_pulse_freq"] = freq_vec[idx]
# #     # config["qubit_gain"] = qubit_gain_vec[idx]
# #     # config["read_pulse_gain"] = read_gain_vec[idx]
# #     Instance_SingleShotProgram = SingleShotProgram(path="dataTestSingleShotProgram", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
# #     data_SingleShot = SingleShotProgram.acquire(Instance_SingleShotProgram)
# #     # SingleShotProgram.display(Instance_SingleShotProgram, data_SingleShot, plotDisp=True, save_fig=False)
# #     # ## SingleShotProgram.save_data(Instance_SingleShotProgram, data_SingleShot)
# #     # ## SingleShotProgram.save_config(Instance_SingleShotProgram)
# #     # plt.show()
# #
# #     SingleShotProgram.display(Instance_SingleShotProgram, data_SingleShot, plotDisp=True, save_fig=True)
# #     print(idx)
#
# # #



# ##################################### code for running  2D single shot fidelity optimization
# UpdateConfig = {
#     ##### set yoko
#     "yokoVoltage": -1.7,
#     #### define basic parameters
#     ###### cavity
#     "reps": 2000,  # this will used for all experiements below unless otherwise changed in between trials
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 10, # [Clock ticks]
#     "read_pulse_gain": 12000, # [DAC units]
#     "read_pulse_freq": 5988.21, # [MHz]
#     ##### qubit spec parameters
#     "qubit_pulse_style": "arb",
#     "qubit_gain": 25000,
#     # "qubit_length": 10,  ###us, this is used if pulse style is const
#     "sigma": 0.3,  ### units us, define a 20ns sigma
#     "qubit_freq": 1334.75,
#     "relax_delay": 2000,  ### turned into us inside the run function
#     #### define shots
#     "shots": 2000, ### this gets turned into "reps"
#     #### define the loop parameters
#
#     "x_var": "read_pulse_freq",
#     "x_start": 5988.21 - 1.0,
#     "x_stop": 5988.21 + 1.0,
#     "x_num": 21,
#
#     "y_var": "read_pulse_gain",
#     "y_start": 15000,
#     "y_stop": 25000,
#     "y_num": 11,
# }
# config = BaseConfig | UpdateConfig
#
# yoko1.SetVoltage(config["yokoVoltage"])
#
# Instance_SingleShot_2Dsweep = SingleShot_2Dsweep(path="dataTestSingleShot_2Dsweep", outerFolder=outerFolder, cfg=config,
#                                                soc=soc, soccfg=soccfg)
# data_SingleShot_2Dsweep = SingleShot_2Dsweep.acquire(Instance_SingleShot_2Dsweep)
# SingleShot_2Dsweep.save_data(Instance_SingleShot_2Dsweep, data_SingleShot_2Dsweep)
# SingleShot_2Dsweep.save_config(Instance_SingleShot_2Dsweep)


# ####################################################################################
################## code finding T1 of a thermal state
UpdateConfig = {
    ##### set yoko
    "yokoVoltage": 1.393,
    ###### cavity
    #"reps": 0,  # this line does nothing, is overwritten with "shots"
    "read_pulse_style": "const", # --Fixed
    "read_length": 12, # [Clock ticks]
    "read_pulse_gain": 14000, # [DAC units]
    "read_pulse_freq": 5988.33, # [MHz]
    ##### qubit spec parameters
    "qubit_pulse_style": "arb",
    "qubit_gain": 15000,
    # "qubit_length": 10,  ###us, this is used if pulse style is const
    "sigma": 0.3,  ### units us, define a 20ns sigma
    "qubit_freq": 1715.6,
    "relax_delay": 1500,  ### turned into us inside the run function
    #### define shots
    "shots": 3000, ### this gets turned into "reps"
    ### define the wait times
    "wait_start": 0,
    "wait_stop": 2000,
    "wait_num": 11,
    ##### define number of clusters to use
    "cen_num": 4,
}
config = BaseConfig | UpdateConfig

yoko1.SetVoltage(config["yokoVoltage"])

Instance_T1_ThermalPS = T1_ThermalPS(path="dataTestT1_ThermalPS", outerFolder=outerFolder, cfg=config,
                                               soc=soc, soccfg=soccfg)
data_T1_ThermalPS = T1_ThermalPS.acquire()
# T1_ThermalPS.display(Instance_T1_ThermalPS, data_T1_ThermalPS, plotDisp=True, save_fig=True)
T1_ThermalPS.save_data(Instance_T1_ThermalPS, data_T1_ThermalPS)

# #### loop over different flux points
# yoko_vec = np.linspace(0.10, 0.45, 15)
#
# for idx in range(len(yoko_vec)):
#     print('starting run number ' + str(idx))
#     config["yokoVoltage"] = yoko_vec[idx]
#     yoko1.SetVoltage(config["yokoVoltage"])
#
#     Instance_T1_ThermalPS = T1_ThermalPS(path="dataTestT1_ThermalPS", outerFolder=outerFolder, cfg=config,
#                                          soc=soc, soccfg=soccfg)
#     data_T1_ThermalPS = T1_ThermalPS.acquire(Instance_T1_ThermalPS)
#     # T1_ThermalPS.display(Instance_T1_ThermalPS, data_T1_ThermalPS, plotDisp=True, save_fig=True)
#     T1_ThermalPS.save_data(Instance_T1_ThermalPS, data_T1_ThermalPS)
#
#     print('finished run number ' + str(idx))

################# code finding T1 of a thermal state using pulses
# UpdateConfig = {
#     ##### set yoko
#     "yokoVoltage": -1.7,
#     ###### cavity
#     #"reps": 0,  # this line does nothing, is overwritten with "shots"
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 5, # [Clock ticks]
#     "read_pulse_gain": 13000, # [DAC units]
#     "read_pulse_freq": 5988.2, # [MHz]
#     ##### qubit spec parameters
#     "qubit_pulse_style": "arb",
#     "qubit_gain": 20000, #12000,
#     # "qubit_length": 10,  ###us, this is used if pulse style is const
#     "sigma": 0.300,  ### units us, define a 20ns sigma
#     # "flat_top_length": 0.010,
#     "qubit_freq": 1331.3,
#     "relax_delay": 50,  ### turned into us inside the run function
#     #### define shots
#     "shots": 5000, ### this gets turned into "reps"
#     ### define the wait times
#     "wait_start": 0,
#     "wait_stop": 2500,
#     "wait_num": 101,
#     ##### define number of clusters to use
#     "cen_num": 3,
# }
# config = BaseConfig | UpdateConfig
#
# yoko1.SetVoltage(config["yokoVoltage"])
# print('starting scan: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
#
# Instance_T1_PS = T1_PS(path="dataTestT1_PS", outerFolder=outerFolder, cfg=config,
#                                                soc=soc, soccfg=soccfg)
# data_T1_PS = T1_PS.acquire(Instance_T1_PS)
# T1_PS.save_data(Instance_T1_PS, data_T1_PS)
# T1_PS.save_config(Instance_T1_PS)
#
# print('end of scan: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))


##############################################################################################################
# ####################################### code for running basic single shot exerpiment with post selection
# UpdateConfig = {
#     ##### set yoko
#     "yokoVoltage": -1.7,
#     ###### cavity
#     "reps": 2000,  # this will used for all experiements below unless otherwise changed in between trials
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 5, # us
#     "read_pulse_gain": 13000, # [DAC units]
#     "read_pulse_freq": 5988.2, # [MHz]
#     ##### qubit spec parameters
#     "qubit_pulse_style": "arb",
#     "qubit_gain": 18000,
#     # "qubit_length": 10,  ###us, this is used if pulse style is const
#     "sigma": 0.300,  ### units us, define a 20ns sigma
#     "qubit_freq": 1334.75,
#     "relax_delay": 500,  ### turned into us inside the run function
#     #### define shots
#     "shots": 2000, ### this gets turned into "reps"
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
# SingleShotPS.save_config(Instance_SingleShotPS)



# # #####################################################################################################################
# ###################################### code for running Amplitude rabi Blob with post selection
# UpdateConfig = {
#     ##### define attenuators
#     "yokoVoltage": -1.29,
#     ###### cavity
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 10, # us
#     "read_pulse_gain": 5000, # [DAC units]
#     "read_pulse_freq": 6360.36, # [MHz]
#     ##### spec parameters for finding the qubit frequency
#     "qubit_freq_start": 70,
#     "qubit_freq_stop": 120,
#     "RabiNumPoints": 51,  ### number of points
#     "qubit_pulse_style": "arb",
#     "sigma": 0.100,  ### units us, define a 20ns sigma
#     # "flat_top_length": 0.025, ### in us
#     "relax_delay": 10,  ### turned into us inside the run function
#     ##### amplitude rabi parameters
#     "qubit_gain_start": 10000,
#     "qubit_gain_step": 2000, ### stepping amount of the qubit gain
#     "qubit_gain_expts": 11, ### number of steps
#     # "AmpRabi_reps": 2000,  # number of averages for the experiment
#     ##### define number of clusters to use
#     "cen_num": 3,
#     "shots": 3000,  ### this gets turned into "reps"
# }
# config = BaseConfig | UpdateConfig
#
# yoko1.SetVoltage(config["yokoVoltage"])
#
# Instance_AmplitudeRabi_PS = AmplitudeRabi_PS(path="dataTestAmplitudeRabi_PS", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg, progress=True)
# data_AmplitudeRabi_PS = AmplitudeRabi_PS.acquire(Instance_AmplitudeRabi_PS)
# AmplitudeRabi_PS.save_data(Instance_AmplitudeRabi_PS, data_AmplitudeRabi_PS)
# AmplitudeRabi_PS.save_config(Instance_AmplitudeRabi_PS)


# # ####################################### code for running repeated single shot measurements
# UpdateConfig = {
#     ##### set yoko
#     "yokoVoltage": -1.37,
#     ###### cavity
#     "reps": 2000,  # this will used for all experiements below unless otherwise changed in between trials
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 10, # [Clock ticks]
#     "read_pulse_gain": 13000, # [DAC units]
#     "read_pulse_freq": 5988.21, # [MHz]
#     ##### qubit spec parameters
#     "qubit_pulse_style": "arb",
#     "qubit_gain": 15000,
#     "qubit_length": 10,  ###us, this is used if pulse style is const
#     "sigma": 0.30,  ### units us
#     #"flat_top_length": 0.200,  ### in us
#     "qubit_freq": 1343,
#     "relax_delay": 2000,  ### turned into us inside the run function
#     #### define shots
#     "shots": 5000, ### this gets turned into "reps"
#
#     ##### time parameters
#     "delay": 5, # s
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