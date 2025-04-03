
#### import packages
import os
path = os.getcwd()
os.add_dll_directory(os.path.dirname(path)+'\\PythonDrivers')
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Calib.initialize import *

from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mSpecSlice_dynamic import SpecSlice

from matplotlib import pyplot as plt
import datetime

#### define the saving path
outerFolder = "Z:\\TantalumFluxonium\\Data\\2023_07_20_BF2_cooldown_3\\TF4\\"


print('starting time: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))

#################################### Running the actual experiments

# Only run this if no proxy already exists
soc, soccfg = makeProxy()
print(soccfg)

plt.ioff()


#################################

################################## code for running qubit spec on repeat
UpdateConfig = {
    ##### define attenuators
    "yokoVoltage": 0.25,
    ###### cavity
    "read_pulse_style": "const", # --Fixed
    "read_length": 5, # us
    "read_pulse_gain": 10000, # [DAC units]
    "read_pulse_freq": 6425.3,
    ##### spec parameters for finding the qubit frequency
    "qubit_freq_start": 2869 - 20,
    "qubit_freq_stop": 2869 + 20,
    "SpecNumPoints": 81,  ### number of points
    "qubit_pulse_style": "flat_top",
    "sigma": 0.050,  ### units us
    "qubit_length": 1, ### units us, doesnt really get used though
    "flat_top_length": 0.300, ### in us
    "relax_delay": 500,  ### turned into us inside the run function
    "qubit_gain": 20000, # Constant gain to use
    # "qubit_gain_start": 18500, # shouldn't need this...
    "spec_reps": 5,
    "sets": 50,
}

config = BaseConfig | UpdateConfig ### note that UpdateConfig will overwrite elements in BaseConfig

# set the yoko frequency
yoko1.SetVoltage(config["yokoVoltage"])
print("Voltage is ", yoko1.GetVoltage(), " Volts")

Instance_specSlice = SpecSlice(path="dataTestSpecSlice_dynamic", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
data_specSlice = SpecSlice.acquire(Instance_specSlice)

SpecSlice.display(Instance_specSlice, data_specSlice, plotDisp=True)
SpecSlice.save_data(Instance_specSlice, data_specSlice)
SpecSlice.save_config(Instance_specSlice)



print('end time: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))

plt.show()

