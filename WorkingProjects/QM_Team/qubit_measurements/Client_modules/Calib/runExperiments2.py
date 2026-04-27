#### import packages
import os
path = os.getcwd()
#print(path)
os.add_dll_directory(r'C:\Users\newforce\Documents\GitHub\HouckLab_QICK\WorkingProjects\QM_Team\qubit_measurements\Client_modules')
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Calib.initialize import *
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mTransmission_SaraTest import Transmission
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mTransmission import Transmission
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mTransVsGain import TransVsGain
from WorkingProjects.QM_Team .qubit_measurements.Client_modules.Experiments.mSpecSlice_SaraTest import SpecSlice
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mAmplitudeRabi import AmplitudeRabi
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mAmplitudeRabi_Blob import AmplitudeRabi_Blob
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mT1Experiment import T1Experiment
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mT2Experiment import T2Experiment
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mSingleShotProgram import SingleShotProgram
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mT2EchoExperiment import T2EchoExperiment
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mSingleShot_2Dsweep import SingleShot_2Dsweep
from matplotlib import pyplot as plt
import matplotlib
matplotlib.use('TkAgg')
import datetime

#### define the saving path
outerFolder = "Z:/t1Team/Data/2024-08-09_cooldown/TATQ01-Si_02/Q4_7p21//"

###qubitAtten = attenuator(27797, attenuation_int= 10, print_int = False)

print('starting time: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))

soc, soccfg = makeProxy()

########################################################################################################################
########################################################################################################################
#######################################################################################################################
# Experiments #####

####Transmission versus Power ###
# UpdateConfig = {
#     ##### change gain instead option
#     "trans_gain_start": 1000,
#     "trans_gain_stop": 20000,
#     "trans_gain_num": 15,
#     ###### cavity
#     "trans_reps": 500,  # this will used for all experiments below unless otherwise changed in between trials
#     "read_pulse_style": "const",  # --Fixed
#     "readout_length": 20,  # [us]
#     # "read_pulse_gain": 10000,  # [DAC units]
#     "trans_freq_start": 7214.95 - 1.0,  # [MHz] actual frequency is this number + "cavity_LO" use span for +/- part
#     "trans_freq_stop": 7214.95 + 1.0,  # [MHz] actual frequency is this number + "cavity_LO"
#     "TransNumPoints": 201,
#     "relax_delay": 20, #5 times T1 -- this is the delay between each experiment
# }
# config = BaseConfig | UpdateConfig
#
# Instance_TransVsGain = TransVsGain(path="dataTestTransVsGain", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
# data_TransVsGain = TransVsGain.acquire(Instance_TransVsGain)
# TransVsGain.save_data(Instance_TransVsGain, data_TransVsGain)
# TransVsGain.save_config(Instance_TransVsGain)

# ######################################################################################################################
# ######################################################################################################################
##Configure for Transmission Experiment ###
UpdateConfig_transmission={
    "reps": 1000,  # this will be used for all experiments below unless otherwise changed in between trials
    "read_pulse_style": "const", # --Fixed
    "readout_length": 20, # us
    "read_pulse_gain": 6000, # [DAC units]
    "read_pulse_freq": 7214.95, # #7194.787174129353, # [MHz] actual frequency is this number + "cavity_LO"
    "nqz": 2,  #### refers to cavity
    ##### define transmission experiment parameters
    "TransSpan": 1, ### MHz, span will be center+/- this parameter
    "TransNumPoints": 101, ### number of points in the transmission frequecny
}
# #
# ## Configure for qubit experiment ###
UpdateConfig_qubit = {
    "qubit_pulse_style": "const",
    "qubit_gain": 75,
    "qubit_freq": 3795,  #Rabi Amp use this frequency
    "qubit_length": 20,
    #### define spec slice experiment parameters
    "qubit_freq_start": 3803 - 20,
    "qubit_freq_stop": 3803 + 20,
    "SpecNumPoints": 101,  ### number of points
    'spec_reps': 1000,
    'relax_delay': 1000
}
#
# For Resonator Transmission
UpdateConfig = UpdateConfig_transmission | UpdateConfig_qubit
config = BaseConfig | UpdateConfig ### note that UpdateConfig will overwrite elements in BaseConfig
# #
# Instance_trans = Transmission(path="dataTestTransmission", cfg=config,soc=soc,soccfg=soccfg, outerFolder = outerFolder)
# data_trans = Transmission.acquire(Instance_trans)
# Transmission.display(Instance_trans, data_trans, plotDisp=True)
# Transmission.save_data(Instance_trans, data_trans)
# # # # # # #
# ######For Qubit Spec Experiment
# config["read_pulse_freq"] = Instance_trans.peakFreq ### Update the transmission frequency to be the peak
# print("Cavity freq IF [MHz] = ", Instance_trans.peakFreq)


# UpdateConfig = UpdateConfig_transmission | UpdateConfig_qubit
# config = BaseConfig | UpdateConfig ### note that UpdateConfig will overwrite elements in BaseConfig
# Instance_specSlice = SpecSlice(path="dataTestSpecSlice", cfg=config,soc=soc,soccfg=soccfg, outerFolder = outerFolder)
# data_specSlice= SpecSlice.acquire(Instance_specSlice)
# SpecSlice.display(Instance_specSlice, data_specSlice, plotDisp=True)
# SpecSlice.save_data(Instance_specSlice, data_specSlice)
# SpecSlice.save_config(Instance_specSlice)

# #######################################################################################################################
# ########################################################################################################################
# Amplitude Rabi ###
config["qubit_pulse_style"]= "arb"
config["sigma"] = 0.40
config["qubit_gain_start"] = 0
config["qubit_gain_step"] = 1000
config["qubit_gain_expts"] = 10
config["AmpRabi_reps"] = 3000
config["relax_delay"] = 1000

# config["flat_top_length"] = 20
#
Instance_AmplitudeRabi = AmplitudeRabi(path="dataTestAmplitudeRabi", cfg=config,soc=soc,soccfg=soccfg, outerFolder = outerFolder)
data_AmplitudeRabi = AmplitudeRabi.acquire(Instance_AmplitudeRabi)
AmplitudeRabi.display(Instance_AmplitudeRabi, data_AmplitudeRabi, plotDisp=True)
AmplitudeRabi.save_data(Instance_AmplitudeRabi, data_AmplitudeRabi)
AmplitudeRabi.save_config(Instance_AmplitudeRabi)
#
# ######################################################################################################################
# ######################################################################################################################
#######Rabi Blob Experiment ###
# UpdateConfig = {
#     ###### cavity
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 20, # us
#     "read_pulse_gain": 6000, # [DAC units]
#     "read_pulse_freq": 7214.95,
#     ##### spec parameters for finding the qubit frequency
#     "qubit_freq_start": 3795 - 5,
#     "qubit_freq_stop":  3795 + 5,
#     "RabiNumPoints": 31,  ### number of points
#     "qubit_pulse_style": "arb",
#     "sigma": 0.20,  ### units us, define a 20ns sigma pluse is 4 x sigma
#     # "flat_top_length": 0.3, ### in us
#     "relax_delay": 1500,  ### turned into us inside the run function
#     ##### amplitude rabi parameters
#     "qubit_gain_start": 1000,
#     "qubit_gain_step": 500, ### stepping amount of the qubit gain      the max gain for RFSoC is 30000
#     "qubit_gain_expts": 15, ### number of steps
#     "AmpRabi_reps": 1000,  # number of averages for the experiment
# }
# config = BaseConfig | UpdateConfig
#
# Instance_AmplitudeRabi_Blob = AmplitudeRabi_Blob(path="dataTestRabiAmpBlob", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg, progress=True)
# data_AmplitudeRabi_Blob = AmplitudeRabi_Blob.acquire(Instance_AmplitudeRabi_Blob)
# AmplitudeRabi_Blob.save_data(Instance_AmplitudeRabi_Blob, data_AmplitudeRabi_Blob)
# AmplitudeRabi_Blob.save_config(Instance_AmplitudeRabi_Blob)

######################################################################################################################
# ########################################################################################################################
# # # # # T1 Measurement ###
# # # #
# trials = [1, 2, 3, 4, 5]
# # #
# # trials = [1]
# #
# for trial in trials:
#     print(trial)
#
#     UpdateConfig = {
#         ###### cavity
#         "read_pulse_style": "const", # --Fixed
#         "read_length": 20, # us
#         "read_pulse_gain": 1200, # [DAC units]
#         "read_pulse_freq": 7200.185 - 0.035, # [MHz] actual frequency is this number + "cavity_LO"
#         ##### spec parameters for finding the qubit frequency
#         "qubit_freq": 3907.486,
#         "qubit_gain": 27200,
#         "sigma": 0.15,  ### units us, define a 20ns sigma
#         "qubit_pulse_style": "arb", #### arb means gaussian here
#         "relax_delay": 3000,  ### turned into us inside the run function
#         ##### T1 parameters
#         "start": 0, ### us
#         "step": 50, ### us
#         "expts": 41, ### number of experiments
#         "reps": 3000, ### number of averages on each experiment
#     }
#     config = BaseConfig | UpdateConfig
#
#     Instance_T1Experiment = T1Experiment(path="dataTestT1Experiment", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg,  progress=True)
#     data_T1Experiment = T1Experiment.acquire(Instance_T1Experiment)
#     T1Experiment.display(Instance_T1Experiment, data_T1Experiment, plotDisp=True)
#     T1Experiment.save_data(Instance_T1Experiment, data_T1Experiment)
#     T1Experiment.save_config(Instance_T1Experiment)


# #####################################################################################################################
# ## T2 Measurement ###
# UpdateConfig = {
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 20, # us
#     "read_pulse_gain": 1200, # [DAC units]
#     "read_pulse_freq": 7200.15, # [MHz] actual frequency is this number + "cavity_LO"
#     ##### spec parameters for finding the qubit frequency
#     "qubit_freq": 3907.48 + 0.5,
#     "qubit_gain": 11000,#30000
#     # "pi2_qubit_gain": 10000,
#     "sigma": 0.20,  ### units us, define a 20ns sigma
#     "qubit_pulse_style": "arb", #### arb means gaussain here
#     # "flat_top_length": 0.080,
#     "relax_delay": 2000,  ### turned into us inside the run function
#     ##### T2 ramsey parameters
#     "start": 0.00, ### us
#     "step": 0.25, ### us
#     "expts": 150, ### number of experiemnts 800
#     "reps": 2000, ### number of averages on each experiment 5000++6
# }
# config = BaseConfig | UpdateConfig
#
# Instance_T2Experiment = T2Experiment(path="dataTestT2RExperiment", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
# data_T2Experiment = T2Experiment.acquire(Instance_T2Experiment)
# T2Experiment.save_data(Instance_T2Experiment, data_T2Experiment)
# T2Experiment.save_config(Instance_T2Experiment)
# T2Experiment.display(Instance_T2Experiment, data_T2Experiment, plotDisp=True)
# #
# ########################################################################################################################
# # ### T2 echo measurement ###
# UpdateConfig = {
#     ###### cavity
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 20, # us
#     "read_pulse_gain": 250, # [DAC units]
#     "read_pulse_freq": 7600.46, # [MHz] actual frequency is this number + "cavity_LO"
#     ##### spec parameters for finding the qubit frequency
#     "qubit_freq": 5023.5,
#     "pi_qubit_gain": 10000,
#     "pi2_qubit_gain": 5000,
#     "sigma": 0.05,  ### units us, define a 20ns sigma
#     "qubit_pulse_style": "arb", #### arb means gaussain here
#     "relax_delay": 1000,  ### turned into us inside the run function
#     ##### T1 parameters
#     "start": 0, ### us
#     "step": 0.05, ### us
#     "expts": 101, ### number of experiemnts
#     "reps": 2000, ### number of averages on each experiment
# }
# config = BaseConfig | UpdateConfig
#
# Instance_T2EchoExperiment = T2EchoExperiment(path="dataTestT2EchoExperiment", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg,  progress=True)
# data_T2EchoExperiment = T2EchoExperiment.acquire(Instance_T2EchoExperiment)
# T2EchoExperiment.display(Instance_T2EchoExperiment, data_T2EchoExperiment, plotDisp=True)
# T2EchoExperiment.save_data(Instance_T2EchoExperiment, data_T2EchoExperiment)
# T2EchoExperiment.save_config(Instance_T2EchoExperiment)

# ########################################################################################################################
# # ## Basic Single Shot Experiment ###
# UpdateConfig = {
#     ###### cavity
#     # "reps": 3000,  # this will used for all experiments below unless otherwise changed in between trials
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 20, # [Clock ticks]
#     "read_pulse_gain": 1200, # [DAC units]
#     "read_pulse_freq":  7200.185 - 0.035, # [MHz]
#     ##### qubit spec parameters
#     "qubit_pulse_style": "arb",
#     "qubit_gain": 25000,
#     # "qubit_length": 10,  ###us, this is used if pulse style is const
#     "sigma": 0.15,  ### units us, define a 20ns sigma
#     "qubit_freq": 3907.5,
#     "relax_delay": 2500,  ### turned into us inside the run function
#     #### define shots
#     "shots": 2000, ### this gets turned into "reps"
# }
# config = BaseConfig | UpdateConfig
#
# Instance_SingleShotProgram = SingleShotProgram(path="dataTestSingleShotProgram", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
# data_SingleShot = SingleShotProgram.acquire(Instance_SingleShotProgram)
# SingleShotProgram.display(Instance_SingleShotProgram, data_SingleShot, plotDisp=True, save_fig=True)
# SingleShotProgram.save_data(Instance_SingleShotProgram, data_SingleShot)
# SingleShotProgram.save_config(Instance_SingleShotProgram)

# ######################
# ####################################### code for running  2D single shot fidelity optimization
# UpdateConfig = {
#     ##### set yoko
#     # "yokoVoltage": -7.2,
#     #### define basic parameters
#     ###### cavity
#     "reps": 2000,  # this will used for all experiements below unless otherwise changed in between trials
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 20, # [Clock ticks]
#     "read_pulse_gain": 400, # [DAC units]
#     "read_pulse_freq": 7418.458, # [MHz]
#     ##### qubit spec parameters
#     "qubit_pulse_style": "arb",
#     "qubit_gain": 25000,
#     # "qubit_length": 10,  ###us, this is used if pulse style is const
#     "sigma": 0.150,  ### units us, define a 20ns sigma
#     "qubit_freq": 3907.5,
#     "relax_delay": 2500,  ### turned into us inside the run function
#     #### define shots
#     "shots": 1000, ### this gets turned into "reps"
#     #### define the loop parameters
#     "x_var": "read_pulse_freq",
#     "x_start": 7200.185 - 0.2,
#     "x_stop": 7200.185 + 0.2,
#     "x_num": 21,
#
#     "y_var": "read_pulse_gain",
#     "y_start": 1200,
#     "y_stop": 1500,
#     "y_num": 4,
# }
# config = BaseConfig | UpdateConfig
#
# # yoko1.SetVoltage(config["yokoVoltage"])
#
# Instance_SingleShot_2Dsweep = SingleShot_2Dsweep(path="dataTestSingleShot_2Dsweep", outerFolder=outerFolder, cfg=config,
#                                                soc=soc, soccfg=soccfg)
# data_SingleShot_2Dsweep = SingleShot_2Dsweep.acquire(Instance_SingleShot_2Dsweep)
# SingleShot_2Dsweep.save_data(Instance_SingleShot_2Dsweep, data_SingleShot_2Dsweep)
# SingleShot_2Dsweep.save_config(Instance_SingleShot_2Dsweep)

#####################################################################################################################

print('end time: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
plt.show()
