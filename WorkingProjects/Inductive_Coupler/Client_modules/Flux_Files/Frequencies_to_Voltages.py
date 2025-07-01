from Helper_Functions.Import_Functions_Transmon import *
from Initialize_Qubit_Information import *


FF_amplitudes = {
    'Q1': 0,
    'Q2': 0,
    'Q3': 0,
    'Q5': 0,
}

frequencies = {
    'Q1': 4000,
    'Q2': 4000,
    'Q3': 4000,
    'Q5': 4000,
    'C1': -0.5,  #
    'C2': -0.5,
    'C3': -0.5,
}

frequencies = {
    'Q1': 4000,
    'Q2': 4000,
    'Q3': 4000,
    'Q4': 4000,
    'Q5': 4000,
    'Q6': 4000,
    'Q7': 4000,
    'Q8': 4000,
    'C1': -0.5,  #
    'C2': -0.5,
    'C3': -0.5,
    'C4': -0.5,  #
    'C5': -0.5,
    'C6': 0,
}

flux_vector = []
FF_flux_vector = []
for key in order_of_items:
    if frequencies[key] < 10:
        flux_vector.append(frequencies[key])
        continue
    try:
        flux_val = model_mapping[key].flux(frequencies[key] / 1e3)
        sign_ = flux_sign[key]
        if np.sign(flux_val) != sign_:
            flux_val *= -1
    except:
        print(key + ' frequency is outside requested bounds! Flux set to 0')
        flux_val = 0
    flux_vector.append(flux_val)

voltages = flux_to_voltage(flux_vector, crosstalk_matrix, crosstalk_offset, crosstalk_inverse)
fluxes_rounded = voltage_to_flux(np.round(voltages, 4), crosstalk_matrix, crosstalk_offset, crosstalk_inverse)
for i in range(len(voltages)):
    print(
        f"     '{order_of_items[i]}': {np.round(voltages[i], 4)}, #{np.round(model_mapping[order_of_items[i]].freq(fluxes_rounded[i]) * 1e3, 2)}")
