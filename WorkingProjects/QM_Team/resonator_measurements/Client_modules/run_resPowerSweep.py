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
# input['mixerCenter_f'] = 1700  # center frequency for the mixer
# input['span_f'] = .08  # frequency span to sweep over. The same for all resonators
# input['res_f'] = [5.9e3, 6.401658e3, 7.04506e3, 7.5e3]  # center frequencies of the resonators

# define frequencies
input['mixerCenter_f'] = 1700  # center frequency for the mixer
input['span_f'] = .02  # frequency span to sweep over. The same for all resonators
# input['res_f'] = [6.1477131e3, 6.5812862e3, 7e3, 7.5e3]  # center frequencies of the resonators
input['res_f'] = [6.49275e3, 6.643545e3, 7e3, 7.5e3]  # center frequencies of the resonators

# define numbers of points
input['n_expts'] = 451  # number of points along the frequency axis

# timing. Units are clock cycles, but converted from us
input['ring_up_time'] = 500  # time waiting for the resonator to ring up at the start of each sweep
input['ring_between_time'] = 50  # time waiting for the resonator to ring up at the start of each sweep
input['adc_trig_offset'] = 0.1  # time after the DAC starts the final steady pulse before the ADC starts it's read

# power
input['basePower'] = 0
input['attenSerial'] = [27712, 27784]
# input['gain'] = [1, 0.7, 0, 0]
input['gain'] = [0.35, 0.35, 0, 0]

# parameters which vary per power point
# input['attenList'] = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
# input['readout_lengthList'] = [1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000]  # time to average over
# input['n_roundsList'] = [2, 2, 2, 2, 2, 4, 8, 10, 10, 10]  # number of times to sweep along the frequency axis
# input['n_repsList'] = [200, 200, 200, 200, 200, 500, 1000, 2000, 2000, 4000] # number of repetitions to take at each frequency point

input['attenList'] = [0]
input['readout_lengthList'] = [1000]  # time to average over
input['n_roundsList'] = [2]  # number of times to sweep along the frequency axis
input['n_repsList'] = [100] # number of repetitions to take at each frequency point


# Acquire
for i, atten in enumerate(input['attenList']):
    # update per power parameters
    input['power'] = input['basePower']-atten
    input['n_rounds'] = input['n_roundsList'][i]
    input['n_reps'] = input['n_repsList'][i]
    input['readout_length'] = input['readout_lengthList'][i]

    # set attenuation. Split it evenly across all attenuators
    # NOTE: What happens if we average to somewhere between the resolution of the attenuators? Possible issue
    for serial in input['attenSerial']:
        setatten(atten/len(input['attenSerial']), serial, printv=True)

    # run a frequency sweep
    Instance = ResSweep(path=savePath, prefix='data_p'+str(input['power']), input=input, soc=soc, soccfg=soccfg)
    data = ResSweep.acquire(Instance)
    ResSweep.display(Instance, data)
    ResSweep.save_data(Instance, data)
