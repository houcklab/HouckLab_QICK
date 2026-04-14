from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import BaseConfig
import numpy as np



# [3511, 3953, 4175, 3648, 3823, 4239, 3581, 3889]

Readout_2356_FF = np.array([-26873,   -3584,  11400,  -14883,   -6067,  20356, -13960,  -5381])



BS2356_Readout = {
    '1': {'Readout': {'Frequency': 7121.0, 'Gain': 1800,
                      'FF_Gains': Readout_2356_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3511.7, 'sigma': 0.01, 'Gain': 10788},
          'Pulse_FF': Readout_2356_FF},
    '2': {'Readout': {'Frequency': 7077.35, 'Gain': 1700,
                      'FF_Gains': Readout_2356_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3928.7, 'sigma': 0.01, 'Gain': 8600},
          'Pulse_FF': Readout_2356_FF},
    '3': {'Readout': {'Frequency': 7511.4, 'Gain': 1200,
                      'FF_Gains': Readout_2356_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4162.5, 'sigma': 0.01, 'Gain': 20505},
          'Pulse_FF': Readout_2356_FF},
    '4': {'Readout': {'Frequency': 7567.85, 'Gain': 2200,
                      'FF_Gains': Readout_2356_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3640.1, 'sigma': 0.01, 'Gain': 15599},
          'Pulse_FF': Readout_2356_FF},
    '5': {'Readout': {'Frequency': 7363.15, 'Gain': 1200,
                      'FF_Gains': Readout_2356_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3826.6, 'sigma': 0.01, 'Gain': 24310},
          'Pulse_FF': Readout_2356_FF},
    '6': {'Readout': {'Frequency': 7442.0, 'Gain': 1500,
                      'FF_Gains': Readout_2356_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4232.3, 'sigma': 0.01, 'Gain': 20713},
          'Pulse_FF': Readout_2356_FF},
    '7': {'Readout': {'Frequency': 7253.4, 'Gain': 1500,
                      'FF_Gains': Readout_2356_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3579.2, 'sigma': 0.01, 'Gain': 11130},
          'Pulse_FF': Readout_2356_FF},
    '8': {'Readout': {'Frequency': 7308.9, 'Gain': 1500,
                      'FF_Gains': Readout_2356_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3877.7, 'sigma': 0.01, 'Gain': 13550},
          'Pulse_FF': Readout_2356_FF},

}

