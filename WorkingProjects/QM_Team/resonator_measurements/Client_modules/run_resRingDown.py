from mResRingDown import *
from socProxy import makeProxy
import h5py
from PythonDrivers.control_atten import setatten
# import PythonDrivers.YOKOGS200 as YOKOGS200
import os
savePath = r'Z:/t1Team/Data/TALE03_06_16_22/RFSOC/timeDomain'

# Python 3.7
# os.environ['PATH'] = os.getcwd() + '\\PythonDrivers' + os.pathsep + os.environ['PATH']
# Python 3.8 and newer
os.add_dll_directory(os.getcwd() + '\\PythonDrivers')

# Only run this if no proxy already exists
soc, soccfg = makeProxy('192.168.1.147')
print(soccfg)

input = {}

# roundsList = [10, 20, 40, 80, 160, 320, 640, 1280, 2560, 5120]
# for i, ringTime in enumerate([1280, 640, 320, 160, 80, 40, 20, 10, 5]):

roundsList = [10, 20, 40, 80, 160, 320, 640]
for i, ringTime in enumerate([100, 50, 25, 15, 8, 4, 2]):
    # define frequencies
    input['LO_f'] = 5e3  # local oscillator frequency
    input['mixer_freq'] = 1700  # center frequency for the mixer
    # input['res_f'] = [5.9e3, 6.401658e3, 7.04506e3, 7.5e3]  # center frequencies of the resonators
    # input['res_f'] = [6.29686e3, 7e3, 7.5e3, 6.545e3]  # center frequencies of the resonators
    input['res_f'] = [6.29686e3, 7.1e3, 7.3e3, 6.545e3]  # center frequencies of the resonators

    # define numbers of points
    input['n_rounds'] = roundsList[i]  # number of times to sweep along the frequency axis
    input['n_reps'] = 500  # number of repetitions to take at each frequency point

    # timing. Units are clock cycles, but converted from us
    input['ring_up_time'] = ringTime  # time waiting for the resonator to ring up at the start of each sweep
    input['readout_length'] = 0.1  # time to average over
    input['relax_delay'] = 3*ringTime
    input['init_delay'] = ringTime/5
    input['t_delayArray'] = np.linspace(0, 2*ringTime+input['init_delay'], 250)

    # power
    input['basePower'] = 0
    # input['gain'] = [0, 0.35, 0.6, 0]
    input['gain'] = [0.6, 0, 0, 0.6]

    # Acquire
    Instance = ResRingDown(prefix='Ringdown_t'+str(ringTime), path=savePath, input=input, soc=soc, soccfg=soccfg)
    data = ResRingDown.acquire(Instance)
    ResRingDown.display(Instance, data)
    ResRingDown.save_data(Instance, data)