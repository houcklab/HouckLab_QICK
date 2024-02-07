#### import packages
import os
path = os.getcwd()
# os.add_dll_directory(os.path.dirname(path)+'\\PythonDrivers')
os.add_dll_directory(r'C:\Users\newforce\Documents\GitHub\HouckLab_QICK\MasterProject\Client_modules')
from WorkingProjects.QM_Team.Client_modules.Calib.initialize import *
from WorkingProjects.QM_Team.Client_modules.Experiments.mTransmission_SaraTest import Transmission
# from WorkingProjects.QM_Team.Client_modules.Experiments.mTransmission import Transmission
from WorkingProjects.QM_Team.Client_modules.Experiments.mTransVsGain import TransVsGain
from WorkingProjects.QM_Team.Client_modules.Experiments.mSpecSlice_SaraTest import SpecSlice
from WorkingProjects.QM_Team.Client_modules.Experiments.mAmplitudeRabi import AmplitudeRabi
from WorkingProjects.QM_Team.Client_modules.Experiments.mAmplitudeRabi_Blob import AmplitudeRabi_Blob
from WorkingProjects.QM_Team.Client_modules.Experiments.mT1Experiment import T1Experiment
from WorkingProjects.QM_Team.Client_modules.Experiments.mT2Experiment import T2Experiment
from WorkingProjects.QM_Team.Client_modules.Experiments.mSingleShotProgram import SingleShotProgram

from matplotlib import pyplot as plt
import matplotlib
matplotlib.use('TkAgg')
import datetime

#### define the saving path
outerFolder = "Z:\\t1Team\\Data\\2023-11-30_cooldown\\TATPR6_StarCryo_CanD\\7p4_65\\"

###qubitAtten = attenuator(27797, attenuation_int= 10, print_int = False)

print('starting time: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))

soc, soccfg = makeProxy()

########################################################################################################################
########################################################################################################################
########################################################################################################################
#### Experiments #####

### Transmission versus Power ###
# UpdateConfig = {
#     ##### change gain instead option
#     "trans_gain_start": 0,
#     "trans_gain_stop": 10000,
#     "trans_gain_num": 24,
#     ###### cavity
#     "trans_reps": 6000,  # this will used for all experiments below unless otherwise changed in between trials
#     "read_pulse_style": "const",  # --Fixed
#     "readout_length": 40,  # [us]
#     # "read_pulse_gain": 10000,  # [DAC units]
#     "trans_freq_start": 7499.99 - 1,  # [MHz] actual frequency is this number + "cavity_LO"
#     "trans_freq_stop": 7499.99 + 1,  # [MHz] actual frequency is this number + "cavity_LO"
#     "TransNumPoints": 201,  ### number of points in the transmission frequecny
#     "relax_delay": 2,
# }
# config = BaseConfig | UpdateConfig
#
# Instance_TransVsGain = TransVsGain(path="dataTestTransVsGain", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
# data_TransVsGain = TransVsGain.acquire(Instance_TransVsGain)
# TransVsGain.save_data(Instance_TransVsGain, data_TransVsGain)
# TransVsGain.save_config(Instance_TransVsGain)

########################################################################################################################
#######################################################################################################################
# # # Configure for Transmission Experiment ###
# UpdateConfig_transmission={
#     "reps": 5000,  # this will be used for all experiments below unless otherwise changed in between trials
#     "read_pulse_style": "const", # --Fixed
#     "readout_length": 20, # us
#     "read_pulse_gain": 2000, # [DAC units]
#     "read_pulse_freq": 7391.8, # [MHz] actual frequency is this number + "cavity_LO"
#     "nqz": 2,  #### refers to cavity
#     ##### define transmission experiment parameters
#     "TransSpan": 1, ### MHz, span will be center+/- this parameter
#     "TransNumPoints": 101, ### number of points in the transmission frequecny
# }
#
# ## Configure for qubit experiment ###
# UpdateConfig_qubit = {
#     "qubit_pulse_style": "const",
#     "qubit_gain": 8000,
#     "qubit_freq": 5480,
#     "qubit_length": 20,
#     #### define spec slice experiment parameters
#     "qubit_freq_start": 5480 - 40,
#     "qubit_freq_stop": 5480 + 40,
#     "SpecNumPoints": 201,  ### number of points
#     'spec_reps': 5000,
# }
#
# UpdateConfig = UpdateConfig_transmission | UpdateConfig_qubit
# config = BaseConfig | UpdateConfig ### note that UpdateConfig will overwrite elements in BaseConfig

# ## For Resonator Transmission ###
# Instance_trans = Transmission(path="dataTestTransmission", cfg=config,soc=soc,soccfg=soccfg, outerFolder = outerFolder)
# data_trans= Transmission.acquire(Instance_trans)
# Transmission.display(Instance_trans, data_trans, plotDisp=True)
# Transmission.save_data(Instance_trans, data_trans)
#
# config["read_pulse_freq"] = Instance_trans.peakFreq ### Update the transmission frequency to be the peak
# print("Cavity freq IF [MHz] = ", Instance_trans.peakFreq)

### For Qubit Spec Experiment ###
# Instance_specSlice = SpecSlice(path="dataTestSpecSlice", cfg=config,soc=soc,soccfg=soccfg, outerFolder = outerFolder)
# data_specSlice= SpecSlice.acquire(Instance_specSlice)
# SpecSlice.display(Instance_specSlice, data_specSlice, plotDisp=True)
# SpecSlice.save_data(Instance_specSlice, data_specSlice)
# SpecSlice.save_config(Instance_specSlice)

########################################################################################################################
########################################################################################################################
# ## Amplitude Rabi ###
# config["qubit_pulse_style"]= "flat_top"
# config["sigma"] = 0.5
# config["flat_top_length"] = 20
#
# Instance_AmplitudeRabi = AmplitudeRabi(path="dataTestAmplitudeRabi", cfg=config,soc=soc,soccfg=soccfg, outerFolder = outerFolder)
# data_AmplitudeRabi = AmplitudeRabi.acquire(Instance_AmplitudeRabi)
# AmplitudeRabi.display(Instance_AmplitudeRabi, data_AmplitudeRabi, plotDisp=True)
# AmplitudeRabi.save_data(Instance_AmplitudeRabi, data_AmplitudeRabi)
# AmplitudeRabi.save_config(Instance_AmplitudeRabi)

#######################################################################################################################
########################################################################################################################
###########Rabi Blob Experiment ###
# UpdateConfig = {
#     ###### cavity
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 20, # us
#     "read_pulse_gain": 2000, # [DAC units]
#     "read_pulse_freq": 7391.8,
#     ##### spec parameters for finding the qubit frequency
#     "qubit_freq_start": 5485 - 2,
#     "qubit_freq_stop":  5485 + 2,
#     "RabiNumPoints": 11,  ### number of points
#     "qubit_pulse_style": "arb",
#     "sigma": 0.300,  ### units us, define a 20ns sigma
#     # "flat_top_length": 0.3, ### in us
#     "relax_delay": 800,  ### turned into us inside the run function
#     ##### amplitude rabi parameters
#     "qubit_gain_start": 0,
#     "qubit_gain_step": 1000, ### stepping amount of the qubit gain
#     "qubit_gain_expts": 26, ### number of steps
#     "AmpRabi_reps": 3000,  # number of averages for the experiment
# }
# config = BaseConfig | UpdateConfig
#
# Instance_AmplitudeRabi_Blob = AmplitudeRabi_Blob(path="dataTestRabiAmpBlob", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg, progress=True)
# data_AmplitudeRabi_Blob = AmplitudeRabi_Blob.acquire(Instance_AmplitudeRabi_Blob)
# AmplitudeRabi_Blob.save_data(Instance_AmplitudeRabi_Blob, data_AmplitudeRabi_Blob)
# AmplitudeRabi_Blob.save_config(Instance_AmplitudeRabi_Blob)
#
# #######################################################################################################################
########################################################################################################################
### T1 Measurement ###
UpdateConfig = {
    ###### cavity
"read_pulse_style": "const",  # --Fixed
"read_length": 20,  # us
"read_pulse_gain": 2000,  # [DAC units]
"read_pulse_freq": 7391.8,  # [MHz] actual frequency is this number + "cavity_LO"
##### spec parameters for finding the qubit frequency
"qubit_freq": 5485,
"qubit_gain": 20000,
"sigma": 0.30,  ### units us, define a 20ns sigma
"qubit_pulse_style": "arb",  #### arb means gaussian here
"relax_delay": 1000,  ### turned into us inside the run function
##### T1 parameters
"start": 0,  ### us
"step": 20,  ### us
"expts": 51,  ### number of experiments
"reps": 5000,  ### number of averages on each experiment
}
config = BaseConfig | UpdateConfig

Instance_T1Experiment = T1Experiment(path="dataTestT1Experiment", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg,  progress=True)
data_T1Experiment = T1Experiment.acquire(Instance_T1Experiment)
T1Experiment.display(Instance_T1Experiment, data_T1Experiment, plotDisp=True)
T1Experiment.save_data(Instance_T1Experiment, data_T1Experiment)
T1Experiment.save_config(Instance_T1Experiment)

########################################################################################################################
########################################################################################################################
### T2 Measurement ###
# UpdateConfig = {
#     ##### define flux point
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 20, # us
#     "read_pulse_gain": 5000, # [DAC units]
#     "read_pulse_freq": 7622.81, # [MHz] actual frequency is this number + "cavity_LO"
#     ##### spec parameters for finding the qubit frequency
#     "qubit_freq": 5312 - 0.02,
#     "qubit_gain": 7550,
#     # "pi2_qubit_gain": 10000,
#     "sigma": 0.30,  ### units us, define a 20ns sigma
#     "qubit_pulse_style": "arb", #### arb means gaussain here
#     # "flat_top_length": 0.080,
#     "relax_delay": 600,  ### turned into us inside the run function
#     ##### T2 ramsey parameters
#     "start": 0.00, ### us
#     "step": 1, ### us
#     "expts": 201, ### number of experiemnts
#     "reps": 1600, ### number of averages on each experiment
# }
# config = BaseConfig | UpdateConfig
#
# Instance_T2Experiment = T2Experiment(path="dataTestT2RExperiment", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
# data_T2Experiment = T2Experiment.acquire(Instance_T2Experiment)
# T2Experiment.display(Instance_T2Experiment, data_T2Experiment, plotDisp=True)
# T2Experiment.save_data(Instance_T2Experiment, data_T2Experiment)
# T2Experiment.save_config(Instance_T2Experiment)

########################################################################################################################
########################################################################################################################
### Basic Single Shot Experiment ###
# UpdateConfig = {
#     ###### cavity
#     # "reps": 3000,  # this will used for all experiments below unless otherwise changed in between trials
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 40, # [Clock ticks]
#     "read_pulse_gain": 5000, # [DAC units]
#     "read_pulse_freq": 7622.81, # [MHz]
#     ##### qubit spec parameters
#     "qubit_pulse_style": "arb",
#     "qubit_gain": 7550,
#     # "qubit_length": 10,  ###us, this is used if pulse style is const
#     "sigma": 0.30,  ### units us, define a 20ns sigma
#     "qubit_freq": 5312,
#     "relax_delay": 200,  ### turned into us inside the run function
#     #### define shots
#     "shots": 10000, ### this gets turned into "reps"
# }
# config = BaseConfig | UpdateConfig
#
# Instance_SingleShotProgram = SingleShotProgram(path="dataTestSingleShotProgram", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
# data_SingleShot = SingleShotProgram.acquire(Instance_SingleShotProgram)
# SingleShotProgram.display(Instance_SingleShotProgram, data_SingleShot, plotDisp=True, save_fig=True)
# SingleShotProgram.save_data(Instance_SingleShotProgram, data_SingleShot)
# SingleShotProgram.save_config(Instance_SingleShotProgram)
#
#####################################################################################################################

print('end time: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
plt.show()
