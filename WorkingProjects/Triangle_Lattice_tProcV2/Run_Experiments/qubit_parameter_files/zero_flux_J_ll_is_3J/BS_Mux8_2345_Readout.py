from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import BaseConfig
import numpy as np



Readout_2345_FF = np.array([-11636, 2296, 10900, -7061, -14428, 9517, 843, -21379])
# Readout_2345_FF = np.array([-26873, -29001, -25392, -27560, -25700, -28060, -25722, -24395])

# (3725.0, 4060.0, 4240.0, 3835.0, 3621.0, 4139.0, 3953.0, 3512.0)
BS2345_Readout = {
    '1': {'Readout': {'Frequency': 7121.1, 'Gain': 1800,
                      'FF_Gains': Readout_2345_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3715.0, 'sigma': 0.015, 'Gain': 13447},
          'Pulse_FF': Readout_2345_FF},
    '2': {'Readout': {'Frequency': 7078.1, 'Gain': 2100,
                      'FF_Gains': Readout_2345_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4047.4, 'sigma': 0.01, 'Gain': 9381},
          'Pulse_FF': Readout_2345_FF},
    '3': {'Readout': {'Frequency': 7511.8, 'Gain': 2400,
                      'FF_Gains': Readout_2345_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4100.7, 'sigma': 0.018, 'Gain': 17169},
          'Pulse_FF': Readout_2345_FF},
    '4': {'Readout': {'Frequency': 7568.1, 'Gain': 2400,
                      'FF_Gains': Readout_2345_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3779.3, 'sigma': 0.01, 'Gain': 18104},
          'Pulse_FF': Readout_2345_FF},
    '5': {'Readout': {'Frequency': 7362.9, 'Gain': 2400,
                      'FF_Gains': Readout_2345_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3617.1, 'sigma': 0.01, 'Gain': 12324},
          'Pulse_FF': Readout_2345_FF},
    '6': {'Readout': {'Frequency': 7441.6, 'Gain': 2400,
                      'FF_Gains': Readout_2345_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4078.4, 'sigma': 0.01, 'Gain': 7578},
          'Pulse_FF': Readout_2345_FF},
    '7': {'Readout': {'Frequency': 7253.9, 'Gain': 900,
                      'FF_Gains': Readout_2345_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3941.3, 'sigma': 0.01, 'Gain': 7742},
          'Pulse_FF': Readout_2345_FF},
    '8': {'Readout': {'Frequency': 7308.5, 'Gain': 2400,
                      'FF_Gains': Readout_2345_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3516.0, 'sigma': 0.015, 'Gain': 16836},
          'Pulse_FF': Readout_2345_FF},
}

