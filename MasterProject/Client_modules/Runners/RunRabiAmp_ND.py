
#### import packages
import os
path = os.getcwd()
os.add_dll_directory(os.path.dirname(path)+'\\PythonDrivers')
from MasterProject.Client_modules.CoreLib.socProxy import makeProxy
from MasterProject.Client_modules.Initialization.initialize import BaseConfig
from MasterProject.Client_modules.Experiments.RabiAmp_ND import RabiAmp_ND_Experiment
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
    "yokoVoltage": 0.0,
    ###### cavity
    "read_pulse_style": "const", # --Fixed
    "read_length": 10, # us
    "read_pulse_gain": 10000, # [DAC units]
    "read_pulse_freq": 6425.3,
    ##### spec parameters for finding the qubit frequency
    "qubit_freq_start": 2869 - 10,
    "qubit_freq_stop": 2869 + 10,
    "qubit_freq_expts": 41,
    "qubit_pulse_style": "arb",
    "sigma": 0.300,  ### units us, define a 20ns sigma
    # "flat_top_length": 0.300, ### in us
    "relax_delay": 500,  ### turned into us inside the run function
    ##### amplitude rabi parameters
    "qubit_gain_start": 1000,
    "qubit_gain_stop": 5000, ### stepping amount of the qubit gain
    "qubit_gain_expts": 2, ### number of steps
    "reps": 50,  # number of averages for the experiment
}
config = BaseConfig | UpdateConfig

yoko1.SetVoltage(config["yokoVoltage"])
#

### Note: This way of measuring uses the old 'Experiment' class that should be revised or retired
Instance_RabiAmp_ND_Experiment = RabiAmp_ND_Experiment(path="dataRabiAmp_ND", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg, progress=True)
data_RabiAmp_ND_Experiment = RabiAmp_ND_Experiment.acquire(Instance_RabiAmp_ND_Experiment)
RabiAmp_ND_Experiment.save_data(Instance_RabiAmp_ND_Experiment, data_RabiAmp_ND_Experiment)
# RabiAmp_ND_Experiment.save_config(Instance_RabiAmp_ND_Experiment)

RabiAmp_ND_Experiment.display(Instance_RabiAmp_ND_Experiment, data_RabiAmp_ND_Experiment, plotDisp = True, figNum = 1)



#####################################################################################################################

print('end time: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))

plt.show()

# #
# plt.show(block = True)
