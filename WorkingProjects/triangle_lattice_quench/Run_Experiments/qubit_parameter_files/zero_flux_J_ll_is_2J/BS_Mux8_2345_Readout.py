from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import BaseConfig
import numpy as np



Readout_2345_FF = np.array([-11636, 2296, 23900, -7061, -14428, 9517, 843, -21379])

# (3725.0, 4060.0, 4240.0, 3835.0, 3621.0, 4139.0, 3953.0, 3512.0)
BS2345_Readout = {
    '1': {'Readout': {'Frequency': 7121.4, 'Gain': 1200,
                      'FF_Gains': Readout_2345_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3718.5, 'sigma': 0.01, 'Gain': 22702},
          'Pulse_FF': Readout_2345_FF},
    '2': {'Readout': {'Frequency': 7077.8, 'Gain': 1900,
                      'FF_Gains': Readout_2345_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4059.1, 'sigma': 0.01, 'Gain': 10100},
          'Pulse_FF': Readout_2345_FF},
    '3': {'Readout': {'Frequency': 7511.55, 'Gain': 1500,
                      'FF_Gains': Readout_2345_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4238.4, 'sigma': 0.018, 'Gain': 14000},
          'Pulse_FF': Readout_2345_FF},
    '4': {'Readout': {'Frequency': 7568.1, 'Gain': 1800,
                      'FF_Gains': Readout_2345_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3829.4, 'sigma': 0.01, 'Gain': 20033},
          'Pulse_FF': Readout_2345_FF},
    '5': {'Readout': {'Frequency': 7362.6, 'Gain': 1600,
                      'FF_Gains': Readout_2345_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3621.5, 'sigma': 0.01, 'Gain': 12670},
          'Pulse_FF': Readout_2345_FF},
    '6': {'Readout': {'Frequency': 7441.65, 'Gain': 2700,
                      'FF_Gains': Readout_2345_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4130.4, 'sigma': 0.01, 'Gain': 19333},
          'Pulse_FF': Readout_2345_FF},
    '7': {'Readout': {'Frequency': 7253.9, 'Gain': 1100,
                      'FF_Gains': Readout_2345_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3951.8, 'sigma': 0.01, 'Gain': 8300},
          'Pulse_FF': Readout_2345_FF},
    '8': {'Readout': {'Frequency': 7308.4, 'Gain': 1700,
                      'FF_Gains': Readout_2345_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3515.5, 'sigma': 0.015, 'Gain': 16115},
          'Pulse_FF': Readout_2345_FF},
}

