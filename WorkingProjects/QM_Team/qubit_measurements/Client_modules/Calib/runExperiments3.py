### Qubit Measurement Code - Last used 8-11-2024 ###

### Import Packages ###
import os
import datetime
import matplotlib
from matplotlib import pyplot as plt
matplotlib.use('TkAgg')

path = os.getcwd()
os.add_dll_directory(r'C:\Users\my\Documents\GitHub\HouckLab_QICK\WorkingProjects\QM_Team\qubit_measurements\Client_modules')

# Import Experiments
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Calib.initialize import *
# from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mTransmission_SaraTest import Transmission
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

print('starting time: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
soc, soccfg = makeProxy()

### Qubits ###
qubit_7p2190 =
Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 7219.0, 'Gain': 2300},
          'Qubit': {'Frequency': 1831, 'Gain': 30000},
          'Pulse_FF': [0, 0, 0, 0]},

    }

# Save path
cooldownFolder = "Z:\\t1Team\\Data\\2024-08-09_cooldown\\TATQ01-Si_01\\"
deviceFolder = "7p2190"
outerFolder = cooldownFolder + deviceFolder + "\\"

### Run an experiment ###

## Possible experiments: 'transmission_vs_power' , 'rabi_blob' , 'T1', 'T2R' , 'T2E' , 'single_shot' , ' 2D_single_shot'

experiment = 'rabi_blob'

### Experiments #####

###Transmission versus Power ###
if experiment == 'transmission_vs_power':
    UpdateConfig = {
        ##### change gain instead option
        "trans_gain_start": 500,
        "trans_gain_stop": 5000,
        "trans_gain_num": 10,
        ###### cavity
        "trans_reps": 1000,  # this will used for all experiments below unless otherwise changed in between trials
        "read_pulse_style": "const",  # --Fixed
        "readout_length": 50,  # [us]
        # "read_pulse_gain": 10000,  # [DAC units]
        "trans_freq_start": 6846.65 - 0.5, #6735.456810631229 - 2,  # [MHz] actual frequency is this number + "cavity_LO" use span for +/- part
        "trans_freq_stop": 6846.65 + 0.5, #6735.456810631229 + 2,  # [MHz] actual frequency is this number + "cavity_LO"
        "TransNumPoints": 101,
        "relax_delay": 1, #5 times T1 -- this is the delay between each experiment
    }
    config = BaseConfig | UpdateConfig

    Instance_TransVsGain = TransVsGain(path="dataTestTransVsGain", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
    data_TransVsGain = TransVsGain.acquire(Instance_TransVsGain)
    TransVsGain.save_data(Instance_TransVsGain, data_TransVsGain)
    TransVsGain.save_config(Instance_TransVsGain)

# ######################################################################################################################
# ######################################################################################################################
###Configure for Transmission Experiment ###
UpdateConfig_transmission={
    "reps": 1000,  # this will be used for all experiments below unless otherwise changed in between trials
    "read_pulse_style": "const", # --Fixed
    "readout_length": 20, # us
    "read_pulse_gain": 3000, # [DAC units]
    "read_pulse_freq": 7219.0, #6735.456810631229, # #7194.787174129353, # [MHz] actual frequency is this number + "cavity_LO"
    "nqz": 2,  #### refers to cavity
    ##### define transmission experiment parameters
    "TransSpan": 1, ### MHz, span will be center+/- this parameter
    "TransNumPoints": 301, ### number of points in the transmission frequecny
}

# ## Configure for qubit experiment ###
UpdateConfig_qubit = {
    "qubit_pulse_style": "const",
    "qubit_gain": 5000,
    "qubit_freq": 4474.75,
    "qubit_length": 20,
    #### define spec slice experiment parameters
    "qubit_freq_start": 4474.75 - 1,
    "qubit_freq_stop": 4474.75 + 1,
    "SpecNumPoints": 401,  ### number of points
    'spec_reps': 1000,
}

##### For Resonator Transmission
# UpdateConfig = UpdateConfig_transmission | UpdateConfig_qubit
# config = BaseConfig | UpdateConfig ### note that UpdateConfig will overwrite elements in BaseConfig
#
# Instance_trans = Transmission(path="dataTestTransmission", cfg=config,soc=soc,soccfg=soccfg, outerFolder = outerFolder)
# data_trans = Transmission.acquire(Instance_trans)
# Transmission.display(Instance_trans, data_trans, plotDisp=True)
# Transmission.save_data(Instance_trans, data_trans)
# Instance_trans.save_config()
#
# config["read_pulse_freq"] = Instance_trans.peakFreq ### Update the transmission frequency to be the peak
# print("Cavity freq IF [MHz] = ", Instance_trans.peakFreq)

##### For Qubit Spec Experiment
# UpdateConfig = UpdateConfig_transmission | UpdateConfig_qubit
# config = BaseConfig | UpdateConfig ### note that UpdateConfig will overwrite elements in BaseConfig

# Instance_specSlice = SpecSlice(path="dataTestSpecSlice", cfg=config,soc=soc,soccfg=soccfg, outerFolder = outerFolder)
# data_specSlice= SpecSlice.acquire(Instance_specSlice)
# SpecSlice.display(Instance_specSlice, data_specSlice, plotDisp=True)
# SpecSlice.save_data(Instance_specSlice, data_specSlice)
# SpecSlice.save_config(Instance_specSlice)

# #######################################################################################################################
# ########################################################################################################################
#### Amplitude Rabi ###
# config["qubit_pulse_style"]= "arb"
# config["sigma"] = 0.2
# config["qubit_gain_start"] = 500
# config["qubit_gain_step"] = 2000
# config["qubit_gain_expts"] = 10
# config["AmpRabi_reps"] = 500
# config["relax_delay"] = 10000

# config["flat_top_length"] = 20
#
# Instance_AmplitudeRabi = AmplitudeRabi(path="dataTestAmplitudeRabi", cfg=config,soc=soc,soccfg=soccfg, outerFolder = outerFolder)
# data_AmplitudeRabi = AmplitudeRabi.acquire(Instance_AmplitudeRabi)
# AmplitudeRabi.display(Instance_AmplitudeRabi, data_AmplitudeRabi, plotDisp=True)
# AmplitudeRabi.save_data(Instance_AmplitudeRabi, data_AmplitudeRabi)
# AmplitudeRabi.save_config(Instance_AmplitudeRabi)

#######################################################################################################################
#######################################################################################################################
### Rabi Blob Experiment ###
UpdateConfig = {
    ## cavity parameters ##
    "read_pulse_style": "const",
    "read_length": 20,                      # resonator drive length [us]
    "read_pulse_gain": 3000,                # resonator drive power [DAC units]
    "read_pulse_freq": 7219.0,              # resonator frequency [MHz]
    ## qubit parameters ##
    "qubit_freq_start": 4475 - 2,           # first qubit freq point [MHz]
    "qubit_freq_stop": 4475 + 2,            # last qubit freq point [MHz]
    "RabiNumPoints": 5,                     # division of qubit freq range
    "qubit_pulse_style": "arb",             # arb: gaussian
    "sigma": 0.4,                           # 4 * sigma = pulse length [us]
    "flat_top_length": 3,                   # [us]
    "relax_delay": 6000,                    # time between experiments [us]
    ## amplitude rabi parameters ##
    "qubit_gain_start": 500,               # first qubit gain point [DAC]
    "qubit_gain_step": 2000,                # qubit gain step (max gain for RFSoC is 30000)
    "qubit_gain_expts": 10,                 # number of steps
    "AmpRabi_reps": 500,                    # number of averages
}

config = BaseConfig | UpdateConfig

Instance_AmplitudeRabi_Blob = AmplitudeRabi_Blob(path="dataTestRabiAmpBlob", outerFolder=outerFolder, cfg=config, soc=soc, soccfg=soccfg, progress=True)
data_AmplitudeRabi_Blob = AmplitudeRabi_Blob.acquire(Instance_AmplitudeRabi_Blob)
AmplitudeRabi_Blob.save_data(Instance_AmplitudeRabi_Blob, data_AmplitudeRabi_Blob)
AmplitudeRabi_Blob.save_config(Instance_AmplitudeRabi_Blob)

######################################################################################################################
# # ########################################################################################################################
# # # # # # T1 Measurement ###
# # # #
trials = 1000

# for trial in range(trials):
#     time.sleep(30)
#     print(trial)
#
#     UpdateConfig = {
#         ### Cavity Parameters ###
#         "read_pulse_style": "const",
#         "read_length": 20,             # resonator pulse length [us]
#         "read_pulse_gain": 6000,       # resonator drive [DAC units]
#         "read_pulse_freq": 7013.7,     # resonator frequency [MHz]
#         ### Qubit Parameters ###
#         "qubit_freq": 4102.35,         # qubit frequency [MHz]
#         "qubit_gain": 32000,           # qubit drive [DAC units]
#         "sigma": 0.4,                  # 4 * sigma = pulse length [us]
#         "qubit_pulse_style": "arb",    # arb: gaussian
#         "relax_delay": 20000,          # time between experiments [us]
#         ### T1 Parameters ###
#         "start": 0,                    # [us]
#         "step": 150,                   # [us]
#         "expts": 50,                   # step * expts = total measurement length
#         "reps": 500,                   # number of averages on each experiment
#     }
#     config = BaseConfig | UpdateConfig
#
#     Instance_T1Experiment = T1Experiment(path="dataTestT1Experiment", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg,  progress=True)
#     data_T1Experiment = T1Experiment.acquire(Instance_T1Experiment)
#     T1Experiment.display(Instance_T1Experiment, data_T1Experiment, plotDisp=False)
#     T1Experiment.save_data(Instance_T1Experiment, data_T1Experiment)
#     T1Experiment.save_config(Instance_T1Experiment)

#####################################################################################################################
#T2 Measurement ###
UpdateConfig = {
    "read_pulse_style": "const", # --Fixed
    "read_length": 20, # us
    "read_pulse_gain": 4000, # [DAC units]
    "read_pulse_freq": 6932.6, # [MHz] actual frequency is this number + "cavity_LO"
    ##### spec parameters for finding the qubit frequency
    "qubit_freq": 3924.72 - 0.1,
    "qubit_gain": 32000,
    "pi2_qubit_gain": 16000,
    "sigma": 0.40,  ### units us, define a 20ns sigma
    "qubit_pulse_style": "arb", #### arb means gaussain here
    # "flat_top_length": 0.080,
    "relax_delay": 3000,  ### turned into us inside the run function
    ##### T2 ramsey parameters
    "start": 0.00, ### us
    "step": 0.05, ### us
    "expts": 100, ### number of experiemnts 800
    "reps": 500, ### number of averages on each experiment 5000++6
}
# config = BaseConfig | UpdateConfig
#
# Instance_T2Experiment = T2Experiment(path="dataTestT2RExperiment", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
# data_T2Experiment = T2Experiment.acquire(Instance_T2Experiment)
# T2Experiment.save_data(Instance_T2Experiment, data_T2Experiment)
# T2Experiment.save_config(Instance_T2Experiment)
# T2Experiment.display(Instance_T2Experiment, data_T2Experiment, plotDisp=True)
#
# # ########################################################################################################################
### T2 echo measurement ###
# UpdateConfig = {
#     ###### cavity
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 10, # us
#     "read_pulse_gain": 1200, # [DAC units]
#     "read_pulse_freq": 7302.04, # [MHz] actual frequency is this number + "cavity_LO"
#     ##### spec parameters for finding the qubit frequency
#     "qubit_freq": 3627.57, #no need for detunning for echo
#     "pi_qubit_gain": 14000,
#     "pi2_qubit_gain": 5000,
#     "sigma": 0.2,  ### units us, define a 20ns sigma
#     "qubit_pulse_style": "arb", #### arb means gaussain here
#     "relax_delay": 4000,  ### turned into us inside the run function
#     ##### T1 parameters
#     "start": 0, ### us
#     "step": 5, ### us
#     "expts": 41, ### number of experiments
#     "reps": 1000, ### number of averages on each experiment
# }
# config = BaseConfig | UpdateConfig
#
# Instance_T2EchoExperiment = T2EchoExperiment(path="dataTestT2EchoExperiment", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg,  progress=True)
# data_T2EchoExperiment = T2EchoExperiment.acquire(Instance_T2EchoExperiment)
# T2EchoExperiment.display(Instance_T2EchoExperiment, data_T2EchoExperiment, plotDisp=True)
# T2EchoExperiment.save_data(Instance_T2EchoExperiment, data_T2EchoExperiment)
# T2EchoExperiment.save_config(Instance_T2EchoExperiment)

# ########################################################################################################################
## Basic Single Shot Experiment ###
UpdateConfig = {
    ###### cavity
    # "reps": 3000,  # this will used for all experiments below unless otherwise changed in between trials
    "read_pulse_style": "const", # --Fixed
    "read_length": 20, # [Clock ticks]
    "read_pulse_gain": 6000, # [DAC units]
    "read_pulse_freq": 7013.7, # [MHz]
    ##### qubit spec parameters
    "qubit_pulse_style": "arb",
    "qubit_gain": 32000,
    # "qubit_length": 10,  ###us, this is used if pulse style is const
    "sigma": 0.4,  ### units us, define a 20ns sigma
    "qubit_freq": 4102.35,
    "relax_delay": 20000,  ### turned into us inside the run function
    #### define shots
    "shots": 2000, ### this gets turned into "reps"
}
# config = BaseConfig | UpdateConfig
#
# Instance_SingleShotProgram = SingleShotProgram(path="dataTestSingleShotProgram", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
# data_SingleShot = SingleShotProgram.acquire(Instance_SingleShotProgram)
# SingleShotProgram.display(Instance_SingleShotProgram, data_SingleShot, plotDisp=True, save_fig=True)
# SingleShotProgram.save_data(Instance_SingleShotProgram, data_SingleShot)
# SingleShotProgram.save_config(Instance_SingleShotProgram)

####################################### code for running  2D single shot fidelity optimization
UpdateConfig = {
    "reps": 1000,  # this will used for all experiements below unless otherwise changed in between trials
    "read_pulse_style": "const", # --Fixed
    "read_length": 10, # [Clock ticks]
    "read_pulse_gain": 5000, # [DAC units]
    "read_pulse_freq": 6735.4, #7060.803322259137, # [MHz]
    ##### qubit spec parameters
    "qubit_pulse_style": "arb",
    "qubit_gain": 25000,
    # "qubit_length": 10,  ###us, this is used if pulse style is const
    "sigma": 0.2,  ### units us, define a 20ns sigma
    "qubit_freq": 3514.0,
    "relax_delay": 5000,  ### turned into us inside the run function
    #### define shots
    "shots": 1000, ### this gets turned into "reps"
    #### define the loop parameters
    "x_var": "read_pulse_freq",
    "x_start": 6735.2 - 0.5,
    "x_stop": 6735.2 + 0.5,
    "x_num": 4,

    "y_var": "read_pulse_gain",
    "y_start": 1000,
    "y_stop": 8000,
    "y_num": 6,
}
# config = BaseConfig | UpdateConfig
#
# Instance_SingleShot_2Dsweep = SingleShot_2Dsweep(path="dataTestSingleShot_2Dsweep", outerFolder=outerFolder, cfg=config,
#                                                soc=soc, soccfg=soccfg)
# data_SingleShot_2Dsweep = SingleShot_2Dsweep.acquire(Instance_SingleShot_2Dsweep)
# SingleShot_2Dsweep.save_data(Instance_SingleShot_2Dsweep, data_SingleShot_2Dsweep)
# SingleShot_2Dsweep.save_config(Instance_SingleShot_2Dsweep)

#####################################################################################################################

print('end time: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
plt.show()
