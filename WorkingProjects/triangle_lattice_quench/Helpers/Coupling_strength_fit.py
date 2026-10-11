import numpy as np
from scipy.optimize import curve_fit

# Fit functions
def cosfit(t, freq, A, y0, tau, phi):
    return y0 + np.abs(A) * np.exp(-t / np.abs(tau)) * np.cos(2 * np.pi * freq * t + phi)

def freqfit(d, d0, b, g):
    '''frequency of oscillations, = 2g at Δ=0.'''
    return 2 * np.sqrt(b * (d - d0) ** 2 + g ** 2)

# Helpers to get initial guess for frequencies
def frequency_guess(t, y):
    '''Given a real y(t), find a guess for the oscillation frequency of y(t).
    Use to fit to chevrons.'''
    fft_ampl = np.abs(np.fft.rfft(y))
    freqs = np.fft.rfftfreq(len(y)) / (t[1] - t[0])  # units of 1/time

    return freqs[np.argmax(fft_ampl[1:])+1]

def omega_guess(t, y):
    '''frequency_guess but multiplied by 2π'''
    return 2 * np.pi * frequency_guess(t, y)


# Quick chevron fit
def fit_chevron(gains, times, pop_matrix, b_guess=1.36055267e-04, return_fit_points=False):
    '''gains: array of gains (y-axis)
       times: array of times (x-axis)
       pop_matrix: (gains, times) matrix of expectation values or populations

       Frequency will be returned in  1/(unit of times).
       e.g. times is in us -> returns MHz'''

    freq_list = []
    fit_gains_list = []

    for i, exp in enumerate(pop_matrix):
        try:
            # freqfit(gains[i], center_gain_guess,  5e-11, 13)
            p0 = [frequency_guess(times, exp), np.max(exp) - np.min(exp), exp[0], times[-1], 1e-3]
            cos_params, _ = curve_fit(cosfit, times, exp, p0, maxfev=int(1e9))


            freq_list.append(cos_params[0])
            fit_gains_list.append(gains[i])
        except RuntimeError:
            pass

    p0 = [fit_gains_list[np.argmin(freq_list)], b_guess, np.min(freq_list)/2]
    freq_param, pcov = curve_fit(freqfit, fit_gains_list, freq_list, p0=p0)

    perr = np.sqrt(np.diag(pcov))

    if return_fit_points:
        return freq_param, pcov, perr, freq_list, fit_gains_list
    else:
        return freq_param