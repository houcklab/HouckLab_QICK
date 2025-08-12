import numpy as np



def rotate_data(data, theta):
    i = data[0]
    q = data[1]
    i_new = i * np.cos(theta) - q * np.sin(theta)
    q_new = i * np.sin(theta) + q * np.cos(theta)

    return (i_new, q_new)

def count_percentage(data, threshold):
    i = data[0]

    excited_population = sum(val > threshold for val in i)
    return excited_population / len(i)

def average_data(data):
    i = data[0][0]
    return np.mean(i)

def correct_occ(pop_data, confusion_matrix):
    '''Args: pop_data: 1d array of excited state percentages
             confusion_matrix: [[ngg, nge], [neg, nee]] characterizing state preparation and readout error
       Returns: 1d array of excited state percentages, adjusted by confusion matrix'''

    vec = np.vstack([1.-pop_data, pop_data])

    return (np.linalg.inv(confusion_matrix)[1,:]  @  vec).flatten()

def pop_to_expect(pop_vec):
    '''Converts populations in [0,1] to expectations in [-1,1]'''
    return 2*pop_vec - 1
