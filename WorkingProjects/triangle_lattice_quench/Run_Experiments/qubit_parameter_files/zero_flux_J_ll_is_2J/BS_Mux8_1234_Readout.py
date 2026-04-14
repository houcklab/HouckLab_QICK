from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import BaseConfig
import numpy as np

# Leave this as such to ensure that we don't have to recalib pulses if
# we want to recalib 1234 readouts
# Readout_4Q = np.array([ -3201, -16560,  22421,  7239,  -5739, -10336,  20407,   -661]) #
# [3934, 3636, 4240, 4207, 3831, 3735, 4240, 3990]

# updated after copy
Readout_1234_FF = np.array([-6582, -16565, 9400, 400, -8754, -26060, 8407, -6026]) #
# [3849, 3636, 4175, 4053, 3754, 3495, 4126, 3899]
BS1234_Readout = {
    '1': {'Readout': {'Frequency': 7121.4, 'Gain': 1400,
                      'FF_Gains': Readout_1234_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3847.8, 'sigma': 0.015, 'Gain': 19246},
          'Pulse_FF': Readout_1234_FF},
    '2': {'Readout': {'Frequency': 7077.0, 'Gain': 2400,
                      'FF_Gains': Readout_1234_FF, 'Readout_Time': 2, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3634.0, 'sigma': 0.01, 'Gain': 9761},
          'Pulse_FF': Readout_1234_FF},
    '3': {'Readout': {'Frequency': 7511.4, 'Gain': 1500,
                      'FF_Gains': Readout_1234_FF, 'Readout_Time': 2, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4136.7, 'sigma': 0.02, 'Gain': 8862},
          'Pulse_FF': Readout_1234_FF},
    '4': {'Readout': {'Frequency': 7568.4, 'Gain': 2000,
                      'FF_Gains': Readout_1234_FF, 'Readout_Time': 2, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4003.1, 'sigma': 0.01, 'Gain': 18350},
          'Pulse_FF': Readout_1234_FF},
    '5': {'Readout': {'Frequency': 7362.85, 'Gain': 1500,
                      'FF_Gains': Readout_1234_FF, 'Readout_Time': 2, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3754.6, 'sigma': 0.015, 'Gain': 7189},
          'Pulse_FF': Readout_1234_FF},
    '6': {'Readout': {'Frequency': 7440.85, 'Gain': 1500,
                      'FF_Gains': Readout_1234_FF, 'Readout_Time': 2, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3500.0, 'sigma': 0.01, 'Gain': 25406},
          'Pulse_FF': Readout_1234_FF},
    '7': {'Readout': {'Frequency': 7254.4, 'Gain': 900,
                      'FF_Gains': Readout_1234_FF, 'Readout_Time': 2, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4109.7, 'sigma': 0.01, 'Gain': 9210},
          'Pulse_FF': Readout_1234_FF},
    '8': {'Readout': {'Frequency': 7308.9, 'Gain': 1500,
                      'FF_Gains': Readout_1234_FF, 'Readout_Time': 2.5, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3859.3, 'sigma': 0.01, 'Gain': 13773},
          'Pulse_FF': Readout_1234_FF},
}


# this was from an older config file where all neighbors are 300 MHz away from each other

# Readout_1234_FF = np.array([-12706,   4899,  13421,  -4010,  -8537,  20543,   3328, -17003])
Readout_4Q = np.array([-12706,   4899,  13421,  -4010,  -8537,  20543,   3328, -17003])
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
