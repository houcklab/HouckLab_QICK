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