from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import BaseConfig
import numpy as np


# (3950.0, 3700.0, 4380.0, 4150.0, 3550.0, 3800.0, 4300.0, 4050.0)
Readout_1234_FF = np.array([-4000, -17218, 25392, 5500, -7419, -13000, 19191, 1800]) #




Readout_1234_FF = np.array(Readout_1234_FF)


# this was from an older config file where all neighbors are 300 MHz away from each other
# Readout_1234_FF = np.array([-8464, -27262, 9303, -5379, -16232, 16903, 584, -12960])
# (3830.0, 3530.0, 4230.0, 3930.0, 3630.0, 4330.0, 3980.0, 3680.0)



BS1234_Readout = {
    '1': {'Readout': {'Frequency': 7121.4, 'Gain': 714,
                      'FF_Gains': Readout_1234_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3925.7, 'sigma': 0.03, 'Gain': 5732},
          'Pulse_FF': Readout_1234_FF},
    '2': {'Readout': {'Frequency': 7077.0, 'Gain': 1100,
                      'FF_Gains': Readout_1234_FF, 'Readout_Time': 2, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3626.5, 'sigma': 0.03, 'Gain': 4650},
          'Pulse_FF': Readout_1234_FF},
    '3': {'Readout': {'Frequency': 7511.6, 'Gain': 714,
                      'FF_Gains': Readout_1234_FF, 'Readout_Time': 2, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4340.2, 'sigma': 0.03, 'Gain': 12196},
          'Pulse_FF': Readout_1234_FF},
    '4': {'Readout': {'Frequency': 7568.4, 'Gain': 1400,
                      'FF_Gains': Readout_1234_FF, 'Readout_Time': 2, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4144.7, 'sigma': 0.03, 'Gain': 6556},
          'Pulse_FF': Readout_1234_FF},
    '5': {'Readout': {'Frequency': 7362.9, 'Gain': 1000,
                      'FF_Gains': Readout_1234_FF, 'Readout_Time': 2, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3802.0, 'sigma': 0.03, 'Gain': 7999},
          'Pulse_FF': Readout_1234_FF},
    '6': {'Readout': {'Frequency': 7441.0, 'Gain': 820,
                      'FF_Gains': Readout_1234_FF, 'Readout_Time': 2, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3683.6, 'sigma': 0.03, 'Gain': 5633},
          'Pulse_FF': Readout_1234_FF},
    '7': {'Readout': {'Frequency': 7254.3, 'Gain': 1400,
                      'FF_Gains': Readout_1234_FF, 'Readout_Time': 2, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4277.3, 'sigma': 0.03, 'Gain': 4907},
          'Pulse_FF': Readout_1234_FF},
    '8': {'Readout': {'Frequency': 7309.4, 'Gain': 1057,
                      'FF_Gains': Readout_1234_FF, 'Readout_Time': 2.5, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4085.3, 'sigma': 0.03, 'Gain': 5150},
          'Pulse_FF': Readout_1234_FF},
}



# old
# BS1234_Readout = {
#     '1': {'Readout': {'Frequency': 7121.1, 'Gain': 1400,
#                       'FF_Gains': Readout_1234_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
#           'Qubit': {'Frequency': 3824.6, 'sigma': 0.03, 'Gain': 6046},
#           'Pulse_FF': Readout_1234_FF},
#     '2': {'Readout': {'Frequency': 7076.6, 'Gain': 1400,
#                       'FF_Gains': Readout_1234_FF, 'Readout_Time': 2, 'ADC_Offset': 1},
#           'Qubit': {'Frequency': 3533.5, 'sigma': 0.03, 'Gain': 3862},
#           'Pulse_FF': Readout_1234_FF},
#     '3': {'Readout': {'Frequency': 7510.9, 'Gain': 1057,
#                       'FF_Gains': Readout_1234_FF, 'Readout_Time': 2, 'ADC_Offset': 1},
#           'Qubit': {'Frequency': 4237.1, 'sigma': 0.03, 'Gain': 12000},
#           'Pulse_FF': Readout_1234_FF},
#     '4': {'Readout': {'Frequency': 7568.1, 'Gain': 1228,
#                       'FF_Gains': Readout_1234_FF, 'Readout_Time': 2, 'ADC_Offset': 1},
#           'Qubit': {'Frequency': 3924.3, 'sigma': 0.03, 'Gain': 7834},
#           'Pulse_FF': Readout_1234_FF},
#     '5': {'Readout': {'Frequency': 7362.9, 'Gain': 1400,
#                       'FF_Gains': Readout_1234_FF, 'Readout_Time': 2.5, 'ADC_Offset': 1},
#           'Qubit': {'Frequency': 3633.7, 'sigma': 0.03, 'Gain': 7558},
#           'Pulse_FF': Readout_1234_FF},
#     '6': {'Readout': {'Frequency': 7442.1, 'Gain': 1400,
#                       'FF_Gains': Readout_1234_FF, 'Readout_Time': 2, 'ADC_Offset': 1},
#           'Qubit': {'Frequency': 4338.3, 'sigma': 0.03, 'Gain': 6029},
#           'Pulse_FF': Readout_1234_FF},
#     '7': {'Readout': {'Frequency': 7253.8, 'Gain': 885,
#                       'FF_Gains': Readout_1234_FF, 'Readout_Time': 2, 'ADC_Offset': 1},
#           'Qubit': {'Frequency': 3984.0, 'sigma': 0.03, 'Gain': 7230},
#           'Pulse_FF': Readout_1234_FF},
#     '8': {'Readout': {'Frequency': 7308.9, 'Gain': 1400,
#                       'FF_Gains': Readout_1234_FF, 'Readout_Time': 2.5, 'ADC_Offset': 1},
#           'Qubit': {'Frequency': 3690.1, 'sigma': 0.03, 'Gain': 6001},
#           'Pulse_FF': Readout_1234_FF},
# }



