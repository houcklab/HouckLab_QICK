
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
        # print(Voltage_matrix_inverse,FluxQuanta_offsets, flux_array )

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



def Freq_to_Voltage(frequency_list, list_of_dictionaries, inverse_voltage_matrix, offset_vector):
    Fluxes_low, Fluxes_high = Flux_Freq(frequency_list, list_of_dictionaries)
    return (flux_to_voltage((Fluxes_low, Fluxes_high), inverse_voltage_matrix, offset_vector))


# def Voltage_to_Freq(voltage_list, list_of_dictionaries, voltage_matrix, offset_vector):
#     voltage_flux_quanta = voltage_to_flux(voltage_list, voltage_matrix, offset_vector)
#     frequencies = []
#     for i in range(len(voltage_list)):
#         EjEc = list_of_dictionaries[i]["EjEc"]
#         di = list_of_dictionaries[i]["di"]
#         frequencies.append(np.sqrt(8 * EjEc * Ej(di, voltage_flux_quanta[i])) * 1e3)
#     return (frequencies)


def Voltage_Cross_Coupling(voltage_vector, voltage_matrix):
    return(voltage_matrix.dot(voltage_vector ))
def FF_Cross_Coupling(FF_Vector, FF_Voltage_Matrix):
    return(FF_Voltage_Matrix.dot(FF_Vector))
def Voltage_to_Flux(voltage_vector, flux_quanta_list, offset_vector):
    return(voltage_vector / flux_quanta_list - offset_vector)
# def voltage_to_flux(voltage_vector, voltage_matrix, offset_vector, flux_quanta_list):
#     # print(voltage_matrix, voltage_vector, flux_quanta_list)
#     return(voltage_matrix.dot(voltage_vector ) / flux_quanta_list - offset_vector)

def ResonatorFrequency(qubit_freq, w0, coupling):
    return(w0 + coupling / (w0 - qubit_freq))


def cavity_frequency_qubit(qubit_frequency, qubit_label, cavity_dictionary):
    w0 = cavity_dictionary[qubit_label]['w0']
    chi = cavity_dictionary[qubit_label]['chi']
    offset = {'qubit1': 0.0003, 'qubit2': 0.0002, 'qubit3': 0.0002, 'qubit4': 0}
    offset = {'qubit1': 0, 'qubit2': 0, 'qubit3': 0, 'qubit4': 0}
    return (ResonatorFrequency(qubit_frequency, w0, chi) + offset[qubit_label])




EjEc_together = False

if EjEc_together:
    def Voltage_to_Frequency(voltage_vector, FF_vector, voltage_matrix, FF_matrix, flux_quanta_list, offset_vector, list_of_dictionaries):
        transpose_matrix = np.copy(voltage_matrix).T
        voltage_matrix_modified = (transpose_matrix * flux_quanta_list).T
        voltage_yoko = Voltage_Cross_Coupling(voltage_vector, voltage_matrix_modified)
        voltage_FF = FF_Cross_Coupling(FF_vector, FF_matrix)
        total_voltage = voltage_yoko + voltage_FF
        flux_values = Voltage_to_Flux(total_voltage, flux_quanta_list, offset_vector)
        frequencies = []
        for i in range(len(flux_values)):
            EjEc = list_of_dictionaries[i]["EjEc"]
            di = list_of_dictionaries[i]["di"]
            frequencies.append(np.sqrt(8 * EjEc * Ej(di, flux_values[i])) * 1e3)
        return(frequencies)
    def Voltage_to_Freq(voltage_list, list_of_dictionaries, voltage_matrix, offset_vector):
        voltage_flux_quanta = voltage_to_flux(voltage_list, voltage_matrix, offset_vector)
        frequencies = []
        for i in range(len(voltage_list)):
            EjEc = list_of_dictionaries[i]["EjEc"]
            di = list_of_dictionaries[i]["di"]
            frequencies.append(np.sqrt(8 * EjEc * Ej(di, voltage_flux_quanta[i])) * 1e3)
        return (frequencies)
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
    def flux(frequency, EjEc, d):
        EjEc *= 8
        numerator = np.sqrt((frequency ** 4) / (EjEc ** 2) - d ** 2)
        denominator = np.sqrt(1 - d ** 2)
        return np.arccos(numerator / denominator) / np.pi



if not EjEc_together:
    def Voltage_to_Frequency(voltage_vector, FF_vector, voltage_matrix, FF_matrix, flux_quanta_list, offset_vector, list_of_dictionaries):
        transpose_matrix = np.copy(voltage_matrix).T
        voltage_matrix_modified = (transpose_matrix * flux_quanta_list).T
        voltage_yoko = Voltage_Cross_Coupling(voltage_vector, voltage_matrix_modified)
        voltage_FF = FF_Cross_Coupling(FF_vector, FF_matrix)
        total_voltage = voltage_yoko + voltage_FF
        flux_values = Voltage_to_Flux(total_voltage, flux_quanta_list, offset_vector)
        frequencies = []
        for i in range(len(flux_values)):
            Ej_ = list_of_dictionaries[i]["Ej"]
            di = list_of_dictionaries[i]["di"]
            Ec_ = list_of_dictionaries[i]["Ec"]
            frequencies.append((np.sqrt(8 * Ej_ * Ec_ * Ej(di, flux_values[i])) - Ec_ - Ec_ * np.sqrt(Ec_ / (8 * Ej_ * Ej(di, flux_values[i]))))* 1e3)
        return(frequencies)
    def Voltage_to_Freq(voltage_list, list_of_dictionaries, voltage_matrix, offset_vector):
        voltage_flux_quanta = voltage_to_flux(voltage_list, voltage_matrix, offset_vector)
        frequencies = []
        for i in range(len(voltage_list)):
            Ej_ = list_of_dictionaries[i]["Ej"]
            di = list_of_dictionaries[i]["di"]
            Ec_ = list_of_dictionaries[i]["Ec"]
            frequencies.append(np.sqrt(8 * Ej_ * Ec_ * Ej(di, voltage_flux_quanta[i])) - Ec_)
        return(frequencies)
    def Flux_Freq(frequency_array, list_of_dictionaries):
        fluxes_low = []
        fluxes_high = []

        for i in range(len(frequency_array)):
            freq = frequency_array[i]
            parameter = list_of_dictionaries[i]
            d = parameter['di']
            Ej_ = parameter['Ej']
            Ec_ = parameter['Ec']
            flux_value = flux(freq, Ej_, Ec_, d)
            fluxes_low.append(flux(freq, Ej_, Ec_,  d))
            fluxes_high.append(1 - flux(freq, Ej_, Ec_, d))
        return(np.array(fluxes_low), np.array(fluxes_high))

    # def flux(frequency, Ej_, Ec_, d):
    #     Ej_ *= 8
    #     numerator = np.sqrt(((frequency + Ec_) ** 4) / ((Ej_ * Ec_) ** 2) - d **2)
    #     denominator = np.sqrt(1 - d ** 2)
    #     return np.arccos(numerator / denominator) / np.pi
    def flux(frequency, Ej_, Ec_, d):
        Ej_new = Find_Ej(frequency, Ec_)
        return(Ej_to_flux(Ej_new, d, Ej_))
    def Find_Ej(frequency, Ec_):
        first_term = (3 * Ec_**2 + 2 * Ec_ * frequency + frequency ** 2) / (16 * Ec_)
        second_term = (1 / 16) * np.sqrt((5 * Ec_**4 + 12 * frequency * Ec_**3 + 10 * frequency ** 2 * Ec_**2 + 4 * frequency ** 3 * Ec_ + frequency ** 4) / (Ec_**2))
        return(first_term + second_term)
    def Ej_to_flux(Ej, d, Ej_):
        numerator = np.sqrt((Ej / Ej_)**2 - d**2)
        denominator = np.sqrt(1 - d ** 2)
        return  np.arccos(numerator / denominator) / np.pi
def same_format(results):
    voltage_matrix = results['Fitted Voltage Matrix']
    inverse_voltage_matrix = np.linalg.inv(voltage_matrix)
    offset_vector = results['Fitted Offset Vector']
    cavity_dictionaries = results['Cavity Dictionaries']
    list_of_dictionaries = [{'di': results['Fitted d'][i], 'Ej': results['Fitted Ej'][i],
                             'Ec': results['Fitted Ec'][i], 'flux_quanta': 1 / voltage_matrix [i, i]} for i in range(4)]
    # offset_vector = np.array([1 / voltage_matrix [i, i] for i in range(4)])

    return (list_of_dictionaries, voltage_matrix, inverse_voltage_matrix, offset_vector,cavity_dictionaries)
file_location = 'Z:\Jeronimo\Measurements\Qubit_Parameters'
list_of_dictionaries, voltage_matrix, inverse_voltage_matrix, offset_vector,cavity_dictionaries = pickle.load(open(file_location +
                                                                                                                   '\Calibration_Parameters_4Q_221019.p', 'rb'))


# file_location = 'Z:\Jeronimo\Measurements\RFSOC_4Qubit_R\Qubit_Yoko_Calibration'
# list_of_dictionaries, voltage_matrix, inverse_voltage_matrix, offset_vector,cavity_dictionaries = pickle.load(open(file_location +
#                                                                                                                    '\Calibration_Parameters_RFSOC_300.p', 'rb'))
# FF_matrix = pickle.load(open(file_location + '\FF_matrix.p', 'rb'))
# print(list_of_dictionaries)


# list_of_dictionaries, voltage_matrix, inverse_voltage_matrix, offset_vector,cavity_dictionaries = pickle.load(open(file_location +
#                                                                                                                    '\\4Q_0Flux\Calibration_Parameters_4Q_0F_230203.p', 'rb'))
# offset_vector[0] += 0.000
# offset_vector[1] += -0.001
# offset_vector[2] += -0.00 #0.00453
# offset_vector[3] += 0.001

file_location = 'Z:\Jeronimo\Measurements\Qubit_Parameters'
list_of_dictionaries, voltage_matrix, inverse_voltage_matrix, offset_vector,cavity_dictionaries = pickle.load(open(file_location +
                                                                                                                   '\\4Q_ABV1\Calibration_Parameters.p', 'rb'))


results_everything = pickle.load(open(file_location + '\\4Q_ABV1\Results.p', 'rb'))
list_of_dictionaries, voltage_matrix, inverse_voltage_matrix, offset_vector,cavity_dictionaries = same_format(results_everything)

offset_vector[0] += 0
# offset_vector[1] += 0.039
offset_vector[2] += 0
offset_vector[3] += 0

file_location = 'Z:\Jeronimo\Measurements\RFSOC_4Qubit_0F\Qubit_Yoko_Calibration'
FF_matrix = pickle.load(open(file_location + '\FF_matrix.p', 'rb'))

rounding_number = 4
Flux_Quanta_List = np.array([list_of_dictionaries[i]['flux_quanta'] for i in range(len(list_of_dictionaries))])

print('Defining Yoko')
yoko_voltages = [ 0.1913,  0.7168, -0.2923, -0.0492]
yoko_voltages = [ 0, 0.2345, 0, 0]
yoko_voltages = [0.0852, -0.3669, -0.0874, 0.2018]
yoko_voltages = [0, 0, 0, 0]


Fast_flux_vector = [0, 0, 0, 0]

qubit1_freq, qubit2_freq, qubit3_freq, qubit4_freq = Voltage_to_Frequency(np.round(yoko_voltages, 8), Fast_flux_vector,
                                                                          voltage_matrix, FF_matrix, Flux_Quanta_List,
                                                                          offset_vector, list_of_dictionaries)
qubit_frequencies = {'qubit1': qubit1_freq, "qubit2": qubit2_freq, 'qubit3': qubit3_freq, 'qubit4': qubit4_freq}
print('After FastFlux:')
print('Qubits:', np.round(np.array([qubit1_freq, qubit2_freq, qubit3_freq, qubit4_freq]), 2))
cavity_frequencies = np.array(
    [cavity_frequency_qubit(qubit_frequencies['qubit' + str(i + 1)] / 1e3, 'qubit' + str(i + 1),
                            cavity_dictionaries) for i in range(4)])
print("Cavity:", np.round(cavity_frequencies * 1e3, 2))
print()

# pulse and measure left qubit (?)
qubit1_freq = 5.0
qubit2_freq = 5.0 - 0.18
qubit3_freq = 5.0 + 0.21
qubit4_freq = 5.0 + 0.03 - 0.005

qubit1_freq = 5.5
qubit2_freq = 4.1504
qubit3_freq = 5.5
qubit4_freq = 4.1465

qubit_frequencies = {'qubit1': qubit1_freq, "qubit2": qubit2_freq, 'qubit3': qubit3_freq, 'qubit4': qubit4_freq}
# readout_qubit_label = 'qubit' + str(Readout_qubit_index)
cavity_frequencies = np.array([cavity_frequency_qubit(qubit_frequencies['qubit' + str(i + 1)],'qubit' + str(i + 1),
                                                                            cavity_dictionaries) for i in range(4)])


yoko_voltages = Freq_to_Voltage([qubit1_freq, qubit2_freq, qubit3_freq, qubit4_freq],
                                                 list_of_dictionaries,
                                                 inverse_voltage_matrix, offset_vector)
print("Yoko voltages:", np.round(yoko_voltages, rounding_number))
print("Cav frequency:", np.round(cavity_frequencies * 1e3, 1))
print('Qubit freqs: ', np.round(np.array([qubit1_freq, qubit2_freq, qubit3_freq, qubit4_freq]) * 1e3, 2))

# for i in range(4):
#     print(f'yoko{69+i}.SetVoltage({np.round(yoko_voltages[i], rounding_number)})')
print(f"voltages = [{np.round(yoko_voltages[0], rounding_number)}, {np.round(yoko_voltages[1], rounding_number)}, {np.round(yoko_voltages[2], rounding_number)}, {np.round(yoko_voltages[3], rounding_number)}]")
# print('yoko69.SetVoltage(' + str(np.round(yoko_voltages[0], rounding_number)) + ')')
# print('yoko70.SetVoltage(' + str(np.round(yoko_voltages[1], rounding_number)) + ')')
# print('yoko71.SetVoltage(' + str(np.round(yoko_voltages[2], rounding_number)) + ')')
# print('yoko72.SetVoltage(' + str(np.round(yoko_voltages[3], rounding_number)) + ')')


Fast_flux_vector = np.array([-8000, 8000,  15000, 0])

print()
print('Pi Pulse')
if Fast_flux_vector.any() != 0:
    Voltage_to_Frequency
    qubit1_freq, qubit2_freq, qubit3_freq, qubit4_freq = Voltage_to_Frequency(np.round(yoko_voltages, 4) ,Fast_flux_vector,
                                                                         voltage_matrix, FF_matrix, Flux_Quanta_List,
                                                                        offset_vector,  list_of_dictionaries)
    qubit_frequencies = {'qubit1': qubit1_freq, "qubit2": qubit2_freq, 'qubit3': qubit3_freq, 'qubit4': qubit4_freq}
    print('After FastFlux:')
    print('Qubits:', np.round(np.array([qubit1_freq, qubit2_freq, qubit3_freq, qubit4_freq]), 2))
    cavity_frequencies = np.array([cavity_frequency_qubit(qubit_frequencies['qubit' + str(i + 1)] / 1e3, 'qubit' + str(i + 1),
                                                          cavity_dictionaries) for i in range(4)])
    print("Cavity:", np.round(cavity_frequencies * 1e3, 2))

# all_gains = [10000, 11000]
#
# # all_gains = [ -5000, -10000, -20000]
# for g in all_gains:
#     Fast_flux_vector = np.array([0, 0, 0, g])
#     print(g)
#     if Fast_flux_vector.any() != 0:
#         Voltage_to_Frequency
#         qubit1_freq, qubit2_freq, qubit3_freq, qubit4_freq = Voltage_to_Frequency(np.round(yoko_voltages, 4) ,Fast_flux_vector,
#                                                                              voltage_matrix, FF_matrix, Flux_Quanta_List,
#                                                                             offset_vector,  list_of_dictionaries)
#         qubit_frequencies = {'qubit1': qubit1_freq, "qubit2": qubit2_freq, 'qubit3': qubit3_freq, 'qubit4': qubit4_freq}
#         # print('After FastFlux:')
#         print('Qubits:', np.round(np.array([qubit1_freq, qubit2_freq, qubit3_freq, qubit4_freq]), 2))
#         # cavity_frequencies = np.array([cavity_frequency_qubit(qubit_frequencies['qubit' + str(i + 1)] / 1e3, 'qubit' + str(i + 1),
#         #                                                       cavity_dictionaries) for i in range(4)])
#         # print("Cavity:", np.round(cavity_frequencies * 1e3, 2))
#
# print('Q1')
# Fast_flux_vector = np.array([0, 5000, 0, 0])
# if Fast_flux_vector.any() != 0:
#     Voltage_to_Frequency
#     qubit1_freq, qubit2_freq, qubit3_freq, qubit4_freq = Voltage_to_Frequency(np.round(yoko_voltages, 4) ,Fast_flux_vector,
#                                                                          voltage_matrix, FF_matrix, Flux_Quanta_List,
#                                                                         offset_vector,  list_of_dictionaries)
#     qubit_frequencies = {'qubit1': qubit1_freq, "qubit2": qubit2_freq, 'qubit3': qubit3_freq, 'qubit4': qubit4_freq}
#     print('After FastFlux:')
#     print('Qubits:', np.round(np.array([qubit1_freq, qubit2_freq, qubit3_freq, qubit4_freq]), 2))
#     cavity_frequencies = np.array([cavity_frequency_qubit(qubit_frequencies['qubit' + str(i + 1)] / 1e3, 'qubit' + str(i + 1),
#                                                           cavity_dictionaries) for i in range(4)])
#     print("Cavity:", np.round(cavity_frequencies * 1e3, 2))
#
# print()
# print('Q2')
# Fast_flux_vector = np.array([0, 10000, 0, 0])
# if Fast_flux_vector.any() != 0:
#     Voltage_to_Frequency
#     qubit1_freq, qubit2_freq, qubit3_freq, qubit4_freq = Voltage_to_Frequency(np.round(yoko_voltages, 4) ,Fast_flux_vector,
#                                                                          voltage_matrix, FF_matrix, Flux_Quanta_List,
#                                                                         offset_vector,  list_of_dictionaries)
#     qubit_frequencies = {'qubit1': qubit1_freq, "qubit2": qubit2_freq, 'qubit3': qubit3_freq, 'qubit4': qubit4_freq}
#     print('After FastFlux:')
#     print('Qubits:', np.round(np.array([qubit1_freq, qubit2_freq, qubit3_freq, qubit4_freq]), 2))
#     cavity_frequencies = np.array([cavity_frequency_qubit(qubit_frequencies['qubit' + str(i + 1)] / 1e3, 'qubit' + str(i + 1),
#                                                           cavity_dictionaries) for i in range(4)])
#     print("Cavity:", np.round(cavity_frequencies * 1e3, 2))
#
# print()
# print('Q3')
# Fast_flux_vector = np.array([0, 0, 10000, 0])
# if Fast_flux_vector.any() != 0:
#     Voltage_to_Frequency
#     qubit1_freq, qubit2_freq, qubit3_freq, qubit4_freq = Voltage_to_Frequency(np.round(yoko_voltages, 4) ,Fast_flux_vector,
#                                                                          voltage_matrix, FF_matrix, Flux_Quanta_List,
#                                                                         offset_vector,  list_of_dictionaries)
#     qubit_frequencies = {'qubit1': qubit1_freq, "qubit2": qubit2_freq, 'qubit3': qubit3_freq, 'qubit4': qubit4_freq}
#     print('After FastFlux:')
#     print('Qubits:', np.round(np.array([qubit1_freq, qubit2_freq, qubit3_freq, qubit4_freq]), 2))
#     cavity_frequencies = np.array([cavity_frequency_qubit(qubit_frequencies['qubit' + str(i + 1)] / 1e3, 'qubit' + str(i + 1),
#                                                           cavity_dictionaries) for i in range(4)])
#     print("Cavity:", np.round(cavity_frequencies * 1e3, 2))
#
# print()
# print('Q4')
# Fast_flux_vector = np.array([-10000, 0, 0, -7000])
# if Fast_flux_vector.any() != 0:
#     Voltage_to_Frequency
#     qubit1_freq, qubit2_freq, qubit3_freq, qubit4_freq = Voltage_to_Frequency(np.round(yoko_voltages, 4) ,Fast_flux_vector,
#                                                                          voltage_matrix, FF_matrix, Flux_Quanta_List,
#                                                                         offset_vector,  list_of_dictionaries)
#     qubit_frequencies = {'qubit1': qubit1_freq, "qubit2": qubit2_freq, 'qubit3': qubit3_freq, 'qubit4': qubit4_freq}
#     print('After FastFlux:')
#     print('Qubits:', np.round(np.array([qubit1_freq, qubit2_freq, qubit3_freq, qubit4_freq]), 2))
#     cavity_frequencies = np.array([cavity_frequency_qubit(qubit_frequencies['qubit' + str(i + 1)] / 1e3, 'qubit' + str(i + 1),
#                                                           cavity_dictionaries) for i in range(4)])
#     print("Cavity:", np.round(cavity_frequencies * 1e3, 2))
#

# print("cavity frequency for {}: {}".format(readout_qubit_label,
#                                            np.round((cavity_frequency_qubit(qubit_frequencies[readout_qubit_label],
#                                                                             readout_qubit_label,
#                                                                             cavity_dictionaries)) * 1e3,
#                                                     rounding_number)))






# qubit1_freq, qubit2_freq, qubit3_freq, qubit4_freq = Voltage_to_Freq([ -0.335, -0.388 + 0.0, 0, 0],list_of_dictionaries,  voltage_matrix, offset_vector)
# qubit_frequencies = {'qubit1': qubit1_freq, "qubit2": qubit2_freq, 'qubit3': qubit3_freq, 'qubit4': qubit4_freq}
# print(np.round( np.array([qubit1_freq, qubit2_freq, qubit3_freq, qubit4_freq]), 1))
# print("cavity frequency for {}: {}".format(readout_qubit_label,
#                                            np.round((cavity_frequency_qubit(qubit_frequencies[readout_qubit_label] / 1e3,
#                                                                             readout_qubit_label,
#                                                                             cavity_dictionaries)) * 1e3,
#                                                     rounding_number)))
# #
# print(offset_vector)
