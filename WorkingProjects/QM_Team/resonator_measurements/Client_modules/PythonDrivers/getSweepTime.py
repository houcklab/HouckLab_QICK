import numpy as np
from PythonDrivers.getInputDicts import getInputDicts

def printSweepTime(chipDict,dBm_lookup_file):
    inputDicts = getInputDicts(chipDict,measType='power_sweep',dBm_lookup_file=dBm_lookup_file)
    inputDict=inputDicts[0]
    print('Time per sweep (2 resonators):',sum(np.multiply(inputDict['n_roundsList'],inputDict['n_repsList']))*(.024*inputDict['n_expts'])/60,'min')