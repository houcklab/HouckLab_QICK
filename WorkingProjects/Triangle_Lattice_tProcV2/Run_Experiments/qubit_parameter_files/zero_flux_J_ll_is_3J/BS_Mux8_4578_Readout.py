from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import BaseConfig
import numpy as np



Readout_4578_FF = np.array([-25873,   -3818,  11421, -18769,   -3364,  9356, -24722,  -8690])
# [3512, 3947, 4219, 3573, 3891, 4175, 3438, 3767]

BS4578_Readout = {
    '1': {'Readout': {'Frequency': 7121.05, 'Gain': 1250,
                      'FF_Gains': Readout_4578_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3513.0, 'sigma': 0.01, 'Gain': 10598},
          'Pulse_FF': Readout_4578_FF},
    '2': {'Readout': {'Frequency': 7077.4, 'Gain': 1750,
                      'FF_Gains': Readout_4578_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3927.4, 'sigma': 0.01, 'Gain': 8840},
          'Pulse_FF': Readout_4578_FF},
    '3': {'Readout': {'Frequency': 7511.35, 'Gain': 1500,
                      'FF_Gains': Readout_4578_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4164.1, 'sigma': 0.015, 'Gain': 11020},
          'Pulse_FF': Readout_4578_FF},
    '4': {'Readout': {'Frequency': 7567.8, 'Gain': 1500,
                      'FF_Gains': Readout_4578_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3574.5, 'sigma': 0.01, 'Gain': 16664},
          'Pulse_FF': Readout_4578_FF},
    '5': {'Readout': {'Frequency': 7363.2, 'Gain': 1700,
                      'FF_Gains': Readout_4578_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3896.0, 'sigma': 0.01, 'Gain': 9380},
          'Pulse_FF': Readout_4578_FF},
    '6': {'Readout': {'Frequency': 7441.65, 'Gain': 1500,
                      'FF_Gains': Readout_4578_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4126.3, 'sigma': 0.01, 'Gain': 20773},
          'Pulse_FF': Readout_4578_FF},
    '7': {'Readout': {'Frequency': 7253.4, 'Gain': 1500,
                      'FF_Gains': Readout_4578_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3441.6, 'sigma': 0.01, 'Gain': 7873},
          'Pulse_FF': Readout_4578_FF},
    '8': {'Readout': {'Frequency': 7308.7, 'Gain': 1800,
                      'FF_Gains': Readout_4578_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3780.9, 'sigma': 0.01, 'Gain': 20800},
          'Pulse_FF': Readout_4578_FF},

}
