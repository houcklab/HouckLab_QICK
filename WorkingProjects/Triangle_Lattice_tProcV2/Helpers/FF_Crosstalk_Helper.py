import numpy as np

'''Currently implemented in FFDefinitions in FF_utils.py, to correct constant pulse FF gains,
and in FFEnvelope_Helpers.py, to correct arbitrary waveform gains.'''

# ff_crosstalk_matrix_path = None
ff_crosstalk_matrix_path = r"Z:\QSimMeasurements\Measurements\8QV1_Triangle_Lattice\qubit_parameters\FF_crosstalk_2.csv"

if ff_crosstalk_matrix_path is not None:
    FF_CROSSTALK = np.loadtxt(ff_crosstalk_matrix_path, delimiter=",")
    FF_CORRECTION = np.linalg.inv(FF_CROSSTALK)
    print("Applying FF crosstalk correction.")
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