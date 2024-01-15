#### import packages
import os

path = os.getcwd()
os.add_dll_directory(os.path.dirname(path) + '\\PythonDrivers')

from WorkingProjects.Tantalum_fluxonium.Client_modules.Calib.initialize import *

from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mAmplitudeRabiBlob_PS_switch import AmplitudeRabi_PS_switch
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mSingleShotPS_switch import SingleShotPS_switch
from matplotlib import pyplot as plt
import datetime

# Define the saving path
outerFolder = "Z:\\TantalumFluxonium\\Data\\2023_10_31_BF2_cooldown_6\\TF4\\"

# Print the start time
print('starting time: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))

# Only run this if no proxy already exists
soc, soccfg = makeProxy()

# Disable the interactive mode
plt.ioff()

# ####################################################################################################################
#
SwitchConfig = {
    "trig_buffer_start": 0.035, # in us
    "trig_buffer_end": 0.024, # in us
    "trig_delay": 0.07, # in us
}
#
# ###########################################
# # ###### amplitude rabi with post seelction and triggering the swtich
# UpdateConfig = {
#     ##### define attenuators
#     "yokoVoltage": -2.4,
#     ###### cavity
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 10, # us
#     "read_pulse_gain": 10000,  # [DAC units]
#     "read_pulse_freq": 6437.55,  # [MHz]
#     ##### spec parameters for finding the qubit frequency
#     "qubit_freq_start": 3955 - 15,
#     "qubit_freq_stop": 3955 + 15,
#     "RabiNumPoints": 31,  ### number of points
#     "qubit_pulse_style": "arb",
#     "sigma": 0.100,  ### units us, define a 20ns sigma
#     # "flat_top_length": 0.600, ### in us
#     "relax_delay": 10,  ### turned into us inside the run function
#     ##### amplitude rabi parameters
#     "qubit_gain_start": 500,
#     "qubit_gain_step": 1500, ### stepping amount of the qubit gain
#     "qubit_gain_expts": 3, ### number of steps
#     # "AmpRabi_reps": 2000,  # number of averages for the experiment
#     ##### define number of clusters to use
#     "cen_num": 2,
#     "shots": 5000,  ### this gets turned into "reps"
# }
# config = BaseConfig | UpdateConfig | SwitchConfig
#
# yoko1.SetVoltage(config["yokoVoltage"])
#
# Instance_AmplitudeRabi_PS_switch = AmplitudeRabi_PS_switch(path="dataTestAmplitudeRabi_PS_switch", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg, progress=True)
# data_AmplitudeRabi_PS_switch = AmplitudeRabi_PS_switch.acquire(Instance_AmplitudeRabi_PS_switch)
# AmplitudeRabi_PS_switch.save_data(Instance_AmplitudeRabi_PS_switch, data_AmplitudeRabi_PS_switch)
# AmplitudeRabi_PS_switch.save_config(Instance_AmplitudeRabi_PS_switch)



# # # # ##############################################################################################################
####################################### code for running basic single shot experiment with post selection
UpdateConfig = {
    ##### set yoko
    "yokoVoltage": -2.4,
    ###### cavity
    "reps": 2000,  # this will be used for all experiments below unless otherwise changed in between trials
    "read_pulse_style": "const",  # --Fixed
    "read_length": 10,  # us
    "read_pulse_gain": 10000,  # [DAC units]
    "read_pulse_freq": 6437.55,  # [MHz]
    ##### qubit spec parameters
    "qubit_pulse_style": "arb",
    "qubit_gain": 1400,
    # "qubit_length": 10,  ###us, this is used if pulse style is const
    # "flat_top_length": 0.600, ### in us
    "sigma": 0.100,  ### units us, define a 20ns sigma
    "qubit_freq": 3964.5,
    "relax_delay": 1000,  ### turned into us inside the run function
    #### define shots
    "shots": 5000,  ### this gets turned into "reps"
    #### define info for clustering
    "cen_num": 2,
}
config = BaseConfig | UpdateConfig | SwitchConfig

yoko1.SetVoltage(config["yokoVoltage"])
Instance_SingleShotPS_switch = SingleShotPS_switch(path="dataTestSingleShotPS_switch", outerFolder=outerFolder, cfg=config,
                                     soc=soc, soccfg=soccfg)
data_SingleShotPS_switch = SingleShotPS_switch.acquire(Instance_SingleShotPS_switch)
# data_SingleShotPS_switch.display(Instance_SingleShotPS, data_SingleShotPS, plotDisp=True, save_fig=True)
SingleShotPS_switch.save_data(Instance_SingleShotPS_switch, data_SingleShotPS_switch)
SingleShotPS_switch.save_config(Instance_SingleShotPS_switch)
# # #

#####################################################################################################################

print('end time: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))

plt.show()