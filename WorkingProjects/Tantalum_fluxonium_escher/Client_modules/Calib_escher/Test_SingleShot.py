#%%

import os
# path = os.getcwd()


# os.add_dll_directory(os.path.dirname(path)+'\\PythonDrivers')
path = r'/WorkingProjects/Tantalum_fluxonium_escher\Client_modules\PythonDrivers'
os.add_dll_directory(path)
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Calib_escher.initialize import *
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mSingleShotProgram import SingleShotProgram
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mSingleShot_2Dsweep import SingleShot_2Dsweep
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mT1_PS_sse import T1_PS_sse
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mSingleShotPS import SingleShotPS
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mAmplitudeRabiBlob_PS import AmplitudeRabi_PS
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mAmplitudeRabiFlux_PS import AmplitudeRabiFlux_PS
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mT2R_PS import T2R_PS
from matplotlib import pyplot as plt
import datetime
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mT1_PS import T1_PS
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mRepeatReadout import RepeatReadout

# Define the saving path
outerFolder = "Z:\\TantalumFluxonium\\Data\\2024_03_25_BF2_cooldown_7\\WTF\\"

# Only run this if no proxy already exists
soc, soccfg = makeProxy()

# Define the switch cofidg
SwitchConfig = {
    "trig_buffer_start": 0.035, # in us
    "trig_buffer_end": 0.024, # in us
    "trig_delay": 0.07, # in us
}
BaseConfig = BaseConfig | SwitchConfig

#%%

# TITLE: code for running basic single shot experiment
UpdateConfig = {
    # set yoko
    "yokoVoltage": 3.6,

    # cavity
    "reps": 2000,
    "read_pulse_style": "const",
    "read_length": 20,
    "read_pulse_gain":  10000,
    "read_pulse_freq": 7392.3,

    # qubit spec parameters
    "qubit_pulse_style": "flat_top",
    "qubit_gain": 7000,
    "qubit_length": 20,
    "sigma": 0.05,
    "flat_top_length": 5,
    "qubit_freq": 830.72,
    "relax_delay": 2000,

    # define shots
    "shots": 10000,
    "use_switch": True,
}
config = BaseConfig | UpdateConfig

yoko2.SetVoltage(config["yokoVoltage"])

#%%
# TITLE: Single shot experiment
plt.close('all')
Instance_SingleShotProgram = SingleShotProgram(path="dataTestSingleShotProgram", outerFolder=outerFolder, cfg=config,
                                               soc=soc, soccfg=soccfg)
data_SingleShot = SingleShotProgram.acquire(Instance_SingleShotProgram)
SingleShotProgram.save_data(Instance_SingleShotProgram, data_SingleShot)
SingleShotProgram.save_config(Instance_SingleShotProgram)
SingleShotProgram.display(Instance_SingleShotProgram, data_SingleShot, plotDisp=True, save_fig=True)

#%%
# TITLE: Optimize fidelity over different parameters
plt.close('all')
outerFolder_sweep = outerFolder + "singleShotSweeps_qubitFreq\\"
loop_len = 6
param_dict = {
    'read_pulse_freq': config["read_pulse_freq"] + np.linspace(-0.2, 0.2, 21),
    'qubit_freq': config["qubit_freq"] + np.linspace(-50, 50, 21),
    'qubit_gain': np.linspace(15000, 22000, 21, dtype=int),
    'read_pulse_gain': np.linspace(7000, 12000, 6, dtype=int)
}
vary = "read_pulse_gain"

for idx in range(param_dict[vary].shape[0]):
    config[vary] = param_dict[vary][idx]
    Instance_SingleShotProgram = SingleShotProgram(path="SingleShot_sweeps_yoko_"+str(config["yokoVoltage"]), outerFolder=outerFolder_sweep, cfg=config,soc=soc,soccfg=soccfg)
    data_SingleShot = SingleShotProgram.acquire(Instance_SingleShotProgram)
    SingleShotProgram.display(Instance_SingleShotProgram, data_SingleShot, plotDisp=False, save_fig=True)
    SingleShotProgram.save_data(Instance_SingleShotProgram, data_SingleShot)
    SingleShotProgram.save_config(Instance_SingleShotProgram)
    plt.clf()
    print(idx)

#%%


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
#
#%%
# TITLE: T1 of a thermal state
UpdateConfig = {
    # set yoko
    "yokoVoltage": 2.384,
    "yokoVoltage_freqPoint": 2.384,

    # cavity
    "read_pulse_style": "const",
    "read_length": 20,
    "read_pulse_gain": 10000, # [DAC units]
    "read_pulse_freq": 7392.3, # [MHz]

    # qubit spec parameters
    "qubit_pulse_style": "flat_top",
    "qubit_gain": 7000,
    "flat_top_length": 20,
    "sigma": 0.05,
    "qubit_freq": 830.72,
    "relax_delay": 100,

    # Experiment parameters
    "shots": 10000,
    "wait_start": 0,
    "wait_stop": 20000,
    "wait_num": 11,
    "wait_type": "linear",
    "cen_num": 2,
    'use_switch': True,
    "fridge_temp": 10,

}
config = BaseConfig | UpdateConfig

yoko1.SetVoltage(config["yokoVoltage"])
#%%
plt.close("all")
print('starting scan: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
Instance_T1_ThermalPS = T1_PS_sse(path="dataTestT1_ThermalPS", outerFolder=outerFolder, cfg=config,
                                               soc=soc, soccfg=soccfg)
data_T1_ThermalPS = Instance_T1_ThermalPS.acquire()
data_T1_ThermalPS = Instance_T1_ThermalPS.process_data(data_T1_ThermalPS)
Instance_T1_ThermalPS.display(data_T1_ThermalPS, plotDisp=True, save_fig=True)
Instance_T1_ThermalPS.save_data(data_T1_ThermalPS)

print('end of scan: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
#%%
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

# ################ code finding T1 of a thermal state using pulses
# UpdateConfig = {
#     ##### set yoko
#     "yokoVoltage": -0.23,
#     ###### cavity
#     #"reps": 0,  # this line does nothing, is overwritten with "shots"
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 20, # [Clock ticks]
#     "read_pulse_gain": 6000, # [DAC units]
#     "read_pulse_freq": 7392.17, # [MHz]
#     ##### qubit spec parameters
#     "qubit_pulse_style": "arb",
#     "qubit_gain": 10000, #12000,
#     # "qubit_length": 10,  ###us, this is used if pulse style is const
#     "sigma": 0.025,  ### units us, define a 20ns sigma
#     "flat_top_length": 10.0,
#     "qubit_freq": 655,
#     "relax_delay": 10,  ### turned into us inside the run function
#     #### define shots
#     "shots": 5000, ### this gets turned into "reps"
#     ### define the wait times
#     "wait_start": 0,
#     "wait_stop": 15000,
#     "wait_num": 15,
#     ##### define number of clusters to use
#     "cen_num": 2,
#
#     "use_switch": True,
# }
# config = BaseConfig | UpdateConfig
#
# yoko1.SetVoltage(config["yokoVoltage"])
# print('starting scan: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
#
# # Estimating Time
# time_per_scan = config["shots"] * (
#         np.linspace(config["wait_start"], config["wait_stop"], config["wait_num"])
#         + config["relax_delay"]) * 1e-6
# total_time = np.sum(time_per_scan) / 60
# print('total time estimate: ' + str(total_time) + " minutes")
# #
# Instance_T1_PS = T1_PS(path="dataTestT1_PS", outerFolder=outerFolder, cfg=config,
#                                                soc=soc, soccfg=soccfg)
# data_T1_PS = T1_PS.acquire(Instance_T1_PS)
# T1_PS.save_data(Instance_T1_PS, data_T1_PS)
# T1_PS.save_config(Instance_T1_PS)
#
# print('end of scan: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))


# ############################################################################################################
# ###################################### code for running basic single shot experiment with post selection
# UpdateConfig = {
#     ##### set yoko
#     "yokoVoltage": -0.24,
#     ###### cavity
#     "reps": 2000,  # this will used for all experiements below unless otherwise changed in between trials
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 50, # us
#     "read_pulse_gain": 6000, # [DAC units]
#     "read_pulse_freq": 7392.2, # [MHz]
#     ##### qubit spec parameters
#     "qubit_pulse_style": "flat_top",
#     "qubit_gain": 30000,
#     # "qubit_length": 10,  ###us, this is used if pulse style is const
#     "flat_top_length": 50.0,  ### in us
#     "sigma": 0.25,  ### units us, define a 20ns sigma
#     "qubit_freq": 810,
#     "relax_delay": 100,  ### turned into us inside the run function
#     #### define shots
#     "shots": 5000, ### this gets turned into "reps"
#     #### define info for clustering
#     "cen_num": 2,
#
#     "use_switch": True,
# }
# config = BaseConfig | UpdateConfig
#
# yoko1.SetVoltage(config["yokoVoltage"])
# Instance_SingleShotPS = SingleShotPS(path="dataTestSingleShotPS", outerFolder=outerFolder, cfg=config,
#                                                soc=soc, soccfg=soccfg)
# data_SingleShotPS = SingleShotPS.acquire(Instance_SingleShotPS)
# #####SingleShotPS.display(Instance_SingleShotPS, data_SingleShotPS, plotDisp=True, save_fig=True)
# SingleShotPS.save_data(Instance_SingleShotPS, data_SingleShotPS)
# SingleShotPS.save_config(Instance_SingleShotPS)
# # #


# #####################################################################################################################
###################################### code for running Amplitude rabi Blob with post selection
# UpdateConfig = {
#     ##### define attenuators
#     "yokoVoltage": -0.24,
#     ###### cavity
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 25, # us
#     "read_pulse_gain": 7000, # [DAC units]
#     "read_pulse_freq": 7392.0, # [MHz]
#     ##### spec parameters for finding the qubit frequency
#     "qubit_freq_start": 700,
#     "qubit_freq_stop": 900,
#     "RabiNumPoints": 101,  ### number of points
#     "qubit_pulse_style": "flat_top",
#     "sigma": 0.025,  ### units us, define a 20ns sigma
#     "flat_top_length": 50.0, ### in us
#     "relax_delay": 1000,  ### turned into us inside the run function
#     ##### amplitude rabi parameters
#     "qubit_gain_start": 25000,
#     "qubit_gain_step": 5000, ### stepping amount of the qubit gain
#     "qubit_gain_expts": 2, ### number of steps
#     # "AmpRabi_reps": 2000,  # number of averages for the experiment
#     ##### define number of clusters to use
#     "cen_num": 2,
#     "shots": 3000,  ### this gets turned into "reps"
#
#     "use_switch": True,
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
#     "yokoVoltage": -0.23,
#     ###### cavity
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 10, # us
#     "read_pulse_gain": 8000, # [DAC units]
#     "read_pulse_freq": 7392.17, # [MHz]
#     ##### qubit spec parameters
#     "qubit_pulse_style": "flat_top",
#     "qubit_gain": 10000, #22000,
#     # "qubit_length": 10,  ###us, this is used if pulse style is const
#     "sigma": 0.025,  ### units us, define a 20ns sigma
#     "flat_top_length": 10,
#     "qubit_freq": 655.0,
#     "relax_delay": 10,  ### turned into us inside the run function
#     #### define shots
#     "shots": 5000, ### this gets turned into "reps"
#     ### define the wait times
#     "wait_start": 0.0,
#     "wait_stop": 2000.0,
#     "wait_num": 11,
#     ##### define number of clusters to use
#     "cen_num": 2,
#
#     "use_switch": True,
# }
# config = BaseConfig | UpdateConfig
#
# yoko1.SetVoltage(config["yokoVoltage"])
# print('starting scan: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
# # Estimating Time
# time_per_scan = config["shots"] * (
#         np.linspace(config["wait_start"], config["wait_stop"], config["wait_num"])
#         + config["relax_delay"]) * 1e-6
# total_time = np.sum(time_per_scan) / 60
# print('total time estimate: ' + str(total_time) + " minutes")
#
# Instance_T2R_PS = T2R_PS(path="dataTestT2R_PS", outerFolder=outerFolder, cfg=config,
#                                                soc=soc, soccfg=soccfg)
# data_T2R_PS = T2R_PS.acquire(Instance_T2R_PS)
# T2R_PS.save_data(Instance_T2R_PS, data_T2R_PS)
# T2R_PS.save_config(Instance_T2R_PS)
#
# print('end of scan: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))


#####################################################################################################################
# print('program complete: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
plt.show()