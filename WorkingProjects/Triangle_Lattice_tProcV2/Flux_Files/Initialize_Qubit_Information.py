from Import_Functions_Transmon import *
import os

directory = r"Z:\QSimMeasurements\Measurements\\8QV1_Triangle_Lattice\\qubit_parameters\\Dictionary_File\\"

files = os.listdir(directory)
sorted_files = sorted(files)
file_name = sorted_files[-1]  # most recent
# print(sorted_files)
dictionary_everything = read_info(directory + file_name)
order_of_items = ['Q1', 'Q2', 'Q3', 'Q4', 'Q5', 'Q6', 'Q7', 'Q8', 'C1', 'C2', 'C3', 'C4', 'C5', 'C6'] ## Order of crosstalk matrices and everything!

order_of_qubits = ['Q1', 'Q2', 'Q3', 'Q4', 'Q5', 'Q6', 'Q7', 'Q8']
order_of_couplers = ['C1', 'C2', 'C3', 'C4', 'C5', 'C6']
flux_sign = {
    'Q1': -1,
    'Q2': -1,
    'Q3': -1,
    'Q4': -1,
    'Q5': -1,
    'Q6': -1,
    'Q7': -1,
    'Q8': -1,
    'C1': -1,
    'C2': -1,
    'C3': -1,
    'C4': -1,
    'C5': -1,
    'C6': -1,

    'Q1_bare': -1,
    'Q2_bare': -1,
    'Q3_bare': -1,
    'Q4_bare': -1,
    'Q5_bare': -1,
    'Q6_bare': -1,
    'Q7_bare': -1,
    'Q8_bare': -1,
}


model_mapping = {key: Transmon(dictionary_everything[key], key) for
             key in flux_sign.keys()}
crosstalk_matrix = dictionary_everything['crosstalk_matrix']
crosstalk_offset = dictionary_everything['crosstalk_offset']
crosstalk_inverse = dictionary_everything['crosstalk_inverse']
beta_matrix = dictionary_everything['betas']

