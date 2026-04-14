from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import BaseConfig
import numpy as np



# [3809, 3564, 4085, 4273, 3629, 3953, 4240, 3499]
Readout_3467_FF = np.array([ -8205, -20801,  5347,  11105,  -24044,   -722,  20407, -14395])

BS3467_Readout = {
    '1': {'Readout': {'Frequency': 7121.35, 'Gain': 1500,
                      'FF_Gains': Readout_3467_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3807.8, 'sigma': 0.01, 'Gain': 8760},
          'Pulse_FF': Readout_3467_FF},
    '2': {'Readout': {'Frequency': 7076.9, 'Gain': 2300,
                      'FF_Gains': Readout_3467_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3567.8, 'sigma': 0.01, 'Gain': 12750},
          'Pulse_FF': Readout_3467_FF},
    '3': {'Readout': {'Frequency': 7511.0, 'Gain': 1000,
                      'FF_Gains': Readout_3467_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4066.1, 'sigma': 0.02, 'Gain': 17540},
          'Pulse_FF': Readout_3467_FF},
    '4': {'Readout': {'Frequency': 7568.7, 'Gain': 1800,
                      'FF_Gains': Readout_3467_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4194.1, 'sigma': 0.01, 'Gain': 10080},
          'Pulse_FF': Readout_3467_FF},
    '5': {'Readout': {'Frequency': 7362.75, 'Gain': 1500,
                      'FF_Gains': Readout_3467_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3501.4, 'sigma': 0.01, 'Gain': 19550},
          'Pulse_FF': Readout_3467_FF},
    '6': {'Readout': {'Frequency': 7441.4, 'Gain': 1500,
                      'FF_Gains': Readout_3467_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3943.5, 'sigma': 0.01, 'Gain': 12000},
          'Pulse_FF': Readout_3467_FF},
    '7': {'Readout': {'Frequency': 7254.4, 'Gain': 1400,
                      'FF_Gains': Readout_3467_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4238.0, 'sigma': 0.01, 'Gain': 6200},
          'Pulse_FF': Readout_3467_FF},
    '8': {'Readout': {'Frequency': 7308.6, 'Gain': 1900,
                      'FF_Gains': Readout_3467_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3638.0, 'sigma': 0.015, 'Gain': 13651},
          'Pulse_FF': Readout_3467_FF},
}

