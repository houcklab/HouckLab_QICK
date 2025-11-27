from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import BaseConfig
import numpy as np


# (3950.0, 3700.0, 4380.0, 4150.0, 3550.0, 3800.0, 4300.0, 4050.0)
Readout_1234_FF = np.array([-4000, -17218, 25392, 5500, -7419, -13000, 19191, 0]) #




Readout_1234_FF = np.array(Readout_1234_FF)


# this was from an older config file where all neighbors are 300 MHz away from each other
# Readout_1234_FF = np.array([-8464, -27262, 9303, -5379, -16232, 16903, 584, -12960])
# (3830.0, 3530.0, 4230.0, 3930.0, 3630.0, 4330.0, 3980.0, 3680.0)



BS1234_Readout = {
    '1': {'Readout': {'Frequency': 7121.1, 'Gain': 885,
                      'FF_Gains': Readout_1234_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3938.3, 'sigma': 0.03, 'Gain': 5185},
          'Pulse_FF': Readout_1234_FF},
    '2': {'Readout': {'Frequency': 7077.2, 'Gain': 1000,
                      'FF_Gains': Readout_1234_FF, 'Readout_Time': 2, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3638.4, 'sigma': 0.03, 'Gain': 5052},
          'Pulse_FF': Readout_1234_FF},
    '3': {'Readout': {'Frequency': 7511.4, 'Gain': 750,
                      'FF_Gains': Readout_1234_FF, 'Readout_Time': 2, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4394.6, 'sigma': 0.03, 'Gain': 12386},
          'Pulse_FF': Readout_1234_FF},
    '4': {'Readout': {'Frequency': 7568.4, 'Gain': 1000,
                      'FF_Gains': Readout_1234_FF, 'Readout_Time': 2, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4187.0, 'sigma': 0.03, 'Gain': 6268},
          'Pulse_FF': Readout_1234_FF},
    '5': {'Readout': {'Frequency': 7362.9, 'Gain': 800,
                      'FF_Gains': Readout_1234_FF, 'Readout_Time': 2, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3829.4, 'sigma': 0.03, 'Gain': 12266},
          'Pulse_FF': Readout_1234_FF},
    '6': {'Readout': {'Frequency': 7441.0, 'Gain': 1000,
                      'FF_Gains': Readout_1234_FF, 'Readout_Time': 2, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3705.3, 'sigma': 0.03, 'Gain': 7090},
          'Pulse_FF': Readout_1234_FF},
    '7': {'Readout': {'Frequency': 7254.35, 'Gain': 700,
                      'FF_Gains': Readout_1234_FF, 'Readout_Time': 2, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4303.0, 'sigma': 0.03, 'Gain': 6326},
          'Pulse_FF': Readout_1234_FF},
    '8': {'Readout': {'Frequency': 7308.9, 'Gain': 885,
                      'FF_Gains': Readout_1234_FF, 'Readout_Time': 2.5, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4027.6, 'sigma': 0.03, 'Gain': 6598},
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



