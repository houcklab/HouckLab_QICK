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
from STFU.Client_modules.Experiments.mT2EchoExperiment import T2EchoExperiment
from STFU.Client_modules.Experiments.mT2Experiment import T2Experiment
from matplotlib import pyplot as plt

#### define the saving path
outerFolder = "Z:\Parth\Data\Tantalum_Fluxonium\TF1SC1_B3_RFSOC\Q2\\"

# Only run this if no proxy already exists
soc, soccfg = makeProxy()
# print(soccfg)

plt.ioff()

# Configure for transmission experiment
UpdateConfig={
    "reps": 10,                         ### This will used for all experiements below unless otherwise changed in between trials
    "read_pulse_style": "const",
    "read_length": 10,                  ### in us
    "read_pulse_gain": 12000,#12000,           ### [DAC units]
    "read_pulse_freq": 891.5,          ### [MHz] actual frequency is this number + "cavity_LO"

    ##### define tranmission experiment parameters

    "TransSpan": 1,                     ### MHz, span will be center+/- this parameter
    "TransNumPoitns": 200,              ### Number of points in the transmission frequency

    ##### define the yoko voltage

    "yokoVoltage": 0.396,
    "relax_delay": 4000,
}

# Updating the BaseConfig Dictionary from initialize
config = BaseConfig | UpdateConfig

# set the yoko frequency
yoko1.SetVoltage(config["yokoVoltage"])
print("Voltage is ", yoko1.GetVoltage(), " Volts")

############### code for finding the cavity ######################

Instance_trans = Transmission(path="dataTestTransmission", cfg=config,soc=soc,soccfg=soccfg, outerFolder = outerFolder)
data_trans= Transmission.acquire()
Transmission.display(Instance_trans)
Transmission.save_data(Instance_trans, data_trans)


## update the transmission frequency to be the peak
config["read_pulse_freq"] = Instance_trans.peakFreq
print(Instance_trans.peakFreq)



########### T2 measurement
UpdateConfig = {
    ##### spec parameters for finding the qubit frequency
    "qubit_freq": 265.56  ,
    "pi_qubit_gain": 856,
    "pi2_qubit_gain": 428,
    "sigma": 0.2,                   ### units us, define a 20ns sigma
    "qubit_pulse_style": "arb",     ### arb means gaussain here
    "relax_delay": 2000,            ### turned into us inside the run function
    ##### T2 ramsey parameters
    "start": 0.010,                 ### us
    "step": 15,                      ### us
    "expts": 51,                    ### number of experiemnts
    "reps": 2500,                   ### number of averages on each experiment
    "yokoVoltage": [0.39742],#[0.39598,0.39599,0.396,0.39601,0.39602],
    "actVolt" : 0
}
config = config | UpdateConfig



config["phase_step"] = soccfg.deg2reg(2*360/config["expts"], gen_ch=config["qubit_ch"])

for volt in config["yokoVoltage"]:
    print(volt)
    yoko1.SetVoltage(volt)
    # config["actVolt"] = volt
    fringe_freq = 0.02
    correction = 245883.9436673*volt**2  -195471.08394789*volt  +38847.9518476
    config["qubit_freq"] = 265.56 - fringe_freq + correction
    print("qubit frequency is = " + str(config["qubit_freq"]) + " Mhz")
    print("Voltage is ", yoko1.GetVoltage(), " Volts")
    config["actVolt"] = yoko1.GetVoltage()
    Instance_T2Experiment = T2EchoExperiment(path="T2Echo", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
    data_T2Experiment = T2EchoExperiment.acquire()
    T2EchoExperiment.display(Instance_T2Experiment)
    T2EchoExperiment.save_data(Instance_T2Experiment, data_T2Experiment)
    T2EchoExperiment.save_config(Instance_T2Experiment)
