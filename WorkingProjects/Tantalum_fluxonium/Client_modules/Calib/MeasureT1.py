#### import packages
import os
path = os.getcwd()
os.add_dll_directory(os.path.dirname(path)+'\\PythonDrivers')
from STFU.Client_modules.Calib.initialize import *
from STFU.Client_modules.Experiments.mTransmission_SaraTest import Transmission
from STFU.Client_modules.Experiments.mSpecSlice_SaraTest import SpecSlice
from STFU.Client_modules.Experiments.mAmplitudeRabi import AmplitudeRabi
from STFU.Client_modules.Experiments.mTransVsGain import TransVsGain
from STFU.Client_modules.Experiments.mAmplitudeRabi_Blob import AmplitudeRabi_Blob
from STFU.Client_modules.Experiments.mAmplitudeRabi_CavityPower import AmplitudeRabi_CavityPower
from STFU.Client_modules.Experiments.mT1Experiment import T1Experiment
from STFU.Client_modules.Experiments.mT1Experiment2 import T1Experiment2
from matplotlib import pyplot as plt

#### define the saving path
outerFolder = "Z:\Parth\Data\Tantalum_Fluxonium\TF1SC1_B3_RFSOC\Q2\\"

# Only run this if no proxy already exists
soc, soccfg = makeProxy()

plt.ioff()

# Configure for transmission experiment
UpdateConfig={
    "reps": 10,                         ### This will used for all experiements below unless otherwise changed in between trials
    "read_pulse_style": "const",
    "read_length": 10,                  ### in us
    "read_pulse_gain": 12000,           ### [DAC units]
    "read_pulse_freq": 891.5 ,          ### [MHz] actual frequency is this number + "cavity_LO"

    ##### define tranmission experiment parameters

    "TransSpan": 1,                     ### MHz, span will be center+/- this parameter
    "TransNumPoitns": 200,              ### Number of points in the transmission frequency

    ##### define the yoko voltage

    "yokoVoltage": 0.39742,
    "relax_delay": 4000,
}

# Updating the BaseConfig Dictionary from initialize
config = BaseConfig | UpdateConfig

# set the yoko frequency
yoko1.SetVoltage(config["yokoVoltage"])
print("Voltage is ", yoko1.GetVoltage(), " Volts")

############### code for finding the cavity ######################

Instance_trans = Transmission(path="dataTestTransmission", cfg=config,soc=soc,soccfg=soccfg, outerFolder = outerFolder)
data_trans= Transmission.acquire(Instance_trans)
Transmission.display(Instance_trans, data_trans, plotDisp=False)
Transmission.save_data(Instance_trans, data_trans)


## update the transmission frequency to be the peak
config["read_pulse_freq"] = Instance_trans.peakFreq
print(Instance_trans.peakFreq)

############### code for finding the T1 ######################

# Configure qubit for T1 Experiment
UpdateConfig = {
    "qubit_pulse_style": "arb",
    "sigma" : 0.2,                      ### in us
    "qubit_gain": 856,
    "qubit_freq": 265.56,

    ##### T1 parameters
    "start":0,
    "ntime_steps": 31,                 ### stepping amount of the qubit gain
    "total_time": 3000,                 ### number of steps
    "T1_reps": 10000,              ### number of averages for the experiment
    "relax_delay": 7000,
}

# Update the current config file
config = config | UpdateConfig

for i in range(3 ):
    Instance_T1Experiment2 = T1Experiment2(path="dataTestT1Experiment", cfg=config,soc=soc,soccfg=soccfg, outerFolder = outerFolder)
    data_T1Experiment2 = T1Experiment2.acquire(Instance_T1Experiment2)
    T1Experiment2.display(Instance_T1Experiment2, data_T1Experiment2, plotDisp=True)
    T1Experiment2.save_data(Instance_T1Experiment2, data_T1Experiment2)
    T1Experiment2.save_config(Instance_T1Experiment2)
    config = config | UpdateConfig

