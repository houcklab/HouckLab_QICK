import numpy as np
from pathlib import Path
import json

from triangle_lattice_quench.Device_Calibration.Device_calib.DeviceInterface import DeviceInterface

'''Currently implemented in FFDefinitions in FF_utils.py, to correct constant pulse FF gains,
and in FFEnvelope_Helpers.py, to correct arbitrary waveform gains.'''

# ff_crosstalk_matrix_path = None
# ff_crosstalk_matrix_path = Path(r"Z:\QSimMeasurements\Measurements\8QV1_Triangle_Lattice\_qubit_parameters\FF_crosstalk_2.csv")

APPLY_FF_CROSSTALK = False

if APPLY_FF_CROSSTALK:
    with open(r"C:\Users\houck\Documents\HouckLab_QICK\WorkingProjects\triangle_lattice_quench\Device_Calibration\PRESENT_CONFIG.json") as f:
        data = json.load(f)
        DEVICE_PATH = data["DEVICE_PATH"]
        dev = DeviceInterface.from_json(DEVICE_PATH)

        FF_CROSSTALK = dev.get_ff_crosstalk_matrix()
        FF_CORRECTION = np.linalg.inv(FF_CROSSTALK)
    print(f"Applying FF crosstalk correction from device {DEVICE_PATH}.")
else:
    FF_CORRECTION = None
    print("No FF crosstalk correction applied.")

def correct(arr):
    if FF_CORRECTION is None:
        return arr
    else:
        maxv = 32766
        arr = FF_CORRECTION  @ np.array(arr)
        arr[arr > maxv] = maxv
        arr[arr < -maxv] = -maxv
        return arr