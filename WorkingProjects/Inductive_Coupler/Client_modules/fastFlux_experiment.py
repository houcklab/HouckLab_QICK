from mLoopback import Loopback
from mTransmission import Transmission
import matplotlib.pyplot as plt
from socProxy import makeProxy, soc, soccfg
import h5py
import PythonDrivers.YOKOGS200 as YOKOGS200
import os
os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
from WorkingProjects.Inductive_Coupler.Client_modules.initialize import *
from WorkingProjects.Inductive_Coupler.Client_modules.mfastFlux import *

FF_channel1 = 1 #4 is middle qubit, 6 is left qubit
FF_channel2 = 2 #4 is middle qubit, 6 is left qubit
FF_channel3 = 3 #4 is middle qubit, 6 is left qubit

FF_gain1 = 30000 * 0
FF_gain2 = 30000 * 1
FF_gain3 = 30000 * 0


config={
    "reps": 2000,  # this will used for all experiements below unless otherwise changed in between trials
    "ff_pulse_style": "const", # --Fixed
    "ff_length": 0.05, # [us]
    "ff_freq": 0, # [MHz] actual frequency is this number + "cavity_LO"
    ##### define tranmission experiment parameters
    "ff_nqz": 1, ### MHz, span will be center+/- this parameter
    "relax_delay": 0.15, ### number of points in the transmission frequecny
    "ff_ch": 4, #### cavity attenuator attenuation value
    "soft_avgs": 50000,
    "FF_list_readout": [(FF_channel1, FF_gain1),
    (FF_channel2, FF_gain2), (FF_channel3, FF_gain3)]
}

prog = LoopbackProgramFastFlux(soccfg, config)
prog.acquire_decimated(soc, load_pulses=True, progress=False)