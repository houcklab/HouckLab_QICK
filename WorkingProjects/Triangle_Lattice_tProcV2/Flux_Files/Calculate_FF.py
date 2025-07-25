import numpy as np

from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.Device_calibration import full_device_calib
from Import_Functions_Transmon import *
from Initialize_Qubit_Information import flux_sign, model_mapping

from Initialize_Qubit_Information import flux_vector, dressed_qubit_freqs, coupler_freqs, beta_matrix

plot_effective_system = True
suffix = "expt"

frequencies = {
    'Q1': 4200,
    'Q2': 3800,
    'Q3': 3700,
    # 'Q4': 4000,
    # 'Q5': 0,
    # 'Q6': 0,
    # 'Q7': 0,
    # 'Q8': 0,
}
flux_was_given = {key: (freq < 10) for key,freq in frequencies.items()}

target_fluxes = np.copy(flux_vector)

mappings = ['Q1_bare', 'Q2_bare', 'Q3_bare', 'Q4_bare', 'Q5_bare', 'Q6_bare', 'Q7_bare', 'Q8_bare']
for index, key in enumerate(['Q1', 'Q2', 'Q3', 'Q4', 'Q5', 'Q6', 'Q7', 'Q8']):
    if frequencies.get(key) is not None:
        if flux_was_given[key]: # flux given
            target_fluxes[index] = frequencies[key]

        else: # dressed_freq -> bare_freq -> flux
            dressed_freq = frequencies[key]
            adjacent_couplers = np.nonzero(beta_matrix[index, 8:])[0] + 0
            bare_freq = full_device_calib.get_bare_freq(dressed_freq, [coupler_freqs[c] for c in adjacent_couplers], betas= [beta_matrix[index, c+8] for c in adjacent_couplers])
            flux = flux_sign[mappings[index]]*model_mapping[mappings[index]].flux(bare_freq / 1e3)

            target_fluxes[index] = flux

##!!! models such as Q1_bare have the flux_quanta in FF gain (~100,000) stored in flux_quantum_voltage !!!
# TODO: find a better place to store this info... - Joshua 7/25/25
FF_flux_quanta = np.array([model_mapping[bare_mapping].flux_quantum_voltage for bare_mapping in mappings])

flux_changes = np.asarray(target_fluxes) - np.asarray(flux_vector)
flux_changes = flux_changes[:8]

gains_list = flux_changes * FF_flux_quanta

gains_list = np.rint(gains_list).astype(int)

np.set_printoptions(linewidth=100000)
print(repr(gains_list))

for j, gain in zip(range(1, 1+len(gains_list)), gains_list):
    print(f"FF_gain{j}_{suffix} = {gain}")

if plot_effective_system:
    bare_order_of_items = ['Q1_bare', 'Q2_bare', 'Q3_bare', 'Q4_bare', 'Q5_bare', 'Q6_bare', 'Q7_bare', 'Q8_bare',
                       'C1', 'C2', 'C3', 'C4', 'C5', 'C6']
    bare_frequencies = [1000*model_mapping[mapping].freq(flux) for mapping,flux in zip(bare_order_of_items, target_fluxes)]

    full_device_calib.dress_system(bare_frequencies, beta_matrix=beta_matrix, plot=True)
