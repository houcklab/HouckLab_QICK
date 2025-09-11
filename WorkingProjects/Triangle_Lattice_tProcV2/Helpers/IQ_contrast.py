import numpy as np
import scipy

def IQ_angle(Imat, Qmat):
    def newQvariance(theta):
        newQ = np.sin(theta)*Imat + np.cos(theta)*Qmat
        return np.max(newQ) - np.min(newQ)
    angle = scipy.optimize.minimize(newQvariance, (np.pi/4,)).x
    return angle

def rotate(theta, Imat, Qmat):
    return np.cos(theta)*Imat - np.sin(theta)*Qmat, np.sin(theta)*Imat + np.cos(theta)*Qmat # newI, newQ

def IQ_contrast(Imat, Qmat):
    theta = IQ_angle(Imat, Qmat)
    rotated_I, rotated_Q = rotate(theta, Imat, Qmat)
    return rotated_I - np.mean(rotated_I)

def normalize_contrast(*args):
    if len(args) == 1:
        contrast = args[0]
    elif len(args) == 2:
        contrast = IQ_contrast(args[0], args[1])
    else:
        raise ValueError

    contrast -= np.min(contrast)
    contrast /= (np.max(contrast)/2)
    contrast -= 1

    return contrast

def frequency_guess(t, y):
    '''Given a real y(t), find a guess for the oscillation frequency of y(t).
    Use to fit to chevrons.'''
    fft_ampl = np.abs(np.fft.rfft(y))
    freqs = np.fft.rfftfreq(len(y)) / (t[1] - t[0])  # units of 1/time

    return freqs[np.argmax(fft_ampl[1:])+1]

def omega_guess(t, y):
    '''Above but multiplied by 2π'''
    return 2 * np.pi * frequency_guess(t, y)