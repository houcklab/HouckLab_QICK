from Import_Functions_Transmon import *
from Initialize_Qubit_Information import *

all_qubits_and_couplers = ['Q1', 'Q2', 'Q3', 'Q4', 'Q5', 'Q6', 'Q7', 'Q8',
                           'C1', 'C2', 'C3', 'C4', 'C5', 'C6']

voltages = [0.0743, 1.4213, -0.1825, 1.3751, 1.2473, 1.3359, 1.2115, 1.1834,
            1.5, 1.5641, 1.4432, 1.6475, 1.4175, 1.4889]

voltages = [-1, 0, -0.6, 0, 0, 0, 0, 0,
            0.9, 0, 0, 0, 0, 0]

Voltage_Dictionary = {all_qubits_and_couplers[i]: voltages[i] for i in range(len(all_qubits_and_couplers))}

# Voltage_Dictionary = {
#     'Q1': -1,  # 3842.9
#     'Q2': 0,  # 4404.95
#     'Q3': -0.6,  # 4363.82
#     'Q4': 0, # 4422.81
#     'Q5': 0, # 4377.97
#     'Q6': 0, # 4361.65
#     'Q7': 0, # 4313.94
#     'Q8': 0,  # 4403.23
#     'C1': 0,  # 5800.0
#     'C2': 0, # 5800.0
#     'C3': 0,  # 5800.0
#     'C4': 0, # 5800.0
#     'C5': 0,  # 5800.0
#     'C6': 0, # 5800.0
# }


Voltage_Dictionary['C1'] = 1.5


voltage_vector = [Voltage_Dictionary[key] for key in order_of_items]
fluxes_rounded = voltage_to_flux(np.round(voltage_vector, 4), crosstalk_matrix, crosstalk_offset, crosstalk_inverse)
for i in range(len(voltage_vector)):
    print(
        f"     '{order_of_items[i]}': {np.round(model_mapping[order_of_items[i]].freq(fluxes_rounded[i]) * 1e3, 2)},")

print()
print()
print(f'C1: {np.round(model_mapping[order_of_items[8]].freq(fluxes_rounded[8]) * 1e3, 2)}')