"""
file to create basic initialization of things used for RFSOC This will include:
- defining names for the variable attneuators
- defining yoko name
- defining the basic config dict that will state the channels used for all subsequent code

NOTE: this file is intended as a template on how to structure the initialize
file. In order to use this file, you will need to update various parameters
including the varible attenutor and yoko addresses (if you have those in your
setup, by default those are commented out here). As well the BaseConfig dict
needs to be adjusted to reflect the individual setup
"""

### import relevent libraries
from MasterProject.Client_modules.CoreLib.socProxy import makeProxy
from MasterProject.Client_modules.PythonDrivers.YOKOGS200 import YOKOGS200
import os
import pyvisa as visa
from pathlib import Path


# Get the directory of the current Python script
script_directory = os.path.dirname(os.path.realpath(__file__))
script_parent_directory = os.path.dirname(script_directory)
try:
    os.add_dll_directory(os.path.join(script_parent_directory, 'PythonDrivers'))
except AttributeError:
    os.environ["PATH"] = script_parent_directory + '\\PythonDrivers' + ";" + os.environ["PATH"]


#### define a attenuator class to change define attenuators for the setup
class attenuator:
    def __init__(self, serialNum, attenuation_int= 50, print_int = True):
        self.serialNum = serialNum
        self.attenuation = attenuation_int
        setatten(attenu = attenuation_int, serial = self.serialNum, printv = print_int)

    def SetAttenuation(self, attenuation, printOut = False):
        self.attenuation = attenuation
        setatten(attenu = attenuation, serial = self.serialNum, printv = printOut)

# ##### define the varible attenuators
# Atten_address = 27797
# Atten = attenuator(Atten_address)
#
# ##### define yoko
# yoko_GPIB = 'GPIB0::2::INSTR'
# yoko1 = YOKOGS200(VISAaddress = yoko_GPIB, rm = visa.ResourceManager())
# yoko1.SetMode('voltage')


###### define default configuration
BaseConfig={
        "res_ch": 0, # --Fixed
        "qubit_ch": 1,  # --Fixed
        "mixer_freq":0.0, # MHz
        "ro_chs":[0] , # --Fixed
        "reps":1000, # --Fixed
        "nqz": 2, #### refers to cavity
        "qubit_nqz": 2,
        "relax_delay":10, # us
        "res_phase":0, # --Fixed
        "pulse_style": "const", # --Fixed
        "read_length": 5, # units us, previously this was just names "length"
        # Try varying length from 10-100 clock ticks
        "pulse_gain":30000, # [DAC units]
        # Try varying pulse_gain from 500 to 30000 DAC units
        "pulse_freq": 0.0, # [MHz]
        # In this program the signal is up and downconverted digitally so you won't see any frequency
        # components in the I/Q traces below. But since the signal gain depends on frequency,
        # if you lower pulse_freq you will see an increased gain.
        "adc_trig_offset": 0.468+0.02, #+ 1, #soc.us2cycles(0.468-0.02), # [Clock ticks]
        # Try varying adc_trig_offset from 100 to 220 clock ticks
        "cavity_LO": 0.0,
       }
