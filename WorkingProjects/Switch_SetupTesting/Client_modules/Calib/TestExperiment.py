
#### import packages
import os
path = os.getcwd()
os.add_dll_directory(os.path.dirname(path)+'\\PythonDrivers')
from WorkingProjects.Switch_SetupTesting.Client_modules.Calib.initialize import *
from WorkingProjects.Switch_SetupTesting.Client_modules.Experiments.mAmplitudeRabi import AmplitudeRabi
from matplotlib import pyplot as plt
import datetime

#### define the saving path
outerFolder = "Z:\\TantalumFluxonium\\Data\\2023_07_20_BF2_cooldown_3\\TF4\\"

###qubitAtten = attenuator(27797, attenuation_int= 10, print_int = False)

print('starting time: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))

#################################### Running the actual experiments

# Only run this if no proxy already exists
soc, soccfg = makeProxy()
# print(soccfg)

print('proxy made!!!!!')

plt.ioff()

# # # Configure for transmission experiment
# UpdateConfig_transmission={
#     "reps": 10,  # this will used for all experiements below unless otherwise changed in between trials
#     "read_pulse_style": "const", # --Fixed
#     "readout_length": 10, # us
#     "read_pulse_gain": 2000,#500, # [DAC units]
#     "read_pulse_freq": 6.3605 , # [MHz] actual frequency is this number + "cavity_LO"
#     "nqz": 2,  #### refers to cavity
#     ##### define tranmission experiment parameters
#     "TransSpan": 1, ### MHz, span will be center+/- this parameter
#     "TransNumPoitns": 200, ### number of points in the transmission frequecny
# }

# # Configure for qubit experiment
# UpdateConfig_qubit = {
#     "qubit_pulse_style": "const",
#     "qubit_gain": 3000,
#     "qubit_freq": 265.56, ###########
#     "qubit_length": 30,
#     ##### define spec slice experiment parameters
#     "qubit_freq_start": 264,
#     "qubit_freq_stop": 267,
#     "SpecNumPoints": 21,  ### number of points
#     'spec_reps': 1800,
#     ##### amplitude rabi parameters
#     "qubit_gain_start": 0, ########
#     "qubit_gain_step": 200, #200 ### stepping amount of the qubit gain
#     "qubit_gain_expts": 26,#26,  ### number of steps
#     "AmpRabi_reps": 2000,#10000,  # number of averages for the experiment
#     ##### define the yoko voltage
#     "yokoVoltage": 0.0,
#     "relax_delay": 1500,
# }
#
# UpdateConfig = UpdateConfig_transmission | UpdateConfig_qubit
# config = BaseConfig | UpdateConfig ### note that UpdateConfig will overwrite elements in BaseConfig
#
# # set the yoko frequency
# yoko1.SetVoltage(config["yokoVoltage"])
# print("Voltage is ", yoko1.GetVoltage(), " Volts")
#
# #
#
# ##################################### code for runnning basic transmission and specSlice
# # perform the cavity transmission experiment
#
# Instance_trans = Transmission(path="dataTestTransmission", cfg=config,soc=soc,soccfg=soccfg, outerFolder = outerFolder)
# data_trans= Transmission.acquire(Instance_trans)
# Transmission.display(Instance_trans, data_trans, plotDisp=True)
# Transmission.save_data(Instance_trans, data_trans)

#
# ## update the transmission frequency to be the peak
# config["read_pulse_freq"] = Instance_trans.peakFreq
# print("Cavity freq IF [MHz] = ", Instance_trans.peakFreq)
#
# # Instance_specSlice = SpecSlice(path="dataTestSpecSlice", cfg=config,soc=soc,soccfg=soccfg, outerFolder = outerFolder)
# # data_specSlice= SpecSlice.acquire(Instance_specSlice)
# # SpecSlice.display(Instance_specSlice, data_specSlice, plotDisp=True)
# # SpecSlice.save_data(Instance_specSlice, data_specSlice)
#
# #
# config["qubit_pulse_style"]= "arb"
# config["sigma"] = 0.2 # 0.2 # us
# #
# # # #
# # # # # print(config)
# Instance_AmplitudeRabi = AmplitudeRabi(path="dataTestAmplitudeRabi", cfg=config,soc=soc,soccfg=soccfg, outerFolder = outerFolder)
# data_AmplitudeRabi = AmplitudeRabi.acquire(Instance_AmplitudeRabi)
# AmplitudeRabi.display(Instance_AmplitudeRabi, data_AmplitudeRabi, plotDisp=True)
# AmplitudeRabi.save_data(Instance_AmplitudeRabi, data_AmplitudeRabi)
# AmplitudeRabi.save_config(Instance_AmplitudeRabi)
#
# #
#
# ########################################################################################################################

################################### code for running Amplitude rabi Blob
UpdateConfig = {
    ##### define attenuators
    "yokoVoltage": -2.80,
    ###### cavity
    "read_pulse_style": "const", # --Fixed
    "read_length": 5, # us
    "read_pulse_gain": 10000, # [DAC units]
    "read_pulse_freq": 6437.2,
    ##### spec parameters for finding the qubit frequency
    "qubit_freq": 2033,
    "qubit_pulse_style": "arb",
    "sigma": 0.300,  ### units us, define a 20ns sigma
    # "flat_top_length": 0.100, ### in us
    "relax_delay": 500,  ### turned into us inside the run function
    "qubit_gain": 15000,
    "AmpRabi_reps": 10,
}
config = BaseConfig | UpdateConfig


#### update the qubit and cavity attenuation
# yoko1.SetVoltage(config["yokoVoltage"])

# ##### run actual experiment

#### change gain instead of attenuation
Instance_AmplitudeRabi = AmplitudeRabi(path="dataTestTransVsGain", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
data_AmplitudeRabi = AmplitudeRabi.acquire(Instance_AmplitudeRabi)
# AmplitudeRabi.save_data(Instance_AmplitudeRabi, data_AmplitudeRabi)
# AmplitudeRabi.save_config(Instance_AmplitudeRabi)


print('end time: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))

plt.show()

# #
# plt.show(block = True)
