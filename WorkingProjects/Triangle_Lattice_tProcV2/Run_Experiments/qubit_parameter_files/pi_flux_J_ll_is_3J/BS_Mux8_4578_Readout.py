from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import BaseConfig
import numpy as np



Readout_4578_FF = np.array(
    [-26873,   2505,  25392, -22000,  -1581,  13799, -21000,  -6388])
# (3535.3, 4100.0, 4389.6, 3640.0, 3900.0, 4300.0, 3460.3, 4000.0)

BS4578_Readout = {
    '1': {'Readout': {'Frequency': 7121.0, 'Gain': 1116,
                      'FF_Gains': Readout_4578_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3539.5, 'sigma': 0.03, 'Gain': 3173},
          'Pulse_FF': Readout_4578_FF},
    '2': {'Readout': {'Frequency': 7077.6, 'Gain': 750,
                      'FF_Gains': Readout_4578_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4109.5, 'sigma': 0.03, 'Gain': 8483},
          'Pulse_FF': Readout_4578_FF},
    '3': {'Readout': {'Frequency': 7511.6, 'Gain': 1000,
                      'FF_Gains': Readout_4578_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4406.9, 'sigma': 0.03, 'Gain': 9744},
          'Pulse_FF': Readout_4578_FF},
    '4': {'Readout': {'Frequency': 7568.1, 'Gain': 1216,
                      'FF_Gains': Readout_4578_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3591.3, 'sigma': 0.03, 'Gain': 8706},
          'Pulse_FF': Readout_4578_FF},
    '5': {'Readout': {'Frequency': 7362.9, 'Gain': 1216,
                      'FF_Gains': Readout_4578_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4004.3, 'sigma': 0.03, 'Gain': 6252},
          'Pulse_FF': Readout_4578_FF},
    '6': {'Readout': {'Frequency': 7441.6, 'Gain': 1216,
                      'FF_Gains': Readout_4578_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4301.6, 'sigma': 0.03, 'Gain': 5415},
          'Pulse_FF': Readout_4578_FF},
    '7': {'Readout': {'Frequency': 7253.4, 'Gain': 900,
                      'FF_Gains': Readout_4578_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3499.7, 'sigma': 0.03, 'Gain': 17175},
          'Pulse_FF': Readout_4578_FF},
    '8': {'Readout': {'Frequency': 7308.8, 'Gain': 850,
                      'FF_Gains': Readout_4578_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
                'Qubit': {'Frequency': 3880.4, 'sigma': 0.03, 'Gain': 5129},
          'Pulse_FF': Readout_4578_FF},
}
