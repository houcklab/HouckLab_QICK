from Import_Functions_Transmon import *
from Initialize_Qubit_Information import *

found_qubit = ['Q3', 3600,  3491.4]  #found Freq, expected freq
# found_qubit = ['C1', 0, 0.02]  #found Freq, expected freq

crosstalk_offset_modified = modify_crosstalk_offset(found_qubit, crosstalk_offset, model_mapping, crosstalk_matrix, order_of_items, flux_sign)
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