
#### import packages
import os
path = os.getcwd()
os.add_dll_directory(os.path.dirname(path)+'\\PythonDrivers')

from WorkingProjects.Tantalum_fluxonium.Client_modules.Calib.initialize import *
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mSingleShotProgram import SingleShotProgram
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mT1_ThermalPS import T1_ThermalPS

from matplotlib import pyplot as plt
import datetime

#### define the saving path
outerFolder = "Z:\\TantalumFluxonium\\Data\\2023_10_09_BF2_cooldown_5\\TF4\\"

###qubitAtten = attenuator(27797, attenuation_int= 10, print_int = False)

print('starting time: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))

#################################### Running the actual experiments

# Only run this if no proxy already exists
soc, soccfg = makeProxy()
# print(soccfg)

plt.ioff()
####################################################################################################################


# # ####################################### code for running basic single shot exerpiment
# UpdateConfig = {
#     ##### set yoko
#     "yokoVoltage": -3.825 + 0.00,
#     ###### cavity
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 5, # us
#     "read_pulse_gain": 11000, # [DAC units]
#     "read_pulse_freq": 6436.92, # [MHz]
#     ##### qubit spec parameters
#     "qubit_pulse_style": "arb",
#     "qubit_gain": 0,
#     "qubit_length": 10,  ###us, this is used if pulse style is const
#     "sigma": 0.050,  ### units us
#     "flat_top_length": 0.300,  ### in us
#     "qubit_freq": 2869,
#     "relax_delay": 1000,  ### turned into us inside the run function
#     #### define shots
#     "shots": 5000, ### this gets turned into "reps"
# }
# config = BaseConfig | UpdateConfig
#
# yoko1.SetVoltage(config["yokoVoltage"])
#
# Instance_SingleShotProgram = SingleShotProgram(path="dataTestSingleShotProgram", outerFolder=outerFolder, cfg=config,
#                                                soc=soc, soccfg=soccfg)
# data_SingleShot = SingleShotProgram.acquire(Instance_SingleShotProgram)
# SingleShotProgram.display(Instance_SingleShotProgram, data_SingleShot, plotDisp=True, save_fig=True)
# SingleShotProgram.save_data(Instance_SingleShotProgram, data_SingleShot)
# SingleShotProgram.save_config(Instance_SingleShotProgram)
# #
#
# # # ##### run the single shot experiment
# # loop_len = 21
# # freq_vec = config["read_pulse_freq"] + np.linspace(-0.5, 0.5, loop_len)
# #
# # for idx in range(loop_len):
# #     config["read_pulse_freq"] = freq_vec[idx]
# #
# #     Instance_SingleShotProgram = SingleShotProgram(path="dataTestSingleShotProgram_paramSweep_q2", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
# #     data_SingleShot = SingleShotProgram.acquire(Instance_SingleShotProgram)
# #
# #     SingleShotProgram.display(Instance_SingleShotProgram, data_SingleShot, plotDisp=True, save_fig=True)
# #     plt.clf()
# #     print(idx)

##################################################################################
##################################################################################
################## code finding T1 of a thermal state
UpdateConfig = {
    ##### set yoko
    "yokoVoltage": -3.825 - 0.02,
    ###### cavity
    #"reps": 0,  # this line does nothing, is overwritten with "shots"
    "read_pulse_style": "const", # --Fixed
    "read_length": 5, # [Clock ticks]
    "read_pulse_gain": 11000, # [DAC units]
    "read_pulse_freq": 6436.92, # [MHz]
    ##### qubit spec parameters
    "qubit_pulse_style": "arb",
    "qubit_gain": 0,
    # "qubit_length": 10,  ###us, this is used if pulse style is const
    "sigma": 0.0,  ### units us, define a 20ns sigma
    "qubit_freq": 0,
    "relax_delay": 10,  ### turned into us inside the run function
    #### define shots
    "shots": 5000, ### this gets turned into "reps"
    ### define the wait times
    "wait_start": 1,
    "wait_stop": 1001,
    "wait_num": 201,
    ##### define number of clusters to use
    "cen_num": 2,
}
config = BaseConfig | UpdateConfig

yoko1.SetVoltage(config["yokoVoltage"])
print('starting scan: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))

Instance_T1_ThermalPS = T1_ThermalPS(path="dataTestT1_ThermalPS", outerFolder=outerFolder, cfg=config,
                                               soc=soc, soccfg=soccfg)
data_T1_ThermalPS = T1_ThermalPS.acquire(Instance_T1_ThermalPS)
# T1_ThermalPS.display(Instance_T1_ThermalPS, data_T1_ThermalPS, plotDisp=True, save_fig=True)
T1_ThermalPS.save_data(Instance_T1_ThermalPS, data_T1_ThermalPS)
T1_ThermalPS.save_config(Instance_T1_ThermalPS)

#####################################################################################################################

print('end time: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))

plt.show()
