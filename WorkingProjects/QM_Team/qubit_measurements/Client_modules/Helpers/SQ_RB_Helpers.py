import numpy as np


def gauss(mu=0, si=25, length=100, maxv=32766):
    """
    Create a numpy array containing a Gaussian function

    :param mu: Mu (peak offset) of Gaussian
    :type mu: float
    :param sigma: Sigma (standard deviation) of Gaussian
    :type sigma: float
    :param length: Length of array
    :type length: int
    :param maxv: Maximum amplitude of Gaussian
    :type maxv: float
    :return: Numpy array containing a Gaussian function
    :rtype: array
    """
    x = np.arange(0, length)
    y = maxv * np.exp(-(x-mu)**2/si**2)
    return y


def generate_rbsequence(depth):
    """Single qubit RB program to generate a sequence of 'd' gates followed
        by an inverse gate to bring the qubit back in 'g' state
    """

    gate_symbol = ['I', 'Z', 'X', 'Y', 'Z/2', 'X/2', 'Y/2', '-Z/2', '-X/2', '-Y/2']
    inverse_gate_symbol = ['I', '-Y/2', 'X/2', 'X', 'Y/2', '-X/2']

    """Modeled the bloch sphere as 6-node graph, each rotation in the RB sequence is effectively
    exchanging the node label on the bloch sphere.
    For example: Z rotation is doing this: (+Z->+Z, -Z->-Z, +X->+Y, +Y->-X, -X->-Y, -Y->+X)
    """
    matrix_ref = {}
    """Matrix columns are [Z, X, Y, -Z, -X, -Y]"""

    matrix_ref['0'] = np.matrix([[1, 0, 0, 0, 0, 0],
                                 [0, 1, 0, 0, 0, 0],
                                 [0, 0, 1, 0, 0, 0],
                                 [0, 0, 0, 1, 0, 0],
                                 [0, 0, 0, 0, 1, 0],
                                 [0, 0, 0, 0, 0, 1]])
    matrix_ref['1'] = np.matrix([[1, 0, 0, 0, 0, 0],
                                 [0, 0, 0, 0, 1, 0],
                                 [0, 0, 0, 0, 0, 1],
                                 [0, 0, 0, 1, 0, 0],
                                 [0, 1, 0, 0, 0, 0],
                                 [0, 0, 1, 0, 0, 0]])
    matrix_ref['2'] = np.matrix([[0, 0, 0, 1, 0, 0],
                                 [0, 1, 0, 0, 0, 0],
                                 [0, 0, 0, 0, 0, 1],
                                 [1, 0, 0, 0, 0, 0],
                                 [0, 0, 0, 0, 1, 0],
                                 [0, 0, 1, 0, 0, 0]])
    matrix_ref['3'] = np.matrix([[0, 0, 0, 1, 0, 0],
                                 [0, 0, 0, 0, 1, 0],
                                 [0, 0, 1, 0, 0, 0],
                                 [1, 0, 0, 0, 0, 0],
                                 [0, 1, 0, 0, 0, 0],
                                 [0, 0, 0, 0, 0, 1]])
    matrix_ref['4'] = np.matrix([[1, 0, 0, 0, 0, 0],
                                 [0, 0, 0, 0, 0, 1],
                                 [0, 1, 0, 0, 0, 0],
                                 [0, 0, 0, 1, 0, 0],
                                 [0, 0, 1, 0, 0, 0],
                                 [0, 0, 0, 0, 1, 0]])
    matrix_ref['5'] = np.matrix([[0, 0, 1, 0, 0, 0],
                                 [0, 1, 0, 0, 0, 0],
                                 [0, 0, 0, 1, 0, 0],
                                 [0, 0, 0, 0, 0, 1],
                                 [0, 0, 0, 0, 1, 0],
                                 [1, 0, 0, 0, 0, 0]])
    matrix_ref['6'] = np.matrix([[0, 0, 0, 0, 1, 0],
                                 [1, 0, 0, 0, 0, 0],
                                 [0, 0, 1, 0, 0, 0],
                                 [0, 1, 0, 0, 0, 0],
                                 [0, 0, 0, 1, 0, 0],
                                 [0, 0, 0, 0, 0, 1]])
    matrix_ref['7'] = np.matrix([[1, 0, 0, 0, 0, 0],
                                 [0, 0, 1, 0, 0, 0],
                                 [0, 0, 0, 0, 1, 0],
                                 [0, 0, 0, 1, 0, 0],
                                 [0, 0, 0, 0, 0, 1],
                                 [0, 1, 0, 0, 0, 0]])
    matrix_ref['8'] = np.matrix([[0, 0, 0, 0, 0, 1],
                                 [0, 1, 0, 0, 0, 0],
                                 [1, 0, 0, 0, 0, 0],
                                 [0, 0, 1, 0, 0, 0],
                                 [0, 0, 0, 0, 1, 0],
                                 [0, 0, 0, 1, 0, 0]])
    matrix_ref['9'] = np.matrix([[0, 1, 0, 0, 0, 0],
                                 [0, 0, 0, 1, 0, 0],
                                 [0, 0, 1, 0, 0, 0],
                                 [0, 0, 0, 0, 1, 0],
                                 [1, 0, 0, 0, 0, 0],
                                 [0, 0, 0, 0, 0, 1]])

    """Generate a random gate sequence of a certain depth 'd'"""
    gate_seq = []
    for ii in range(depth):
        gate_seq.append(np.random.randint(0, 9))
    """Initial node"""
    a0 = np.matrix([[1], [0], [0], [0], [0], [0]])
    anow = a0
    for i in gate_seq:
        anow = np.dot(matrix_ref[str(i)], anow)
    anow1 = np.matrix.tolist(anow.T)[0]
    """Returns the """
    max_index = anow1.index(max(anow1))
    symbol_seq = [gate_symbol[i] for i in gate_seq]
    symbol_seq.append(inverse_gate_symbol[max_index])
    return symbol_seq

def generate_gate_set(gain_pi, gain_pi2):
    gateset_dict = {
        "I": {
            "phase": 0, "gain": 0, "style": "arb",
        },
        "X": {
            "phase": 0, "gain": gain_pi, "style": "arb",
        },
        "Y": {
            "phase": -90, "gain": gain_pi, "style": "arb",
        },
        "Z": {
            "phase": 0, "gain": 0, "style": "arb",
        },
        "X/2": {
            "phase": 0, "gain": gain_pi2, "style": "arb",
        },
        "-X/2": {
            "phase": 180, "gain": gain_pi2, "style": "arb",
        },

        "Y/2": {
            "phase": -90, "gain": gain_pi2, "style": "arb",
        },
        "-Y/2": {
            "phase": 90, "gain": gain_pi2, "style": "arb",
        },
        "Z/2": {
            "phase": 0, "gain": 0, "style": "arb",
        },
        "-Z/2": {
            "phase": 0, "gain": 0, "style": "arb",
        },
    }
    return(gateset_dict)
