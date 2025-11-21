from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import BaseConfig
import numpy as np



# (3535.3, 4100.0, 4389.6, 3640.0, 3900.0, 4300.0, 3460.3, 4000.0)
Readout_4578_FF = np.array(
    # [-26873, 2277, 25392, -17533, -1000, 14426, -25722, -5631]
    [-20326, 2277, 25392, -14533, -1000, 14426, -17722, -5631]
)


BS4578_Readout = {
    '1': {'Readout': {'Frequency': 7121.04, 'Gain': 900,
                      'FF_Gains': Readout_4578_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3562.3, 'sigma': 0.03, 'Gain': 7871},
          'Pulse_FF': Readout_4578_FF},
    '2': {'Readout': {'Frequency': 7077.9, 'Gain': 1228,
                      'FF_Gains': Readout_4578_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4075.7, 'sigma': 0.03, 'Gain': 4800},
          'Pulse_FF': Readout_4578_FF},
    '3': {'Readout': {'Frequency': 7511.7, 'Gain': 885,
                      'FF_Gains': Readout_4578_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4341.0, 'sigma': 0.03, 'Gain': 10813},
          'Pulse_FF': Readout_4578_FF},
    '4': {'Readout': {'Frequency': 7567.6, 'Gain': 1100,
                      'FF_Gains': Readout_4578_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3658.8, 'sigma': 0.03, 'Gain': 5654},
          'Pulse_FF': Readout_4578_FF},
    '5': {'Readout': {'Frequency': 7362.9, 'Gain': 1057,
                      'FF_Gains': Readout_4578_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3971.2, 'sigma': 0.03, 'Gain': 9325},
          'Pulse_FF': Readout_4578_FF},
    '6': {'Readout': {'Frequency': 7442.0, 'Gain': 1100,
                      'FF_Gains': Readout_4578_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4250.6, 'sigma': 0.03, 'Gain': 8817},
          'Pulse_FF': Readout_4578_FF},
    '7': {'Readout': {'Frequency': 7253.4, 'Gain': 714,
                      'FF_Gains': Readout_4578_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3511.4, 'sigma': 0.03, 'Gain': 12439},
          'Pulse_FF': Readout_4578_FF},
    '8': {'Readout': {'Frequency': 7308.8, 'Gain': 1057,
                      'FF_Gains': Readout_4578_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3879.5, 'sigma': 0.03, 'Gain': 6076},
          'Pulse_FF': Readout_4578_FF},
}
