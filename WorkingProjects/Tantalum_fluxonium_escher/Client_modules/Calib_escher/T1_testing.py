
#### import packages
import os
path = os.getcwd()
os.add_dll_directory(os.path.dirname(path)+'\\PythonDrivers')
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Calib.initialize import *
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mTransmission_SaraTest import Transmission
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mSpecSlice_SaraTest import SpecSlice
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mAmplitudeRabi import AmplitudeRabi
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mTransVsGain import TransVsGain
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mAmplitudeRabi_Blob import AmplitudeRabi_Blob
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mAmplitudeRabi_CavityPower import AmplitudeRabi_CavityPower
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mT1Experiment import T1Experiment
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mT2EchoExperiment import T2EchoExperiment
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mSingleShotProgram import SingleShotProgram
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mSingleShot_2Dsweep import SingleShot_2Dsweep
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mAmplitudeRabiBlob_PS import AmplitudeRabi_PS
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mAmplitudeRabiFlux_PS import AmplitudeRabiFlux_PS
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mQubitSpecRepeat import QubitSpecRepeat
from matplotlib import pyplot as plt

#### define the saving path
outerFolder = "Z:\JakeB\Data\Tantalum_Fluxonium\TF3SC1_B1\\"

###qubitAtten = attenuator(27797, attenuation_int= 10, print_int = False)


#################################### Running the actual experiments

# Only run this if no proxy already exists
soc, soccfg = makeProxy()
# print(soccfg)

plt.ioff()



# #################################### code for transmission vs power
# UpdateConfig = {
#     "yokoVoltage": 1.9,
#     ##### change gain instead option
#     "trans_gain_start": 100,
#     "trans_gain_stop": 5000,
#     "trans_gain_num": 21,
#     ###### cavity
#     "trans_reps": 500,  # this will used for all experiements below unless otherwise changed in between trials
#     "read_pulse_style": "const",  # --Fixed
#     "readout_length": 10,  # [us]
#     # "read_pulse_gain": 10000,  # [DAC units]
#     "trans_freq_start": 5987,  # [MHz] actual frequency is this number + "cavity_LO"
#     "trans_freq_stop": 5989,  # [MHz] actual frequency is this number + "cavity_LO"
#     "TransNumPoints": 100,  ### number of points in the transmission frequecny
# }
#
# config = BaseConfig | UpdateConfig
#
# #### update the qubit and cavity attenuation
# yoko1.SetVoltage(config["yokoVoltage"])
#
# # ##### run actual experiment
#
# #### change gain instead of attenuation
# Instance_TransVsGain = TransVsGain(path="dataTestTransVsGain", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
# data_TransVsGain = TransVsGain.acquire(Instance_TransVsGain)
# TransVsGain.save_data(Instance_TransVsGain, data_TransVsGain)
# TransVsGain.save_config(Instance_TransVsGain)


# ###################################################################################################################
# ################################### code for running Amplitude rabi Blob
# UpdateConfig = {
#     ##### define attenuators
#     "yokoVoltage": -1.5,
#     ###### cavity
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 10, # us
#     "read_pulse_gain": 5000, # [DAC units]
#     "read_pulse_freq": 6360.37, # [MHz]
#     ##### spec parameters for finding the qubit frequency
#     "qubit_freq_start": 340,
#     "qubit_freq_stop": 370,
#     "RabiNumPoints": 31,  ### number of points
#     "qubit_pulse_style": "arb",
#     "sigma": 0.100,  ### units us, define a 20ns sigma
#     # "flat_top_length": 0.025, ### in us
#     "relax_delay": 5000,  ### turned into us inside the run function
#     ##### amplitude rabi parameters
#     "qubit_gain_start": 0,
#     "qubit_gain_step": 5000, ### stepping amount of the qubit gain
#     "qubit_gain_expts": 7, ### number of steps
#     "AmpRabi_reps": 2000,  # number of averages for the experiment
# }
# config = BaseConfig | UpdateConfig
#
# yoko1.SetVoltage(config["yokoVoltage"])
#
# Instance_AmplitudeRabi_Blob = AmplitudeRabi_Blob(path="dataTestRabiAmpBlob", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg, progress=True)
# data_AmplitudeRabi_Blob = AmplitudeRabi_Blob.acquire(Instance_AmplitudeRabi_Blob)
# AmplitudeRabi_Blob.save_data(Instance_AmplitudeRabi_Blob, data_AmplitudeRabi_Blob)
# AmplitudeRabi_Blob.save_config(Instance_AmplitudeRabi_Blob)
# # # #
# #

######################################################################################################################
########################### T1 measurement
UpdateConfig = {
    ##### define attenuators
    "yokoVoltage": -0.72,
    ###### cavity
    "read_pulse_style": "const", # --Fixed
    "read_length": 10, # us
    "read_pulse_gain": 3000, # [DAC units]
    "read_pulse_freq": 5988.61, # [MHz]
    ##### spec parameters for finding the qubit frequency
    "qubit_freq": 1713.6,
    "qubit_gain": 11500,
    "sigma": 0.100,  ### units us, define a 20ns sigma
    "qubit_pulse_style": "arb", #### arb means gaussain here
    "relax_delay": 5000,  ### turned into us inside the run function
    ##### T1 parameters
    "start": 0, ### us
    "step": 20, ### us
    "expts": 51, ### number of experiemnts
    "reps": 1000, ### number of averages on each experiment
}
config = BaseConfig | UpdateConfig

yoko1.SetVoltage(config["yokoVoltage"])
print("Voltage is ", yoko1.GetVoltage(), " Volts")

Instance_T1Experiment = T1Experiment(path="dataTestT1Experiment", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg,  progress=True)
data_T1Experiment = T1Experiment.acquire(Instance_T1Experiment)
T1Experiment.display(Instance_T1Experiment, data_T1Experiment, plotDisp=True)
T1Experiment.save_data(Instance_T1Experiment, data_T1Experiment)
T1Experiment.save_config(Instance_T1Experiment)


##########################################################################################

# ######################################################################################################################
# # ######### T2 echo measurement
# UpdateConfig = {
#     ##### define attenuators
#     "yokoVoltage": 12.3,
#     ###### cavity
#     "read_pulse_style": "const",  # --Fixed
#     "read_length": 10,  # us
#     "read_pulse_gain": 1300,  # [DAC units]
#     "read_pulse_freq": 5988.4,  # [MHz] actual frequency is this number + "cavity_LO"
#     ##### spec parameters for finding the qubit frequency
#     "qubit_freq": 1447,
#     "pi_qubit_gain": 25000,
#     "pi2_qubit_gain": 12500,
#     "sigma": 0.100,  ### units us, define a 20ns sigma
#     "qubit_pulse_style": "arb", #### arb means gaussain here
#     "relax_delay": 1000,  ### turned into us inside the run function
#     ##### T1 parameters
#     "start": 0, ### us
#     "step": 2, ### us
#     "expts": 41, ### number of experiemnts
#     "reps": 1500, ### number of averages on each experiment
# }
# config = BaseConfig | UpdateConfig
# yoko1.SetVoltage(config["yokoVoltage"])
# print("Voltage is ", yoko1.GetVoltage(), " Volts")
#
# Instance_T2EchoExperiment = T2EchoExperiment(path="dataTestT2EchoExperiment", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg,  progress=True)
# data_T2EchoExperiment = T2EchoExperiment.acquire(Instance_T2EchoExperiment)
# T2EchoExperiment.display(Instance_T2EchoExperiment, data_T2EchoExperiment, plotDisp=True)
# T2EchoExperiment.save_data(Instance_T2EchoExperiment, data_T2EchoExperiment)
# T2EchoExperiment.save_config(Instance_T2EchoExperiment)
# #

################################################################################################

plt.show()