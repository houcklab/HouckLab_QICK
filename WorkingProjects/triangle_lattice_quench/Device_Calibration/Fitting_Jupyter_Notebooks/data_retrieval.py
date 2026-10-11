import matplotlib.pyplot as plt
import numpy as np
import h5py
import scipy
from scipy.io import loadmat
from scipy.optimize import curve_fit, root_scalar, minimize
from scipy.signal import savgol_filter
import os

from functools import lru_cache

pnax_expts_dict = {
    'trans':'Transmission8Qubit_Tri',
    'spec' :'2Tone8Qubit_Tri'
    }

rfsoc_expts_dict = {
    'rfc':'RamseyFreqCal',
    'ff' : 'FFSpecCal'
}


'''Use h5py.File(filename, mode=mode) from now on, and
    in functions, use np.asarray to allow polymorphism with
    both h5 datasets and python lists/arrays.'''

@lru_cache
def rfsoc_data(date, time, exp_name, year='2025', mode='r'):
    return h5py.File(rfsoc_filename(date, time, exp_name, year=year), mode=mode)


### File name generation ###

def pnax_filename(date, time, exp_name, year='2025'):
    if exp_name in pnax_expts_dict:
        exp_name = pnax_expts_dict[exp_name]
    return fr'Z:\QSimMeasurements\Measurements\8QV1_Triangle_lattice\pnax{date}{year[2:]}\{exp_name}_{year}{date}_{time}'

def rfsoc_filename(date, time, exp_name, suffix='data', year='2025'):
    if exp_name in rfsoc_expts_dict:
        exp_name = rfsoc_expts_dict[exp_name]
    month, day = date[0:2], date[2:4]
    h, m, s = time[0:2], time[2:4], time[4:6] # hour, minute, second
    return fr'Z:\QSimMeasurements\Measurements\8QV1_Triangle_lattice\{exp_name}\{exp_name}_{year}_{month}_{day}\{exp_name}_{year}_{month}_{day}_{h}_{m}_{s}_{suffix}.h5'

def rfsoc_prefix(date, prefix, exp_name, num_to_return=1, year='2025'):
    if exp_name in rfsoc_expts_dict:
        exp_name = rfsoc_expts_dict[exp_name]
    month, day = date[0:2], date[2:4]
    dir = rf"Z:\QSimMeasurements\Measurements\8QV1_Triangle_lattice\{exp_name}\{exp_name}_{year}_{month}_{day}"
    files = sorted(filter(lambda x: x[-(len(prefix)+3):] == f'{prefix}.h5', os.listdir(dir)), key=lambda f: os.path.getmtime(dir+'\\'+f))
    files = [dir+'\\'+ file for file in files]

    print(files[-num_to_return])
    return files[-num_to_return]

def lorentzian_fit(x, x0, a, b, c):
    return a/(1+(x-x0)**2/b**2)+c

def center_freqs(freqs, mesh):
    _, freqs, _ = get_center_frequencies(np.arange(mesh.shape[0]),freqs,mesh)
    return freqs

def get_center_frequencies(voltages, frequencies, transmission_data, start_index=5, frequency_index_span=150, plot_fits=False, toss_failures = False):
    '''
    use a Lorentzian fit to get the center frequencies
    this is different from Jeronimo's function in that you pass the transpose of what you pass into that one here
    :param frequency_index_span: number of points around peak to try fit
    Z_data:
    '''
    center_frequencies = []
    center_frequency_errors = []
    voltages_with_fit = []
    
    if isinstance(start_index, int):
        start_indices = [start_index] * transmission_data.shape[0]
    else:
        start_indices = list(start_index)
    
    for i in range(transmission_data.shape[0]):
        start_index = start_indices[i] if i < len(start_indices) else start_indices[-1]
        row = transmission_data[i, start_index:]
        
        peak_index = np.argmax(np.abs(row)) + start_index
        center_frequency_guess = frequencies[peak_index]
        
        # fit to lorentzian
        # restrict fit in range span around peak
        # print(frequencies.shape, transmission_data.shape)
        # MHz_per_index = (frequencies[1] - frequencies[0])/1e6
        # frequency_index_span = int(np.ceil(frequency_MHz_span / MHz_per_index))
        restricted_frequencies = frequencies[max(peak_index - frequency_index_span//2, 0):min(peak_index + frequency_index_span//2, len(frequencies))]
        restricted_row = transmission_data[i,max(peak_index - frequency_index_span//2, 0):min(peak_index + frequency_index_span//2, len(frequencies))]

        filtered_row = savgol_filter(restricted_row, 7, 1)
        
        bounds = ([restricted_frequencies[0], 0, -np.inf, -np.inf], [restricted_frequencies[-1], np.inf, np.inf, np.inf])
        initial_guess = [center_frequency_guess, np.max(filtered_row)-np.min(filtered_row), 4e-3, np.min(filtered_row)]
        # print(restricted_frequencies.shape, filtered_row.shape)
        try:
            popt, pcov = curve_fit(lorentzian_fit, restricted_frequencies, filtered_row, p0=initial_guess, bounds=bounds)
        except:
            if not toss_failures:
                print(f'Couldn\'t fit index {i}, using maximum')
                
                # use max as the center frequency
                center_frequencies.append(restricted_frequencies[np.argmax(filtered_row)])
                voltages_with_fit.append(voltages[i])
                center_frequency_errors.append(frequencies[-1] - frequencies[0])
            else:
                print(f'Couldn\'t fit index {i}')
        else:
            # Fit succeeded, append results
            center_frequencies.append(popt[0])
            center_frequency_errors.append(np.sqrt(np.diag(pcov)[0]))
            voltages_with_fit.append(voltages[i])
            
        if plot_fits:
            plt.plot(restricted_frequencies, filtered_row, linestyle='', marker='o', label='data')
            print(popt)
            fit_frequencies = np.linspace(frequencies[start_index], frequencies[-1], 1000)
            plt.plot(fit_frequencies, lorentzian_fit(fit_frequencies, *popt), label='fit')
            plt.plot(fit_frequencies, lorentzian_fit(fit_frequencies, *initial_guess), label='guess')
            plt.axvline(center_frequency_guess, color='red', linestyle=':')
            plt.legend()
            plt.xlabel('Frequency (MHz)')
            plt.title(f'Lorentzian fit for index {i}')
            plt.show()

            print(f'Center frequency is {popt[0]} MHz')
            
    return np.array(voltages_with_fit), np.array(center_frequencies), np.array(center_frequency_errors)