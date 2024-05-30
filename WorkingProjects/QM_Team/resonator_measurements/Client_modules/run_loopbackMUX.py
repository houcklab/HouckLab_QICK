from mLoopback import Loopback
from socProxy import makeProxy
import h5py
from PythonDrivers.control_atten import setatten
# import PythonDrivers.YOKOGS200 as YOKOGS200
import os

# Python 3.7
# os.environ['PATH'] = os.getcwd() + '\\PythonDrivers' + os.pathsep + os.environ['PATH']
# Python 3.8 and newer
os.add_dll_directory(os.getcwd() + '\\PythonDrivers')

# YOKOGS200.main(Yokovalue)

#setatten(0,27784,True)

# To do: translate some of these to be from the qchip, wiremap
config = {"res_ch": 6,  # --Fixed
          "mixer_freq": 1500,  # MHz
          "ro_chs": [0, 1, 2, 3],  # --Fixed
          "reps": 1,  # --Fixed
          "relax_delay": 0,  # --Fixed
          "pulse_style": "const",  # --Fixed

          #         "length":2**31-1, # [Clock ticks]
          # "length": 50,  # [Clock ticks]
          "length": 200,  # [Clock ticks]
          # Try varying length from 10-100 clock ticks

          "readout_length": 1000,  # [Clock ticks]
          # Try varying readout_length from 50-1000 clock ticks

          "pulse_freqs": [-530, -220, 350, 810],
          # In this program the signal is up and downconverted digitally so you won't see any frequency
          # components in the I/Q traces below. But since the signal gain depends on frequency,
          # if you lower pulse_freq you will see an increased gain.

          "adc_trig_offset": 100,  # [Clock ticks]
          # Try varying adc_trig_offset from 100 to 220 clock ticks

          "soft_avgs": 1000,
          # Try varying soft_avgs from 1 to 200 averages
          }

# Only run this if no proxy already exists
soc, soccfg = makeProxy('192.168.1.120')
print(soccfg)

# Acquire decimated
decimatedInstance = Loopback(path="dataTestLoopback", cfg=config,soc=soc,soccfg=soccfg)
data = Loopback.acquire_decimated(decimatedInstance)
Loopback.display_decimated(decimatedInstance, data)
Loopback.save_data(decimatedInstance, data)

# Acquire
config['reps'] = 200
Instance = Loopback(path="dataTestLoopback", cfg=config,soc=soc,soccfg=soccfg)
data = Loopback.acquire(Instance)
Loopback.display(Instance, data)

# Look at a data file
with h5py.File(decimatedInstance.fname, "r") as f:
    # List all groups
    print("Keys: %s" % f.keys())
    a_group_key = list(f.keys())[0]
    # Get the data
    data = list(f[a_group_key])
    print("Viewing data file")