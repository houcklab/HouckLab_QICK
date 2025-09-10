from Import_Functions_Transmon import *
from Initialize_Qubit_Information import *

found_qubits =[ ['Q1', -0.25, -0.250891],
                ['Q2', -0.25, -0.2500082],
                ['Q3', -0.25, -0.24715350416298892],
                ['Q4', -0.25, -0.24584221995381955],
                ['Q5', -0.25, -0.24737098257030732],
                ['Q6', -0.25, -0.24710625827490773],
                ['Q7', -0.25, -0.25000529111419123],
                ['Q8', -0.25, -0.23912886038832082],
]  # expected freq, found freq] # expected freq, found freq

# found_qubit =

# found_qubit = ['C1', 0, 0.02]  # expected freq, found freq
crosstalk_offset_modified = crosstalk_offset

for found_qubit in found_qubits:
    crosstalk_offset_modified = modify_crosstalk_offset(found_qubit, crosstalk_offset_modified, model_mapping, crosstalk_matrix, order_of_items, flux_sign)

dictionary_everything['crosstalk_offset'] = crosstalk_offset_modified

print(crosstalk_offset - crosstalk_offset_modified)
print(crosstalk_offset_modified)
# #
print('Previous version!!!!')
print(directory + file_name)
total_path = directory + file_name_('8Q_Parameters')

print('New File!!!!')
print(total_path)
save_info(dictionary_everything, total_path)