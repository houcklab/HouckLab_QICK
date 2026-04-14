from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import BaseConfig
import numpy as np



# (3580.0, 4150.0, 4380.0, 3770.0, 4000.0, 4280.0, 3690.0, 3850.0)
Readout_2356_FF = np.array([-20357, 4582, 21495, -11609, -1488, 12985, -10406, -6771])

Readout_2356_FF = np.array([-20357, 4582, 21495, -11609, -1488, 12985, -12406, -6771])

Readout_2356_FF = np.array([-20357, 4582, 21495, -11609, -1488, 12000, -12406, -6771])


Readout_2356_FF = np.array([-20357, 4582, 21495, -11609, -1000, 12000, -12406, -6771])

Readout_2356_FF = np.array([-26873,   4054,  25392, -10000,  -3620,  12500, -14436,  -5165])



BS2356_Readout = {
    '1': {'Readout': {'Frequency': 7121.0, 'Gain': 850,
                      'FF_Gains': Readout_2356_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3539.3, 'sigma': 0.03, 'Gain': 3222},
          'Pulse_FF': Readout_2356_FF},
    '2': {'Readout': {'Frequency': 7077.9, 'Gain': 833,
                      'FF_Gains': Readout_2356_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4141.3, 'sigma': 0.03, 'Gain': 4500},
          'Pulse_FF': Readout_2356_FF},
    '3': {'Readout': {'Frequency': 7511.4, 'Gain': 440,
                      'FF_Gains': Readout_2356_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4406.4, 'sigma': 0.03, 'Gain': 9654},
          'Pulse_FF': Readout_2356_FF},
    '4': {'Readout': {'Frequency': 7568.1, 'Gain': 1216,
                      'FF_Gains': Readout_2356_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3814.5, 'sigma': 0.03, 'Gain': 5333},
          'Pulse_FF': Readout_2356_FF},
    '5': {'Readout': {'Frequency': 7363.0, 'Gain': 850,
                      'FF_Gains': Readout_2356_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3952.8, 'sigma': 0.03, 'Gain': 9665},
          'Pulse_FF': Readout_2356_FF},
    '6': {'Readout': {'Frequency': 7441.7, 'Gain': 850,
                      'FF_Gains': Readout_2356_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4282.1, 'sigma': 0.03, 'Gain': 8092},
          'Pulse_FF': Readout_2356_FF},
    '7': {'Readout': {'Frequency': 7253.6, 'Gain': 816,
                      'FF_Gains': Readout_2356_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3603.7, 'sigma': 0.03, 'Gain': 6803},
          'Pulse_FF': Readout_2356_FF},
    '8': {'Readout': {'Frequency': 7308.9, 'Gain': 666,
                      'FF_Gains': Readout_2356_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3917.0, 'sigma': 0.03, 'Gain': 7500},
          'Pulse_FF': Readout_2356_FF},
}

