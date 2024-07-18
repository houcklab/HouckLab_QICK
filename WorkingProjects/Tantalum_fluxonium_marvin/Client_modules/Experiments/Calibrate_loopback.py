from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mTransmission_SaraTest import Transmission

import os
os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Calib.initialize import *


# Yokovalue = -0.052 #-0.798 # (0 flux, re-measure) #-0.666 # (0.2 flux, re-measure) #0.7015 #(0.58 flux target 0 zz) #0.2 #(0.19 flux, still far away from coupler) #-0.049 (0 flux) #0.0225 (from TQ3 measurement, 0 flux)
# YOKOGS200.main(Yokovalue)
#
# setatten(36,27787,True)
# setatten(16,27797,True)

# To do: translate some of these to be from the qchip, wiremap

# # Time of flight
# config = {"res_ch": 0,  # --Fixed
#           "mixer_freq": 0.0,  # MHz
#           "nqz": 1,
#           "ro_chs": [0],  # --Fixed
#           "reps": 1,  # --Fixed
#           "relax_delay": 10,  # --Fixed
#           "res_phase": 0,  # --Fixed
#           "pulse_style": "const",  # --Fixed
#
#           "length": 500,  # [Clock ticks]
#           # Try varying length from 10-100 clock ticks
#
#           "readout_length": 1000,  # [Clock ticks]
#           # Try varying readout_length from 50-1000 clock ticks
#
#           "pulse_gain": 30000,  # [DAC units]
#           # Try varying pulse_gain from 500 to 30000 DAC units
#
#           "pulse_freq": 800,  # [MHz]
#           # In this program the signal is up and downconverted digitally so you won't see any frequency
#           # components in the I/Q traces below. But since the signal gain depends on frequency,
#           # if you lower pulse_freq you will see an increased gain.
#
#           "adc_trig_offset": soc.us2cycles(0.468 - 0.02),  # [Clock ticks]
#           # Try varying adc_trig_offset from 100 to 220 clock ticks
#
#           "soft_avgs": 30000
#           # Try varying soft_avgs from 1 to 200 averages
#
#           }

# Transmission
UpdateConfig={
        "reps": 2000,  # --Fixed
        "pulse_style": "const", # --Fixed
        "length": soc.us2cycles(5), # [Clock ticks]
        # Try varying length from 10-100 clock ticks
        "pulse_gain":30000, # [DAC units]
        # Try varying pulse_gain from 500 to 30000 DAC units
        "pulse_freq": 893, # [MHz]
       }

config = BaseConfig | UpdateConfig ### note that UpdateConfig will overwrite elements in BaseConfig
config["readout_length"] = config["length"]
cavity_LO = 6.5e9

#----------------

# Only run this if no proxy already exists
soc, soccfg = makeProxy()
print(soccfg)

# Loop over modules
i = 0
while i < 1:
    # Instance = Loopback(path="dataTestLoopback", cfg=config,soc=soc,soccfg=soccfg)
    # data= Loopback.acquire(Instance)
    # Loopback.display(Instance, data)
    # Loopback.save_data(Instance, data)

    Instance = Transmission(path="dataTestTransmission", cfg=config,soc=soc,soccfg=soccfg)
    data= Transmission.acquire(Instance)
    Transmission.display(Instance)
    Transmission.save_data(Instance, data)

    i += 1

# Look at a data file
with h5py.File(Instance.fname, "r") as f:
    # List all groups
    print("Keys: %s" % f.keys())
    a_group_key = list(f.keys())[0]
    # Get the data
    data = list(f[a_group_key])
    print("Viewing data file")

