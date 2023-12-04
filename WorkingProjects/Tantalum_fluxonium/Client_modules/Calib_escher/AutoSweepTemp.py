import os
import time

path = os.getcwd()
os.add_dll_directory(os.path.dirname(path) + '\\PythonDrivers')
import WorkingProjects.Tantalum_fluxonium.Client_modules.PythonDrivers.LS370 as lk
import pyvisa
import datetime

from WorkingProjects.Tantalum_fluxonium.Client_modules.Calib_escher.initialize import *

### Set up the Lakeshore
rm = pyvisa.ResourceManager()
LS370_connection = rm.open_resource('GPIB0::12::INSTR')
lakeshore = lk.Lakeshore370(LS370_connection)

### Defining temperature sweep configuration
tempr_cfg = {
    'tempr_list': [15, 30, 50, 60, 50, 30, 10],  # [in mK]
    'wait_time': 15 * 60,  # [in seconds]
}

### Defining common experiment configurations
UpdateConfig = {
    ##### set yoko
    "yokoVoltage": -0.22,  # [in V]
    "yokoVoltage_freqPoint": -0.22,  # [in V] used for naming the file systems
    ###### cavity
    "reps": 2000,  # placeholder for reps. Cannot be undefined
    "read_pulse_style": "const",
    "read_length": 10,  # [in us]
    "read_pulse_gain": 9000,  # [in DAC units]
    "read_pulse_freq": 7392.357,  # [in MHz]
    ##### qubit spec parameters
    "qubit_pulse_style": "arb",
    "qubit_gain": 0,  # [in DAC Units]
    "sigma": 0.005,  # [in us]
    "qubit_freq": 495,  # [in MHz]
    "relax_delay": 1000,  # [in us] : Will keep on getting updated
}
config = BaseConfig | UpdateConfig

for i in range(len(tempr_cfg["tempr_list"])):
    ## Set temperature and wait for 'wait_time' for the fridge to thermalize
    # TODO : Generalize the wait_time for hot and cold thermalize
    lakeshore.set_temp(tempr_cfg["tempr_list"][i])
    time.sleep(tempr_cfg["wait_time"])
    # Update temperature in the config file
    UpdateConfig = {
        "fridge_temp": tempr_cfg["tempr_list"][i],
    }
    config = config | UpdateConfig

    ## Measure T1


# Turn off the heater with lakeshore
lakeshore.set_setpoint(5)
lakeshore.set_heater_range(0)
time.sleep(60)
