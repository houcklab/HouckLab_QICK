#### import packages
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


###################################### code for running transmission vs gain
UpdateConfig = {
    ### set flux point
    'yoko1Voltage': -0.235,
    'yoko2Voltage': -0.68,
    ####
    "relax_delay": 2, # us
    ###### cavity
    "trans_reps": 200,
    "read_pulse_style": "const",  # --Fixed
    "read_length": 5,  # us
    "read_pulse_gain": 625,  # [DAC units]
    "read_pulse_freq": 6575.87,  ### MHz

    ##### define experiement parameters
    "trans_gain_start": 10000,
    "trans_gain_stop": 1001,
    "trans_gain_num": 2,
    #### freq points
    "trans_freq_start": 6575.87 - 0.1,  # [MHz] actual frequency is this number + "cavity_LO"
    "trans_freq_stop": 6575.87 + 0.1,  # [MHz] actual frequency is this number + "cavity_LO"
    "TransNumPoints": 2,  ### number of points in the transmission frequecny
}

config = BaseConfig | UpdateConfig

############# Biasing at the right flux point
yoko1.SetVoltage(config["yoko1Voltage"])
yoko2.SetVoltage(config["yoko2Voltage"])

#### change gain instead of attenuation
Instance_TransVsGain = TransVsGain(path="dataTestTransVsGain", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
data_TransVsGain = TransVsGain.acquire(Instance_TransVsGain)
TransVsGain.save_data(Instance_TransVsGain, data_TransVsGain)
TransVsGain.save_config(Instance_TransVsGain)


#####################################################################################

plt.show()