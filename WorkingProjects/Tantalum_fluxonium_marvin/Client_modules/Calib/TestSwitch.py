#### import packages
import os

path = os.getcwd()
os.add_dll_directory(os.path.dirname(path) + '\\PythonDrivers')

from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Calib.initialize import *

from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mAmplitudeRabiBlob_PS_switch import AmplitudeRabi_PS_switch
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mSingleShotPS_switch import SingleShotPS_switch
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mT1_PS import T1_PS
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
# # #########################################
# # ###### amplitude rabi with post selection and triggering the swtich
# UpdateConfig = {
#     ##### define yoko
#     "yokoVoltage": -2.25,
#     ###### cavity
#     "read_pulse_style": "const",  # --Fixed
#     "read_length": 10,  # us
#     "read_pulse_gain": 8000,  # [DAC units]
#     "read_pulse_freq": 6436.9,  # [MHz]
#     ##### spec parameters for finding the qubit frequency
#     "qubit_freq_start": 2894 - 20,
#     "qubit_freq_stop": 2894 + 20,
#     "RabiNumPoints": 41,  ### number of points
#     "qubit_pulse_style": "arb",
#     "sigma": 0.050,  ### units us, define a 20ns sigma
#     # "flat_top_length": 10.00, ### in us
#     "relax_delay": 50,  ### turned into us inside the run function
#     ##### amplitude rabi parameters
#     "qubit_gain_start": 10000,
#     "qubit_gain_step": 5000,  ### stepping amount of the qubit gain
#     "qubit_gain_expts": 3,  ### number of steps
#     # "AmpRabi_reps": 2000,  # number of averages for the experiment
#     ##### define number of clusters to use
#     "cen_num": 3,
#     "shots": 4000,  ### this gets turned into "reps"
# }
# config = BaseConfig | UpdateConfig | SwitchConfig
#
# yoko1.SetVoltage(config["yokoVoltage"])
#
# Instance_AmplitudeRabi_PS_switch = AmplitudeRabi_PS_switch(path="dataTestAmplitudeRabi_PS_switch", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg, progress=True)
# data_AmplitudeRabi_PS_switch = AmplitudeRabi_PS_switch.acquire(Instance_AmplitudeRabi_PS_switch)
# AmplitudeRabi_PS_switch.save_data(Instance_AmplitudeRabi_PS_switch, data_AmplitudeRabi_PS_switch)
# AmplitudeRabi_PS_switch.save_config(Instance_AmplitudeRabi_PS_switch)
# #


# # # # # # # ##############################################################################################################
# ####################################### code for running basic single shot experiment with post selection
# UpdateConfig = {
#     ##### define yoko
#     "yokoVoltage": -2.25,
#     ###### cavity
#     "read_pulse_style": "const",  # --Fixed
#     "read_length": 10,  # us
#     "read_pulse_gain": 8000,  # [DAC units]
#     "read_pulse_freq": 6436.9,  # [MHz]
#     ##### qubit spec parameters
#     "qubit_pulse_style": "arb",
#     "qubit_gain": 20000,
#     # "qubit_length": 10,  ###us, this is used if pulse style is const
#     # "flat_top_length": 10.00, ### in us
#     "sigma": 0.050,  ### units us, define a 20ns sigma
#     "qubit_freq": 2892,
#     "relax_delay": 10,  ### turned into us inside the run function
#     #### define shots
#     "shots": 10000,  ### this gets turned into "reps"
#     #### define info for clustering
#     "cen_num": 3,
# }
# config = BaseConfig | UpdateConfig | SwitchConfig
#
# yoko1.SetVoltage(config["yokoVoltage"])
# Instance_SingleShotPS_switch = SingleShotPS_switch(path="dataTestSingleShotPS_switch", outerFolder=outerFolder, cfg=config,
#                                      soc=soc, soccfg=soccfg)
# data_SingleShotPS_switch = SingleShotPS_switch.acquire(Instance_SingleShotPS_switch)
# # data_SingleShotPS_switch.display(Instance_SingleShotPS, data_SingleShotPS, plotDisp=True, save_fig=True)
# SingleShotPS_switch.save_data(Instance_SingleShotPS_switch, data_SingleShotPS_switch)
# SingleShotPS_switch.save_config(Instance_SingleShotPS_switch)

#####################################################################################################################

# # ###############################################################################
################## code finding T1 of a thermal state using pulses
UpdateConfig = {
    ##### define attenuators
    "yokoVoltage": -2.4 + 1.25,
    ###### cavity
    "read_pulse_style": "const", # --Fixed
    "read_length": 5, # us
    "read_pulse_gain": 10000, # [DAC units]
    "read_pulse_freq": 6437.4,
    ##### qubit spec parameters
    "qubit_pulse_style": "arb",
    "qubit_gain": 5000, #12000,
    # "qubit_length": 10,  ###us, this is used if pulse style is const
    "sigma": 0.050,  ### units us, define a 20ns sigma
    # "flat_top_length": 0.300,
    "qubit_freq": 4139.0,
    "relax_delay": 100,  ### turned into us inside the run function
    #### define shots
    "shots": 10000, ### this gets turned into "reps"
    ### define the wait times
    "wait_start": 0,
    "wait_stop": 1000,
    "wait_num": 3,
    ##### define number of clusters to use
    "cen_num": 3,
    "use_switch": True,
}
config = BaseConfig | UpdateConfig | SwitchConfig

yoko1.SetVoltage(config["yokoVoltage"])
print('starting scan: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))

scan_time = (np.sum(np.linspace(config["wait_start"], config["wait_stop"], config["wait_num"])) + config["relax_delay"])*config["shots"] *1e-6 / 60

print('estimated time: ' + str(round(scan_time, 2)) + ' minutes')

Instance_T1_PS = T1_PS(path="dataTestT1_PS", outerFolder=outerFolder, cfg=config,
                                               soc=soc, soccfg=soccfg)
data_T1_PS = T1_PS.acquire(Instance_T1_PS)
T1_PS.save_data(Instance_T1_PS, data_T1_PS)
print('scan complete starting data processing: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
T1_PS.save_config(Instance_T1_PS)
T1_PS.process_data(Instance_T1_PS, data_T1_PS)

print('end of analysis: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))

#####################################################################################################################
print('end time: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))

plt.show()