from Import_Functions_Transmon import *
from Initialize_Qubit_Information import *

voltages = {
    'Q1': 0,
    'Q2': 0,
    'Q3': 0,
    'Q4': 0,
    'Q5': 0,
    'Q6': 0,
    'Q7': 0,
    'Q8': 0,
    'C1': 0,
    'C2': 0,
    'C3': 0,
    'C4': 0,
    'C5': 0,
    'C6': 0
}

voltage_vector = [voltages[key] for key in order_of_items]
fluxes_rounded = voltage_to_flux(np.round(voltage_vector, 4), crosstalk_matrix, crosstalk_offset, crosstalk_inverse)
for i in range(len(voltages)):
    print(
        f"     '{order_of_items[i]}': {np.round(model_mapping[order_of_items[i]].freq(fluxes_rounded[i]) * 1e3, 2)}")
