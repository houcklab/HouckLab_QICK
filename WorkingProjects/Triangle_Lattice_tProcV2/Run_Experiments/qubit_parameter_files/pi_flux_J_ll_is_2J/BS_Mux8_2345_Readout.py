from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import BaseConfig
import numpy as np


Readout_2345_FF = np.array([-12000, 4000, 17468, -7500, -14000, 12000, 0, -18000])



BS2345_Readout = {
    '1': {'Readout': {'Frequency': 7121.1, 'Gain': 714,
                      'FF_Gains': Readout_2345_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3735.9, 'sigma': 0.03, 'Gain': 7704},
          'Pulse_FF': Readout_2345_FF},
    '2': {'Readout': {'Frequency': 7077.9, 'Gain': 1228,
                      'FF_Gains': Readout_2345_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4136.0, 'sigma': 0.03, 'Gain': 5049},
          'Pulse_FF': Readout_2345_FF},
    '3': {'Readout': {'Frequency': 7511.1, 'Gain': 885,
                      'FF_Gains': Readout_2345_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4361.2, 'sigma': 0.03, 'Gain': 8869},
          'Pulse_FF': Readout_2345_FF},
    '4': {'Readout': {'Frequency': 7567.9, 'Gain': 1400,
                      'FF_Gains': Readout_2345_FF, 'Readout_Time': 2.5, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3870.3, 'sigma': 0.03, 'Gain': 10024},
          'Pulse_FF': Readout_2345_FF},
    '5': {'Readout': {'Frequency': 7362.5, 'Gain': 928,
                      'FF_Gains': Readout_2345_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3680.1, 'sigma': 0.03, 'Gain': 11155},
          'Pulse_FF': Readout_2345_FF},
    '6': {'Readout': {'Frequency': 7441.6, 'Gain': 757,
                      'FF_Gains': Readout_2345_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4271.6, 'sigma': 0.03, 'Gain': 9914},
          'Pulse_FF': Readout_2345_FF},
    '7': {'Readout': {'Frequency': 7253.8, 'Gain': 714,
                      'FF_Gains': Readout_2345_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3969.8, 'sigma': 0.03, 'Gain': 6416},
          'Pulse_FF': Readout_2345_FF},
    '8': {'Readout': {'Frequency': 7308.6, 'Gain': 1228,
                      'FF_Gains': Readout_2345_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3588.7, 'sigma': 0.03, 'Gain': 5990},
          'Pulse_FF': Readout_2345_FF},
}

