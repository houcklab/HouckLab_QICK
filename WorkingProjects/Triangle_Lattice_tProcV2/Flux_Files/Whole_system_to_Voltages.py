from Import_Functions_Transmon import *
from Initialize_Qubit_Information import *

import matplotlib.pyplot as plt


from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.Device_calibration import full_device_calib

print_single_vector = True
plot_bare_system = True
plot_effective_system = True

frequencies = {
    'Q1': -0.5,
    'Q2': -0.5,
    'Q3': -0.5,
    'Q4': -0,
    'Q5': -0.5,
    'Q6': -0.5,
    'Q7': -0.5,
    'Q8': -0.5,
    'C1': 0,
    'C2': 0,
    'C3': 0,
    'C4': 0,
    'C5': 0,
    'C6': 0,
}


# Whether you gave a flux value for a key
flux_was_given = {key: (type(freq) is not str) and (freq < 10) for key,freq in frequencies.items()}


dressed_qubit_freqs = []
# If qubit freqs given, treat as dressed frequency. If flux given, use approximate frequency, then set back to exact flux at end
for key in order_of_qubits:
    if flux_was_given[key]: # as flux
        flux = frequencies[key]
        dressed_qubit_freqs.append(model_mapping[key].freq(flux) * 1000)
    else: # as frequency
        dressed_qubit_freqs.append(frequencies[key])

coupler_freqs = []
for j, key in enumerate(order_of_couplers):
    if type(frequencies[key]) == str: # Given as coupling strength
        tunable_coupling = float(frequencies[key])

        bounds = [model_mapping[key].freq(-0.5) * 1000, model_mapping[key].freq(0) * 1000]
        coupler_freq = full_device_calib.invert_eff_g(tunable_coupling, dressed_qubit_freqs[j], dressed_qubit_freqs[j+2],
                                        beta_matrix[j,j+8], beta_matrix[j+2,j+8], beta_matrix[j,j+2])[0]
        coupler_freqs.append(coupler_freq)
    elif flux_was_given[key]: # as flux
        flux = frequencies[key]
        coupler_freqs.append(model_mapping[key].freq(flux) * 1000)
    else: # as frequency
        coupler_freqs.append(frequencies[key])

# Convert dressed qubit freqs and coupler freqs to 14 bare freqs
bare_freqs_all = full_device_calib.dressed_freqs_to_bare_freqs(dressed_qubit_freqs, coupler_freqs, beta_matrix)

# All freqs above in MHz

# Convert these bare freqs to fluxes
bare_order_of_items = ['Q1_bare', 'Q2_bare', 'Q3_bare', 'Q4_bare', 'Q5_bare', 'Q6_bare', 'Q7_bare', 'Q8_bare',
                       'C1', 'C2', 'C3', 'C4', 'C5', 'C6']
flux_vector = []
for mapping_key, freq, orig_key in zip(bare_order_of_items, bare_freqs_all, order_of_items):
    if flux_was_given[orig_key]:
        flux_vector.append(frequencies[orig_key])
    else:
        flux_vector.append(flux_sign[mapping_key]*model_mapping[mapping_key].flux(freq / 1e3))


if __name__ == "__main__":
    voltages = flux_to_voltage(flux_vector, crosstalk_matrix, crosstalk_offset, crosstalk_inverse)
    # fluxes_rounded = voltage_to_flux(np.round(voltages, 4), crosstalk_matrix, crosstalk_offset, crosstalk_inverse)


    # Printing and plotting
    # Convert back to dressed frequencies to check
    effective_qubit_freqs, g_matrix = full_device_calib.dress_system(bare_freqs_all, beta_matrix=beta_matrix, plot=False)

    printed_freqs = np.concatenate([effective_qubit_freqs, coupler_freqs])
    for i in range(len(voltages)):
        print(
            f"     '{order_of_items[i]}': {np.round(voltages[i], 4)}, #{np.round(printed_freqs[i], 2)}")

    if print_single_vector:
        print(repr(np.round(voltages, 4)))

    if plot_bare_system:
        full_device_calib.bare_system(bare_freqs_all, beta_matrix, plot=True)

    if plot_effective_system:
        full_device_calib.plot_dressed_system(effective_qubit_freqs, g_matrix)

    plt.show(block=True)


    # print(crosstalk_matrix)


    # plot crosstalk matrix
    # import matplotlib.pyplot as plt
    # plt.imshow(crosstalk_matrix, interpolation='none')
    # plt.show()
    # all_qubits_and_couplers = ['Q1', 'Q2', 'Q3', 'Q4', 'Q5', 'Q6', 'Q7', 'Q8', 'C1', 'C2', 'C3', 'C4', 'C5', 'C6']
    # plt.xticks(range(14), all_qubits_and_couplers)
    # plt.xlabel('Qubit or Coupler')
    # plt.ylabel('Fluxline')
