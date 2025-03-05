'''Joshua's FF Compensation Helper'''

import numpy as np

def loadIQArray(name):
    return np.load(fr"Z:\QSimMeasurements\Measurements\5QV2_Triangle_Lattice\CompensatedFFPulses\{name}.npy")