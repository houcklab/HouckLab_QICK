from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import BaseConfig
import numpy as np

# Leave this as such to ensure that we don't have to recalib pulses if
# we want to recalib 1234 readouts
Readout_4Q = np.array([-4441, -18120, 25392, 4879, -8117, -12750, 18637, -2500]) #
# (3950.0, 3700.0, 4380.0, 4150.0, 3550.0, 3800.0, 4300.0, 4050.0)

# updated after copy
Readout_1234_FF = np.array([-4441, -18120, 25392, 4879, -8117, -12750, 18637, -2500]) #

Readout_1234_FF = np.array(Readout_1234_FF)



BS1234_Readout = {
    '1': {'Readout': {'Frequency': 7121.4, 'Gain': 676,
                      'FF_Gains': Readout_1234_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3934.2, 'sigma': 0.03, 'Gain': 4842},
          'Pulse_FF': Readout_1234_FF},
    '2': {'Readout': {'Frequency': 7076.9, 'Gain': 1100,
                      'FF_Gains': Readout_1234_FF, 'Readout_Time': 2, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3636.1, 'sigma': 0.03, 'Gain': 5030},
          'Pulse_FF': Readout_1234_FF},
    '3': {'Readout': {'Frequency': 7511.3, 'Gain': 1000,
                      'FF_Gains': Readout_1234_FF, 'Readout_Time': 2, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4405.7, 'sigma': 0.03, 'Gain': 9570},
          'Pulse_FF': Readout_1234_FF},
    '4': {'Readout': {'Frequency': 7568.4, 'Gain': 1100,
                      'FF_Gains': Readout_1234_FF, 'Readout_Time': 2, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4187.4, 'sigma': 0.03, 'Gain': 6570},
          'Pulse_FF': Readout_1234_FF},
    '5': {'Readout': {'Frequency': 7362.8, 'Gain': 1100,
                      'FF_Gains': Readout_1234_FF, 'Readout_Time': 2, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3831.4, 'sigma': 0.03, 'Gain': 14170},
          'Pulse_FF': Readout_1234_FF},
    '6': {'Readout': {'Frequency': 7441.2, 'Gain': 633,
                      'FF_Gains': Readout_1234_FF, 'Readout_Time': 2, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3733.2, 'sigma': 0.03, 'Gain': 5933},
          'Pulse_FF': Readout_1234_FF},
    '7': {'Readout': {'Frequency': 7254.3, 'Gain': 800,
                      'FF_Gains': Readout_1234_FF, 'Readout_Time': 2, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4305.2, 'sigma': 0.03, 'Gain': 6726},
          'Pulse_FF': Readout_1234_FF},
    '8': {'Readout': {'Frequency': 7309.0, 'Gain': 480,
                      'FF_Gains': Readout_1234_FF, 'Readout_Time': 2.5, 'ADC_Offset': 1},
           'Qubit': {'Frequency': 3993.3, 'sigma': 0.03, 'Gain': 6687},
          'Pulse_FF': Readout_1234_FF},
}


# this was from an older config file where all neighbors are 300 MHz away from each other

Readout_1234_FF = np.array([-4711, -29001, 25392, 2830, -16738, -8417, 25722, -1899])
# (3930.0, 3547.6, 4150.0, 4200, 3630.0, 3850, 4332.6, 4100.0)
BS1234_Readout = {
    '1': {'Readout': {'Frequency': 7121.4, 'Gain': 650,
                      'FF_Gains': Readout_1234_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3927.9, 'sigma': 0.03, 'Gain': 4912},
          'Pulse_FF': Readout_1234_FF},
    '2': {'Readout': {'Frequency': 7076.85, 'Gain': 816,
                      'FF_Gains': Readout_1234_FF, 'Readout_Time': 2, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3532.5, 'sigma': 0.03, 'Gain': 3954},
          'Pulse_FF': Readout_1234_FF},
    '3': {'Readout': {'Frequency': 7511.4, 'Gain': 916,
                      'FF_Gains': Readout_1234_FF, 'Readout_Time': 2, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4405.6, 'sigma': 0.03, 'Gain': 10300},
          'Pulse_FF': Readout_1234_FF},
    '4': {'Readout': {'Frequency': 7568.3, 'Gain': 1000,
                      'FF_Gains': Readout_1234_FF, 'Readout_Time': 2, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4140.6, 'sigma': 0.03, 'Gain': 9189},
          'Pulse_FF': Readout_1234_FF},
    '5': {'Readout': {'Frequency': 7362.65, 'Gain': 1100,
                      'FF_Gains': Readout_1234_FF, 'Readout_Time': 2.5, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3633.8, 'sigma': 0.03, 'Gain': 7961},
          'Pulse_FF': Readout_1234_FF},
    '6': {'Readout': {'Frequency': 7441.1, 'Gain': 833,
                      'FF_Gains': Readout_1234_FF, 'Readout_Time': 2, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3831.3, 'sigma': 0.03, 'Gain': 5353},
          'Pulse_FF': Readout_1234_FF},
    '7': {'Readout': {'Frequency': 7254.6, 'Gain': 1000,
                      'FF_Gains': Readout_1234_FF, 'Readout_Time': 2, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4333.5, 'sigma': 0.03, 'Gain': 7140},
          'Pulse_FF': Readout_1234_FF},
    '8': {'Readout': {'Frequency': 7308.9, 'Gain': 850,
                      'FF_Gains': Readout_1234_FF, 'Readout_Time': 2.5, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4011.1, 'sigma': 0.03, 'Gain': 5140},
          'Pulse_FF': Readout_1234_FF},
}


# Readout_1234_FF = np.array([-8632, -29001, 9109, -3000, -16738, 16185, -484, -13141])
# (3830.0, 3530.0, 4230.0, 3930.0, 3630.0, 4330.0, 3980.0, 3680.0)

# old
# BS1234_Readout = {
#     '1': {'Readout': {'Frequency': 7121.2, 'Gain': 666,
#                       'FF_Gains': Readout_1234_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
#           'Qubit': {'Frequency': 3826.6, 'sigma': 0.03, 'Gain': 6000},
#           'Pulse_FF': Readout_1234_FF},
#     '2': {'Readout': {'Frequency': 7076.8, 'Gain': 1016,
#                       'FF_Gains': Readout_1234_FF, 'Readout_Time': 2, 'ADC_Offset': 1},
#           'Qubit': {'Frequency': 3539.6, 'sigma': 0.03, 'Gain': 4041},
#           'Pulse_FF': Readout_1234_FF},
#     '3': {'Readout': {'Frequency': 7511.1, 'Gain': 653,
#                       'FF_Gains': Readout_1234_FF, 'Readout_Time': 2, 'ADC_Offset': 1},
#           'Qubit': {'Frequency': 4237.7, 'sigma': 0.03, 'Gain': 13000},
#           'Pulse_FF': Readout_1234_FF},
#     '4': {'Readout': {'Frequency': 7568.1, 'Gain': 1033,
#                       'FF_Gains': Readout_1234_FF, 'Readout_Time': 2, 'ADC_Offset': 1},
#           'Qubit': {'Frequency': 3995.9, 'sigma': 0.03, 'Gain': 13000},
#           'Pulse_FF': Readout_1234_FF},
#     '5': {'Readout': {'Frequency': 7362.6, 'Gain': 1100,
#                       'FF_Gains': Readout_1234_FF, 'Readout_Time': 2.5, 'ADC_Offset': 1},
#           'Qubit': {'Frequency': 3634.4, 'sigma': 0.03, 'Gain': 7996},
#           'Pulse_FF': Readout_1234_FF},
#     '6': {'Readout': {'Frequency': 7441.65, 'Gain': 750,
#                       'FF_Gains': Readout_1234_FF, 'Readout_Time': 2, 'ADC_Offset': 1},
#           'Qubit': {'Frequency': 4332.6, 'sigma': 0.03, 'Gain': 6084},
#           'Pulse_FF': Readout_1234_FF},
#     '7': {'Readout': {'Frequency': 7253.8, 'Gain': 647,
#                       'FF_Gains': Readout_1234_FF, 'Readout_Time': 2, 'ADC_Offset': 1},
#           'Qubit': {'Frequency': 3958.8, 'sigma': 0.03, 'Gain': 6481},
#           'Pulse_FF': Readout_1234_FF},
#     '8': {'Readout': {'Frequency': 7308.6, 'Gain': 1000,
#                       'FF_Gains': Readout_1234_FF, 'Readout_Time': 2.5, 'ADC_Offset': 1},
#           'Qubit': {'Frequency': 3696.8, 'sigma': 0.03, 'Gain': 5804},
#           'Pulse_FF': Readout_1234_FF},
# }



