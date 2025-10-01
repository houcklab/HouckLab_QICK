import itertools

import numpy as np

def collate(n1, n2):
    '''
    Converts shots of n1 and n2 into shots of (n2-n1).
    2 matrices of (timesteps, shots) where each shot is 0 or 1
    ---> 1 matrix of (timesteps, 4) where the 4 is the probability of 00, 01, 10, or 11\
    '''
    # n1: last axis is shots
    n1 = np.asarray(n1, dtype=int)
    n2 = np.asarray(n2, dtype=int)

    new_matrix = np.zeros((*n1.shape, 2, 2))
    for ijk in itertools.product(*(range(dim) for dim in n1.shape)):
            new_matrix[*ijk, n1[*ijk], n2[*ijk]] = 1
    new_matrix = np.reshape(new_matrix, (*n1.shape, 4))

    # new_matrix: second-to-last axis is shots, last axis is 00, 01, 10, 11
    probs = np.mean(new_matrix, axis=-2)

    return probs

def get_nn_correlations(n1, n2, n3, n4):
    '''
    Converts shots of n1, n2, n3, and n4 (last axis = reps) into an average value of
    (n2-n1)*(n4-n3)
    '''
    n21 = n2 - n1
    n43 = n4 - n3
    return np.mean(n21 * n43, axis=-1)

def get_corrected_nn_correlations(n1, n2, n3, n4, conf_mats):
    '''
        Converts shots of n1, n2, n3, and n4 (last axis = reps) into an average value of
        (n2-n1)*(n4-n3)
        Pass in a list of four 2x2 confusion matrices for the final argument.
    '''
    conf1, conf2, conf3, conf4 = conf_mats

    conf24 = np.kron(conf2, conf4)
    conf14 = np.kron(conf1, conf4)
    conf23 = np.kron(conf2, conf3)
    conf13 = np.kron(conf1, conf3)

    # Data in form of (shots in) [00, 01, 10, 11]
    q24 = np.linalg.inv(conf24) @ collate(n2, n4).T
    q14 = np.linalg.inv(conf14) @ collate(n1, n4).T
    q23 = np.linalg.inv(conf23) @ collate(n2, n3).T
    q13 = np.linalg.inv(conf13) @ collate(n1, n3).T

    # Count number of 11 results = <n1 * n2>
    n24 = np.array([0, 0, 0, 1]) @ q24
    n14 = np.array([0, 0, 0, 1]) @ q14
    n23 = np.array([0, 0, 0, 1]) @ q23
    n13 = np.array([0, 0, 0, 1]) @ q13

    corrected_nn = n24 - n14 - n23 + n13

    return corrected_nn