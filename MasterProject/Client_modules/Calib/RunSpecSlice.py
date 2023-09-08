
#### import packages
import os
path = os.getcwd()
os.add_dll_directory(os.path.dirname(path)+'\\PythonDrivers')
from MasterProject.Client_modules.CoreLib.socProxy import makeProxy
from MasterProject.Client_modules.Calib.initialize import BaseConfig
from MasterProject.Client_modules.Experiments.SpecSlice import SpecSliceExperiment, SpecSlice
from MasterProject.Client_modules.PythonDrivers.YOKOGS200 import YOKOGS200
import pyvisa as visa
from matplotlib import pyplot as plt
import datetime



#### define the saving path
outerFolder = "Z:\\TantalumFluxonium\\Data\\2023_07_20_BF2_cooldown_3\\TF4\\"

###qubitAtten = attenuator(27797, attenuation_int= 10, print_int = False)

print('starting time: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))

#################################### Running the actual experiments

# Only run this if no proxy already exists
soc, soccfg = makeProxy()

plt.ioff()

####### define the yoko
yoko_GPIB = 'GPIB0::2::INSTR'
yoko1 = YOKOGS200(VISAaddress = yoko_GPIB, rm = visa.ResourceManager())
yoko1.SetMode('voltage')

####################################################################################################################
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
    "reps": 100,
}
config = BaseConfig | UpdateConfig

yoko1.SetVoltage(config["yokoVoltage"])
#

Instance_SpecSliceExperiment = SpecSliceExperiment(path="dataSpecSlice", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg, progress=True)
data_SpecSliceExperiment = SpecSliceExperiment.acquire(Instance_SpecSliceExperiment)
SpecSliceExperiment.save_data(Instance_SpecSliceExperiment, data_SpecSliceExperiment)
SpecSliceExperiment.save_config(Instance_SpecSliceExperiment)

SpecSliceExperiment.display(Instance_SpecSliceExperiment, data_SpecSliceExperiment, plotDisp = True, figNum = 1)



#####################################################################################################################

print('end time: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))

plt.show()

# #
# plt.show(block = True)
