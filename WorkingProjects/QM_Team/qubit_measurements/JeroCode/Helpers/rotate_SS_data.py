import numpy as np

def rotate_data(data, theta):
    i = data[0]
    q = data[1]
    i_new = i * np.cos(theta) - q * np.sin(theta)
    q_new = i * np.sin(theta) + q * np.cos(theta)

    return((i_new, q_new))

def count_percentage(data, threshold):
    i = data[0][0]

    excited_population = sum(val > threshold for val in i)
    return(excited_population / len(i))

def average_data(data):
    i = data[0][0]
    return(np.mean(i))


