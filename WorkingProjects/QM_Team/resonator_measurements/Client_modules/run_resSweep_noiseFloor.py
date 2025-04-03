from mResSweep_noiseFloor import *
from socProxy import makeProxy
import h5py
from PythonDrivers.control_atten import setatten
# import PythonDrivers.YOKOGS200 as YOKOGS200
import os

# Python 3.7
# os.environ['PATH'] = os.getcwd() + '\\PythonDrivers' + os.pathsep + os.environ['PATH']
# Python 3.8 and newer
os.add_dll_directory(os.getcwd() + '\\PythonDrivers')

# Only run this if no proxy already exists
soc, soccfg = makeProxy('192.168.1.103')
print(soccfg)

input = {}
input['LO_f'] = 5e3  # local oscillator frequency
# input['mixerCenter_f'] = 1461.9975  # center frequency for the mixer
# input['span_f'] = 0.015  # frequency span to sweep over. The same for all resonators

# for spectrum analyzer shots
input['mixerCenter_f'] = 1450  # center frequency for the mixer
input['span_f'] = 0.005  # frequency span to sweep over. The same for all resonators

input['res_f'] = [5.9749294e3, 6.281788e3, 6.85059e3, 7.310013e3]  # center frequencies of the resonators
# input['res_f'] = [i-0.84 for i in input['res_f']]



# define numbers of points
input['n_expts'] = 101  # number of points along the frequency axis
input['n_rounds'] = 2000  # number of times to sweep along the frequency axis
input['n_reps'] = 1000  # number of repetitions to take at each frequency point

# timing. Units are clock cycles, but converted from us
input['ring_up_time'] = soc.us2cycles(2000)  # time waiting for the resonator to ring up at the start of each sweep
input['ring_between_time'] = soc.us2cycles(20)  # time to wait between adjacent frequency points
input['readout_length'] = soc.us2cycles(2)  # time to average over
input['relax_delay'] = soc.us2cycles(1)  # time to wait between the end of the readout and moving to the next frequency point

# power
input['basePower'] = -80
input['attenList'] = [0]
input['attenSerial'] = []

config = {"res_ch": 6,  # --Fixed
          "ro_chs": [0, 1, 2, 3],  # --Fixed
          "pulse_style": "const",  # --Fixed
          "length": 2 ** 31 - 1,  # [Clock ticks]
          }

# Acquire decimated
decimatedInstance = ResSweep(path="dataResSweep", input=input, cfg=config, soc=soc, soccfg=soccfg)
data = ResSweep.acquire_decimated(decimatedInstance)
ResSweep.display_decimated(decimatedInstance, data)
# ResSweep.save_data(decimatedInstance, data)

# Acquire
Instance = ResSweep(path="dataResSweep", input=input, cfg=config, soc=soc, soccfg=soccfg)
data = ResSweep.acquire(Instance)
ResSweep.display(Instance, data)
ResSweep.save_data(Instance, data)



# Look at a data file
with h5py.File(Instance.fname, "r") as f:
    # List all groups
    print("Keys: %s" % f.keys())
    a_group_key = list(f.keys())[0]
    # Get the data
    data = list(f[a_group_key])
    print("Viewing data file")