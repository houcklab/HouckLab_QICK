from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import BaseConfig
import numpy as np


Readout_2345_FF = np.array([-12000, 4000, 17468, -7500, -14000, 12000, 0, -18000])

Readout_2345_FF = np.array([-12000, 4000, 17468, -7500, -14000, 11500, 0, -18000])

Readout_2345_FF = np.array([-12000, 4000, 17468, -7500, -14000, 11500, 1000, -18000])

Readout_2345_FF = np.array([-12000, 5354, 25392, -7128, -25700, 14170, 1000, -16132])



BS2345_Readout = {
    '1': {'Readout': {'Frequency': 7121.1, 'Gain': 1500,
                      'FF_Gains': Readout_2345_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3731.0, 'sigma': 0.03, 'Gain': 5255},
          'Pulse_FF': Readout_2345_FF},
    '2': {'Readout': {'Frequency': 7077.9, 'Gain': 2400,
                      'FF_Gains': Readout_2345_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4160.0, 'sigma': 0.03, 'Gain': 2443},
          'Pulse_FF': Readout_2345_FF},
    '3': {'Readout': {'Frequency': 7511.4, 'Gain': 900,
                      'FF_Gains': Readout_2345_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4395.5, 'sigma': 0.03, 'Gain': 6300},
          'Pulse_FF': Readout_2345_FF},
    '4': {'Readout': {'Frequency': 7568.0, 'Gain': 2400,
                      'FF_Gains': Readout_2345_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3867.4, 'sigma': 0.03, 'Gain': 5665},
          'Pulse_FF': Readout_2345_FF},
    '5': {'Readout': {'Frequency': 7362.9, 'Gain': 2100,
                      'FF_Gains': Readout_2345_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3521.4, 'sigma': 0.03, 'Gain': 5569},
          'Pulse_FF': Readout_2345_FF},
    '6': {'Readout': {'Frequency': 7441.8, 'Gain': 1500,
                      'FF_Gains': Readout_2345_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4292.9, 'sigma': 0.03, 'Gain': 3441},
          'Pulse_FF': Readout_2345_FF},
    '7': {'Readout': {'Frequency': 7254.1, 'Gain': 1200,
                      'FF_Gains': Readout_2345_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3986.8, 'sigma': 0.03, 'Gain': 4126},
          'Pulse_FF': Readout_2345_FF},
    '8': {'Readout': {'Frequency': 7308.7, 'Gain': 1800,
                      'FF_Gains': Readout_2345_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3592.9, 'sigma': 0.03, 'Gain': 3806},
          'Pulse_FF': Readout_2345_FF},
}

