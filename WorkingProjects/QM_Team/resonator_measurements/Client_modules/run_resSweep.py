from mResSweep import *
from socProxy import makeProxy
import h5py
from PythonDrivers.control_atten import setatten
# import PythonDrivers.YOKOGS200 as YOKOGS200
import os
savePath = r'Z:\t1Team\Data\TALE02_06_16_22\RFSOC\freqDomain'

# Python 3.7
# os.environ['PATH'] = os.getcwd() + '\\PythonDrivers' + os.pathsep + os.environ['PATH']
# Python 3.8 and newer
os.add_dll_directory(os.getcwd() + '\\PythonDrivers')

# create proxy to ZCU216 board
soc, soccfg = makeProxy('192.168.1.120')
print(soccfg)

input = {}
input['LO_f'] = 5e3  # local oscillator frequency

# for spectrum analyzer shots
# input['mixerCenter_f'] = 1700  # center frequency for the mixer
# input['span_f'] = 0  # frequency span to sweep over. The same for all resonators
# input['res_f'] = [5.9e3, 6.411658e3, 7.05506e3, 7.5e3]  # center frequencies of the resonators

#frequencies for large span measurement
# input['LO_f'] = 0e3  # local oscillator frequency
# input['mixerCenter_f'] = 1.5e3  # center frequency for the mixer
# input['span_f'] = 1000  # frequency span to sweep over. The same for all resonators
# input['res_f'] = [1.5e3]  # center frequencies of the resonators

# define frequencies
input['mixerCenter_f'] = 1700  # center frequency for the mixer
input['span_f'] = .06  # frequency span to sweep over. The same for all resonators
# input['res_f'] = [6.1477131e3, 6.5812862e3, 7e3, 7.5e3]  # center frequencies of the resonators
input['res_f'] = [6.49275e3, 6.643545e3, 7e3, 7.5e3]  # center frequencies of the resonators

# define numbers of points
input['n_expts'] = 301  # number of points along the frequency axis
input['n_rounds'] = 1  # number of times to sweep along the frequency axis
input['n_reps'] = 200  # number of repetitions to take at each frequency point

# timing. Units are clock cycles, but converted from us
input['ring_up_time'] = 500  # time waiting for the resonator to ring up at the start of each sweep
input['ring_between_time'] = 50  # time waiting for the resonator to ring up at the start of each sweep
input['readout_length'] = 1000  # time to average over
input['adc_trig_offset'] = 0.1  # time after the DAC starts the final steady pulse before the ADC starts it's read

# power
input['basePower'] = 0
input['attenList'] = [0]
input['attenSerial'] = [27712, 27784]
input['gain'] = [0.35, 0.35, 0, 0]

# Acquire decimated
# decimatedInstance = ResSweep(path="dataResSweep", input=input, cfg=config, soc=soc, soccfg=soccfg)
# data = ResSweep.acquire_decimated(decimatedInstance)
# ResSweep.display_decimated(decimatedInstance, data)

# Acquire
input['power'] = input['basePower']
Instance = ResSweep(path=savePath, prefix='data', input=input, soc=soc, soccfg=soccfg)
data = ResSweep.acquire(Instance)
ResSweep.display(Instance, data)
ResSweep.save_data(Instance, data)
