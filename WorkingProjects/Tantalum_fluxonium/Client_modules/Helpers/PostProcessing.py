from WorkingProjects.Tantalum_fluxonium.Client_modules.Calib_escher.initialize import *
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mT1_PS_sse import T1_PS_sse
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mSingleShotTemp_sse import SingleShotSSE
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mQND import QNDmeas
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mTimeOfFlight_PS import TimeOfFlightPS
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mSpecSlice import SpecSlice

import h5py
import json
import numpy as np

def h5_to_dict(filename):
    dict = {}
    with h5py.File(filename+".h5", 'r') as f:
        for key in f.keys():
            dict[key] = f[key][()]
    return dict

def json_to_dict(filename):
    with open(filename+".json") as f:
        data = f.read()
    dict = json.loads(data)
    return dict

loc = 'Z:\\TantalumFluxonium\\Data\\2023_10_31_BF2_cooldown_6\\WTF\\TempChecks\\Yoko_-0.23\\T1_PS_temp_10\\T1_PS_temp_10_2023_12_05\\'
fname = 'T1_PS_temp_10_2023_12_05_22_20_27_data'
data = {"config": json_to_dict(loc+fname) , "data": h5_to_dict(loc+fname)}

# Processing the data
Instance_T1 = T1_PS_sse(path="random", outerFolder="random",
                        cfg=data["config"], soc=soc, soccfg=soccfg)
Instance_T1.process_data(data)
Instance_T1.display(data, plotDisp=True, saveFig = False)