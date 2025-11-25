from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import BaseConfig
import numpy as np


Readout_2345_FF = np.array([-12000, 4000, 17468, -7500, -14000, 12000, 0, -18000])

Readout_2345_FF = np.array([-12000, 4000, 17468, -7500, -14000, 11500, 0, -18000])

Readout_2345_FF = np.array([-12000, 4000, 17468, -7500, -14000, 11500, 1000, -18000])

Readout_2345_FF = np.array([-12000, 4000, 17468, -7000, -14000, 11500, 1000, -18000])



BS2345_Readout = {
    '1': {'Readout': {'Frequency': 7121.1, 'Gain': 714,
                      'FF_Gains': Readout_2345_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3732.0, 'sigma': 0.03, 'Gain': 8687},
          'Pulse_FF': Readout_2345_FF},
    '2': {'Readout': {'Frequency': 7077.3, 'Gain': 1400,
                      'FF_Gains': Readout_2345_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4130.5, 'sigma': 0.03, 'Gain': 6026},
          'Pulse_FF': Readout_2345_FF},
    '3': {'Readout': {'Frequency': 7511.6, 'Gain': 1400,
                      'FF_Gains': Readout_2345_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4351.6, 'sigma': 0.03, 'Gain': 8595},
          'Pulse_FF': Readout_2345_FF},
    '4': {'Readout': {'Frequency': 7568.1, 'Gain': 1400,
                      'FF_Gains': Readout_2345_FF, 'Readout_Time': 2.5, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3871.6, 'sigma': 0.03, 'Gain': 5956},
          'Pulse_FF': Readout_2345_FF},
    '5': {'Readout': {'Frequency': 7363.2, 'Gain': 1400,
                      'FF_Gains': Readout_2345_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3660.5, 'sigma': 0.03, 'Gain': 8592},
          'Pulse_FF': Readout_2345_FF},
    '6': {'Readout': {'Frequency': 7442.0, 'Gain': 1400,
                      'FF_Gains': Readout_2345_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4252.7, 'sigma': 0.03, 'Gain': 8373},
          'Pulse_FF': Readout_2345_FF},
    '7': {'Readout': {'Frequency': 7253.8, 'Gain': 885,
                      'FF_Gains': Readout_2345_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3986.8, 'sigma': 0.03, 'Gain': 6518},
          'Pulse_FF': Readout_2345_FF},
    '8': {'Readout': {'Frequency': 7308.7, 'Gain': 1228,
                      'FF_Gains': Readout_2345_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3560.3, 'sigma': 0.03, 'Gain': 6348},
          'Pulse_FF': Readout_2345_FF},
}

