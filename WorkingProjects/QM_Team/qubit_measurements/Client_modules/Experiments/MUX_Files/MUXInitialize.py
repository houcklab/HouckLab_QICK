"""
file to create basic initialization of things used for RFSOC This will include: 
- defining names for the attenuators
- defining yoko name
- defining spirack and D5aModule
- defining the basic config dict that will state the channels used for all subsequent code
"""

### import relevent libraries
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.CoreLib.socProxy import *
import os
import platform
# if 'macOS' not in platform.platform():
    # import visa
    # from WorkingProjects.Inductive_Coupler.Client_modules.PythonDrivers.control_atten import setatten
    # from WorkingProjects.Inductive_Coupler.Client_modules.PythonDrivers.YOKOGS200 import *

BaseConfig = {
    "res_ch": 6,  # --Fixed
    "qubit_ch": 1,  # --Fixed
    "mixer_freq": 0.0,  # MHz
    "ro_chs": [0],  # --Fixed
    "reps": 1000,  # --Fixed
    "nqz": 2, #1,  #### refers to cavity
    "qubit_nqz": 1,
    "relax_delay": 3000,  # --Fixed
    "res_phase": 0,  # --Fixed
    "pulse_style": "const",  # --Fixed
    "length": 30,  # [Clock ticks]
    "pulse_gain": 30000,  # [DAC units]
    "adc_trig_offset": 1,  # [us]
    # Try varying adc_trig_offset from 100 to 220 clock ticks
    "cavity_LO": 0, #6.5e9
    # "cavity_winding_freq": 0.45917414, #1.0903695 * 0,
    # 'cavity_winding_offset': -32.10723885 + np.pi #-15.77597 * 0
    "cavity_winding_freq": 0,
    'cavity_winding_offset': 0
}
FF_channel1 = 0
FF_channel2 = 1
FF_channel3 = 2
FF_channel4 = 3


FF_Qubits = {
    str(1): {'channel': FF_channel1, 'delay_time': 0.017 + 0.0045},
    str(2): {'channel': FF_channel2, 'delay_time': 0},
    str(3): {'channel': FF_channel3, 'delay_time': 0},
    str(4): {'channel': FF_channel4, 'delay_time': 0},
}