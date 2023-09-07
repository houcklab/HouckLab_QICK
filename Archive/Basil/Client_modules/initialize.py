"""
file to create basic initialization of things used for RFSOC This will include: 
- defining names for the attneuators
- defining yoko name
- defining the basic config dict that will state the channels used for all subsequent code
"""

### import relevent libraries
from Basil.Client_modules.socProxy import makeProxy, soc, soccfg
import h5py
import visa
from Basil.Client_modules.PythonDrivers.control_atten import setatten
from Basil.Client_modules.PythonDrivers.YOKOGS200 import *
import os
os.add_dll_directory(os.getcwd() + '.\..\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')

###### define default configuration
BaseConfig={
        "res_ch":0, # --Fixed
        "qubit_ch": 2,  # --Fixed
        "mixer_freq":0.0, # MHz
        "ro_chs":[0], # --Fixed
        "reps":1000, # --Fixed
        "nqz":1, #### refers to cavity
        "qubit_nqz": 2,
        "relax_delay":150, # --Fixed
        "res_phase":0, # --Fixed
        "pulse_style": "const", # --Fixed
        "length": 10, # [Clock ticks]
        "pulse_gain":30000, # [DAC units]
        "adc_trig_offset": 0.5, # [Clock ticks]
        # Try varying adc_trig_offset from 100 to 220 clock ticks
        "cavity_LO": 7e9
       }

