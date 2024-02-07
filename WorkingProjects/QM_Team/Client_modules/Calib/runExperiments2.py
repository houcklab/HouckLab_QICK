#### import packages
import os
path = os.getcwd()
os.add_dll_directory(r'C:\Users\my\Documents\GitHub\HouckLab_QICK\WorkingProjects\QM_Team\Client_modules')
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
outerFolder = "Z:\\t1Team\\Data\\2024_01_23_CoolDown\\2024_02_07_LowTc_Qubit_RecoolDown\\"

###qubitAtten = attenuator(27797, attenuation_int= 10, print_int = False)

print('starting time: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))

soc, soccfg = makeProxy()

########################################################################################################################
########################################################################################################################
########################################################################################################################
#### Experiments #####

# Transmission versus Power ###
# UpdateConfig = {
#     ##### change gain instead option
#     "trans_gain_start": 6000,
#     "trans_gain_stop": 25000,
#     "trans_gain_num": 13,
#     ###### cavity
#     "trans_reps": 8000,  # this will used for all experiments below unless otherwise changed in between trials
#     "read_pulse_style": "const",  # --Fixed
#     "readout_length": 40,  # [us]
#     # "read_pulse_gain": 10000,  # [DAC units]
#     "trans_freq_start": 7523.2 - 1,  # [MHz] actual frequency is this number + "cavity_LO"
#     "trans_freq_stop": 7523.2 + 1,  # [MHz] actual frequency is this number + "cavity_LO"
#     "TransNumPoints": 201,  ### number of points in the transmission frequecny
#     "relax_delay": 2,
# }
# config = BaseConfig | UpdateConfig
#
# Instance_TransVsGain = TransVsGain(path="dataTestTransVsGain", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
# data_TransVsGain = TransVsGain.acquire(Instance_TransVsGain)
# TransVsGain.save_data(Instance_TransVsGain, data_TransVsGain)
# TransVsGain.save_config(Instance_TransVsGain)
#
########################################################################################################################
#######################################################################################################################
###Configure for Transmission Experiment ###
UpdateConfig_transmission={
    "reps": 4000,  # this will be used for all experiments below unless otherwise changed in between trials
    "read_pulse_style": "const", # --Fixed
    "readout_length": 20, # us
    "read_pulse_gain": 5000, # [DAC units]
    "read_pulse_freq": 7523.3, # [MHz] actual frequency is this number + "cavity_LO"
    "nqz": 2,  #### refers to cavity
    ##### define transmission experiment parameters
    "TransSpan": 1, ### MHz, span will be center+/- this parameter
    "TransNumPoints": 101, ### number of points in the transmission frequecny
}
#
# ## Configure for qubit experiment ###
UpdateConfig_qubit = {
    "qubit_pulse_style": "const",
    "qubit_gain": 200,
    "qubit_freq": 4703,
    "qubit_length": 40,
    #### define spec slice experiment parameters
    "qubit_freq_start": 4680,
    "qubit_freq_stop": 4720,
    "SpecNumPoints": 101,  ### number of points
    'spec_reps': 20000,
}
#### For Resonator Transmission
UpdateConfig = UpdateConfig_transmission | UpdateConfig_qubit
config = BaseConfig | UpdateConfig ### note that UpdateConfig will overwrite elements in BaseConfig

# Instance_trans = Transmission(path="dataTestTransmission", cfg=config,soc=soc,soccfg=soccfg, outerFolder = outerFolder)
# data_trans= Transmission.acquire(Instance_trans)
# Transmission.display(Instance_trans, data_trans, plotDisp=True)
# Transmission.save_data(Instance_trans, data_trans)
# #
# For Qubit Spec Experiment
# config["read_pulse_freq"] = Instance_trans.peakFreq ### Update the transmission frequency to be the peak
# print("Cavity freq IF [MHz] = ", Instance_trans.peakFreq)


# UpdateConfig = UpdateConfig_transmission | UpdateConfig_qubit
# config = BaseConfig | UpdateConfig ### note that UpdateConfig will overwrite elements in BaseConfig
# Instance_specSlice = SpecSlice(path="dataTestSpecSlice", cfg=config,soc=soc,soccfg=soccfg, outerFolder = outerFolder)
# data_specSlice= SpecSlice.acquire(Instance_specSlice)
# SpecSlice.display(Instance_specSlice, data_specSlice, plotDisp=True)
# SpecSlice.save_data(Instance_specSlice, data_specSlice)
# SpecSlice.save_config(Instance_specSlice)

########################################################################################################################
########################################################################################################################
# ## Amplitude Rabi ###
# config["qubit_pulse_style"]= "arb"
# config["sigma"] = 0.1
# config["qubit_gain_start"] = 0
# config["qubit_gain_step"] = 10
# config["qubit_gain_expts"] = 29
# config["AmpRabi_reps"] = 4000

#config["flat_top_length"] = 20

# Instance_AmplitudeRabi = AmplitudeRabi(path="dataTestAmplitudeRabi", cfg=config,soc=soc,soccfg=soccfg, outerFolder = outerFolder)
# data_AmplitudeRabi = AmplitudeRabi.acquire(Instance_AmplitudeRabi)
# AmplitudeRabi.display(Instance_AmplitudeRabi, data_AmplitudeRabi, plotDisp=True)
#AmplitudeRabi.save_data(Instance_AmplitudeRabi, data_AmplitudeRabi)
#AmplitudeRabi.save_config(Instance_AmplitudeRabi)

#######################################################################################################################
########################################################################################################################
###########Rabi Blob Experiment ###
UpdateConfig = {
    ###### cavity
    "read_pulse_style": "const", # --Fixed
    "read_length": 20, # us
    "read_pulse_gain": 5000, # [DAC units]
    "read_pulse_freq": 7523.3,
    ##### spec parameters for finding the qubit frequency
    "qubit_freq_start": 4707,
    "qubit_freq_stop":  4709,
    "RabiNumPoints": 11,  ### number of points
    "qubit_pulse_style": "arb",
    "sigma": 0.20,  ### units us, define a 20ns sigma
    # "flat_top_length": 0.3, ### in us
    "relax_delay": 200,  ### turned into us inside the run function
    ##### amplitude rabi parameters
    "qubit_gain_start": 000,
    "qubit_gain_step": 1000, ### stepping amount of the qubit gain
    "qubit_gain_expts": 25, ### number of steps
    "AmpRabi_reps": 4000,  # number of averages for the experiment
}
config = BaseConfig | UpdateConfig

# Instance_AmplitudeRabi_Blob = AmplitudeRabi_Blob(path="dataTestRabiAmpBlob", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg, progress=True)
# data_AmplitudeRabi_Blob = AmplitudeRabi_Blob.acquire(Instance_AmplitudeRabi_Blob)
# AmplitudeRabi_Blob.save_data(Instance_AmplitudeRabi_Blob, data_AmplitudeRabi_Blob)
# AmplitudeRabi_Blob.save_config(Instance_AmplitudeRabi_Blob)

#######################################################################################################################
########################################################################################################################
## T1 Measurement ###
UpdateConfig = {
    ###### cavity
    "read_pulse_style": "const", # --Fixed
    "read_length": 10, # us
    "read_pulse_gain": 5000, # [DAC units]
    "read_pulse_freq": 7523.3, # [MHz] actual frequency is this number + "cavity_LO"
    ##### spec parameters for finding the qubit frequency
    "qubit_freq": 4708,
    "qubit_gain": 25000,
    "sigma": 0.10,  ### units us, define a 20ns sigma
    "qubit_pulse_style": "arb", #### arb means gaussian here
    "relax_delay": 1000,  ### turned into us inside the run function
    ##### T1 parameters
    "start": 0, ### us
    "step": 50, ### us
    "expts": 31, ### number of experiments
    "reps": 10000, ### number of averages on each experiment
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
#     "read_length": 10, # us
#     "read_pulse_gain": 2500, # [DAC units]
#     "read_pulse_freq": 7600.82, # [MHz] actual frequency is this number + "cavity_LO"
#     ##### spec parameters for finding the qubit frequency
#     "qubit_freq": 5056 - 0.05,
#     "qubit_gain": 3850,
#     # "pi2_qubit_gain": 10000,
#     "sigma": 0.10,  ### units us, define a 20ns sigma
#     "qubit_pulse_style": "arb", #### arb means gaussain here
#     # "flat_top_length": 0.080,
#     "relax_delay": 1000,  ### turned into us inside the run function
#     ##### T2 ramsey parameters
#     "start": 0.00, ### us
#     "step": 0.5, ### us
#     "expts": 301, ### number of experiemnts
#     "reps": 3000, ### number of averages on each experiment
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
#     "read_length": 10, # [Clock ticks]
#     "read_pulse_gain": 2500, # [DAC units]
#     "read_pulse_freq": 7600.82, # [MHz]
#     ##### qubit spec parameters
#     "qubit_pulse_style": "arb",
#     "qubit_gain": 7700,
#     # "qubit_length": 10,  ###us, this is used if pulse style is const
#     "sigma": 0.100,  ### units us, define a 20ns sigma
#     "qubit_freq": 5056,
#     "relax_delay": 1000,  ### turned into us inside the run function
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
