
#### import packages
import os
path = os.getcwd()
os.add_dll_directory(os.path.dirname(path)+'\\PythonDrivers')
from STFU.Client_modules.Calib_escher.initialize import *
from STFU.Client_modules.Experiments.mTransmission_SaraTest import Transmission
from STFU.Client_modules.Experiments.mSpecSlice_SaraTest import SpecSlice
from STFU.Client_modules.Experiments.mAmplitudeRabi import AmplitudeRabi
from STFU.Client_modules.Experiments.mTransVsGain import TransVsGain
from STFU.Client_modules.Experiments.mAmplitudeRabi_Blob import AmplitudeRabi_Blob
from STFU.Client_modules.Experiments.mAmplitudeRabi_CavityPower import AmplitudeRabi_CavityPower
from STFU.Client_modules.Experiments.mT1Experiment import T1Experiment
from STFU.Client_modules.Experiments.mT2Experiment import T2Experiment
from STFU.Client_modules.Experiments.mT2EchoExperiment import T2EchoExperiment
from STFU.Client_modules.Experiments.mSingleShotProgram import SingleShotProgram
from STFU.Client_modules.Experiments.mSingleShot_2Dsweep import SingleShot_2Dsweep
from STFU.Client_modules.Experiments.mAmplitudeRabiBlob_PS import AmplitudeRabi_PS
from STFU.Client_modules.Experiments.mAmplitudeRabiFlux_PS import AmplitudeRabiFlux_PS
from STFU.Client_modules.Experiments.mQubitSpecRepeat import QubitSpecRepeat
from STFU.Client_modules.Experiments.mQubit_ef_spectroscopy import Qubit_ef_spectroscopy
from matplotlib import pyplot as plt

#### define the saving path
outerFolder = "Z:\\TantalumFluxonium\\Data\\2023_07_20_BF2_cooldown_3\\TF3SC1\\"

###qubitAtten = attenuator(27797, attenuation_int= 10, print_int = False)


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
#
# ################################### code for transmission vs power
# UpdateConfig = {
#     "yokoVoltage": -1.39, #3.1
#     ##### change gain instead option
#     "trans_gain_start": 0000,
#     "trans_gain_stop": 30000,
#     "trans_gain_num": 31,
#     ###### cavity
#     "trans_reps": 500,  # this will used for all experiments below unless otherwise changed in between trials
#     "read_pulse_style": "const",  # --Fixed
#     "readout_length": 20,  # [us]
#     # "read_pulse_gain": 10000,  # [DAC units]
#     "trans_freq_start": 5987,  # [MHz] actual frequency is this number + "cavity_LO"
#     "trans_freq_stop": 5989,  # [MHz] actual frequency is this number + "cavity_LO"
#     "TransNumPoints": 201,  ### number of points in the transmission frequecny
#     "relax_delay": 10, # us
# }
#
# config = BaseConfig | UpdateConfig
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


#################################################################################################################
################################## code for running Amplitude rabi Blob
# UpdateConfig = {
#     ##### define attenuators
#     "yokoVoltage": 0.815,
#     ###### cavity
#     "read_pulse_style": "const",  # --Fixed
#     "read_length": 10,  # us
#     "read_pulse_gain": 12000,  # [DAC units]
#     "read_pulse_freq": 5988.33,  # MHz
#     ##### spec parameters for finding the qubit frequency
#     "qubit_freq_start": 1716 - 2,
#     "qubit_freq_stop": 1716 + 20,
#     "RabiNumPoints": 41,  ### number of points
#     "qubit_pulse_style": "arb",
#     "sigma": 0.3,  ### units us, define a 20ns sigma
#     # "flat_top_length": 0.025, ### in us
#     "relax_delay": 500,  ### turned into us inside the run function
#     ##### amplitude rabi parameters
#     "qubit_gain_start": 0,
#     "qubit_gain_step": 2000,  ### stepping amount of the qubit gain
#     "qubit_gain_expts": 15,  ### number of steps
#     "AmpRabi_reps": 500,  # number of averages for the experiment
#     "two_pulses": False, # Pulse twice for calibrating a pi/2 pulse
# }
# config = BaseConfig | UpdateConfig
#
# yoko1.SetVoltage(config["yokoVoltage"])
#
# Instance_AmplitudeRabi_Blob = AmplitudeRabi_Blob(path="dataTestRabiAmpBlob", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg, progress=True)
# data_AmplitudeRabi_Blob = AmplitudeRabi_Blob.acquire(Instance_AmplitudeRabi_Blob)
# AmplitudeRabi_Blob.save_data(Instance_AmplitudeRabi_Blob, data_AmplitudeRabi_Blob)
# AmplitudeRabi_Blob.save_config(Instance_AmplitudeRabi_Blob)


####################################### code for running Amplitude rabi vs Cavity Power
# UpdateConfig = {
#     ##### define attenuators
#     "yokoVoltage": -0.15,
#     ###### cavity gain steps
#     "reps": 5,  # this will used for all experiements below unless otherwise changed in between trials
#     "readout_length": 10, # us
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 10, # us
#     "read_pulse_gain" : 3000,
#     "cav_amp_start": 2000, # [DAC units]
#     "cav_amp_stop": 4000,
#     "cavNumPoints": 11,
#     "read_pulse_freq": 559.17, # [MHz] actual frequency is this number + "cavity_LO"
#     ##### define tranmission experiment parameters
#     "TransSpan": 2, ### MHz, span will be center+/- this parameter
#     "TransNumPoitns": 200, ### number of points in the transmission frequecny
#     ##### the qubit frequency
#     "qubit_freq" : 264.071,
#     "qubit_pulse_style": "arb",
#     "sigma": 0.2,  ### units us, define a 20ns sigma
#     "relax_delay": 6000,  ### turned into us inside the run function
#     ##### amplitude rabi parameters
#     "qubit_gain_start": 0,
#     "qubit_gain_step": 200, ### stepping amount of the qubit gain
#     "qubit_gain_expts": 11, ### number of steps
#     "AmpRabi_reps": 500,  # number of averages for the experiment
#     "two_pulses": False, # If we want to calibrate a pi/2 pulse
# }
# config = BaseConfig | UpdateConfig
#
# yoko1.SetVoltage(config["yokoVoltage"])
#
# Instance_AmplitudeRabi_CavityPower = AmplitudeRabi_CavityPower(path="dataTestRabiAmpCavity", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg, progress=True)
# data_AmplitudeRabi_CavityPower = AmplitudeRabi_CavityPower.acquire(Instance_AmplitudeRabi_CavityPower)
# AmplitudeRabi_CavityPower.save_data(Instance_AmplitudeRabi_CavityPower, data_AmplitudeRabi_CavityPower)
# AmplitudeRabi_CavityPower.save_config(Instance_AmplitudeRabi_CavityPower)


######################################################################################################################
# ######### T1 measurement
# UpdateConfig = {
#     ##### define attenuators
#     "yokoVoltage": 0.815,
#     ###### cavity
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 12, # us
#     "read_pulse_gain": 12000, # [DAC units]
#     "read_pulse_freq": 5988.33 , # [MHz] actual frequency is this number + "cavity_LO"
#     ##### spec parameters for finding the qubit frequency
#     "qubit_freq": 1715.6,
#     "qubit_gain": 20000,
#     "sigma": 0.300,  ### units us, define a 20ns sigma
#     "qubit_pulse_style": "arb", #### arb means gaussain here
#     "relax_delay": 1000,  ### turned into us inside the run function
#     ##### T1 parameters
#     "start": 0, ### us
#     "step": 40, ### us
#     "expts": 31, ### number of experiemnts
#     "reps": 5000, ### number of averages on each experiment
# }
# config = BaseConfig | UpdateConfig
#
# # small_update_config = {
# #     "start": 0, ### us
# #     "step": 100, ### us
# #     "expts": 4, ### number of experiemnts
# #     "reps": 3000, ### number of averages on each experiment
# # }
# # config = config | small_update_config
# #
# # print(config)
# # config = UpdateConfig
#
# yoko1.SetVoltage(config["yokoVoltage"])
# print("Voltage is ", yoko1.GetVoltage(), " Volts")
#
# Instance_T1Experiment = T1Experiment(path="dataTestT1Experiment", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg,  progress=True)
# data_T1Experiment = T1Experiment.acquire(Instance_T1Experiment)
# T1Experiment.display(Instance_T1Experiment, data_T1Experiment, plotDisp=True)
# T1Experiment.save_data(Instance_T1Experiment, data_T1Experiment)
# T1Experiment.save_config(Instance_T1Experiment)
#
# # for idx in range(30):
# #     Instance_T1Experiment = T1Experiment(path="dataTestT1Experiment", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg,  progress=True)
# #     data_T1Experiment = T1Experiment.acquire(Instance_T1Experiment)
# #     T1Experiment.display(Instance_T1Experiment, data_T1Experiment, plotDisp=True)
# #     T1Experiment.save_data(Instance_T1Experiment, data_T1Experiment)
# #     T1Experiment.save_config(Instance_T1Experiment)


######################################################################################################################
######### T2 Ramsey measurement doesn't work, the code does nothing
# UpdateConfig = {
#     ##### define attenuators
#     "yokoVoltage": 0.815,
#     ###### cavity
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 8, # us
#     "read_pulse_gain": 14000, # [DAC units]
#     "read_pulse_freq": 5988.33, # [MHz] actual frequency is this number + "cavity_LO"
#     ##### spec parameters for finding the qubit frequency
#     "qubit_freq": 1715.6,
#     "pi_qubit_gain": 20000, # Gain of pi pulse
#     "pi2_qubit_gain": 10000, # Gain of pi/2 pulse
#     "sigma": 0.300,  ### units us, define a 20ns sigma
#     "qubit_pulse_style": "arb", #### arb means gaussain here
#     "relax_delay": 1500,  ### turned into us inside the run function
#     ##### T1 parameters
#     "start": 0, ### us
#     "step": 15, ### us
#     "expts": 21, ### number of experiemnts
#     "reps": 1000, ### number of averages on each experiment
# }
# config = BaseConfig | UpdateConfig
# yoko1.SetVoltage(config["yokoVoltage"])
# print("Voltage is ", yoko1.GetVoltage(), " Volts")
#
# Instance_T2Experiment = T2Experiment(path="dataTestT2Experiment", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg,  progress=True)
# data_T2Experiment = T2Experiment.acquire(Instance_T2Experiment)
# T2Experiment.display(Instance_T2Experiment, data_T2Experiment, plotDisp=True)
# T2Experiment.save_data(Instance_T2Experiment, data_T2Experiment)
# T2Experiment.save_config(Instance_T2Experiment)

######################################################################################################################
######### T2 echo measurement
# UpdateConfig = {
#     ##### define attenuators
#     "yokoVoltage": 0.815,
#     ###### cavity
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 8, # us
#     "read_pulse_gain": 14000, # [DAC units]
#     "read_pulse_freq": 5988.33, # [MHz] actual frequency is this number + "cavity_LO"
#     ##### spec parameters for finding the qubit frequency
#     "qubit_freq": 1715.6,
#     "pi_qubit_gain": 20000, # Gain of pi pulse
#     "pi2_qubit_gain": 10000, # Gain of pi/2 pulse
#     "sigma": 0.300,  ### units us, define a 20ns sigma
#     "qubit_pulse_style": "arb", #### arb means gaussain here
#     "relax_delay": 1500,  ### turned into us inside the run function
#     ##### T1 parameters
#     "start": 0, ### us
#     "step": 15, ### us
#     "expts": 31, ### number of experiemnts
#     "reps": 10000, ### number of averages on each experiment
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
# # # ####################################### code for running basic single shot exerpiment
# UpdateConfig = {
#     ##### set yoko
#     "yokoVoltage": 0.815,
#     ###### cavity
#     "reps": 2000,  # this will used for all experiements below unless otherwise changed in between trials
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 8, # [Clock ticks]
#     "read_pulse_gain": 14000, # [DAC units]
#     "read_pulse_freq": 5988.25, # [MHz]
#     ##### qubit spec parameters
#     "qubit_pulse_style": "arb",
#     "qubit_gain": 20000,
#     # "qubit_length": 10,  ###us, this is used if pulse style is const
#     "sigma": 0.300,  ### units us, define a 20ns sigma
#     "qubit_freq": 1715.6,
#     "relax_delay": 1000,  ### turned into us inside the run function
#     #### define shots
#     "shots": 3000, ### this gets turned into "reps"
# }
# config = BaseConfig | UpdateConfig
#
# yoko1.SetVoltage(config["yokoVoltage"])
# #
# # # ##### run the single shot experiment on loop
# # loop_len = 11
# # freq_vec = config["read_pulse_freq"] + np.linspace(-0.2, 0.2, loop_len)
# # # read_gain_vec = np.linspace(10000, 15000, loop_len, dtype=int)
# # # read_len_vec = np.linspace(5, 15, loop_len, dtype=int)
# # # qubit_gain_vec = np.linspace(12000, 14000, loop_len, dtype=int)
# # # qubit_freq_vec = config["qubit_freq"] + np.linspace(-0.2, 0.2, loop_len)
#
# # fid_vec = np.zeros(loop_len)
# # for idx in range(loop_len):
# #     config["read_pulse_freq"] = freq_vec[idx]
# #     # config["read_pulse_gain"] = rea   ad_gain_vec[idx]
# #     # config["read_length"] = read_len_vec[idx]
# #     # config["qubit_freq"] = qubit_freq_vec[idx]
# #     # config["qubit_gain"] = qubit_gain_vec[idx]
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
# #
# # # plt.plot(read_gain_vec, fid_vec, 'o')
# # # plt.xlabel('readout gain')
# #
# # # plt.plot(freq_vec, fid_vec, 'o')
# # # plt.xlabel('read pulse freq')
# #
# # # plt.plot(read_len_vec, fid_vec, 'o')
# # # plt.xlabel('Read pulse length (us)')
# #
# # # plt.plot(qubit_freq_vec, fid_vec, 'o')
# # # plt.xlabel('qubit freq')
# #
# # plt.plot(qubit_gain_vec, fid_vec, 'o')
# # plt.xlabel('qubit gain')
# #
# # plt.ylabel('fidelity')
# # plt.ylim([0,1])
#
#
# Instance_SingleShotProgram = SingleShotProgram(path="dataTestSingleShotProgram", outerFolder=outerFolder, cfg=config,
#                                                soc=soc, soccfg=soccfg)
# data_SingleShot = SingleShotProgram.acquire(Instance_SingleShotProgram)
# SingleShotProgram.display(Instance_SingleShotProgram, data_SingleShot, plotDisp=True, save_fig=True)
# SingleShotProgram.save_data(Instance_SingleShotProgram, data_SingleShot)
# SingleShotProgram.save_config(Instance_SingleShotProgram)

#####################################################################################################################

# ####################################### code for running  2D single shot fidelity optimization
# UpdateConfig = {
#     ##### set yoko
#     "yokoVoltage": 0.815,
#     #### define basic parameters
#     ###### cavity
#     "reps": 2000,  # this will used for all experiements below unless otherwise changed in between trials
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 8, # [Clock ticks]
#     "read_pulse_gain": 11000, # [DAC units]
#     "read_pulse_freq": 5988.33, # [MHz]
#     ##### qubit spec parameters
#     "qubit_pulse_style": "arb",
#     "qubit_gain": 20000,
#     # "qubit_length": 10,  ###us, this is used if pulse style is const
#     "sigma": 0.300,  ### units us, define a 20ns sigma
#     "qubit_freq": 1715.6,
#     "relax_delay": 500,  ### turned into us inside the run function
#     #### define shots
#     "shots": 1000, ### this gets turned into "reps"
#     #### define the loop parameters
#     "x_var": "read_pulse_freq",
#     "x_start": 5988.27 - 0.5,
#     "x_stop": 5988.27 + 0.5,
#     "x_num": 51,
#
#     "y_var": "read_pulse_gain",
#     "y_start": 14500,
#     "y_stop": 15500,
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


#####################################################################################################################
# ###################################### code for running Amplitude rabi Blob with post selection
# UpdateConfig = {
#     ##### define attenuators
#     "yokoVoltage": 3.125,
#     ###### cavity
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 10, # us
#     "read_pulse_gain": 4000, # [DAC units]
#     "read_pulse_freq": 5988.375, # [MHz]
#     ##### spec parameters for finding the qubit frequency
#     "qubit_freq_start": 140,
#     "qubit_freq_stop": 160,
#     "RabiNumPoints": 21,  ### number of points
#     "qubit_pulse_style": "arb",
#     "sigma": 0.200,  ### units us, define a 20ns sigma
#     # "flat_top_length": 0.025, ### in us
#     "relax_delay": 1000,  ### turned into us inside the run function
#     ##### amplitude rabi parameters
#     "qubit_gain_start": 3000,
#     "qubit_gain_step": 2000, ### stepping amount of the qubit gain
#     "qubit_gain_expts": 14, ### number of steps
#     # "AmpRabi_reps": 2000,  # number of averages for the experiment
#     ##### define number of clusters to use
#     "cen_num": 3,
#     "shots": 1000,  ### this gets turned into "reps"
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
#     "yokoVoltage": 0.87,
#     ###### cavity
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 10, # us
#     "read_pulse_gain": 14500, # [DAC units]
#     "read_pulse_freq": 8891.2, # [MHz]
#     ##### spec parameters for finding the qubit frequency
#     "qubit_freq_start": 303,
#     "qubit_freq_stop": 304.5,
#     "RabiNumPoints": 31,  ### number of points
#     "qubit_pulse_style": "arb",
#     "sigma": 1,  ### units us, define a 20ns sigma
#     "qubit_gain": 17000,
#     # "flat_top_length": 0.025, ### in us
#     "relax_delay": 3000,  ### turned into us inside the run function
#     ##### define the yoko voltage
#     "yokoVoltageStart": 0.85,
#     "yokoVoltageStop": 0.9,
#     "yokoVoltageNumPoints": 11,
#     # "AmpRabi_reps": 2000,  # number of averages for the experiment
#     ##### define number of clusters to use
#     "cen_num": 3,
#     "shots": 2000,  ### this gets turned into "reps"
# }
# config = BaseConfig | UpdateConfig
#
# yoko1.SetVoltage(config["yokoVoltage"])
#
# Instance_AmplitudeRabiFlux_PS = AmplitudeRabiFlux_PS(path="dataTestAmplitudeRabiFlux_PS", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg, progress=True)
# data_AmplitudeRabiFlux_PS = AmplitudeRabiFlux_PS.acquire(Instance_AmplitudeRabiFlux_PS)
# AmplitudeRabiFlux_PS.save_data(Instance_AmplitudeRabiFlux_PS, data_AmplitudeRabiFlux_PS)
# AmplitudeRabiFlux_PS.save_config(Instance_AmplitudeRabiFlux_PS)


#####################################################################################################################
################################ code for running qubit spec on repeat
# UpdateConfig = {
#     ##### define attenuators
#     "yokoVoltage": 0.7,
#     ###### cavity
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 12, # us
#     "read_pulse_gain": 12000, # [DAC units]
#     "read_pulse_freq": 5988.33,
#     ##### spec parameters for finding the qubit frequency
#     "qubit_freq_start": 1704, #1167-10
#     "qubit_freq_stop": 1718,
#     "SpecNumPoints": 31,  ### number of points
#     "qubit_pulse_style": "arb",
#     "qubit_length": 1, # us, changes experiment time but is necessary for "const" style
#     "sigma": 0.300,  ### units us, define a 20ns sigma
#     # "qubit_length": 1, ### units us, doesnt really get used though
#     # "flat_top_length": 0.025, ### in us
#     "relax_delay": 500,  ### turned into us inside the run function
#     "qubit_gain": 25000, # Constant gain to use
#     # "qubit_gain_start": 18500, # shouldn't need this...
#     "reps": 200, # number of averages of every experiment
#     ##### time parameters
#     "delay":  10, # s
#     "repetitions": 2,  ### number of steps
# }
# config = BaseConfig | UpdateConfig
#
# yoko1.SetVoltage(config["yokoVoltage"])
# # #
# Instance_QubitSpecRepeat = QubitSpecRepeat(path="dataQubitSpecRepeat", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg, progress=True)
# data_QubitSpecRepeat = QubitSpecRepeat.acquire(Instance_QubitSpecRepeat)
# QubitSpecRepeat.save_data(Instance_QubitSpecRepeat, data_QubitSpecRepeat)
# QubitSpecRepeat.save_config(Instance_QubitSpecRepeat)
#
# # #
# # for idx in range(4):
# #     Instance_QubitSpecRepeat = QubitSpecRepeat(path="dataQubitSpecRepeat", outerFolder=outerFolder, cfg=config, soc=soc,
# #                                                soccfg=soccfg, progress=True)
# #     data_QubitSpecRepeat = QubitSpecRepeat.acquire(Instance_QubitSpecRepeat)
# #     QubitSpecRepeat.save_data(Instance_QubitSpecRepeat, data_QubitSpecRepeat)
# #     QubitSpecRepeat.save_config(Instance_QubitSpecRepeat)


#####################################################################################################################
################################ code for running qubit ef spec
UpdateConfig = {
    ##### define attenuators
    "yokoVoltage": 0,
    ###### cavity
    "read_pulse_style": "const", # --Fixed
    "read_length": 10, # us
    "read_pulse_gain": 12000, # [DAC units]
    "read_pulse_freq": 5988.33,
    # g-e parameters
    "qubit_ge_freq": 1715.6, # MHz
    "qubit_ge_gain": 20000, # Gain for pi pulse in DAC units
    ##### spec parameters for finding the qubit frequency
    "qubit_ef_freq_start": 1150, #1167-10
    "qubit_ef_freq_step": 0.5,
    "SpecNumPoints": 201,  ### number of points
    "qubit_pulse_style": "arb",
    "qubit_length": 1, # us, changes experiment time but is necessary for "const" style
    "sigma": 0.300,  ### units us, define a 20ns sigma
    # "qubit_length": 1, ### units us, doesnt really get used though
    # "flat_top_length": 0.025, ### in us
    "relax_delay": 500,  ### turned into us inside the run function
    "qubit_gain": 20000, # Constant gain to use
    # "qubit_gain_start": 18500, # shouldn't need this...
    "reps": 1000, # number of averages of every experiment
}
config = BaseConfig | UpdateConfig

yoko1.SetVoltage(config["yokoVoltage"])
# #
Instance_Qubit_ef_spectroscopy = Qubit_ef_spectroscopy(path="dataQubit_ef_spectroscopy", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg, progress=True)
data_Qubit_ef_spectroscopy = Qubit_ef_spectroscopy.acquire(Instance_Qubit_ef_spectroscopy)
Qubit_ef_spectroscopy.save_data(Instance_Qubit_ef_spectroscopy, data_Qubit_ef_spectroscopy)
Qubit_ef_spectroscopy.save_config(Instance_Qubit_ef_spectroscopy)
Qubit_ef_spectroscopy.display(Instance_Qubit_ef_spectroscopy, data_Qubit_ef_spectroscopy, plotDisp=True)



#####################################################################################################################
plt.show()

# #
# plt.show(block = True)
