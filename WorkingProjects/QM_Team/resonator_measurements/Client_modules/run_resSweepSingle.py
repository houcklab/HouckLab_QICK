from mResSweepSingle import *
from socProxy import makeProxy
import h5py
from PythonDrivers.control_atten import setatten
# import PythonDrivers.YOKOGS200 as YOKOGS200
import os
savePath = r'C:\Users\my\Documents\GitHub\ZCU216_Russell\res_dev\Client_modules\dataResSweep'

# Python 3.7
# os.environ['PATH'] = os.getcwd() + '\\PythonDrivers' + os.pathsep + os.environ['PATH']
# Python 3.8 and newer
os.add_dll_directory(os.getcwd() + '\\PythonDrivers')

# Only run this if no proxy already exists
soc, soccfg = makeProxy('192.168.1.117')
print(soccfg)

input = {}
# input['res_f'] = [8.5e3, 7e3, 7.8059e3, 7.310015e3]  # center frequencies of the resonators
# input['res_f'] = [i-0.84 for i in input['res_f']]
# for spectrum analyzer shots
# input['mixerCenter_f'] = 1700  # center frequency for the mixer
# input['span_f'] = 0  # frequency span to sweep over. The same for all resonators
# input['res_f'] = [6.148e3, 6.581e3, 7e3, 7.5e3]  # center frequencies of the resonators

#frequencies for large span measurement
# input['LO_f'] = 0e3  # local oscillator frequency
# input['mixerCenter_f'] = 1.5e3  # center frequency for the mixer
# input['span_f'] = 1000  # frequency span to sweep over. The same for all resonators
# input['res_f'] = [1.5e3]  # center frequencies of the resonators

# define frequencies
input['LO_f'] = 5e3  # local oscillator frequency
input['mixerCenter_f'] = 1700  # center frequency for the mixer
input['span_f'] = .03  # frequency span to sweep over. The same for all resonators
# input['span_f'] = .0  # frequency span to sweep over. The same for all resonators
input['res_f'] = 6.401658e3  # center frequencies of the resonators
# input['res_f'] = [5.9e3, 6.401658e3, 7.14506e3, 7.5e3]  # center frequencies of the resonators
# input['span_f'] = 0.03  # frequency span to sweep over. The same for all resonators
# input['res_f'] = [6.49275e3, 6e3, 7e3, 7.5e3]  # center frequencies of the resonators

# define numbers of points
input['n_expts'] = 60  # number of points along the frequency axis
input['n_rounds'] = 1  # number of times to sweep along the frequency axis
input['n_reps'] = 200 # number of repetitions to take at each frequency point

# timing. Units are clock cycles, but converted from us
input['ring_up_time'] = 50  # time waiting for the resonator to ring up at the start of each sweep
input['ring_between_time'] = 5  # time waiting for the resonator to ring up at the start of each sweep
input['readout_length'] = 10  # time to average over
input['adc_trig_offset'] = 0.1
# input['relax_delay'] = soc.us2cycles(1)

# power
input['basePower'] = -30
input['attenList'] = [0]
input['attenSerial'] = []
# input['gain'] = [1, 0, 0, 0]
input['gain'] = 1
# input['gain'] = [1, 0.35, 0.6, 1]
# input['gain'] = [0, 0.7, 0, 0]
# input['gain'] = [0.03, 0.016, 0, 0]

# Acquire decimated
# decimatedInstance = ResSweep(path="dataResSweep", input=input, cfg=config, soc=soc, soccfg=soccfg)
# data = ResSweep.acquire_decimated(decimatedInstance)
# ResSweep.display_decimated(decimatedInstance, data)

# Acquire
Instance = ResSweep(path=savePath, input=input, soc=soc, soccfg=soccfg)
data = ResSweep.acquire(Instance)
ResSweep.display(Instance, data)
ResSweep.save_data(Instance, data)
