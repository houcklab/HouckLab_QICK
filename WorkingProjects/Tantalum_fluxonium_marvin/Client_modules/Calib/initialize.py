"""
file to create basic initialization of things used for RFSOC This will include: 
- defining names for the attneuators
- defining yoko name
- defining the basic config dict that will state the channels used for all subsequent code
"""

# import relevent libraries
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.CoreLib.socProxy import *
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.PythonDrivers.YOKOGS200 import *
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.PythonDrivers.mlbf_driver import *
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.PythonDrivers.control_atten import *
import os
import pyvisa as visa

path = r'C:\Users\pjatakia\Documents\GitHub\HouckLab_QICK\WorkingProjects\Tantalum_fluxonium_marvin\Client_modules\PythonDrivers'
os.add_dll_directory(os.path.dirname(path) + '\\PythonDrivers')

# TITLE : Hardware to connect to
is_cavity_atten = False
is_qubit_atten = False
is_yoko1 = True
is_yoko2 = False
is_mlbf_filter = True

# TITLE : Connect to Attenuator
if is_cavity_atten:
    cavity_atten = attenuator(27787)
if is_qubit_atten:
    qubit_atten = attenuator(27797)

# TITLE: Connect to Yoko
if is_yoko1:
    yoko1 = YOKOGS200(VISAaddress='GPIB1::5::INSTR', rm=visa.ResourceManager())
    #yoko1 = YOKOGS200(VISAaddress= 'USB::0xB21::0x39::91PB12678', rm=visa.ResourceManager())
    #yoko1 = YOKOGS200(VISAaddress='GPIB1::2::INSTR', rm=visa.ResourceManager()) # HC yoko
    yoko1.SetMode('voltage')
if is_yoko2:
    yoko2 = YOKOGS200(VISAaddress = 'GPIB1::5::INSTR', rm = visa.ResourceManager())
    yoko2.SetMode('voltage')

# TITLE: Connect to MLBF
if is_mlbf_filter:
    mlbf_filter = MLBFDriver("192.168.1.10")


# TITLE : default configuration
BaseConfig = {
    "res_ch": 0,  # --Fixed
    "qubit_ch": 1,  # --Fixed
    "mixer_freq": 0.0,  # MHz
    "ro_chs": [0],  # --Fixed
    "reps": 1000,  # --Fixed
    "nqz": 2,  #### refers to cavity
    "mode_periodic": False,
    "qubit_nqz": 1,
    "relax_delay": 10,  # us
    "res_phase": 0,  # --Fixed
    "pulse_style": "const",  # --Fixed
    "read_length": 5,  # units us, previously this was just names "length"
    # Try varying length from 10-100 clock ticks
    "pulse_gain": 30000,  # [DAC units]
    # Try varying pulse_gain from 500 to 30000 DAC units
    "pulse_freq": 0.0,  # [MHz]
    # In this program the signal is up and downconverted digitally so you won't see any frequency
    # components in the I/Q traces below. But since the signal gain depends on frequency,
    # if you lower pulse_freq you will see an increased gain.
    "adc_trig_offset": 0.530,  # Try varying adc_trig_offset from 100 to 220 clock ticks
    "cavity_LO": 0.0,

    # switch parameters
    "trig_buffer_start": 0.035,  # in us
    "trig_buffer_end": 0.024,  # in us
    "trig_delay": 0.07,  # in us

}
