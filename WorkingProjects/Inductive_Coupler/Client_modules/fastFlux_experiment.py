from mLoopback import Loopback
from mTransmission import Transmission
import matplotlib.pyplot as plt
from socProxy import makeProxy, soc, soccfg
import h5py
from PythonDrivers.control_atten import setatten
import PythonDrivers.YOKOGS200 as YOKOGS200
import os
os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
from q4diamond.Client_modules.initialize import *
from q4diamond.Client_modules.mfastFlux import *

FF_channel1 = 0 #4 is middle qubit, 6 is left qubit
FF_channel2 = 1 #4 is middle qubit, 6 is left qubit
FF_channel3 = 2 #4 is middle qubit, 6 is left qubit

FF_gain1 = 0
FF_gain2 = 0
FF_gain3 = 20000


config={
    "reps": 2000,  # this will used for all experiements below unless otherwise changed in between trials
    "ff_pulse_style": "const", # --Fixed
    "ff_length": 0.05, # [us]
    "ff_freq": 0, # [MHz] actual frequency is this number + "cavity_LO"
    ##### define tranmission experiment parameters
    "ff_nqz": 1, ### MHz, span will be center+/- this parameter
    "relax_delay": 100, ### number of points in the transmission frequecny
    "ff_ch": 4, #### cavity attenuator attenuation value
    "soft_avgs": 20000,
    "FF_list_readout": [(FF_channel1, FF_gain1),
    (FF_channel2, FF_gain2), (FF_channel3, FF_gain3)]
}

prog = LoopbackProgramFastFlux(soccfg, config)
prog.acquire_decimated(soc, load_pulses=True, progress=False)