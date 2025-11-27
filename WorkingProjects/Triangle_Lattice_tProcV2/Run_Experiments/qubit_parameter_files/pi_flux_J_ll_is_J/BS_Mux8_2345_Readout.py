from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import BaseConfig
import numpy as np


Readout_2345_FF = np.array([-12000, 4000, 17468, -7500, -14000, 12000, 0, -18000])

Readout_2345_FF = np.array([-12000, 4000, 17468, -7500, -14000, 11500, 0, -18000])

Readout_2345_FF = np.array([-12000, 4000, 17468, -7500, -14000, 11500, 1000, -18000])

Readout_2345_FF = np.array([-12000, 4000, 17468, -7000, -15200, 11500, 1000, -18000])



BS2345_Readout = {
    '1': {'Readout': {'Frequency': 7121.1, 'Gain': 714,
                      'FF_Gains': Readout_2345_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3731.0, 'sigma': 0.03, 'Gain': 8353},
          'Pulse_FF': Readout_2345_FF},
    '2': {'Readout': {'Frequency': 7077.55, 'Gain': 1000,
                      'FF_Gains': Readout_2345_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4130.5, 'sigma': 0.03, 'Gain': 6026},
          'Pulse_FF': Readout_2345_FF},
    '3': {'Readout': {'Frequency': 7511.4, 'Gain': 885,
                      'FF_Gains': Readout_2345_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4351.6, 'sigma': 0.03, 'Gain': 7928},
          'Pulse_FF': Readout_2345_FF},
    '4': {'Readout': {'Frequency': 7568.1, 'Gain': 1200,
                      'FF_Gains': Readout_2345_FF, 'Readout_Time': 2.5, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3871.6, 'sigma': 0.03, 'Gain': 10789},
          'Pulse_FF': Readout_2345_FF},
    '5': {'Readout': {'Frequency': 7362.6, 'Gain': 850,
                      'FF_Gains': Readout_2345_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3635.0, 'sigma': 0.03, 'Gain': 8000},
          'Pulse_FF': Readout_2345_FF},
    '6': {'Readout': {'Frequency': 7441.5, 'Gain': 1200,
                      'FF_Gains': Readout_2345_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4253.3, 'sigma': 0.03, 'Gain': 8573},
          'Pulse_FF': Readout_2345_FF},
    '7': {'Readout': {'Frequency': 7254.06, 'Gain': 400,
                      'FF_Gains': Readout_2345_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3986.8, 'sigma': 0.03, 'Gain': 6258},
          'Pulse_FF': Readout_2345_FF},
    '8': {'Readout': {'Frequency': 7308.7, 'Gain': 1228,
                      'FF_Gains': Readout_2345_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3560.3, 'sigma': 0.03, 'Gain': 6348},
          'Pulse_FF': Readout_2345_FF},
}

