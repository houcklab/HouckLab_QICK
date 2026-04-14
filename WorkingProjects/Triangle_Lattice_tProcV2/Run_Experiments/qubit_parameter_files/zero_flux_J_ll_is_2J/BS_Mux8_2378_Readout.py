from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import BaseConfig
import numpy as np



# [3511, 3912, 4195, 3588, 3751, 3836, 4001, 4240]
Readout_2378_FF = np.array([-26873,  -4342,  11421, -17948,  -8885,  -5901,   2926,  11232])



BS2378_Readout = {
    '1': {'Readout': {'Frequency': 7120.92, 'Gain': 1500,
                      'FF_Gains': Readout_2378_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3511.5, 'sigma': 0.01, 'Gain': 10828},
          'Pulse_FF': Readout_2378_FF},
    '2': {'Readout': {'Frequency': 7077.55, 'Gain': 1900,
                      'FF_Gains': Readout_2378_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3911.5, 'sigma': 0.01, 'Gain': 10000},
          'Pulse_FF': Readout_2378_FF},
    '3': {'Readout': {'Frequency': 7511.25, 'Gain': 1700,
                      'FF_Gains': Readout_2378_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4160.4, 'sigma': 0.01, 'Gain': 20000},
          'Pulse_FF': Readout_2378_FF},
    '4': {'Readout': {'Frequency': 7567.8, 'Gain': 1800,
                      'FF_Gains': Readout_2378_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3584.0, 'sigma': 0.01, 'Gain': 18500},
          'Pulse_FF': Readout_2378_FF},
    '5': {'Readout': {'Frequency': 7362.85, 'Gain': 1800,
                      'FF_Gains': Readout_2378_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3747.0, 'sigma': 0.01, 'Gain': 12281},
          'Pulse_FF': Readout_2378_FF},
    '6': {'Readout': {'Frequency': 7441.1, 'Gain': 1900,
                      'FF_Gains': Readout_2378_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3833.9, 'sigma': 0.01, 'Gain': 12000},
          'Pulse_FF': Readout_2378_FF},
    '7': {'Readout': {'Frequency': 7254.0, 'Gain': 1100,
                      'FF_Gains': Readout_2378_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3996.6, 'sigma': 0.01, 'Gain': 7052},
          'Pulse_FF': Readout_2378_FF},
    '8': {'Readout': {'Frequency': 7309.6, 'Gain': 1400,
                      'FF_Gains': Readout_2378_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4242.9, 'sigma': 0.015, 'Gain': 19100},
          'Pulse_FF': Readout_2378_FF},

}

