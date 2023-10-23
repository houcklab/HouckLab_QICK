
#### import packages
import os
path = os.getcwd()
os.add_dll_directory(os.path.dirname(path)+'\\PythonDrivers')

from WorkingProjects.Tantalum_fluxonium.Client_modules.Calib.initialize import *
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mTransmission_SaraTest import Transmission
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mSpecSlice_SaraTest import SpecSlice
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mAmplitudeRabi import AmplitudeRabi
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mTransVsGain import TransVsGain
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mAmplitudeRabi_Blob import AmplitudeRabi_Blob
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mAmplitudeRabi_CavityPower import AmplitudeRabi_CavityPower
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mT1Experiment import T1Experiment
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mT2Experiment import T2Experiment
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mT2EchoExperiment import T2EchoExperiment
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mSingleShotProgram import SingleShotProgram
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mSingleShot_2Dsweep import SingleShot_2Dsweep
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mAmplitudeRabiBlob_PS import AmplitudeRabi_PS
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mAmplitudeRabiFlux_PS import AmplitudeRabiFlux_PS
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mQubitSpecRepeat import QubitSpecRepeat
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.m2QubitFluxDrift import TwoQubitFluxDrift
from matplotlib import pyplot as plt
import datetime

#### define the saving path
outerFolder = "Z:\\TantalumFluxonium\\Data\\2023_10_09_BF2_cooldown_5\\TF4\\"

###qubitAtten = attenuator(27797, attenuation_int= 10, print_int = False)

print('starting time: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))

#################################### Running the actual experiments

# Only run this if no proxy already exists
soc, soccfg = makeProxy()
# print(soccfg)

plt.ioff()

# # # Configure for transmission experiment
# UpdateConfig_transmission={
#     "reps": 10,  # this will used for all experiements below unless otherwise changed in between trials
#     "read_pulse_style": "const", # --Fixed
#     "readout_length": 10, # us
#     "read_pulse_gain": 2000,#500, # [DAC units]
#     "read_pulse_freq": 6.3605 , # [MHz] actual frequency is this number + "cavity_LO"
#     "nqz": 2,  #### refers to cavity
#     ##### define tranmission experiment parameters
#     "TransSpan": 1, ### MHz, span will be center+/- this parameter
#     "TransNumPoitns": 200, ### number of points in the transmission frequecny
# }

# # Configure for qubit experiment
# UpdateConfig_qubit = {
#     "qubit_pulse_style": "const",
#     "qubit_gain": 3000,
#     "qubit_freq": 265.56, ###########
#     "qubit_length": 30,
#     ##### define spec slice experiment parameters
#     "qubit_freq_start": 264,
#     "qubit_freq_stop": 267,
#     "SpecNumPoints": 21,  ### number of points
#     'spec_reps': 1800,
#     ##### amplitude rabi parameters
#     "qubit_gain_start": 0, ########
#     "qubit_gain_step": 200, #200 ### stepping amount of the qubit gain
#     "qubit_gain_expts": 26,#26,  ### number of steps
#     "AmpRabi_reps": 2000,#10000,  # number of averages for the experiment
#     ##### define the yoko voltage
#     "yokoVoltage": 0.0,
#     "relax_delay": 1500,
# }
#
# UpdateConfig = UpdateConfig_transmission | UpdateConfig_qubit
# config = BaseConfig | UpdateConfig ### note that UpdateConfig will overwrite elements in BaseConfig
#
# # set the yoko frequency
# yoko1.SetVoltage(config["yokoVoltage"])
# print("Voltage is ", yoko1.GetVoltage(), " Volts")
#
# #
#
# ##################################### code for runnning basic transmission and specSlice
# # perform the cavity transmission experiment
#
# Instance_trans = Transmission(path="dataTestTransmission", cfg=config,soc=soc,soccfg=soccfg, outerFolder = outerFolder)
# data_trans= Transmission.acquire(Instance_trans)
# Transmission.display(Instance_trans, data_trans, plotDisp=True)
# Transmission.save_data(Instance_trans, data_trans)

#
# ## update the transmission frequency to be the peak
# config["read_pulse_freq"] = Instance_trans.peakFreq
# print("Cavity freq IF [MHz] = ", Instance_trans.peakFreq)
#
# # Instance_specSlice = SpecSlice(path="dataTestSpecSlice", cfg=config,soc=soc,soccfg=soccfg, outerFolder = outerFolder)
# # data_specSlice= SpecSlice.acquire(Instance_specSlice)
# # SpecSlice.display(Instance_specSlice, data_specSlice, plotDisp=True)
# # SpecSlice.save_data(Instance_specSlice, data_specSlice)
#
# #
# config["qubit_pulse_style"]= "arb"
# config["sigma"] = 0.2 # 0.2 # us
# #
# # # #
# # # # # print(config)
# Instance_AmplitudeRabi = AmplitudeRabi(path="dataTestAmplitudeRabi", cfg=config,soc=soc,soccfg=soccfg, outerFolder = outerFolder)
# data_AmplitudeRabi = AmplitudeRabi.acquire(Instance_AmplitudeRabi)
# AmplitudeRabi.display(Instance_AmplitudeRabi, data_AmplitudeRabi, plotDisp=True)
# AmplitudeRabi.save_data(Instance_AmplitudeRabi, data_AmplitudeRabi)
# AmplitudeRabi.save_config(Instance_AmplitudeRabi)
#
# #
#
# ########################################################################################################################

# # #################################### code for transmission vs power
# UpdateConfig = {
#     "yokoVoltage": -3.1,
#     ##### change gain instead option
#     "trans_gain_start": 1000,
#     "trans_gain_stop": 20000,
#     "trans_gain_num": 20,
#     ###### cavity
#     "trans_reps": 200,  # this will used for all experiements below unless otherwise changed in between trials
#     "read_pulse_style": "const",  # --Fixed
#     "readout_length": 10,  # [us]
#     # "read_pulse_gain": 10000,  # [DAC units]
#     "trans_freq_start": 6438 - 2,  # [MHz] actual frequency is this number + "cavity_LO"
#     "trans_freq_stop": 6438 + 2,  # [MHz] actual frequency is this number + "cavity_LO"
#     "TransNumPoints": 401,  ### number of points in the transmission frequecny
#     "relax_delay": 2,
# }
# config = BaseConfig | UpdateConfig
#
#
# #### update the qubit and cavity attenuation
# yoko1.SetVoltage(config["yokoVoltage"])
#
# # ##### run actual experiment
#
# #### change gain instead of attenuation
# Instance_TransVsGain = TransVsGain(path="dataTestTransVsGain", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
# data_TransVsGain = TransVsGain.acquire(Instance_TransVsGain)
# TransVsGain.save_data(Instance_TransVsGain, data_TransVsGain)
# TransVsGain.save_config(Instance_TransVsGain)


# # # # # # ###########################################################################################################
# ################################### code for running Amplitude rabi Blob
# UpdateConfig = {
#     ##### define attenuators
#     "yokoVoltage": -2.80,
#     ###### cavity
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 5, # us
#     "read_pulse_gain": 10000, # [DAC units]
#     "read_pulse_freq": 6437.2,
#     ##### spec parameters for finding the qubit frequency
#     "qubit_freq_start": 3582 - 5,
#     "qubit_freq_stop": 3582 + 5,
#     "RabiNumPoints": 41,  ### number of points
#     "qubit_pulse_style": "arb",
#     "sigma": 0.150,  ### units us, define a 20ns sigma
#     # "flat_top_length": 0.100, ### in us
#     "relax_delay": 500,  ### turned into us inside the run function
#     ##### amplitude rabi parameters
#     "qubit_gain_start": 0,
#     "qubit_gain_step": 1000, ### stepping amount of the qubit gain
#     "qubit_gain_expts": 31, ### number of steps
#     "AmpRabi_reps": 500,  # number of averages for the experiment
# }
# config = BaseConfig | UpdateConfig
#
# yoko1.SetVoltage(config["yokoVoltage"])
#
# Instance_AmplitudeRabi_Blob = AmplitudeRabi_Blob(path="dataTestRabiAmpBlob", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg, progress=True)
# data_AmplitudeRabi_Blob = AmplitudeRabi_Blob.acquire(Instance_AmplitudeRabi_Blob)
# AmplitudeRabi_Blob.save_data(Instance_AmplitudeRabi_Blob, data_AmplitudeRabi_Blob)
# AmplitudeRabi_Blob.save_config(Instance_AmplitudeRabi_Blob)

# #
# #
# # # # # # # # # ######################################################################################################################
# ######### T1 measurement
# UpdateConfig = {
#     ##### define attenuators
#     "yokoVoltage": -2.8,
#     ###### cavity
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 5, # us
#     "read_pulse_gain": 10000, # [DAC units]
#     "read_pulse_freq": 6437.2, # [MHz] actual frequency is this number + "cavity_LO"
#     ##### spec parameters for finding the qubit frequency
#     "qubit_freq": 2034.5,
#     "qubit_gain": 12000,
#     "sigma": 0.150,  ### units us, define a 20ns sigma
#     # "flat_top_length": 0.200, ### in us
#     "qubit_pulse_style": "arb", #### arb means gaussain here
#     "relax_delay": 1000,  ### turned into us inside the run function
#     ##### T1 parameters
#     "start": 0, ### us
#     "step": 10, ### us
#     "expts": 101, ### number of experiemnts
#     "reps": 500, ### number of averages on each experiment
# }
# config = BaseConfig | UpdateConfig
#
# yoko1.SetVoltage(config["yokoVoltage"])
# print("Voltage is ", yoko1.GetVoltage(), " Volts")
# #
# Instance_T1Experiment = T1Experiment(path="dataTestT1Experiment", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg,  progress=True)
# data_T1Experiment = T1Experiment.acquire(Instance_T1Experiment)
# T1Experiment.display(Instance_T1Experiment, data_T1Experiment, plotDisp=True)
# T1Experiment.save_data(Instance_T1Experiment, data_T1Experiment)
# T1Experiment.save_config(Instance_T1Experiment)

#
# # #### loop over readout parameters
# # delay_vec = np.linspace(1000, 5000, 5)
# #
# # for idx in range(len(delay_vec)):
# #     print('starting run number ' + str(idx))
# #     config["relax_delay"] = int(delay_vec[idx])
# #     print('starting scan: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
# #
# #     Instance_T1Experiment = T1Experiment(path="dataTestT1Experiment_DelaySweep", outerFolder=outerFolder, cfg=config, soc=soc,
# #                                          soccfg=soccfg, progress=True)
# #     data_T1Experiment = T1Experiment.acquire(Instance_T1Experiment)
# #     T1Experiment.display(Instance_T1Experiment, data_T1Experiment, plotDisp=True, save_fig=True)
# #     T1Experiment.save_data(Instance_T1Experiment, data_T1Experiment)
# #     T1Experiment.save_config(Instance_T1Experiment)
#
# # # #
# # # # #### loop over a tight flux range
# # # # yoko_vec = np.linspace(-1.16 - 0.2, -1.16 + 0.2, 11)
# # # #
# # # # for idx in range(len(yoko_vec)):
# # # #     print('starting run number ' + str(idx))
# # # #     config["yokoVoltage"] = yoko_vec[idx]
# # # #     yoko1.SetVoltage(config["yokoVoltage"])
# # # #     print('starting scan: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
# # # #
# # # #     Instance_T1Experiment = T1Experiment(path="dataTestT1Experiment_yokoSweep", outerFolder=outerFolder, cfg=config, soc=soc,
# # # #                                          soccfg=soccfg, progress=True)
# # # #     data_T1Experiment = T1Experiment.acquire(Instance_T1Experiment)
# # # #     T1Experiment.display(Instance_T1Experiment, data_T1Experiment, plotDisp=True, save_fig=True)
# # # #     T1Experiment.save_data(Instance_T1Experiment, data_T1Experiment)
# # # #     T1Experiment.save_config(Instance_T1Experiment)


# #######################################################################################################################
# #
# ########## T2 measurement
# UpdateConfig = {
#     ##### define flux point
#     "yokoVoltage": -2.8,    ###### cavity
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 5, # us
#     "read_pulse_gain": 10000, # [DAC units]
#     "read_pulse_freq": 6437.2, # [MHz] actual frequency is this number + "cavity_LO"
#     ##### spec parameters for finding the qubit frequency
#     "qubit_freq": 2034.5 - 1.0,
#     "qubit_gain": 16000,
#     "pi2_qubit_gain": 8000,
#     "sigma": 0.150,  ### units us, define a 20ns sigma
#     "qubit_pulse_style": "arb", #### arb means gaussain here
#     # "flat_top_length": 0.080,
#     "relax_delay": 1000,  ### turned into us inside the run function
#     ##### T2 ramsey parameters
#     "start": 0.00, ### us
#     "step": 0.05, ### us
#     "expts": 101, ### number of experiemnts
#     "reps": 500, ### number of averages on each experiment
# }
# config = BaseConfig | UpdateConfig
#
# yoko1.SetVoltage(config["yokoVoltage"])
#
# Instance_T2Experiment = T2Experiment(path="dataTestT2RExperiment", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
# data_T2Experiment = T2Experiment.acquire(Instance_T2Experiment)
# T2Experiment.display(Instance_T2Experiment, data_T2Experiment, plotDisp=True)
# T2Experiment.save_data(Instance_T2Experiment, data_T2Experiment)
# T2Experiment.save_config(Instance_T2Experiment)
#
# # for idx in range(4):
# #     Instance_T2Experiment = T2Experiment(path="dataTestT2RExperiment", outerFolder=outerFolder, cfg=config, soc=soc,
# #                                          soccfg=soccfg)
# #     data_T2Experiment = T2Experiment.acquire(Instance_T2Experiment)
# #     T2Experiment.display(Instance_T2Experiment, data_T2Experiment, plotDisp=True)
# #     T2Experiment.save_data(Instance_T2Experiment, data_T2Experiment)
# #     T2Experiment.save_config(Instance_T2Experiment)


######################################################################################################################
# ######### T2 echo measurement
# UpdateConfig = {
#     ##### define attenuators
#     "yokoVoltage": -1.16,
#     ###### cavity
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 10, # us
#     "read_pulse_gain": 10000, # [DAC units]
#     "read_pulse_freq": 5988.37, # [MHz] actual frequency is this number + "cavity_LO"
#     ##### spec parameters for finding the qubit frequency
#     "qubit_freq": 1716.5,
#     "pi_qubit_gain": 3300,
#     "pi2_qubit_gain": 1650,
#     "sigma": 0.050,  ### units us, define a 20ns sigma
#     "qubit_pulse_style": "arb", #### arb means gaussain here
#     "relax_delay": 3000,  ### turned into us inside the run function
#     ##### T1 parameters
#     "start": 0, ### us
#     "step": 5, ### us
#     "expts": 201, ### number of experiemnts
#     "reps": 500, ### number of averages on each experiment
# }
# config = BaseConfig | UpdateConfig
# yoko1.SetVoltage(config["yokoVoltage"])
# print("Voltage is ", yoko1.GetVoltage(), " Volts")
#
# Instance_T2EchoExperiment = T2EchoExperiment(path="dataTestT2EchoExperiment", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg,  progress=True)
# data_T2EchoExperiment = T2EchoExperiment.acquire(Instance_T2EchoExperiment)
# T2EchoExperiment.display(Instance_T2EchoExperiment, data_T2EchoExperiment, plotDisp=True)
# T2EchoExperiment.save_data(Instance_T2EchoExperiment, data_T2EchoExperiment)
# T2EchoExperiment.save_config(Instance_T2EchoExperiment)

# ######################################################################################################################
# # # # ####################################### code for running basic single shot exerpiment
# UpdateConfig = {
#     ##### set yoko
#     "yokoVoltage": -13.0,
#     ###### cavity
#     "reps": 2000,  # this will used for all experiements below unless otherwise changed in between trials
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 10, # [Clock ticks]
#     "read_pulse_gain": 18000, # [DAC units]
#     "read_pulse_freq": 5988.44, # [MHz]
#     ##### qubit spec parameters
#     "qubit_pulse_style": "arb",
#     "qubit_gain": 16000,
#     # "qubit_length": 10,  ###us, this is used if pulse style is const
#     "sigma": 0.100,  ### units us, define a 20ns sigma
#     "qubit_freq": 1713.0,
#     "relax_delay": 5000,  ### turned into us inside the run function
#     #### define shots
#     "shots": 1000, ### this gets turned into "reps"
# }
# config = BaseConfig | UpdateConfig
#
# yoko1.SetVoltage(config["yokoVoltage"])
# #
# # ##### run the single shot experiment
# # loop_len = 11
# # #freq_vec = config["read_pulse_freq"] + np.linspace(-0.2, 0.2, loop_len)
# # #qubit_gain_vec = np.linspace(10000, 29000, loop_len, dtype=int)
# # read_gain_vec = np.linspace(4000, 5000, loop_len, dtype=int)
# # fid_vec = np.zeros(loop_len)
# # for idx in range(loop_len):
# #     #config["read_pulse_freq"] = freq_vec[idx]
# #     #config["qubit_gain"] = qubit_gain_vec[idx]
# #     config["read_pulse_gain"] = read_gain_vec[idx]
# #     Instance_SingleShotProgram = SingleShotProgram(path="dataTestSingleShotProgram", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
# #     data_SingleShot = SingleShotProgram.acquire(Instance_SingleShotProgram)
# #     SingleShotProgram.display(Instance_SingleShotProgram, data_SingleShot, plotDisp=False, save_fig=False)
# #     # SingleShotProgram.save_data(Instance_SingleShotProgram, data_SingleShot)
# #     # SingleShotProgram.save_config(Instance_SingleShotProgram)
# #
# #     plt.show()
# #
# #     fid_vec[idx] = Instance_SingleShotProgram.fid
# #
# # plt.figure(107)
# # #plt.plot(qubit_gain_vec, fid_vec, 'o')
# # #plt.xlabel('qubit gain')
# #
# # plt.plot(read_gain_vec, fid_vec, 'o')
# # plt.xlabel('readout gain')
# #
# # # plt.plot(freq_vec, fid_vec, 'o')
# # # plt.xlabel('read pulse freq')
# # plt.ylabel('fidelity')
# # plt.ylim([0,1])
# #
#
# Instance_SingleShotProgram = SingleShotProgram(path="dataTestSingleShotProgram", outerFolder=outerFolder, cfg=config,
#                                                soc=soc, soccfg=soccfg)
# data_SingleShot = SingleShotProgram.acquire(Instance_SingleShotProgram)
# SingleShotProgram.display(Instance_SingleShotProgram, data_SingleShot, plotDisp=True, save_fig=True)

#####################################################################################################################

# ####################################### code for running  2D single shot fidelity optimization
# UpdateConfig = {
#     ##### set yoko
#     "yokoVoltage": -7.2,
#     #### define basic parameters
#     ###### cavity
#     "reps": 2000,  # this will used for all experiements below unless otherwise changed in between trials
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 10, # [Clock ticks]
#     "read_pulse_gain": 3500, # [DAC units]
#     "read_pulse_freq": 5988.275, # [MHz]
#     ##### qubit spec parameters
#     "qubit_pulse_style": "arb",
#     "qubit_gain": 20000,
#     # "qubit_length": 10,  ###us, this is used if pulse style is const
#     "sigma": 0.200,  ### units us, define a 20ns sigma
#     "qubit_freq": 1202.5,
#     "relax_delay": 1000,  ### turned into us inside the run function
#     #### define shots
#     "shots": 1000, ### this gets turned into "reps"
#     #### define the loop parameters
#     "x_var": "read_pulse_freq",
#     "x_start": 5988.275 - 0.5,
#     "x_stop": 5988.275 + 0.5,
#     "x_num": 21,
#
#     "y_var": "read_pulse_gain",
#     "y_start": 3000,
#     "y_stop": 5000,
#     "y_num": 3,
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


# # ####################################################################################################################
# ###################################### code for running Amplitude rabi Blob with post selection
# UpdateConfig = {
#     ##### define attenuators
#     "yokoVoltage": -0.18,
#     ###### cavity
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 5, # us
#     "read_pulse_gain": 8000, # [DAC units]
#     "read_pulse_freq": 6064.9, # [MHz]
#     ##### spec parameters for finding the qubit frequency
#     "qubit_freq_start": 284 - 10,
#     "qubit_freq_stop": 284 + 10,
#     "RabiNumPoints": 21,  ### number of points
#     "qubit_pulse_style": "arb",
#     "sigma": 0.015,  ### units us, define a 20ns sigma
#     # "flat_top_length": 0.600, ### in us
#     "relax_delay": 100,  ### turned into us inside the run function
#     ##### amplitude rabi parameters
#     "qubit_gain_start": 10000,
#     "qubit_gain_step": 2000, ### stepping amount of the qubit gain
#     "qubit_gain_expts": 11, ### number of steps
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


#
# #################################### code for running Amplitude rabi Blob while sweeping flux
# UpdateConfig = {
#     ##### define attenuators
#     "yokoVoltage": -0.18,
#     ###### cavity
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 5, # us
#     "read_pulse_gain": 8000, # [DAC units]
#     "read_pulse_freq": 6064.9, # [MHz]
#     ##### spec parameters for finding the qubit frequency
#     "qubit_freq_start": 290 - 20,
#     "qubit_freq_stop": 290 + 20,
#     "RabiNumPoints": 21,  ### number of points
#     "qubit_pulse_style": "arb",
#     "sigma": 0.015,  ### units us, define a 20ns sigma
#     "qubit_gain": 18000,
#     # "flat_top_length": 0.200, ### in us
#     "relax_delay": 100,  ### turned into us inside the run function
#     ##### define the yoko voltage
#     "yokoVoltageStart": -0.18 - 0.02,
#     "yokoVoltageStop": -0.18 + 0.02,
#     "yokoVoltageNumPoints": 11,
#     # "AmpRabi_reps": 2000,  # number of averages for the experiment
#     ##### define number of clusters to use
#     "cen_num": 2,
#     "shots": 4000,  ### this gets turned into "reps"
# }
# config = BaseConfig | UpdateConfig
#
# yoko1.SetVoltage(config["yokoVoltage"])
#
# Instance_AmplitudeRabiFlux_PS = AmplitudeRabiFlux_PS(path="dataTestAmplitudeRabiFlux_PS", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg, progress=True)
# data_AmplitudeRabiFlux_PS = AmplitudeRabiFlux_PS.acquire(Instance_AmplitudeRabiFlux_PS)
# AmplitudeRabiFlux_PS.save_data(Instance_AmplitudeRabiFlux_PS, data_AmplitudeRabiFlux_PS)
# AmplitudeRabiFlux_PS.save_config(Instance_AmplitudeRabiFlux_PS)


# # # ##################################################################################################################
# ################################## code for running qubit spec on repeat
# UpdateConfig = {
#     ##### define attenuators
#     "yokoVoltage": -2.97 - 0.00,
#     ###### cavity
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 20, # us
#     "read_pulse_gain": 11000, # [DAC units]
#     "read_pulse_freq": 6437.5,
#     ##### spec parameters for finding the qubit frequency
#     "qubit_freq_start": 1908.5 - 5,
#     "qubit_freq_stop": 1908.5 + 5,
#     "SpecNumPoints": 201,  ### number of points
#     "qubit_pulse_style": "arb",
#     "sigma": 0.400,  ### units us
#     "qubit_length": 1, ### units us, doesnt really get used though
#     # "flat_top_length": 0.300, ### in us
#     "relax_delay": 800,  ### turned into us inside the run function
#     "qubit_gain": 400, # Constant gain to use
#     # "qubit_gain_start": 18500, # shouldn't need this...
#     "reps": 750,
#     ##### time parameters
#     "delay": 120, # s
#     "repetitions": 201,  ### number of steps
# }
# config = BaseConfig | UpdateConfig
#
# yoko1.SetVoltage(config["yokoVoltage"])
# #
# Instance_QubitSpecRepeat = QubitSpecRepeat(path="dataQubitSpecRepeat", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg, progress=True)
# data_QubitSpecRepeat = QubitSpecRepeat.acquire(Instance_QubitSpecRepeat)
# QubitSpecRepeat.save_data(Instance_QubitSpecRepeat, data_QubitSpecRepeat)
# QubitSpecRepeat.save_config(Instance_QubitSpecRepeat)

# #
# for idx in range(5):
#     Instance_QubitSpecRepeat = QubitSpecRepeat(path="dataQubitSpecRepeat", outerFolder=outerFolder, cfg=config, soc=soc,
#                                                soccfg=soccfg, progress=True)
#     data_QubitSpecRepeat = QubitSpecRepeat.acquire(Instance_QubitSpecRepeat)
#     QubitSpecRepeat.save_data(Instance_QubitSpecRepeat, data_QubitSpecRepeat)
#     QubitSpecRepeat.save_config(Instance_QubitSpecRepeat)

# ##################################################################################################################
# ################################## code for running qubit spec on repeat on multiple qubits
# UpdateConfig = {
#     ##### define attenuators
#     "yokoVoltage": -3.1,
#     ########################### Qubit 1
#     ###### cavity
#     "read1_pulse_style": "const", # --Fixed
#     "read1_length": 20, # us
#     "read1_pulse_gain": 8000, # [DAC units]
#     "read1_pulse_freq": 6437.5,
#     ##### spec parameters for finding the qubit frequency
#     "qubit1_freq_start": 1789.5 - 10,
#     "qubit1_freq_stop": 1789.5 + 10,
#     "SpecNumPoints1": 101,  ### number of points
#     "qubit1_pulse_style": "arb",
#     "sigma1": 0.400,  ### units us
#     # "qubit1_length": 1, ### units us, doesnt really get used though
#     # "flat_top_length": 0.025, ### in us
#     "qubit1_gain": 12000, # Constant gain to use
#     # "qubit_gain_start": 18500, # shouldn't need this...
#
#     ############################ Qubit 2
#     ###### cavity
#     "read2_pulse_style": "const",  # --Fixed
#     "read2_length": 20,  # us
#     "read2_pulse_gain": 8000,  # [DAC units]
#     "read2_pulse_freq": 6437.5,
#     ##### spec parameters for finding the qubit frequency
#     "qubit2_freq_start": 2925.0 - 10,
#     "qubit2_freq_stop": 2925.0 + 10,
#     "SpecNumPoints2": 101,  ### number of points
#     "qubit2_pulse_style": "arb",
#     "sigma2": 0.400,  ### units us
#     # "qubit2_length": 1,  ### units us, doesnt really get used though
#     # "flat_top_length": 0.025, ### in us
#     "qubit2_gain": 2000,  # Constant gain to use
#     # "qubit_gain_start": 18500, # shouldn't need this...
#
#     #### for both qubits
#     "relax_delay": 750,  ### turned into us inside the run function
#     "reps": 750,
#     ##### time parameters
#     "delay":  120, # s
#     "repetitions": 331,  ### number of steps
# }
# config = BaseConfig | UpdateConfig
#
# yoko1.SetVoltage(config["yokoVoltage"])
# #
# Instance_TwoQubitFluxDrift = TwoQubitFluxDrift(path="dataTwoQubitFluxDrift", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg, progress=True)
# data_TwoQubitFluxDrift = TwoQubitFluxDrift.acquire(Instance_TwoQubitFluxDrift)
# TwoQubitFluxDrift.save_data(Instance_TwoQubitFluxDrift, data_TwoQubitFluxDrift)
# TwoQubitFluxDrift.save_config(Instance_TwoQubitFluxDrift)

#####################################################################################################################

print('end time: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))

plt.show()

# #
# plt.show(block = True)
