"""
file to create basic initialization of things used for RFSOC This will include: 
- defining names for the attenuators
- defining spirack and D5aModule
- defining the basic config dict that will state the channels used for all subsequent code
"""

### import relevent libraries
from WorkingProjects.tProc_V2.socProxy import makeProxy, soc, soccfg
import os
import platform
# if 'macOS' not in platform.platform():
    # import visa
    # from WorkingProjects.Inductive_Coupler.Client_modules.PythonDrivers.control_atten import setatten
    # from WorkingProjects.Inductive_Coupler.Client_modules.PythonDrivers.YOKOGS200 import *

# if 'macOS' in platform.platform():
#     if "LD_LIBRARY_PATH" in os.environ.keys():
#         os.environ["LD_LIBRARY_PATH"] += r":.\..\..\\PythonDrivers"
#     else:
#         os.environ["LD_LIBRARY_PATH"] = r".\..\..\\PythonDrivers"
# else:
#     os.add_dll_directory(os.getcwd() + r'.\..\..\\PythonDrivers')

# if 'macOS' not in platform.platform():
#     #### define a attenuator class to change define attenuators for the setup
#     class attenuator:
#         def __init__(self, serialNum, attenuation_int=50, print_int=False):
#             self.serialNum = serialNum
#             self.attenuation = attenuation_int
#             setatten(attenu=attenuation_int, serial=self.serialNum, printv=print_int)
#
#         def SetAttenuation(self, attenuation, printOut=False):
#             self.attenuation = attenuation
#             setatten(attenu=attenuation, serial=self.serialNum, printv=printOut)
#
#
#     # ##### define the attenuators
#     cavityAtten = attenuator(27786)
#     qubitAtten = attenuator(27796)  ####*********CHECK THIS****####


#Define Save folder
outerFolder = r"Z:\QSimMeasurements\Measurements\RFSOC_tProcV2_test\\"

###### define default configuration
BaseConfig = {
    "res_ch": 4,  # --Fixed
    "qubit_ch": 5,  # --Fixed
    "mixer_freq": 0, # 7200,  # MHz
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
    "cavity_LO": 6.50e9,  #in Hz
    "cavity_winding_freq": 1.0903695,
    'cavity_winding_offset': -15.77597
}
FF_channel1 = 8
FF_channel2 = 9
FF_channel3 = 10
FF_channel4 = 11
# FF_channel5 = 12
# FF_channel6 = 13
# FF_channel7 = 14
# FF_channel8 = 15



FF_Qubits = {
    str(1): {'channel': FF_channel1, 'delay_time': 0.005},
    str(2): {'channel': FF_channel2, 'delay_time': 0.00},
    str(3): {'channel': FF_channel3, 'delay_time': 0.002},
    str(4): {'channel': FF_channel4, 'delay_time': 0.00},
}


Additional_Delays = {
    str(1): {'channel': 4, 'delay_time': 0}
}

BaseConfig["Additional_Delays"] = Additional_Delays