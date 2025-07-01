from Import_Functions_Transmon import *
from Initialize_Qubit_Information import *

Voltage_Dictionary = {
    'Q1': -0.6599,  # 3842.9
    'Q2': 0.0397,  # 4404.95
    'Q3': -0.0144,  # 4363.82
    'Q4': 0.0212,  # 4422.81
    'Q5': -0.021,  # 4377.97
    'Q6': 0.0085,  # 4361.65
    'Q7': -0.031,  # 4313.94
    'Q8': -0.0036,  # 4403.23
    'C1': -0.0394,  # 5800.0
    'C2': 0.0314,  # 5800.0
    'C3': -0.0434,  # 5800.0
    'C4': 0.0104,  # 5800.0
    'C5': -0.0462,  # 5800.0
    'C6': 0.0041,  # 5800.0
}

voltage_vector = [Voltage_Dictionary[key] for key in order_of_items]
fluxes_rounded = voltage_to_flux(np.round(voltage_vector, 4), crosstalk_matrix, crosstalk_offset, crosstalk_inverse)
for i in range(len(voltage_vector)):
    print(
        f"     '{order_of_items[i]}': {np.round(model_mapping[order_of_items[i]].freq(fluxes_rounded[i]) * 1e3, 2)},")
