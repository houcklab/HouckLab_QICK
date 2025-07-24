from Import_Functions_Transmon import *
from Initialize_Qubit_Information import *

found_qubits =[
                 ['Q2', -0.25, -0.249510709697290785],  # expected freq, found freq
                 ['Q5', -0.25, -0.2518956339498992] , # expected freq, found freq
                 ['Q6', -0.25, -0.2475177832852412],  # expected freq, found freq
                 ['Q7', -0.25, -0.2541860024621924],
                 ['Q8', -0.25, -0.2576648827144932]]  # expected freq, found freq] # expected freq, found freq

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