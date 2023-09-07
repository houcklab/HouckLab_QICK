"""
file to create basic initialization of things used for RFSOC This will include: 
- defining names for the attneuators
- defining yoko name
- defining the basic config dict that will state the channels used for all subsequent code
"""

### import relevent libraries
from socProxy import makeProxy, soc, soccfg
import h5py
from PythonDrivers.control_atten import setatten
from PythonDrivers.YOKOGS200 import *
import os
import visa
os.add_dll_directory(os.getcwd() + '\\PythonDrivers')

#### define a attenuator class to change define attenuators for the setup
class attenuator:
    def __init__(self, serialNum, attenuation_int= 50, print_int = True):
        self.serialNum = serialNum
        self.attenuation = attenuation_int
        setatten(attenu = attenuation_int, serial = self.serialNum, printv = print_int)

    def SetAttenuation(self, attenuation, printOut = False):
        self.attenuation = attenuation
        setatten(attenu = attenuation, serial = self.serialNum, printv = printOut)

# ##### define the attenuators
# cavityAtten = attenuator(27787)
# qubitAtten = attenuator(27797)

# ##### define yoko
# yoko1 = YOKOGS200(VISAaddress = 'GPIB0::5::INSTR', rm = visa.ResourceManager())
# yoko1.SetVoltage(-0.052)
# print("Voltage is ", yoko1.GetVoltage(), " Volts")


###### define default configuration
BaseConfig={"res_ch":0, # --Fixed
        "mixer_freq":0.0, # MHz
        "ro_chs":[0], # --Fixed
        "reps":1000, # --Fixed
        "nqz":1,
        "relax_delay":10, # --Fixed
        "res_phase":0, # --Fixed
        "pulse_style": "const", # --Fixed
        "length": soc.us2cycles(5), # [Clock ticks]
        # Try varying length from 10-100 clock ticks
        "pulse_gain":30000, # [DAC units]
        # Try varying pulse_gain from 500 to 30000 DAC units
        "pulse_freq": 893, # [MHz]
        # In this program the signal is up and downconverted digitally so you won't see any frequency
        # components in the I/Q traces below. But since the signal gain depends on frequency,
        # if you lower pulse_freq you will see an increased gain.
        "adc_trig_offset": soc.us2cycles(0.468-0.02), # [Clock ticks]
        # Try varying adc_trig_offset from 100 to 220 clock ticks
       }

#### define function to combine dictions and use the updated definitions