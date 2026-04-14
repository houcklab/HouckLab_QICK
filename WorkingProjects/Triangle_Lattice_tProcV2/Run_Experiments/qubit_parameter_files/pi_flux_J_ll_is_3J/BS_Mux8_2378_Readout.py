from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import BaseConfig
import numpy as np



# (3580.0, 4150.0, 4380.0, 3770.0, 3690.0, 3850.0, 4000.0, 4280.0)
Readout_2378_FF = np.array([-26873,    969,  25392, -19000, -11206,  -8255,    266,   8206])



BS2378_Readout = {
    '1': {'Readout': {'Frequency': 7121.0, 'Gain': 1100,
                      'FF_Gains': Readout_2378_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3539.1, 'sigma': 0.03, 'Gain': 3135},
          'Pulse_FF': Readout_2378_FF},
    '2': {'Readout': {'Frequency': 7077.5, 'Gain': 760,
                      'FF_Gains': Readout_2378_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4075.1, 'sigma': 0.03, 'Gain': 5030},
          'Pulse_FF': Readout_2378_FF},
    '3': {'Readout': {'Frequency': 7511.6, 'Gain': 800,
                      'FF_Gains': Readout_2378_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4406.0, 'sigma': 0.03, 'Gain': 9790},
          'Pulse_FF': Readout_2378_FF},
    '4': {'Readout': {'Frequency': 7567.6, 'Gain': 1216,
                      'FF_Gains': Readout_2378_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3626.4, 'sigma': 0.03, 'Gain': 6875},
          'Pulse_FF': Readout_2378_FF},
    '5': {'Readout': {'Frequency': 7362.8, 'Gain': 1200,
                      'FF_Gains': Readout_2378_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3751.2, 'sigma': 0.03, 'Gain': 5677},
          'Pulse_FF': Readout_2378_FF},
    '6': {'Readout': {'Frequency': 7441.1, 'Gain': 850,
                      'FF_Gains': Readout_2378_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3836.9, 'sigma': 0.03, 'Gain': 6837},
          'Pulse_FF': Readout_2378_FF},
    '7': {'Readout': {'Frequency': 7253.8, 'Gain': 1033,
                      'FF_Gains': Readout_2378_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3978.4, 'sigma': 0.03, 'Gain': 7500},
          'Pulse_FF': Readout_2378_FF},
    '8': {'Readout': {'Frequency': 7309.2, 'Gain': 780,
                      'FF_Gains': Readout_2378_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4261.7, 'sigma': 0.03, 'Gain': 7693},
          'Pulse_FF': Readout_2378_FF},

}

