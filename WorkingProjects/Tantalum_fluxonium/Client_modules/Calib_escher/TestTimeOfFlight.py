#### import packages
import os
import numpy as np
from matplotlib import pyplot as plt
from tqdm import tqdm
import datetime

path = os.getcwd()
os.add_dll_directory(os.path.dirname(path) + '\\PythonDrivers')
from WorkingProjects.Tantalum_fluxonium.Client_modules.Calib_escher.initialize import *
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mTimeOfFlight_PS import TimeOfFlightPS

UpdateConfig = {
    ##### set yoko
    "yokoVoltage": -0.5,
    "yokoVoltage_freqPoint": -0.5,
    ###### cavity
    "reps": 1,  # this will be used for all experiments below unless otherwise changed in between trials
    "read_pulse_style": "const",  # --Fixed
    "read_length": 15,  # [us]
    "read_length_tof": 2,  # [us]
    "read_pulse_gain": 7000,  # [DAC units]
    "read_pulse_freq": 7392.25,  # [MHz]
    ##### qubit spec parameters
    "qubit_pulse_style": "flat_top",
    "qubit_gain": 23000,
    # "qubit_length": 10,  ###us, this is used if pulse style is const
    "sigma": 0.005,  ### units us, define a 20ns sigma
    "flat_top_length": 10,  ### in us
    "qubit_freq": 4819,
    "relax_delay": 1,
    #### define experiment specific parameters
    "shots": 50000,
    "offset": 0,  # [us] placeholder for actual value
    "offset_start": 0,  # [us]
    "offset_end": 10,  # [us]
    "offset_num": 3,  # [Number of points]
    "max_pulse_length" : 5,
    ##### record the fridge temperature in units of mK
    "fridge_temp": 10,
}
config = BaseConfig | UpdateConfig

yoko1.SetVoltage(config["yokoVoltage"])
#
# print('starting scan: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
# time_required = np.sum((np.linspace(config["offset"], config["offset_end"],config["offset_num"]) + 2*config["max_pulse_length"])*config["shots"])*1e-6/60
# print("Time required is " + str(time_required) + " min")
# outerFolder = "Z:\\TantalumFluxonium\\Data\\2023_10_31_BF2_cooldown_6\\WTF\\TempChecks\\Yoko_" + str(
#     config["yokoVoltage_freqPoint"]) + "\\"
# Instance_TimeOfFlightPS = TimeOfFlightPS(path="TimeOfFlightPS_temp_"+str(config["fridge_temp"]), outerFolder=outerFolder, cfg=config,
#                                                soc=soc, soccfg=soccfg)
# data_TimeOfFlightPS = Instance_TimeOfFlightPS.acquire()
# data_TimeOfFlightPS = Instance_TimeOfFlightPS.processData(data_TimeOfFlightPS, save_all=False)
# Instance_TimeOfFlightPS.save_data(data_TimeOfFlightPS)
# Instance_TimeOfFlightPS.save_config()
# Instance_TimeOfFlightPS.display(data = data_TimeOfFlightPS, plotDisp=True, save_all=False)
# print('stopping scan: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
# SingleShotProgram.display(Instance_SingleShotProgram, data_SingleShot, plotDisp=True, save_fig=True)

### Run for different read_pulse_gain
len_vec = 6
read_pulse_gain_vec = np.linspace(5000,10000, len_vec, dtype=int)
print('starting scan: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
time_required = np.sum((np.linspace(config["offset"], config["offset_end"],config["offset_num"]) + 3*config["max_pulse_length"])*config["shots"])*1e-6*len_vec/60
print("Time required is " + str(time_required) + " min")
outerFolder = "Z:\\TantalumFluxonium\\Data\\2023_10_31_BF2_cooldown_6\\WTF\\TempChecks\\Yoko_" + str(
    config["yokoVoltage_freqPoint"]) + "\\"
for i in tqdm(range(len_vec)):
    config["read_pulse_gain"] = read_pulse_gain_vec[i]
    Instance_TimeOfFlightPS = TimeOfFlightPS(path="TimeOfFlightPS_temp_" + str(config["fridge_temp"]),
                                             outerFolder=outerFolder, cfg=config,
                                             soc=soc, soccfg=soccfg)
    data_TimeOfFlightPS = Instance_TimeOfFlightPS.acquire()
    data_TimeOfFlightPS = Instance_TimeOfFlightPS.processData(data_TimeOfFlightPS, save_all=False)
    Instance_TimeOfFlightPS.save_data(data_TimeOfFlightPS)
    Instance_TimeOfFlightPS.save_config()
    Instance_TimeOfFlightPS.display(data=data_TimeOfFlightPS, plotDisp=False, save_all=False)
print('stopping scan: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))