from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import BaseConfig
import numpy as np

# Leave this as such to ensure that we don't have to recalib pulses if
# we want to recalib 1234 readouts
# Readout_4Q = np.array([ -3201, -16560,  22421,  7239,  -5739, -10336,  20407,   -661]) #
# [3934, 3636, 4240, 4207, 3831, 3735, 4240, 3990]

# updated after copy
Readout_1234_FF = np.array([-6582, -16565, 4400, -1600, -9754, -26060, 2407, -8526]) #
# [3842, 3632, 4082, 3978, 3745, 3490, 4049, 3795]
BS1234_Readout = {
    '1': {'Readout': {'Frequency': 7121.4, 'Gain': 1700,
                      'FF_Gains': Readout_1234_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3834.4, 'sigma': 0.015, 'Gain': 14666},
          'Pulse_FF': Readout_1234_FF},
    '2': {'Readout': {'Frequency': 7077.15, 'Gain': 2400,
                      'FF_Gains': Readout_1234_FF, 'Readout_Time': 2, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3626.5, 'sigma': 0.01, 'Gain': 8638},
          'Pulse_FF': Readout_1234_FF},
    '3': {'Readout': {'Frequency': 7511.2, 'Gain': 1200,
                      'FF_Gains': Readout_1234_FF, 'Readout_Time': 2, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4013.7, 'sigma': 0.02, 'Gain': 9944},
          'Pulse_FF': Readout_1234_FF},
    '4': {'Readout': {'Frequency': 7568.2, 'Gain': 2400,
                      'FF_Gains': Readout_1234_FF, 'Readout_Time': 2, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3931.9, 'sigma': 0.01, 'Gain': 12000},
          'Pulse_FF': Readout_1234_FF},
    '5': {'Readout': {'Frequency': 7362.9, 'Gain': 2400,
                      'FF_Gains': Readout_1234_FF, 'Readout_Time': 2, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3714.0, 'sigma': 0.015, 'Gain': 18370},
          'Pulse_FF': Readout_1234_FF},
    '6': {'Readout': {'Frequency': 7440.9, 'Gain': 2100,
                      'FF_Gains': Readout_1234_FF, 'Readout_Time': 2, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3493.5, 'sigma': 0.02, 'Gain': 12613},
          'Pulse_FF': Readout_1234_FF},
    '7': {'Readout': {'Frequency': 7253.9, 'Gain': 1500,
                      'FF_Gains': Readout_1234_FF, 'Readout_Time': 2, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3976.6, 'sigma': 0.01, 'Gain': 6713},
          'Pulse_FF': Readout_1234_FF},
    '8': {'Readout': {'Frequency': 7308.6, 'Gain': 1800,
                      'FF_Gains': Readout_1234_FF, 'Readout_Time': 2.5, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3777.7, 'sigma': 0.01, 'Gain': 17336},
          'Pulse_FF': Readout_1234_FF},
}


# this was from an older config file where all neighbors are 300 MHz away from each other

# Readout_1234_FF = np.array([-12706,   4899,  13421,  -4010,  -8537,  20543,   3328, -17003])
# Readout_4Q = np.array([-12706,   4899,  13421,  -4010,  -8537,  20543,   3328, -17003])
# [3708, 4138, 4353, 3929, 3779, 4250, 4030, 3576]
# BS1234_Readout = {
#     '1': {'Readout': {'Frequency': 7121.0, 'Gain': 666,
#                       'FF_Gains': Readout_1234_FF, 'Readout_Time': 3.3, 'ADC_Offset': 0.9},
#           'Qubit': {'Frequency': 3697.7, 'sigma': 0.01, 'Gain': 9298},
#           'Pulse_FF': Readout_1234_FF},
#     '2': {'Readout': {'Frequency': 7077.8, 'Gain': 1000,
#                       'FF_Gains': Readout_1234_FF, 'Readout_Time': 2.3, 'ADC_Offset': 0.9},
#           'Qubit': {'Frequency': 4107.8, 'sigma': 0.01, 'Gain': 8532},
#           'Pulse_FF': Readout_1234_FF},
#     '3': {'Readout': {'Frequency': 7511.4, 'Gain': 850,
#                       'FF_Gains': Readout_1234_FF, 'Readout_Time': 2.3, 'ADC_Offset': 0.9},
#           'Qubit': {'Frequency': 4186.0, 'sigma': 0.01, 'Gain': 11874},
#           'Pulse_FF': Readout_1234_FF},
#     '4': {'Readout': {'Frequency': 7568.1, 'Gain': 1000,
#                       'FF_Gains': Readout_1234_FF, 'Readout_Time': 2.3, 'ADC_Offset': 0.9},
#           'Qubit': {'Frequency': 3895.0, 'sigma': 0.01, 'Gain': 10066},
#           'Pulse_FF': Readout_1234_FF},
#     '5': {'Readout': {'Frequency': 7362.85, 'Gain': 1033,
#                       'FF_Gains': Readout_1234_FF, 'Readout_Time': 2.8, 'ADC_Offset': 0.9},
#           'Qubit': {'Frequency': 3760.6, 'sigma': 0.01, 'Gain': 6469},
#           'Pulse_FF': Readout_1234_FF},
#     '6': {'Readout': {'Frequency': 7441.85, 'Gain': 1000,
#                       'FF_Gains': Readout_1234_FF, 'Readout_Time': 2.3, 'ADC_Offset': 0.9},
#           'Qubit': {'Frequency': 4237.9, 'sigma': 0.01, 'Gain': 11065},
#           'Pulse_FF': Readout_1234_FF},
#     '7': {'Readout': {'Frequency': 7254.15, 'Gain': 800,
#                       'FF_Gains': Readout_1234_FF, 'Readout_Time': 2.3, 'ADC_Offset': 0.9},
#           'Qubit': {'Frequency': 4012.0, 'sigma': 0.01, 'Gain': 2973},
#           'Pulse_FF': Readout_1234_FF},
#     '8': {'Readout': {'Frequency': 7308.6, 'Gain': 1000,
#                       'FF_Gains': Readout_1234_FF, 'Readout_Time': 2.8, 'ADC_Offset': 0.9},
#           'Qubit': {'Frequency': 3580.1, 'sigma': 0.01, 'Gain': 7881},
#           'Pulse_FF': Readout_1234_FF},
# }
#
# #
