#### import packages
import os
path = os.getcwd()
os.add_dll_directory(os.path.dirname(path)+'\\PythonDrivers')
from Protomon.Client_modules.Calib.initialize import *
from Protomon.Client_modules.Helpers.hist_analysis import *
from Protomon.Client_modules.Helpers.MixedShots_analysis import *
from matplotlib import pyplot as plt

from Protomon.Client_modules.Experiments.mTransmission import Transmission
from Protomon.Client_modules.Experiments.mSpecSlice_ShashwatTest import SpecSlice
from Protomon.Client_modules.Experiments.mFluxDriftTest import FluxDriftTest
from Protomon.Client_modules.Experiments.mSpecVsFlux import SpecVsFlux
from Protomon.Client_modules.Experiments.mSingleShotProgram import SingleShotProgram
from Protomon.Client_modules.Experiments.mSingleShotPS import SingleShotPS
from Protomon.Client_modules.Experiments.mSingleShot_2Dsweep import SingleShot_2Dsweep
from Protomon.Client_modules.Experiments.mAmplitudeRabi_ShashwatTest import AmplitudeRabi
from Protomon.Client_modules.Experiments.mAmplitudeRabi_Blob_ShashwatTest import AmplitudeRabi_Blob
from Protomon.Client_modules.Experiments.mT1Experiment import T1Experiment
from Protomon.Client_modules.Experiments.mT2Experiment import T2Experiment
from Protomon.Client_modules.Experiments.mTransVsGain import TransVsGain
from Protomon.Client_modules.Experiments.mLoopback import Loopback
from Protomon.Client_modules.Experiments.mReadOpt_wSingleShot import ReadOpt_wSingleShot
from Protomon.Client_modules.Experiments.mGainReadOpt_wSingleShot import GainReadOpt_wSingleShot
from Protomon.Client_modules.Experiments.mPiOpt_wSingleShot import PiOpt_wSingleShot

#### define the saving path
outerFolder = "Z:\Shashwat\Protomon\FMV8_TD\\"

#################################### Running the actual experiments

# Only run this if no proxy already exists
soc, soccfg = makeProxy()
# print(soccfg)

plt.ioff()

# ###################################### code for running basic single shot exerpiment
# #
# # config = {'res_ch': 0, 'qubit_ch': 2, 'mixer_freq': 0.0, 'ro_chs': [0],
# #  'nqz': 1, 'qubit_nqz': 1, 'relax_delay': 20, 'res_phase': 0,
# #  'adc_trig_offset': 0.51, 'cavity_LO': 0, 'qubit_pulse_style': 'arb', 'qubit_gain': 1000,
# #  'qubit_freq': 2494.9, 'qubit_length': 50, 'qubit_relax_delay': 2000, 'qubit_freq_start': 2480,
# #  'qubit_freq_stop': 2518, 'SpecNumPoints': 101, 'spec_reps': 10, 'spec_rounds': 10, 'yokoVoltage': 0.11,
# #  'read_pulse_style': 'const', 'read_pulse_gain': 100, 'read_pulse_freq': 4729.1,
# #  'sigma': 0.08, 'qubit_gain_start': 0, 'qubit_gain_step': 750, 'qubit_gain_expts': 39, 'AmpRabi_reps': 10, 'AmpRabi_rounds': 5000, # 4000
# #  'yokoVoltageStart': .1, 'yokoVoltageStop': 0.25, 'yokoVoltageNumPoints': 41,
# #  'trans_freq_start': 4723, 'trans_freq_stop': 4733, 'TransNumPoints': 101, 'trans_reps': 2000, 'trans_rounds': 1,
# #  'qubit_freq_start_rabiBlob': 2494, 'qubit_freq_stop_rabiBlob': 2496, 'qubit_freq_expts_rabiBlob': 8,
# #  'qubit_gain_pi': 8000, 'shots':5000, 'read_length': 10, 'T1_reps': 10, 'T1_rounds': 5000}
#
#
# # # #### run the single shot experiment
#
# # Instance_SingleShotProgram = SingleShotProgram(path="dataTestSingleShotProgram", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
# # data_SingleShot = SingleShotProgram.acquire(Instance_SingleShotProgram)
# # SingleShotProgram.display(Instance_SingleShotProgram, data_SingleShot, plotDisp=False)
# # SingleShotProgram.save_data(Instance_SingleShotProgram, data_SingleShot)
# # SingleShotProgram.save_config(Instance_SingleShotProgram)
#
#
# ################################################################################################################
#
# # ### loop over a few read times to find fidelity as a function of read time
# # readArr = np.array([1,2,3,4,5,6,7,8,9,10,12,14,16])
# # # readArr = np.linspace(1, 40, 40)
# # fidArr = np.zeros(len(readArr))
# #
# # for i in range(len(readArr)):
# #     config['read_length'] = readArr[i]
# #     Instance_SingleShotProgram = SingleShotProgram(path="SingleShot_readTimeSweeps", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
# #     data_SingleShotProgram = SingleShotProgram.acquire(Instance_SingleShotProgram)
# #     SingleShotProgram.display(Instance_SingleShotProgram, data_SingleShotProgram, plotDisp=False)
# #     fidArr[i] = Instance_SingleShotProgram.fid
# #     plt.clf()
# #     print(i/len(readArr))
# #
# # plt.figure(101)
# # plt.plot(readArr, fidArr, 'o')
# # plt.xlabel('Read Length (us)')
# # plt.ylabel('Fidelity')
# # plt.show()
# # print("Debug point")
#
# # # Preliminary readout length can now be set:
# # config['read_length'] = 5
# # config['shots'] = 3000
# #
# # ### loop over a different read frequencies
# # freqDiffArr = np.linspace(-10.0,10.0, 21)
# # fidArr = np.zeros(len(freqDiffArr))
# #
# # for i in range(len(freqDiffArr)):
# #     config['read_pulse_freq'] = 4729.1 + freqDiffArr[i]
# #     Instance_SingleShotProgram = SingleShotProgram(path="SingleShot_readFreqSweeps", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
# #     data_SingleShotProgram = SingleShotProgram.acquire(Instance_SingleShotProgram)
# #     SingleShotProgram.display(Instance_SingleShotProgram, data_SingleShotProgram, plotDisp=False)
# #     fidArr[i] = Instance_SingleShotProgram.fid
# #     plt.clf()
# #     print(i/len(freqDiffArr))
# #
# # plt.figure(101)
# # plt.plot(freqDiffArr, fidArr, 'o')
# # plt.xlabel('Detunning (MHz)')
# # plt.ylabel('Fidelity')
# # plt.show()
# # print("Debug point")
#
# ########################################################################################################################
# ###################################### code for optimizing readout parameters
# config = {'res_ch': 0, 'qubit_ch': 2, 'mixer_freq': 0.0, 'ro_chs': [0],
#  'nqz': 1, 'qubit_nqz': 1, 'relax_delay': 20, 'res_phase': 0,
#  'adc_trig_offset': 0.51, 'cavity_LO': 0, 'qubit_pulse_style': 'arb', 'qubit_gain': 600,
#  'qubit_freq': 2494.9, 'qubit_length': 50, 'qubit_relax_delay': 2000, 'qubit_freq_start': 2493.5, ### TEMPORARILY RELAX DELAY VERY LOW FOR DRIFT
#  'qubit_freq_stop': 2497.5, 'SpecNumPoints': 23, 'spec_reps': 550, 'spec_rounds': 20, 'yokoVoltage': 0.11,
#  'read_pulse_style': 'const', 'read_pulse_gain': 100, 'read_pulse_freq': 4729.1, #4729.3?
#  'sigma': 0.08, 'qubit_gain_start': 0, 'qubit_gain_step': 640, 'qubit_gain_expts': np.int64(32000/640), 'AmpRabi_reps': 2000, 'AmpRabi_rounds': 25, # 4000
#  'yokoVoltageStart': .1, 'yokoVoltageStop': 0.25, 'yokoVoltageNumPoints': 41,
#  'trans_freq_start': 4726, 'trans_freq_stop': 4732, 'TransNumPoints': 51, 'trans_reps': 4000, 'trans_rounds': 1,
#  'qubit_freq_start_rabiBlob': 2494, 'qubit_freq_stop_rabiBlob': 2496, 'qubit_freq_expts_rabiBlob': 8,
#  'qubit_gain_pi': 8000, 'shots':1500, 'read_length': 5,
#  'trans_gain_start_readopt': 20, 'trans_gain_stop_readopt': 300, 'trans_gain_num_readopt': 21,
#  'trans_freq_start_readopt': 4729.1-10, 'trans_freq_stop_readopt': 4729.1+10, 'trans_freq_num_readopt': 21,
#  'qubit_gain_start_readopt': 7500, 'qubit_gain_stop_readopt': 8500, 'qubit_gain_num_readopt': 21,
#  'qubit_freq_start_readopt': 2494.9 - 10, 'qubit_freq_stop_readopt': 2494.9 + 10, 'qubit_freq_num_readopt': 11,
#  'T1_reps': 3000, 'T1_rounds': 25,  "T1_start": 0, "T1_step": 10, "T1_expts": 100,"pigain": 12000,
#  "drift_wait_step": 0.01,  ### (min) time of each waiting step
#  "drift_wait_num": 500,  ### number of steps to take
# "T2R_reps": 1, "T2R_rounds": 1, "T2R_start":0, "T2R_step": .01, "T2R_expts":50, "pi2gain": 5575,"T2R_phase_step": 8*360/100, #Degrees,
# ## What xanthe did: 8 fringes with 100 points
# }
# yoko1.SetVoltage(config["yokoVoltage"])
# Instance_trans = Transmission(path="dataTestTransmission", cfg=config,soc=soc,soccfg=soccfg, outerFolder = outerFolder)
# data_trans= Transmission.acquire(Instance_trans)
# Transmission.display(Instance_trans, data_trans, plotDisp=False)
# Transmission.save_data(Instance_trans, data_trans)
# ### update the transmission frequency to be the peak
# config["read_pulse_freq"] = Instance_trans.peakFreq
# print("new cavity freq =", config["read_pulse_freq"])
# # config["read_pulse_freq"] = 4729.581196581196
#
# # config['qubit_relax_delay'] = 20
# # Instance_specSlice = SpecSlice(path="dataTestSpecSlice", cfg=config,soc=soc,soccfg=soccfg, outerFolder = outerFolder)
# # data_specSlice= SpecSlice.acquire(Instance_specSlice)
# # SpecSlice.display(Instance_specSlice, data_specSlice, plotDisp=True)
# # SpecSlice.save_data(Instance_specSlice, data_specSlice)
# # ### update the transmission frequency to be the peak
# # config["qubit_freq"] = Instance_specSlice.peakFreq
# # print("new qubit freq =", config["qubit_freq"])
#
# # ##### Flux drift experiment
# # Instance_FluxDriftTest = FluxDriftTest(path="dataTestFluxDriftTest", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
# # data_FluxDriftTest = FluxDriftTest.acquire(Instance_FluxDriftTest, plotDisp=False, plotSave=True)
# # FluxDriftTest.save_data(Instance_FluxDriftTest, data_FluxDriftTest)
# # FluxDriftTest.save_config(Instance_FluxDriftTest)
#
# # config['qubit_relax_delay'] = 2000
# # Instance_AmplitudeRabi = AmplitudeRabi(path="dataTestAmplitudeRabi", cfg=config,soc=soc,soccfg=soccfg, outerFolder = outerFolder)
# # data_AmplitudeRabi = AmplitudeRabi.acquire(Instance_AmplitudeRabi)
# # AmplitudeRabi.display(Instance_AmplitudeRabi, data_AmplitudeRabi, plotDisp=True)
# # AmplitudeRabi.save_data(Instance_AmplitudeRabi, data_AmplitudeRabi)
# # AmplitudeRabi.save_config(Instance_AmplitudeRabi)
#
# # Instance_T1Experiment = T1Experiment(path="dataTestT1Experiment", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
# # data_T1Experiment = T1Experiment.acquire(Instance_T1Experiment)
# # T1Experiment.display(Instance_T1Experiment, data_T1Experiment, plotDisp=True)
# # T1Experiment.save_data(Instance_T1Experiment, data_T1Experiment)
# # T1Experiment.save_config(Instance_T1Experiment)
#
# for i in range(10):
#  Instance_T1Experiment = T1Experiment(path="dataTestT1Experiment", outerFolder=outerFolder, cfg=config, soc=soc,
#                                       soccfg=soccfg)
#  data_T1Experiment = T1Experiment.acquire(Instance_T1Experiment)
#  T1Experiment.display(Instance_T1Experiment, data_T1Experiment, plotDisp=False)
#  T1Experiment.save_data(Instance_T1Experiment, data_T1Experiment)
#  T1Experiment.save_config(Instance_T1Experiment)
#
# print("finished")
#
# #fringe_freq = 4 #MHz
# #config["qubit_freq"] = config["qubit_freq"]# - fringe_freq
# #print("qubit frequency is = " + str(config["qubit_freq"]) + " Mhz")
# # Instance_T2Experiment = T2Experiment(path="T2Ramsey", outerFolder=outerFolder, cfg=config, soc=soc, soccfg=soccfg)
# # data_T2Experiment = T2Experiment.acquire(Instance_T2Experiment)
# # T2Experiment.display(Instance_T2Experiment, data_T2Experiment, plotDisp=True)
# # T2Experiment.save_data(Instance_T2Experiment, data_T2Experiment)
# # T2Experiment.save_config(Instance_T2Experiment)
#
# # ##### run the actual experiment
# # Instance_GainReadOpt_wSingleShot = GainReadOpt_wSingleShot(path="dataTestGainReadOpt_wSingleShot", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
# # data_GainReadOpt_wSingleShot = GainReadOpt_wSingleShot.acquire(Instance_GainReadOpt_wSingleShot, plotDisp=False, plotSave=True)
# # GainReadOpt_wSingleShot.save_data(Instance_GainReadOpt_wSingleShot, data_GainReadOpt_wSingleShot)
# # GainReadOpt_wSingleShot.save_config(Instance_GainReadOpt_wSingleShot)
#
# ######################################################################################################################
#
# # Instance_PiOpt_wSingleShot = PiOpt_wSingleShot(path="dataTestPiOpt_wSingleShot", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
# # data_PiOpt_wSingleShot = PiOpt_wSingleShot.acquire(Instance_PiOpt_wSingleShot, plotDisp=False, plotSave=True)
# # PiOpt_wSingleShot.save_data(Instance_PiOpt_wSingleShot, data_PiOpt_wSingleShot)
# # PiOpt_wSingleShot.save_config(Instance_PiOpt_wSingleShot)


#
# ###################################### code for running basic single shot exerpiment
# UpdateConfig = {
#     ### set flux point
#     'yoko1Voltage': -0.235,
#     'yoko2Voltage': -0.68,
#     ###### cavity
#     # "reps": 2000,  # this will used for all experiements below unless otherwise changed in between trials
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 10, # us
#     "read_pulse_gain": 500, # [DAC units]
#     "read_pulse_freq": 6576.1, ### MHz
#     ##### qubit spec parameters
#     "qubit_pulse_style": "arb",
#     "sigma": 0.080,  ### units us, define a 20ns sigma
#     "qubit_gain": 16000,
#     "qubit_freq": 3407.92,
#     ##### define shots
#     "shots": 1000, ### this gets turned into "reps"
#     "relax_delay": 100,  # us
# }
#
# config = BaseConfig | UpdateConfig
#
# # Biasing at the right flux point
# yoko1.SetVoltage(config["yoko1Voltage"])
# yoko2.SetVoltage(config["yoko2Voltage"])
# config = BaseConfig | UpdateConfig
#
# Instance_SingleShotPS = SingleShotPS(path="dataTestSingleShotPS", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg, progress=True)
# data_SingleShotPS = SingleShotPS.acquire(Instance_SingleShotPS)
# SingleShotPS.save_data(Instance_SingleShotPS, data_SingleShotPS)
# SingleShotPS.save_config(Instance_SingleShotPS)
# SingleShotPS.display(Instance_SingleShotPS, data_SingleShotPS, plotDisp=True)




###################################### code for running basic single shot exerpiment
# UpdateConfig = {
#     ### set flux point
# 'yoko1Voltage': -0.46068325,
#     'yoko2Voltage': -1.5017185,
# ###### cavity
# # "reps": 2000, # this will used for all experiements below unless otherwise changed in between trials
# "read_pulse_style": "const",  # --Fixed
# "read_length": 4,  # us
# "read_pulse_gain": 241,  # [DAC units]
# "read_pulse_freq": 6575.66,  ### MHz
# ##### qubit spec parameters
# "qubit_pulse_style": "arb",  ###
# "sigma": 0.080,  ### units us
# "qubit_length": .32,
# "qubit_gain_pi": 4500,
# "qubit_freq": 2729.6,
# ##### define shots
# "shots": 2000,  ### this gets turned into "reps"
# "qubit_relax_delay": 50,  # us
#
#     ##### define shots
#     "shots": 2000,  ### this gets turned into "reps"
#     "relax_delay": 50,  # us
# }
#
# config = BaseConfig | UpdateConfig
#
# # Biasing at the right flux point
# yoko1.SetVoltage(config["yoko1Voltage"])
# yoko2.SetVoltage(config["yoko2Voltage"])
#
# Instance_SingleShotProgram = SingleShotProgram(path="dataTestSingleShotProgram", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg, progress=True)
# data_SingleShotProgram = SingleShotProgram.acquire(Instance_SingleShotProgram)
# SingleShotProgram.save_data(Instance_SingleShotProgram, data_SingleShotProgram)
# SingleShotProgram.save_config(Instance_SingleShotProgram)
# SingleShotProgram.display(Instance_SingleShotProgram, data_SingleShotProgram, plotDisp=True)
# #


#####################################################################################################################

#################################### 2d sweep with single shot
UpdateConfig = {
    ### set flux point
    'yoko1Voltage': -0.46068325,
    'yoko2Voltage': -1.5017185,
    ###### cavity
    # "reps": 2000, # this will used for all experiements below unless otherwise changed in between trials
    "read_pulse_style": "const",  # --Fixed
    "read_length": 5,  # us
    "read_pulse_gain": 241,  # [DAC units]
    "read_pulse_freq": 6575,  ### MHz
    ##### qubit spec parameters
    'qubit_nqz': 2,
    "qubit_pulse_style": "arb",  ###
    "sigma": 0.08,#0.080,  ### units us
    "qubit_length": 1.0,
    "qubit_gain_pi": 3238,
    "qubit_freq": 5652,
    ##### define shots
    "shots": 2000,  ### 2000  this gets turned into "reps"
    "qubit_relax_delay": 300,  # us

    #### define the loop parameters
    "x_var": "read_pulse_freq",
    "x_start": 6576 - 1 ,
    "x_stop": 6576 + 1,
    "x_num": 5,

    "y_var": "read_pulse_gain",
    "y_start": 100,
    "y_stop": 2000,
    "y_num": 11,
}
config = BaseConfig | UpdateConfig

### yoko reset
######### yoko1.SetVoltage(-5)
####### yoko2.SetVoltage(-5)

############# Biasing at the right flux point
yoko1.SetVoltage(config["yoko1Voltage"])
yoko2.SetVoltage(config["yoko2Voltage"])

Instance_SingleShot_2Dsweep = SingleShot_2Dsweep(path="dataTestSingleShot_2Dsweep", outerFolder=outerFolder, cfg=config,
                                               soc=soc, soccfg=soccfg)
data_SingleShot_2Dsweep = SingleShot_2Dsweep.acquire(Instance_SingleShot_2Dsweep)
SingleShot_2Dsweep.save_data(Instance_SingleShot_2Dsweep, data_SingleShot_2Dsweep)
SingleShot_2Dsweep.save_config(Instance_SingleShot_2Dsweep)

########################################################################################################################
plt.show()