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
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mAmplitudeRabiBlob_PS_sse import AmplitudeRabi_PS_sse
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

SwitchConfig = {
    "trig_buffer_start": 0.035, # in us
    "trig_buffer_end": 0.024, # in us
    "trig_delay": 0.07, # in us
}

BaseConfig = BaseConfig | SwitchConfig


# # ################################################################################################################
# # # ####################################### code for running basic single shot exerpiment
# UpdateConfig = {
#     ##### set yoko
#     "yokoVoltage": -0.48,
#     "yokoVoltage_freqPoint": -0.48,
#     ###### cavity
#     "reps": 2000,  # this will be used for all experiments below unless otherwise changed in between trials
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 20, # [Clock ticks]
#     "read_pulse_gain": 6000, # [DAC units]
#     "read_pulse_freq": 7392.238,# [MHz]
#     ##### qubit spec parameters
#     "qubit_pulse_style": "flat_top",
#     "qubit_gain": 7000,
#     # "qubit_length": 10,  ###us, this is used if pulse style is const
#     "sigma": 0.005,  ### units us, define a 20ns sigma
#     "flat_top_length": 20, ### in us
#     "qubit_freq": 4516.03,
#     "relax_delay": 2000,  ### turned into us inside the run function
#     #### define shots
#     "shots": 5000, ### this gets turned into "reps"
#     ##### record the fridge temperature in units of mK
#     "fridge_temp": fridge_temp,
#     "use_switch": True,
# }
# config = BaseConfig | UpdateConfig
#
# yoko1.SetVoltage(config["yokoVoltage"])
#
# # outerFolder = "Z:\\TantalumFluxonium\\Data\\2023_10_31_BF2_cooldown_6\\WTF\\TempChecks\\Yoko_"+str(config["yokoVoltage_freqPoint"])+"\\"
# # Instance_SingleShotProgram = SingleShotProgram(path="SingleShot_temp_"+str(config["fridge_temp"]), outerFolder=outerFolder, cfg=config,
# #                                                soc=soc, soccfg=soccfg)
# # data_SingleShot = SingleShotProgram.acquire(Instance_SingleShotProgram)
# # SingleShotProgram.save_data(Instance_SingleShotProgram, data_SingleShot)
# # SingleShotProgram.save_config(Instance_SingleShotProgram)
# # SingleShotProgram.display(Instance_SingleShotProgram, data_SingleShot, plotDisp=True, save_fig=True)
# # # #
# # # # # ##### run the single shot experiment
# outerFolder = "Z:\\TantalumFluxonium\\Data\\2023_10_31_BF2_cooldown_6\\WTF\\singleShotSweeps\\"
# loop_len = 11
# freq_vec = config["read_pulse_freq"] + np.linspace(-0.5, 0.5, loop_len)
# # qubit_gain_vec = np.linspace(10000, 20000, loop_len, dtype=int)
# # read_gain_vec = np.linspace(6000, 13000, loop_len, dtype=int)
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
#     "yokoVoltage": -0.29,
#     "yokoVoltage_freqPoint": -0.29,
#     ###### cavity
#     #"reps": 0,  # this line does nothing, is overwritten with "shots"
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 20, # [Clock ticks]
#     "read_pulse_gain": 6000, # [DAC units]
#     "read_pulse_freq": 7392.52, # [MHz]
#     ##### qubit spec parameters
#     "qubit_pulse_style": "flat_top",
#     "qubit_gain": 6000,
#     "flat_top_length": 20,
#     # "qubit_length": 10,  ###us, this is used if pulse style is const
#     "sigma": 0.005,  ### units us, define a 20ns sigma
#     "qubit_freq": 1578.773,
#     "relax_delay": 5,  ### turned into us inside the run function
#     #### define shots
#     "shots": 30000, ### this gets turned into "reps"
#     ### define the wait times
#     "wait_start": 0,
#     "wait_stop": 8000,
#     "wait_num": 21,
#     'wait_type': 'linear',
#     ##### define number of clusters to use
#     "cen_num": 2,
#     ##### record the fridge temperature in units of mK
#     "fridge_temp": fridge_temp,
#     "use_switch":True
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
#     "yokoVoltage": -0.29,
#     "yokoVoltage_freqPoint": -0.29,
#     ###### cavity
#     "reps": 2000,  # this will be used for all experiments below unless otherwise changed in between trials
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 20, # [Clock ticks]
#     "read_pulse_gain": 6000, # [DAC units]
#     "read_pulse_freq": 7392.52, # [MHz]
#     ##### qubit spec parameters
#     "qubit_pulse_style": "flat_top",
#     "qubit_gain": 6000,
#     "sigma": 0.005,  ### units us, define a 20ns sigma
#     "qubit_freq": 1578.773,
#     "relax_delay": 35000,  ### turned into us inside the run function
#     "flat_top_length": 20,
#     #### define shots
#     "shots": 80000, ### this gets turned into "reps"
#     ##### record the fridge temperature in units of mK
#     "fridge_temp": fridge_temp,
#     "use_switch": True,
#     "initialize_pulse": True
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
UpdateConfig = {
    ##### set yoko
    "yokoVoltage": -0.48,
    "yokoVoltage_freqPoint": -0.48,
    ###### cavity
    "reps": 2000,  # this will used for all experiements below unless otherwise changed in between trials
    "read_pulse_style": "const", # --Fixed
    "read_length": 20, # us
    "read_pulse_gain": 6000, # [DAC units]
    "read_pulse_freq": 7392.238, # [MHz]
    ##### qubit spec parameters
    "qubit_pulse_style": "flat_top",
    "qubit_gain": 6000,
    # "qubit_length": 10,  ###us, this is used if pulse style is const
    "sigma": 0.005,  ### units us, define a 20ns sigma
    "flat_top_length": 20.0, ### in us
    "qubit_freq": 4516.03,
    "relax_delay": 0.01,  ### turned into us inside the run function
    #### define shots
    "shots": 400000, ### this gets turned into "reps"
    #### define info for clustering
    "cen_num": 2,
#     ##### record the fridge temperature in units of mK
    "fridge_temp": fridge_temp,
    'use_switch':True,
}
config = BaseConfig | UpdateConfig

outerFolder = "Z:\\TantalumFluxonium\\Data\\2023_10_31_BF2_cooldown_6\\WTF\\QND_Checks\\Yoko_"+str(config["yokoVoltage_freqPoint"])+"\\"
#
# yoko1.SetVoltage(config["yokoVoltage"])
#
# # Instance_QNDmeas = QNDmeas(path="QND_Meas_temp_"+str(config["fridge_temp"]), outerFolder=outerFolder, cfg=config,
# #                                                soc=soc, soccfg=soccfg)
# # data_QNDmeas = Instance_QNDmeas.acquire()
# # data_QNDmeas = Instance_QNDmeas.process_data(data_QNDmeas, toPrint=True, confidence_selection=0.95)
# # Instance_QNDmeas.save_data(data_QNDmeas)
# # Instance_QNDmeas.save_config()
# # Instance_QNDmeas.display(data_QNDmeas, plotDisp=True)
# # print('data saved: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
#
#
# ##### loop over readout parameters and try to improve QNDness
avg = 10
read_length_vec = config["read_length"] + np.linspace(-10,15, 6)
read_gain_vec = config["read_pulse_gain"] + np.linspace(-2000, 2000, 9, dtype = int)
Tempr = np.zeros((read_length_vec.size, read_gain_vec.size, avg))

for idx_avg in range(avg):
    print(idx_avg)
    for idx_length in range(read_length_vec.size):
        for idx_gain in range(read_gain_vec.size):
            config["read_length"] = read_length_vec[idx_length]
            config["read_pulse_gain"] = read_gain_vec[idx_gain]
            Instance_QNDmeas = QNDmeas(path="QND_Meas_Sweeps_temp_" + str(config["fridge_temp"]), outerFolder=outerFolder, cfg=config,
                                       soc=soc, soccfg=soccfg)
            data_QNDmeas = QNDmeas.acquire(Instance_QNDmeas)
            data_QNDmeas = Instance_QNDmeas.process_data(data_QNDmeas, toPrint=True, confidence_selection=0.95)
            QNDmeas.save_data(Instance_QNDmeas, data_QNDmeas)
            QNDmeas.save_config(Instance_QNDmeas)
            Instance_QNDmeas.display(data_QNDmeas, plotDisp=False)
            Tempr[idx_length, idx_gain, idx_avg] = np.min([data_QNDmeas["data"]["T_0_0"], data_QNDmeas["data"]["T_1_1"]])
###########

plt.figure(figsize=(10, 6))
plt.imshow(np.average(Tempr, axis = 2).T, origin='lower', extent=[read_length_vec.min(), read_length_vec.max(), read_gain_vec.min(), read_gain_vec.max()], aspect='auto', cmap='viridis')
plt.colorbar(label='Tempr')
plt.xlabel('read_length_vec')
plt.ylabel('read_gain_vec')
plt.title('2D plot of Tempr')
plt.tight_layout()
plt.show()

# Create a 2d plot


#####################################################################################################################
# ###TITLE: Amplitude rabi Blob with post selection
# region Amplitude Rabi PS Config
# UpdateConfig = {
#     ##### define attenuators
#     "yokoVoltage": -0.46,
#     "yokoVoltage_freqPoint": -0.46,
#     ###### cavity
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 20, # us
#     "read_pulse_gain": 6000, # [DAC units]
#     "read_pulse_freq": 7392.39, # [MHz]
#     ##### spec parameters for finding the qubit frequency
#     "qubit_freq_start": 4150,
#     "qubit_freq_stop": 4250,
#     "RabiNumPoints": 11,  ### number of points
#     "qubit_pulse_style": "flat_top",
#     "sigma": 0.050,  ### units us, define a 20ns sigma
#     "flat_top_length": 10, ### in us
#     "relax_delay": 1000,  ### turned into us inside the run function
#     ##### amplitude rabi parameters
#     "qubit_gain_start": 2000,
#     "qubit_gain_step": 500, ### stepping amount of the qubit gain
#     "qubit_gain_expts": 3, ### number of steps
#     # "AmpRabi_reps": 2000,  # number of averages for the experiment
#     ##### define number of clusters to use
#     "cen_num": 2,
#     "shots": 2000,  ### this gets turned into "reps"
#     "fridge_temp": fridge_temp,
#     "use_switch": True,
#     "initialize_pulse": True,
#     "initialize_qubit_gain": 30000,
# }
# config = BaseConfig | UpdateConfig
#
# outerFolder = "Z:\\TantalumFluxonium\\Data\\2023_10_31_BF2_cooldown_6\\WTF\\Rabi_Chevron\\Yoko_"+str(config["yokoVoltage_freqPoint"])+"\\"
#
# yoko1.SetVoltage(config["yokoVoltage"])
# print("Voltage is ", yoko1.GetVoltage(), " Volts")
#
# # Calculating Time required
# time_required = (config["qubit_gain_expts"]*config["RabiNumPoints"]*config["shots"]*
#                  (config["flat_top_length"] + 2*config["read_length"] + config["relax_delay"])/1e6/60)
# print("Time required is " + str(time_required) + " min")
#
# print('starting scan: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
# Instance_AmplitudeRabi_PS = AmplitudeRabi_PS_sse(path="Rabi_Chevron_temp_" + str(config["fridge_temp"]), outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg, progress=True)
# data_AmplitudeRabi_PS = Instance_AmplitudeRabi_PS.acquire()
# data_AmplitudeRabi_PS = Instance_AmplitudeRabi_PS.process_data(data_AmplitudeRabi_PS)
# Instance_AmplitudeRabi_PS.save_data(data_AmplitudeRabi_PS)
# Instance_AmplitudeRabi_PS.save_config()
# Instance_AmplitudeRabi_PS.display(data_AmplitudeRabi_PS, plotDisp=True)
#endregion

#####################################################################################################################
print('program complete: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
plt.show()

