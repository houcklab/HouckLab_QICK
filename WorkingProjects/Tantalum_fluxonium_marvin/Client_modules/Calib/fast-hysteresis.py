import os

# path = os.getcwd() # Old method, does not work with cells. I have shifted the following code to initialize
path = r'C:\Users\pjatakia\Documents\GitHub\HouckLab_QICK\WorkingProjects\Tantalum_fluxonium_marvin\Client_modules\PythonDrivers'
os.add_dll_directory(os.path.dirname(path) + '\\PythonDrivers')

from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Calib.initialize import *
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mLoopback import LoopbackProgram
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mTransmission_SaraTest import Transmission
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mSpecSlice_SaraTest import SpecSlice
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mSpecSlice_bkg_subtracted import SpecSlice_bkg_sub
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mAmplitudeRabi import AmplitudeRabi
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mTransVsGain import TransVsGain
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mAmplitudeRabi_Blob import AmplitudeRabi_Blob
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mAmplitudeRabi_CavityPower import \
    AmplitudeRabi_CavityPower
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mT1Experiment import T1Experiment
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mT2Experiment import T2Experiment
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mT2EchoExperiment import T2EchoExperiment
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mSingleShotProgram import SingleShotProgram
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mSingleShot_2Dsweep import SingleShot_2Dsweep
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mAmplitudeRabiBlob_PS import AmplitudeRabi_PS
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mAmplitudeRabiFlux_PS import AmplitudeRabiFlux_PS
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mQubitSpecRepeat import QubitSpecRepeat
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.m2QubitFluxDrift import TwoQubitFluxDrift
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mConstantTone import ConstantTone_Experiment
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mT1_PS import T1_PS
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mSingleShotTemp_sse import SingleShotSSE

from matplotlib import pyplot as plt
import datetime

# Define the saving path
outerFolder = "Z:\\TantalumFluxonium\\Data\\2024_06_29_cooldown\\QCage_dev\\"

# Print the start time
print('starting time: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))

# Only run this if no proxy already exists
soc, soccfg = makeProxy()

SwitchConfig = {
    "trig_buffer_start": 0.035, # in us
    "trig_buffer_end": 0.024, # in us
    "trig_delay": 0.07, # in us
}
BaseConfig = BaseConfig  | SwitchConfig

#%%
# Defining changes to the config
UpdateConfig = {
    # define the yoko voltage
    "yokoVoltageStart": 1.5,
    "yokoVoltageStop": 15,
    #"yokoVoltageNumPoints": 11,

    # Parameters
    "reps": 300,  # Number of repetitions

    # cavity
    "read_pulse_style": "const",
    "read_length": 20,
    "read_pulse_gain": 500,
    "read_pulse_freq":  6250,
    "num_shots": 20,

    # Experiment Parameters
    "TransSpan": 10,  # [MHz] span will be center frequency +/- this parameter
    "TransNumPoints": 301,  # number of points in the transmission frequency
}


config = BaseConfig | UpdateConfig

#%%
# Run experiment: Set at starting voltage, measure num_shots times. Ramp directly up to yokoVoltageStop then down, measure num_shots times again at yokoVoltageStart.
print('setting Yoko')
yoko1._rampstep = 0.01
yoko1.SetVoltage(config['yokoVoltageStart'])

cavity_freqs_start = np.zeros([config['num_shots'],1])
cavity_freqs_stop = np.zeros([config['num_shots'],1])
from tqdm import tqdm
for i in tqdm(range(config['num_shots'])):
    #measure and store cavity frequency
    config['read_pulse_freq'] = 6250
    Instance_trans = Transmission(path="Hyst_dataTestTransmission", cfg=config, soc=soc, soccfg=soccfg,
                                  outerFolder=outerFolder)
    data_trans = Instance_trans.acquire()
    Instance_trans.save_data(data_trans)
    Instance_trans.display(data_trans, plotDisp=False)
    cavity_freqs_start[i] = Instance_trans.peakFreq

print('ramping up to yokoStopVoltage and baack down')

yoko1.SetVoltage(config['yokoVoltageStop'])
time.sleep(60) #sit here for a bit - magnet ring up?
print('ramping up to yokoStopVoltage and back down')

yoko1.SetVoltage(config['yokoVoltageStart'])
#Measure for the second time
for i in tqdm(range(config['num_shots'])):
    #measure and store cavity frequency
    config['read_pulse_freq'] = 6250
    Instance_trans = Transmission(path="Hyst_dataTestTransmission", cfg=config, soc=soc, soccfg=soccfg,
                                  outerFolder=outerFolder)
    data_trans = Instance_trans.acquire()
    Instance_trans.save_data(data_trans)
    Instance_trans.display(data_trans, plotDisp=False)
    cavity_freqs_stop[i] = Instance_trans.peakFreq

     #%%