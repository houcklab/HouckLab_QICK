"""
file to create basic initialization of things used for RFSOC This will include: 
- defining names for the attenuators
- defining yoko name
- defining the basic config dict that will state the channels used for all subsequent code
"""

### import relevent libraries
from WorkingProjects.Inductive_Coupler.Client_modules.socProxy import makeProxy, soc, soccfg
import h5py
import os
import platform
if 'macOS' not in platform.platform():
    import visa
    from WorkingProjects.Inductive_Coupler.Client_modules.PythonDrivers.YOKOGS200 import *

if 'macOS' in platform.platform():
    if "LD_LIBRARY_PATH" in os.environ.keys():
        os.environ["LD_LIBRARY_PATH"] += ":.\..\\PythonDrivers"
    else:
        os.environ["LD_LIBRARY_PATH"] = ".\..\\PythonDrivers"
else:
    # os.add_dll_directory(os.getcwd() + '.\..\\PythonDrivers')
    os.add_dll_directory(os.getcwd() + '.\\PythonDrivers')


if 'macOS' not in platform.platform():
    #### define a attenuator class to change define attenuators for the setup
    class attenuator:
        def __init__(self, serialNum, attenuation_int=50, print_int=False):
            self.serialNum = serialNum
            self.attenuation = attenuation_int

        def SetAttenuation(self, attenuation, printOut=False):
            self.attenuation = attenuation


    # ##### define the attenuators
    cavityAtten = attenuator(27786)
    qubitAtten = attenuator(27796)  ####*********CHECK THIS****####

    # ##### define yoko
    # yoko69 = YOKOGS200(VISAaddress='GPIB0::1::INSTR', rm=visa.ResourceManager())
    # yoko70 = YOKOGS200(VISAaddress='GPIB0::2::INSTR', rm=visa.ResourceManager())
    # yoko71 = YOKOGS200(VISAaddress='GPIB0::3::INSTR', rm=visa.ResourceManager())
    # yoko72 = YOKOGS200(VISAaddress='GPIB0::4::INSTR', rm=visa.ResourceManager())

# yoko1 = YOKOGS200(VISAaddress = 'GPIB0::5::INSTR', rm = visa.ResourceManager())
# yoko1.SetVoltage(-0.052)
# print("Voltage is ", yoko1.GetVoltage(), " Volts")

#Define saving path
outerFolder = "Z:\Jeronimo\Measurements\RFSOC_4Qubit_0F\\"

###### define default configuration
BaseConfig = {
    "res_ch": 0,  # --Fixed
    "qubit_ch": 2,  # --Fixed
    "mixer_freq": 0.0,  # MHz
    "ro_chs": [0],  # --Fixed
    "reps": 1000,  # --Fixed
    "nqz": 2, #1,  #### refers to cavity
    "qubit_nqz": 2,
    "relax_delay": 150,  # --Fixed
    "res_phase": 0,  # --Fixed
    "pulse_style": "const",  # --Fixed
    "length": 7,  # [Clock ticks]
    "pulse_gain": 30000,  # [DAC units]
    "adc_trig_offset": 0.5,  # [us]
    # Try varying adc_trig_offset from 100 to 220 clock ticks
    "cavity_LO": 0, #6.5e9
    # "cavity_winding_freq": 0.45917414, #1.0903695 * 0,
    # 'cavity_winding_offset': -32.10723885 + np.pi #-15.77597 * 0
    "cavity_winding_freq": 1.0903695,
    'cavity_winding_offset': -15.77597
}
FF_channel1 = 1
FF_channel2 = 4
FF_channel3 = 6
FF_channel4 = 5

# FF_Qubits = {
#     str(1): {'channel': FF_channel1, 'delay_time': 0.017},
#     str(2): {'channel': FF_channel2, 'delay_time': 0},
#     str(3): {'channel': FF_channel3, 'delay_time': 0},
#     str(4): {'channel': FF_channel4, 'delay_time': 0},
# }

FF_Qubits = {
    str(1): {'channel': FF_channel1, 'delay_time': 0.017 + 0.0045},
    str(2): {'channel': FF_channel2, 'delay_time': 0},
    str(3): {'channel': FF_channel3, 'delay_time': 0},
    str(4): {'channel': FF_channel4, 'delay_time': 0},
}