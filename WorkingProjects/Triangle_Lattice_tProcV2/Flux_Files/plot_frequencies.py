import matplotlib.pyplot as plt
import numpy as np


# import qubit parameters from this file
from WorkingProjects.Triangle_Lattice_tProcV2.Run_Experiments.qubit_parameter_files.Qubit_Parameters_Master import *

from Initialize_Qubit_Information import model_mapping
from Whole_system_to_Voltages import flux_vector, dressed_qubit_freqs, coupler_freqs, beta_matrix
from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.Device_calibration import full_device_calib

def ff_gains_to_freqs(ff_gains):
    mappings = ['Q1_bare', 'Q2_bare', 'Q3_bare', 'Q4_bare', 'Q5_bare', 'Q6_bare', 'Q7_bare', 'Q8_bare']
    FF_flux_quanta = np.array([model_mapping[bare_mapping].flux_quantum_voltage for bare_mapping in mappings])

    flux_changes = np.asarray(ff_gains) / FF_flux_quanta

    target_fluxes = flux_vector + np.concatenate([flux_changes, np.zeros(6)])

    bare_order_of_items = ['Q1_bare', 'Q2_bare', 'Q3_bare', 'Q4_bare', 'Q5_bare', 'Q6_bare', 'Q7_bare', 'Q8_bare',
                       'C1', 'C2', 'C3', 'C4', 'C5', 'C6']
    bare_frequencies = [1000*model_mapping[mapping].freq(flux) for mapping,flux in zip(bare_order_of_items, target_fluxes)]

    dressed_freqs, g_matrix = full_device_calib.dress_system(bare_frequencies, beta_matrix=beta_matrix, plot=False)

    return dressed_freqs


intermediate_jump_gains = [-13344, None, 8565, None, -4754, None, 19250, None]
for i in range(len(intermediate_jump_gains)):
    if intermediate_jump_gains[i] is None:
        intermediate_jump_gains[i] = BS_FF[i]

gains = [Readout_FF, Ramp_FF, intermediate_jump_gains, BS_FF, Readout_FF]

freqs = np.array([ff_gains_to_freqs(arr) for arr in tuple(gains)])

# gains = np.array([pulse_145, Readout_FF4])
for i in range(freqs.shape[1]):
    plt.plot(freqs[:,i], label=f'Q{i+1}')
plt.xlabel('experimental section index')
plt.ylabel('gain')
plt.legend()
plt.show()


