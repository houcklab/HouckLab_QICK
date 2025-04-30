"""
file to create basic initialization of things used for RFSOC This will include: 
- defining names for the attenuators
- defining yoko name
- defining spirack and D5aModule
- defining the basic config dict that will state the channels used for all subsequent code
"""

from WorkingProjects.Inductive_Coupler.Client_modules.socProxy import makeProxy, soc, soccfg
import os
import platform

if 'macOS' in platform.platform():
    if "LD_LIBRARY_PATH" in os.environ.keys():
        os.environ["LD_LIBRARY_PATH"] += ":.\..\\PythonDrivers"
    else:
        os.environ["LD_LIBRARY_PATH"] = ".\..\\PythonDrivers"
else:
    os.add_dll_directory(os.getcwd() + '\\..\\PythonDrivers')


#Define Save folder
outerFolder = "Z:\QSimMeasurements\Measurements\\4Q_Test_Scalinq\\"


###### define default configuration
BaseConfig = {
    "res_ch": 6,  # --Fixed
    "qubit_ch": 4,  # --Fixed
    "mixer_freq": 7200,  # MHz
    "ro_chs": [0, 1],  # --Fixed
    "reps": 1000,  # --Fixed
    "nqz": 1, #1,  #### refers to cavity
    "qubit_nqz": 2,
    "relax_delay": 200,  # --Fixed
    "res_phase": 0,  # --Fixed
    "pulse_style": "const",  # --Fixed
    "length": 20,  # length of cavity pulse for readout in us
    "pulse_gain": 30000,  # [DAC units]
    "adc_trig_offset": 0.5,  # [us]
    # Try varying adc_trig_offset from 100 to 220 clock ticks
    "cavity_LO": 6.8e9,  #in Hz

    # "cavity_winding_freq": 1.0903695,
    # 'cavity_winding_offset': -15.77597
}
FF_channel1 = 0
FF_channel2 = 1
FF_channel3 = 2
FF_channel4 = 3

FF_channel1 = 3
FF_channel2 = 2
FF_channel3 = 0
FF_channel4 = 1

FF_Qubits = {
    str(1): {'channel': FF_channel1, 'delay_time': 0.005},
    str(2): {'channel': FF_channel2, 'delay_time': 0.00},
    str(3): {'channel': FF_channel3, 'delay_time': 0.002},
    str(4): {'channel': FF_channel4, 'delay_time': 0.00},
}



# FF_Qubits = {
#     str(1): {'channel': FF_channel1, 'delay_time': 0.002},
#     str(2): {'channel': FF_channel2, 'delay_time': 0.00},
#     str(3): {'channel': FF_channel3, 'delay_time': 0.000},
#     str(4): {'channel': FF_channel4, 'delay_time': 0.00},
# }

Additional_Delays = {
    str(1): {'channel': 4, 'delay_time': 0}
}

BaseConfig["Additional_Delays"] = Additional_Delays