from qick import *
from qick import helpers
import matplotlib.pyplot as plt
import numpy as np
from q4diamond.Client_modules.Experiment import ExperimentClass
from q4diamond.Client_modules.Helpers.hist_analysis import *
from tqdm.notebook import tqdm
import time
import q4diamond.Client_modules.Helpers.FF_utils as FF
from q4diamond.Client_modules.Running_Experiments_MUX.MUXInitialize import *
from q4diamond.Client_modules.Experimental_Scripts_MUX.mTimingScope import TimingProg

import os
# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')


FF_channel1 = 0 #4 is middle qubit, 6 is left qubit
FF_channel2 = 1 #4 is middle qubit, 6 is left qubit
FF_channel3 = 2 #4 is middle qubit, 6 is left qubit
FF_channel4 = 3 #4 is middle qubit, 6 is left qubit

FF_gain1 = 30000
FF_gain2 = 0
FF_gain3 = 0

FF_Qubits = {
    str(1): {'channel': FF_channel1, 'delay_time': 0.0028 *2.9} ,
    str(2): {'channel': FF_channel2, 'delay_time': 0.0028 *2.6},
    str(3): {'channel': FF_channel3, 'delay_time': 0.0},
    str(4): {'channel': FF_channel4, 'delay_time': 0},
}
Additional_Delays = {
    str(1): {'channel': 4, 'delay_time': 0.0}    #This is not working right now!!!!
}

config={
    "reps": 3,  # this will used for all experiements below unless otherwise changed in between trials
    ##### define tranmission experiment parameters
    "qubit_nqz": 2, ### MHz, span will be center+/- this parameter
    "relax_delay": 5, ### number of points in the transmission frequecny
    "qubit_ch": 4, #### cavity attenuator attenuation value
    "qubit_gain": 10000,  #### cavity attenuator attenuation value

    # "soft_avgs": 300,
    "length": 0.03,
}
config["Additional_Delays"] = Additional_Delays

FF_Qubits[str(1)] |= {'Gain_Readout': 0, 'Gain_Expt': 0, 'Gain_Pulse': 0}
FF_Qubits[str(2)] |= {'Gain_Readout': 0, 'Gain_Expt': 0, 'Gain_Pulse': 0}
FF_Qubits[str(3)] |= {'Gain_Readout': 0, 'Gain_Expt': 0, 'Gain_Pulse': 0}
FF_Qubits[str(4)] |= {'Gain_Readout': 0, 'Gain_Expt': 0, 'Gain_Pulse': 0}
config["FF_Qubits"] = FF_Qubits
for i in range(1):
    soc.reset_gens()
    prog = TimingProg(soccfg, config)
    print(prog)
    prog.acquire(soc, load_pulses=True, progress=False)
    print('done')