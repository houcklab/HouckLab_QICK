import numpy as np
from datetime import datetime
import pickle

from scipy.optimize import curve_fit, root_scalar, minimize

def flux_to_voltage(flux_vector, crosstalk_matrix, crosstalk_offset, crosstalk_inverse):
    return crosstalk_inverse @ (flux_vector + crosstalk_offset * np.diag(crosstalk_matrix))


def voltage_to_flux(voltage_vector, crosstalk_matrix, crosstalk_offset, crosstalk_inverse):
    return crosstalk_matrix @ voltage_vector - crosstalk_offset * np.diag(crosstalk_matrix)

def file_name_(file_name, end='.pkl'):
    now = datetime.now()
    time_only = now.strftime("%H%M%S")
    time_only_day = now.strftime("20%y%m%d")

    time_only_day

    day_time = rf"{time_only_day}_{time_only}_" + file_name + end
    return (day_time)


def save_info(Dictionary, file_name):
    with open(file_name, 'wb') as f:
        pickle.dump(Dictionary, f)


def read_info(file_name):
    with open(file_name, 'rb') as f:
        Dictionary = pickle.load(f)
    return (Dictionary)
#
def modify_crosstalk_offset(found_qubit_info, crosstalk_offset, model_mapping, crosstalk_matrix, order_of_items, flux_sign):
    if found_qubit_info[1] > 10:
        found_flux = model_mapping[found_qubit_info[0]].flux(found_qubit_info[2] / 1e3) * flux_sign[found_qubit_info[0]]
        expected_flux = model_mapping[found_qubit_info[0]].flux(found_qubit_info[1] / 1e3) * flux_sign[found_qubit_info[0]]
    else:
        found_flux = found_qubit_info[2]
        expected_flux = found_qubit_info[1]
    index_crosstalk = order_of_items.index(found_qubit_info[0])
    crosstalk_offset_modified = np.copy(crosstalk_offset)
    # Subtraction is because of the minus sign of crosstalk_offset in voltage_to_flux
    crosstalk_offset_modified[index_crosstalk] -= (found_flux - expected_flux) / crosstalk_matrix[index_crosstalk][index_crosstalk]
    return(crosstalk_offset_modified)


class Transmon:
    def __init__(self, transmon_popt, name='Qubit'):
        '''
        transmon_popt: [x0, a, fq, ec, d]
        '''
        x0, a, fq, ec, d = transmon_popt
        self.name = name
        self.transmon_popt = transmon_popt
        self.flux_quantum_voltage = fq
        self.voltage_offset = x0

        # flux -> freq
        self.freq = create_qubit_function(self.transmon_popt)
        # freq -> flux
        self.flux = create_qubit_inverse_function(self.freq)

        # functions using V, no crosstalk correction
        self.V_to_freq = lambda V: transmon_fit(V, *self.transmon_popt)
        self.flux_to_V = create_qubit_flux_to_voltage(self.transmon_popt)
        self.V_to_flux = create_qubit_voltage_to_flux(self.transmon_popt)


def transmon_fit(x, x0, a, fq, ec, d):
    '''
        x0: offset (Volts)
        a: maximum qubit frequency
        fq: flux quantum in volts
        ec: "charging energy", offset
        d: junction asymmetry
    '''
    return np.sqrt(np.abs(a ** 2) * np.sqrt(
        np.cos(np.pi / fq * (x - x0)) ** 2 + (d ** 2) * np.sin(np.pi / fq * (x - x0)) ** 2)) - ec


def coupler_resonator_fit(x, x0, a, fq, ec, d, β, Ω, M):
    '''a: maximum qubit frequency ~ 5
      fq: flux quantum in volts ~ 2 to 3
      ec: "charging energy" ~ 0.2
      d: junction asymmetry E [0, 1.0]
      β: coupling factor ~ 1e-3
      Ω: resonator frequency ~ 7 (average of your resonator)
      M: crosstalk factor ~ 1e-5
   '''

    coupler_freq = transmon_fit(x, x0, a, fq, ec, d)
    resonator_freq = Ω + M * x  # effect of other qubits' crosstalk

    g = β * np.sqrt(coupler_freq * resonator_freq)
    delta = coupler_freq - resonator_freq
    return resonator_freq - g ** 2 / delta

def Q_deriv(x, a, d, c):
    '''First derivative of transmon_fit with respect to flux'''
    x = x * np.pi
    return 0.25 * a * (-2 * np.cos(x) * np.sin(x) + 2 * (d ** 2) * np.cos(x) * np.sin(x)) * (
                (a * (np.sqrt(np.cos(x) ** 2 + (d ** 2) * (np.sin(x) ** 2)))) ** -0.5) * (
                (np.cos(x) ** 2 + (d ** 2) * (np.sin(x) ** 2)) ** -0.5)


def create_qubit_function(_popt):
    x0, a, fq, ec, d = _popt
    return lambda x: transmon_fit(fq * x + x0, *_popt)


def create_qubit_inverse_function(qubit_function):
    def find_root(f, __qubit_function):
        bracket = (0, 0.5)

        if isinstance(f, (list, np.ndarray)):
            fluxes = np.empty(len(f))
            for i in range(len(f)):
                root_function = lambda flux: __qubit_function(flux) - f[i]
                result = root_scalar(root_function, bracket=bracket)
                fluxes[i] = result.root
            return fluxes
        elif isinstance(f, (int, float)):
            root_function = lambda flux: __qubit_function(flux) - f
            result = root_scalar(root_function, bracket=bracket)
            return result.root

    return lambda f: find_root(f, qubit_function)


def create_qubit_flux_to_voltage(_popt):
    x0, a, fq, ec, d = _popt
    return lambda x: fq * x + x0


def create_qubit_voltage_to_flux(_popt):
    x0, a, fq, ec, d = _popt
    return lambda x: (x - x0) / fq