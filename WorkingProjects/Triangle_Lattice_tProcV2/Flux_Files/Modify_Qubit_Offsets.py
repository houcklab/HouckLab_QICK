from Import_Functions_Transmon import *
from Initialize_Qubit_Information import *

found_qubits =[
                 ['Q8', 3889.9, 3866.3]]  # expected freq, found freq] # expected freq, found freq

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