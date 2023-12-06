
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
outerFolder = "Z:\\TantalumFluxonium\\Data\\2023_10_31_BF2_cooldown_6\\WTF\\"

###qubitAtten = attenuator(27797, attenuation_int= 10, print_int = False)


#################################### Running the actual experiments

# Only run this if no proxy already exists
soc, soccfg = makeProxy()
# # print(soccfg)

print('program starting: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))


###########
#### define the switch cofidg
SwitchConfig = {
    "trig_buffer_start": 0.035, # in us
    "trig_buffer_end": 0.024, # in us
    "trig_delay": 0.07, # in us
}
##########
#
# plt.ioff()
#
#
# # ####################################### code for running basic single shot exerpiment
# UpdateConfig = {
#     ##### set yoko
#     "yokoVoltage": -0.21,
#     ###### cavity
#     "reps": 2000,  # this will used for all experiements below unless otherwise changed in between trials
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 15, # [Clock ticks]
#     "read_pulse_gain":  12000, # [DAC units]
#     "read_pulse_freq": 7392.3, # [MHz]
#     ##### qubit spec parameters
#     "qubit_pulse_style": "arb",
#     "qubit_gain": 10000,
#     # "qubit_length": 10,  ###us, this is used if pulse style is const
#     "sigma": 0.4,  ### units us, define a 20ns sigma
#     "flat_top_length": 1.0, ### in us
#     "qubit_freq": 510,
#     "relax_delay": 6000,  ### turned into us inside the run function
#     #### define shots
#     "shots": 10000, ### this gets turned into "reps"
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

# # ########
# ##### run the single shot experiment
# outerFolder = "Z:\\TantalumFluxonium\\Data\\2023_10_31_BF2_cooldown_6\\WTF\\singleShotSweeps\\"
# loop_len = 6
# # freq_vec = config["read_pulse_freq"] + np.linspace(-1, 1, loop_len)
# # qubit_gain_vec = np.linspace(10000, 20000, loop_len, dtype=int)
# read_gain_vec = np.linspace(10000, 15000, loop_len, dtype=int)
# for idx in range(loop_len):
#     # config["read_pulse_freq"] = freq_vec[idx]
#     # config["qubit_gain"] = qubit_gain_vec[idx]
#     config["read_pulse_gain"] = read_gain_vec[idx]
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
# # ###########



# ##################################### code for running  2D single shot fidelity optimization
# UpdateConfig = {
#     ##### set yoko
#     "yokoVoltage": -0.5,
#     #### define basic parameters
#     ###### cavity
#     "reps": 2000,  # this will used for all experiements below unless otherwise changed in between trials
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 10, # [Clock ticks]
#     "read_pulse_gain": 10000, # [DAC units]
#     "read_pulse_freq": 7392.6, # [MHz]
#     ##### qubit spec parameters
#     "qubit_pulse_style": "flat_top",
#     "qubit_gain": 10000,
#     # "qubit_length": 10,  ###us, this is used if pulse style is const
#     "sigma": 0.005,  ### units us, define a 20ns sigma
#     "flat_top_length": 0.025, ### in us
#     "qubit_freq": 4825.0,
#     "relax_delay": 1000,  ### turned into us inside the run function
#     #### define shots
#     "shots": 2000, ### this gets turned into "reps"
#     #### define the loop parameters
#
#     "x_var": "qubit_freq",
#     "x_start": 4825 - 5,
#     "x_stop": 4825 + 5,
#     "x_num": 11,
#
#     "y_var": "qubit_gain",
#     "y_start": 15000,
#     "y_stop": 30000,
#     "y_num": 5,
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


# #################################################################################
# ################# code finding T1 of a thermal state
# UpdateConfig = {
#     ##### set yoko
#     "yokoVoltage": -0.23,
#     ###### cavity
#     #"reps": 0,  # this line does nothing, is overwritten with "shots"
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 10, # [Clock ticks]
#     "read_pulse_gain": 8000, # [DAC units]
#     "read_pulse_freq": 7392.17, # [MHz]
#     ##### qubit spec parameters
#     "qubit_pulse_style": "arb",
#     "qubit_gain": 0,
#     # "qubit_length": 10,  ###us, this is used if pulse style is const
#     "sigma": 0.3,  ### units us, define a 20ns sigma
#     "qubit_freq": 650,
#     "relax_delay": 4000,  ### turned into us inside the run function
#     #### define shots
#     "shots": 10000, ### this gets turned into "reps"
#     ### define the wait times
#     "wait_start": 0,
#     "wait_stop": 10000,
#     "wait_num": 41,
#     ##### define number of clusters to use
#     "cen_num": 2,
# }
# config = BaseConfig | UpdateConfig
#
# yoko1.SetVoltage(config["yokoVoltage"])
#
# print('starting scan: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
# Instance_T1_ThermalPS = T1_ThermalPS(path="dataTestT1_ThermalPS", outerFolder=outerFolder, cfg=config,
#                                                soc=soc, soccfg=soccfg)
# data_T1_ThermalPS = T1_ThermalPS.acquire(Instance_T1_ThermalPS)
# # T1_ThermalPS.display(Instance_T1_ThermalPS, data_T1_ThermalPS, plotDisp=True, save_fig=True)
# T1_ThermalPS.save_data(Instance_T1_ThermalPS, data_T1_ThermalPS)
#
# print('end of scan: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))

#### loop over different flux points
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


#############################################################################################################
####################################### code for running basic single shot experiment with post selection
UpdateConfig = {
    ##### set yoko
    "yokoVoltage": -0.23,
    ###### cavity
    "reps": 2000,  # this will used for all experiements below unless otherwise changed in between trials
    "read_pulse_style": "const", # --Fixed
    "read_length": 10, # us
    "read_pulse_gain": 8000, # [DAC units]
    "read_pulse_freq": 7392.17, # [MHz]
    ##### qubit spec parameters
    "qubit_pulse_style": "flat_top",
    "qubit_gain": 30000,
    # "qubit_length": 10,  ###us, this is used if pulse style is const
    "flat_top_length": 20.0,  ### in us
    "sigma": 0.025,  ### units us, define a 20ns sigma
    "qubit_freq": 650,
    "relax_delay": 10,  ### turned into us inside the run function
    #### define shots
    "shots": 20000, ### this gets turned into "reps"
    #### define info for clustering
    "cen_num": 2,
}
config = BaseConfig | UpdateConfig

yoko1.SetVoltage(config["yokoVoltage"])
Instance_SingleShotPS = SingleShotPS(path="dataTestSingleShotPS", outerFolder=outerFolder, cfg=config,
                                               soc=soc, soccfg=soccfg)
data_SingleShotPS = SingleShotPS.acquire(Instance_SingleShotPS)
SingleShotPS.display(Instance_SingleShotPS, data_SingleShotPS, plotDisp=True, save_fig=True)
SingleShotPS.save_data(Instance_SingleShotPS, data_SingleShotPS)
SingleShotPS.save_config(Instance_SingleShotPS)



# # #####################################################################################################################
# ###################################### code for running Amplitude rabi Blob with post selection
# UpdateConfig = {
#     ##### define attenuators
#     "yokoVoltage": -0.23,
#     ###### cavity
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 10, # us
#     "read_pulse_gain": 8000, # [DAC units]
#     "read_pulse_freq": 7392.17, # [MHz]
#     ##### spec parameters for finding the qubit frequency
#     "qubit_freq_start": 650 - 25,
#     "qubit_freq_stop": 650 + 25,
#     "RabiNumPoints": 51,  ### number of points
#     "qubit_pulse_style": "flat_top",
#     "sigma": 0.025,  ### units us, define a 20ns sigma
#     "flat_top_length": 20., ### in us
#     "relax_delay": 10,  ### turned into us inside the run function
#     ##### amplitude rabi parameters
#     "qubit_gain_start": 10000,
#     "qubit_gain_step": 10000, ### stepping amount of the qubit gain
#     "qubit_gain_expts": 2, ### number of steps
#     # "AmpRabi_reps": 2000,  # number of averages for the experiment
#     ##### define number of clusters to use
#     "cen_num": 2,
#     "shots": 5000,  ### this gets turned into "reps"
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


# # ####################################################################################
# ################## code finding T2R of a thermal state using pulses
# UpdateConfig = {
#     ##### set yoko
#     "yokoVoltage": -6.0,
#     ###### cavity
#     #"reps": 0,  # this line does nothing, is overwritten with "shots"
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 10, # [Clock ticks]
#     "read_pulse_gain": 25000, # [DAC units]
#     "read_pulse_freq": 7229.43, # [MHz]
#     ##### qubit spec parameters
#     "qubit_pulse_style": "arb",
#     "qubit_gain": 11000, #22000,
#     # "qubit_length": 10,  ###us, this is used if pulse style is const
#     "sigma": 0.050,  ### units us, define a 20ns sigma
#     # "flat_top_length": 0.150,
#     "qubit_freq": 4238.0 - 1.0,
#     "relax_delay": 50,  ### turned into us inside the run function
#     #### define shots
#     "shots": 2000, ### this gets turned into "reps"
#     ### define the wait times
#     "wait_start": 0.0,
#     "wait_stop": 50.0,
#     "wait_num": 101,
#     ##### define number of clusters to use
#     "cen_num": 2,
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


#####################################################################################################################
print('program complete: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
plt.show()