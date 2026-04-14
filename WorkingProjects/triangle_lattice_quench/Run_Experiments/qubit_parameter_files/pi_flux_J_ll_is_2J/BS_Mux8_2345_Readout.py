from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import BaseConfig
import numpy as np


Readout_2345_FF = np.array([-12000, 4000, 17468, -7500, -14000, 12000, 0, -18000])



BS2345_Readout = {
    '1': {'Readout': {'Frequency': 7121.1, 'Gain': 1500,
                      'FF_Gains': Readout_2345_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3738.4, 'sigma': 0.03, 'Gain': 4687},
          'Pulse_FF': Readout_2345_FF},
    '2': {'Readout': {'Frequency': 7077.9, 'Gain': 2100,
                      'FF_Gains': Readout_2345_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4136.3, 'sigma': 0.03, 'Gain': 3041},
          'Pulse_FF': Readout_2345_FF},
    '3': {'Readout': {'Frequency': 7511.1, 'Gain': 1500,
                      'FF_Gains': Readout_2345_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4361.5, 'sigma': 0.03, 'Gain': 4878},
          'Pulse_FF': Readout_2345_FF},
    '4': {'Readout': {'Frequency': 7567.9, 'Gain': 2400,
                      'FF_Gains': Readout_2345_FF, 'Readout_Time': 2.5, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3866.1, 'sigma': 0.03, 'Gain': 6600},
          'Pulse_FF': Readout_2345_FF},
    '5': {'Readout': {'Frequency': 7362.8, 'Gain': 2400,
                      'FF_Gains': Readout_2345_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3680.4, 'sigma': 0.03, 'Gain': 6412},
          'Pulse_FF': Readout_2345_FF},
    '6': {'Readout': {'Frequency': 7441.9, 'Gain': 1500,
                      'FF_Gains': Readout_2345_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4268.6, 'sigma': 0.03, 'Gain': 4914},
          'Pulse_FF': Readout_2345_FF},
    '7': {'Readout': {'Frequency': 7253.8, 'Gain': 1200,
                      'FF_Gains': Readout_2345_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3967.1, 'sigma': 0.03, 'Gain': 3514},
          'Pulse_FF': Readout_2345_FF},
    '8': {'Readout': {'Frequency': 7308.6, 'Gain': 1800,
                      'FF_Gains': Readout_2345_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3587.0, 'sigma': 0.03, 'Gain': 3771},
          'Pulse_FF': Readout_2345_FF},

}



