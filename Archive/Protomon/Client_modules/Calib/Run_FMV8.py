#### import packages
import numpy as np

import os
path = os.getcwd()
os.add_dll_directory(os.path.dirname(path)+'\\PythonDrivers')
from Protomon.Client_modules.Calib.initialize import *
from Protomon.Client_modules.Helpers.hist_analysis import *
from Protomon.Client_modules.Helpers.MixedShots_analysis import *
from matplotlib import pyplot as plt
from time import sleep
from Protomon.Client_modules.Experiments.mSpectrumanalyzer import Spectrumanalyzer
from Protomon.Client_modules.Experiments.mTransmission import Transmission
from Protomon.Client_modules.Experiments.mSpecSlice_ShashwatTest import SpecSlice
from Protomon.Client_modules.Experiments.mFluxDriftTest import FluxDriftTest
from Protomon.Client_modules.Experiments.mSpecVsFlux import SpecVsFlux
from Protomon.Client_modules.Experiments.mSingleShotProgram import SingleShotProgram
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

########################################################################################################################
###################################### code for optimizing readout parameters
config = {'res_ch': 1, 'qubit_ch': 3,#3,#5,
          'mixer_freq': 0.0, 'ro_chs': [0],
# Yoko parameters
'yoko1Voltage': -5,
    'yoko2Voltage': -5,
# 'yoko1Voltage': 0.37925, 'yoko2Voltage': 1.5565,
#'yoko1Voltage': 0.35975, 'yoko2Voltage': 1.4855,

# Cavity parameters
 'nqz': 2, 'relax_delay': 200, 'res_phase': 0,
'trans_freq_start': 6570, 'trans_freq_stop': 6582, 'TransNumPoints': 101, 'trans_reps': 80, 'trans_rounds': 1, 'read_pulse_gain': 241,
 'adc_trig_offset': 0.51, 'cavity_LO': 0,  'read_pulse_style': 'const',  'read_pulse_freq': 6576.02, 'read_length': 4,

 # Qubit parameters
 'qubit_pulse_style': 'const', 'qubit_gain': 1000, 'qubit_nqz': 1, #12500 is a bit broader
 'qubit_freq': 5649.2, 'qubit_length': 10, 'qubit_relax_delay': 200,
 # 'qubit_freq_start': 4410, 'qubit_freq_stop': 4450, 'SpecNumPoints': 301, 'spec_reps': 100, 'spec_rounds': 10, # Broad transition
'qubit_freq_start': 2650, 'qubit_freq_stop': 2900 , 'SpecNumPoints':251, 'spec_reps': 100, 'spec_rounds': 10, # qubit freq stop=2800, pts=151, reps=100 Qubit transition

# # Rabi experiment
 'qubit_gain_start': 0, 'qubit_gain_step': 50, 'qubit_gain_expts': 200, 'AmpRabi_reps': 100, 'AmpRabi_rounds': 10,'sigma': 0.08,#.08,#0.08, # 4000

# # Yoko sweep0.376 1.472
 'yoko1VoltageStart': 0.38,  'yoko1VoltageStop':0.384,   'yoko2VoltageStart': 1.6601818181818189 , 'yoko2VoltageStop': 1.4790909090909086, 'yokoVoltageNumPoints': 41,# "theta":0.1,
# 0.3885125 1.590225 # sweeping common
# # Rabi blob
 'qubit_freq_start_rabiBlob': 2703-10, 'qubit_freq_stop_rabiBlob': 2703+10, 'qubit_freq_expts_rabiBlob': 151,
#
# ## Readout optimization
#  'trans_gain_start_readopt': 20, 'trans_gain_stop_readopt': 300, 'trans_gain_num_readopt': 21,
#  'trans_freq_start_readopt': 4729.1-10, 'trans_freq_stop_readopt': 4729.1+10, 'trans_freq_num_readopt': 21,
#  'qubit_gain_start_readopt': 7500, 'qubit_gain_stop_readopt': 8500, 'qubit_gain_num_readopt': 21,
#  'qubit_freq_start_readopt': 2494.9 - 10, 'qubit_freq_stop_readopt': 2494.9 + 10, 'qubit_freq_num_readopt': 11,
#
# # T1 measurement
  'T1_reps': 100, 'T1_rounds': 50,  "T1_start": 0, "T1_step": .5, "T1_expts": 200,"pigain": 4500,
# Drift measurement
 "drift_wait_step": 0.01,  ### (min) time of each waiting step
 "drift_wait_num": 1000,  ### number of steps to take
# # T2 measurement


"T2R_reps": 100, "T2R_rounds": 10, "start":0, "step": .1, "T2R_expts":50, "pi2_qubit_gain": 10580/2,"T2R_phase_step": 8*360/100, #Degrees,
## What xanthe did: 8 fringes with 100 points

          }

# yoko1.SetVoltage(-5)
# yoko2.SetVoltage(-5)

# Biasing at the right flux point
yoko1.SetVoltage(config["yoko1Voltage"])
yoko2.SetVoltage(config["yoko2Voltage"])

### Spectrum analyzer tuneup
## Cavity tuneup
## 'trans_freq_start': 6575, 'trans_freq_stop': 6577, 'TransNumPoints': 51, 'trans_reps': 4000, 'trans_rounds': 1, 'read_pulse_gain': 500,
## Qubit tuneup
## 'trans_freq_start': 3000, 'trans_freq_stop': 3001, 'TransNumPoints': 51, 'trans_reps': 4000000, 'trans_rounds': 1, 'read_pulse_gain': 30000,
# Instance_spectrum = Spectrumanalyzer(path="spectrumAnalyzer", cfg=config,soc=soc,soccfg=soccfg, outerFolder = outerFolder)
# data_trans= Spectrumanalyzer.acquire(Instance_spectrum)

# Instance_trans = Transmission(path="Transmission", cfg=config,soc=soc,soccfg=soccfg, outerFolder = outerFolder)
# data_trans= Transmission.acquire(Instance_trans)
# Transmission.display(Instance_trans, data_trans, plotDisp=True)
# # Transmission.save_data(Instance_trans, data_trans)
# ### update the transmission frequency to be the peak
# config["read_pulse_freq"] = Instance_trans.peakFreq -0.1
# print("new cavity freq =", config["read_pulse_freq"])


# Instance_SingleShotProgram = SingleShotProgram(path="SingleShotProgram", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
# data_SingleShot = SingleShotProgram.acquire(Instance_SingleShotProgram)
# SingleShotProgram.display(Instance_SingleShotProgram, data_SingleShot, plotDisp=False)

Instance_SpecVsFlux = SpecVsFlux(path="dataTestSpecVsFlux", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
data_SpecVsFlux = SpecVsFlux.acquire(Instance_SpecVsFlux,plotDisp = False, plotSave = True)
SpecVsFlux.save_data(Instance_SpecVsFlux, data_SpecVsFlux)
SpecVsFlux.save_config(Instance_SpecVsFlux)

              print("debug")

Instance_specSlice = SpecSlice(path="SpecSlice", cfg=config,soc=soc,soccfg=soccfg, outerFolder = outerFolder)
data_specSlice= SpecSlice.acquire(Instance_specSlice)
SpecSlice.display(Instance_specSlice, data_specSlice, plotDisp=True)
SpecSlice.save_data(Instance_specSlice, data_specSlice)
### update the spec frequency to be the peak
config["qubit_freq"] =  Instance_specSlice.peakFreq
print("new qubit freq =", config["qubit_freq"])

print("debug")


#
# Instance_AmplitudeRabi_Blob = AmplitudeRabi_Blob(path="dataTestRabiAmpBlob", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg, progress=True)
# data_AmplitudeRabi_Blob = AmplitudeRabi_Blob.acquire(Instance_AmplitudeRabi_Blob)
# AmplitudeRabi_Blob.save_data(Instance_AmplitudeRabi_Blob, data_AmplitudeRabi_Blob)
# AmplitudeRabi_Blob.save_config(Instance_AmplitudeRabi_Blob)
#
# print("debug")

# for i in range(864):
#     Instance_specSlice = SpecSlice(path="SpecSlice", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
#     data_specSlice = SpecSlice.acquire(Instance_specSlice)
#     SpecSlice.display(Instance_specSlice, data_specSlice, plotDisp=False)
#     SpecSlice.save_data(Instance_specSlice, data_specSlice)
#     sleep(300)
#


##### Flux drift experiment
# Instance_FluxDriftTest = FluxDriftTest(path="dataTestFluxDriftTest", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
# data_FluxDriftTest = FluxDriftTest.acquire(Instance_FluxDriftTest, plotDisp=True, plotSave=True)
# FluxDriftTest.save_data(Instance_FluxDriftTest, data_FluxDriftTest)
# FluxDriftTest.save_config(Instance_FluxDriftTest)

config['qubit_relax_delay'] = 100 # was 200 before
Instance_AmplitudeRabi = AmplitudeRabi(path="dataTestAmplitudeRabi", cfg=config,soc=soc,soccfg=soccfg, outerFolder = outerFolder)
data_AmplitudeRabi = AmplitudeRabi.acquire(Instance_AmplitudeRabi)
AmplitudeRabi.display(Instance_AmplitudeRabi, data_AmplitudeRabi, plotDisp=True)
AmplitudeRabi.save_data(Instance_AmplitudeRabi, data_AmplitudeRabi)
AmplitudeRabi.save_config(Instance_AmplitudeRabi)

#




#
# Instance_T1Experiment = T1Experiment(path="dataTestT1Experiment", outerFolder=outerFolder, cfg=config, soc=soc,
#                                       soccfg=soccfg)
# data_T1Experiment = T1Experiment.acquire(Instance_T1Experiment)
# T1Experiment.display(Instance_T1Experiment, data_T1Experiment, plotDisp=True)
# T1Experiment.save_data(Instance_T1Experiment, data_T1Experiment)
# T1Experiment.save_config(Instance_T1Experiment)

# print("debug")
# for i in range(1):
#  Instance_T1Experiment = T1Experiment(path="dataTestT1Experiment", outerFolder=outerFolder, cfg=config, soc=soc,
#                                       soccfg=soccfg)
#  data_T1Experiment = T1Experiment.acquire(Instance_T1Experiment)
#  T1Experiment.display(Instance_T1Experiment, data_T1Experiment, plotDisp=True)
#  T1Experiment.save_data(Instance_T1Experiment, data_T1Experiment)
#  T1Experiment.save_config(Instance_T1Experiment)



# fringe_freq = 4 #MHz
# config["qubit_freq"] = config["qubit_freq"]# - fringe_freq
# print("qubit frequency is = " + str(config["qubit_freq"]) + " Mhz")
# Instance_T2Experiment = T2Experiment(path="T2Ramsey", outerFolder=outerFolder, cfg=config, soc=soc, soccfg=soccfg)
# data_T2Experiment = T2Experiment.acquire(Instance_T2Experiment)
# T2Experiment.display(Instance_T2Experiment, data_T2Experiment, plotDisp=True)
# T2Experiment.save_data(Instance_T2Experiment, data_T2Experiment)
# T2Experiment.save_config(Instance_T2Experiment)
# print("finished")
# ##### run the actual experiment
# Instance_GainReadOpt_wSingleShot = GainReadOpt_wSingleShot(path="dataTestGainReadOpt_wSingleShot", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
# data_GainReadOpt_wSingleShot = GainReadOpt_wSingleShot.acquire(Instance_GainReadOpt_wSingleShot, plotDisp=False, plotSave=True)
# GainReadOpt_wSingleShot.save_data(Instance_GainReadOpt_wSingleShot, data_GainReadOpt_wSingleShot)
# GainReadOpt_wSingleShot.save_config(Instance_GainReadOpt_wSingleShot)

######################################################################################################################

# Instance_PiOpt_wSingleShot = PiOpt_wSingleShot(path="dataTestPiOpt_wSingleShot", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
# data_PiOpt_wSingleShot = PiOpt_wSingleShot.acquire(Instance_PiOpt_wSingleShot, plotDisp=False, plotSave=True)
# PiOpt_wSingleShot.save_data(Instance_PiOpt_wSingleShot, data_PiOpt_wSingleShot)
# PiOpt_wSingleShot.save_config(Instance_PiOpt_wSingleShot)


########################################################################################################################
plt.show()