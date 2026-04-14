from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import BaseConfig
import numpy as np

# Leave this as such to ensure that we don't have to recalib pulses if
# we want to recalib 1234 readouts
# Readout_4Q = np.array([ -3201, -16560,  22421,  7239,  -5739, -10336,  20407,   -661]) #
# [3934, 3636, 4240, 4207, 3831, 3735, 4240, 3990]

# updated after copy
Readout_1234_FF = np.array([-4361, 14824, -13961, 0, -3340, -20322, -3516, 9801])
# (3913.0, 4300.0, 3600.0, 3985.0, 4331.0, 3550.0, 3850.0, 4260.0)
BS1234_Readout = {
    '1': {'Readout': {'Frequency': 7121.3, 'Gain': 1200,
                      'FF_Gains': Readout_1234_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3912.2, 'sigma': 0.02, 'Gain': 4918},
          'Pulse_FF': Readout_1234_FF},
    '2': {'Readout': {'Frequency': 7077.9, 'Gain': 2400,
                      'FF_Gains': Readout_1234_FF, 'Readout_Time': 2.5, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4299.3, 'sigma': 0.02, 'Gain': 3421},
          'Pulse_FF': Readout_1234_FF},
    '3': {'Readout': {'Frequency': 7510.6, 'Gain': 1500,
                      'FF_Gains': Readout_1234_FF, 'Readout_Time': 2.5, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3599.7, 'sigma': 0.02, 'Gain': 13876},
          'Pulse_FF': Readout_1234_FF},
    '4': {'Readout': {'Frequency': 7568.4, 'Gain': 2100,
                      'FF_Gains': Readout_1234_FF, 'Readout_Time': 2.5, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4022.3, 'sigma': 0.02, 'Gain': 6821},
          'Pulse_FF': Readout_1234_FF},
    '5': {'Readout': {'Frequency': 7363.9, 'Gain': 2100,
                      'FF_Gains': Readout_1234_FF, 'Readout_Time': 2.5, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4353.6, 'sigma': 0.02, 'Gain': 4551},
          'Pulse_FF': Readout_1234_FF},
    '6': {'Readout': {'Frequency': 7440.9, 'Gain': 2100,
                      'FF_Gains': Readout_1234_FF, 'Readout_Time': 2.5, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3553.5, 'sigma': 0.02, 'Gain': 4904},
          'Pulse_FF': Readout_1234_FF},
    '7': {'Readout': {'Frequency': 7254.1, 'Gain': 1500,
                      'FF_Gains': Readout_1234_FF, 'Readout_Time': 2.5, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3853.5, 'sigma': 0.02, 'Gain': 4725},
          'Pulse_FF': Readout_1234_FF},
    '8': {'Readout': {'Frequency': 7309.4, 'Gain': 2100,
                      'FF_Gains': Readout_1234_FF, 'Readout_Time': 2.5, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4262.2, 'sigma': 0.02, 'Gain': 7314},
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
