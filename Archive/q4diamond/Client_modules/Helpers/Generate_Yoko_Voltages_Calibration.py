
import itertools
import numpy as np
import pickle


def voltage_to_flux(voltage_vector, voltage_matrix, offset_vector):
    return (voltage_matrix.dot(voltage_vector) - offset_vector)


# for more qubits, change repeat = 4 in itertools:
x = [0, 1, 2, 3]  # this should remain 4 because this counts the different fluxes:[fluxlow, -low, high, -high]
all_combinatorics = [p for p in itertools.product(x, repeat=4)]


def flux_to_voltage(flux_quanta, Voltage_matrix_inverse, FluxQuanta_offsets, minimum_only=False):
    fluxes_low, fluxes_high = flux_quanta
    all_flux_quantas = []
    for i in range(len(fluxes_low)):
        all_flux_quantas.append([fluxes_low[i], -fluxes_low[i], fluxes_high[i], -fluxes_high[i]])

    minimum = np.inf
    minimum_voltages = np.array([0, 0, 0])
    for comb in all_combinatorics:
        index1, index2, index3, index4 = comb
        flux_array = [all_flux_quantas[0][index1], all_flux_quantas[1][index2], all_flux_quantas[2][index3],
                      all_flux_quantas[3][index4]]
        voltages = Voltage_matrix_inverse.dot(FluxQuanta_offsets + flux_array)
        voltages_squared = np.sum(voltages ** 2)
        if voltages_squared < minimum:
            minimum = voltages_squared
            minimum_voltages = voltages

    return (minimum_voltages)

def Ej(d, phiext):
    '''
    phiext is in units of flux quanta
    '''
    return(1 * np.sqrt((np.cos(np.pi * phiext))**2 + d**2 * (np.sin(np.pi * phiext)**2)))

def flux(frequency, EjEc, d):
    EjEc *= 8
    numerator = np.sqrt((frequency ** 4) / (EjEc ** 2) - d ** 2)
    denominator = np.sqrt(1 - d ** 2)
    return np.arccos(numerator / denominator) / np.pi


def Flux_Freq(frequency_array, list_of_dictionaries):
    fluxes_low = []
    fluxes_high = []

    for i in range(len(frequency_array)):
        freq = frequency_array[i]
        parameter = list_of_dictionaries[i]
        d = parameter['di']
        offset = parameter['EjEc']
        flux_value = flux(freq, offset, d)
        fluxes_low.append(flux(freq, offset, d))
        fluxes_high.append(1 - flux(freq, offset, d))

    return (np.array(fluxes_low), np.array(fluxes_high))


def Freq_to_Voltage(frequency_list, list_of_dictionaries, inverse_voltage_matrix, offset_vector):
    Fluxes_low, Fluxes_high = Flux_Freq(frequency_list, list_of_dictionaries)
    return (flux_to_voltage((Fluxes_low, Fluxes_high), inverse_voltage_matrix, offset_vector))


def Voltage_to_Freq(voltage_list, list_of_dictionaries, voltage_matrix, offset_vector):
    voltage_flux_quanta = voltage_to_flux(voltage_list, voltage_matrix, offset_vector)
    frequencies = []
    for i in range(len(voltage_list)):
        EjEc = list_of_dictionaries[i]["EjEc"]
        di = list_of_dictionaries[i]["di"]
        frequencies.append(np.sqrt(8 * EjEc * Ej(di, voltage_flux_quanta[i])) * 1e3)
    return (frequencies)

def ResonatorFrequency(qubit_freq, w0, coupling):
    return(w0 + coupling / (w0 - qubit_freq))


def cavity_frequency_qubit(qubit_frequency, qubit_label, cavity_dictionary):
    w0 = cavity_dictionary[qubit_label]['w0']
    chi = cavity_dictionary[qubit_label]['chi']
    offset = {'qubit1': 0.0003, 'qubit2': 0.0002, 'qubit3': 0.0002, 'qubit4': 0}
    offset = {'qubit1': 0, 'qubit2': 0, 'qubit3': 0, 'qubit4': 0}
    return (ResonatorFrequency(qubit_frequency, w0, chi) + offset[qubit_label])

file_location = 'Z:\Jeronimo\Measurements\Qubit_Parameters'
list_of_dictionaries, voltage_matrix, inverse_voltage_matrix, offset_vector,cavity_dictionaries = pickle.load(open(file_location +
                                                                                                                   '\Calibration_Parameters_4Q_221019.p', 'rb'))


print(list_of_dictionaries, voltage_matrix, offset_vector)

# pulse and measure left qubit (?)
qubit1_freq = 4.8
qubit2_freq = 4.8
qubit3_freq = 4.8
qubit4_freq = 4.8

Readout_qubit_index = 2  #1 indexed

rounding_number = 4
# desired_frequencies = [4.695, 4.415, 4.120]
# offset_vector[0] += 0.038
# offset_vector[1] += 0.035
# offset_vector[2] += 0.029  #compensate for having FF pulses off during this

# offset_vector[0] += 0.000
# offset_vector[1] += -0.001
# offset_vector[2] += -0.00 #0.00453
# offset_vector[3] += 0.001

qubit_frequencies = {'qubit1': qubit1_freq, "qubit2": qubit2_freq, 'qubit3': qubit3_freq, 'qubit4': qubit4_freq}
readout_qubit_label = 'qubit' + str(Readout_qubit_index)
print("cavity frequency for {}: {}".format(readout_qubit_label,
                                           np.round((cavity_frequency_qubit(qubit_frequencies[readout_qubit_label],
                                                                            readout_qubit_label,
                                                                            cavity_dictionaries)) * 1e3,
                                                    rounding_number)))
print("Yoko voltages:", np.round(Freq_to_Voltage([qubit1_freq, qubit2_freq, qubit3_freq, qubit4_freq],
                                                 list_of_dictionaries,
                                                 inverse_voltage_matrix, offset_vector), rounding_number))
qubit1_freq, qubit2_freq, qubit3_freq, qubit4_freq = Voltage_to_Freq([ -0.335, -0.388 + 0.0, 0, 0],list_of_dictionaries,  voltage_matrix, offset_vector)
qubit_frequencies = {'qubit1': qubit1_freq, "qubit2": qubit2_freq, 'qubit3': qubit3_freq, 'qubit4': qubit4_freq}
print(np.round( np.array([qubit1_freq, qubit2_freq, qubit3_freq, qubit4_freq]), 1))
print("cavity frequency for {}: {}".format(readout_qubit_label,
                                           np.round((cavity_frequency_qubit(qubit_frequencies[readout_qubit_label] / 1e3,
                                                                            readout_qubit_label,
                                                                            cavity_dictionaries)) * 1e3,
                                                    rounding_number)))
# #
# print(offset_vector)

"""
Generate quasi-random Yoko voltage values
Want total voltage to be less than ~0.8 V, to minimize fridge heating
Want qubit frequencies greater than 100 MHz from each other so that we can ignore avoided crossings
"""
import numpy as np
import pickle as pkl
import matplotlib.pyplot as plt

def Ej(d, phi_ext):
    return (np.cos(np.pi * phi_ext) ** 2 + d ** 2 * np.sin(np.pi * phi_ext) ** 2) ** 0.5

def voltage_to_flux(voltage_vector, voltage_matrix, offset_vector):
    return(voltage_matrix.dot(voltage_vector) - offset_vector)
# def Voltage_to_Freq(voltage_list, list_of_dictionaries, voltage_matrix, offset_vector):
#     voltage_flux_quanta = voltage_to_flux(voltage_list, voltage_matrix, offset_vector)
#     frequencies = []
#     for i in range(len(voltage_list)):
#         EjEc = list_of_dictionaries[i]["EjEc"]
#         di = list_of_dictionaries[i]["di"]
#         frequencies.append(np.sqrt(8 * EjEc * Ej(di, voltage_flux_quanta[i])))
#     return(frequencies)

def Voltage_to_Freq(voltage_list, list_of_dictionaries, voltage_matrix, offset_vector):
    voltage_flux_quanta = voltage_to_flux(voltage_list, voltage_matrix, offset_vector)
    frequencies = []
    for i in range(len(voltage_list)):
        Ej_ = list_of_dictionaries[i]["Ej"]
        di = list_of_dictionaries[i]["di"]
        Ec_ = list_of_dictionaries[i]["Ec"]
        frequencies.append(np.sqrt(8 * Ej_ * Ec_ * Ej(di, voltage_flux_quanta[i])) - Ec_)
    return(frequencies)


def qfs_conflict(freqs, buf=0.15):
    "checks to see if qubit frequencies are too close, 100 MHz default"
    for i, f1 in enumerate(freqs):
        for j, f2 in enumerate(freqs):
            if j <= i:
                continue
            if abs(f1 - f2) < buf:
                return True
    return False

def cavity_frequency_qubit(qubit_frequency, qubit_label, cavity_dictionary):
    w0 = cavity_dictionary[qubit_label]['w0']
    chi = cavity_dictionary[qubit_label]['chi']
    # offset = {'qubit1': 0.0003, 'qubit2': 0.0002, 'qubit3': 0.0002, 'qubit4': 0}
    offset = {'qubit1': 0, 'qubit2': 0, 'qubit3': 0, 'qubit4': 0}
    return (ResonatorFrequency(qubit_frequency, w0, chi) + offset[qubit_label])

# file_location = 'Z:\Jeronimo\Measurements\Qubit_Parameters'
# list_of_dictionaries, voltage_matrix, inverse_voltage_matrix, offset_vector,cavity_dictionaries = pickle.load(open(file_location +
#                                                                                                                    '\Calibration_Parameters_4Q_221019.p', 'rb'))

list_of_dictionaries, voltage_matrix, inverse_voltage_matrix, offset_vector,cavity_dictionaries = pickle.load(open(file_location +
                                                                                                                   '\\4Q_0Flux\Calibration_Parameters_4Q_0F_230203.p', 'rb'))
list_of_dictionaries, voltage_matrix, inverse_voltage_matrix, offset_vector,cavity_dictionaries = pickle.load(open(file_location +
                                                                                                                   '\\4Q_0Flux\Calibration_Parameters_RFSOC_Test.p', 'rb'))

print(cavity_dictionaries)
maximum_total_voltage = 1
frequency_conflict = 0.07
npts = range(300)
vs_in = []
qfs = []
cfs = []
for n in npts:
    v4_in = 1.6 * (np.random.rand(4) - 0.5)
    while sum(abs(v4_in)) > maximum_total_voltage:  # ensure that absolute voltage sum is less than 0.8
        v4_in = 1.6 * (np.random.rand(4) - 0.5)
    f4_q = Voltage_to_Freq(v4_in, list_of_dictionaries, voltage_matrix, offset_vector)
    while qfs_conflict(f4_q):
        v4_in = 1.6 * (np.random.rand(4) - 0.5)
        while sum(abs(v4_in)) > maximum_total_voltage:  # ensure that absolute voltage sum is less than 0.8
            v4_in = 1.6 * (np.random.rand(4) - 0.5)
        f4_q = Voltage_to_Freq(v4_in, list_of_dictionaries, voltage_matrix, offset_vector)
    f4_c = [cavity_frequency_qubit(f4_q[i], 'qubit' + str(i + 1), cavity_dictionaries) * 1e3 for i in range(len(v4_in))]
    vs_in.append(v4_in)
    qfs.append(f4_q)
    cfs.append(f4_c)
# print(cavity_dictionaries)

# print(vs_in[0], qfs, cfs)
# print(np.round(np.array(vs_in), 3))
vs_in = np.round(np.array(vs_in), 3)
# print(vs_in, qfs, cfs)

voltages = list(np.linspace(-0.8, 0.8, 161))
freqs = []
for v in voltages:
    freqs.append(Voltage_to_Freq([v, v, v, v], list_of_dictionaries, np.diag(np.diagonal(voltage_matrix)), offset_vector))
freqs = np.array(freqs).transpose()
fig, axes = plt.subplots(4, 1, sharex=True)
axes[0].plot(voltages, freqs[0], lw=0.5, c='gray')
axes[1].plot(voltages, freqs[1], lw=0.5, c='gray')
axes[2].plot(voltages, freqs[2], lw=0.5, c='gray')
axes[3].plot(voltages, freqs[3], lw=0.5, c='gray')
for v4_in, q4f in zip(vs_in, qfs):
    print("total |V|: ", sum(abs(v4_in)))
    axes[0].plot(v4_in[0], q4f[0], '.')
    axes[1].plot(v4_in[1], q4f[1], '.')
    axes[2].plot(v4_in[2], q4f[2], '.')
    axes[3].plot(v4_in[3], q4f[3], '.')
plt.xlabel("qubit approx. voltage in (V)")

dat = {'yokoVs': vs_in,
       'qubitFreqs': qfs,
       'cavityFreqs': cfs}
plt.show()
index = 0
print(vs_in[index], qfs[index], cfs[index])
# pickle.dump(dat, open('Yoko_Voltages_0F_300.p', 'wb'))